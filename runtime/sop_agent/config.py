import os
from dataclasses import dataclass


@dataclass(frozen=True)
class SopConfig:
    jira_base_url: str = os.environ.get("JIRA_BASE_URL", "https://jira.atlassian.com")
    bedrock_region: str = os.environ.get("BEDROCK_REGION", os.environ.get("AWS_REGION", "eu-west-1"))
    model_id: str = os.environ.get("BEDROCK_MODEL_ID", "eu.amazon.nova-lite-v1:0")
    mcp_gateway_url: str = os.environ.get("MCP_GATEWAY_URL", "")


DEFAULT_CONFIG = SopConfig()
