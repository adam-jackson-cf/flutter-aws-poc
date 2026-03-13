"""Load and validate Flutter design artefacts."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


@dataclass(frozen=True)
class ArtifactRecord:
    key: str
    path: Path
    payload: dict[str, Any]


@dataclass(frozen=True)
class DesignAdapter:
    source_root: Path
    artifact_dirs: dict[str, str]
    schema_files: dict[str, str]
    required_identity_tags: tuple[str, ...]
    allowed_execution_scopes: tuple[str, ...]
    workflow_required_risk_tiers: tuple[str, ...]
    published_states: tuple[str, ...]


@dataclass(frozen=True)
class DesignRepository:
    capability_definitions: list[ArtifactRecord]
    safety_envelopes: dict[str, ArtifactRecord]
    workflow_contracts: dict[str, ArtifactRecord]
    evaluation_packs: dict[str, ArtifactRecord]


def load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return payload


def load_adapter(path: Path) -> DesignAdapter:
    payload = load_json_object(path)
    artifact_dirs = _string_dict(payload.get("artifact_dirs"))
    schema_files = _string_dict(payload.get("schema_files"))
    return DesignAdapter(
        source_root=path.resolve().parents[3],
        artifact_dirs=artifact_dirs,
        schema_files=schema_files,
        required_identity_tags=tuple(_string_list(payload.get("required_identity_tags"))),
        allowed_execution_scopes=tuple(_string_list(payload.get("allowed_execution_scopes"))),
        workflow_required_risk_tiers=tuple(_string_list(payload.get("workflow_required_risk_tiers"))),
        published_states=tuple(_string_list(payload.get("published_states"))),
    )


def iter_artifact_files(repo_root: Path, relative_dir: str) -> list[Path]:
    root = repo_root / relative_dir
    if not root.exists():
        return []
    return sorted(
        path
        for path in root.rglob("*.json")
        if all(not part.startswith(".") for part in path.relative_to(root).parts)
    )


def load_schema(repo_root: Path, adapter: DesignAdapter, schema_name: str) -> dict[str, Any]:
    relative_path = adapter.schema_files[schema_name]
    schema_path = adapter.source_root / relative_path
    return load_json_object(schema_path)


def validate_schema_records(
    repo_root: Path,
    adapter: DesignAdapter,
    *,
    artifact_type: str,
    schema_name: str,
    require_files: bool,
) -> tuple[list[ArtifactRecord], list[str]]:
    relative_dir = adapter.artifact_dirs[artifact_type]
    files = iter_artifact_files(repo_root, relative_dir)
    if require_files and not files:
        return [], [f"{relative_dir}: expected at least one JSON artefact"]

    schema = load_schema(repo_root, adapter, schema_name)
    validator = Draft202012Validator(schema)
    records: list[ArtifactRecord] = []
    violations: list[str] = []

    for path in files:
        record, record_violations = _validate_single_record(
            repo_root=repo_root,
            validator=validator,
            artifact_type=artifact_type,
            path=path,
        )
        violations.extend(record_violations)
        if record is not None:
            records.append(record)

    return records, sorted(set(violations))


def load_design_repository(repo_root: Path, adapter: DesignAdapter) -> DesignRepository:
    capability_definitions, capability_violations = validate_schema_records(
        repo_root,
        adapter,
        artifact_type="capability_definitions",
        schema_name="capability_definition",
        require_files=False,
    )
    safety_envelopes, envelope_violations = validate_schema_records(
        repo_root,
        adapter,
        artifact_type="safety_envelopes",
        schema_name="safety_envelope",
        require_files=False,
    )
    workflow_contracts, workflow_violations = validate_schema_records(
        repo_root,
        adapter,
        artifact_type="workflow_contracts",
        schema_name="workflow_contract",
        require_files=False,
    )
    evaluation_packs, evaluation_violations = validate_schema_records(
        repo_root,
        adapter,
        artifact_type="evaluation_packs",
        schema_name="evaluation_pack",
        require_files=False,
    )

    if capability_violations or envelope_violations or workflow_violations or evaluation_violations:
        combined = capability_violations + envelope_violations + workflow_violations + evaluation_violations
        raise ValueError("\n".join(combined))

    return DesignRepository(
        capability_definitions=capability_definitions,
        safety_envelopes={record.key: record for record in safety_envelopes},
        workflow_contracts={record.key: record for record in workflow_contracts},
        evaluation_packs={record.key: record for record in evaluation_packs},
    )


def published_state(record: ArtifactRecord) -> str:
    return str(record.payload["metadata"]["lifecycle_state"])


def artefact_key(payload: dict[str, Any], artifact_type: str) -> str:
    metadata = _dict_value(payload.get("metadata"))
    if artifact_type == "capability_definitions":
        return f"{metadata['capability_id']}@{metadata['version']}"
    if artifact_type == "safety_envelopes":
        return f"{metadata['envelope_id']}@{metadata['version']}"
    if artifact_type == "workflow_contracts":
        return f"{metadata['workflow_id']}@{metadata['version']}"
    if artifact_type == "evaluation_packs":
        return f"{metadata['pack_id']}@{metadata['version']}"
    raise KeyError(f"unsupported artefact type: {artifact_type}")


def _dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_dict(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError("expected a JSON object of string values")
    return {str(key): str(item) for key, item in value.items()}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _validate_single_record(
    *,
    repo_root: Path,
    validator: Draft202012Validator,
    artifact_type: str,
    path: Path,
) -> tuple[ArtifactRecord | None, list[str]]:
    try:
        payload = load_json_object(path)
    except ValueError as exc:
        return None, [str(exc)]

    violations = _schema_violations(repo_root=repo_root, validator=validator, path=path, payload=payload)
    if violations:
        return None, violations

    key = artefact_key(payload, artifact_type)
    return ArtifactRecord(key=key, path=path, payload=payload), []


def _schema_violations(
    *,
    repo_root: Path,
    validator: Draft202012Validator,
    path: Path,
    payload: dict[str, Any],
) -> list[str]:
    violations: list[str] = []
    for error in sorted(validator.iter_errors(payload), key=lambda item: list(item.path)):
        location = ".".join(str(part) for part in error.path) or "$"
        violations.append(f"{path.relative_to(repo_root).as_posix()}:{location}: {error.message}")
    return violations
