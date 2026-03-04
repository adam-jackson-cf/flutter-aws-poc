import importlib
import json
import subprocess
import sys
from dataclasses import FrozenInstanceError
from argparse import Namespace
from pathlib import Path
from typing import Any, Dict

import pytest

from evals import run_eval
from evals.aws_pipeline_runner import PipelineRunResult


def _sample_case() -> Dict[str, Any]:
    return {
        "case_id": "case1",
        "request_text": "Need update for JRASERVER-1",
        "expected_intent": "status_update",
        "expected_issue_key": "JRASERVER-1",
        "expected_response_anchor": "status update",
        "expected_tool": {"native": "jira_api_get_issue_by_key", "mcp": "jira_get_issue_by_key"},
    }


def _runtime_args(**overrides: Any) -> Namespace:
    args = {
        "scope": "route",
        "agent_runtime_arn": "arn:aws:bedrock:eu-west-1:123456789012:runtime/test",
        "agent_runtime_qualifier": "",
        "aws_region": "eu-west-1",
        "model_id": "eu.amazon.nova-lite-v1:0",
        "runtime_model_id": "eu.amazon.nova-lite-v1:0",
        "bedrock_region": "eu-west-1",
        "model_provider": "auto",
        "enable_judge": False,
        "judge_model_id": "eu.amazon.nova-lite-v1:0",
        "judge_region": "",
        "openai_max_output_tokens": 2000,
    }
    args.update(overrides)
    return Namespace(**args)


def _pricing_snapshot_args(catalog_path: Path, **overrides: Any) -> Namespace:
    args = {
        "model_id": "model-a",
        "model_pricing_catalog": str(catalog_path),
        "price_input_per_1m_tokens_usd": "",
        "price_output_per_1m_tokens_usd": "",
        "openai_reasoning_effort": "medium",
    }
    args.update(overrides)
    return Namespace(**args)


def _sample_run_payload() -> Dict[str, Any]:
    return {
        "intake": {"intent": "status_update"},
        "tool_result": {"key": "JRASERVER-1", "summary": "s", "status": "Done"},
        "generated_response": {"customer_response": "status update for JRASERVER-1"},
        "run_metrics": {
            "total_latency_ms": 12.5,
            "tool_failure": False,
            "llm_input_tokens": 12,
            "llm_output_tokens": 3,
            "llm_total_tokens": 15,
        },
        "native_selection": {"selected_tool": "jira_api_get_issue_by_key"},
        "mcp_selection": {"selected_tool": "jira_get_issue_by_key"},
    }


def test_parse_args_and_simple_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MODEL_PROVIDER", raising=False)
    monkeypatch.delenv("AGENT_RUNTIME_ARN", raising=False)
    monkeypatch.delenv("AGENTCORE_RUNTIME_ARN", raising=False)
    monkeypatch.delenv("AGENT_RUNTIME_QUALIFIER", raising=False)
    monkeypatch.setenv("MODEL_ID", "gpt-5.2-codex")
    monkeypatch.setenv("BEDROCK_MODEL_ID", "eu.amazon.nova-lite-v1:0")
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_eval.py", "--dataset", "d.jsonl", "--flow", "native", "--aws-region", "eu-west-1"],
    )
    args = run_eval.parse_args()
    assert args.flow == "native"
    assert args.model_provider == "auto"
    assert args.openai_reasoning_effort == "medium"
    assert args.openai_text_verbosity == "medium"
    assert args.openai_max_output_tokens == 2000
    assert args.model_pricing_catalog == "evals/model_pricing_usd_per_1m_tokens.json"
    assert args.price_input_per_1m_tokens_usd == ""
    assert args.price_output_per_1m_tokens_usd == ""
    assert args.model_id == "gpt-5.2-codex"
    assert args.runtime_model_id == "gpt-5.2-codex"
    assert args.agent_runtime_arn == ""
    assert args.agent_runtime_qualifier == "production"
    assert args.judge_model_id == "eu.amazon.nova-lite-v1:0"
    assert run_eval.utc_compact_now().endswith("Z")
    assert run_eval.sanitize_run_id(" bad id ") == "bad-id"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_eval.py",
            "--dataset",
            "d.jsonl",
            "--flow",
            "native",
            "--agent-runtime-qualifier",
            "canary",
        ],
    )
    args = run_eval.parse_args()
    assert args.agent_runtime_qualifier == "canary"

    monkeypatch.setattr(sys, "argv", ["run_eval.py", "--dataset", "d.jsonl"])
    with pytest.raises(SystemExit):
        run_eval.parse_args()

    monkeypatch.setattr(sys, "argv", ["run_eval.py", "--flow", "native"])
    with pytest.raises(SystemExit):
        run_eval.parse_args()


