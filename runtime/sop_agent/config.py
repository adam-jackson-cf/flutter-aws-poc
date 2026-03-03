import os
from dataclasses import dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class SopConfig:
    jira_base_url: str = os.environ.get("JIRA_BASE_URL", "https://jira.atlassian.com")
    bedrock_region: str = os.environ.get("BEDROCK_REGION", os.environ.get("AWS_REGION", "eu-west-1"))
    model_id: str = os.environ.get("MODEL_ID", "eu.amazon.nova-lite-v1:0")
    model_provider: str = os.environ.get("MODEL_PROVIDER", "auto")
    openai_reasoning_effort: str = os.environ.get("OPENAI_REASONING_EFFORT", "medium")
    openai_text_verbosity: str = os.environ.get("OPENAI_TEXT_VERBOSITY", "medium")
    openai_max_output_tokens: int = int(os.environ.get("OPENAI_MAX_OUTPUT_TOKENS", "2000"))
    mcp_gateway_url: str = os.environ.get("MCP_GATEWAY_URL", "")
    llm_gateway_function_name: str = os.environ.get("LLM_GATEWAY_FUNCTION_NAME", "")

    def provider_options(self) -> Dict[str, Dict[str, Any]]:
        return {
            "openai": {
                "reasoning_effort": self.openai_reasoning_effort.strip().lower() or "medium",
                "verbosity": self.openai_text_verbosity.strip().lower() or "medium",
                "max_output_tokens": int(self.openai_max_output_tokens),
            }
        }


DEFAULT_CONFIG = SopConfig()
