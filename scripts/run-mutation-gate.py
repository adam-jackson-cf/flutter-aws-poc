#!/usr/bin/env python3
from __future__ import annotations

import ast
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class MutationTarget:
    file_path: str
    test_paths: tuple[str, ...]
    package_dirs: tuple[str, ...]
    coverage_target: str


@dataclass(frozen=True)
class MutationCandidate:
    index: int
    kind: str
    lineno: int


@dataclass(frozen=True)
class MutationResult:
    file_path: str
    kind: str
    lineno: int
    status: str
    exit_code: int


COMPARISON_SWAP: dict[type[ast.cmpop], Callable[[], ast.cmpop]] = {
    ast.Eq: ast.NotEq,
    ast.NotEq: ast.Eq,
    ast.Lt: ast.GtE,
    ast.GtE: ast.Lt,
    ast.Gt: ast.LtE,
    ast.LtE: ast.Gt,
    ast.Is: ast.IsNot,
    ast.IsNot: ast.Is,
    ast.In: ast.NotIn,
    ast.NotIn: ast.In,
}

BINOP_SWAP: dict[type[ast.operator], Callable[[], ast.operator]] = {
    ast.Add: ast.Sub,
    ast.Sub: ast.Add,
    ast.Mult: ast.FloorDiv,
    ast.FloorDiv: ast.Mult,
}

TARGETS: tuple[MutationTarget, ...] = (
    MutationTarget(
        file_path="evals/run_eval.py",
        test_paths=("tests/test_evals_run_eval_full.py",),
        package_dirs=("evals", "runtime", "aws"),
        coverage_target="evals",
    ),
    MutationTarget(
        file_path="runtime/sop_agent/main.py",
        test_paths=("tests/test_runtime_core_full.py",),
        package_dirs=("runtime", "evals", "aws"),
        coverage_target="runtime",
    ),
)


class CandidateCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.candidates: list[MutationCandidate] = []
        self.index = 0

    def _add(self, node: ast.AST, kind: str) -> None:
        self.candidates.append(
            MutationCandidate(
                index=self.index,
                kind=kind,
                lineno=getattr(node, "lineno", 0),
            )
        )
        self.index += 1

    def visit_Compare(self, node: ast.Compare) -> None:
        if len(node.ops) == 1 and type(node.ops[0]) in COMPARISON_SWAP:
            self._add(node, f"compare:{type(node.ops[0]).__name__}")
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        if isinstance(node.op, (ast.And, ast.Or)):
            self._add(node, f"boolop:{type(node.op).__name__}")
        self.generic_visit(node)

    def visit_UnaryOp(self, node: ast.UnaryOp) -> None:
        if isinstance(node.op, ast.Not):
            self._add(node, "unary:not")
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        if type(node.op) in BINOP_SWAP:
            self._add(node, f"binop:{type(node.op).__name__}")
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, bool):
            self._add(node, "const:bool")
        self.generic_visit(node)


class SingleMutationTransformer(ast.NodeTransformer):
    def __init__(self, target_index: int) -> None:
        self.target_index = target_index
        self.current_index = 0
        self.applied = False

    def _check_target(self) -> bool:
        idx = self.current_index
        self.current_index += 1
        return idx == self.target_index

    def visit_Compare(self, node: ast.Compare) -> ast.AST:
        node = self.generic_visit(node)
        if len(node.ops) == 1 and type(node.ops[0]) in COMPARISON_SWAP:
            if self._check_target():
                self.applied = True
                return ast.copy_location(
                    ast.Compare(
                        left=node.left,
                        ops=[COMPARISON_SWAP[type(node.ops[0])]()],
                        comparators=node.comparators,
                    ),
                    node,
                )
        return node

    def visit_BoolOp(self, node: ast.BoolOp) -> ast.AST:
        node = self.generic_visit(node)
        if isinstance(node.op, (ast.And, ast.Or)):
            if self._check_target():
                self.applied = True
                new_op = ast.Or() if isinstance(node.op, ast.And) else ast.And()
                return ast.copy_location(ast.BoolOp(op=new_op, values=node.values), node)
        return node

    def visit_UnaryOp(self, node: ast.UnaryOp) -> ast.AST:
        node = self.generic_visit(node)
        if isinstance(node.op, ast.Not):
            if self._check_target():
                self.applied = True
                return ast.copy_location(node.operand, node)
        return node

    def visit_BinOp(self, node: ast.BinOp) -> ast.AST:
        node = self.generic_visit(node)
        if type(node.op) in BINOP_SWAP:
            if self._check_target():
                self.applied = True
                return ast.copy_location(
                    ast.BinOp(left=node.left, op=BINOP_SWAP[type(node.op)](), right=node.right),
                    node,
                )
        return node

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        node = self.generic_visit(node)
        if isinstance(node.value, bool):
            if self._check_target():
                self.applied = True
                return ast.copy_location(ast.Constant(value=not node.value), node)
        return node


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def run_baseline_tests(root: Path, target: MutationTarget, timeout_seconds: int) -> None:
    cmd = [sys.executable, "-m", "pytest", "-q", "--maxfail=1", *target.test_paths]
    completed = subprocess.run(cmd, cwd=str(root), check=False, capture_output=True, text=True, timeout=timeout_seconds)
    if completed.returncode != 0:
        print(completed.stdout)
        print(completed.stderr, file=sys.stderr)
        raise RuntimeError(f"Baseline tests failed for {target.file_path}")


