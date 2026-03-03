import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List

from ..domain import NATIVE_TOOL_SCOPE_BY_INTENT, issue_payload_complete_for_tool
from .jira_native_sdk import JiraSdkClient
from .llm_gateway_invoke_client import invoke_llm_gateway
from .tool_flow_result import ToolFlowScope, flow_failure, flow_success

TOOL_SCOPE_BY_INTENT: Dict[str, List[str]] = NATIVE_TOOL_SCOPE_BY_INTENT


class StrandsNativeFlowError(RuntimeError):
    pass


def _extract_json(raw_text: str) -> Dict[str, Any]:
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise StrandsNativeFlowError("Native selector output did not contain JSON")
    candidate = raw_text[start : end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        repaired = re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", candidate)
        return json.loads(repaired)


@dataclass(frozen=True)
class SelectionResolution:
    selection: Dict[str, Any]
    selected_tool: str


@dataclass(frozen=True)
class NativeModelConfig:
    model_id: str
    region: str
    model_provider: str = "auto"
    provider_options: Dict[str, Any] | None = None


class StrandsNativeFlow:
    def __init__(
        self,
        jira_client: JiraSdkClient,
        config: NativeModelConfig,
    ) -> None:
        self._jira_client = jira_client
        self._model_id = config.model_id
        self._region = config.region
        self._model_provider = config.model_provider
        self._provider_options = config.provider_options

    @staticmethod
    def _status_snapshot(issue: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "key": issue["key"],
            "status": issue.get("status", "Unknown"),
            "updated": issue.get("updated", ""),
        }

    @staticmethod
    def _priority_context(issue: Dict[str, Any]) -> Dict[str, Any]:
        priority = issue.get("priority", "None")
        risk_band = (
            "high"
            if priority in {"Highest", "High", "Critical"}
            else "medium" if priority == "Medium" else "low"
        )
        return {"key": issue["key"], "priority": priority, "risk_band": risk_band}

    @staticmethod
    def _labels(issue: Dict[str, Any]) -> Dict[str, Any]:
        return {"key": issue["key"], "labels": issue.get("labels", [])}

    @staticmethod
    def _project_key(issue: Dict[str, Any]) -> Dict[str, Any]:
        key = issue.get("key", "")
        project_key = key.split("-", 1)[0] if "-" in key else ""
        return {"key": key, "project_key": project_key}

    @staticmethod
    def _updated(issue: Dict[str, Any]) -> Dict[str, Any]:
        return {"key": issue["key"], "updated": issue.get("updated", "")}

    def _invoke_native_tool(self, tool_name: str, intake: Dict[str, Any]) -> Dict[str, Any]:
        issue_key = intake["issue_key"]
        issue = self._jira_client.get_issue(issue_key)
        if tool_name == "jira_api_write_issue_followup_note":
            return self._jira_client.write_issue_followup_note(
                issue_key=issue_key,
                note_text=str(intake.get("request_text", "")),
            )
        read_handlers = {
            "jira_api_get_issue_by_key": lambda item: item,
            "jira_api_get_issue_status_snapshot": self._status_snapshot,
            "jira_api_get_issue_priority_context": self._priority_context,
            "jira_api_get_issue_labels": self._labels,
            "jira_api_get_issue_project_key": self._project_key,
            "jira_api_get_issue_update_timestamp": self._updated,
        }
        selected = read_handlers.get(tool_name)
        if selected is not None:
            return selected(issue)
        raise StrandsNativeFlowError(f"unsupported_native_tool:{tool_name}")

    @staticmethod
    def _tool_prompt_lines(scoped_names: List[str]) -> str:
        return "\n".join(f"- {name}" for name in scoped_names)

    def _select_tool(self, intake: Dict[str, Any], scoped_names: List[str], dry_run: bool) -> SelectionResolution:
        default_tool = scoped_names[0] if scoped_names else "jira_api_get_issue_by_key"
        if dry_run:
            return SelectionResolution(
                selection={"selected_tool": default_tool, "reason": "dry_run"},
                selected_tool=default_tool,
            )
        prompt = (
            "You are a reasoning-scope orchestration agent.\n"
            "The tool catalog is pre-filtered by capability bindings and task scope.\n"
            f"Request: {intake['request_text']}\n"
            f"Issue key: {intake['issue_key']}\n"
            "Choose exactly one tool name from the provided list.\n"
            'Return strict JSON only: {"tool":"<name>","reason":"<short reason>"}.\n'
            "Scoped tool list:\n"
            f"{self._tool_prompt_lines(scoped_names)}"
        )
        raw = invoke_llm_gateway(
            model_id=self._model_id,
            prompt=prompt,
            region=self._region,
            provider=self._model_provider,
            provider_options=self._provider_options,
        )
        parsed = _extract_json(raw)
        selected_tool = str(parsed.get("tool", ""))
        return SelectionResolution(
            selection={"selected_tool": selected_tool, "reason": str(parsed.get("reason", ""))},
            selected_tool=selected_tool,
        )

    def fetch_issue_with_agent(self, intake: Dict[str, Any], dry_run: bool = False) -> Dict[str, Any]:
        issue_key = intake["issue_key"]
        intent = str(intake.get("intent", "general_triage"))
        scoped_names = TOOL_SCOPE_BY_INTENT.get(intent, TOOL_SCOPE_BY_INTENT["general_triage"])
        scope = ToolFlowScope(intent=intent, scoped_tool_count=len(scoped_names))

        try:
            selection = self._select_tool(intake=intake, scoped_names=scoped_names, dry_run=dry_run)
        except Exception as exc:  # noqa: BLE001
            reason = f"native_agent_error:{exc}"
            return flow_failure(selection={"tool": "", "reason": reason}, issue_key=issue_key, reason=reason, scope=scope)

        if selection.selected_tool not in scoped_names:
            return flow_failure(
                selection={"tool": selection.selected_tool, "reason": str(selection.selection.get("reason", ""))},
                issue_key=issue_key,
                reason=f"selected_unknown_tool:{selection.selected_tool}",
                scope=scope,
            )

        try:
            issue_payload = self._invoke_native_tool(selection.selected_tool, intake)
        except Exception as exc:  # noqa: BLE001
            return flow_failure(
                selection={"tool": selection.selected_tool, "reason": str(selection.selection.get("reason", ""))},
                issue_key=issue_key,
                reason=f"native_tool_call_error:{exc}",
                scope=scope,
            )

        if not issue_payload_complete_for_tool(
            tool_result=issue_payload,
            tool_name=selection.selected_tool,
        ):
            return flow_failure(
                selection={"tool": selection.selected_tool, "reason": str(selection.selection.get("reason", ""))},
                issue_key=issue_key,
                reason="native_missing_issue_payload",
                scope=scope,
            )

        return flow_success(
            selection={"tool": selection.selected_tool, "reason": str(selection.selection.get("reason", ""))},
            issue=issue_payload,
            scope=scope,
        )
