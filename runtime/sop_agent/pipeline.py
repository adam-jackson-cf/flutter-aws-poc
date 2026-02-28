import time
from typing import Any, Dict

from .config import SopConfig
from .stages.generation_stage import generate_response
from .stages.intake_stage import run_intake
from .tools.jira_mcp_flow import McpJiraFlow, McpSelectionError
from .tools.jira_native_sdk import JiraSdkClient
from .tools.strands_native_flow import StrandsNativeFlow


class SopPipeline:
    def __init__(self, config: SopConfig) -> None:
        self._config = config
        self._jira = JiraSdkClient(base_url=config.jira_base_url)
        self._strands_native = StrandsNativeFlow(
            jira_client=self._jira,
            model_id=config.model_id,
            region=config.bedrock_region,
        )
        self._mcp = None
        if config.mcp_gateway_url:
            self._mcp = McpJiraFlow(
                jira_client=self._jira,
                model_id=config.model_id,
                region=config.bedrock_region,
                gateway_url=config.mcp_gateway_url,
            )

    def run_route(self, request_text: str, flow: str, dry_run: bool = False) -> Dict[str, Any]:
        started = time.time()
        intake = run_intake(request_text)

        if flow == "native":
            native_outcome = self._strands_native.fetch_issue_with_agent(intake=intake, dry_run=dry_run)
            issue = native_outcome["issue"]
            tool_failure = bool(native_outcome["tool_failure"])
            selection = native_outcome["selection"]
        elif flow == "mcp":
            if self._mcp is None:
                raise McpSelectionError("MCP flow requires MCP_GATEWAY_URL to be configured")
            mcp_outcome = self._mcp.fetch_issue_with_selection(intake=intake, dry_run=dry_run)
            issue = mcp_outcome["issue"]
            tool_failure = bool(mcp_outcome["tool_failure"])
            selection = mcp_outcome["selection"]
        else:
            raise ValueError("flow must be one of: native, mcp")

        total_latency_ms = round((time.time() - started) * 1000, 2)

        return {
            "flow": flow,
            "intake": intake,
            "tool_selection": selection,
            "tool_failure": tool_failure,
            "issue": issue,
            "metrics": {
                "intent": intake["intent"],
                "total_latency_ms": total_latency_ms,
                "tool_failure": tool_failure,
            },
        }

    def run(self, request_text: str, flow: str, dry_run: bool = False) -> Dict[str, Any]:
        started = time.time()
        route = self.run_route(request_text=request_text, flow=flow, dry_run=dry_run)
        intake = route["intake"]
        issue = route["issue"]
        tool_failure = bool(route["tool_failure"])
        selection = route["tool_selection"]

        response = generate_response(
            intake=intake,
            issue=issue,
            model_id=self._config.model_id,
            region=self._config.bedrock_region,
            dry_run=dry_run,
        )

        total_latency_ms = round((time.time() - started) * 1000, 2)

        return {
            "flow": flow,
            "intake": intake,
            "tool_selection": selection,
            "tool_failure": tool_failure,
            "issue": issue,
            "response": response,
            "metrics": {
                "intent": intake["intent"],
                "total_latency_ms": total_latency_ms,
                "tool_failure": tool_failure,
            },
        }
