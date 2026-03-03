import json
import os
import socket
import time
from typing import Any, Dict, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import boto3

from bedrock_client import call_bedrock_with_usage
from network_security import validate_endpoint_url
from quality_helpers import merge_usage as _quality_merge_usage
from quality_helpers import safe_int as _quality_safe_int

_OPENAI_API_KEY_CACHE = ""


def _is_bedrock_style_model_id(model_id: str) -> bool:
    return "." in model_id and ":" in model_id


def _infer_provider(model_id: str) -> str:
    if _is_bedrock_style_model_id(model_id):
        return "bedrock"
    normalized = model_id.strip().lower()
    if normalized.startswith("gpt-") or "codex" in normalized or normalized.startswith("o1") or normalized.startswith("o3"):
        return "openai"
    return "bedrock"


def _selected_provider(model_id: str, provider: str) -> str:
    configured = provider.strip().lower()
    if configured in {"bedrock", "openai"}:
        return configured
    return _infer_provider(model_id)


def _parse_openai_secret_value(secret_value: str) -> str:
    candidate = secret_value.strip()
    if not candidate:
        return ""
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        return candidate
    if isinstance(payload, str):
        return payload.strip()
    if isinstance(payload, dict):
        for key in ("OPENAI_API_KEY", "openai_api_key", "api_key", "key"):
            value = payload.get(key, "")
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _resolve_openai_api_key(region: str) -> str:
    global _OPENAI_API_KEY_CACHE
    if _OPENAI_API_KEY_CACHE:
        return _OPENAI_API_KEY_CACHE

    direct_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if direct_key:
        _OPENAI_API_KEY_CACHE = direct_key
        return _OPENAI_API_KEY_CACHE

    secret_arn = os.environ.get("OPENAI_API_KEY_SECRET_ARN", "").strip()
    if not secret_arn:
        raise RuntimeError("openai_api_key_missing:configure_secret_or_env")

    secret_region = _secret_region_from_arn(secret_arn=secret_arn, default_region=region)
    secret_client = boto3.client("secretsmanager", region_name=secret_region)
    response = secret_client.get_secret_value(SecretId=secret_arn)
    secret_value = str(response.get("SecretString", "")).strip()
    api_key = _parse_openai_secret_value(secret_value)
    if not api_key:
        raise RuntimeError("openai_api_key_missing:secret_value_not_parseable")
    _OPENAI_API_KEY_CACHE = api_key
    return _OPENAI_API_KEY_CACHE


def _secret_region_from_arn(secret_arn: str, default_region: str) -> str:
    if not secret_arn.startswith("arn:"):
        return default_region
    parts = secret_arn.split(":")
    if len(parts) < 4:
        return default_region
    arn_region = parts[3].strip()
    return arn_region or default_region


def _extract_openai_response_text(payload: Dict[str, Any]) -> str:
    output_text = payload.get("output_text", "")
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    parts = _openai_output_text_parts(payload)
    merged = "\n".join(parts).strip()
    if not merged:
        raise ValueError("openai_response_missing_text")
    return merged


def _openai_output_text_parts(payload: Dict[str, Any]) -> list[str]:
    output = payload.get("output", [])
    if not isinstance(output, list):
        raise ValueError("openai_response_missing_output")
    parts: list[str] = []
    for item in output:
        parts.extend(_openai_output_item_texts(item))
    return parts


def _openai_output_item_texts(item: Any) -> list[str]:
    if not isinstance(item, dict):
        return []
    content = item.get("content", [])
    if not isinstance(content, list):
        return []
    texts: list[str] = []
    for content_item in content:
        if isinstance(content_item, dict):
            text = content_item.get("text", "")
            if isinstance(text, str) and text.strip():
                texts.append(text)
    return texts


