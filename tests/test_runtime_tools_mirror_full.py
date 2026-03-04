from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

import pytest

lambda_common = importlib.import_module("tests.test_aws_lambda_common_full")
coverage_gap = importlib.import_module("tests.test_coverage_gap_branches")

_LAMBDA_PATH = Path(__file__).resolve().parents[1] / "aws" / "lambda"

_RUNTIME_MODULE_MAP = {
    "artifact_store": "runtime.sop_agent.tools.artifact_store",
    "fetch_mcp_stage": "runtime.sop_agent.stages.fetch_mcp_stage",
    "fetch_native_stage": "runtime.sop_agent.stages.fetch_native_stage",
    "generate_stage": "runtime.sop_agent.stages.generate_stage",
    "evaluate_stage": "runtime.sop_agent.stages.evaluate_stage",
    "jira_client": "runtime.sop_agent.tools.jira_client",
    "json_extract": "runtime.sop_agent.tools.json_extract",
    "llm_gateway_invoke_client": "runtime.sop_agent.tools.llm_gateway_invoke_client",
    "mcp_gateway_client": "runtime.sop_agent.tools.mcp_gateway_client",
    "network_security": "runtime.sop_agent.tools.network_security",
    "parse_stage": "runtime.sop_agent.stages.parse_stage",
    "request_grounding": "runtime.sop_agent.tools.request_grounding",
    "response_generation": "runtime.sop_agent.tools.response_generation",
    "runtime_config": "runtime.sop_agent.tools.runtime_config",
    "stage_metrics": "runtime.sop_agent.stages.stage_metrics",
    "tool_selection": "runtime.sop_agent.tools.tool_selection",
    "tooling_domain": "runtime.sop_agent.domain.tooling",
    "write_actions": "runtime.sop_agent.tools.write_actions",
}


def _import_lambda_module(name: str) -> Any:
    if str(_LAMBDA_PATH) not in sys.path:
        sys.path.insert(0, str(_LAMBDA_PATH))
    return importlib.import_module(name)


def _import_runtime_module(name: str) -> Any:
    if name in _RUNTIME_MODULE_MAP:
        return importlib.import_module(_RUNTIME_MODULE_MAP[name])
    if name == "bedrock_client":
        return _import_lambda_module(name)
    raise ModuleNotFoundError(f"runtime mirror import unsupported: {name}")


def test_runtime_mirror_network_security_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lambda_common, "_import_lambda_module", _import_runtime_module)
    lambda_common.test_network_security_helpers(monkeypatch)


def test_runtime_mirror_jira_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lambda_common, "_import_lambda_module", _import_runtime_module)
    lambda_common.test_jira_client(monkeypatch)


def test_runtime_mirror_tooling_and_selection_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lambda_common, "_import_lambda_module", _import_runtime_module)
    lambda_common.test_tooling_and_selection_helpers(monkeypatch)


def test_runtime_mirror_mcp_gateway_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lambda_common, "_import_lambda_module", _import_runtime_module)
    lambda_common.test_mcp_gateway_client_transport_and_tool_payload(monkeypatch)


def test_runtime_mirror_config_and_auxiliary_modules(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lambda_common, "_import_lambda_module", _import_runtime_module)
    lambda_common.test_runtime_config_and_auxiliary_module_branches(monkeypatch)


def test_runtime_mirror_request_grounding_module(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lambda_common, "_import_lambda_module", _import_runtime_module)
    lambda_common.test_request_grounding_module(monkeypatch)


def test_runtime_mirror_write_actions_and_runtime_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(coverage_gap, "_import_lambda_module", _import_runtime_module)
    coverage_gap.test_write_actions_runtime_config_and_bedrock_branches(monkeypatch)


def test_runtime_mirror_tool_selection_schema_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(coverage_gap, "_import_lambda_module", _import_runtime_module)
    coverage_gap.test_tool_selection_schema_helpers(monkeypatch)


def test_runtime_mirror_grounding_and_native_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(coverage_gap, "_import_lambda_module", _import_runtime_module)
    coverage_gap.test_request_grounding_and_native_stage_branches(monkeypatch)


def test_runtime_mirror_fetch_mcp_parsing_and_attempt_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(coverage_gap, "_import_lambda_module", _import_runtime_module)
    coverage_gap.test_fetch_mcp_stage_parsing_and_attempt_resolution(monkeypatch)


def test_runtime_mirror_evaluate_stage_resolution_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(coverage_gap, "_import_lambda_module", _import_runtime_module)
    coverage_gap.test_evaluate_stage_metrics_and_resolution_helpers(monkeypatch)


def test_runtime_mirror_llm_invoke_client_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(coverage_gap, "_import_lambda_module", _import_runtime_module)
    coverage_gap.test_lambda_invoke_client_config_and_parse_branches(monkeypatch)


def test_runtime_mirror_llm_invoke_client_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(coverage_gap, "_import_lambda_module", _import_runtime_module)
    coverage_gap.test_lambda_invoke_client_request_execution_and_retries(monkeypatch)


def test_runtime_quality_helpers_branches() -> None:
    quality_helpers = importlib.import_module("runtime.sop_agent.tools.quality_helpers")
    assert quality_helpers.safe_int(True) == 1
    assert quality_helpers.safe_int("7") == 7
    assert quality_helpers.safe_int("bad") == 0
    assert quality_helpers.safe_int(None) == 0
    assert quality_helpers.parse_positive_int("3", error_code="bad_value") == 3
    with pytest.raises(ValueError, match="bad_value"):
        quality_helpers.parse_positive_int("0", error_code="bad_value")
    with pytest.raises(ValueError, match="bad_value"):
        quality_helpers.parse_positive_int("x", error_code="bad_value")
    usage = quality_helpers.merge_usage(
        {"input_tokens": 2, "output_tokens": 1, "total_tokens": 3},
        {"input_tokens": 3, "output_tokens": -5, "total_tokens": 4},
    )
    assert usage == {"input_tokens": 5, "output_tokens": 0, "total_tokens": 7}
    assert quality_helpers.selection_llm_usage({}) == {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }
    assert quality_helpers.selection_llm_usage({"llm_usage": "bad"}) == {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }
    assert quality_helpers.extract_failure_reason({"result": {"failure_reason": " bad "}}, container="result") == "bad"
    assert quality_helpers.extract_failure_reason({"result": "bad"}, container="result") == ""


def test_runtime_json_extract_branches() -> None:
    json_extract = importlib.import_module("runtime.sop_agent.tools.json_extract")
    parsed = json_extract.extract_json_object('before {"a":"b\\q"} after')
    assert parsed["a"] == "b\\q"
    with pytest.raises(ValueError):
        json_extract.extract_json_object("invalid")
