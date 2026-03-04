#!/usr/bin/env python3
"""Shared helpers for eval acceptance report scripts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
_RUN_EVAL_PATH_PATTERN = re.compile(r"(^|/)reports/runs/(?P<run_id>[^/]+)/eval/")


@dataclass(frozen=True)
class EvalInputSelector:
    eval_paths: list[str]
    run_ids: list[str]
    eval_file_name: str


@dataclass(frozen=True)
class OutputPathRequest:
    output_json: str
    output_md: str
    output_run_id: str
    input_paths: list[Path]
    report_stem: str


def repo_root() -> Path:
    return REPO_ROOT


def load_json_object(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ValueError(f"input_file_missing:{path}") from exc
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"input_file_invalid_json:{path}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"input_file_not_object:{path}")
    return parsed


def resolve_eval_input_paths(selector: EvalInputSelector) -> list[Path]:
    resolved: list[Path] = []
    for raw_path in selector.eval_paths:
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            candidate = REPO_ROOT / candidate
        resolved.append(candidate.resolve())
    for run_id in selector.run_ids:
        normalized_run_id = run_id.strip()
        if not normalized_run_id:
            continue
        resolved.append((REPO_ROOT / "reports" / "runs" / normalized_run_id / "eval" / selector.eval_file_name).resolve())
    if not resolved:
        raise ValueError("eval_input_missing:set_eval_path_or_run_id")
    return resolved


def infer_run_id_from_path(path: Path) -> str:
    matched = _RUN_EVAL_PATH_PATTERN.search(path.as_posix())
    if not matched:
        return ""
    return str(matched.group("run_id")).strip()


def default_report_output_paths(request: OutputPathRequest) -> tuple[Path, Path]:
    json_path = _optional_output_path(request.output_json)
    md_path = _optional_output_path(request.output_md)
    if json_path is not None and md_path is not None:
        return json_path, md_path
    if json_path is not None or md_path is not None:
        raise ValueError("output_paths_incomplete:set_both_output_json_and_output_md")

    base_dir = _default_output_dir(output_run_id=request.output_run_id, input_paths=request.input_paths)
    return (
        (base_dir / f"{request.report_stem}.json").resolve(),
        (base_dir / f"{request.report_stem}.md").resolve(),
    )


def _optional_output_path(value: str) -> Path | None:
    normalized = value.strip()
    if not normalized:
        return None
    candidate = Path(normalized).expanduser()
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    return candidate.resolve()


def _default_output_dir(*, output_run_id: str, input_paths: list[Path]) -> Path:
    normalized_run_id = output_run_id.strip()
    if normalized_run_id:
        return (REPO_ROOT / "reports" / "runs" / normalized_run_id / "eval").resolve()

    if len(input_paths) != 1:
        raise ValueError("output_path_required_for_multiple_inputs")

    only_input = input_paths[0]
    return only_input.parent.resolve()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_markdown(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = text if text.endswith("\n") else f"{text}\n"
    path.write_text(normalized, encoding="utf-8")
