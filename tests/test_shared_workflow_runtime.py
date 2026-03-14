from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from runtime.adapters import FixtureBackedMcpAdapter, FixtureBackedRagAdapter, McpInvocation
from runtime.engine import ExecutionContext, _binding_for_tool, _delegated_capability_ref, _hitl_record
from runtime.models import (
    EvaluationPack,
    parse_capability_definition,
    parse_evaluation_pack,
    parse_workflow_contract,
)
from runtime.repository import GovernedArtifactRepository, split_ref
from runtime import (
    SharedWorkflowRuntime,
    bootstrap_scenarios,
    publish_manifest,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def _identity_context() -> dict[str, str]:
    return {
        "tenant_id": "flutter-internal",
        "brand": "shared-platform",
        "role": "operator",
        "use_case": "e2e-validation",
    }


def test_publish_manifest_includes_both_orchestrators() -> None:
    repository = GovernedArtifactRepository(REPO_ROOT)

    manifest = publish_manifest(repository)

    capability_ids = {item["capability_id"] for item in manifest["capabilities"]}
    assert "player-protection-case-orchestrator" in capability_ids
    assert "pr-verifier-orchestrator" in capability_ids
    assert any(
        item["capability_id"] == "pr-verifier-orchestrator" and item["version"] == "1.0.0"
        for item in manifest["capabilities"]
    )
    assert any(
        item["workflow_id"] == "player-protection-case-handling"
        for item in manifest["workflow_contracts"]
    )
    assert any(
        item["workflow_id"] == "pr-verification-review"
        for item in manifest["workflow_contracts"]
    )


def test_bootstrap_scenarios_writes_manifest_to_disk(tmp_path: Path) -> None:
    output_path = bootstrap_scenarios(
        repo_root=REPO_ROOT,
        output_path=tmp_path / "published-manifest.json",
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert output_path.is_file()
    assert payload["artifact_root"] == "."
    assert "repo_root" not in payload
    assert len(payload["capabilities"]) >= 4


def test_repository_resolves_versioned_workflow_and_eval_refs(tmp_path: Path) -> None:
    capability_root = tmp_path / "capability-definitions"
    workflow_root = tmp_path / "workflow-contracts"
    evaluation_root = tmp_path / "evaluation-packs"
    capability_root.mkdir()
    workflow_root.mkdir()
    evaluation_root.mkdir()

    capability_root.joinpath("cap.json").write_text(
        json.dumps(
            {
                "kind": "CapabilityDefinition",
                "metadata": {
                    "capability_id": "custom-capability",
                    "version": "1.0.0",
                    "lifecycle_state": "Published",
                },
                "prompt": {
                    "prompt_ref": "prompts/custom-capability",
                    "prompt_sha256": "a" * 64,
                },
                "governance": {
                    "risk_tier": "R1",
                    "workflow_contract_ref": "wf@1.0.0",
                    "execution_model": {"scopes": ["Reasoning", "Process"]},
                },
                "identity": {
                    "required_tags": ["tenant_id", "brand", "role", "use_case"]
                },
                "tool_bindings": [
                    {
                        "tool_id": "customer-360-reader",
                        "kind": "mcp",
                        "action_class": "read",
                        "requires_identity_context": True,
                    }
                ],
                "evaluation": {"evaluation_pack_ref": "pack@1.0.0"},
            }
        ),
        encoding="utf-8",
    )

    for version in ("1.0.0", "2.0.0"):
        workflow_root.joinpath(f"wf-{version}.json").write_text(
            json.dumps(
                {
                    "kind": "WorkflowContract",
                    "metadata": {"workflow_id": "wf", "version": version},
                    "governance": {"risk_tier": "R1"},
                    "steps": [{"step_id": version, "mode": "automated"}],
                }
            ),
            encoding="utf-8",
        )
        evaluation_root.joinpath(f"pack-{version}.json").write_text(
            json.dumps(
                {
                    "kind": "EvaluationPack",
                    "metadata": {"pack_id": "pack", "version": version},
                    "capability_ref": "custom-capability@1.0.0",
                }
            ),
            encoding="utf-8",
        )

    repository = GovernedArtifactRepository(tmp_path)

    assert repository.get_workflow_contract("wf@1.0.0").version == "1.0.0"
    assert repository.get_evaluation_pack("pack@1.0.0").version == "1.0.0"


def test_player_protection_requires_hitl_before_regulated_write(tmp_path: Path) -> None:
    runtime = SharedWorkflowRuntime(
        repository=GovernedArtifactRepository(REPO_ROOT),
        mcp_adapter=FixtureBackedMcpAdapter(),
        rag_adapter=FixtureBackedRagAdapter(),
        audit_root=tmp_path,
    )

    with pytest.raises(PermissionError, match="Regulated write requires human review approval"):
        runtime.execute(
            "player-protection-case-orchestrator",
            "1.0.0",
            request={
                "case_id": "case-001",
                "customer_id": "customer-001",
                "approved_action": "cool_off",
            },
            identity_context=_identity_context(),
        )


def test_player_protection_records_audit_before_regulated_write(tmp_path: Path) -> None:
    mcp_adapter = FixtureBackedMcpAdapter()
    runtime = SharedWorkflowRuntime(
        repository=GovernedArtifactRepository(REPO_ROOT),
        mcp_adapter=mcp_adapter,
        rag_adapter=FixtureBackedRagAdapter(),
        audit_root=tmp_path,
    )

    execution = runtime.execute(
        "player-protection-case-orchestrator",
        "1.0.0",
        request={
            "case_id": "case-002",
            "customer_id": "customer-002",
            "approved_action": "deposit-limit",
            "human_review": {
                "approved": True,
                "reviewer": "safer-gambling-reviewer",
                "decision_id": "hitl-001",
            },
        },
        identity_context=_identity_context(),
    )

    audit = json.loads(Path(execution["audit_path"]).read_text(encoding="utf-8"))
    write_ahead_index = next(
        index
        for index, event in enumerate(audit["events"])
        if event["event_type"] == "write_ahead_audit_committed"
    )
    regulated_write_index = next(
        index
        for index, event in enumerate(audit["events"])
        if event["event_type"] == "tool_invoked"
        and event["payload"]["tool_id"] == "rg-intervention-write"
    )
    assert write_ahead_index < regulated_write_index
    assert audit["delegations"][0]["capability_id"] == "customer-360-specialist"
    assert audit["delegations"][0]["capability_version"] == "1.0.0"
    assert execution["result"]["regulated_write"]["status"] == "committed"
    assert len(mcp_adapter.writes) == 1
    assert mcp_adapter.writes[0]["tool_id"] == "rg-intervention-write"


def test_pr_verifier_rejects_internal_write_without_approval(tmp_path: Path) -> None:
    runtime = SharedWorkflowRuntime(
        repository=GovernedArtifactRepository(REPO_ROOT),
        mcp_adapter=FixtureBackedMcpAdapter(),
        rag_adapter=FixtureBackedRagAdapter(),
        audit_root=tmp_path,
    )

    with pytest.raises(PermissionError, match="Internal write requires human review approval"):
        runtime.execute(
            "pr-verifier-orchestrator",
            "1.0.0",
            request={
                "pull_request_id": "123",
                "changed_files": ["runtime/engine.py"],
                "publish_review": True,
                "known_issues": [
                    {
                        "path": "runtime/engine.py",
                        "title": "Missing guard",
                        "severity": "high",
                        "evidence": "Internal write path lacks approval",
                        "remediation": "Require human review before writeback",
                    }
                ],
            },
            identity_context=_identity_context(),
        )


def test_pr_verifier_returns_structured_review_and_controlled_writeback(tmp_path: Path) -> None:
    mcp_adapter = FixtureBackedMcpAdapter()
    runtime = SharedWorkflowRuntime(
        repository=GovernedArtifactRepository(REPO_ROOT),
        mcp_adapter=mcp_adapter,
        rag_adapter=FixtureBackedRagAdapter(),
        audit_root=tmp_path,
    )

    execution = runtime.execute(
        "pr-verifier-orchestrator",
        "1.0.0",
        request={
            "pull_request_id": "456",
            "changed_files": ["runtime/engine.py", "runtime/repository.py"],
            "required_tests": ["tests/test_shared_workflow_runtime.py"],
            "publish_review": True,
            "known_issues": [
                {
                    "path": "runtime/engine.py",
                    "title": "Audit order regression",
                    "severity": "medium",
                    "evidence": "Write executes before audit event",
                    "remediation": "Emit write-ahead audit event before internal write",
                }
            ],
            "human_review": {
                "approved": True,
                "reviewer": "eng-reviewer",
                "decision_id": "eng-hitl-001",
            },
        },
        identity_context=_identity_context(),
    )

    audit = json.loads(Path(execution["audit_path"]).read_text(encoding="utf-8"))
    result = execution["result"]

    assert result["summary"] == "Governed review completed"
    assert result["findings"][0]["title"] == "Audit order regression"
    assert result["required_tests"] == ["tests/test_shared_workflow_runtime.py"]
    assert result["writeback"]["status"] == "committed"
    assert result["hitl_record"]["approved"] is True
    assert audit["delegations"][0]["capability_id"] == "diff-review-specialist"
    assert audit["delegations"][0]["capability_version"] == "1.0.0"
    assert audit["cost_attribution"]["capability_id"] == "pr-verifier-orchestrator"
    assert audit["cost_attribution"]["capability_version"] == "1.0.0"
    assert len(mcp_adapter.writes) == 1
    assert mcp_adapter.writes[0]["tool_id"] == "pr-comment-writer"


def test_runtime_requires_full_identity_context(tmp_path: Path) -> None:
    runtime = SharedWorkflowRuntime(
        repository=GovernedArtifactRepository(REPO_ROOT),
        audit_root=tmp_path,
    )

    with pytest.raises(PermissionError, match="missing identity context tags"):
        runtime.execute(
            "pr-verifier-orchestrator",
            "1.0.0",
            request={"pull_request_id": "789", "changed_files": []},
            identity_context={
                "tenant_id": "flutter-internal",
                "brand": "shared-platform",
            },
        )


def test_runtime_can_execute_specialists_directly(tmp_path: Path) -> None:
    runtime = SharedWorkflowRuntime(
        repository=GovernedArtifactRepository(REPO_ROOT),
        audit_root=tmp_path,
    )

    customer = runtime.execute(
        "customer-360-specialist",
        "1.0.0",
        request={"customer_id": "customer-003"},
        identity_context=_identity_context(),
    )
    diff = runtime.execute(
        "diff-review-specialist",
        "1.0.0",
        request={
            "pull_request_id": "901",
            "changed_files": ["runtime/models.py"],
            "known_issues": ["ignore-this-non-dict"],
        },
        identity_context=_identity_context(),
    )

    assert customer["result"]["customer_id"] == "customer-003"
    assert diff["result"]["required_tests"] == ["targeted-regression"]


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({}, "capability definition missing metadata.capability_id"),
        (
            {
                "metadata": {"capability_id": "cap"},
                "prompt": {"prompt_ref": "prompts/cap", "prompt_sha256": "a" * 64},
                "governance": {"risk_tier": "R1"},
                "tool_bindings": [],
                "evaluation": {"evaluation_pack_ref": "cap@1.0.0"},
            },
            "cap: missing metadata.version",
        ),
        (
            {
                "metadata": {"capability_id": "cap", "version": "1.0.0"},
                "prompt": {},
                "governance": {"risk_tier": "R1"},
                "tool_bindings": [],
                "evaluation": {"evaluation_pack_ref": "cap@1.0.0"},
            },
            "cap: missing prompt metadata",
        ),
        (
            {
                "metadata": {"capability_id": "cap", "version": "1.0.0"},
                "prompt": {"prompt_ref": "prompts/cap", "prompt_sha256": "a" * 64},
                "governance": {},
                "tool_bindings": [],
                "evaluation": {"evaluation_pack_ref": "cap@1.0.0"},
            },
            "cap: missing governance.risk_tier",
        ),
        (
            {
                "metadata": {"capability_id": "cap", "version": "1.0.0"},
                "prompt": {"prompt_ref": "prompts/cap", "prompt_sha256": "a" * 64},
                "governance": {"risk_tier": "R1"},
                "tool_bindings": {},
                "evaluation": {"evaluation_pack_ref": "cap@1.0.0"},
            },
            "cap: tool_bindings must be a list",
        ),
        (
            {
                "metadata": {"capability_id": "cap", "version": "1.0.0"},
                "prompt": {"prompt_ref": "prompts/cap", "prompt_sha256": "a" * 64},
                "governance": {"risk_tier": "R1"},
                "tool_bindings": ["bad"],
                "evaluation": {"evaluation_pack_ref": "cap@1.0.0"},
            },
            "cap: tool_bindings[0] must be an object",
        ),
        (
            {
                "metadata": {"capability_id": "cap", "version": "1.0.0"},
                "prompt": {"prompt_ref": "prompts/cap", "prompt_sha256": "a" * 64},
                "governance": {"risk_tier": "R1"},
                "tool_bindings": [{"tool_id": "tool"}],
                "evaluation": {"evaluation_pack_ref": "cap@1.0.0"},
            },
            "cap: tool_bindings[0] missing tool_id, kind, or action_class",
        ),
    ],
)
def test_parse_capability_definition_validation(
    payload: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=re.escape(message)):
        parse_capability_definition(payload)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({}, "workflow contract missing metadata.workflow_id"),
        ({"metadata": {"workflow_id": "wf"}}, "wf: missing metadata.version"),
        (
            {"metadata": {"workflow_id": "wf", "version": "1.0.0"}, "governance": {}},
            "wf: missing governance.risk_tier",
        ),
        (
            {
                "metadata": {"workflow_id": "wf", "version": "1.0.0"},
                "governance": {"risk_tier": "R1"},
                "steps": [],
            },
            "wf: steps must be a non-empty list",
        ),
        (
            {
                "metadata": {"workflow_id": "wf", "version": "1.0.0"},
                "governance": {"risk_tier": "R1"},
                "steps": ["bad"],
            },
            "wf: steps[0] must be an object",
        ),
        (
            {
                "metadata": {"workflow_id": "wf", "version": "1.0.0"},
                "governance": {"risk_tier": "R1"},
                "steps": [{"step_id": "one"}],
            },
            "wf: steps[0] missing step_id or mode",
        ),
    ],
)
def test_parse_workflow_contract_validation(
    payload: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=re.escape(message)):
        parse_workflow_contract(payload)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({}, "evaluation pack missing metadata.pack_id"),
        ({"metadata": {"pack_id": "pack"}}, "pack: missing metadata.version"),
        (
            {"metadata": {"pack_id": "pack", "version": "1.0.0"}},
            "pack: missing capability_ref",
        ),
    ],
)
def test_parse_evaluation_pack_validation(payload: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=re.escape(message)):
        parse_evaluation_pack(payload)


