import os
import time
from dataclasses import dataclass
from typing import Any, Dict

from mcp_gateway_client import call_gateway_tool, extract_gateway_tool_payload, list_gateway_tools
from runtime_config import selected_gateway_url, selected_model_id, selected_model_provider, selected_provider_options, selected_region
from stage_metrics import append_stage_metric
from tool_selection import (
    StageToolOutcome,
    StageToolScope,
    ToolSelectionRequest,
    ToolSelectorConfig,
    select_mcp_tool_call,
    stage_tool_failure,
    stage_tool_success,
    validate_gateway_tool_arguments,
)
from tooling_domain import issue_payload_complete_for_tool, scope_gateway_tools_by_intent, strip_gateway_tool_prefix


@dataclass(frozen=True)
class McpCatalog:
    all_tools: list[Dict[str, Any]]
    scoped_tools: list[Dict[str, Any]]
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
    tool_payload: Dict[str, Any]
    issue_key: str
    scope: StageToolScope
    selection: Dict[str, Any]


@dataclass(frozen=True)
class SelectionResolution:
    selection: Dict[str, Any]
    selected_tool: str
    selected_arguments: Dict[str, Any]
    attempts: int
    construction_failures: int
    failure_reason: str
    attempt_trace: list[Dict[str, Any]]


@dataclass(frozen=True)
class SelectorRuntimeConfig:
    model_id: str
    region: str
    dry_run: bool
    model_provider: str
    provider_options: Dict[str, Dict[str, Any]]


@dataclass(frozen=True)
class ResolutionInput:
    selection: Dict[str, Any]
    selected_tool: str
    selected_arguments: Dict[str, Any]
    attempts: int
    construction_failures: int
    llm_usage_totals: Dict[str, int]
    attempt_trace: list[Dict[str, Any]]
    failure_reason: str


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


def _build_scope(gateway_url: str, region: str, intent: str) -> McpCatalog:
    all_tools = list_gateway_tools(gateway_url=gateway_url, region=region)
    scoped_tools = scope_gateway_tools_by_intent(all_tools, intent)
    tool_map = {str(tool.get("name", "")): tool for tool in scoped_tools}
    return McpCatalog(
        all_tools=all_tools,
        scoped_tools=scoped_tools,
        tool_map=tool_map,
        scope=_scope_from_catalog(intent=intent, scoped_tools=scoped_tools, all_tools=all_tools),
    )


def _select_tool(
    intake: Dict[str, Any],
    catalog: McpCatalog,
    runtime_config: SelectorRuntimeConfig,
    retry_feedback: str = "",
) -> Dict[str, Any]:
    default_tool = str(catalog.scoped_tools[0].get("name", "jira_get_issue_by_key")) if catalog.scoped_tools else "jira_get_issue_by_key"
    return select_mcp_tool_call(
        selection=ToolSelectionRequest(
            request_text=intake["request_text"],
            issue_key=intake["issue_key"],
            tools=catalog.scoped_tools,
            default_tool=default_tool,
            retry_feedback=retry_feedback,
        ),
        config=ToolSelectorConfig(
            model_id=runtime_config.model_id,
            region=runtime_config.region,
            dry_run=runtime_config.dry_run,
            model_provider=runtime_config.model_provider,
            provider_options=runtime_config.provider_options,
        ),
    )


