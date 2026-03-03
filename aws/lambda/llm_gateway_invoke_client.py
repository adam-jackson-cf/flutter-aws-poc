import json
import os
import random
import time
from dataclasses import dataclass
from typing import Any, Dict, Tuple

import boto3
from botocore.config import Config
from quality_helpers import safe_int as _quality_safe_int


@dataclass(frozen=True)
class GatewayInvokeRequest:
    model_id: str
    provider: str
    region: str
    prompt: str
    provider_options: Dict[str, Any] | None = None


@dataclass(frozen=True)
class GatewayInvokeResponse:
    text: str
    usage: Dict[str, int]
    provider_used: str
    model_used: str
    latency_ms: float


def _function_name() -> str:
    value = str(os.environ.get("LLM_GATEWAY_FUNCTION_NAME", "")).strip()
    if not value:
        raise RuntimeError("llm_gateway_unconfigured:function_name_missing")
    return value


def _max_attempts() -> int:
    raw = str(os.environ.get("LLM_GATEWAY_INVOKE_MAX_ATTEMPTS", "3")).strip() or "3"
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError("llm_gateway_invoke_max_attempts_invalid") from exc
    if value < 1:
        raise ValueError("llm_gateway_invoke_max_attempts_invalid")
    return value


def _timeout_seconds() -> float:
    raw = str(os.environ.get("LLM_GATEWAY_INVOKE_TIMEOUT_SECONDS", "30")).strip() or "30"
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError("llm_gateway_invoke_timeout_invalid") from exc
    if value <= 0:
        raise ValueError("llm_gateway_invoke_timeout_invalid")
    return value


def _payload(request: GatewayInvokeRequest) -> bytes:
    return json.dumps(
        {
            "model_id": request.model_id,
            "provider": request.provider,
            "region": request.region,
            "prompt": request.prompt,
            "provider_options": request.provider_options or {},
        }
    ).encode("utf-8")


def _client(region: str) -> Any:
    connect_timeout = max(1, int(_timeout_seconds()))
    return boto3.client(
        "lambda",
        region_name=region,
        config=Config(
            read_timeout=connect_timeout + 5,
            connect_timeout=connect_timeout,
            retries={"max_attempts": 1, "mode": "standard"},
        ),
    )


def _safe_int(value: Any) -> int:
    return _quality_safe_int(value)


def _parse_invoke_payload(raw_payload: Dict[str, Any]) -> GatewayInvokeResponse:
    if not bool(raw_payload.get("ok", False)):
        error_code = str(raw_payload.get("error_code", "")).strip() or "gateway_error"
        error_message = str(raw_payload.get("error_message", "")).strip() or "unknown_error"
        raise RuntimeError(f"llm_gateway_error:{error_code}:{error_message}")
    usage = raw_payload.get("usage", {})
    if not isinstance(usage, dict):
        usage = {}
    return GatewayInvokeResponse(
        text=str(raw_payload.get("text", "")),
        usage={
            "input_tokens": max(0, _safe_int(usage.get("input_tokens", 0))),
            "output_tokens": max(0, _safe_int(usage.get("output_tokens", 0))),
            "total_tokens": max(0, _safe_int(usage.get("total_tokens", 0))),
        },
        provider_used=str(raw_payload.get("provider_used", "")),
        model_used=str(raw_payload.get("model_used", "")),
        latency_ms=float(raw_payload.get("latency_ms", 0.0) or 0.0),
    )


def _invoke_once(request: GatewayInvokeRequest) -> GatewayInvokeResponse:
    client = _client(request.region)
    response = client.invoke(
        FunctionName=_function_name(),
        InvocationType="RequestResponse",
        Payload=_payload(request),
    )
    status_code = int(response.get("StatusCode", 0))
    if status_code != 200:
        raise RuntimeError(f"llm_gateway_invoke_status:{status_code}")
    function_error = str(response.get("FunctionError", "")).strip()
    payload_stream = response.get("Payload")
    raw = payload_stream.read().decode("utf-8") if payload_stream is not None else ""
    if function_error:
        raise RuntimeError(f"llm_gateway_function_error:{function_error}:{raw}")
    try:
        payload = json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        raise RuntimeError("llm_gateway_invoke_response_invalid_json") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("llm_gateway_invoke_response_invalid_payload")
    return _parse_invoke_payload(payload)


def _retryable_error(exc: BaseException) -> bool:
    message = str(exc)
    return any(
        token in message
        for token in (
            "TooManyRequestsException",
            "ServiceException",
            "ThrottlingException",
            "ReadTimeoutError",
            "EndpointConnectionError",
            "llm_gateway_invoke_status:429",
            "llm_gateway_invoke_status:500",
            "llm_gateway_invoke_status:502",
            "llm_gateway_invoke_status:503",
            "llm_gateway_invoke_status:504",
        )
    )


def _sleep_backoff(attempt: int) -> None:
    jitter = random.uniform(0.0, 0.05)
    time.sleep(min(1.0, 0.15 * attempt) + jitter)


def invoke_llm_gateway_with_usage(
    *,
    model_id: str,
    prompt: str,
    region: str,
    provider: str = "auto",
    provider_options: Dict[str, Any] | None = None,
) -> Tuple[str, Dict[str, int]]:
    request = GatewayInvokeRequest(
        model_id=model_id,
        provider=provider,
        region=region,
        prompt=prompt,
        provider_options=provider_options,
    )
    attempts = _max_attempts()
    last_error: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = _invoke_once(request)
            return response.text, response.usage
        except Exception as exc:  # noqa: BLE001 - explicit retry policy
            last_error = exc
            if attempt >= attempts or not _retryable_error(exc):
                break
            _sleep_backoff(attempt)
    raise RuntimeError(f"llm_gateway_invoke_failed:{last_error}") from last_error


def invoke_llm_gateway(
    *,
    model_id: str,
    prompt: str,
    region: str,
    provider: str = "auto",
    provider_options: Dict[str, Any] | None = None,
) -> str:
    text, _usage = invoke_llm_gateway_with_usage(
        model_id=model_id,
        prompt=prompt,
        region=region,
        provider=provider,
        provider_options=provider_options,
    )
    return text