def test_repository_and_adapter_error_paths(tmp_path: Path) -> None:
    empty_repository = GovernedArtifactRepository(tmp_path)
    assert empty_repository.list_capabilities() == ()
    assert empty_repository.list_workflows() == ()
    assert empty_repository.list_evaluation_packs() == ()

    repository = GovernedArtifactRepository(REPO_ROOT)
    with pytest.raises(KeyError, match="Unknown capability"):
        repository.get_capability("missing-capability", "1.0.0")
    with pytest.raises(KeyError, match="Unknown workflow contract"):
        repository.get_workflow_contract("missing-workflow@1.0.0")
    with pytest.raises(KeyError, match="Unknown evaluation pack"):
        repository.get_evaluation_pack("missing-pack@1.0.0")
    with pytest.raises(ValueError, match="Invalid artifact reference"):
        split_ref("invalid-ref")

    non_list_pack = EvaluationPack(
        pack_id="pack",
        version="1.0.0",
        capability_ref="cap@1.0.0",
        payload={"datasets": "bad"},
    )
    missing_file_pack = EvaluationPack(
        pack_id="pack",
        version="1.0.0",
        capability_ref="cap@1.0.0",
        payload={"datasets": [{"path": "datasets/does-not-exist.jsonl"}]},
    )
    assert repository.resolve_dataset_paths(non_list_pack) == ()
    with pytest.raises(FileNotFoundError, match="missing dataset file"):
        repository.resolve_dataset_paths(missing_file_pack)

    with pytest.raises(KeyError, match="Unsupported MCP tool binding"):
        FixtureBackedMcpAdapter().invoke(
            "unknown-tool",
            McpInvocation(
                capability_id="capability",
                capability_version="1.0.0",
                request={},
                identity_context=_identity_context(),
            ),
        )
    with pytest.raises(KeyError, match="Unsupported RAG tool binding"):
        FixtureBackedRagAdapter().search(
            "unknown-tool",
            query="test",
            identity_context=_identity_context(),
        )


