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


@dataclass(frozen=True)
class McpRunContext:
    event: Dict[str, Any]
    started: float
    issue_key: str
    selected_tool: str
    set_scope: bool


@dataclass(frozen=True)
class ValidationInput:
    selected_tool: str
    expected_tool_unprefixed: str
    tool_payload: Dict[str, Any]
    issue_key: str
    scope: StageToolScope
    selection: Dict[str, Any]


def _run_context(
    event: Dict[str, Any],
    started: float,
    issue_key: str,
    selected_tool: str,
    set_scope: bool,
) -> McpRunContext:
    return McpRunContext(
        event=event,
        started=started,
        issue_key=issue_key,
        selected_tool=selected_tool,
        set_scope=set_scope,
    )


def _empty_scope(intent: str) -> StageToolScope:
    return StageToolScope(intent=intent, scoped_tool_count=0, catalog_tool_count=0)


def _missing_expected_tool_result(run_context: McpRunContext, intent: str) -> Dict[str, Any]:
    return _failed_result(
        run_context,
        reason="expected_tool_missing",
        selection={"selected_tool": "", "reason": "expected_tool_missing"},
        scope=_empty_scope(intent),
    )


def _gateway_unavailable_result(
    run_context: McpRunContext,
    intent: str,
    exc: Exception,
) -> Dict[str, Any]:
    return _failed_result(
        run_context,
        reason=f"mcp_gateway_unavailable:{exc}",
        selection={"selected_tool": "", "reason": f"mcp_gateway_error:{exc}"},
        scope=_empty_scope(intent),
    )


def _unknown_selected_tool_result(
    run_context: McpRunContext,
    selection: Dict[str, Any],
    scope: StageToolScope,
) -> Dict[str, Any]:
    return _failed_result(
        run_context,
        reason=f"selected_unknown_tool:{run_context.selected_tool}",
        selection=selection,
        scope=scope,
    )


def _tool_call_error_result(
    run_context: McpRunContext,
    selection: Dict[str, Any],
    scope: StageToolScope,
    exc: Exception,
) -> Dict[str, Any]:
    return _failed_result(
        run_context,
        reason=f"mcp_tool_call_error:{exc}",
        selection=selection,
        scope=scope,
    )


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


def _validate_tool_payload(validation: ValidationInput) -> StageToolOutcome:
    if strip_gateway_tool_prefix(validation.selected_tool) != validation.expected_tool_unprefixed:
        return stage_tool_failure(
            issue_key=validation.issue_key,
            reason=f"selected_wrong_tool:{validation.selected_tool}",
            selection=validation.selection,
            scope=validation.scope,
        )
    issue = validation.tool_payload.get("result", validation.tool_payload)
    if not issue_payload_complete_for_tool(issue, validation.expected_tool_unprefixed):
        return stage_tool_failure(
            issue_key=validation.issue_key,
            reason="mcp_gateway_missing_issue_payload",
            selection=validation.selection,
            scope=validation.scope,
        )
    return stage_tool_success(
        tool_result=issue,
        selection=validation.selection,
        scope=validation.scope,
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


def _finalize(
    run_context: McpRunContext,
    outcome: StageToolOutcome,
) -> Dict[str, Any]:
    _apply_outcome(run_context.event, outcome, set_scope=run_context.set_scope)
    return _metric_result(
        run_context.event,
        run_context.started,
        run_context.issue_key,
        run_context.selected_tool,
        outcome,
    )


def _failed_result(
    run_context: McpRunContext,
    reason: str,
    selection: Dict[str, Any],
    scope: StageToolScope,
) -> Dict[str, Any]:
    outcome = stage_tool_failure(
        issue_key=run_context.issue_key,
        reason=reason,
        selection=selection,
        scope=scope,
    )
    return _finalize(run_context, outcome)


def _run_handler(event: Dict[str, Any], started: float) -> Dict[str, Any]:
    intake = event["intake"]
    intent = str(intake.get("intent", "general_triage"))
    issue_key = intake["issue_key"]
    expected_tool_unprefixed = str(event.get("expected_tool", "")).strip()
    initial_context = _run_context(event=event, started=started, issue_key=issue_key, selected_tool="", set_scope=False)
    if not expected_tool_unprefixed:
        return _missing_expected_tool_result(run_context=initial_context, intent=intent)

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
        return _gateway_unavailable_result(
            run_context=initial_context,
            intent=intent,
            exc=exc,
        )

    selection = _select_tool(
        intake=intake,
        model_id=model_id,
        region=region,
        catalog=catalog,
        dry_run=bool(event.get("dry_run", False)),
    )
    selected_tool = str(selection.get("selected_tool", ""))
    selected_context = _run_context(
        event=event,
        started=started,
        issue_key=issue_key,
        selected_tool=selected_tool,
        set_scope=True,
    )

    if selected_tool not in catalog.tool_map:
        return _unknown_selected_tool_result(
            run_context=selected_context,
            selection=selection,
            scope=catalog.scope,
        )

    try:
        tool_payload = _invoke_tool(
            gateway_url=gateway_url,
            region=region,
            selected_tool=selected_tool,
            intake=intake,
            catalog=catalog,
        )
    except Exception as exc:  # noqa: BLE001 - failure should be scored, not crash the pipeline
        return _tool_call_error_result(
            run_context=selected_context,
            selection=selection,
            scope=catalog.scope,
            exc=exc,
        )

    outcome = _validate_tool_payload(
        ValidationInput(
            selected_tool=selected_tool,
            expected_tool_unprefixed=expected_tool_unprefixed,
            tool_payload=tool_payload,
            issue_key=issue_key,
            scope=catalog.scope,
            selection=selection,
        )
    )
    return _finalize(selected_context, outcome)


def handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    return _run_handler(event, started=time.time())
