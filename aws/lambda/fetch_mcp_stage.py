import time
from dataclasses import dataclass
from typing import Any, Dict

from mcp_gateway_client import call_gateway_tool, extract_gateway_tool_payload, list_gateway_tools
from runtime_config import selected_gateway_url, selected_model_id, selected_region
from stage_metrics import append_stage_metric
from tool_selection import (
    StageToolOutcome,
    StageToolScope,
    ToolSelectionRequest,
    ToolSelectorConfig,
    build_gateway_tool_args,
    find_expected_gateway_tool,
    select_mcp_tool,
    stage_tool_failure,
    stage_tool_success,
)
from tooling_domain import issue_payload_complete_for_tool, scope_gateway_tools_by_intent, strip_gateway_tool_prefix


@dataclass(frozen=True)
class McpCatalog:
    all_tools: list[Dict[str, Any]]
    scoped_tools: list[Dict[str, Any]]
    expected_tool: str
    tool_map: Dict[str, Dict[str, Any]]
    scope: StageToolScope


def _scope_from_catalog(intent: str, scoped_tools: list[Dict[str, Any]], all_tools: list[Dict[str, Any]]) -> StageToolScope:
    return StageToolScope(intent=intent, scoped_tool_count=len(scoped_tools), catalog_tool_count=len(all_tools))


def _build_scope(gateway_url: str, region: str, intent: str, expected_tool_unprefixed: str) -> McpCatalog:
    all_tools = list_gateway_tools(gateway_url=gateway_url, region=region)
    scoped_tools = scope_gateway_tools_by_intent(all_tools, intent)
    expected_tool = find_expected_gateway_tool(scoped_tools, unprefixed_tool_name=expected_tool_unprefixed)
    tool_map = {str(tool.get("name", "")): tool for tool in scoped_tools}
    return McpCatalog(
        all_tools=all_tools,
        scoped_tools=scoped_tools,
        expected_tool=expected_tool,
        tool_map=tool_map,
        scope=_scope_from_catalog(intent=intent, scoped_tools=scoped_tools, all_tools=all_tools),
    )


def _select_tool(intake: Dict[str, Any], model_id: str, region: str, catalog: McpCatalog, dry_run: bool) -> Dict[str, Any]:
    return select_mcp_tool(
        selection=ToolSelectionRequest(
            request_text=intake["request_text"],
            issue_key=intake["issue_key"],
            tools=catalog.scoped_tools,
            default_tool=catalog.expected_tool,
        ),
        config=ToolSelectorConfig(
            model_id=model_id,
            region=region,
            dry_run=dry_run,
        ),
    )


def _invoke_tool(gateway_url: str, region: str, selected_tool: str, intake: Dict[str, Any], catalog: McpCatalog) -> Dict[str, Any]:
    args = build_gateway_tool_args(
        selected_tool=catalog.tool_map[selected_tool],
        issue_key=intake["issue_key"],
        request_text=intake["request_text"],
    )
    call_response = call_gateway_tool(
        gateway_url=gateway_url,
        region=region,
        tool_name=selected_tool,
        arguments=args,
    )
    return extract_gateway_tool_payload(call_response)


def _validate_tool_payload(selected_tool: str, expected_tool_unprefixed: str, tool_payload: Dict[str, Any], issue_key: str, scope: StageToolScope, selection: Dict[str, Any]) -> StageToolOutcome:
    if strip_gateway_tool_prefix(selected_tool) != expected_tool_unprefixed:
        return stage_tool_failure(
            issue_key=issue_key,
            reason=f"selected_wrong_tool:{selected_tool}",
            selection=selection,
            scope=scope,
        )
    issue = tool_payload.get("result", tool_payload)
    if not issue_payload_complete_for_tool(issue, expected_tool_unprefixed):
        return stage_tool_failure(
            issue_key=issue_key,
            reason="mcp_gateway_missing_issue_payload",
            selection=selection,
            scope=scope,
        )
    return stage_tool_success(
        tool_result=issue,
        selection=selection,
        scope=scope,
    )