def test_repository_resolves_versioned_capability_refs(tmp_path: Path) -> None:
    capability_root = tmp_path / "capability-definitions"
    workflow_root = tmp_path / "workflow-contracts"
    evaluation_root = tmp_path / "evaluation-packs"
    capability_root.mkdir()
    workflow_root.mkdir()
    evaluation_root.mkdir()

    for version in ("1.0.0", "2.0.0"):
        workflow_root.joinpath(f"wf-{version}.json").write_text(
            json.dumps(
                {
                    "kind": "WorkflowContract",
                    "metadata": {"workflow_id": "wf", "version": version},
                    "governance": {"risk_tier": "R1"},
                    "steps": [{"step_id": "step-1", "mode": "automated"}],
                }
            ),
            encoding="utf-8",
        )
        evaluation_root.joinpath(f"pack-{version}.json").write_text(
            json.dumps(
                {
                    "kind": "EvaluationPack",
                    "metadata": {"pack_id": "pack", "version": version},
                    "capability_ref": f"custom-capability@{version}",
                }
            ),
            encoding="utf-8",
        )

    for version in ("1.0.0", "2.0.0"):
        capability_root.joinpath(f"custom-capability-{version}.json").write_text(
            json.dumps(
                {
                    "kind": "CapabilityDefinition",
                    "metadata": {
                        "capability_id": "custom-capability",
                        "version": version,
                        "lifecycle_state": "Published",
                    },
                    "prompt": {
                        "prompt_ref": "prompts/custom-capability",
                        "prompt_sha256": "a" * 64,
                    },
                    "governance": {
                        "risk_tier": "R1",
                        "workflow_contract_ref": "wf@1.0.0",
                        "execution_model": {"scopes": ["Reasoning"]},
                    },
                    "identity": {
                        "required_tags": ["tenant_id", "brand", "role", "use_case"]
                    },
                    "tool_bindings": [
                        {
                            "tool_id": "customer-360-reader",
                            "kind": "mcp",
                            "action_class": "read",
                            "requires_identity_context": True,
                        }
                    ],
                    "evaluation": {"evaluation_pack_ref": f"pack@{version}"},
                }
            ),
            encoding="utf-8",
        )

    repository = GovernedArtifactRepository(tmp_path)
    assert repository.get_capability("custom-capability", "1.0.0").version == "1.0.0"
    assert repository.get_capability("custom-capability", "2.0.0").version == "2.0.0"


