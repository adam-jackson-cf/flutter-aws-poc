import importlib
import json
import sys
from argparse import Namespace
from pathlib import Path
from typing import Any, Dict
from urllib.error import HTTPError, URLError

import pytest

from evals import aws_pipeline_runner, metrics as eval_metrics, run_eval


def _import_lambda_module(name: str) -> Any:
    lambda_path = Path(__file__).resolve().parents[1] / "aws" / "lambda"
    if str(lambda_path) not in sys.path:
        sys.path.insert(0, str(lambda_path))
    return importlib.import_module(name)


def test_write_actions_runtime_config_and_bedrock_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    write_actions = _import_lambda_module("write_actions")
    runtime_config = _import_lambda_module("runtime_config")
    bedrock_client = _import_lambda_module("bedrock_client")

    assert bedrock_client._safe_int(True) == 1
    assert bedrock_client._safe_int(1.7) == 1
    assert bedrock_client._safe_int("bad") == 0
    assert bedrock_client._safe_int(None) == 0
    assert bedrock_client._bedrock_usage({"usage": "bad"}) == {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    monkeypatch.setenv("OPENAI_MAX_OUTPUT_TOKENS", "oops")
    with pytest.raises(ValueError, match="openai_max_output_tokens_invalid"):
        runtime_config._selected_openai_max_output_tokens({})
    monkeypatch.setenv("OPENAI_MAX_OUTPUT_TOKENS", "12")
    with pytest.raises(ValueError, match="openai_max_output_tokens_too_small"):
        runtime_config._selected_openai_max_output_tokens({})

    with pytest.raises(ValueError, match="note_text_missing"):
        write_actions.write_issue_followup_note({"key": "JRASERVER-1"}, " ", "bucket")
    with pytest.raises(RuntimeError, match="result_bucket_missing_for_write_tool"):
        write_actions.write_issue_followup_note({"key": "JRASERVER-1"}, "x", "")
    with pytest.raises(ValueError, match="issue_key_missing_for_write_tool"):
        write_actions.write_issue_followup_note({"key": ""}, "x", "bucket")

    captured: Dict[str, Any] = {}

    class _S3:
        def put_object(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    class _UUID:
        hex = "abcdef1234567890"

    monkeypatch.setattr(write_actions.boto3, "client", lambda _service: _S3())
    monkeypatch.setattr(write_actions.time, "time", lambda: 1000.123)
    monkeypatch.setattr(write_actions.uuid, "uuid4", lambda: _UUID())
    out = write_actions.write_issue_followup_note({"key": "JRASERVER-1"}, "follow-up", "bucket-a")
    assert captured["Bucket"] == "bucket-a"
    assert out["write_status"] == "committed"
    assert out["write_artifact_uri"].startswith("s3://bucket-a/writes/JRASERVER-1/")


def test_llm_gateway_client_uncovered_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    llm_gateway_client = _import_lambda_module("llm_gateway_client")
    llm_gateway_client._OPENAI_API_KEY_CACHE = ""

    assert llm_gateway_client._infer_provider("plain-model") == "bedrock"
    assert llm_gateway_client._parse_openai_secret_value("") == ""
    assert llm_gateway_client._parse_openai_secret_value("not-json") == "not-json"
    assert llm_gateway_client._parse_openai_secret_value('"k-inline"') == "k-inline"
    assert llm_gateway_client._parse_openai_secret_value('{"unknown":"x"}') == ""
    assert llm_gateway_client._secret_region_from_arn("arn:aws", "eu-west-1") == "eu-west-1"

    llm_gateway_client._OPENAI_API_KEY_CACHE = "cached"
    assert llm_gateway_client._resolve_openai_api_key("eu-west-1") == "cached"
    llm_gateway_client._OPENAI_API_KEY_CACHE = ""

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY_SECRET_ARN", "arn:aws:secretsmanager:eu-west-1:123:secret:x")

    class _Secrets:
        def get_secret_value(self, SecretId: str) -> Dict[str, Any]:  # noqa: N803
            assert SecretId.endswith(":secret:x")
            return {"SecretString": '{"bad":"value"}'}

    monkeypatch.setattr(llm_gateway_client.boto3, "client", lambda *_args, **_kwargs: _Secrets())
    with pytest.raises(RuntimeError, match="openai_api_key_missing:secret_value_not_parseable"):
        llm_gateway_client._resolve_openai_api_key("eu-west-1")

    assert llm_gateway_client._extract_openai_response_text(
        {"output": [{"content": [{"text": "first"}, {"text": "second"}]}]}
    ) == "first\nsecond"
    with pytest.raises(ValueError, match="openai_response_missing_text"):
        llm_gateway_client._extract_openai_response_text({"output": []})
    with pytest.raises(ValueError, match="openai_response_missing_output"):
        llm_gateway_client._openai_output_text_parts({"output": "bad"})
    assert llm_gateway_client._openai_output_item_texts({"content": "bad"}) == []
    assert llm_gateway_client._openai_output_item_texts({"content": ["x"]}) == []
    assert llm_gateway_client._openai_output_item_texts("bad") == []

    with pytest.raises(ValueError, match="openai_http_timeout_seconds_invalid"):
        llm_gateway_client._parse_openai_http_timeout_seconds("abc")
    with pytest.raises(ValueError, match="openai_http_timeout_seconds_invalid"):
        llm_gateway_client._parse_openai_http_timeout_seconds("0")
    with pytest.raises(ValueError, match="openai_http_max_attempts_invalid"):
        llm_gateway_client._parse_openai_http_max_attempts("abc")
    with pytest.raises(ValueError, match="openai_http_max_attempts_invalid"):
        llm_gateway_client._parse_openai_http_max_attempts("0")

    assert llm_gateway_client._is_openai_timeout_exception(URLError("timed out")) is True
    assert llm_gateway_client._is_openai_timeout_exception(URLError(TimeoutError("timeout"))) is True
    assert llm_gateway_client._is_retryable_openai_http_status(408) is True
    assert llm_gateway_client._openai_incomplete_reason({"status": "incomplete", "incomplete_details": "bad"}) == "unknown"
    assert llm_gateway_client._openai_incomplete_reason(
        {"status": "incomplete", "incomplete_details": {"reason": 7}}
    ) == "unknown"
    usage = llm_gateway_client._usage_from_openai_payload(
        {"usage": {"input_tokens": True, "output_tokens": 2.4, "total_tokens": "x"}}
    )
    assert usage == {"input_tokens": 1, "output_tokens": 2, "total_tokens": 0}
    assert llm_gateway_client._safe_int(object()) == 0
    assert llm_gateway_client._usage_from_openai_payload({"usage": "bad"})["input_tokens"] == 0

    opts = llm_gateway_client._resolved_openai_call_options(
        {"reasoning_effort": "", "verbosity": "", "max_output_tokens": "2048"}
    )
    assert opts["max_output_tokens"] == 2048
    with pytest.raises(ValueError, match="openai_max_output_tokens_invalid"):
        llm_gateway_client._parse_max_output_tokens("nope")
    with pytest.raises(ValueError, match="openai_max_output_tokens_too_small"):
        llm_gateway_client._parse_max_output_tokens("32")
    assert llm_gateway_client._openai_scoped_provider_options({"openai": "bad"}) == {}
    assert llm_gateway_client._openai_json_schema_format({"response_json_schema": {"name": "", "schema": {}}}) is None
    assert llm_gateway_client._openai_json_schema_format(
        {"response_json_schema": {"name": "x", "schema": {"type": "object"}, "strict": True}}
    ) == {"type": "json_schema", "name": "x", "schema": {"type": "object"}, "strict": True}

    with pytest.raises(RuntimeError, match="openai_gateway_error:http_500"):
        llm_gateway_client._raise_openai_exception(HTTPError("u", 500, "x", hdrs=None, fp=None))
    with pytest.raises(RuntimeError, match="openai_gateway_error:timeout"):
        llm_gateway_client._raise_openai_exception(TimeoutError("timeout"))
    with pytest.raises(RuntimeError, match="openai_gateway_error:network"):
        llm_gateway_client._raise_openai_exception(URLError("offline"))
    assert (
        llm_gateway_client._should_retry_openai_exception(
            exc=HTTPError("u", 500, "x", hdrs=None, fp=None),
            attempt=0,
            max_attempts=2,
        )
        is True
    )
    assert llm_gateway_client._should_retry_openai_exception(exc=Exception("x"), attempt=0, max_attempts=2) is False
    assert llm_gateway_client._should_retry_openai_exception(exc=URLError("offline"), attempt=0, max_attempts=2) is False

    class _Response:
        def __init__(self, payload: Dict[str, Any]) -> None:
            self._payload = payload

        def __enter__(self) -> "_Response":
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(self._payload).encode("utf-8")

    monkeypatch.setenv("OPENAI_API_KEY", "k-test")
    monkeypatch.setenv("OPENAI_HTTP_TIMEOUT_SECONDS", "5")
    monkeypatch.setenv("OPENAI_HTTP_MAX_ATTEMPTS", "1")
    monkeypatch.setattr(llm_gateway_client, "validate_endpoint_url", lambda **_kwargs: None)
    monkeypatch.setattr(
        llm_gateway_client,
        "urlopen",
        lambda *_args, **_kwargs: _Response({"status": "incomplete", "incomplete_details": {"reason": "content_filter"}}),
    )
    with pytest.raises(RuntimeError, match="openai_response_incomplete:content_filter"):
        llm_gateway_client.call_openai_with_usage("gpt-5.2-codex", "prompt", "eu-west-1")

    captured: Dict[str, Any] = {}

    def _capture_urlopen(req: Any, **_kwargs: Any) -> _Response:
        captured["payload"] = json.loads(req.data.decode("utf-8"))
        return _Response({"output_text": "ok"})

    monkeypatch.setattr(llm_gateway_client, "urlopen", _capture_urlopen)
    text, _usage = llm_gateway_client.call_openai_with_usage(
        "gpt-5.2-codex",
        "prompt",
        "eu-west-1",
        provider_options={"response_json_schema": {"name": "x", "schema": {"type": "object"}, "strict": True}},
    )
    assert text == "ok"
    assert captured["payload"]["text"]["format"]["type"] == "json_schema"

    monkeypatch.setenv("OPENAI_HTTP_MAX_ATTEMPTS", "1")
    monkeypatch.setattr(llm_gateway_client, "urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(URLError("offline")))
    with pytest.raises(RuntimeError, match="openai_gateway_error:network"):
        llm_gateway_client.call_openai_with_usage("gpt-5.2-codex", "prompt", "eu-west-1")

    monkeypatch.setenv("OPENAI_HTTP_MAX_ATTEMPTS", "2")
    monkeypatch.setattr(
        llm_gateway_client,
        "urlopen",
        lambda *_args, **_kwargs: _Response({"status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"}}),
    )
    monkeypatch.setattr(llm_gateway_client.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(llm_gateway_client, "_should_retry_for_max_output_tokens", lambda *_args, **_kwargs: True)
    with pytest.raises(RuntimeError, match="openai_gateway_error:timeout"):
        llm_gateway_client.call_openai_with_usage("gpt-5.2-codex", "prompt", "eu-west-1")


def test_tool_selection_request_grounding_fetch_and_evaluate_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    tool_selection = _import_lambda_module("tool_selection")
    request_grounding = _import_lambda_module("request_grounding")
    fetch_native_stage = _import_lambda_module("fetch_native_stage")
    fetch_mcp_stage = _import_lambda_module("fetch_mcp_stage")
    evaluate_stage = _import_lambda_module("evaluate_stage")

    schema = tool_selection._mcp_call_response_schema(["jira_get_issue_by_key"])
    assert schema["properties"]["tool"]["enum"] == ["jira_get_issue_by_key"]
    summary = tool_selection._tool_input_schema_summary(
        {"inputSchema": {"required": ["issue_key"], "properties": {"issue_key": {"type": "string"}, "x": "bad"}}}
    )
    assert "required=['issue_key']" in summary
    assert "issue_key:string" in summary
    assert "x" not in summary
    assert "jira_get_issue_by_key" in tool_selection._mcp_tool_prompt_lines(
        [{"name": "jira_get_issue_by_key", "description": "desc", "inputSchema": {"required": ["issue_key"]}}]
    )
    assert tool_selection._default_mcp_arguments(
        {"inputSchema": {"required": ["issue_key", "query"]}},
        "JRASERVER-1",
        "help",
    ) == {"issue_key": "JRASERVER-1", "query": "help"}
    assert tool_selection._default_mcp_arguments({"inputSchema": {"required": "bad"}}, "JRASERVER-1", "help") == {}

    monkeypatch.setattr(
        tool_selection,
        "invoke_llm_gateway_with_usage",
        lambda **_kwargs: ('{"tool":"jira_get_issue_by_key","arguments":{"issue_key":"JRASERVER-1"},"reason":"ok"}', {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}),
    )
    selection = tool_selection.select_mcp_tool_call(
        selection=tool_selection.ToolSelectionRequest(
            request_text="r",
            issue_key="JRASERVER-1",
            tools=[{"name": "jira_get_issue_by_key", "description": "d", "inputSchema": {"required": ["issue_key"]}}],
            default_tool="jira_get_issue_by_key",
        ),
        config=tool_selection.ToolSelectorConfig(model_id="m", region="eu-west-1", dry_run=False),
    )
    assert selection["selected_tool"] == "jira_get_issue_by_key"
    assert tool_selection.validate_gateway_tool_arguments({"inputSchema": {}}, "bad") == "mcp_tool_args_invalid:arguments_not_object"
    assert (
        tool_selection.validate_gateway_tool_arguments({"inputSchema": "bad"}, {})
        == "mcp_tool_args_invalid:input_schema_not_object"
    )
    assert (
        tool_selection.validate_gateway_tool_arguments(
            {"inputSchema": {"properties": {"issue_key": {"type": "string"}}}},
            {"extra": "x"},
        )
        == "mcp_tool_args_unknown_arguments:extra"
    )
    assert (
        tool_selection.validate_gateway_tool_arguments(
            {"inputSchema": {"properties": {"labels": {"type": "array_string"}}}},
            {"labels": [1]},
        )
        == "mcp_tool_args_invalid_type:labels:expected_array_string"
    )
    properties, required, schema_error = tool_selection._input_schema_parts({"inputSchema": {"properties": [], "required": "x"}})
    assert properties == {}
    assert required == []
    assert schema_error == ""
    assert tool_selection._argument_type_error(arguments={"x": "y"}, properties={"x": "bad"}) == ""
    assert tool_selection._tool_input_schema_summary({"inputSchema": {"required": "x", "properties": []}}) == "required=[]; properties=[]"

    assert request_grounding._safe_int(True) == 1
    assert request_grounding._safe_int("bad") == 0
    assert request_grounding._safe_int(None) == 0
    with pytest.raises(ValueError, match="grounding_max_attempts_invalid"):
        request_grounding._parse_max_attempts("bad")
    with pytest.raises(ValueError, match="grounding_max_attempts_invalid"):
        request_grounding._parse_max_attempts("0")
    assert request_grounding._validation_error("bad_intent", "JRASERVER-1", ["JRASERVER-1"]).startswith(
        "grounding_invalid_intent"
    )
    with pytest.raises(ValueError, match="grounding_candidate_issue_keys_missing"):
        request_grounding._normalized_candidate_issue_keys({"candidate_issue_keys": []})
    with pytest.raises(ValueError, match="grounding_candidate_issue_keys_missing"):
        request_grounding._normalized_candidate_issue_keys({"candidate_issue_keys": [" ", ""]})

    monkeypatch.setenv("GROUNDING_MAX_ATTEMPTS", "1")
    monkeypatch.setattr(
        request_grounding,
        "invoke_llm_gateway_with_usage",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("bad")),
    )
    grounding_result = request_grounding.resolve_request_grounding(
        intake_seed={"request_text": "x", "candidate_issue_keys": ["JRASERVER-1"], "intent_hint": "status_update"},
        dry_run=False,
        llm_config=request_grounding.GroundingLlmConfig(
            model_id="m",
            region="eu-west-1",
            model_provider="auto",
            provider_options=None,
        ),
    )
    assert grounding_result["attempts"] == 1
    assert grounding_result["failure_reason"].startswith("grounding_response_invalid:")

    assert fetch_native_stage._priority_risk_band("Medium") == "medium"
    assert fetch_native_stage._priority_risk_band("Low") == "low"
    assert fetch_native_stage._safe_int(True) == 1
    assert fetch_native_stage._safe_int("bad") == 0
    assert fetch_native_stage._safe_int(None) == 0
    assert fetch_native_stage._selection_llm_usage({"llm_usage": "bad"}) == {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }
    assert fetch_native_stage._grounding_failure_reason({"grounding": "bad"}) == ""

    with pytest.raises(ValueError, match="mcp_call_construction_max_attempts_invalid"):
        fetch_mcp_stage._parse_max_attempts("bad")
    with pytest.raises(ValueError, match="mcp_call_construction_max_attempts_invalid"):
        fetch_mcp_stage._parse_max_attempts("0")
    assert fetch_mcp_stage._safe_int(True) == 1
    assert fetch_mcp_stage._safe_int("bad") == 0
    assert fetch_mcp_stage._safe_int(None) == 0
    assert fetch_mcp_stage._selection_llm_usage({"llm_usage": "bad"}) == {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }
    assert "Previous attempt invalid" in fetch_mcp_stage._invalid_retry_feedback("mcp_tool_args_missing_required:issue_key")
    assert fetch_mcp_stage._grounding_failure_reason({"grounding": "bad"}) == ""

    catalog = fetch_mcp_stage.McpCatalog(
        all_tools=[],
        scoped_tools=[],
        tool_map={"jira_get_issue_by_key": {"inputSchema": {"required": ["issue_key"], "properties": {"issue_key": {"type": "string"}}}}},
        scope=fetch_mcp_stage.StageToolScope(intent="general_triage", scoped_tool_count=1, catalog_tool_count=1),
    )
    monkeypatch.setattr(
        fetch_mcp_stage,
        "_select_tool",
        lambda **_kwargs: {"selected_tool": "jira_get_issue_by_key", "arguments": "bad", "llm_usage": {}},
    )
    _, _, selected_arguments, _ = fetch_mcp_stage._selection_attempt(
        intake={"request_text": "r", "issue_key": "JRASERVER-1"},
        catalog=catalog,
        runtime_config=fetch_mcp_stage.SelectorRuntimeConfig(
            model_id="m",
            region="eu-west-1",
            dry_run=False,
            model_provider="auto",
            provider_options={},
        ),
        retry_feedback="",
    )
    assert selected_arguments == {}

    monkeypatch.setattr(fetch_mcp_stage, "_max_call_construction_attempts", lambda: 1)
    monkeypatch.setattr(
        fetch_mcp_stage,
        "_selection_attempt",
        lambda **_kwargs: (
            {"selected_tool": "jira_get_issue_by_key", "arguments": {}},
            "jira_get_issue_by_key",
            {},
            {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
        ),
    )
    resolution = fetch_mcp_stage._resolve_tool_call_selection(
        intake={"request_text": "r", "issue_key": "JRASERVER-1"},
        catalog=catalog,
        runtime_config=fetch_mcp_stage.SelectorRuntimeConfig(
            model_id="m",
            region="eu-west-1",
            dry_run=False,
            model_provider="auto",
            provider_options={},
        ),
    )
    assert resolution.failure_reason.startswith("mcp_tool_args_missing_required")

    failed_event: Dict[str, Any] = {"metrics": {"stages": []}}
    unknown_tool = fetch_mcp_stage._unknown_selected_tool_result(
        run_context=fetch_mcp_stage._run_context(
            event=failed_event,
            started=0.0,
            issue_key="JRASERVER-1",
            selected_tool="unknown_tool",
            set_scope=False,
        ),
        selection={"selected_tool": "unknown_tool"},
        scope=fetch_mcp_stage._empty_scope("general_triage"),
    )
    assert unknown_tool["tool_result"]["failure_reason"].startswith("selected_unknown_tool")

    assert evaluate_stage._selected_tool_for_metrics({"flow": "mcp", "mcp_selection": {"selected_tool": "mcp_tool"}}) == "mcp_tool"
    assert evaluate_stage._selected_tool_for_metrics({"flow": "native", "native_selection": {"selected_tool": "native_tool"}}) == "native_tool"
    assert evaluate_stage._int_metric(True) == 1
    assert evaluate_stage._int_metric(2.7) == 2
    assert evaluate_stage._int_metric("bad") == 0
    assert evaluate_stage._mcp_call_construction_metrics({"flow": "mcp", "mcp_call_construction": "bad"}) == {
        "attempts": 0,
        "retries": 0,
        "failures": 0,
    }
    taxonomy = evaluate_stage._mcp_call_construction_error_taxonomy(
        {
            "flow": "mcp",
            "mcp_call_construction": {
                "attempt_trace": [
                    {"arg_errors": "mcp_tool_args_missing_required:issue_key"},
                    {"arg_errors": "mcp_tool_args_missing_required:issue_key"},
                    {"arg_errors": ""},
                    "bad",
                ]
            },
        }
    )
    assert taxonomy == {"mcp_tool_args_missing_required": 2}
    assert evaluate_stage._mcp_call_construction_error_taxonomy({"flow": "mcp", "mcp_call_construction": {"attempt_trace": "bad"}}) == {}
    assert evaluate_stage._mcp_call_construction_error_taxonomy({"flow": "mcp", "mcp_call_construction": "bad"}) == {}
    assert evaluate_stage._grounding_metrics({"grounding": "bad"})["failure"] is False
    assert evaluate_stage._aggregate_llm_usage({"llm_usage": "bad"}) == {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }
    assert evaluate_stage._aggregate_llm_usage({"llm_usage": {"a": "bad", "b": {"input_tokens": 1, "output_tokens": 2, "total_tokens": 3}}}) == {
        "input_tokens": 1,
        "output_tokens": 2,
        "total_tokens": 3,
    }


def test_jira_tool_target_argument_and_write_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    jira_tool_target = _import_lambda_module("jira_tool_target")

    assert jira_tool_target._extract_arguments({"params": {"arguments": {"issue_key": "JRASERVER-1"}}}) == {
        "issue_key": "JRASERVER-1"
    }
    assert jira_tool_target._extract_arguments({"arguments": '{"issue_key":"JRASERVER-2"}'}) == {"issue_key": "JRASERVER-2"}
    assert jira_tool_target._extract_arguments({"arguments": 3}) == {}

    captured: Dict[str, Any] = {}
    monkeypatch.setenv("RESULT_BUCKET", "bucket-x")
    def _write_issue_followup_note(**kwargs: Any) -> Dict[str, Any]:
        captured["kwargs"] = kwargs
        return {"key": kwargs["issue"]["key"]}

    monkeypatch.setattr(jira_tool_target, "write_issue_followup_note", _write_issue_followup_note)
    out = jira_tool_target._result_write_issue_followup_note({"key": "JRASERVER-7"}, {"note_text": "  hello  "})
    assert captured["kwargs"]["note_text"] == "hello"
    assert captured["kwargs"]["result_bucket"] == "bucket-x"
    assert out["key"] == "JRASERVER-7"


def test_runner_metrics_and_run_eval_helper_branches(tmp_path: Path) -> None:
    execution_input = aws_pipeline_runner.AwsPipelineRunner._execution_input(
        aws_pipeline_runner.PipelineRunRequest(
            flow="native",
            request_text="x",
            case_id="case",
            expected_tool="jira_get_issue_by_key",
            dry_run=False,
            model_id="gpt-5.2-codex",
            runtime_model_id="eu.amazon.nova-lite-v1:0",
            bedrock_region="eu-west-1",
            model_provider="openai",
            openai_reasoning_effort="high",
            openai_text_verbosity="medium",
            openai_max_output_tokens=4096,
        )
    )
    assert execution_input["bedrock_region"] == "eu-west-1"
    assert execution_input["openai_max_output_tokens"] == 4096

    summary = eval_metrics.aggregate_case_metrics(
        [
            {
                "metrics": {
                    "intent_match": True,
                    "issue_key_match": True,
                    "tool_match": True,
                    "tool_failure": False,
                    "issue_payload_complete": True,
                    "issue_key_resolution_match": True,
                    "business_success": True,
                    "grounding_failure": True,
                    "grounding_attempts": 2,
                    "grounding_retry_count": 1,
                    "call_construction_failure": True,
                    "call_construction_recovered": True,
                    "call_construction_attempts": 2,
                    "call_construction_retries": 1,
                    "write_case": True,
                    "write_tool_selected": True,
                    "write_tool_match": True,
                    "latency_ms": 100.0,
                    "response_similarity": 0.9,
                    "llm_input_tokens": 100,
                    "llm_output_tokens": 20,
                    "llm_total_tokens": 120,
                }
            }
        ]
    )
    assert summary["issue_key_resolution_match_rate"] == 1.0
    assert summary["grounding_failure_rate"] == 1.0
    assert summary["call_construction_recovery_rate"] == 1.0
    assert summary["write_tool_match_rate"] == 1.0

    assert run_eval._to_int(True) == 1
    assert run_eval._to_int("bad") == 0
    assert run_eval._to_float(True) == 1.0
    assert run_eval._to_float("bad") == 0.0
    with pytest.raises(ValueError, match="value_missing"):
        run_eval._parse_positive_float("", field_name="value")
    with pytest.raises(ValueError, match="value_invalid"):
        run_eval._parse_positive_float("abc", field_name="value")
    with pytest.raises(ValueError, match="value_must_be_positive"):
        run_eval._parse_positive_float("-1", field_name="value")
    assert run_eval._safe_ratio(5.0, 0.0) == 0.0

    with pytest.raises(ValueError, match="model_pricing_catalog_missing"):
        run_eval._resolve_pricing_catalog_path("")
    with pytest.raises(ValueError, match="model_pricing_catalog_missing:"):
        run_eval._resolve_pricing_catalog_path("missing-file.json")

    bad_json_path = tmp_path / "bad-json.json"
    bad_json_path.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="model_pricing_catalog_invalid_json"):
        run_eval._load_pricing_catalog(bad_json_path)

    bad_object_path = tmp_path / "bad-object.json"
    bad_object_path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="model_pricing_catalog_invalid_object"):
        run_eval._load_pricing_catalog(bad_object_path)

    with pytest.raises(ValueError, match="model_pricing_invalid_for_model:model-x"):
        run_eval._valid_pricing_pair(
            "model-x",
            {"input_per_1m_tokens_usd": 0, "output_per_1m_tokens_usd": 1},
        )

    invalid_catalog_path = tmp_path / "catalog-invalid-models.json"
    invalid_catalog_path.write_text(json.dumps({"version": "v1", "models": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="model_pricing_catalog_invalid_models"):
        run_eval._pricing_snapshot_for_model(
            Namespace(
                model_id="model-x",
                openai_reasoning_effort="",
                model_pricing_catalog=str(invalid_catalog_path),
                price_input_per_1m_tokens_usd="",
                price_output_per_1m_tokens_usd="",
            )
        )

    bucket = run_eval._adversarial_bucket_template()
    run_eval._accumulate_adversarial_bucket(
        bucket,
        {
            "business_success": True,
            "tool_failure": False,
            "tool_match": True,
            "issue_key_resolution_match": True,
            "grounding_failure": True,
            "call_construction_failure": True,
            "write_case": True,
            "write_tool_match": True,
            "latency_ms": 11.0,
            "llm_input_tokens": 5.0,
            "llm_output_tokens": 2.0,
            "llm_total_tokens": 7.0,
        },
    )
    assert bucket["issue_key_resolution_match_count"] == 1
    assert bucket["grounding_failure_count"] == 1
    assert bucket["write_tool_match_count"] == 1

    assert run_eval._selection_divergence_metrics({"cases": "bad"}, {"cases": []}) == {
        "selection_divergence_rate": 0.0,
        "selection_divergence_count": 0.0,
        "selection_divergence_compared_cases": 0.0,
    }
    assert run_eval._case_key({"iteration": True, "case_id": "a"}) == (1, "a")
    assert run_eval._case_key({"iteration": "bad", "case_id": "a"}) == (0, "a")
    mapped = run_eval._rows_by_case_key([{"iteration": 1, "case_id": "a"}, {}, "bad"])
    assert mapped == {(1, "a"): {"iteration": 1, "case_id": "a"}}

    run_eval._validate_judge_args(
        Namespace(enable_judge=True, judge_region="eu-west-1", judge_model_id="eu.amazon.nova-lite-v1:0")
    )
    with pytest.raises(ValueError, match="judge model id must be a Bedrock model identifier"):
        run_eval._validate_judge_args(
            Namespace(enable_judge=True, judge_region="eu-west-1", judge_model_id="gpt-5.2-codex")
        )

    assert run_eval._is_bedrock_model_identifier("arn:aws:bedrock:eu-west-1:123:model/x") is True
    assert run_eval._is_bedrock_model_identifier("arn:aws-us-gov:bedrock:us-gov-west-1:123:model/x") is True
    assert run_eval._is_bedrock_model_identifier("arn:aws-cn:bedrock:cn-north-1:123:model/x") is True
    assert run_eval._is_bedrock_model_identifier("eu.amazon.nova-lite-v1:0") is True
    assert run_eval._is_bedrock_model_identifier("") is False


def test_lambda_llm_gateway_stage_and_invoke_client_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    stage = _import_lambda_module("llm_gateway_stage")
    invoke_client = _import_lambda_module("llm_gateway_invoke_client")

    assert stage._safe_dict({"a": 1}) == {"a": 1}
    assert stage._safe_dict("bad") == {}
    assert stage._safe_str("  x  ") == "x"
    assert stage._safe_str(1) == ""
    with pytest.raises(ValueError, match="model_id_missing"):
        stage._parse_request({"region": "eu-west-1", "prompt": "x"})
    with pytest.raises(ValueError, match="region_missing"):
        stage._parse_request({"model_id": "m", "prompt": "x"})
    with pytest.raises(ValueError, match="prompt_missing"):
        stage._parse_request({"model_id": "m", "region": "eu-west-1"})
    assert stage._safe_usage("bad") == {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    monkeypatch.setattr(
        stage,
        "call_llm_gateway_with_usage",
        lambda **_kwargs: ("ok", {"input_tokens": "2", "output_tokens": 3.7, "total_tokens": None}),
    )
    success = stage.handler(
        {
            "model_id": "model-a",
            "provider": "openai",
            "region": "eu-west-1",
            "prompt": "hello",
            "provider_options": {"openai": {"verbosity": "low"}},
        },
        None,
    )
    assert success["ok"] is True
    assert success["text"] == "ok"
    assert success["usage"]["input_tokens"] == 2
    assert success["provider_used"] == "openai"

    monkeypatch.setattr(stage, "call_llm_gateway_with_usage", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("boom:bad")))
    failed = stage.handler({"model_id": "model-a", "provider": "auto", "region": "eu-west-1", "prompt": "hello"}, None)
    assert failed["ok"] is False
    assert failed["error_code"] == "boom"
    assert stage.lambda_handler({"model_id": "model-a", "provider": "auto", "region": "eu-west-1", "prompt": "hello"}, None)["ok"] is False

    monkeypatch.delenv("LLM_GATEWAY_FUNCTION_NAME", raising=False)
    with pytest.raises(RuntimeError, match="llm_gateway_unconfigured"):
        invoke_client._function_name()
    monkeypatch.setenv("LLM_GATEWAY_FUNCTION_NAME", "fn")
    assert invoke_client._function_name() == "fn"
    monkeypatch.setenv("LLM_GATEWAY_INVOKE_MAX_ATTEMPTS", "bad")
    with pytest.raises(ValueError, match="llm_gateway_invoke_max_attempts_invalid"):
        invoke_client._max_attempts()
    monkeypatch.setenv("LLM_GATEWAY_INVOKE_MAX_ATTEMPTS", "0")
    with pytest.raises(ValueError, match="llm_gateway_invoke_max_attempts_invalid"):
        invoke_client._max_attempts()
    monkeypatch.setenv("LLM_GATEWAY_INVOKE_MAX_ATTEMPTS", "2")
    assert invoke_client._max_attempts() == 2
    monkeypatch.setenv("LLM_GATEWAY_INVOKE_TIMEOUT_SECONDS", "bad")
    with pytest.raises(ValueError, match="llm_gateway_invoke_timeout_invalid"):
        invoke_client._timeout_seconds()
    monkeypatch.setenv("LLM_GATEWAY_INVOKE_TIMEOUT_SECONDS", "0")
    with pytest.raises(ValueError, match="llm_gateway_invoke_timeout_invalid"):
        invoke_client._timeout_seconds()
    monkeypatch.setenv("LLM_GATEWAY_INVOKE_TIMEOUT_SECONDS", "2")
    assert invoke_client._timeout_seconds() == 2.0

    payload = invoke_client._payload(
        invoke_client.GatewayInvokeRequest(
            model_id="m",
            provider="auto",
            region="eu-west-1",
            prompt="p",
            provider_options=None,
        )
    )
    assert b'"provider_options": {}' in payload

    captured: Dict[str, Any] = {}
    monkeypatch.setattr(
        invoke_client.boto3,
        "client",
        lambda service, **kwargs: captured.update({"service": service, **kwargs}) or "client",
    )
    assert invoke_client._client("eu-west-1") == "client"
    assert captured["service"] == "lambda"
    assert invoke_client._safe_int(True) == 1
    assert invoke_client._safe_int("bad") == 0
    assert invoke_client._safe_int(None) == 0

    with pytest.raises(RuntimeError, match="llm_gateway_error:gateway_error:unknown_error"):
        invoke_client._parse_invoke_payload({"ok": False, "error_code": "", "error_message": ""})
    parsed = invoke_client._parse_invoke_payload(
        {"ok": True, "text": "x", "usage": "bad", "provider_used": "p", "model_used": "m", "latency_ms": 1.5}
    )
    assert parsed.text == "x"
    assert parsed.usage["total_tokens"] == 0
    assert invoke_client._retryable_error(RuntimeError("llm_gateway_invoke_status:503")) is True
    assert invoke_client._retryable_error(RuntimeError("other")) is False
    slept: Dict[str, float] = {}
    monkeypatch.setattr(invoke_client.random, "uniform", lambda *_args: 0.01)
    monkeypatch.setattr(invoke_client.time, "sleep", lambda seconds: slept.setdefault("seconds", seconds))
    invoke_client._sleep_backoff(2)
    assert slept["seconds"] > 0.0

    class _Payload:
        def __init__(self, raw: str) -> None:
            self._raw = raw

        def read(self) -> bytes:
            return self._raw.encode("utf-8")

    class _Client:
        def __init__(self, response: Dict[str, Any]) -> None:
            self._response = response

        def invoke(self, **_kwargs: Any) -> Dict[str, Any]:
            return self._response

    request = invoke_client.GatewayInvokeRequest(
        model_id="m",
        provider="auto",
        region="eu-west-1",
        prompt="p",
    )
    monkeypatch.setenv("LLM_GATEWAY_FUNCTION_NAME", "fn")
    monkeypatch.setattr(invoke_client, "_client", lambda _region: _Client({"StatusCode": 500}))
    with pytest.raises(RuntimeError, match="llm_gateway_invoke_status:500"):
        invoke_client._invoke_once(request)
    monkeypatch.setattr(
        invoke_client,
        "_client",
        lambda _region: _Client({"StatusCode": 200, "FunctionError": "Unhandled", "Payload": _Payload("raw")}),
    )
    with pytest.raises(RuntimeError, match="llm_gateway_function_error:Unhandled:raw"):
        invoke_client._invoke_once(request)
    monkeypatch.setattr(
        invoke_client,
        "_client",
        lambda _region: _Client({"StatusCode": 200, "Payload": _Payload("{bad")}),
    )
    with pytest.raises(RuntimeError, match="llm_gateway_invoke_response_invalid_json"):
        invoke_client._invoke_once(request)
    monkeypatch.setattr(
        invoke_client,
        "_client",
        lambda _region: _Client({"StatusCode": 200, "Payload": _Payload("[]")}),
    )
    with pytest.raises(RuntimeError, match="llm_gateway_invoke_response_invalid_payload"):
        invoke_client._invoke_once(request)
    monkeypatch.setattr(
        invoke_client,
        "_client",
        lambda _region: _Client({"StatusCode": 200, "Payload": _Payload('{"ok": true, "text": "ok", "usage": {"input_tokens": 1}}')}),
    )
    assert invoke_client._invoke_once(request).text == "ok"

    monkeypatch.setattr(invoke_client, "_max_attempts", lambda: 2)
    attempts = {"count": 0}
    monkeypatch.setattr(invoke_client, "_retryable_error", lambda _exc: True)
    monkeypatch.setattr(invoke_client, "_sleep_backoff", lambda _attempt: None)
    def _retry_once(_request: Any) -> Any:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("llm_gateway_invoke_status:503")
        return invoke_client.GatewayInvokeResponse(
            text="ok",
            usage={"input_tokens": 1, "output_tokens": 2, "total_tokens": 3},
            provider_used="auto",
            model_used="m",
            latency_ms=1.0,
        )
    monkeypatch.setattr(invoke_client, "_invoke_once", _retry_once)
    assert invoke_client.invoke_llm_gateway_with_usage(model_id="m", prompt="p", region="eu-west-1")[0] == "ok"
    monkeypatch.setattr(invoke_client, "_invoke_once", lambda _request: (_ for _ in ()).throw(RuntimeError("bad")))
    monkeypatch.setattr(invoke_client, "_retryable_error", lambda _exc: False)
    with pytest.raises(RuntimeError, match="llm_gateway_invoke_failed:bad"):
        invoke_client.invoke_llm_gateway_with_usage(model_id="m", prompt="p", region="eu-west-1")
    monkeypatch.setattr(invoke_client, "invoke_llm_gateway_with_usage", lambda **_kwargs: ("text", {"total_tokens": 1}))
    assert invoke_client.invoke_llm_gateway(model_id="m", prompt="p", region="eu-west-1") == "text"
