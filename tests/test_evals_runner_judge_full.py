import io
import json
from pathlib import Path
from typing import Any, Dict

import pytest

from evals import aws_pipeline_runner, cloudwatch_publish, judge


def test_parse_s3_uri_valid_and_invalid() -> None:
    bucket, key = aws_pipeline_runner._parse_s3_uri("s3://bucket/key/path.json")
    assert bucket == "bucket"
    assert key == "key/path.json"
    with pytest.raises(ValueError):
        aws_pipeline_runner._parse_s3_uri("https://example.com/nope")


def test_runner_init_requires_required_args() -> None:
    with pytest.raises(ValueError):
        aws_pipeline_runner.AgentCoreRuntimeRunner(
            aws_pipeline_runner.AgentCoreRuntimeRunnerConfig(agent_runtime_arn="", aws_region="eu-west-1")
        )
    with pytest.raises(ValueError):
        aws_pipeline_runner.AgentCoreRuntimeRunner(
            aws_pipeline_runner.AgentCoreRuntimeRunnerConfig(
                agent_runtime_arn="arn:aws:bedrock:eu-west-1:123456789012:runtime/test",
                aws_region="",
            )
        )


class _FakeBody:
    def __init__(self, text: str) -> None:
        self._text = text

    def read(self) -> bytes:
        return self._text.encode("utf-8")


class _FakeS3:
    def __init__(self, payload: Dict[str, Any] | None = None) -> None:
        self.payload = payload or _valid_artifact_payload(flow="native")

    def get_object(self, Bucket: str, Key: str) -> Dict[str, Any]:  # noqa: N803
        assert Bucket == "bucket-a"
        assert Key == "artifact.json"
        return {"Body": _FakeBody(json.dumps(self.payload))}


class _FakeSts:
    def get_caller_identity(self) -> Dict[str, str]:
        return {"Account": "123", "Arn": "arn:aws:iam::123:role/test", "UserId": "uid"}


def _valid_artifact_payload(flow: str) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "contract_version": "2.0.0",
        "flow": flow,
        "intake": {"intent": "status_update", "issue_key": "JRASERVER-1"},
        "tool_result": {"key": "JRASERVER-1"},
        "run_metrics": {"tool_failure": False, "business_success": True},
    }
    if flow == "native":
        payload["native_selection"] = {"selected_tool": "jira_api_get_issue_by_key"}
    elif flow == "mcp":
        payload["mcp_selection"] = {"selected_tool": "jira_get_issue_by_key"}
    return payload


def test_runtime_runner_run_case_success_with_direct_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: Dict[str, Any] = {}

    class _RuntimeClient:
        def invoke_agent_runtime(self, **kwargs: Any) -> Dict[str, Any]:
            captured["request"] = kwargs
            return {
                "traceId": "trace-123",
                "response": io.BytesIO(json.dumps(_valid_artifact_payload(flow="native")).encode("utf-8")),
            }

    class _Session:
        def client(self, service_name: str) -> Any:
            if service_name == "bedrock-agentcore":
                return _RuntimeClient()
            if service_name == "s3":
                return _FakeS3()
            return _FakeSts()

    monkeypatch.setattr(aws_pipeline_runner.boto3, "Session", lambda **_kwargs: _Session())
    runner = aws_pipeline_runner.AgentCoreRuntimeRunner(
        aws_pipeline_runner.AgentCoreRuntimeRunnerConfig(
            agent_runtime_arn="arn:aws:bedrock:eu-west-1:123456789012:runtime/test",
            aws_region="eu-west-1",
            qualifier="live",
        )
    )
    result = runner.run_case(
        aws_pipeline_runner.PipelineRunRequest(
            flow="native",
            request_text="check JRASERVER-1",
            case_id="case",
            expected_tool="jira_get_issue_by_key",
            dry_run=False,
            runtime_model_id="eu.amazon.nova-lite-v1:0",
            model_provider="openai",
            openai_reasoning_effort="high",
            openai_text_verbosity="medium",
        )
    )
    sent_payload = json.loads(captured["request"]["payload"].decode("utf-8"))
    assert captured["request"]["agentRuntimeArn"].endswith(":runtime/test")
    assert captured["request"]["contentType"] == "application/json"
    assert captured["request"]["accept"] == "application/json"
    assert captured["request"]["qualifier"] == "live"
    assert sent_payload["runtime_model_id"] == "eu.amazon.nova-lite-v1:0"
    assert sent_payload["model_provider"] == "openai"
    assert result.execution_arn == "trace-123"
    assert result.artifact_s3_uri == ""
    assert result.payload["native_selection"]["selected_tool"] == "jira_api_get_issue_by_key"


