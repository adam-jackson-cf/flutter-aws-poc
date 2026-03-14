"""Bootstrap helpers for publishing shared workflow scenario manifests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .repository import GovernedArtifactRepository


def publish_manifest(repository: GovernedArtifactRepository) -> dict[str, Any]:
    """Return the deterministic shared workflow publication manifest."""

    return repository.publication_manifest()


def bootstrap_scenarios(
    *,
    repo_root: str | Path,
    output_path: str | Path,
) -> Path:
    """Write the shared workflow publication manifest to disk."""

    repository = GovernedArtifactRepository(repo_root)
    manifest = publish_manifest(repository)
    output = Path(output_path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return output