def _metric_result(event: Dict[str, Any], started: float, issue_key: str, selected_tool: str, outcome: StageToolOutcome) -> Dict[str, Any]:
    return append_stage_metric(
        event,
        "fetch_mcp",
        started,
        {
            "issue_key": issue_key,
            "selected_tool": selected_tool,
            "tool_failure": outcome.tool_failure,
            "catalog_tool_count": outcome.scope.catalog_tool_count,
            "scoped_tool_count": outcome.scope.scoped_tool_count,
        },
    )


def _apply_outcome(event: Dict[str, Any], outcome: StageToolOutcome, set_scope: bool) -> None:
    event["mcp_selection"] = outcome.selection
    event["tool_path"] = "mcp_gateway"
    event["tool_failure"] = outcome.tool_failure
    event["tool_result"] = outcome.tool_result
    if set_scope:
        event["mcp_scope"] = {
            "intent": outcome.scope.intent,
            "scoped_tool_count": outcome.scope.scoped_tool_count,
            "catalog_tool_count": outcome.scope.catalog_tool_count,
        }


def handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    started = time.time()
    intake = event["intake"]
    intent = str(intake.get("intent", "general_triage"))
    expected_tool_unprefixed = str(event.get("expected_tool", "")).strip()
    if not expected_tool_unprefixed:
        outcome = stage_tool_failure(
            issue_key=intake["issue_key"],
            reason="expected_tool_missing",
            selection={"selected_tool": "", "reason": "expected_tool_missing"},
            scope=StageToolScope(intent=intent, scoped_tool_count=0, catalog_tool_count=0),
        )
        _apply_outcome(event, outcome, set_scope=False)
        return _metric_result(event, started, intake["issue_key"], "", outcome)

    model_id = selected_model_id(event)
    region = selected_region(event)
    gateway_url = selected_gateway_url(event)
    try:
        catalog = _build_scope(
            gateway_url=gateway_url,
            region=region,
            intent=intent,
            expected_tool_unprefixed=expected_tool_unprefixed,
        )
    except Exception as exc:  # noqa: BLE001 - failure should be scored, not crash the pipeline
        reason = f"mcp_gateway_unavailable:{exc}"
        outcome = stage_tool_failure(
            issue_key=intake["issue_key"],
            reason=reason,
            selection={"selected_tool": "", "reason": f"mcp_gateway_error:{exc}"},
            scope=StageToolScope(intent=intent, scoped_tool_count=0, catalog_tool_count=0),
        )
        _apply_outcome(event, outcome, set_scope=False)
        return _metric_result(event, started, intake["issue_key"], "", outcome)

    selection = _select_tool(
        intake=intake,
        model_id=model_id,
        region=region,
        catalog=catalog,
        dry_run=bool(event.get("dry_run", False)),
    )
    selected_tool = str(selection.get("selected_tool", ""))

    if selected_tool not in catalog.tool_map:
        outcome = stage_tool_failure(
            issue_key=intake["issue_key"],
            reason=f"selected_unknown_tool:{selected_tool}",
            selection=selection,
            scope=catalog.scope,
        )
        _apply_outcome(event, outcome, set_scope=True)
        return _metric_result(event, started, intake["issue_key"], selected_tool, outcome)

    try:
        tool_payload = _invoke_tool(
            gateway_url=gateway_url,
            region=region,
            selected_tool=selected_tool,
            intake=intake,
            catalog=catalog,
        )
    except Exception as exc:  # noqa: BLE001 - failure should be scored, not crash the pipeline
        outcome = stage_tool_failure(
            issue_key=intake["issue_key"],
            reason=f"mcp_tool_call_error:{exc}",
            selection=selection,
            scope=catalog.scope,
        )
        _apply_outcome(event, outcome, set_scope=True)
        return _metric_result(event, started, intake["issue_key"], selected_tool, outcome)

    outcome = _validate_tool_payload(
        selected_tool=selected_tool,
        expected_tool_unprefixed=expected_tool_unprefixed,
        tool_payload=tool_payload,
        issue_key=intake["issue_key"],
        scope=catalog.scope,
        selection=selection,
    )
    _apply_outcome(event, outcome, set_scope=True)
    return _metric_result(event, started, intake["issue_key"], selected_tool, outcome)
