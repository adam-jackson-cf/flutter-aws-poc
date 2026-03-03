import importlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

from runtime.sop_agent.domain import contracts as runtime_contracts
from runtime.sop_agent.stages import intake_stage
from runtime.sop_agent.tools import jira_mcp_flow, strands_native_flow


def _import_lambda_module(module_name: str) -> Any:
    lambda_path = Path(__file__).resolve().parents[1] / "aws" / "lambda"
    if str(lambda_path) not in sys.path:
        sys.path.insert(0, str(lambda_path))
    return importlib.import_module(module_name)


def _load_contract() -> dict[str, Any]:
    contract_path = Path(__file__).resolve().parents[1] / "contracts" / "jira_tools.contract.json"
    return json.loads(contract_path.read_text(encoding="utf-8"))


def _load_contract_generator() -> Any:
    generator_path = Path(__file__).resolve().parents[1] / "scripts" / "generate_tool_contract_artifacts.py"
    spec = importlib.util.spec_from_file_location("generate_tool_contract_artifacts", generator_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("request_text", "expected_intent"),
    [
        ("Customer reports bug and outage for JRASERVER-1", "bug_triage"),
        ("Feature request for roadmap on JRASERVER-1", "feature_request"),
        ("Need latest status update for JRASERVER-1", "status_update"),
        ("Please review JRASERVER-1", "general_triage"),
    ],
)
def test_intent_classification_parity(request_text: str, expected_intent: str) -> None:
    intake_domain = _import_lambda_module("intake_domain")
    assert intake_stage.classify_intent(request_text) == expected_intent
    assert intake_domain.classify_intent(request_text) == expected_intent


def test_intake_risk_hint_parity() -> None:
    intake_domain = _import_lambda_module("intake_domain")
    request_text = "Need update for JRASERVER-2 regarding security escalation and compliance"
    runtime_intake = intake_stage.run_intake(
        request_text,
        intake_stage.IntakeModelConfig(
            model_id="eu.amazon.nova-lite-v1:0",
            region="eu-west-1",
            dry_run=True,
        ),
    )
    lambda_intake = intake_domain.extract_intake(request_text)
    assert runtime_intake["risk_hints"] == lambda_intake["risk_hints"]


def test_scope_maps_snapshot() -> None:
    tooling_domain = _import_lambda_module("tooling_domain")
    fetch_native_stage = _import_lambda_module("fetch_native_stage")
    contract = _load_contract()

    expected_mcp_scope = contract["mcp_tool_scope_by_intent"]
    assert jira_mcp_flow.TOOL_SCOPE_BY_INTENT == expected_mcp_scope
    assert tooling_domain.MCP_TOOL_SCOPE_BY_INTENT == expected_mcp_scope
    assert runtime_contracts.MCP_TOOL_SCOPE_BY_INTENT == expected_mcp_scope

    expected_native_scope = contract["native_tool_scope_by_intent"]
    assert strands_native_flow.TOOL_SCOPE_BY_INTENT == expected_native_scope
    assert fetch_native_stage.NATIVE_TOOL_SCOPE_BY_INTENT == expected_native_scope
    assert runtime_contracts.NATIVE_TOOL_SCOPE_BY_INTENT == expected_native_scope


def test_completeness_mapping_snapshot() -> None:
    tooling_domain = _import_lambda_module("tooling_domain")
    contract = _load_contract()
    expected = contract["tool_completeness_fields_by_operation"]
    assert tooling_domain.TOOL_COMPLETENESS_FIELDS_BY_OPERATION == expected
    assert runtime_contracts.TOOL_COMPLETENESS_FIELDS_BY_OPERATION == expected


def test_cdk_tool_name_snapshot() -> None:
    contract = _load_contract()
    infra_stack = Path(__file__).resolve().parents[1] / "infra" / "lib" / "flutter-agentcore-poc-stack.ts"
    generated_contract = Path(__file__).resolve().parents[1] / "infra" / "lib" / "generated" / "jira-tool-contract.ts"

    stack_text = infra_stack.read_text(encoding="utf-8")
    assert 'from "./generated/jira-tool-contract"' in stack_text
    assert "toolSchema: agentcore.ToolSchema.fromInline(buildGatewayToolSchema())" in stack_text
    assert 'name: "jira_' not in stack_text

    generated_text = generated_contract.read_text(encoding="utf-8")
    names = []
    for line in generated_text.splitlines():
        line = line.strip()
        match = re.match(r'^"name":\s*"(jira_[^"]+)",?$', line)
        if match:
            names.append(match.group(1))

    assert names == [tool["name"] for tool in contract["gateway_tools"]]


def test_generated_artifacts_lockstep_with_contract_source() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    contract = _load_contract()
    generator = _load_contract_generator()

    expected_runtime = "\n".join(generator._runtime_lines(contract))
    expected_lambda = "\n".join(generator._lambda_lines(contract))
    expected_infra = "\n".join(generator._infra_lines(contract))

    runtime_contract = repo_root / "runtime" / "sop_agent" / "domain" / "contracts.py"
    lambda_contract = repo_root / "aws" / "lambda" / "contract_values.py"
    infra_contract = repo_root / "infra" / "lib" / "generated" / "jira-tool-contract.ts"

    assert runtime_contract.read_text(encoding="utf-8") == expected_runtime
    assert lambda_contract.read_text(encoding="utf-8") == expected_lambda
    assert infra_contract.read_text(encoding="utf-8") == expected_infra