def _parse_max_attempts(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError("mcp_call_construction_max_attempts_invalid") from exc
    if parsed < 1:
        raise ValueError("mcp_call_construction_max_attempts_invalid")
    return parsed


def _max_call_construction_attempts() -> int:
    raw = str(os.environ.get("MCP_CALL_CONSTRUCTION_MAX_ATTEMPTS", "2")).strip() or "2"
    return _parse_max_attempts(raw)


def _selection_with_construction(
    selection: Dict[str, Any],
    attempts: int,
    construction_failures: int,
    llm_usage: Dict[str, int],
    attempt_trace: list[Dict[str, Any]],
) -> Dict[str, Any]:
    enriched = dict(selection)
    enriched["construction_attempts"] = attempts
    enriched["construction_retries"] = max(0, attempts - 1)
    enriched["construction_failures"] = construction_failures
    enriched["llm_input_tokens"] = _safe_int(llm_usage.get("input_tokens", 0))
    enriched["llm_output_tokens"] = _safe_int(llm_usage.get("output_tokens", 0))
    enriched["llm_total_tokens"] = _safe_int(llm_usage.get("total_tokens", 0))
    enriched["construction_attempt_trace"] = attempt_trace
    enriched["construction_attempt_trace_map"] = {
        f"attempt_{entry.get('attempt', index)}": {
            "tool": str(entry.get("tool", "")),
            "arg_errors": str(entry.get("arg_errors", "")),
            "status": str(entry.get("status", "")),
        }
        for index, entry in enumerate(attempt_trace, start=1)
    }
    return enriched


def _safe_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return 0
    return 0


def _selection_llm_usage(selection: Dict[str, Any]) -> Dict[str, int]:
    source = selection.get("llm_usage", {})
    if not isinstance(source, dict):
        source = {}
    return {
        "input_tokens": max(0, _safe_int(source.get("input_tokens", 0))),
        "output_tokens": max(0, _safe_int(source.get("output_tokens", 0))),
        "total_tokens": max(0, _safe_int(source.get("total_tokens", 0))),
    }


def _merge_usage(total: Dict[str, int], delta: Dict[str, int]) -> Dict[str, int]:
    return {
        "input_tokens": max(0, _safe_int(total.get("input_tokens", 0)) + _safe_int(delta.get("input_tokens", 0))),
        "output_tokens": max(0, _safe_int(total.get("output_tokens", 0)) + _safe_int(delta.get("output_tokens", 0))),
        "total_tokens": max(0, _safe_int(total.get("total_tokens", 0)) + _safe_int(delta.get("total_tokens", 0))),
    }


def _selection_attempt(
    *,
    intake: Dict[str, Any],
    catalog: McpCatalog,
    runtime_config: SelectorRuntimeConfig,
    retry_feedback: str,
) -> tuple[Dict[str, Any], str, Dict[str, Any], Dict[str, int]]:
    selection = _select_tool(
        intake=intake,
        catalog=catalog,
        runtime_config=runtime_config,
        retry_feedback=retry_feedback,
    )
    selected_tool = str(selection.get("selected_tool", ""))
    selected_arguments = selection.get("arguments", {})
    if not isinstance(selected_arguments, dict):
        selected_arguments = {}
    return selection, selected_tool, selected_arguments, _selection_llm_usage(selection)


def _invalid_retry_feedback(error: str) -> str:
    return (
        f"Previous attempt invalid: {error}. "
        "Return arguments that match the tool input schema exactly."
    )


def _unknown_tool_retry_feedback(error: str) -> str:
    return (
        f"Previous attempt invalid: {error}. "
        "Choose one tool from the scoped list and provide valid arguments."
    )


def _invalid_trace_entry(
    *,
    attempts: int,
    selected_tool: str,
    error: str,
) -> Dict[str, Any]:
    return {
        "attempt": attempts,
        "tool": selected_tool,
        "arg_errors": error,
        "status": "invalid",
    }


def _valid_trace_entry(attempts: int, selected_tool: str) -> Dict[str, Any]:
    return {
        "attempt": attempts,
        "tool": selected_tool,
        "arg_errors": "",
        "status": "valid",
    }


def _selection_resolution(resolution_input: ResolutionInput) -> SelectionResolution:
    return SelectionResolution(
        selection=_selection_with_construction(
            resolution_input.selection,
            attempts=resolution_input.attempts,
            construction_failures=resolution_input.construction_failures,
            llm_usage=resolution_input.llm_usage_totals,
            attempt_trace=resolution_input.attempt_trace,
        ),
        selected_tool=resolution_input.selected_tool,
        selected_arguments=resolution_input.selected_arguments,
        attempts=resolution_input.attempts,
        construction_failures=resolution_input.construction_failures,
        failure_reason=resolution_input.failure_reason,
        attempt_trace=resolution_input.attempt_trace,
    )


def _resolve_tool_call_selection(
    intake: Dict[str, Any],
    catalog: McpCatalog,
    runtime_config: SelectorRuntimeConfig,
) -> SelectionResolution:
    max_attempts = _max_call_construction_attempts()
    attempts = 0
    construction_failures = 0
    retry_feedback = ""
    last_selection: Dict[str, Any] = {"selected_tool": "", "arguments": {}, "reason": ""}
    last_failure_reason = ""
    llm_usage_totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    attempt_trace: list[Dict[str, Any]] = []

    while attempts < max_attempts:
        attempts += 1
        (
            selection,
            selected_tool,
            selected_arguments,
            llm_usage,
        ) = _selection_attempt(
            intake=intake,
            catalog=catalog,
            runtime_config=runtime_config,
            retry_feedback=retry_feedback,
        )
        llm_usage_totals = _merge_usage(llm_usage_totals, llm_usage)
        last_selection = selection
        if selected_tool not in catalog.tool_map:
            construction_failures += 1
            last_failure_reason = f"selected_unknown_tool:{selected_tool}"
            attempt_trace.append(_invalid_trace_entry(attempts=attempts, selected_tool=selected_tool, error=last_failure_reason))
            retry_feedback = _unknown_tool_retry_feedback(last_failure_reason)
            continue

        arguments_validation_error = validate_gateway_tool_arguments(
            selected_tool=catalog.tool_map[selected_tool],
            arguments=selected_arguments,
        )
        if arguments_validation_error:
            construction_failures += 1
            last_failure_reason = arguments_validation_error
            attempt_trace.append(_invalid_trace_entry(attempts=attempts, selected_tool=selected_tool, error=arguments_validation_error))
            retry_feedback = _invalid_retry_feedback(arguments_validation_error)
            continue

        attempt_trace.append(_valid_trace_entry(attempts, selected_tool))
        return _selection_resolution(
            ResolutionInput(
                selection=selection,
                selected_tool=selected_tool,
                selected_arguments=selected_arguments,
                attempts=attempts,
                construction_failures=construction_failures,
                llm_usage_totals=llm_usage_totals,
                attempt_trace=attempt_trace,
                failure_reason="",
            )
        )

    return _selection_resolution(
        ResolutionInput(
            selection=last_selection,
            selected_tool=str(last_selection.get("selected_tool", "")),
            selected_arguments=last_selection.get("arguments", {}) if isinstance(last_selection.get("arguments", {}), dict) else {},
            attempts=attempts,
            construction_failures=construction_failures,
            llm_usage_totals=llm_usage_totals,
            attempt_trace=attempt_trace,
            failure_reason=last_failure_reason or "mcp_call_construction_retry_exhausted",
        )
    )


def _selector_runtime_config(event: Dict[str, Any]) -> SelectorRuntimeConfig:
    return SelectorRuntimeConfig(
        model_id=selected_model_id(event),
        region=selected_region(event),
        dry_run=bool(event.get("dry_run", False)),
        model_provider=selected_model_provider(event),
        provider_options=selected_provider_options(event),
    )


def _selection_metric_value(selection: Dict[str, Any], key: str) -> int:
    return _safe_int(selection.get(key, 0))


def _invoke_tool(gateway_url: str, region: str, selected_tool: str, tool_arguments: Dict[str, Any]) -> Dict[str, Any]:
    call_response = call_gateway_tool(
        gateway_url=gateway_url,
        region=region,
        tool_name=selected_tool,
        arguments=tool_arguments,
    )
    return extract_gateway_tool_payload(call_response)


def _validate_tool_payload(validation: ValidationInput) -> StageToolOutcome:
    issue = validation.tool_payload.get("result", validation.tool_payload)
    selected_tool_unprefixed = strip_gateway_tool_prefix(validation.selected_tool)
    if not issue_payload_complete_for_tool(issue, selected_tool_unprefixed):
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
            "call_construction_attempts": _selection_metric_value(outcome.selection, "construction_attempts"),
            "call_construction_retries": _selection_metric_value(outcome.selection, "construction_retries"),
            "call_construction_failures": _selection_metric_value(outcome.selection, "construction_failures"),
            "llm_input_tokens": _selection_metric_value(outcome.selection, "llm_input_tokens"),
            "llm_output_tokens": _selection_metric_value(outcome.selection, "llm_output_tokens"),
            "llm_total_tokens": _selection_metric_value(outcome.selection, "llm_total_tokens"),
        },
    )