def test_eval_input_dataclasses_are_frozen() -> None:
    context = run_eval.CaseRunContext(flow="native", scope="route", iteration=1)
    with pytest.raises(FrozenInstanceError):
        context.flow = "mcp"  # type: ignore[misc]

    config = run_eval.EvaluationConfig(
        dry_run=True,
        scope="route",
        iterations=1,
        model_id="eu.amazon.nova-lite-v1:0",
        runtime_model_id="eu.amazon.nova-lite-v1:0",
        bedrock_region="eu-west-1",
        model_provider="auto",
        runner=object(),
        judge=None,
    )
    with pytest.raises(FrozenInstanceError):
        config.dry_run = False  # type: ignore[misc]

    payload = run_eval.ActualPayloadInput(
        intent_actual="status_update",
        issue_key_actual="JRASERVER-1",
        selected_tool="jira_get_issue_by_key",
        tool="jira_get_issue_by_key",
        failure_reason="",
        generated_response="ok",
        run=PipelineRunResult(execution_arn="arn", payload={}, artifact_s3_uri="s3://bucket/key"),
    )
    with pytest.raises(FrozenInstanceError):
        payload.selected_tool = "jira_get_issue_status_snapshot"  # type: ignore[misc]

    metrics = run_eval.CaseMetricsPayloadInput(
        intent_match=True,
        issue_key_match=True,
        issue_key_resolution_match=True,
        tool_failure=False,
        tool_match=True,
        issue_payload_complete=True,
        business_success=True,
        failure_reason="",
        total_latency_ms=1.0,
        response_similarity=1.0,
        call_construction_failure=False,
        call_construction_attempts=0,
        call_construction_retries=0,
        call_construction_recovered=False,
        grounding_failure=False,
        grounding_attempts=0,
        grounding_retries=0,
        write_case=False,
        write_tool_selected=False,
        write_tool_match=False,
        llm_input_tokens=0,
        llm_output_tokens=0,
        llm_total_tokens=0,
    )
    with pytest.raises(FrozenInstanceError):
        metrics.tool_failure = True  # type: ignore[misc]

    outcome = run_eval.CaseOutcome(
        intent_actual="status_update",
        issue_key_actual="JRASERVER-1",
        selected_tool="jira_get_issue_by_key",
        tool="jira_get_issue_by_key",
        failure_reason="",
        issue_payload_complete=True,
        tool_failure=False,
        intent_match=True,
        issue_key_match=True,
        issue_key_resolution_match=True,
        tool_match=True,
        business_success=True,
        total_latency_ms=1.0,
        response_similarity=1.0,
        call_construction_failure=False,
        call_construction_attempts=0,
        call_construction_retries=0,
        call_construction_recovered=False,
        grounding_failure=False,
        grounding_attempts=0,
        grounding_retries=0,
        write_case=False,
        write_tool_selected=False,
        write_tool_match=False,
        llm_input_tokens=0,
        llm_output_tokens=0,
        llm_total_tokens=0,
    )
    with pytest.raises(FrozenInstanceError):
        outcome.business_success = False  # type: ignore[misc]

    outcome_input = run_eval.CaseOutcomeInput(
        case=_sample_case(),
        context=run_eval.CaseRunContext(flow="native", scope="route", iteration=1),
        run_payload=_sample_run_payload(),
        run_metrics={"tool_failure": False},
        tool_result={"key": "JRASERVER-1", "summary": "ok", "status": "Done"},
        expected_tool="jira_api_get_issue_by_key",
        total_latency_ms=1.0,
        response_similarity=1.0,
    )
    with pytest.raises(FrozenInstanceError):
        outcome_input.expected_tool = "jira_get_issue_status_snapshot"  # type: ignore[misc]


def test_repo_root_added_to_sys_path_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root = str(run_eval.REPO_ROOT)
    trimmed_sys_path = [entry for entry in sys.path if entry != repo_root]
    monkeypatch.setattr(sys, "path", trimmed_sys_path.copy())
    importlib.reload(run_eval)
    assert sys.path[0] == repo_root


def test_load_dataset_validation(tmp_path: Path) -> None:
    row = _sample_case()
    valid = tmp_path / "valid.jsonl"
    valid.write_text("\n" + json.dumps(row) + "\n", encoding="utf-8")
    loaded = run_eval.load_dataset(str(valid))
    assert loaded[0]["case_id"] == "case1"

    bad_obj = tmp_path / "bad_obj.jsonl"
    bad_obj.write_text('"x"\n', encoding="utf-8")
    with pytest.raises(ValueError):
        run_eval.load_dataset(str(bad_obj))

    missing = dict(row)
    del missing["expected_tool"]
    missing_file = tmp_path / "missing.jsonl"
    missing_file.write_text(json.dumps(missing), encoding="utf-8")
    with pytest.raises(ValueError):
        run_eval.load_dataset(str(missing_file))

    bad_expected_obj = dict(row)
    bad_expected_obj["expected_tool"] = "not-an-object"
    bad_expected_file = tmp_path / "bad_expected.jsonl"
    bad_expected_file.write_text(json.dumps(bad_expected_obj), encoding="utf-8")
    with pytest.raises(ValueError):
        run_eval.load_dataset(str(bad_expected_file))

    missing_flow_tool = dict(row)
    missing_flow_tool["expected_tool"] = {"native": "", "mcp": "jira_get_issue_by_key"}
    missing_flow_file = tmp_path / "missing_flow_tool.jsonl"
    missing_flow_file.write_text(json.dumps(missing_flow_tool), encoding="utf-8")
    with pytest.raises(ValueError):
        run_eval.load_dataset(str(missing_flow_file))

    bad_tool = dict(row)
    bad_tool["expected_tool"] = {"native": "bad", "mcp": "jira_get_issue_by_key"}
    bad_tool_file = tmp_path / "bad_tool.jsonl"
    bad_tool_file.write_text(json.dumps(bad_tool), encoding="utf-8")
    with pytest.raises(ValueError):
        run_eval.load_dataset(str(bad_tool_file))


