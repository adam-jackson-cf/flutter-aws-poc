import json
import re
from typing import Any, Dict, List

from strands import Agent, tool
from strands.models import BedrockModel

from .jira_native_sdk import JiraSdkClient
from .tool_flow_result import ToolFlowScope, flow_failure, flow_success


class StrandsNativeFlowError(RuntimeError):
    pass


EXPECTED_TOOL = "jira_api_get_issue_by_key"
TOOL_SCOPE_BY_INTENT: Dict[str, List[str]] = {
    "bug_triage": ["jira_api_get_issue_by_key", "jira_api_get_issue_priority_context", "jira_api_get_issue_status_snapshot"],
    "status_update": ["jira_api_get_issue_by_key", "jira_api_get_issue_status_snapshot", "jira_api_get_issue_update_timestamp"],
    "feature_request": ["jira_api_get_issue_by_key", "jira_api_get_issue_labels", "jira_api_get_issue_project_key"],
    "general_triage": ["jira_api_get_issue_by_key", "jira_api_get_issue_status_snapshot"],
}


def _extract_json(raw_text: str) -> Dict[str, Any]:
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise StrandsNativeFlowError("Strands output did not contain JSON")
    candidate = raw_text[start : end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        repaired = re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", candidate)
        return json.loads(repaired)


class StrandsNativeFlow:
    def __init__(self, jira_client: JiraSdkClient, model_id: str, region: str) -> None:
        self._jira_client = jira_client
        self._model_id = model_id
        self._region = region

    def _scoped_native_tools(self, scoped_names: List[str]) -> List[Any]:
        @tool
        def jira_api_get_issue_by_key(issue_key: str) -> dict:
            """Fetch full public Jira issue payload by issue key via native API client."""
            return self._jira_client.get_issue(issue_key)

        @tool
        def jira_api_get_issue_status_snapshot(issue_key: str) -> dict:
            """Fetch issue status and updated timestamp via native API client."""
            issue = self._jira_client.get_issue(issue_key)
            return {"key": issue["key"], "status": issue.get("status", "Unknown"), "updated": issue.get("updated", "")}

        @tool
        def jira_api_get_issue_priority_context(issue_key: str) -> dict:
            """Fetch issue priority and risk band via native API client."""
            issue = self._jira_client.get_issue(issue_key)
            priority = issue.get("priority", "None")
            risk_band = "high" if priority in {"Highest", "High", "Critical"} else "medium" if priority == "Medium" else "low"
            return {"key": issue["key"], "priority": priority, "risk_band": risk_band}

        @tool
        def jira_api_get_issue_labels(issue_key: str) -> dict:
            """Fetch issue labels via native API client."""
            issue = self._jira_client.get_issue(issue_key)
            return {"key": issue["key"], "labels": issue.get("labels", [])}

        @tool
        def jira_api_get_issue_project_key(issue_key: str) -> dict:
            """Fetch project key derived from issue key via native API client."""
            issue = self._jira_client.get_issue(issue_key)
            key = issue.get("key", "")
            project_key = key.split("-", 1)[0] if "-" in key else ""
            return {"key": key, "project_key": project_key}

        @tool
        def jira_api_get_issue_update_timestamp(issue_key: str) -> dict:
            """Fetch issue update timestamp via native API client."""
            issue = self._jira_client.get_issue(issue_key)
            return {"key": issue["key"], "updated": issue.get("updated", "")}

        tool_functions = {
            "jira_api_get_issue_by_key": jira_api_get_issue_by_key,
            "jira_api_get_issue_status_snapshot": jira_api_get_issue_status_snapshot,
            "jira_api_get_issue_priority_context": jira_api_get_issue_priority_context,
            "jira_api_get_issue_labels": jira_api_get_issue_labels,
            "jira_api_get_issue_project_key": jira_api_get_issue_project_key,
            "jira_api_get_issue_update_timestamp": jira_api_get_issue_update_timestamp,
        }
        return [tool_functions[name] for name in scoped_names]

    def _run_selection_agent(self, intake: Dict[str, Any], scoped_tools: List[Any]) -> Dict[str, Any]:
        model = BedrockModel(
            model_id=self._model_id,
            region_name=self._region,
            temperature=0.1,
            max_tokens=1200,
        )

        agent = Agent(
            model=model,
            tools=scoped_tools,
            system_prompt=(
                "You are a reasoning-scope support orchestration agent. "
                "The tool list is pre-scoped by capability bindings and task intent. "
                "Use exactly one tool call and return strict JSON only."
            ),
        )

        prompt = (
            "Select one tool from the scoped native API tool list and call it with issue_key. "
            "Return strict JSON: "
            '{"selected_tool":"<tool>","reason":"<short reason>","issue":{...tool output...}}. '
            f"Intake: {json.dumps(intake)}"
        )

        result = agent(prompt)
        payload = result.to_dict()
        text_blocks = [block.get("text", "") for block in payload["message"]["content"] if "text" in block]
        return _extract_json("\n".join(text_blocks))

    @staticmethod
    def _validate_agent_result(parsed: Dict[str, Any], *, issue_key: str, scoped_names: List[str], scope: ToolFlowScope) -> Dict[str, Any]:
        selected_tool = str(parsed.get("selected_tool", ""))
        issue = parsed.get("issue")
        if selected_tool not in scoped_names:
            return flow_failure(
                selection={"tool": selected_tool, "reason": str(parsed.get("reason", ""))},
                issue_key=issue_key,
                reason=f"selected_unknown_tool:{selected_tool}",
                scope=scope,
            )
        if selected_tool != EXPECTED_TOOL:
            return flow_failure(
                selection={"tool": selected_tool, "reason": str(parsed.get("reason", ""))},
                issue_key=issue_key,
                reason=f"selected_wrong_tool:{selected_tool}",
                scope=scope,
            )
        if not isinstance(issue, dict) or not issue.get("key"):
            return flow_failure(
                selection={"tool": selected_tool, "reason": str(parsed.get("reason", ""))},
                issue_key=issue_key,
                reason="native_missing_issue_payload",
                scope=scope,
            )

        return flow_success(
            selection={"tool": selected_tool, "reason": str(parsed.get("reason", "native_agent_tool_choice"))},
            issue=issue,
            scope=scope,
        )

    def fetch_issue_with_agent(self, intake: Dict[str, Any], dry_run: bool = False) -> Dict[str, Any]:
        issue_key = intake["issue_key"]
        intent = str(intake.get("intent", "general_triage"))
        scoped_names = TOOL_SCOPE_BY_INTENT.get(intent, TOOL_SCOPE_BY_INTENT["general_triage"])
        scope = ToolFlowScope(intent=intent, scoped_tool_count=len(scoped_names))
        if dry_run:
            issue = self._jira_client.get_issue(issue_key)
            return flow_success(selection={"tool": EXPECTED_TOOL, "reason": "dry_run"}, issue=issue, scope=scope)

        scoped_tools = self._scoped_native_tools(scoped_names)
        try:
            parsed = self._run_selection_agent(intake=intake, scoped_tools=scoped_tools)
        except Exception as exc:  # noqa: BLE001
            reason = f"native_agent_error:{exc}"
            return flow_failure(selection={"tool": "", "reason": reason}, issue_key=issue_key, reason=reason, scope=scope)
        return self._validate_agent_result(parsed=parsed, issue_key=issue_key, scoped_names=scoped_names, scope=scope)