def _apply_outcome(event: Dict[str, Any], outcome: StageToolOutcome, set_scope: bool) -> None:
    event["mcp_selection"] = outcome.selection
    event["tool_path"] = "mcp_gateway"
    event["tool_failure"] = outcome.tool_failure
    event["tool_result"] = outcome.tool_result
    event["mcp_call_construction"] = {
        "attempts": _selection_metric_value(outcome.selection, "construction_attempts"),
        "retries": _selection_metric_value(outcome.selection, "construction_retries"),
        "failures": _selection_metric_value(outcome.selection, "construction_failures"),
        "attempt_trace": outcome.selection.get("construction_attempt_trace", []),
        "attempt_trace_map": outcome.selection.get("construction_attempt_trace_map", {}),
    }
    event.setdefault("llm_usage", {})
    event["llm_usage"]["fetch_mcp_tool_selection"] = {
        "input_tokens": _selection_metric_value(outcome.selection, "llm_input_tokens"),
        "output_tokens": _selection_metric_value(outcome.selection, "llm_output_tokens"),
        "total_tokens": _selection_metric_value(outcome.selection, "llm_total_tokens"),
    }
    if set_scope:
        event["mcp_scope"] = {
            "intent": outcome.scope.intent,
            "scoped_tool_count": outcome.scope.scoped_tool_count,
            "catalog_tool_count": outcome.scope.catalog_tool_count,
        }