def test_runtime_delegate_rejects_unsupported_delegated_capability(tmp_path: Path) -> None:
    runtime = SharedWorkflowRuntime(
        repository=GovernedArtifactRepository(REPO_ROOT),
        audit_root=tmp_path,
    )
    context = ExecutionContext(
        identity_context=_identity_context(),
        audit={"events": [], "delegations": [], "invocation_chain": [], "tool_calls": []},
    )

    with pytest.raises(ValueError, match="Unsupported delegated capability"):
        runtime._delegate(  # noqa: SLF001
            "pr-verifier-orchestrator@1.0.0",
            request={},
            context=context,
        )


def test_runtime_helper_lookups_raise_for_missing_entries() -> None:
    capability = GovernedArtifactRepository(REPO_ROOT).get_capability(
        "pr-verifier-orchestrator",
        "1.0.0",
    )

    with pytest.raises(KeyError, match="missing tool binding"):
        _binding_for_tool(capability, "missing-tool")

    with pytest.raises(KeyError, match="missing delegated capability ref"):
        _delegated_capability_ref(capability, "missing-specialist")


def test_repository_skips_non_dict_and_blank_dataset_paths(tmp_path: Path) -> None:
    capability_root = tmp_path / "capability-definitions"
    evaluation_root = tmp_path / "evaluation-packs"
    capability_root.mkdir()
    evaluation_root.mkdir()
    dataset_file = tmp_path / "datasets" / "valid.jsonl"
    dataset_file.parent.mkdir()
    dataset_file.write_text("{}\n", encoding="utf-8")

    capability_root.joinpath("cap.json").write_text(
        json.dumps(
            {
                "kind": "CapabilityDefinition",
                "metadata": {"capability_id": "cap", "version": "1.0.0", "lifecycle_state": "Published"},
                "prompt": {"prompt_ref": "prompts/cap", "prompt_sha256": "a" * 64},
                "governance": {"risk_tier": "R1", "execution_model": {"scopes": ["Reasoning"]}},
                "identity": {"required_tags": ["tenant_id", "brand", "role", "use_case"]},
                "tool_bindings": [{"tool_id": "customer-360-reader", "kind": "mcp", "action_class": "read", "requires_identity_context": True}],
                "evaluation": {"evaluation_pack_ref": "pack@1.0.0"},
            }
        ),
        encoding="utf-8",
    )
    evaluation_root.joinpath("pack.json").write_text(
        json.dumps(
            {
                "kind": "EvaluationPack",
                "metadata": {"pack_id": "pack", "version": "1.0.0"},
                "capability_ref": "cap@1.0.0",
                "datasets": ["skip-me", {"path": ""}, {"path": "datasets/valid.jsonl"}],
            }
        ),
        encoding="utf-8",
    )

    repository = GovernedArtifactRepository(tmp_path)

    assert repository.resolve_dataset_paths(repository.get_evaluation_pack("pack@1.0.0")) == (
        dataset_file.resolve(),
    )


