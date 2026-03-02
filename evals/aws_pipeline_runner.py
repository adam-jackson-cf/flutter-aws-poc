import json
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

import boto3


EXECUTION_NAME_PATTERN = re.compile(r"[^A-Za-z0-9_-]")


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
    runtime_bedrock_model_id: str = ""
    bedrock_region: str = ""
    model_provider: str = ""
    openai_reasoning_effort: str = ""
    openai_text_verbosity: str = ""
    openai_max_output_tokens: int = 0


@dataclass(frozen=True)
class AwsPipelineRunnerConfig:
    state_machine_arn: str
    aws_region: str
    aws_profile: Optional[str] = None
    poll_interval_seconds: float = 2.0
    execution_timeout_seconds: int = 900


class AwsPipelineRunner:
    def __init__(self, config: AwsPipelineRunnerConfig) -> None:
        if not config.state_machine_arn:
            raise ValueError("state_machine_arn is required")
        if not config.aws_region:
            raise ValueError("aws_region is required")

        session_kwargs: Dict[str, Any] = {"region_name": config.aws_region}
        if config.aws_profile:
            session_kwargs["profile_name"] = config.aws_profile
        session = boto3.Session(**session_kwargs)

        self._state_machine_arn = config.state_machine_arn
        self._poll_interval_seconds = config.poll_interval_seconds
        self._execution_timeout_seconds = config.execution_timeout_seconds
        self._sfn = session.client("stepfunctions")
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
        started = time.time()
        execution_name = self._build_execution_name(
            flow=request.flow,
            case_id=request.case_id,
        )
        started_response = self._sfn.start_execution(
            stateMachineArn=self._state_machine_arn,
            name=execution_name,
            input=json.dumps(self._execution_input(request)),
        )
        execution_arn = started_response["executionArn"]
        return self._wait_for_execution_result(
            execution_arn=execution_arn,
            flow=request.flow,
            started=started,
        )

    @staticmethod
    def _execution_input(request: PipelineRunRequest) -> Dict[str, Any]:
        payload = {
            "flow": request.flow,
            "request_text": request.request_text,
            "case_id": request.case_id,
            "expected_tool": request.expected_tool,
            "dry_run": request.dry_run,
        }
        if request.model_id:
            payload["model_id"] = request.model_id
        if request.runtime_bedrock_model_id:
            payload["runtime_bedrock_model_id"] = request.runtime_bedrock_model_id
        if request.bedrock_region:
            payload["bedrock_region"] = request.bedrock_region
        if request.model_provider:
            payload["model_provider"] = request.model_provider
        if request.openai_reasoning_effort:
            payload["openai_reasoning_effort"] = request.openai_reasoning_effort
        if request.openai_text_verbosity:
            payload["openai_text_verbosity"] = request.openai_text_verbosity
        if request.openai_max_output_tokens > 0:
            payload["openai_max_output_tokens"] = request.openai_max_output_tokens
        return payload

    def _wait_for_execution_result(
        self,
        *,
        execution_arn: str,
        flow: str,
        started: float,
    ) -> PipelineRunResult:
        while True:
            description = self._sfn.describe_execution(executionArn=execution_arn)
            status = description["status"]
            if status == "SUCCEEDED":
                return self._successful_execution_result(
                    execution_arn=execution_arn,
                    flow=flow,
                    output=str(description.get("output", "")),
                )

            if status in {"FAILED", "TIMED_OUT", "ABORTED"}:
                self._raise_execution_failure(status=status, description=description)

            if (time.time() - started) > self._execution_timeout_seconds:
                raise TimeoutError(f"Execution timed out after {self._execution_timeout_seconds}s: {execution_arn}")

            time.sleep(self._poll_interval_seconds)

    def _successful_execution_result(
        self,
        *,
        execution_arn: str,
        flow: str,
        output: str,
    ) -> PipelineRunResult:
        if not output:
            raise RuntimeError(f"State machine execution missing output: {execution_arn}")
        payload = json.loads(output)
        artifact_s3_uri = str(payload.get("artifact_s3_uri", "")).strip()
        if not artifact_s3_uri:
            raise RuntimeError(f"State machine output missing artifact_s3_uri: {execution_arn}")
        artifact_payload = self._read_artifact(artifact_s3_uri)
        self._validate_artifact_payload(payload=artifact_payload, flow=flow)
        return PipelineRunResult(
            execution_arn=execution_arn,
            payload=artifact_payload,
            artifact_s3_uri=artifact_s3_uri,
        )

    @staticmethod
    def _raise_execution_failure(
        *,
        status: str,
        description: Dict[str, Any],
    ) -> None:
        error = description.get("error", "unknown_error")
        cause = description.get("cause", "unknown_cause")
        raise RuntimeError(f"Execution {status}: {error}: {cause}")

    def _read_artifact(self, artifact_s3_uri: str) -> Dict[str, Any]:
        bucket, key = _parse_s3_uri(artifact_s3_uri)
        response = self._s3.get_object(Bucket=bucket, Key=key)
        body = response["Body"].read().decode("utf-8")
        return json.loads(body)

    @staticmethod
    def _require_dict_field(payload: Dict[str, Any], key: str) -> Dict[str, Any]:
        value = payload.get(key)
        if not isinstance(value, dict):
            raise RuntimeError(f"artifact_schema_invalid:{key}_missing_or_not_object")
        return value

    @staticmethod
    def _selection_key_for_flow(flow: str) -> Optional[str]:
        return {"native": "native_selection", "mcp": "mcp_selection"}.get(flow)

    @staticmethod
    def _validate_selection_payload(payload: Dict[str, Any], selection_key: str) -> None:
        selection_payload = AwsPipelineRunner._require_dict_field(payload, selection_key)
        selected_tool = selection_payload.get("selected_tool", "")
        if not isinstance(selected_tool, str):
            raise RuntimeError(f"artifact_schema_invalid:{selection_key}.selected_tool_not_string")

    @staticmethod
    def _validate_artifact_payload(payload: Dict[str, Any], flow: str) -> None:
        if not isinstance(payload, dict):
            raise RuntimeError("artifact_schema_invalid:payload_not_object")

        for key in ("intake", "tool_result", "run_metrics"):
            AwsPipelineRunner._require_dict_field(payload, key)

        selection_key = AwsPipelineRunner._selection_key_for_flow(flow)
        if selection_key is not None:
            AwsPipelineRunner._validate_selection_payload(payload, selection_key)

        payload_flow = str(payload.get("flow", "")).strip()
        if payload_flow and payload_flow != flow:
            raise RuntimeError(
                f"artifact_schema_invalid:flow_mismatch:expected={flow}:actual={payload_flow}"
            )

    @staticmethod
    def _build_execution_name(flow: str, case_id: str) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        normalized_case = EXECUTION_NAME_PATTERN.sub("-", case_id)[:30].strip("-")
        normalized_flow = EXECUTION_NAME_PATTERN.sub("-", flow)[:12].strip("-")
        suffix = uuid.uuid4().hex[:8]
        name = f"eval-{normalized_flow}-{normalized_case}-{timestamp}-{suffix}"
        return name[:80]
