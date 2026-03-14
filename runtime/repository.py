"""Artifact repository for published governed workflow definitions."""

from __future__ import annotations

from collections.abc import Callable
import json
from pathlib import Path
from typing import Any

from .models import (
    CapabilityDefinition,
    EvaluationPack,
    WorkflowContract,
    parse_capability_definition,
    parse_evaluation_pack,
    parse_workflow_contract,
)


class GovernedArtifactRepository:
    """Loads published workflow artifacts from the repository tree."""

    def __init__(self, repo_root: str | Path) -> None:
        self.repo_root = Path(repo_root).resolve()
        self._capabilities: dict[str, CapabilityDefinition] | None = None
        self._workflows: dict[str, WorkflowContract] | None = None
        self._evaluation_packs: dict[str, EvaluationPack] | None = None

    @property
    def capability_root(self) -> Path:
        return self.repo_root / "capability-definitions"

    @property
    def workflow_root(self) -> Path:
        return self.repo_root / "workflow-contracts"

    @property
    def evaluation_root(self) -> Path:
        return self.repo_root / "evaluation-packs"

    def list_capabilities(self) -> tuple[CapabilityDefinition, ...]:
        return tuple(self._load_capabilities().values())

    def list_workflows(self) -> tuple[WorkflowContract, ...]:
        return tuple(self._load_workflows().values())

    def list_evaluation_packs(self) -> tuple[EvaluationPack, ...]:
        return tuple(self._load_evaluation_packs().values())

    def get_capability(self, capability_id: str, capability_version: str) -> CapabilityDefinition:
        return self.get_capability_by_ref(f"{capability_id}@{capability_version}")

    def get_capability_by_ref(self, capability_ref: str) -> CapabilityDefinition:
        split_ref(capability_ref)
        capability = self._load_capabilities().get(capability_ref)
        if capability is None:
            raise KeyError(f"Unknown capability: {capability_ref}")
        return capability

    def get_workflow_contract(self, workflow_ref: str) -> WorkflowContract:
        split_ref(workflow_ref)
        workflow = self._load_workflows().get(workflow_ref)
        if workflow is None:
            raise KeyError(f"Unknown workflow contract: {workflow_ref}")
        return workflow

    def get_evaluation_pack(self, evaluation_ref: str) -> EvaluationPack:
        split_ref(evaluation_ref)
        pack = self._load_evaluation_packs().get(evaluation_ref)
        if pack is None:
            raise KeyError(f"Unknown evaluation pack: {evaluation_ref}")
        return pack

    def resolve_dataset_paths(self, evaluation_pack: EvaluationPack) -> tuple[Path, ...]:
        datasets = evaluation_pack.payload.get("datasets", [])
        resolved: list[Path] = []
        if not isinstance(datasets, list):
            return ()
        for dataset in datasets:
            if not isinstance(dataset, dict):
                continue
            path_value = str(dataset.get("path", "")).strip()
            if not path_value:
                continue
            dataset_path = (self.repo_root / path_value).resolve()
            if not dataset_path.is_file():
                raise FileNotFoundError(
                    f"{evaluation_pack.pack_id}: missing dataset file {dataset_path}"
                )
            resolved.append(dataset_path)
        return tuple(resolved)

    def publication_manifest(self) -> dict[str, Any]:
        """Return a deterministic publishable artifact manifest."""

        capabilities = []
        for capability in sorted(
            self.list_capabilities(),
            key=lambda item: (item.capability_id, item.version),
        ):
            evaluation_pack = self.get_evaluation_pack(capability.evaluation_pack_ref)
            dataset_paths = self.resolve_dataset_paths(evaluation_pack)
            capabilities.append(
                {
                    "capability_id": capability.capability_id,
                    "version": capability.version,
                    "risk_tier": capability.risk_tier,
                    "workflow_contract_ref": capability.workflow_contract_ref,
                    "evaluation_pack_ref": capability.evaluation_pack_ref,
                    "prompt_ref": capability.prompt_ref,
                    "prompt_sha256": capability.prompt_sha256,
                    "scopes": list(capability.scopes),
                    "delegated_capability_refs": list(capability.delegated_capability_refs),
                    "tool_bindings": [
                        {
                            "tool_id": binding.tool_id,
                            "kind": binding.kind,
                            "action_class": binding.action_class,
                        }
                        for binding in capability.tool_bindings
                    ],
                    "datasets": [
                        str(path.relative_to(self.repo_root))
                        for path in dataset_paths
                    ],
                }
            )

        workflows = [
            {
                "workflow_id": workflow.workflow_id,
                "version": workflow.version,
                "risk_tier": workflow.risk_tier,
                "step_modes": [step.mode for step in workflow.steps],
            }
            for workflow in sorted(
                self.list_workflows(),
                key=lambda item: (item.workflow_id, item.version),
            )
        ]

        evaluation_packs = [
            {
                "pack_id": pack.pack_id,
                "version": pack.version,
                "capability_ref": pack.capability_ref,
            }
            for pack in sorted(
                self.list_evaluation_packs(),
                key=lambda item: (item.pack_id, item.version),
            )
        ]

        return {
            "artifact_root": ".",
            "capabilities": capabilities,
            "workflow_contracts": workflows,
            "evaluation_packs": evaluation_packs,
        }

    def _load_capabilities(self) -> dict[str, CapabilityDefinition]:
        if self._capabilities is None:
            self._capabilities = self._load_directory(
                self.capability_root,
                parse_capability_definition,
                key_builder=lambda record: str(record.capability_ref),
                artifact_label="capability ref",
            )
        return self._capabilities

    def _load_workflows(self) -> dict[str, WorkflowContract]:
        if self._workflows is None:
            self._workflows = self._load_directory(
                self.workflow_root,
                parse_workflow_contract,
                key_builder=lambda record: f"{record.workflow_id}@{record.version}",
                artifact_label="workflow contract ref",
            )
        return self._workflows

    def _load_evaluation_packs(self) -> dict[str, EvaluationPack]:
        if self._evaluation_packs is None:
            self._evaluation_packs = self._load_directory(
                self.evaluation_root,
                parse_evaluation_pack,
                key_builder=lambda record: f"{record.pack_id}@{record.version}",
                artifact_label="evaluation pack ref",
            )
        return self._evaluation_packs

    def _load_directory(
        self,
        root: Path,
        parser: Any,
        *,
        key_builder: Callable[[Any], str],
        artifact_label: str,
    ) -> dict[str, Any]:
        if not root.is_dir():
            return {}
        records: dict[str, Any] = {}
        for path in sorted(root.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            record = parser(payload)
            record_key = key_builder(record)
            if record_key in records:
                raise ValueError(f"Duplicate {artifact_label}: {record_key}")
            records[record_key] = record
        return records


def split_ref(reference: str) -> tuple[str, str]:
    """Split `artifact-id@version` into its two parts."""

    identifier, separator, version = reference.partition("@")
    if not separator or not identifier or not version:
        raise ValueError(f"Invalid artifact reference: {reference}")
    return identifier, version
