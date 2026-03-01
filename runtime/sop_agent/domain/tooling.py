from typing import Any, Dict, List

from .contracts import TOOL_COMPLETENESS_FIELDS_BY_OPERATION


def strip_target_prefix(tool_name: str) -> str:
    if "__" not in tool_name:
        return tool_name
    return tool_name.split("__", 1)[1]


def canonical_tool_operation(tool_name: str) -> str:
    name = strip_target_prefix(tool_name).strip()
    if name.startswith("jira_api_"):
        return name[len("jira_api_") :]
    if name.startswith("jira_"):
        return name[len("jira_") :]
    return name


def issue_payload_complete_for_tool(tool_result: Dict[str, Any], tool_name: str) -> bool:
    if not isinstance(tool_result, dict):
        return False

    operation = canonical_tool_operation(tool_name)
    required_fields = TOOL_COMPLETENESS_FIELDS_BY_OPERATION.get(operation, ["key"])
    for field in required_fields:
        value = tool_result.get(field)
        if field == "labels":
            if not isinstance(value, list):
                return False
            continue

        text = str(value).strip()
        if not text:
            return False
        if field == "status" and text.lower() in {"unknown", "none"}:
            return False
    return True


def build_tool_arguments(selected_tool: Dict[str, Any], issue_key: str, request_text: str) -> Dict[str, Any]:
    input_schema = selected_tool.get("inputSchema", {})
    required = input_schema.get("required", [])
    if not isinstance(required, list):
        required = []
    args: Dict[str, Any] = {}
    if "issue_key" in required:
        args["issue_key"] = issue_key
    if "query" in required:
        args["query"] = request_text
    return args


def scope_tools_by_intent(
    tools: List[Dict[str, Any]],
    intent: str,
    scope_by_intent: Dict[str, List[str]],
) -> List[Dict[str, Any]]:
    allowed = set(scope_by_intent.get(intent, scope_by_intent["general_triage"]))
    scoped = [tool for tool in tools if strip_target_prefix(str(tool.get("name", ""))) in allowed]
    if not scoped:
        raise RuntimeError(f"empty_scoped_tool_catalog:intent={intent}")
    return scoped