def _grounding_failure_reason(event: Dict[str, Any]) -> str:
    grounding = event.get("grounding", {})
    if not isinstance(grounding, dict):
        return ""
    return str(grounding.get("failure_reason", "")).strip()


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
    initial_context = _run_context(event=event, started=started, issue_key=issue_key, selected_tool="", set_scope=False)
    grounding_failure_reason = _grounding_failure_reason(event)

    if grounding_failure_reason:
        return _failed_result(
            run_context=initial_context,
            reason=f"grounding_resolution_failed:{grounding_failure_reason}",
            selection={"selected_tool": "", "arguments": {}, "reason": "grounding_failed"},
            scope=_empty_scope(intent),
        )

    selector_runtime_config = _selector_runtime_config(event)
    region = selector_runtime_config.region
    gateway_url = selected_gateway_url(event)
    try:
        catalog = _build_scope(
            gateway_url=gateway_url,
            region=region,
            intent=intent,
        )
    except Exception as exc:  # noqa: BLE001 - failure should be scored, not crash the pipeline
        return _gateway_unavailable_result(
            run_context=initial_context,
            intent=intent,
            exc=exc,
        )

    selection_resolution = _resolve_tool_call_selection(
        intake=intake,
        catalog=catalog,
        runtime_config=selector_runtime_config,
    )
    selected_tool = selection_resolution.selected_tool
    selected_arguments = selection_resolution.selected_arguments
    selection = selection_resolution.selection
    selected_context = _run_context(
        event=event,
        started=started,
        issue_key=issue_key,
        selected_tool=selected_tool,
        set_scope=True,
    )

    if selection_resolution.failure_reason:
        return _failed_result(
            run_context=selected_context,
            reason=selection_resolution.failure_reason,
            selection=selection,
            scope=catalog.scope,
        )

    try:
        tool_payload = _invoke_tool(
            gateway_url=gateway_url,
            region=region,
            selected_tool=selected_tool,
            tool_arguments=selected_arguments,
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
            tool_payload=tool_payload,
            issue_key=issue_key,
            scope=catalog.scope,
            selection=selection,
        )
    )
    return _finalize(selected_context, outcome)


def handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    return _run_handler(event, started=time.time())
