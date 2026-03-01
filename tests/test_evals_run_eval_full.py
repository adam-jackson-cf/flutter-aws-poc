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


def _sample_run_payload() -> Dict[str, Any]:
    return {
        "intake": {"intent": "status_update"},
        "tool_result": {"key": "JRASERVER-1", "summary": "s", "status": "Done"},
        "generated_response": {"customer_response": "status update for JRASERVER-1"},
        "run_metrics": {"total_latency_ms": 12.5, "tool_failure": False},
        "native_selection": {"selected_tool": "jira_api_get_issue_by_key"},
        "mcp_selection": {"selected_tool": "jira_get_issue_by_key"},
    }


def test_parse_args_and_simple_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_eval.py", "--dataset", "d.jsonl", "--flow", "native", "--state-machine-arn", "arn", "--aws-region", "eu-west-1"],
    )
    args = run_eval.parse_args()
    assert args.flow == "native"
    assert run_eval.utc_compact_now().endswith("Z")
    assert run_eval.sanitize_run_id(" bad id ") == "bad-id"

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

    config = run_eval.EvaluationConfig(dry_run=True, scope="route", iterations=1, runner=object(), judge=None)
    with pytest.raises(FrozenInstanceError):
        config.dry_run = False  # type: ignore[misc]

    payload = run_eval.ActualPayloadInput(
        intent_actual="status_update",
        issue_key_actual="JRASERVER-1",
        selected_tool="jira_get_issue_by_key",
        failure_reason="",
        generated_response="ok",
        run=PipelineRunResult(execution_arn="arn", payload={}, artifact_s3_uri="s3://bucket/key"),
    )
    with pytest.raises(FrozenInstanceError):
        payload.selected_tool = "jira_get_issue_status_snapshot"  # type: ignore[misc]

    metrics = run_eval.CaseMetricsPayloadInput(
        intent_match=True,
        issue_key_match=True,
        tool_failure=False,
        tool_match=True,
        issue_payload_complete=True,
        business_success=True,
        failure_reason="",
        total_latency_ms=1.0,
        response_similarity=1.0,
    )
    with pytest.raises(FrozenInstanceError):
        metrics.tool_failure = True  # type: ignore[misc]

    outcome = run_eval.CaseOutcome(
        intent_actual="status_update",
        issue_key_actual="JRASERVER-1",
        selected_tool="jira_get_issue_by_key",
        failure_reason="",
        issue_payload_complete=True,
        tool_failure=False,
        intent_match=True,
        issue_key_match=True,
        tool_match=True,
        business_success=True,
        total_latency_ms=1.0,
        response_similarity=1.0,
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
    assert run_eval._selected_tool_for_flow("x", {}) == "jira_get_issue_by_key"

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
            failure_reason="r",
            generated_response="g",
            run=run,
        )
    )
    assert actual["artifact_s3_uri"] == "s3://bucket/a.json"
    assert run_eval._expected_payload(_sample_case(), "tool")["tool"] == "tool"
    metrics = run_eval._case_metrics_payload(
        run_eval.CaseMetricsPayloadInput(
            intent_match=True,
            issue_key_match=True,
            tool_failure=False,
            tool_match=True,
            issue_payload_complete=True,
            business_success=True,
            failure_reason="",
            total_latency_ms=10.0,
            response_similarity=0.9,
        )
    )
    assert metrics["latency_ms"] == 10.0


def test_case_result_and_evaluate_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    case = _sample_case()
    run = PipelineRunResult(execution_arn="arn:1", payload=_sample_run_payload(), artifact_s3_uri="s3://bucket/a")
    context = run_eval.CaseRunContext(flow="native", scope="full", iteration=1)
    monkeypatch.setattr(run_eval, "lexical_cosine_similarity", lambda *_args: 0.8)
    row = run_eval._case_result_from_payload(case=case, run=run, context=context)
    assert row["metrics"]["business_success"] is True
    assert row["actual"]["execution_arn"] == "arn:1"

    class _Runner:
        def run_case(self, _request: Any) -> PipelineRunResult:
            return PipelineRunResult(execution_arn="arn:1", payload=_sample_run_payload(), artifact_s3_uri="s3://bucket/a")

    class _Judge:
        def score_case(self, _result: Dict[str, Any], scope: str) -> Dict[str, Any]:
            assert scope == "route"
            return {"overall_score": 0.9, "label": "pass"}

    config = run_eval.EvaluationConfig(dry_run=True, scope="route", iterations=2, runner=_Runner(), judge=_Judge())
    flow_result = run_eval.evaluate_flow("native", [case], config)
    assert flow_result["iterations"] == 2
    assert len(flow_result["cases"]) == 2
    assert flow_result["judge_summary"]["evaluated_cases"] == 2
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


def test_runtime_validation_and_plumbing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    args = Namespace(state_machine_arn="arn", aws_region="eu-west-1", enable_judge=False, judge_region="")
    run_eval._validate_runtime_args(args)
    with pytest.raises(ValueError):
        run_eval._validate_runtime_args(Namespace(state_machine_arn="", aws_region="eu-west-1", enable_judge=False, judge_region=""))
    with pytest.raises(ValueError):
        run_eval._validate_runtime_args(Namespace(state_machine_arn="arn", aws_region="", enable_judge=False, judge_region=""))
    with pytest.raises(ValueError):
        run_eval._validate_runtime_args(Namespace(state_machine_arn="arn", aws_region="eu", enable_judge=True, judge_region=""))

    captured_runner_config: Dict[str, Any] = {}

    class _CapturedRunner:
        def __init__(self, config: Any) -> None:
            captured_runner_config.update(vars(config))

    monkeypatch.setattr(run_eval, "AwsPipelineRunner", _CapturedRunner)
    built_runner = run_eval._build_runner(
        Namespace(
            state_machine_arn="arn",
            aws_region="eu-west-1",
            aws_profile="",
            poll_interval_seconds=0.5,
            execution_timeout_seconds=30,
        )
    )
    assert isinstance(built_runner, _CapturedRunner)
    assert captured_runner_config["aws_profile"] is None
    assert captured_runner_config["execution_timeout_seconds"] == 30

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

    assert run_eval._selected_flows("native") == ["native"]
    assert run_eval._selected_flows("both") == ["native", "mcp"]

    comp = run_eval._build_comparison_payload(
        [
            {"summary": {"tool_failure_rate": 0.1, "mean_latency_ms": 10, "mean_response_similarity": 0.8}, "composite_reflection": {"deterministic_release_score": 0.9, "judge_diagnostic_score": 0.7, "overall_reflection_score": 0.8}},
            {"summary": {"tool_failure_rate": 0.2, "mean_latency_ms": 20, "mean_response_similarity": 0.7}, "composite_reflection": {"deterministic_release_score": 0.8, "judge_diagnostic_score": 0.6, "overall_reflection_score": 0.7}},
        ]
    )
    assert comp["tool_failure_delta"] == 0.1

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
            state_machine_arn="arn",
            aws_profile="",
            aws_region="eu-west-1",
            poll_interval_seconds=0.1,
            execution_timeout_seconds=1,
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