def test_tool_operation_and_payload_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    assert run_eval._strip_gateway_tool_prefix("x__jira_get_issue_by_key") == "jira_get_issue_by_key"
    assert run_eval._strip_gateway_tool_prefix("x___jira_get_issue_by_key") == "jira_get_issue_by_key"
    assert run_eval._canonical_tool_operation("jira_api_get_issue_by_key") == "get_issue_by_key"
    assert run_eval._canonical_tool_operation("jira_get_issue_by_key") == "get_issue_by_key"
    assert run_eval._canonical_tool_operation("plain") == "plain"

    assert run_eval._issue_payload_complete_for_tool({"key": "K", "summary": "S", "status": "Done"}, "jira_get_issue_by_key")
    assert run_eval._issue_payload_complete_for_tool({"key": "K", "labels": ["x"]}, "jira_get_issue_labels")
    assert not run_eval._issue_payload_complete_for_tool("bad", "jira_get_issue_by_key")
    assert not run_eval._issue_payload_complete_for_tool({"key": "K", "summary": "S", "status": "Unknown"}, "jira_get_issue_by_key")
    assert not run_eval._issue_payload_complete_for_tool({"key": "", "summary": "S", "status": "Done"}, "jira_get_issue_by_key")
    assert not run_eval._issue_payload_complete_for_tool({"key": "K", "labels": "bad"}, "jira_get_issue_labels")

    case = _sample_case()
    assert run_eval.expected_tool_for_flow(case, "native") == "jira_api_get_issue_by_key"
    assert run_eval.expected_tool_for_flow(case, "mcp") == "jira_get_issue_by_key"
    prefixed_native = dict(case)
    prefixed_native["expected_tool"] = {"native": "x__jira_api_get_issue_by_key", "mcp": "jira_get_issue_by_key"}
    assert run_eval.expected_tool_for_flow(prefixed_native, "native") == "x__jira_api_get_issue_by_key"

    assert run_eval._selected_tool_for_flow("native", {"native_selection": {"selected_tool": "n"}}) == "n"
    assert run_eval._selected_tool_for_flow("mcp", {"mcp_selection": {"selected_tool": "m"}}) == "m"
    assert run_eval._selected_tool_for_flow("native", {"actual": {"selected_tool": "from-actual"}}) == "from-actual"
    assert run_eval._selected_tool_for_flow("mcp", {"actual": {"tool": "from-tool"}}) == "from-tool"
    assert run_eval._selected_tool_for_flow("native", {}) == ""
    assert run_eval._actual_tool_for_flow({"actual": {"tool": "legacy-tool"}}, "fallback-tool") == "legacy-tool"
    assert run_eval._selected_tool_for_flow("x", {}) == "jira_get_issue_by_key"
    assert run_eval._selected_operation({"actual": "not-a-dict"}) == ""

    assert run_eval._total_latency_ms({}, {"total_latency_ms": 9.0}) == 9.0
    assert run_eval._total_latency_ms({"metrics": {"stages": [{"latency_ms": 1.2}, {"latency_ms": 2.3}, "bad"]}}, {"total_latency_ms": 0}) == 3.5

    monkeypatch.setattr(run_eval, "lexical_cosine_similarity", lambda a, b: 0.4 if a and b else 0.0)
    assert run_eval._response_text_and_similarity("route", {}, "x") == ("", 0.0)
    generated, similarity = run_eval._response_text_and_similarity("full", {"customer_response": "abc"}, "anchor")
    assert generated == "abc"
    assert similarity == 0.4

    run = PipelineRunResult(execution_arn="arn", payload={}, artifact_s3_uri="s3://bucket/a.json")
    actual = run_eval._actual_payload(
        run_eval.ActualPayloadInput(
            intent_actual="i",
            issue_key_actual="k",
            selected_tool="tool",
            tool="",
            failure_reason="r",
            generated_response="g",
            run=run,
        )
    )
    assert actual["artifact_s3_uri"] == "s3://bucket/a.json"
    assert actual["tool"] == "tool"
    assert run_eval._expected_payload(_sample_case(), "tool")["tool"] == "tool"
    adversarial_case = {**_sample_case(), "adversarial_vector": "tool_name_bait"}
    assert run_eval._expected_payload(adversarial_case, "tool")["adversarial_vector"] == "tool_name_bait"
    metrics = run_eval._case_metrics_payload(
        run_eval.CaseMetricsPayloadInput(
            intent_match=True,
            issue_key_match=True,
            issue_key_resolution_match=True,
            tool_failure=False,
            tool_match=True,
            issue_payload_complete=True,
            business_success=True,
            failure_reason="",
            total_latency_ms=10.0,
            response_similarity=0.9,
            call_construction_failure=False,
            call_construction_attempts=1,
            call_construction_retries=0,
            call_construction_recovered=False,
            grounding_failure=False,
            grounding_attempts=1,
            grounding_retries=0,
            write_case=False,
            write_tool_selected=False,
            write_tool_match=False,
            llm_input_tokens=0,
            llm_output_tokens=0,
            llm_total_tokens=0,
        )
    )
    assert metrics["latency_ms"] == 10.0
    assert metrics["success"] is True