def test_runtime_runner_reads_artifact_uri_from_runtime_response(monkeypatch: pytest.MonkeyPatch) -> None:
    class _RuntimeClient:
        def invoke_agent_runtime(self, **_kwargs: Any) -> Dict[str, Any]:
            return {
                "response": io.BytesIO(json.dumps({"artifact_s3_uri": "s3://bucket-a/artifact.json"}).encode("utf-8")),
            }

    class _Session:
        def client(self, service_name: str) -> Any:
            if service_name == "bedrock-agentcore":
                return _RuntimeClient()
            if service_name == "s3":
                return _FakeS3(_valid_artifact_payload(flow="native"))
            return _FakeSts()

    monkeypatch.setattr(aws_pipeline_runner.boto3, "Session", lambda **_kwargs: _Session())
    runner = aws_pipeline_runner.AgentCoreRuntimeRunner(
        aws_pipeline_runner.AgentCoreRuntimeRunnerConfig(
            agent_runtime_arn="arn:aws:bedrock:eu-west-1:123456789012:runtime/test",
            aws_region="eu-west-1",
        )
    )
    result = runner.run_case(
        aws_pipeline_runner.PipelineRunRequest(
            flow="native",
            request_text="x",
            case_id="c",
            expected_tool="tool",
            dry_run=False,
        )
    )
    assert result.execution_arn == "agent-runtime://native/c"
    assert result.artifact_s3_uri == "s3://bucket-a/artifact.json"
    assert result.payload["tool_result"]["key"] == "JRASERVER-1"


def test_runtime_runner_rejects_invalid_runtime_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    class _RuntimeClient:
        def invoke_agent_runtime(self, **_kwargs: Any) -> Dict[str, Any]:
            return {"response": io.BytesIO(b"not-json")}

    class _Session:
        def client(self, service_name: str) -> Any:
            if service_name == "bedrock-agentcore":
                return _RuntimeClient()
            if service_name == "s3":
                return _FakeS3()
            return _FakeSts()

    monkeypatch.setattr(aws_pipeline_runner.boto3, "Session", lambda **_kwargs: _Session())
    runner = aws_pipeline_runner.AgentCoreRuntimeRunner(
        aws_pipeline_runner.AgentCoreRuntimeRunnerConfig(
            agent_runtime_arn="arn:aws:bedrock:eu-west-1:123456789012:runtime/test",
            aws_region="eu-west-1",
        )
    )
    with pytest.raises(RuntimeError, match="agent_runtime_response_invalid_json"):
        runner.run_case(
            aws_pipeline_runner.PipelineRunRequest(
                flow="native",
                request_text="x",
                case_id="c",
                expected_tool="tool",
                dry_run=False,
            )
        )


def test_artifact_validation_errors_for_payload_shape() -> None:
    with pytest.raises(RuntimeError, match="artifact_schema_invalid:payload_not_object"):
        aws_pipeline_runner._validate_artifact_payload(payload=[], flow="native")  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="artifact_schema_invalid:native_selection.selected_tool_not_string"):
        aws_pipeline_runner._validate_artifact_payload(
            payload={
                "contract_version": "2.0.0",
                "flow": "native",
                "intake": {"intent": "status_update"},
                "tool_result": {"key": "JRASERVER-1"},
                "run_metrics": {"tool_failure": False},
                "native_selection": {"selected_tool": 123},
            },
            flow="native",
        )

    with pytest.raises(RuntimeError, match="artifact_schema_invalid:flow_mismatch:expected=native:actual=mcp"):
        aws_pipeline_runner._validate_artifact_payload(
            payload={
                "contract_version": "2.0.0",
                "flow": "mcp",
                "intake": {"intent": "status_update"},
                "tool_result": {"key": "JRASERVER-1"},
                "run_metrics": {"tool_failure": False},
                "native_selection": {"selected_tool": "jira_api_get_issue_by_key"},
            },
            flow="native",
        )

    with pytest.raises(RuntimeError, match="artifact_schema_invalid:contract_version_missing"):
        aws_pipeline_runner._validate_artifact_payload(
            payload={
                "flow": "native",
                "intake": {"intent": "status_update"},
                "tool_result": {"key": "JRASERVER-1"},
                "run_metrics": {"tool_failure": False},
                "native_selection": {"selected_tool": "jira_api_get_issue_by_key"},
            },
            flow="native",
        )

    with pytest.raises(
        RuntimeError,
        match="artifact_schema_invalid:contract_version_mismatch:expected=2.0.0:actual=1.0.0",
    ):
        aws_pipeline_runner._validate_artifact_payload(
            payload={
                "contract_version": "1.0.0",
                "flow": "native",
                "intake": {"intent": "status_update"},
                "tool_result": {"key": "JRASERVER-1"},
                "run_metrics": {"tool_failure": False},
                "native_selection": {"selected_tool": "jira_api_get_issue_by_key"},
            },
            flow="native",
            expected_contract_version="2.0.0",
        )

    with pytest.raises(RuntimeError, match="artifact_schema_invalid:eval_schema_version_missing"):
        aws_pipeline_runner.validate_eval_artifact_schema_version(
            payload={},
            expected_eval_schema_version="2.0.0",
        )

    with pytest.raises(
        RuntimeError,
        match="artifact_schema_invalid:eval_schema_version_mismatch:expected=2.0.0:actual=1.0.0",
    ):
        aws_pipeline_runner.validate_eval_artifact_schema_version(
            payload={"eval_schema_version": "1.0.0"},
            expected_eval_schema_version="2.0.0",
        )


