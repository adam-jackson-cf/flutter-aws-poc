import time
from typing import Any, Dict

from common import (
    append_stage_metric,
    build_failure_issue,
    build_gateway_tool_args,
    call_gateway_tool,
    extract_gateway_tool_payload,
    find_expected_gateway_tool,
    list_gateway_tools,
    scope_gateway_tools_by_intent,
    selected_gateway_url,
    selected_model_id,
    selected_region,
    select_mcp_tool,
    strip_gateway_tool_prefix,
)


EXPECTED_TOOL = "jira_get_issue_by_key"


def handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    started = time.time()
    intake = event["intake"]
    intent = str(intake.get("intent", "general_triage"))

    model_id = selected_model_id(event)
    region = selected_region(event)
    gateway_url = selected_gateway_url(event)
    try:
        all_tools = list_gateway_tools(gateway_url=gateway_url, region=region)
        tools = scope_gateway_tools_by_intent(all_tools, intent)
        expected_tool = find_expected_gateway_tool(tools)
    except Exception as exc:  # noqa: BLE001 - failure should be scored, not crash the pipeline
        event["mcp_selection"] = {"selected_tool": "", "reason": f"mcp_gateway_error:{exc}"}
        event["tool_path"] = "mcp_gateway"
        event["tool_failure"] = True
        event["tool_result"] = build_failure_issue(intake["issue_key"], f"mcp_gateway_unavailable:{exc}")
        return append_stage_metric(
            event,
            "fetch_mcp",
            started,
            {
                "issue_key": intake["issue_key"],
                "selected_tool": "",
                "tool_failure": True,
                "catalog_tool_count": 0,
                "scoped_tool_count": 0,
            },
        )
    selection = select_mcp_tool(
        request_text=intake["request_text"],
        issue_key=intake["issue_key"],
        tools=tools,
        expected_tool=expected_tool,
        model_id=model_id,
        region=region,
        dry_run=bool(event.get("dry_run", False)),
    )

    selected_tool = selection["selected_tool"]
    tool_map = {str(tool.get("name", "")): tool for tool in tools}
    event["mcp_selection"] = selection
    event["tool_path"] = "mcp_gateway"
    event["mcp_scope"] = {
        "intent": intent,
        "scoped_tool_count": len(tools),
        "catalog_tool_count": len(all_tools),
    }

    if selected_tool not in tool_map:
        event["tool_failure"] = True
        event["tool_result"] = build_failure_issue(intake["issue_key"], f"selected_unknown_tool:{selected_tool}")
        return append_stage_metric(
            event,
            "fetch_mcp",
            started,
            {
                "issue_key": intake["issue_key"],
                "selected_tool": selected_tool,
                "tool_failure": True,
                "catalog_tool_count": len(all_tools),
                "scoped_tool_count": len(tools),
            },
        )

    args = build_gateway_tool_args(
        selected_tool=tool_map[selected_tool],
        issue_key=intake["issue_key"],
        request_text=intake["request_text"],
    )
    try:
        call_response = call_gateway_tool(
            gateway_url=gateway_url,
            region=region,
            tool_name=selected_tool,
            arguments=args,
        )
        tool_payload = extract_gateway_tool_payload(call_response)
    except Exception as exc:  # noqa: BLE001 - failure should be scored, not crash the pipeline
        event["tool_failure"] = True
        event["tool_result"] = build_failure_issue(intake["issue_key"], f"mcp_tool_call_error:{exc}")
        return append_stage_metric(
            event,
            "fetch_mcp",
            started,
            {
                "issue_key": intake["issue_key"],
                "selected_tool": selected_tool,
                "tool_failure": True,
                "catalog_tool_count": len(all_tools),
                "scoped_tool_count": len(tools),
            },
        )

    if strip_gateway_tool_prefix(selected_tool) != EXPECTED_TOOL:
        event["tool_failure"] = True
        event["tool_result"] = build_failure_issue(intake["issue_key"], f"selected_wrong_tool:{selected_tool}")
    else:
        issue = tool_payload.get("result", tool_payload)
        if not isinstance(issue, dict) or not issue.get("key"):
            event["tool_failure"] = True
            event["tool_result"] = build_failure_issue(intake["issue_key"], "mcp_gateway_missing_issue_payload")
        else:
            event["tool_result"] = issue
            event["tool_failure"] = False

    return append_stage_metric(
        event,
        "fetch_mcp",
        started,
        {
            "issue_key": intake["issue_key"],
            "selected_tool": selected_tool,
            "tool_failure": bool(event["tool_failure"]),
            "catalog_tool_count": len(all_tools),
            "scoped_tool_count": len(tools),
        },
    )