def test_case_result_and_evaluate_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    case = _sample_case()
    run = PipelineRunResult(execution_arn="arn:1", payload=_sample_run_payload(), artifact_s3_uri="s3://bucket/a")
    context = run_eval.CaseRunContext(flow="native", scope="full", iteration=1)
    monkeypatch.setattr(run_eval, "lexical_cosine_similarity", lambda *_args: 0.8)
    row = run_eval._case_result_from_payload(case=case, run=run, context=context)
    assert row["success"] is True
    assert row["metrics"]["business_success"] is True
    assert row["metrics"]["success"] is True
    assert row["actual"]["tool"] == "jira_api_get_issue_by_key"
    assert row["actual"]["execution_arn"] == "arn:1"

    class _Runner:
        def run_case(self, request: Any) -> PipelineRunResult:
            assert request.model_id == "eu.amazon.nova-lite-v1:0"
            assert request.runtime_model_id == "eu.amazon.nova-lite-v1:0"
            assert request.bedrock_region == "eu-west-1"
            assert request.model_provider == "auto"
            assert request.openai_reasoning_effort == "medium"
            assert request.openai_text_verbosity == "medium"
            assert request.openai_max_output_tokens == 2000
            return PipelineRunResult(execution_arn="arn:1", payload=_sample_run_payload(), artifact_s3_uri="s3://bucket/a")

    class _Judge:
        def score_case(self, _result: Dict[str, Any], scope: str) -> Dict[str, Any]:
            assert scope == "route"
            return {"overall_score": 0.9, "label": "pass"}

    config = run_eval.EvaluationConfig(
        dry_run=True,
        scope="route",
        iterations=2,
        model_id="eu.amazon.nova-lite-v1:0",
        runtime_model_id="eu.amazon.nova-lite-v1:0",
        bedrock_region="eu-west-1",
        model_provider="auto",
        runner=_Runner(),
        judge=_Judge(),
        openai_reasoning_effort="medium",
        openai_text_verbosity="medium",
        openai_max_output_tokens=2000,
    )
    flow_result = run_eval.evaluate_flow("native", [case], config)
    assert flow_result["iterations"] == 2
    assert len(flow_result["cases"]) == 2
    assert flow_result["judge_summary"]["evaluated_cases"] == 2
    assert flow_result["token_usage_by_intent"]["status_update"]["case_count"] == 2
    assert flow_result["token_usage_by_intent"]["status_update"]["total_llm_total_tokens"] == 30.0
    assert flow_result["summary"]["total_estimated_cost_usd"] == 0.0
    assert flow_result["token_usage_by_intent"]["status_update"]["total_estimated_cost_usd"] == 0.0
    assert flow_result["adversarial_vector_summary"] == {}
    assert run_eval._count_failure_reasons(flow_result["cases"]) == {}
    assert run_eval._count_failure_reasons(
        [
            {"metrics": {"failure_reason": "mcp_timeout"}},
            {"metrics": {"failure_reason": "mcp_timeout"}},
            {"metrics": {"failure_reason": ""}},
        ]
    ) == {"mcp_timeout": 2}

    outcome = run_eval._derive_case_outcome(
        run_eval.CaseOutcomeInput(
            case=case,
            context=run_eval.CaseRunContext(flow="native", scope="route", iteration=1),
            run_payload={
                "intake": {"intent": case["expected_intent"]},
                "native_selection": {"selected_tool": "jira_api_get_issue_by_key"},
            },
            run_metrics={},
            tool_result={"key": case["expected_issue_key"], "summary": "s", "status": "Done"},
            expected_tool="jira_api_get_issue_by_key",
            total_latency_ms=1.0,
            response_similarity=1.0,
        )
    )
    assert outcome.tool_failure is False
    assert outcome.business_success is True
    assert outcome.tool == "jira_api_get_issue_by_key"


