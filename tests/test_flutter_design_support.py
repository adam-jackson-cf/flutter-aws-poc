import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.linters.flutter_design_support.artifacts import (  # noqa: E402
    DesignRepository,
    artefact_key,
    iter_artifact_files,
    load_adapter,
    load_design_repository,
    load_json_object,
    load_schema,
    published_state,
    validate_schema_records,
)
from scripts.linters.flutter_design_support.publish_readiness import (  # noqa: E402
    process_scope_violations,
    publish_readiness_violations,
)


ADAPTER_PATH = REPO_ROOT / "scripts" / "linters" / "flutter-design" / "flutter-design-linter-profile.json"
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "flutter-design"


@pytest.fixture(scope="module")
def adapter():
    return load_adapter(ADAPTER_PATH)


def test_load_json_object_rejects_non_object(tmp_path: Path) -> None:
    path = tmp_path / "invalid.json"
    path.write_text('["not-an-object"]', encoding="utf-8")

    with pytest.raises(ValueError, match="expected a JSON object"):
        load_json_object(path)


def test_load_adapter_requires_mapping_values(tmp_path: Path) -> None:
    path = tmp_path / "adapter.json"
    path.write_text('{"artifact_dirs": [], "schema_files": {}}', encoding="utf-8")

    with pytest.raises(ValueError, match="expected a JSON object of string values"):
        load_adapter(path)


def test_load_adapter_defaults_non_list_fields_to_empty_sequences(tmp_path: Path) -> None:
    path = tmp_path / "adapter.json"
    path.write_text(
        """
        {
          "artifact_dirs": {"capability_definitions": "capability-definitions"},
          "schema_files": {"capability_definition": "contracts/schemas/capability-definition.schema.json"},
          "required_identity_tags": "tenant_id",
          "allowed_execution_scopes": "Reasoning",
          "workflow_required_risk_tiers": "R2",
          "published_states": "Published"
        }
        """,
        encoding="utf-8",
    )

    adapter = load_adapter(path)

    assert adapter.required_identity_tags == ()
    assert adapter.allowed_execution_scopes == ()
    assert adapter.workflow_required_risk_tiers == ()
    assert adapter.published_states == ()


def test_iter_artifact_files_ignores_hidden_directories(tmp_path: Path) -> None:
    visible_dir = tmp_path / "capability-definitions"
    hidden_dir = visible_dir / ".hidden"
    visible_dir.mkdir(parents=True)
    hidden_dir.mkdir(parents=True)
    (visible_dir / "visible.json").write_text("{}", encoding="utf-8")
    (hidden_dir / "hidden.json").write_text("{}", encoding="utf-8")

    files = iter_artifact_files(tmp_path, "capability-definitions")

    assert files == [visible_dir / "visible.json"]


def test_schema_validation_returns_contract_records(adapter) -> None:
    repo_root = FIXTURE_ROOT / "valid-r1"

    records, violations = validate_schema_records(
        repo_root,
        adapter,
        artifact_type="capability_definitions",
        schema_name="capability_definition",
        require_files=True,
    )

    assert not violations
    assert [record.key for record in records] == ["player-protection-case-review@0.1.0"]
    assert published_state(records[0]) == "Published"


def test_load_schema_uses_adapter_mapping(adapter) -> None:
    schema = load_schema(REPO_ROOT, adapter, "capability_definition")

    assert schema["title"] == "Capability Definition"


def test_load_design_repository_rejects_invalid_schema_fixture(adapter) -> None:
    with pytest.raises(ValueError, match="safety_envelope_ref"):
        load_design_repository(FIXTURE_ROOT / "invalid-schema", adapter)


def test_validate_schema_records_reports_non_object_payload(adapter, tmp_path: Path) -> None:
    capability_dir = tmp_path / "capability-definitions"
    capability_dir.mkdir(parents=True)
    (capability_dir / "broken.json").write_text('["not-an-object"]', encoding="utf-8")

    records, violations = validate_schema_records(
        tmp_path,
        adapter,
        artifact_type="capability_definitions",
        schema_name="capability_definition",
        require_files=True,
    )

    assert records == []
    assert any("expected a JSON object" in violation for violation in violations)


def test_publish_readiness_module_accepts_valid_r2_fixture(adapter) -> None:
    repo_root = FIXTURE_ROOT / "valid-r2"
    repository = load_design_repository(repo_root, adapter)

    assert publish_readiness_violations(repo_root, adapter, repository) == []
    assert process_scope_violations(repo_root, adapter, repository) == []


def test_publish_readiness_module_accepts_valid_r1_process_fixture(adapter) -> None:
    repo_root = FIXTURE_ROOT / "valid-r1-process"
    repository = load_design_repository(repo_root, adapter)

    assert publish_readiness_violations(repo_root, adapter, repository) == []
    assert process_scope_violations(repo_root, adapter, repository) == []


def test_publish_readiness_module_reports_missing_evaluation_pack(adapter) -> None:
    repo_root = FIXTURE_ROOT / "invalid-missing-eval"
    repository = load_design_repository(repo_root, adapter)

    violations = publish_readiness_violations(repo_root, adapter, repository)

    assert any("referenced evaluation pack" in violation for violation in violations)


def test_process_scope_module_reports_missing_workflow_contract(adapter) -> None:
    repo_root = FIXTURE_ROOT / "invalid-r2-no-workflow"
    repository = load_design_repository(repo_root, adapter)

    violations = process_scope_violations(repo_root, adapter, repository)

    assert any("requires workflow_contract_ref" in violation for violation in violations)


