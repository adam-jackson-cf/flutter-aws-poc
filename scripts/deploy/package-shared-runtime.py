#!/usr/bin/env python3
"""Package the shared workflow runtime and governed artifacts for AgentCore."""

from __future__ import annotations

import argparse
import shutil
import sys
import zipfile
from pathlib import Path


ARTIFACT_DIRS = (
    "runtime",
    "capability-definitions",
    "safety-envelopes",
    "workflow-contracts",
    "evaluation-packs",
    "datasets",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Package the shared runtime and workflow artifacts into a zip bundle.",
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root containing runtime and governed artifacts.",
    )
    parser.add_argument(
        "--output-zip",
        required=True,
        help="Zip file path to create.",
    )
    parser.add_argument(
        "--staging-dir",
        help="Optional staging directory. Defaults next to output zip.",
    )
    return parser.parse_args()


def package_runtime(*, repo_root: Path, output_zip: Path, staging_dir: Path) -> Path:
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from runtime.bootstrap import bootstrap_scenarios

    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)
    _copy_artifacts(repo_root, staging_dir)

    bootstrap_scenarios(
        repo_root=repo_root,
        output_path=staging_dir / "published-manifest.json",
    )

    output_zip.parent.mkdir(parents=True, exist_ok=True)
    if output_zip.exists():
        output_zip.unlink()
    _write_archive(staging_dir, output_zip)
    return output_zip


def _copy_artifacts(repo_root: Path, staging_dir: Path) -> None:
    for name in ARTIFACT_DIRS:
        source = repo_root / name
        if not source.exists():
            continue
        target = staging_dir / name
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            shutil.copy2(source, target)


def _write_archive(staging_dir: Path, output_zip: Path) -> None:
    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(staging_dir.rglob("*")):
            if path.is_dir():
                continue
            archive.write(path, path.relative_to(staging_dir))


def main() -> None:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    output_zip = Path(args.output_zip).resolve()
    staging_dir = (
        Path(args.staging_dir).resolve()
        if args.staging_dir
        else output_zip.parent / f"{output_zip.stem}-staging"
    )
    package_runtime(repo_root=repo_root, output_zip=output_zip, staging_dir=staging_dir)
    print(output_zip)


if __name__ == "__main__":
    main()