def test_case_result_normalizes_runtime_actual_tool_fields() -> None:
    case = _sample_case()
    payload = _sample_run_payload()
    payload.pop("native_selection", None)
    payload["actual"] = {"selected_tool": "jira_api_get_issue_by_key"}

    row = run_eval._case_result_from_payload(
        case=case,
        run=PipelineRunResult(execution_arn="arn:actual", payload=payload, artifact_s3_uri=""),
        context=run_eval.CaseRunContext(flow="native", scope="route", iteration=1),
    )
    assert row["actual"]["selected_tool"] == "jira_api_get_issue_by_key"
    assert row["actual"]["tool"] == "jira_api_get_issue_by_key"
    assert row["metrics"]["business_success"] is True
    assert row["metrics"]["success"] is True
    assert row["success"] is True


def test_runtime_validation_enforces_required_runtime_args() -> None:
    run_eval._validate_runtime_args(_runtime_args())
    with pytest.raises(ValueError):
        run_eval._validate_runtime_args(_runtime_args(agent_runtime_arn=""))
    run_eval._validate_runtime_args(_runtime_args(scope="full"))
    with pytest.raises(ValueError):
        run_eval._validate_runtime_args(_runtime_args(aws_region=""))
    with pytest.raises(ValueError):
        run_eval._validate_runtime_args(_runtime_args(model_id=""))
    with pytest.raises(ValueError):
        run_eval._validate_runtime_args(_runtime_args(bedrock_region=""))
    with pytest.raises(ValueError):
        run_eval._validate_runtime_args(_runtime_args(enable_judge=True, aws_region="eu"))
    with pytest.raises(ValueError):
        run_eval._validate_runtime_args(
            _runtime_args(
                model_provider="openai",
                model_id="gpt-5.2-codex",
                judge_model_id="gpt-5.2-codex",
                judge_region="eu-west-1",
                enable_judge=True,
            )
        )
    with pytest.raises(ValueError):
        run_eval._validate_runtime_args(_runtime_args(openai_max_output_tokens=32))
    with pytest.raises(ValueError):
        run_eval._validate_runtime_args(_runtime_args(runtime_model_id=""))
    run_eval._validate_runtime_args(_runtime_args(runtime_model_id="gpt-5.2-codex"))


def test_runtime_validation_builds_runner_and_checks_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_runtime_runner_config: Dict[str, Any] = {}

    class _CapturedRuntimeRunner:
        def __init__(self, config: Any) -> None:
            captured_runtime_runner_config.update(vars(config))

    monkeypatch.setattr(run_eval, "AgentCoreRuntimeRunner", _CapturedRuntimeRunner)
    route_runner = run_eval._build_runner(
        Namespace(
            scope="route",
            agent_runtime_arn="arn:aws:bedrock:eu-west-1:123456789012:runtime/test",
            agent_runtime_qualifier="live",
            aws_region="eu-west-1",
            aws_profile="",
        )
    )
    assert isinstance(route_runner, _CapturedRuntimeRunner)
    assert captured_runtime_runner_config["aws_profile"] is None
    assert captured_runtime_runner_config["qualifier"] == "live"
    assert run_eval._runtime_qualifier(_runtime_args(agent_runtime_qualifier="", scope="route")) == "production"
    assert run_eval._runtime_qualifier(_runtime_args(agent_runtime_qualifier="canary", scope="route")) == "canary"
    assert run_eval._runtime_qualifier(_runtime_args(agent_runtime_qualifier="", scope="full")) == ""

    full_runner = run_eval._build_runner(
        Namespace(
            scope="full",
            agent_runtime_arn="arn:aws:bedrock:eu-west-1:123456789012:runtime/test",
            agent_runtime_qualifier="stable",
            aws_region="eu-west-1",
            aws_profile="",
        )
    )
    assert isinstance(full_runner, _CapturedRuntimeRunner)
    assert captured_runtime_runner_config["aws_profile"] is None
    assert captured_runtime_runner_config["qualifier"] == "stable"

    class _Runner:
        def preflight_identity(self) -> Dict[str, str]:
            return {"account": "123", "arn": "arn:aws:iam::123:role/x"}

    assert run_eval._resolve_aws_identity(_Runner(), dry_run=True) == {}
    assert run_eval._resolve_aws_identity(_Runner(), dry_run=False)["account"] == "123"

    class _BadRunner:
        def preflight_identity(self) -> Dict[str, str]:
            raise RuntimeError("bad")

    with pytest.raises(RuntimeError):
        run_eval._resolve_aws_identity(_BadRunner(), dry_run=False)

    class _IncompleteRunner:
        def preflight_identity(self) -> Dict[str, str]:
            return {"account": "", "arn": ""}

    with pytest.raises(RuntimeError):
        run_eval._resolve_aws_identity(_IncompleteRunner(), dry_run=False)