def test_repository_rejects_duplicate_records(tmp_path: Path) -> None:
    capability_root = tmp_path / "capability-definitions"
    capability_root.mkdir()
    duplicate_payload = {
        "kind": "CapabilityDefinition",
        "metadata": {"capability_id": "cap", "version": "1.0.0", "lifecycle_state": "Published"},
        "prompt": {"prompt_ref": "prompts/cap", "prompt_sha256": "a" * 64},
        "governance": {"risk_tier": "R1", "execution_model": {"scopes": ["Reasoning"]}},
        "identity": {"required_tags": ["tenant_id", "brand", "role", "use_case"]},
        "tool_bindings": [{"tool_id": "customer-360-reader", "kind": "mcp", "action_class": "read", "requires_identity_context": True}],
        "evaluation": {"evaluation_pack_ref": "pack@1.0.0"},
    }
    capability_root.joinpath("one.json").write_text(json.dumps(duplicate_payload), encoding="utf-8")
    capability_root.joinpath("two.json").write_text(json.dumps(duplicate_payload), encoding="utf-8")

    repository = GovernedArtifactRepository(tmp_path)

    with pytest.raises(ValueError, match="Duplicate capability ref"):
        repository.list_capabilities()


def _write_custom_runtime_repo(
    tmp_path: Path,
) -> dict[str, object]:
    capability_root = tmp_path / "capability-definitions"
    workflow_root = tmp_path / "workflow-contracts"
    evaluation_root = tmp_path / "evaluation-packs"
    capability_root.mkdir()
    workflow_root.mkdir()
    evaluation_root.mkdir()

    workflow_root.joinpath("wf.json").write_text(
        json.dumps(
            {
                "kind": "WorkflowContract",
                "metadata": {"workflow_id": "wf", "version": "1.0.0"},
                "governance": {"risk_tier": "R1"},
                "steps": [{"step_id": "step-1", "mode": "automated"}],
            }
        ),
        encoding="utf-8",
    )
    evaluation_root.joinpath("pack.json").write_text(
        json.dumps(
            {
                "kind": "EvaluationPack",
                "metadata": {"pack_id": "pack", "version": "1.0.0"},
                "capability_ref": "custom-capability@1.0.0",
            }
        ),
        encoding="utf-8",
    )

    base_capability = {
        "kind": "CapabilityDefinition",
        "metadata": {
            "capability_id": "custom-capability",
            "version": "1.0.0",
            "lifecycle_state": "Published",
        },
        "prompt": {"prompt_ref": "prompts/custom-capability", "prompt_sha256": "a" * 64},
        "governance": {
            "risk_tier": "R1",
            "workflow_contract_ref": "wf@1.0.0",
            "execution_model": {"scopes": ["Reasoning"]},
        },
        "identity": {"required_tags": ["tenant_id", "brand", "role", "use_case"]},
        "tool_bindings": [
            {
                "tool_id": "customer-360-reader",
                "kind": "mcp",
                "action_class": "read",
                "requires_identity_context": True,
            }
        ],
        "evaluation": {"evaluation_pack_ref": "pack@1.0.0"},
    }
    capability_root.joinpath("custom-capability.json").write_text(
        json.dumps(base_capability),
        encoding="utf-8",
    )
    return base_capability


