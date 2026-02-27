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


class AwsPipelineRunner:
    def __init__(
        self,
        state_machine_arn: str,
        aws_region: str,
        aws_profile: Optional[str] = None,
        poll_interval_seconds: float = 2.0,
        execution_timeout_seconds: int = 900,
    ) -> None:
        if not state_machine_arn:
            raise ValueError("state_machine_arn is required")
        if not aws_region:
            raise ValueError("aws_region is required")

        session_kwargs: Dict[str, Any] = {"region_name": aws_region}
        if aws_profile:
            session_kwargs["profile_name"] = aws_profile
        session = boto3.Session(**session_kwargs)

        self._state_machine_arn = state_machine_arn
        self._poll_interval_seconds = poll_interval_seconds
        self._execution_timeout_seconds = execution_timeout_seconds
        self._sfn = session.client("stepfunctions")
        self._s3 = session.client("s3")

    def run_case(self, flow: str, request_text: str, case_id: str, dry_run: bool) -> PipelineRunResult:
        started = time.time()
        execution_name = self._build_execution_name(flow=flow, case_id=case_id)
        execution_input = {
            "flow": flow,
            "request_text": request_text,
            "case_id": case_id,
            "dry_run": dry_run,
        }
        started_response = self._sfn.start_execution(
            stateMachineArn=self._state_machine_arn,
            name=execution_name,
            input=json.dumps(execution_input),
        )
        execution_arn = started_response["executionArn"]

        while True:
            description = self._sfn.describe_execution(executionArn=execution_arn)
            status = description["status"]
            if status == "SUCCEEDED":
                output = description.get("output", "")
                if not output:
                    raise RuntimeError(f"State machine execution missing output: {execution_arn}")
                payload = json.loads(output)
                artifact_s3_uri = str(payload.get("artifact_s3_uri", "")).strip()
                if not artifact_s3_uri:
                    raise RuntimeError(f"State machine output missing artifact_s3_uri: {execution_arn}")

                artifact_payload = self._read_artifact(artifact_s3_uri)
                return PipelineRunResult(
                    execution_arn=execution_arn,
                    payload=artifact_payload,
                    artifact_s3_uri=artifact_s3_uri,
                )

            if status in {"FAILED", "TIMED_OUT", "ABORTED"}:
                error = description.get("error", "unknown_error")
                cause = description.get("cause", "unknown_cause")
                raise RuntimeError(f"Execution {status}: {error}: {cause}")

            if (time.time() - started) > self._execution_timeout_seconds:
                raise TimeoutError(f"Execution timed out after {self._execution_timeout_seconds}s: {execution_arn}")

            time.sleep(self._poll_interval_seconds)

    def _read_artifact(self, artifact_s3_uri: str) -> Dict[str, Any]:
        bucket, key = _parse_s3_uri(artifact_s3_uri)
        response = self._s3.get_object(Bucket=bucket, Key=key)
        body = response["Body"].read().decode("utf-8")
        return json.loads(body)

    @staticmethod
    def _build_execution_name(flow: str, case_id: str) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        normalized_case = EXECUTION_NAME_PATTERN.sub("-", case_id)[:30].strip("-")
        normalized_flow = EXECUTION_NAME_PATTERN.sub("-", flow)[:12].strip("-")
        suffix = uuid.uuid4().hex[:8]
        name = f"eval-{normalized_flow}-{normalized_case}-{timestamp}-{suffix}"
        return name[:80]