def _parse_openai_http_timeout_seconds(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError("openai_http_timeout_seconds_invalid") from exc
    if parsed <= 0:
        raise ValueError("openai_http_timeout_seconds_invalid")
    return parsed


def _parse_openai_http_max_attempts(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError("openai_http_max_attempts_invalid") from exc
    if parsed < 1:
        raise ValueError("openai_http_max_attempts_invalid")
    return parsed


def _is_openai_timeout_exception(error: BaseException) -> bool:
    if isinstance(error, (TimeoutError, socket.timeout)):
        return True
    if isinstance(error, URLError):
        reason = error.reason
        if isinstance(reason, (TimeoutError, socket.timeout)):
            return True
        if isinstance(reason, str) and "timed out" in reason.lower():
            return True
    return False


def _is_retryable_openai_http_status(status_code: int) -> bool:
    return status_code in {408, 409, 429, 500, 502, 503, 504}


def _openai_incomplete_reason(payload: Dict[str, Any]) -> str:
    status = str(payload.get("status", "")).strip().lower()
    if status != "incomplete":
        return ""
    details = payload.get("incomplete_details", {})
    if not isinstance(details, dict):
        return "unknown"
    reason = details.get("reason", "")
    if not isinstance(reason, str):
        return "unknown"
    normalized = reason.strip().lower()
    return normalized or "unknown"


def _empty_usage() -> Dict[str, int]:
    return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}


def _safe_int(value: Any) -> int:
    return _quality_safe_int(value)


def _usage_from_openai_payload(payload: Dict[str, Any]) -> Dict[str, int]:
    usage = payload.get("usage", {})
    if not isinstance(usage, dict):
        usage = {}
    input_tokens = _safe_int(
        usage.get("input_tokens", usage.get("prompt_tokens", usage.get("inputTokens", 0)))
    )
    output_tokens = _safe_int(
        usage.get("output_tokens", usage.get("completion_tokens", usage.get("outputTokens", 0)))
    )
    total_tokens = _safe_int(
        usage.get("total_tokens", usage.get("totalTokens", input_tokens + output_tokens))
    )
    return {
        "input_tokens": max(0, input_tokens),
        "output_tokens": max(0, output_tokens),
        "total_tokens": max(0, total_tokens),
    }


def _merge_usage(base: Dict[str, int], additional: Dict[str, int]) -> Dict[str, int]:
    return _quality_merge_usage(base, additional)


def _resolved_openai_call_options(openai_options: Dict[str, Any] | None) -> Dict[str, Any]:
    defaults = _openai_runtime_options(None)
    if not isinstance(openai_options, dict):
        return defaults
    reasoning_effort = str(openai_options.get("reasoning_effort", defaults["reasoning_effort"])).strip().lower()
    verbosity = str(openai_options.get("verbosity", defaults["verbosity"])).strip().lower()
    max_output_tokens_raw = str(openai_options.get("max_output_tokens", defaults["max_output_tokens"])).strip()
    return {
        "reasoning_effort": reasoning_effort or defaults["reasoning_effort"],
        "verbosity": verbosity or defaults["verbosity"],
        "max_output_tokens": _parse_max_output_tokens(max_output_tokens_raw),
    }


def call_openai_with_usage(
    model_id: str,
    prompt: str,
    region: str,
    openai_options: Dict[str, Any] | None = None,
    provider_options: Dict[str, Any] | None = None,
) -> Tuple[str, Dict[str, int]]:
    options = _resolved_openai_call_options(openai_options)
    api_base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()
    validate_endpoint_url(
        url=api_base,
        env_var_name="OPENAI_ALLOWED_HOSTS",
        default_allowed_hosts="api.openai.com",
        env_getter=os.environ.get,
    )
    api_key = _resolve_openai_api_key(region=region)
    text_payload: Dict[str, Any] = {"verbosity": str(options["verbosity"])}
    json_schema_format = _openai_json_schema_format(provider_options=provider_options)
    if json_schema_format:
        text_payload["format"] = json_schema_format
    timeout_seconds = _parse_openai_http_timeout_seconds(
        str(os.environ.get("OPENAI_HTTP_TIMEOUT_SECONDS", "60")).strip()
    )
    max_attempts = _parse_openai_http_max_attempts(
        str(os.environ.get("OPENAI_HTTP_MAX_ATTEMPTS", "2")).strip()
    )
    requested_max_output_tokens = int(options["max_output_tokens"])
    usage_totals = _empty_usage()

    for attempt in range(max_attempts):
        request_body = {
            "model": model_id,
            "input": prompt,
            "max_output_tokens": requested_max_output_tokens,
            "reasoning": {"effort": str(options["reasoning_effort"])},
            "text": text_payload,
        }
        request = _openai_request(
            api_base=api_base,
            api_key=api_key,
            request_body=request_body,
        )
        try:
            parsed = _openai_request_payload(request, timeout_seconds)
        except (HTTPError, URLError, TimeoutError, socket.timeout) as exc:
            if _should_retry_openai_exception(exc=exc, attempt=attempt, max_attempts=max_attempts):
                time.sleep(0.5 * (attempt + 1))
                continue
            _raise_openai_exception(exc)

        usage_totals = _merge_usage(usage_totals, _usage_from_openai_payload(parsed))
        incomplete_reason = _openai_incomplete_reason(parsed)
        if _should_retry_for_max_output_tokens(incomplete_reason, attempt, max_attempts):
            requested_max_output_tokens = min(requested_max_output_tokens * 2, 8_000)
            continue
        if incomplete_reason:
            raise RuntimeError(f"openai_response_incomplete:{incomplete_reason}")
        return _extract_openai_response_text(parsed), usage_totals

    raise RuntimeError("openai_gateway_error:timeout")


def _openai_request(
    *,
    api_base: str,
    api_key: str,
    request_body: Dict[str, Any],
) -> Request:
    payload = json.dumps(request_body).encode("utf-8")
    return Request(
        url=f"{api_base.rstrip('/')}/responses",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )


def _openai_request_payload(request: Request, timeout_seconds: float) -> Dict[str, Any]:
    with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - outbound host allowlisted above
        return json.loads(response.read().decode("utf-8"))


def _should_retry_for_max_output_tokens(
    incomplete_reason: str,
    attempt: int,
    max_attempts: int,
) -> bool:
    return incomplete_reason == "max_output_tokens" and (attempt + 1) < max_attempts


def _should_retry_openai_exception(
    *,
    exc: HTTPError | URLError | TimeoutError | socket.timeout,
    attempt: int,
    max_attempts: int,
) -> bool:
    can_retry = (attempt + 1) < max_attempts
    if isinstance(exc, HTTPError):
        return _is_retryable_openai_http_status(exc.code) and can_retry
    if isinstance(exc, (URLError, TimeoutError, socket.timeout)):
        return _is_openai_timeout_exception(exc) and can_retry
    return False


def _raise_openai_exception(
    exc: HTTPError | URLError | TimeoutError | socket.timeout,
) -> None:
    if isinstance(exc, HTTPError):
        raise RuntimeError(f"openai_gateway_error:http_{exc.code}") from exc
    if _is_openai_timeout_exception(exc):
        raise RuntimeError("openai_gateway_error:timeout") from exc
    raise RuntimeError("openai_gateway_error:network") from exc


def call_openai(
    model_id: str,
    prompt: str,
    region: str,
    openai_options: Dict[str, Any] | None = None,
    provider_options: Dict[str, Any] | None = None,
) -> str:
    text, _usage = call_openai_with_usage(
        model_id=model_id,
        prompt=prompt,
        region=region,
        openai_options=openai_options,
        provider_options=provider_options,
    )
    return text


def _openai_runtime_options(provider_options: Dict[str, Any] | None) -> Dict[str, Any]:
    default_reasoning = str(os.environ.get("OPENAI_REASONING_EFFORT", "medium")).strip().lower() or "medium"
    default_verbosity = str(os.environ.get("OPENAI_TEXT_VERBOSITY", "medium")).strip().lower() or "medium"
    default_max_output_tokens = _parse_max_output_tokens(str(os.environ.get("OPENAI_MAX_OUTPUT_TOKENS", "2000")).strip())

    scoped_options: Dict[str, Any] = {}
    if isinstance(provider_options, dict):
        candidate = provider_options.get("openai", provider_options)
        if isinstance(candidate, dict):
            scoped_options = candidate

    reasoning_effort = str(scoped_options.get("reasoning_effort", default_reasoning)).strip().lower() or default_reasoning
    verbosity = str(scoped_options.get("verbosity", default_verbosity)).strip().lower() or default_verbosity
    max_output_tokens = _parse_max_output_tokens(str(scoped_options.get("max_output_tokens", default_max_output_tokens)).strip())
    return {
        "reasoning_effort": reasoning_effort,
        "verbosity": verbosity,
        "max_output_tokens": max_output_tokens,
    }


def _parse_max_output_tokens(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError("openai_max_output_tokens_invalid") from exc
    if parsed < 64:
        raise ValueError("openai_max_output_tokens_too_small")
    return parsed


def _openai_scoped_provider_options(provider_options: Dict[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(provider_options, dict):
        return {}
    candidate = provider_options.get("openai", provider_options)
    if isinstance(candidate, dict):
        return candidate
    return {}


def _openai_json_schema_format(provider_options: Dict[str, Any] | None) -> Dict[str, Any] | None:
    scoped_options = _openai_scoped_provider_options(provider_options)
    schema_config = scoped_options.get("response_json_schema")
    if not isinstance(schema_config, dict):
        return None
    name = str(schema_config.get("name", "")).strip()
    schema = schema_config.get("schema")
    strict = bool(schema_config.get("strict", True))
    if not name or not isinstance(schema, dict):
        return None
    return {
        "type": "json_schema",
        "name": name,
        "schema": schema,
        "strict": strict,
    }


def call_llm_gateway(
    model_id: str,
    prompt: str,
    region: str,
    provider: str = "auto",
    provider_options: Dict[str, Any] | None = None,
) -> str:
    text, _usage = call_llm_gateway_with_usage(
        model_id=model_id,
        prompt=prompt,
        region=region,
        provider=provider,
        provider_options=provider_options,
    )
    return text


def call_llm_gateway_with_usage(
    model_id: str,
    prompt: str,
    region: str,
    provider: str = "auto",
    provider_options: Dict[str, Any] | None = None,
) -> Tuple[str, Dict[str, int]]:
    selected = _selected_provider(model_id=model_id, provider=provider)
    if selected == "openai":
        scoped_options = _openai_scoped_provider_options(provider_options)
        options = _openai_runtime_options(provider_options)
        return call_openai_with_usage(
            model_id=model_id,
            prompt=prompt,
            region=region,
            openai_options=options,
            provider_options=scoped_options,
        )
    return call_bedrock_with_usage(model_id=model_id, prompt=prompt, region=region)
