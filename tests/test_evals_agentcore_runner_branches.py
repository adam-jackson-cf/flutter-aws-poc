import io
from typing import Any, Dict

import pytest

from evals import aws_pipeline_runner


class _FakeRuntimeClient:
    def invoke_agent_runtime(self, **_kwargs: Any) -> Dict[str, Any]:
        return {}


class _FakeS3Client:
    def get_object(self, **_kwargs: Any) -> Dict[str, Any]:
        raise AssertionError("unexpected S3 artifact read")


class _FakeStsClient:
    def get_caller_identity(self) -> Dict[str, str]:
        return {
            "Account": "123456789012",
            "Arn": "arn:aws:iam::123456789012:role/test",
            "UserId": "AIDATEST",
        }


class _FakeSession:
    def __init__(self) -> None:
        self._clients = {
            "bedrock-agentcore": _FakeRuntimeClient(),
            "s3": _FakeS3Client(),
            "sts": _FakeStsClient(),
        }

    def client(self, service_name: str) -> Any:
        return self._clients[service_name]


def _request(**overrides: Any) -> aws_pipeline_runner.PipelineRunRequest:
    payload: Dict[str, Any] = {
        "flow": "native",
        "request_text": "status update",
        "case_id": "case-1",
        "expected_tool": "jira_get_issue_by_key",
        "dry_run": False,
    }
    payload.update(overrides)
    return aws_pipeline_runner.PipelineRunRequest(**payload)


def _install_runtime_session(
    monkeypatch: pytest.MonkeyPatch,
    *,
    captured_kwargs: Dict[str, Any] | None = None,
) -> None:
    fake_session = _FakeSession()

    def _session(**kwargs: Any) -> _FakeSession:
        if captured_kwargs is not None:
            captured_kwargs.update(kwargs)
        return fake_session

    monkeypatch.setattr(aws_pipeline_runner.boto3, "Session", _session)


def test_optional_execution_fields_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    request = _request()
    sentinel = {"forwarded": "yes"}

    def _fake_optional_execution_fields(incoming: aws_pipeline_runner.PipelineRunRequest) -> Dict[str, Any]:
        assert incoming is request
        return sentinel

    monkeypatch.setattr(aws_pipeline_runner, "_optional_execution_fields", _fake_optional_execution_fields)
    assert aws_pipeline_runner._optional_execution_fields(request) is sentinel


def test_agentcore_runner_init_with_profile_and_preflight_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_kwargs: Dict[str, Any] = {}
    _install_runtime_session(monkeypatch, captured_kwargs=captured_kwargs)

    runner = aws_pipeline_runner.AgentCoreRuntimeRunner(
        aws_pipeline_runner.AgentCoreRuntimeRunnerConfig(
            agent_runtime_arn="arn:aws:bedrock:eu-west-1:123456789012:runtime/test",
            aws_region="eu-west-1",
            aws_profile="profile-x",
        )
    )

    assert captured_kwargs == {"region_name": "eu-west-1", "profile_name": "profile-x"}
    assert runner.preflight_identity() == {
        "account": "123456789012",
        "arn": "arn:aws:iam::123456789012:role/test",
        "user_id": "AIDATEST",
    }


def test_execution_reference_falls_back_when_all_runtime_ids_missing() -> None:
    request = _request(flow="mcp", case_id="fallback-case")
    response = {"traceId": "   ", "runtimeSessionId": "", "mcpSessionId": "\n"}

    assert (
        aws_pipeline_runner.AgentCoreRuntimeRunner._execution_reference(response=response, request=request)
        == "agent-runtime://mcp/fallback-case"
    )


def test_read_payload_stream_handles_supported_and_invalid_types() -> None:
    assert aws_pipeline_runner.AgentCoreRuntimeRunner._read_payload_stream(bytearray(b'{"ok":true}')) == b'{"ok":true}'
    assert aws_pipeline_runner.AgentCoreRuntimeRunner._read_payload_stream('{"ok":true}') == b'{"ok":true}'

    with pytest.raises(RuntimeError, match="agent_runtime_response_missing_payload"):
        aws_pipeline_runner.AgentCoreRuntimeRunner._read_payload_stream(None)

    with pytest.raises(RuntimeError, match="agent_runtime_response_invalid_payload_type"):
        aws_pipeline_runner.AgentCoreRuntimeRunner._read_payload_stream(1234)


def test_decode_runtime_payload_rejects_empty_invalid_json_and_non_object() -> None:
    with pytest.raises(RuntimeError, match="agent_runtime_response_empty"):
        aws_pipeline_runner.AgentCoreRuntimeRunner._decode_runtime_payload(io.BytesIO(b""))

    with pytest.raises(RuntimeError, match="agent_runtime_response_invalid_json"):
        aws_pipeline_runner.AgentCoreRuntimeRunner._decode_runtime_payload(io.BytesIO(b"not-json"))

    with pytest.raises(RuntimeError, match="agent_runtime_response_not_object"):
        aws_pipeline_runner.AgentCoreRuntimeRunner._decode_runtime_payload(io.BytesIO(b'["not","an","object"]'))


def test_artifact_payload_for_result_returns_runtime_payload_when_s3_uri_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_runtime_session(monkeypatch)
    runner = aws_pipeline_runner.AgentCoreRuntimeRunner(
        aws_pipeline_runner.AgentCoreRuntimeRunnerConfig(
            agent_runtime_arn="arn:aws:bedrock:eu-west-1:123456789012:runtime/test",
            aws_region="eu-west-1",
        )
    )

    runtime_payload = {"tool_result": {"key": "JRASERVER-1"}}
    assert runner._artifact_payload_for_result(runtime_payload, artifact_s3_uri="") is runtime_payload


def test_require_dict_field_raises_when_payload_field_is_not_object() -> None:
    with pytest.raises(RuntimeError, match="artifact_schema_invalid:intake_missing_or_not_object"):
        aws_pipeline_runner._require_dict_field({"intake": "bad"}, "intake")
