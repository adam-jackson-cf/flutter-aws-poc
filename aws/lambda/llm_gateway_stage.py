import time
from dataclasses import dataclass
from typing import Any, Dict

from llm_gateway_client import call_llm_gateway_with_usage


@dataclass(frozen=True)
class GatewayRequest:
    model_id: str
    provider: str
    region: str
    prompt: str
    provider_options: Dict[str, Any] | None


def _safe_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _safe_str(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def _parse_request(event: Dict[str, Any]) -> GatewayRequest:
    model_id = _safe_str(event.get("model_id"))
    provider = _safe_str(event.get("provider")) or "auto"
    region = _safe_str(event.get("region"))
    prompt = _safe_str(event.get("prompt"))
    if not model_id:
        raise ValueError("gateway_request_invalid:model_id_missing")
    if not region:
        raise ValueError("gateway_request_invalid:region_missing")
    if not prompt:
        raise ValueError("gateway_request_invalid:prompt_missing")
    return GatewayRequest(
        model_id=model_id,
        provider=provider,
        region=region,
        prompt=prompt,
        provider_options=_safe_dict(event.get("provider_options")) or None,
    )


def _safe_usage(usage: Dict[str, Any]) -> Dict[str, int]:
    if not isinstance(usage, dict):
        return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    return {
        "input_tokens": int(usage.get("input_tokens", 0) or 0),
        "output_tokens": int(usage.get("output_tokens", 0) or 0),
        "total_tokens": int(usage.get("total_tokens", 0) or 0),
    }


def handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    started = time.time()
    try:
        request = _parse_request(event if isinstance(event, dict) else {})
        response_text, usage = call_llm_gateway_with_usage(
            model_id=request.model_id,
            prompt=request.prompt,
            region=request.region,
            provider=request.provider,
            provider_options=request.provider_options,
        )
        return {
            "ok": True,
            "text": response_text,
            "usage": _safe_usage(usage),
            "provider_used": request.provider,
            "model_used": request.model_id,
            "latency_ms": round((time.time() - started) * 1000, 2),
        }
    except Exception as exc:  # noqa: BLE001 - boundary returns structured errors to callers
        message = str(exc).strip() or "unknown_error"
        error_code = message.split(":", 1)[0]
        return {
            "ok": False,
            "error_code": error_code,
            "error_message": message,
            "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            "provider_used": _safe_str(event.get("provider")) if isinstance(event, dict) else "",
            "model_used": _safe_str(event.get("model_id")) if isinstance(event, dict) else "",
            "latency_ms": round((time.time() - started) * 1000, 2),
        }


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    return handler(event, context)
