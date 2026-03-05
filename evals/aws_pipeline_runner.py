import json
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

import boto3


DEFAULT_RUNTIME_CONTENT_TYPE = "application/json"
DEFAULT_RUNTIME_ACCEPT = "application/json"


def _parse_s3_uri(uri: str) -> Tuple[str, str]:
    parsed = urlparse(uri)
    if parsed.scheme != "s3" or not parsed.netloc or not parsed.path:
        raise ValueError(f"Invalid S3 URI: {uri}")
    return parsed.netloc, parsed.path.lstrip("/")


@dataclass
class PipelineRunResult:
    execution_arn: str
    payload: Dict[str, Any]
    artifact_s3_uri: str


@dataclass(frozen=True)
class PipelineRunRequest:
    flow: str
    request_text: str
    case_id: str
    expected_tool: str
    dry_run: bool
    model_id: str = ""
    runtime_model_id: str = ""
    bedrock_region: str = ""
    model_provider: str = ""
    openai_reasoning_effort: str = ""
    openai_text_verbosity: str = ""
    openai_max_output_tokens: int = 0
    llm_route_path: str = ""
    execution_mode: str = ""
    mcp_binding_mode: str = ""
    route_semantics_version: str = ""


def _execution_input(request: PipelineRunRequest) -> Dict[str, Any]:
    payload = {
        "flow": request.flow,
        "request_text": request.request_text,
        "case_id": request.case_id,
        "expected_tool": request.expected_tool,
        "dry_run": request.dry_run,
    }
    payload.update(_optional_execution_fields(request))
    return payload


def _optional_execution_fields(request: PipelineRunRequest) -> Dict[str, Any]:
    optional: Dict[str, Any] = {}
    for key, value in (
        ("model_id", request.model_id),
        ("runtime_model_id", request.runtime_model_id),
        ("bedrock_region", request.bedrock_region),
        ("model_provider", request.model_provider),
        ("openai_reasoning_effort", request.openai_reasoning_effort),
        ("openai_text_verbosity", request.openai_text_verbosity),
        ("llm_route_path", request.llm_route_path),
        ("execution_mode", request.execution_mode),
        ("mcp_binding_mode", request.mcp_binding_mode),
        ("route_semantics_version", request.route_semantics_version),
    ):
        if value:
            optional[key] = value
    if request.openai_max_output_tokens > 0:
        optional["openai_max_output_tokens"] = request.openai_max_output_tokens
    return optional


@dataclass(frozen=True)
class AgentCoreRuntimeRunnerConfig:
    agent_runtime_arn: str
    aws_region: str
    aws_profile: Optional[str] = None
    expected_contract_version: str = ""
    content_type: str = DEFAULT_RUNTIME_CONTENT_TYPE
    accept: str = DEFAULT_RUNTIME_ACCEPT
    qualifier: str = ""


def _require_dict_field(payload: Dict[str, Any], key: str) -> Dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise RuntimeError(f"artifact_schema_invalid:{key}_missing_or_not_object")
    return value


def _selection_key_for_flow(flow: str) -> Optional[str]:
    return {"native": "native_selection", "mcp": "mcp_selection"}.get(flow)