def test_runtime_rejects_unknown_shared_runtime_capability(tmp_path: Path) -> None:
    _write_custom_runtime_repo(tmp_path)

    runtime = SharedWorkflowRuntime(
        repository=GovernedArtifactRepository(tmp_path),
        audit_root=tmp_path / "audit",
    )
    with pytest.raises(ValueError, match="Unsupported shared runtime capability"):
        runtime.execute(
            "custom-capability",
            "1.0.0",
            request={"customer_id": "1"},
            identity_context=_identity_context(),
        )


def test_runtime_rejects_non_published_capability(tmp_path: Path) -> None:
    base_capability = _write_custom_runtime_repo(tmp_path)

    draft_payload = json.loads(json.dumps(base_capability))
    draft_payload["metadata"]["lifecycle_state"] = "Draft"
    (tmp_path / "capability-definitions" / "custom-capability.json").write_text(
        json.dumps(draft_payload),
        encoding="utf-8",
    )
    draft_runtime = SharedWorkflowRuntime(
        repository=GovernedArtifactRepository(tmp_path),
        audit_root=tmp_path / "audit-draft",
    )
    with pytest.raises(PermissionError, match="is not published"):
        draft_runtime.execute(
            "custom-capability",
            "1.0.0",
            request={"customer_id": "1"},
            identity_context=_identity_context(),
        )


def test_runtime_rejects_invalid_identity_contract_shape(tmp_path: Path) -> None:
    base_capability = _write_custom_runtime_repo(tmp_path)

    invalid_identity_payload = json.loads(json.dumps(base_capability))
    invalid_identity_payload["identity"]["required_tags"] = "bad"
    (tmp_path / "capability-definitions" / "custom-capability.json").write_text(
        json.dumps(invalid_identity_payload),
        encoding="utf-8",
    )
    invalid_identity_runtime = SharedWorkflowRuntime(
        repository=GovernedArtifactRepository(tmp_path),
        audit_root=tmp_path / "audit-invalid-identity",
    )
    with pytest.raises(ValueError, match="invalid identity.required_tags"):
        invalid_identity_runtime.execute(
            "custom-capability",
            "1.0.0",
            request={"customer_id": "1"},
            identity_context=_identity_context(),
        )


def test_hitl_record_defaults_when_review_payload_is_not_a_mapping() -> None:
    assert _hitl_record({"human_review": "invalid"}) == {"approved": False}