def test_eval_output_and_comparison_helpers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    assert run_eval._selected_flows("native") == ["native"]
    assert run_eval._selected_flows("both") == ["native", "mcp"]

    comp = run_eval._build_comparison_payload(
        [
            {"summary": {"tool_failure_rate": 0.1, "mean_latency_ms": 10, "mean_response_similarity": 0.8, "mean_llm_total_tokens": 100}, "composite_reflection": {"deterministic_release_score": 0.9, "judge_diagnostic_score": 0.7, "overall_reflection_score": 0.8}},
            {"summary": {"tool_failure_rate": 0.2, "mean_latency_ms": 20, "mean_response_similarity": 0.7, "mean_llm_total_tokens": 130}, "composite_reflection": {"deterministic_release_score": 0.8, "judge_diagnostic_score": 0.6, "overall_reflection_score": 0.7}},
        ]
    )
    assert comp["tool_failure_delta"] == 0.1
    assert comp["llm_total_tokens_delta"] == 30
    assert comp["estimated_cost_usd_delta"] == 0.0
    assert comp["total_estimated_cost_usd_delta"] == 0.0
    assert comp["selection_divergence_rate"] == 0.0
    assert comp["selection_divergence_count"] == 0.0

    out_path = tmp_path / "out.json"
    run_eval._write_eval_payload({"x": 1}, str(out_path))
    assert json.loads(out_path.read_text(encoding="utf-8"))["x"] == 1

    payload = {"results": [{"summary": {}}, {"summary": {}}]}
    run_eval._maybe_add_comparison(payload, "native")
    assert "comparison" not in payload
    payload = {
        "results": [
            {"summary": {"tool_failure_rate": 0.1, "mean_latency_ms": 1, "mean_response_similarity": 0.5}, "composite_reflection": {"deterministic_release_score": 1.0, "judge_diagnostic_score": 0.9, "overall_reflection_score": 0.9}},
            {"summary": {"tool_failure_rate": 0.2, "mean_latency_ms": 2, "mean_response_similarity": 0.4}, "composite_reflection": {"deterministic_release_score": 0.8, "judge_diagnostic_score": 0.7, "overall_reflection_score": 0.8}},
        ]
    }
    run_eval._maybe_add_comparison(payload, "both")
    assert "comparison" in payload

    called: Dict[str, Any] = {}
    monkeypatch.setattr(run_eval, "publish_eval_summary_metrics", lambda **kwargs: called.update(kwargs))
    args = Namespace(publish_cloudwatch=False, cloudwatch_namespace="ns", dataset="d", scope="s", aws_region="eu", aws_profile="")
    run_eval._maybe_publish_cloudwatch(args, {"results": []}, "run")
    assert called == {}
    args.publish_cloudwatch = True
    run_eval._maybe_publish_cloudwatch(args, {"results": []}, "run")
    assert called["config"].namespace == "ns"

    run_eval._emit_run_output("out.json", dry_run=True)
    out = capsys.readouterr().out
    assert "WROTE_EVAL=out.json" in out
    assert "SMOKE_OK" in out


def test_live_output_stream_config_and_case_progress_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    class _NoReconfigure:
        reconfigure = None

    class _RaisesReconfigure:
        @staticmethod
        def reconfigure(**_kwargs: Any) -> None:
            raise RuntimeError("boom")

    monkeypatch.setattr(run_eval.sys, "stdout", _NoReconfigure())
    monkeypatch.setattr(run_eval.sys, "stderr", _RaisesReconfigure())
    run_eval._configure_live_output_streams()

    assert run_eval._should_emit_case_progress(processed_cases=10, total_cases=20, result={})
    assert run_eval._should_emit_case_progress(
        processed_cases=11,
        total_cases=20,
        result={"metrics": {"tool_failure": True}},
    )
    assert not run_eval._should_emit_case_progress(
        processed_cases=11,
        total_cases=20,
        result={"metrics": {"tool_failure": False}},
    )