def covered_lines_for_target(root: Path, target: MutationTarget, timeout_seconds: int) -> set[int]:
    with tempfile.NamedTemporaryFile(prefix="mutation-cov-", suffix=".json", delete=False) as handle:
        coverage_json = Path(handle.name)
    try:
        cmd = [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "--maxfail=1",
            f"--cov={target.coverage_target}",
            "--cov-config=.coveragerc",
            f"--cov-report=json:{coverage_json}",
            *target.test_paths,
        ]
        completed = subprocess.run(
            cmd,
            cwd=str(root),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        if completed.returncode != 0:
            print(completed.stdout)
            print(completed.stderr, file=sys.stderr)
            raise RuntimeError(f"Coverage baseline failed for {target.file_path}")

        payload = json.loads(coverage_json.read_text(encoding="utf-8"))
        normalized_target = target.file_path.replace("\\", "/")
        for file_path, stats in payload.get("files", {}).items():
            normalized_file = file_path.replace("\\", "/")
            if normalized_file.endswith(normalized_target):
                return {int(line) for line in stats.get("executed_lines", [])}
        raise RuntimeError(f"Coverage report did not include {target.file_path}")
    finally:
        if coverage_json.exists():
            coverage_json.unlink()


def collect_candidates(source: str) -> list[MutationCandidate]:
    tree = ast.parse(source)
    collector = CandidateCollector()
    collector.visit(tree)
    return collector.candidates


def apply_mutation(source: str, candidate_index: int) -> str:
    original_tree = ast.parse(source)
    tree = copy.deepcopy(original_tree)
    transformer = SingleMutationTransformer(target_index=candidate_index)
    mutated_tree = transformer.visit(tree)
    ast.fix_missing_locations(mutated_tree)
    if not transformer.applied:
        raise RuntimeError(f"Failed to apply mutation index {candidate_index}")
    return ast.unparse(mutated_tree) + "\n"


def run_mutant(
    root: Path,
    target: MutationTarget,
    mutated_content: str,
    timeout_seconds: int,
) -> tuple[str, int]:
    with tempfile.TemporaryDirectory(prefix="mutation-gate-") as tmp:
        tmp_path = Path(tmp)
        for package_dir in target.package_dirs:
            shutil.copytree(root / package_dir, tmp_path / package_dir)
        shutil.copytree(root / "tests", tmp_path / "tests")
        mutated_file = tmp_path / target.file_path
        mutated_file.parent.mkdir(parents=True, exist_ok=True)
        mutated_file.write_text(mutated_content, encoding="utf-8")

        env = os.environ.copy()
        env["PYTHONPATH"] = f"{tmp_path}:{env.get('PYTHONPATH', '')}".rstrip(":")
        cmd = [sys.executable, "-m", "pytest", "-q", "--maxfail=1", *target.test_paths]
        try:
            completed = subprocess.run(
                cmd,
                cwd=str(tmp_path),
                env=env,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return ("timeout", 124)

        if completed.returncode == 0:
            return ("survived", 0)
        return ("killed", completed.returncode)


def main() -> int:
    root = repo_root()
    max_mutants_per_file = int(os.environ.get("MUTATION_MAX_MUTANTS_PER_FILE", "40"))
    mutation_score_target = float(os.environ.get("MUTATION_SCORE_TARGET", "80"))
    timeout_seconds = int(os.environ.get("MUTATION_TEST_TIMEOUT_SECONDS", "60"))

    all_results: list[MutationResult] = []
    for target in TARGETS:
        target_path = root / target.file_path
        source = target_path.read_text(encoding="utf-8")
        candidates = collect_candidates(source)
        covered_lines = covered_lines_for_target(root=root, target=target, timeout_seconds=timeout_seconds)
        selected = [candidate for candidate in candidates if candidate.lineno in covered_lines][:max_mutants_per_file]
        if not selected:
            print(f"No mutation candidates found for {target.file_path}", file=sys.stderr)
            return 1

        run_baseline_tests(root=root, target=target, timeout_seconds=timeout_seconds)

        print(f"Mutating {target.file_path}: {len(selected)} candidate(s)")
        for candidate in selected:
            mutated_content = apply_mutation(source=source, candidate_index=candidate.index)
            status, exit_code = run_mutant(
                root=root,
                target=target,
                mutated_content=mutated_content,
                timeout_seconds=timeout_seconds,
            )
            all_results.append(
                MutationResult(
                    file_path=target.file_path,
                    kind=candidate.kind,
                    lineno=candidate.lineno,
                    status=status,
                    exit_code=exit_code,
                )
            )

    killed = sum(1 for result in all_results if result.status == "killed")
    survived = sum(1 for result in all_results if result.status == "survived")
    timeout = sum(1 for result in all_results if result.status == "timeout")
    total = len(all_results)
    score = 0.0 if total == 0 else (killed / total) * 100.0

    summary = {
        "target_score": mutation_score_target,
        "score": score,
        "total": total,
        "killed": killed,
        "survived": survived,
        "timeout": timeout,
        "max_mutants_per_file": max_mutants_per_file,
        "results": [
            {
                "file_path": result.file_path,
                "kind": result.kind,
                "lineno": result.lineno,
                "status": result.status,
                "exit_code": result.exit_code,
            }
            for result in all_results
        ],
    }

    output_path = root / "reports" / "mutation-gate-summary.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(
        "Mutation summary:",
        f"score={score:.2f}%",
        f"target={mutation_score_target:.2f}%",
        f"killed={killed}",
        f"survived={survived}",
        f"timeout={timeout}",
        f"total={total}",
    )
    print(f"Mutation summary JSON: {output_path}")

    if timeout > 0:
        print(f"Mutation gate failed: {timeout} mutant runs timed out", file=sys.stderr)
        return 1
    if score < mutation_score_target:
        print(
            f"Mutation gate failed: score {score:.2f}% is below target {mutation_score_target:.2f}%",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