def _string_value(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _normalize_actual_payload(actual_payload: Dict[str, Any]) -> tuple[str, str]:
    selected_tool = _string_value(actual_payload.get("selected_tool"))
    tool = _string_value(actual_payload.get("tool"))
    if selected_tool and not tool:
        actual_payload["tool"] = selected_tool
        tool = selected_tool
    elif tool and not selected_tool:
        actual_payload["selected_tool"] = tool
        selected_tool = tool
    return selected_tool, tool


def _normalize_selection_payload(payload: Dict[str, Any], flow: str) -> None:
    normalized_tool = ""
    actual_payload = payload.get("actual")
    if isinstance(actual_payload, dict):
        actual_selected_tool, actual_tool = _normalize_actual_payload(actual_payload)
        normalized_tool = actual_selected_tool or actual_tool

    selection_key = _selection_key_for_flow(flow)
    if selection_key is None:
        return
    selection_payload = payload.get(selection_key)
    if not isinstance(selection_payload, dict):
        if normalized_tool:
            payload[selection_key] = {"selected_tool": normalized_tool}
        return
    if isinstance(selection_payload.get("selected_tool"), str):
        return
    if normalized_tool:
        selection_payload["selected_tool"] = normalized_tool


def _validate_selection_payload(payload: Dict[str, Any], selection_key: str) -> None:
    selection_payload = _require_dict_field(payload, selection_key)
    selected_tool = selection_payload.get("selected_tool", "")
    if not isinstance(selected_tool, str):
        raise RuntimeError(f"artifact_schema_invalid:{selection_key}.selected_tool_not_string")


def _validate_contract_version(
    payload: Dict[str, Any],
    expected_contract_version: str,
) -> None:
    _validate_schema_version_field(
        payload=payload,
        field_name="contract_version",
        expected_value=expected_contract_version,
    )


def _validate_schema_version_field(
    *,
    payload: Dict[str, Any],
    field_name: str,
    expected_value: str,
) -> None:
    actual_value = str(payload.get(field_name, "")).strip()
    if not actual_value:
        raise RuntimeError(f"artifact_schema_invalid:{field_name}_missing")
    if expected_value and actual_value != expected_value:
        raise RuntimeError(
            f"artifact_schema_invalid:{field_name}_mismatch:"
            f"expected={expected_value}:actual={actual_value}"
        )


def validate_eval_artifact_schema_version(
    *,
    payload: Dict[str, Any],
    expected_eval_schema_version: str,
) -> None:
    _validate_schema_version_field(
        payload=payload,
        field_name="eval_schema_version",
        expected_value=expected_eval_schema_version,
    )


def _validate_artifact_payload(
    payload: Dict[str, Any],
    flow: str,
    expected_contract_version: str = "",
) -> None:
    if not isinstance(payload, dict):
        raise RuntimeError("artifact_schema_invalid:payload_not_object")

    _validate_contract_version(
        payload=payload,
        expected_contract_version=expected_contract_version,
    )

    _normalize_selection_payload(payload=payload, flow=flow)

    for key in ("intake", "tool_result", "run_metrics"):
        _require_dict_field(payload, key)

    selection_key = _selection_key_for_flow(flow)
    if selection_key is not None:
        _validate_selection_payload(payload, selection_key)

    payload_flow = str(payload.get("flow", "")).strip()
    if payload_flow and payload_flow != flow:
        raise RuntimeError(
            f"artifact_schema_invalid:flow_mismatch:expected={flow}:actual={payload_flow}"
        )


class AgentCoreRuntimeRunner:
    def __init__(self, config: AgentCoreRuntimeRunnerConfig) -> None:
        if not config.agent_runtime_arn:
            raise ValueError("agent_runtime_arn is required")
        if not config.aws_region:
            raise ValueError("aws_region is required")

        session_kwargs: Dict[str, Any] = {"region_name": config.aws_region}
        if config.aws_profile:
            session_kwargs["profile_name"] = config.aws_profile
        session = boto3.Session(**session_kwargs)

        self._agent_runtime_arn = config.agent_runtime_arn
        self._expected_contract_version = str(config.expected_contract_version).strip()
        self._content_type = str(config.content_type).strip() or DEFAULT_RUNTIME_CONTENT_TYPE
        self._accept = str(config.accept).strip() or DEFAULT_RUNTIME_ACCEPT
        self._qualifier = str(config.qualifier).strip()
        self._runtime = session.client("bedrock-agentcore")
        self._s3 = session.client("s3")
        self._sts = session.client("sts")

    def preflight_identity(self) -> Dict[str, str]:
        response = self._sts.get_caller_identity()
        return {
            "account": str(response.get("Account", "")),
            "arn": str(response.get("Arn", "")),
            "user_id": str(response.get("UserId", "")),
        }

    def run_case(self, request: PipelineRunRequest) -> PipelineRunResult:
        invoke_args: Dict[str, Any] = {
            "agentRuntimeArn": self._agent_runtime_arn,
            "contentType": self._content_type,
            "accept": self._accept,
            "payload": json.dumps(_execution_input(request)).encode("utf-8"),
        }
        if self._qualifier:
            invoke_args["qualifier"] = self._qualifier

        response = self._runtime.invoke_agent_runtime(**invoke_args)
        execution_arn = self._execution_reference(response=response, request=request)
        runtime_payload = self._decode_runtime_payload(response.get("response"))
        artifact_s3_uri = str(runtime_payload.get("artifact_s3_uri", "")).strip()
        artifact_payload = self._artifact_payload_for_result(runtime_payload, artifact_s3_uri)
        _validate_artifact_payload(
            payload=artifact_payload,
            flow=request.flow,
            expected_contract_version=self._expected_contract_version,
        )
        return PipelineRunResult(
            execution_arn=execution_arn,
            payload=artifact_payload,
            artifact_s3_uri=artifact_s3_uri,
        )

    @staticmethod
    def _execution_reference(response: Dict[str, Any], request: PipelineRunRequest) -> str:
        for key in ("traceId", "runtimeSessionId", "mcpSessionId"):
            value = str(response.get(key, "")).strip()
            if value:
                return value
        return f"agent-runtime://{request.flow}/{request.case_id}"

    @staticmethod
    def _decode_runtime_payload(payload_stream: Any) -> Dict[str, Any]:
        raw_payload = AgentCoreRuntimeRunner._read_payload_stream(payload_stream)
        if not raw_payload:
            raise RuntimeError("agent_runtime_response_empty")
        try:
            payload = json.loads(raw_payload.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError("agent_runtime_response_invalid_json") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("agent_runtime_response_not_object")
        return payload

    @staticmethod
    def _read_payload_stream(payload_stream: Any) -> bytes:
        if payload_stream is None:
            raise RuntimeError("agent_runtime_response_missing_payload")
        raw_payload = payload_stream.read() if hasattr(payload_stream, "read") else payload_stream
        if isinstance(raw_payload, bytes):
            return raw_payload
        if isinstance(raw_payload, bytearray):
            return bytes(raw_payload)
        if isinstance(raw_payload, str):
            return raw_payload.encode("utf-8")
        raise RuntimeError("agent_runtime_response_invalid_payload_type")

    def _artifact_payload_for_result(self, runtime_payload: Dict[str, Any], artifact_s3_uri: str) -> Dict[str, Any]:
        if artifact_s3_uri:
            return self._read_artifact(artifact_s3_uri)
        return runtime_payload

    def _read_artifact(self, artifact_s3_uri: str) -> Dict[str, Any]:
        bucket, key = _parse_s3_uri(artifact_s3_uri)
        response = self._s3.get_object(Bucket=bucket, Key=key)
        body = response["Body"].read().decode("utf-8")
        return json.loads(body)
