import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, TypedDict

import boto3

from ..domain import MCP_EXPECTED_TOOL, MCP_TOOL_SCOPE_BY_INTENT, build_tool_arguments, scope_tools_by_intent, strip_target_prefix
from .agentcore_mcp_client import AgentCoreMcpClient
from .jira_native_sdk import JiraSdkClient
from .tool_flow_result import ToolFlowScope, flow_failure, flow_success

EXPECTED_TOOL = MCP_EXPECTED_TOOL
TOOL_SCOPE_BY_INTENT: Dict[str, List[str]] = MCP_TOOL_SCOPE_BY_INTENT


class McpSelectionError(RuntimeError):
    pass


@dataclass(frozen=True)
class ScopedCatalog:
    intent: str
    all_tools: List[Dict[str, Any]]
    scoped_tools: List[Dict[str, Any]]
    expected_tool_name: str
    tool_map: Dict[str, Dict[str, Any]]


class FailureResult(TypedDict, total=False):
    selection: Dict[str, str]
    tool_failure: bool
    issue: Dict[str, Any]
    scope: Dict[str, Any]
    tool_payload: Dict[str, Any]


def _extract_json(raw_text: str) -> Dict[str, Any]:
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise McpSelectionError("LLM did not return JSON for MCP tool selection")
    candidate = raw_text[start : end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        repaired = re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", candidate)
        return json.loads(repaired)


class McpJiraFlow:
    def __init__(self, jira_client: JiraSdkClient, model_id: str, region: str, gateway_url: str) -> None:
        self._jira_client = jira_client
        self._model_id = model_id
        self._region = region
        self._mcp_client = AgentCoreMcpClient(gateway_url=gateway_url, region=region)

    @staticmethod
    def _strip_target_prefix(tool_name: str) -> str:
        return strip_target_prefix(tool_name)

    def _find_expected_tool(self, tools: List[Dict[str, Any]]) -> str:
        for tool in tools:
            name = str(tool.get("name", ""))
            if self._strip_target_prefix(name) == EXPECTED_TOOL:
                return name
        raise McpSelectionError(f"Expected MCP tool {EXPECTED_TOOL} not found in gateway catalog")

    def _scope_tools_for_intent(self, tools: List[Dict[str, Any]], intent: str) -> List[Dict[str, Any]]:
        try:
            return scope_tools_by_intent(tools=tools, intent=intent, scope_by_intent=TOOL_SCOPE_BY_INTENT)
        except RuntimeError as exc:
            raise McpSelectionError(f"No MCP tools available after scoping for intent={intent}") from exc

    @staticmethod
    def _build_tool_arguments(selected_tool: Dict[str, Any], intake: Dict[str, Any]) -> Dict[str, Any]:
        return build_tool_arguments(
            selected_tool=selected_tool,
            issue_key=intake["issue_key"],
            request_text=intake["request_text"],
        )

    def _build_scoped_catalog(self, intent: str) -> ScopedCatalog:
        all_tools = self._mcp_client.list_tools()
        scoped_tools = self._scope_tools_for_intent(all_tools, intent)
        expected_tool_name = self._find_expected_tool(scoped_tools)
        tool_map = {str(tool.get("name", "")): tool for tool in scoped_tools}
        return ScopedCatalog(
            intent=intent,
            all_tools=all_tools,
            scoped_tools=scoped_tools,
            expected_tool_name=expected_tool_name,
            tool_map=tool_map,
        )

    @staticmethod
    def _scope_context(catalog: ScopedCatalog) -> Dict[str, Any]:
        return {
            "intent": catalog.intent,
            "catalog_tool_count": len(catalog.all_tools),
            "scoped_tool_count": len(catalog.scoped_tools),
        }

    def _failure_result(
        self,
        *,
        intake: Dict[str, Any],
        failure_reason: str,
        selection: Dict[str, str],
        catalog: ScopedCatalog | None = None,
        tool_payload: Dict[str, Any] | None = None,
    ) -> FailureResult:
        scope = (
            ToolFlowScope(
                intent=catalog.intent,
                scoped_tool_count=len(catalog.scoped_tools),
                catalog_tool_count=len(catalog.all_tools),
            )
            if catalog is not None
            else ToolFlowScope(intent=str(intake.get("intent", "general_triage")), scoped_tool_count=0)
        )
        result: FailureResult = flow_failure(
            selection=selection,
            issue_key=intake["issue_key"],
            reason=failure_reason,
            scope=scope,
        )
        if catalog is None:
            result.pop("scope", None)
        else:
            result["scope"] = self._scope_context(catalog)
        if tool_payload is not None:
            result["tool_payload"] = tool_payload
        return result

    def _select_tool(
        self,
        request_text: str,
        issue_key: str,
        tools: List[Dict[str, Any]],
        expected_tool_name: str,
        dry_run: bool = False,
    ) -> Dict[str, str]:
        if dry_run:
            return {"tool": expected_tool_name, "reason": "dry_run"}

        tool_list = "\n".join([f"- {tool['name']}: {tool.get('description', '')}" for tool in tools])
        prompt = (
            "You are selecting one MCP tool for a Jira workflow.\n"
            f"Request: {request_text}\n"
            f"Issue key: {issue_key}\n"
            "Choose exactly one tool name from the provided list.\n"
            "Return strict JSON: {\"tool\":\"<name>\",\"reason\":\"<short reason>\"}.\n"
            "Tool list:\n"
            f"{tool_list}"
        )

        client = boto3.client("bedrock-runtime", region_name=self._region)
        response = client.converse(
            modelId=self._model_id,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"temperature": 0.2, "maxTokens": 400},
        )
        text_parts = [chunk.get("text", "") for chunk in response["output"]["message"]["content"] if "text" in chunk]
        payload = _extract_json("\n".join(text_parts))
        return {"tool": str(payload.get("tool", "")), "reason": str(payload.get("reason", ""))}

    def fetch_issue_with_selection(self, intake: Dict[str, Any], dry_run: bool = False) -> Dict[str, Any]:
        intent = str(intake.get("intent", "general_triage"))
        try:
            catalog = self._build_scoped_catalog(intent=intent)
        except Exception as exc:  # noqa: BLE001 - failure should be scored, not throw
            failure_reason = f"mcp_catalog_error:{exc}"
            return self._failure_result(
                intake=intake,
                failure_reason=failure_reason,
                selection={"tool": "", "reason": failure_reason},
            )

        selection = self._select_tool(
            request_text=intake["request_text"],
            issue_key=intake["issue_key"],
            tools=catalog.scoped_tools,
            expected_tool_name=catalog.expected_tool_name,
            dry_run=dry_run,
        )

        selected_tool = selection["tool"]
        if selected_tool not in catalog.tool_map:
            return self._failure_result(
                intake=intake,
                failure_reason=f"selected_unknown_tool:{selected_tool}",
                selection=selection,
                catalog=catalog,
            )

        args = self._build_tool_arguments(selected_tool=catalog.tool_map[selected_tool], intake=intake)
        try:
            call_result = self._mcp_client.call_tool(tool_name=selected_tool, arguments=args)
            tool_payload = self._mcp_client.extract_json_payload(call_result)
        except Exception as exc:  # noqa: BLE001 - failure should be scored, not throw
            return self._failure_result(
                intake=intake,
                failure_reason=f"mcp_invocation_error:{exc}",
                selection=selection,
                catalog=catalog,
            )

        if selected_tool != catalog.expected_tool_name:
            return self._failure_result(
                intake=intake,
                failure_reason=f"selected_wrong_tool:{selected_tool}",
                selection=selection,
                catalog=catalog,
                tool_payload=tool_payload,
            )

        issue = tool_payload.get("result", tool_payload)
        if not isinstance(issue, dict) or not issue.get("key"):
            return self._failure_result(
                intake=intake,
                failure_reason="mcp_missing_issue_payload",
                selection=selection,
                catalog=catalog,
                tool_payload=tool_payload,
            )

        scope = ToolFlowScope(
            intent=catalog.intent,
            scoped_tool_count=len(catalog.scoped_tools),
            catalog_tool_count=len(catalog.all_tools),
        )
        success = flow_success(selection=selection, issue=issue, scope=scope)
        success["scope"] = self._scope_context(catalog)
        return success