def test_adversarial_vector_and_selection_divergence_helpers() -> None:
    rows = [
        {
            "expected": {"adversarial_vector": "tool_name_bait"},
            "metrics": {
                "business_success": True,
                "tool_failure": False,
                "tool_match": True,
                "call_construction_failure": False,
                "write_case": False,
                "write_tool_match": False,
                "latency_ms": 10.0,
                "llm_total_tokens": 120,
            },
        },
        {
            "expected": {"adversarial_vector": "tool_name_bait"},
            "metrics": {
                "business_success": False,
                "tool_failure": True,
                "tool_match": False,
                "call_construction_failure": True,
                "write_case": True,
                "write_tool_match": False,
                "latency_ms": 20.0,
                "llm_total_tokens": 180,
            },
        },
    ]
    breakdown = run_eval._adversarial_vector_breakdown(
        rows,
        pricing_input_per_1m_tokens_usd=1.0,
        pricing_output_per_1m_tokens_usd=2.0,
    )
    assert breakdown["tool_name_bait"]["case_count"] == 2
    assert breakdown["tool_name_bait"]["business_success_rate"] == 0.5
    assert breakdown["tool_name_bait"]["call_construction_failure_rate"] == 0.5
    assert breakdown["tool_name_bait"]["mean_llm_total_tokens"] == 150.0
    assert breakdown["tool_name_bait"]["total_llm_input_tokens"] == 0.0
    assert breakdown["tool_name_bait"]["total_llm_output_tokens"] == 0.0
    assert breakdown["tool_name_bait"]["total_estimated_cost_usd"] == 0.0

    divergence = run_eval._selection_divergence_metrics(
        native_result={
            "cases": [
                {"case_id": "C1", "actual": {"selected_tool": "jira_api_get_issue_by_key"}},
                {"case_id": "C2", "actual": {"selected_tool": "jira_api_get_issue_status_snapshot"}},
            ]
        },
        mcp_result={
            "cases": [
                {"case_id": "C1", "actual": {"selected_tool": "jira-issue-tools___jira_get_issue_by_key"}},
                {"case_id": "C2", "actual": {"selected_tool": "jira-issue-tools___jira_get_issue_labels"}},
            ]
        },
    )
    assert divergence["selection_divergence_compared_cases"] == 2.0
    assert divergence["selection_divergence_count"] == 1.0
    assert divergence["selection_divergence_rate"] == 0.5

    divergence_with_iterations = run_eval._selection_divergence_metrics(
        native_result={
            "cases": [
                {"iteration": 1, "case_id": "C1", "actual": {"selected_tool": "jira_api_get_issue_by_key"}},
                {"iteration": 2, "case_id": "C1", "actual": {"selected_tool": "jira_api_get_issue_by_key"}},
            ]
        },
        mcp_result={
            "cases": [
                {"iteration": 1, "case_id": "C1", "actual": {"selected_tool": "jira_get_issue_by_key"}},
                {"iteration": 2, "case_id": "C1", "actual": {"selected_tool": "jira_get_issue_labels"}},
            ]
        },
    )
    assert divergence_with_iterations["selection_divergence_compared_cases"] == 2.0
    assert divergence_with_iterations["selection_divergence_count"] == 1.0
    assert divergence_with_iterations["selection_divergence_rate"] == 0.5

    divergence_from_tool_alias = run_eval._selection_divergence_metrics(
        native_result={"cases": [{"case_id": "C1", "actual": {"tool": "jira_api_get_issue_by_key"}}]},
        mcp_result={"cases": [{"case_id": "C1", "actual": {"tool": "jira_get_issue_by_key"}}]},
    )
    assert divergence_from_tool_alias["selection_divergence_compared_cases"] == 1.0
    assert divergence_from_tool_alias["selection_divergence_count"] == 0.0
    assert divergence_from_tool_alias["selection_divergence_rate"] == 0.0


