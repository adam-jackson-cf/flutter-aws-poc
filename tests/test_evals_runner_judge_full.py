import io
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
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
        aws_pipeline_runner.AwsPipelineRunner(
            aws_pipeline_runner.AwsPipelineRunnerConfig(state_machine_arn="", aws_region="eu-west-1")
        )
    with pytest.raises(ValueError):
        aws_pipeline_runner.AwsPipelineRunner(
            aws_pipeline_runner.AwsPipelineRunnerConfig(state_machine_arn="arn:aws:states:123", aws_region="")
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


class _FakeSfn:
    def __init__(self, descriptions: list[Dict[str, Any]]) -> None:
        self._descriptions = descriptions
        self.start_called = False

    def start_execution(self, **kwargs: Any) -> Dict[str, str]:
        self.start_called = True
        assert "stateMachineArn" in kwargs
        return {"executionArn": "arn:exec:1"}

    def describe_execution(self, executionArn: str) -> Dict[str, Any]:  # noqa: N803
        assert executionArn == "arn:exec:1"
        return self._descriptions.pop(0)


class _FakeSession:
    def __init__(self, sfn: _FakeSfn, s3: _FakeS3, sts: _FakeSts) -> None:
        self._clients = {"stepfunctions": sfn, "s3": s3, "sts": sts}

    def client(self, service_name: str) -> Any:
        return self._clients[service_name]


def _valid_artifact_payload(flow: str) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
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


def _install_boto3_session(monkeypatch: pytest.MonkeyPatch, descriptions: list[Dict[str, Any]], s3_payload: Dict[str, Any] | None = None) -> None:
    fake_session = _FakeSession(_FakeSfn(descriptions), _FakeS3(s3_payload), _FakeSts())

    def _session(**kwargs: Any) -> _FakeSession:
        assert kwargs["region_name"] == "eu-west-1"
        return fake_session

    monkeypatch.setattr(aws_pipeline_runner.boto3, "Session", _session)


def test_runner_preflight_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_boto3_session(monkeypatch, descriptions=[{"status": "SUCCEEDED", "output": json.dumps({"artifact_s3_uri": "s3://bucket-a/artifact.json"})}])
    runner = aws_pipeline_runner.AwsPipelineRunner(
        aws_pipeline_runner.AwsPipelineRunnerConfig("arn:aws:states:abc", "eu-west-1")
    )
    identity = runner.preflight_identity()
    assert identity["account"] == "123"
    assert identity["arn"].startswith("arn:aws:iam")


def test_runner_init_with_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: Dict[str, Any] = {}

    class _Session:
        def client(self, service_name: str) -> Any:
            if service_name == "stepfunctions":
                return _FakeSfn([{"status": "SUCCEEDED", "output": json.dumps({"artifact_s3_uri": "s3://bucket-a/artifact.json"})}])
            if service_name == "s3":
                return _FakeS3()
            return _FakeSts()

    def _session(**kwargs: Any) -> _Session:
        captured.update(kwargs)
        return _Session()

    monkeypatch.setattr(aws_pipeline_runner.boto3, "Session", _session)
    aws_pipeline_runner.AwsPipelineRunner(
        aws_pipeline_runner.AwsPipelineRunnerConfig(
            "arn:aws:states:abc",
            "eu-west-1",
            aws_profile="profile-x",
        )
    )
    assert captured["profile_name"] == "profile-x"


def test_runner_run_case_success(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_boto3_session(
        monkeypatch,
        descriptions=[
            {"status": "RUNNING"},
            {"status": "SUCCEEDED", "output": json.dumps({"artifact_s3_uri": "s3://bucket-a/artifact.json"})},
        ],
        s3_payload=_valid_artifact_payload(flow="native"),
    )
    monkeypatch.setattr(aws_pipeline_runner.time, "sleep", lambda *_args: None)
    times = iter([0.0, 0.2, 0.4])
    monkeypatch.setattr(aws_pipeline_runner.time, "time", lambda: next(times))

    runner = aws_pipeline_runner.AwsPipelineRunner(
        aws_pipeline_runner.AwsPipelineRunnerConfig(
            "arn:aws:states:abc",
            "eu-west-1",
            execution_timeout_seconds=5,
        )
    )
    result = runner.run_case(
        aws_pipeline_runner.PipelineRunRequest(
            flow="native",
            request_text="check JRASERVER-1",
            case_id="case",
            expected_tool="jira_get_issue_by_key",
            dry_run=True,
        )
    )
    assert result.execution_arn == "arn:exec:1"
    assert result.artifact_s3_uri == "s3://bucket-a/artifact.json"
    assert result.payload["run_metrics"]["business_success"] is True


def test_runner_run_case_failure_modes(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_boto3_session(monkeypatch, descriptions=[{"status": "FAILED", "error": "E", "cause": "C"}])
    runner = aws_pipeline_runner.AwsPipelineRunner(
        aws_pipeline_runner.AwsPipelineRunnerConfig("arn:aws:states:abc", "eu-west-1")
    )
    with pytest.raises(RuntimeError):
        runner.run_case(
            aws_pipeline_runner.PipelineRunRequest(
                flow="native",
                request_text="x",
                case_id="c",
                expected_tool="tool",
                dry_run=False,
            )
        )


def test_runner_run_case_fails_on_artifact_schema_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_boto3_session(
        monkeypatch,
        descriptions=[
            {"status": "SUCCEEDED", "output": json.dumps({"artifact_s3_uri": "s3://bucket-a/artifact.json"})},
        ],
        s3_payload={
            "flow": "native",
            "intake": {"intent": "status_update", "issue_key": "JRASERVER-1"},
            "tool_result": {"key": "JRASERVER-1"},
            "run_metrics": {"tool_failure": False, "business_success": True},
        },
    )
    runner = aws_pipeline_runner.AwsPipelineRunner(
        aws_pipeline_runner.AwsPipelineRunnerConfig("arn:aws:states:abc", "eu-west-1")
    )
    with pytest.raises(RuntimeError, match="artifact_schema_invalid:native_selection_missing_or_not_object"):
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
        aws_pipeline_runner.AwsPipelineRunner._validate_artifact_payload(payload=[], flow="native")  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="artifact_schema_invalid:native_selection.selected_tool_not_string"):
        aws_pipeline_runner.AwsPipelineRunner._validate_artifact_payload(
            payload={
                "flow": "native",
                "intake": {"intent": "status_update"},
                "tool_result": {"key": "JRASERVER-1"},
                "run_metrics": {"tool_failure": False},
                "native_selection": {"selected_tool": 123},
            },
            flow="native",
        )

    with pytest.raises(RuntimeError, match="artifact_schema_invalid:flow_mismatch:expected=native:actual=mcp"):
        aws_pipeline_runner.AwsPipelineRunner._validate_artifact_payload(
            payload={
                "flow": "mcp",
                "intake": {"intent": "status_update"},
                "tool_result": {"key": "JRASERVER-1"},
                "run_metrics": {"tool_failure": False},
                "native_selection": {"selected_tool": "jira_api_get_issue_by_key"},
            },
            flow="native",
        )


def test_runner_run_case_missing_output_and_artifact(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_boto3_session(monkeypatch, descriptions=[{"status": "SUCCEEDED", "output": ""}])
    runner = aws_pipeline_runner.AwsPipelineRunner(
        aws_pipeline_runner.AwsPipelineRunnerConfig("arn:aws:states:abc", "eu-west-1")
    )
    with pytest.raises(RuntimeError):
        runner.run_case(
            aws_pipeline_runner.PipelineRunRequest(
                flow="native",
                request_text="x",
                case_id="c",
                expected_tool="tool",
                dry_run=False,
            )
        )

    _install_boto3_session(monkeypatch, descriptions=[{"status": "SUCCEEDED", "output": "{}"}])
    runner = aws_pipeline_runner.AwsPipelineRunner(
        aws_pipeline_runner.AwsPipelineRunnerConfig("arn:aws:states:abc", "eu-west-1")
    )
    with pytest.raises(RuntimeError):
        runner.run_case(
            aws_pipeline_runner.PipelineRunRequest(
                flow="native",
                request_text="x",
                case_id="c",
                expected_tool="tool",
                dry_run=False,
            )
        )


def test_runner_run_case_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_boto3_session(monkeypatch, descriptions=[{"status": "RUNNING"}] * 3)
    monkeypatch.setattr(aws_pipeline_runner.time, "sleep", lambda *_args: None)
    times = iter([0.0, 10.0, 20.0, 30.0])
    monkeypatch.setattr(aws_pipeline_runner.time, "time", lambda: next(times))
    runner = aws_pipeline_runner.AwsPipelineRunner(
        aws_pipeline_runner.AwsPipelineRunnerConfig(
            "arn:aws:states:abc",
            "eu-west-1",
            execution_timeout_seconds=5,
        )
    )
    with pytest.raises(TimeoutError):
        runner.run_case(
            aws_pipeline_runner.PipelineRunRequest(
                flow="native",
                request_text="x",
                case_id="c",
                expected_tool="tool",
                dry_run=False,
            )
        )


def test_build_execution_name_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeDt:
        @staticmethod
        def now(_tz: Any) -> datetime:
            return datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)

    monkeypatch.setattr(aws_pipeline_runner, "datetime", _FakeDt)
    monkeypatch.setattr(aws_pipeline_runner.uuid, "uuid4", lambda: SimpleNamespace(hex="abcdef1234567890"))
    name = aws_pipeline_runner.AwsPipelineRunner._build_execution_name(flow="flow*&", case_id="case with spaces and symbols/and-a-very-long-tail")
    assert len(name) <= 80
    assert name.startswith("eval-flow-")


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
        "mean_latency_ms": 10,
        "mean_latency_success_ms": 9,
        "mean_latency_failure_ms": 1,
        "mean_response_similarity": 0.9,
        "tool_failure_ci95_low": 0,
        "tool_failure_ci95_high": 0.1,
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
