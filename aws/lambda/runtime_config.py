import os
from typing import Any, Dict

from network_security import validate_endpoint_url


def selected_model_id(event: Dict[str, Any]) -> str:
    return event.get("model_id") or os.environ.get("BEDROCK_MODEL_ID", "eu.amazon.nova-lite-v1:0")


def selected_region(event: Dict[str, Any]) -> str:
    return event.get("bedrock_region") or os.environ.get("BEDROCK_REGION", os.environ.get("AWS_REGION", "eu-west-1"))


def selected_gateway_url(event: Dict[str, Any]) -> str:
    gateway_url = event.get("mcp_gateway_url") or os.environ.get("MCP_GATEWAY_URL", "")
    if not gateway_url:
        raise RuntimeError("MCP_GATEWAY_URL is required for MCP flow")
    validate_endpoint_url(
        url=gateway_url,
        env_var_name="MCP_GATEWAY_ALLOWED_HOSTS",
        default_allowed_hosts=".gateway.bedrock-agentcore.eu-west-1.amazonaws.com",
        env_getter=os.environ.get,
    )
    return gateway_url
