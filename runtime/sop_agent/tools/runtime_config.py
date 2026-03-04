import os
from typing import Any, Dict

from .network_security import validate_endpoint_url


def selected_model_id(event: Dict[str, Any]) -> str:
    return event.get("model_id") or os.environ.get("MODEL_ID", "eu.amazon.nova-lite-v1:0")


def selected_model_provider(event: Dict[str, Any]) -> str:
    return str(event.get("model_provider") or os.environ.get("MODEL_PROVIDER", "auto")).strip().lower() or "auto"


def selected_region(event: Dict[str, Any]) -> str:
    return event.get("bedrock_region") or os.environ.get("BEDROCK_REGION", os.environ.get("AWS_REGION", "eu-west-1"))


def selected_provider_options(event: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    max_output_tokens = _selected_openai_max_output_tokens(event)
    return {
        "openai": {
            "reasoning_effort": str(
                event.get("openai_reasoning_effort") or os.environ.get("OPENAI_REASONING_EFFORT", "medium")
            )
            .strip()
            .lower()
            or "medium",
            "verbosity": str(
                event.get("openai_text_verbosity") or os.environ.get("OPENAI_TEXT_VERBOSITY", "medium")
            )
            .strip()
            .lower()
            or "medium",
            "max_output_tokens": max_output_tokens,
        }
    }


def _selected_openai_max_output_tokens(event: Dict[str, Any]) -> int:
    raw = str(event.get("openai_max_output_tokens") or os.environ.get("OPENAI_MAX_OUTPUT_TOKENS", "2000")).strip() or "2000"
    try:
        parsed = int(raw)
    except ValueError as exc:
        raise ValueError("openai_max_output_tokens_invalid") from exc
    if parsed < 64:
        raise ValueError("openai_max_output_tokens_too_small")
    return parsed


def selected_gateway_url(event: Dict[str, Any]) -> str:
    gateway_url = event.get("mcp_gateway_url") or os.environ.get("MCP_GATEWAY_URL", "")
    if not gateway_url:
        raise RuntimeError("MCP_GATEWAY_URL is required for MCP flow")
    region = selected_region(event)
    validate_endpoint_url(
        url=gateway_url,
        env_var_name="MCP_GATEWAY_ALLOWED_HOSTS",
        default_allowed_hosts=f".gateway.bedrock-agentcore.{region}.amazonaws.com",
        env_getter=os.environ.get,
    )
    return gateway_url