def test_publish_readiness_module_reports_empty_repository(adapter) -> None:
    repository = DesignRepository(
        capability_definitions=[],
        safety_envelopes={},
        workflow_contracts={},
        evaluation_packs={},
    )

    violations = publish_readiness_violations(REPO_ROOT, adapter, repository)

    assert violations == ["capability-definitions: publish gate requires at least one Capability Definition"]


def test_publish_readiness_module_catches_broader_contract_drift(adapter) -> None:
    repo_root = FIXTURE_ROOT / "valid-r2"
    repository = load_design_repository(repo_root, adapter)
    capability = repository.capability_definitions[0]
    payload = capability.payload
    payload["metadata"]["lifecycle_state"] = "Published"
    payload["prompt"]["prompt_ref"] = ""
    payload["prompt"]["prompt_sha256"] = "bad"
    payload["governance"]["execution_model"]["scopes"] = ["Coordination", "Unsupported"]
    payload["governance"]["execution_model"]["delegated_capability_refs"] = []
    payload["routing"]["llm_route"] = "direct"
    payload["identity"]["required_tags"] = ["tenant_id"]
    payload["tool_bindings"] = [
        "bad-binding",
        {"tool_id": "writer", "kind": "mcp", "action_class": "control", "requires_identity_context": False},
    ]
    payload["governance"]["safety_envelope_ref"] = "missing-envelope@1.0.0"

    evaluation_pack = repository.evaluation_packs["account-freeze-orchestrator@0.2.0"]
    evaluation_pack.payload["capability_ref"] = "different-capability@1.0.0"
    evaluation_pack.payload["release_gate"]["status"] = "failed"
    evaluation_pack.payload["release_gate"]["benchmark_pass_rate"] = 0.25
    evaluation_pack.payload["release_gate"]["minimum_benchmark_pass_rate"] = 0.9
    evaluation_pack.payload["datasets"] = ["bad-dataset", {"path": "datasets/missing.jsonl"}]

    workflow_contract = repository.workflow_contracts["account-freeze-review@1.0.0"]
    workflow_contract.payload["governance"]["risk_tier"] = "R3"

    violations = publish_readiness_violations(repo_root, adapter, repository)

    expected_fragments = [
        "execution_model.scopes must always include Reasoning",
        "unsupported values ['Unsupported']",
        "prompt.prompt_ref must be declared",
        "prompt.prompt_sha256 must be a 64-character SHA-256 digest",
        "routing.llm_route must be llm_gateway",
        "identity.required_tags missing ['brand', 'role', 'use_case']",
        "tool_bindings[0] must be an object",
        "tool_bindings[1] must require identity context",
        "kind mcp cannot use action_class control",
        "Coordination scope requires delegated_capability_refs",
        "referenced safety envelope 'missing-envelope@1.0.0' was not found",
        "capability_ref does not match",
        "requires a passed evaluation release gate",
        "benchmark_pass_rate 0.25 is below minimum 0.90",
        "dataset entry must be an object",
        "dataset path 'datasets/missing.jsonl' does not exist",
        "workflow contract 'account-freeze-review@1.0.0' risk tier R3 does not match capability risk tier R2",
    ]

    for fragment in expected_fragments:
        assert any(fragment in violation for violation in violations)


def test_publish_readiness_module_requires_eval_ref_for_published_state(adapter) -> None:
    repo_root = FIXTURE_ROOT / "valid-r1"
    repository = load_design_repository(repo_root, adapter)
    capability = repository.capability_definitions[0]
    capability.payload["metadata"]["lifecycle_state"] = "Published"
    capability.payload["evaluation"]["evaluation_pack_ref"] = ""

    violations = publish_readiness_violations(repo_root, adapter, repository)

    assert any("requires evaluation_pack_ref" in violation for violation in violations)


def test_process_scope_module_reports_missing_referenced_workflow_contract(adapter) -> None:
    repo_root = FIXTURE_ROOT / "valid-r2"
    repository = load_design_repository(repo_root, adapter)
    capability = repository.capability_definitions[0]
    capability.payload["governance"]["workflow_contract_ref"] = "missing-workflow@1.0.0"

    violations = process_scope_violations(repo_root, adapter, repository)

    assert any("referenced workflow contract 'missing-workflow@1.0.0' was not found" in violation for violation in violations)


def test_publish_readiness_module_rejects_r1_customer_write(adapter) -> None:
    repo_root = FIXTURE_ROOT / "invalid-r1-customer-write"
    repository = load_design_repository(repo_root, adapter)

    violations = publish_readiness_violations(repo_root, adapter, repository)

    assert any("risk tier R1 cannot use action_class customer_write" in violation for violation in violations)


def test_publish_readiness_module_rejects_r1_write_without_hitl(adapter) -> None:
    repo_root = FIXTURE_ROOT / "invalid-r1-no-hitl"
    repository = load_design_repository(repo_root, adapter)

    violations = publish_readiness_violations(repo_root, adapter, repository)

    assert any("require at least one human_review tool binding" in violation for violation in violations)


def test_artefact_key_rejects_unsupported_type() -> None:
    with pytest.raises(KeyError, match="unsupported artefact type"):
        artefact_key({"metadata": {}}, "unsupported")
