import json
import re
from typing import Any, Dict, List

import boto3

from .agentcore_mcp_client import AgentCoreMcpClient, AgentCoreMcpClientError
from .jira_native_sdk import JiraSdkClient

EXPECTED_TOOL = "jira_get_issue_by_key"
TOOL_SCOPE_BY_INTENT: Dict[str, List[str]] = {
    "bug_triage": ["jira_get_issue_by_key", "jira_get_issue_priority_context", "jira_get_issue_risk_flags"],
    "status_update": ["jira_get_issue_by_key", "jira_get_issue_status_snapshot", "jira_get_issue_update_timestamp"],
    "feature_request": ["jira_get_issue_by_key", "jira_get_issue_labels", "jira_get_issue_project_key"],
    "general_triage": ["jira_get_issue_by_key", "jira_get_issue_status_snapshot"],
}


class McpSelectionError(RuntimeError):
    pass


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
        if "__" not in tool_name:
            return tool_name
        return re.split(r"__+", tool_name, maxsplit=1)[1]

    def _find_expected_tool(self, tools: List[Dict[str, Any]]) -> str:
        for tool in tools:
            name = str(tool.get("name", ""))
            if self._strip_target_prefix(name) == EXPECTED_TOOL:
                return name
        raise McpSelectionError(f"Expected MCP tool {EXPECTED_TOOL} not found in gateway catalog")

    def _scope_tools_for_intent(self, tools: List[Dict[str, Any]], intent: str) -> List[Dict[str, Any]]:
        allowed = set(TOOL_SCOPE_BY_INTENT.get(intent, TOOL_SCOPE_BY_INTENT["general_triage"]))
        scoped = [tool for tool in tools if self._strip_target_prefix(str(tool.get("name", ""))) in allowed]
        if not scoped:
            raise McpSelectionError(f"No MCP tools available after scoping for intent={intent}")
        return scoped

    @staticmethod
    def _build_tool_arguments(selected_tool: Dict[str, Any], intake: Dict[str, Any]) -> Dict[str, Any]:
        input_schema = selected_tool.get("inputSchema", {})
        required = input_schema.get("required", [])
        if not isinstance(required, list):
            required = []
        args: Dict[str, Any] = {}
        if "issue_key" in required:
            args["issue_key"] = intake["issue_key"]
        if "query" in required:
            args["query"] = intake["request_text"]
        return args

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
            all_tools = self._mcp_client.list_tools()
            tools = self._scope_tools_for_intent(all_tools, intent)
            expected_tool_name = self._find_expected_tool(tools)
            tool_map = {str(tool.get("name", "")): tool for tool in tools}
        except Exception as exc:  # noqa: BLE001 - failure should be scored, not throw
            return {
                "selection": {"tool": "", "reason": f"mcp_catalog_error:{exc}"},
                "tool_failure": True,
                "issue": {
                    "key": intake["issue_key"],
                    "summary": "",
                    "status": "Unknown",
                    "issue_type": "Unknown",
                    "priority": "None",
                    "labels": [],
                    "updated": "",
                    "description": "",
                    "comment_count": 0,
                    "failure_reason": f"mcp_catalog_error:{exc}",
                },
            }

        selection = self._select_tool(
            request_text=intake["request_text"],
            issue_key=intake["issue_key"],
            tools=tools,
            expected_tool_name=expected_tool_name,
            dry_run=dry_run,
        )

        selected_tool = selection["tool"]
        if selected_tool not in tool_map:
            return {
                "selection": selection,
                "tool_failure": True,
                "issue": {
                    "key": intake["issue_key"],
                    "summary": "",
                    "status": "Unknown",
                    "issue_type": "Unknown",
                    "priority": "None",
                    "labels": [],
                    "updated": "",
                    "description": "",
                    "comment_count": 0,
                    "failure_reason": f"selected_unknown_tool:{selected_tool}",
                },
                "scope": {
                    "intent": intent,
                    "catalog_tool_count": len(all_tools),
                    "scoped_tool_count": len(tools),
                },
            }

        args = self._build_tool_arguments(selected_tool=tool_map[selected_tool], intake=intake)
        try:
            call_result = self._mcp_client.call_tool(tool_name=selected_tool, arguments=args)
            tool_payload = self._mcp_client.extract_json_payload(call_result)
        except Exception as exc:  # noqa: BLE001 - failure should be scored, not throw
            return {
                "selection": selection,
                "tool_failure": True,
                "issue": {
                    "key": intake["issue_key"],
                    "summary": "",
                    "status": "Unknown",
                    "issue_type": "Unknown",
                    "priority": "None",
                    "labels": [],
                    "updated": "",
                    "description": "",
                    "comment_count": 0,
                    "failure_reason": f"mcp_invocation_error:{exc}",
                },
                "scope": {
                    "intent": intent,
                    "catalog_tool_count": len(all_tools),
                    "scoped_tool_count": len(tools),
                },
            }

        if selected_tool != expected_tool_name:
            return {
                "selection": selection,
                "tool_failure": True,
                "issue": {
                    "key": intake["issue_key"],
                    "summary": "",
                    "status": "Unknown",
                    "issue_type": "Unknown",
                    "priority": "None",
                    "labels": [],
                    "updated": "",
                    "description": "",
                    "comment_count": 0,
                    "failure_reason": f"selected_wrong_tool:{selected_tool}",
                },
                "tool_payload": tool_payload,
                "scope": {
                    "intent": intent,
                    "catalog_tool_count": len(all_tools),
                    "scoped_tool_count": len(tools),
                },
            }

        issue = tool_payload.get("result", tool_payload)
        if not isinstance(issue, dict) or not issue.get("key"):
            return {
                "selection": selection,
                "tool_failure": True,
                "issue": {
                    "key": intake["issue_key"],
                    "summary": "",
                    "status": "Unknown",
                    "issue_type": "Unknown",
                    "priority": "None",
                    "labels": [],
                    "updated": "",
                    "description": "",
                    "comment_count": 0,
                    "failure_reason": "mcp_missing_issue_payload",
                },
                "tool_payload": tool_payload,
                "scope": {
                    "intent": intent,
                    "catalog_tool_count": len(all_tools),
                    "scoped_tool_count": len(tools),
                },
            }

        return {
            "selection": selection,
            "tool_failure": False,
            "issue": issue,
            "scope": {
                "intent": intent,
                "catalog_tool_count": len(all_tools),
                "scoped_tool_count": len(tools),
            },
        }
