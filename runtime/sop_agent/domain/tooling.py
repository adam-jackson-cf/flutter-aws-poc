from typing import Any, Dict

from .contracts import TOOL_COMPLETENESS_FIELDS_BY_OPERATION


def strip_target_prefix(tool_name: str) -> str:
    if "___" in tool_name:
        return tool_name.split("___", 1)[1]
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