def test_artifact_validation_normalizes_actual_tool_fields() -> None:
    native_payload = {
        "contract_version": "2.0.0",
        "flow": "native",
        "intake": {"intent": "status_update"},
        "tool_result": {"key": "JRASERVER-1"},
        "run_metrics": {"tool_failure": False},
        "actual": {"selected_tool": "jira_api_get_issue_by_key"},
    }
    aws_pipeline_runner._validate_artifact_payload(payload=native_payload, flow="native")
    assert native_payload["actual"]["selected_tool"] == "jira_api_get_issue_by_key"
    assert native_payload["actual"]["tool"] == "jira_api_get_issue_by_key"
    assert native_payload["native_selection"]["selected_tool"] == "jira_api_get_issue_by_key"

    mcp_payload = {
        "contract_version": "2.0.0",
        "flow": "mcp",
        "intake": {"intent": "status_update"},
        "tool_result": {"key": "JRASERVER-1"},
        "run_metrics": {"tool_failure": False},
        "actual": {"tool": "jira_get_issue_by_key"},
    }
    aws_pipeline_runner._validate_artifact_payload(payload=mcp_payload, flow="mcp")
    assert mcp_payload["actual"]["selected_tool"] == "jira_get_issue_by_key"
    assert mcp_payload["actual"]["tool"] == "jira_get_issue_by_key"
    assert mcp_payload["mcp_selection"]["selected_tool"] == "jira_get_issue_by_key"


def test_normalize_selection_payload_handles_unknown_flow_without_changes() -> None:
    payload = {
        "actual": {"selected_tool": "jira_api_get_issue_by_key"},
        "native_selection": {"selected_tool": "jira_api_get_issue_by_key"},
    }
    aws_pipeline_runner._normalize_selection_payload(payload=payload, flow="unknown")
    assert payload["native_selection"]["selected_tool"] == "jira_api_get_issue_by_key"


def test_normalize_selection_payload_backfills_selected_tool_into_selection_dict() -> None:
    payload = {
        "actual": {"selected_tool": "jira_api_get_issue_by_key"},
        "native_selection": {"selected_tool": 123},
    }
    aws_pipeline_runner._normalize_selection_payload(payload=payload, flow="native")
    assert payload["native_selection"]["selected_tool"] == "jira_api_get_issue_by_key"


def test_judge_helpers_and_score_case(monkeypatch: pytest.MonkeyPatch) -> None:
    assert judge._bounded_score("2.0") == 1.0
    assert judge._bounded_score("-1") == 0.0
    assert judge._bounded_score("bad") == 0.0

    with pytest.raises(judge.JudgeError):
        judge._extract_json_object("no braces")

    repaired = judge._extract_json_object('prefix {"tool_choice_score":"0.5","rationale":"x\\\\q"} suffix')
    assert repaired["tool_choice_score"] == "0.5"
    repaired2 = judge._extract_json_object('prefix {"tool_choice_score":"0.5","rationale":"x\\q"} suffix')
    assert repaired2["rationale"] == "x\\q"

    with pytest.raises(ValueError):
        judge.BedrockJudge(model_id="", region="eu-west-1")
    with pytest.raises(ValueError):
        judge.BedrockJudge(model_id="m", region="")

    class _FakeClient:
        def converse(self, **kwargs: Any) -> Dict[str, Any]:
            assert kwargs["modelId"] == "model"
            return {
                "output": {
                    "message": {
                        "content": [
                            {"text": '{"tool_choice_score":1.2,"execution_reliability_score":"0.7","response_quality_score":0.4,"overall_score":0.8,"label":"UNKNOWN","rationale":"ok"}'}
                        ]
                    }
                }
            }

    monkeypatch.setattr(judge.boto3, "client", lambda *_args, **_kwargs: _FakeClient())
    b = judge.BedrockJudge(model_id="model", region="eu-west-1")
    scored = b.score_case(
        case_result={
            "request_text": "Need update",
            "expected": {"tool": "jira_get_issue_by_key"},
            "actual": {"selected_tool": "jira_get_issue_by_key"},
            "metrics": {"tool_match": True},
        },
        scope="route",
    )
    assert scored["tool_choice_score"] == 1.0
    assert scored["label"] == "review"
    assert scored["overall_score"] == 0.8