def test_pricing_snapshot_resolution_base_and_reasoning_models(tmp_path: Path) -> None:
    catalog_path = tmp_path / "pricing.json"
    catalog_path.write_text(
        json.dumps(
            {
                "version": "v-test",
                "models": {
                    "model-a": {
                        "input_per_1m_tokens_usd": 1.0,
                        "output_per_1m_tokens_usd": 2.0,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    snapshot = run_eval._pricing_snapshot_for_model(_pricing_snapshot_args(catalog_path))
    assert snapshot["source"] == "catalog"
    assert snapshot["catalog_version"] == "v-test"
    assert snapshot["pricing_model_key"] == "model-a"
    assert snapshot["reasoning_effort"] == "medium"
    assert snapshot["input_per_1m_tokens_usd"] == 1.0
    assert snapshot["output_per_1m_tokens_usd"] == 2.0

    catalog_path.write_text(
        json.dumps(
            {
                "version": "v-test-2",
                "models": {
                    "model-a": {
                        "input_per_1m_tokens_usd": 1.0,
                        "output_per_1m_tokens_usd": 2.0,
                    },
                    "model-a:reasoning-high": {
                        "input_per_1m_tokens_usd": 3.0,
                        "output_per_1m_tokens_usd": 4.0,
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    reasoning_specific = run_eval._pricing_snapshot_for_model(
        _pricing_snapshot_args(catalog_path, openai_reasoning_effort="high")
    )
    assert reasoning_specific["pricing_model_key"] == "model-a:reasoning-high"
    assert reasoning_specific["input_per_1m_tokens_usd"] == 3.0
    assert reasoning_specific["output_per_1m_tokens_usd"] == 4.0


def test_pricing_snapshot_validation_and_overrides(tmp_path: Path) -> None:
    catalog_path = tmp_path / "pricing.json"
    catalog_path.write_text(
        json.dumps(
            {
                "version": "v-test",
                "models": {
                    "model-a": {
                        "input_per_1m_tokens_usd": 1.0,
                        "output_per_1m_tokens_usd": 2.0,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    override = run_eval._pricing_snapshot_for_model(
        _pricing_snapshot_args(
            catalog_path,
            model_id="model-b",
            price_input_per_1m_tokens_usd="3",
            price_output_per_1m_tokens_usd="4",
            openai_reasoning_effort="low",
        )
    )
    assert override["source"] == "cli_override"
    assert override["input_per_1m_tokens_usd"] == 3.0
    assert override["output_per_1m_tokens_usd"] == 4.0

    with pytest.raises(ValueError):
        run_eval._pricing_snapshot_for_model(
            _pricing_snapshot_args(
                catalog_path,
                model_id="model-b",
                price_input_per_1m_tokens_usd="3",
            )
        )
    with pytest.raises(ValueError):
        run_eval._pricing_snapshot_for_model(_pricing_snapshot_args(catalog_path, model_id="missing-model"))


def test_estimate_cost_usd_supports_million_token_inputs() -> None:
    estimated = run_eval._estimate_cost_usd(
        llm_input_tokens=1_000_000,
        llm_output_tokens=2_000_000,
        input_per_1m_tokens_usd=1.0,
        output_per_1m_tokens_usd=2.0,
    )
    assert estimated == 5.0


def test_main_and_module_guard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dataset_path = tmp_path / "dataset.jsonl"
    dataset_path.write_text(json.dumps(_sample_case()) + "\n", encoding="utf-8")

    class _Runner:
        def run_case(self, _request: Any) -> PipelineRunResult:
            payload = _sample_run_payload()
            payload["metrics"] = {"stages": [{"latency_ms": 1.5}]}
            return PipelineRunResult(execution_arn="arn:exec", payload=payload, artifact_s3_uri="s3://bucket/key")

        def preflight_identity(self) -> Dict[str, str]:
            return {"account": "123", "arn": "arn:aws:iam::123:role/x"}

    monkeypatch.setattr(
        run_eval,
        "parse_args",
        lambda: Namespace(
            dataset=str(dataset_path),
            flow="both",
            output=str(tmp_path / "written.json"),
            iterations=1,
            scope="route",
            run_id="run-1",
            dry_run=False,
            agent_runtime_arn="arn:aws:bedrock:eu-west-1:123456789012:runtime/test",
            agent_runtime_qualifier="",
            aws_profile="",
            aws_region="eu-west-1",
            poll_interval_seconds=0.1,
            execution_timeout_seconds=1,
            model_id="eu.amazon.nova-lite-v1:0",
            runtime_model_id="eu.amazon.nova-lite-v1:0",
            bedrock_region="eu-west-1",
            model_provider="auto",
            openai_reasoning_effort="medium",
            openai_text_verbosity="medium",
            openai_max_output_tokens=2000,
            model_pricing_catalog="evals/model_pricing_usd_per_1m_tokens.json",
            price_input_per_1m_tokens_usd="",
            price_output_per_1m_tokens_usd="",
            publish_cloudwatch=False,
            cloudwatch_namespace="ns",
            enable_judge=False,
            judge_model_id="model",
            judge_region="eu-west-1",
        ),
    )
    monkeypatch.setattr(run_eval, "_build_runner", lambda _args: _Runner())
    assert run_eval.main() == 0
    written = json.loads((tmp_path / "written.json").read_text(encoding="utf-8"))
    assert written["run_id"] == "run-1"
    assert "comparison" in written
    assert written["agent_runtime_arn"] == "arn:aws:bedrock:eu-west-1:123456789012:runtime/test"
    assert written["model"]["model_id"] == "eu.amazon.nova-lite-v1:0"
    assert written["model"]["runtime_model_id"] == "eu.amazon.nova-lite-v1:0"
    assert written["model"]["provider"] == "auto"
    assert written["model"]["openai_reasoning_effort"] == "medium"
    assert written["model"]["openai_text_verbosity"] == "medium"
    assert written["model"]["openai_max_output_tokens"] == 2000
    assert written["model"]["pricing_input_per_1m_tokens_usd"] > 0
    assert written["model"]["pricing_output_per_1m_tokens_usd"] > 0
    assert written["model_pricing_snapshot"]["gateway_model_id"] == "eu.amazon.nova-lite-v1:0"
    assert written["model_pricing_snapshot"]["source"] == "catalog"
    assert written["model_pricing_snapshot"]["pricing_model_key"] == "eu.amazon.nova-lite-v1:0"
    assert written["model_pricing_snapshot"]["reasoning_effort"] == "medium"
    assert written["model_parity"]["gateway_model_id"] == "eu.amazon.nova-lite-v1:0"
    assert written["model_parity"]["runtime_model_id"] == "eu.amazon.nova-lite-v1:0"

    # Execute __main__ path via subprocess CLI smoke test (argument validation path).
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "evals.run_eval",
        ],
        cwd=str(Path(__file__).resolve().parents[1]),
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 2
    assert "--dataset" in completed.stderr