def test_cloudwatch_publish_input_validation_and_chunking(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError):
        cloudwatch_publish.publish_eval_summary_metrics(
            summaries=[],
            config=cloudwatch_publish.CloudWatchPublishConfig(
                namespace="x",
                run_id="r",
                dataset="d",
                scope="s",
                aws_region="eu-west-1",
            ),
        )
    with pytest.raises(ValueError):
        cloudwatch_publish.publish_eval_summary_metrics(
            summaries=[{"flow": "x", "summary": {}}],
            config=cloudwatch_publish.CloudWatchPublishConfig(
                namespace="",
                run_id="r",
                dataset="d",
                scope="s",
                aws_region="eu-west-1",
            ),
        )
    with pytest.raises(ValueError):
        cloudwatch_publish.publish_eval_summary_metrics(
            summaries=[{"flow": "x", "summary": {}}],
            config=cloudwatch_publish.CloudWatchPublishConfig(
                namespace="ns",
                run_id="r",
                dataset="d",
                scope="s",
                aws_region="",
            ),
        )

    sent_batches: list[int] = []

    class _CW:
        def put_metric_data(self, Namespace: str, MetricData: list[Dict[str, Any]]) -> None:  # noqa: N803
            assert Namespace == "ns"
            sent_batches.append(len(MetricData))

    class _Session:
        def client(self, service_name: str) -> _CW:
            assert service_name == "cloudwatch"
            return _CW()

    monkeypatch.setattr(cloudwatch_publish.boto3, "Session", lambda **_kwargs: _Session())

    summary = {
        "intent_accuracy": 1,
        "issue_key_accuracy": 1,
        "tool_match_rate": 1,
        "tool_failure_rate": 0,
        "business_success_rate": 1,
        "issue_payload_completeness_rate": 1,
        "issue_key_resolution_match_rate": 1,
        "mean_latency_ms": 10,
        "mean_latency_success_ms": 9,
        "mean_latency_failure_ms": 1,
        "mean_response_similarity": 0.9,
        "tool_failure_ci95_low": 0,
        "tool_failure_ci95_high": 0.1,
        "grounding_failure_rate": 0.0,
        "mean_grounding_attempts": 1.0,
        "mean_grounding_retries": 0.0,
        "call_construction_failure_rate": 0.0,
        "mean_call_construction_attempts": 1.0,
        "mean_call_construction_retries": 0.0,
        "call_construction_recovery_rate": 0.0,
        "write_case_count": 1.0,
        "write_tool_selected_rate": 1.0,
        "write_tool_match_rate": 1.0,
        "total_llm_input_tokens": 200.0,
        "total_llm_output_tokens": 40.0,
        "total_llm_total_tokens": 240.0,
        "mean_llm_input_tokens": 100.0,
        "mean_llm_output_tokens": 20.0,
        "mean_llm_total_tokens": 120.0,
        "total_estimated_cost_usd": 0.0024,
        "mean_estimated_cost_usd": 0.0012,
    }
    rows = [{"flow": f"flow{i}", "summary": summary} for i in range(2)]
    cloudwatch_publish.publish_eval_summary_metrics(
        summaries=rows,
        config=cloudwatch_publish.CloudWatchPublishConfig(
            namespace="ns",
            run_id="run",
            dataset="dataset",
            scope="route",
            aws_region="eu-west-1",
        ),
    )
    assert sent_batches

    with pytest.raises(ValueError):
        cloudwatch_publish.publish_eval_summary_metrics(
            summaries=[{"flow": "native", "summary": "bad"}],
            config=cloudwatch_publish.CloudWatchPublishConfig(
                namespace="ns",
                run_id="run",
                dataset="dataset",
                scope="route",
                aws_region="eu-west-1",
            ),
        )
