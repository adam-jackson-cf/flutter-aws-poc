import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, TypedDict

from ..domain import MCP_TOOL_SCOPE_BY_INTENT, issue_payload_complete_for_tool, scope_tools_by_intent, strip_target_prefix
from .agentcore_mcp_client import AgentCoreMcpClient
from .jira_native_sdk import JiraSdkClient
from .llm_gateway_invoke_client import invoke_llm_gateway
from .tool_flow_result import ToolFlowScope, flow_failure, flow_success

TOOL_SCOPE_BY_INTENT: Dict[str, List[str]] = MCP_TOOL_SCOPE_BY_INTENT


class McpSelectionError(RuntimeError):
    pass


@dataclass(frozen=True)
class ScopedCatalog:
    intent: str
    all_tools: List[Dict[str, Any]]
    scoped_tools: List[Dict[str, Any]]
    tool_map: Dict[str, Dict[str, Any]]


@dataclass(frozen=True)
class FailureInput:
    intake: Dict[str, Any]
    failure_reason: str
    selection: Dict[str, Any]
    catalog: ScopedCatalog | None = None
    tool_payload: Dict[str, Any] | None = None


@dataclass(frozen=True)
class SelectionInput:
    request_text: str
    issue_key: str
    tools: List[Dict[str, Any]]
    dry_run: bool = False
    retry_feedback: str = ""


@dataclass(frozen=True)
class SelectionResolution:
    selection: Dict[str, Any]
    selected_tool: str
    selected_arguments: Dict[str, Any]
    attempts: int
    construction_failures: int
    failure_reason: str


@dataclass(frozen=True)
class McpModelConfig:
    model_id: str
    region: str
    model_provider: str = "auto"
    provider_options: Dict[str, Any] | None = None


class FailureResult(TypedDict, total=False):
    selection: Dict[str, Any]
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


def _max_attempts() -> int:
    raw = str(os.environ.get("MCP_CALL_CONSTRUCTION_MAX_ATTEMPTS", "2")).strip() or "2"
    try:
        parsed = int(raw)
    except ValueError as exc:
        raise ValueError("mcp_call_construction_max_attempts_invalid") from exc
    if parsed < 1:
        raise ValueError("mcp_call_construction_max_attempts_invalid")
    return parsed


def _tool_input_schema_summary(tool: Dict[str, Any]) -> str:
    input_schema = tool.get("inputSchema", {})
    required = input_schema.get("required", []) if isinstance(input_schema, dict) else []
    if not isinstance(required, list):
        required = []
    properties = input_schema.get("properties", {}) if isinstance(input_schema, dict) else {}
    if not isinstance(properties, dict):
        properties = {}
    property_labels: List[str] = []
    for name, spec in properties.items():
        if not isinstance(spec, dict):
            continue
        data_type = str(spec.get("type", "string")).strip() or "string"
        property_labels.append(f"{name}:{data_type}")
    return f"required={required}; properties={property_labels}"


def _tool_prompt_lines(tools: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for tool in tools:
        name = str(tool.get("name", ""))
        description = str(tool.get("description", "")).strip()
        lines.append(f"- {name}: {description[:220]} ({_tool_input_schema_summary(tool)})")
    return "\n".join(lines)


def _default_arguments(default_tool: Dict[str, Any], issue_key: str, request_text: str) -> Dict[str, Any]:
    input_schema = default_tool.get("inputSchema", {})
    required = input_schema.get("required", []) if isinstance(input_schema, dict) else []
    if not isinstance(required, list):
        required = []
    args: Dict[str, Any] = {}
    if "issue_key" in required:
        args["issue_key"] = issue_key
    if "query" in required:
        args["query"] = request_text
    if "note_text" in required:
        args["note_text"] = request_text
    return args


def _validate_gateway_tool_arguments(selected_tool: Dict[str, Any], arguments: Dict[str, Any]) -> str:
    if not isinstance(arguments, dict):
        return "mcp_tool_args_invalid:arguments_not_object"
    properties, required, schema_error = _input_schema_parts(selected_tool)
    if schema_error:
        return schema_error
    structure_error = _required_and_unknown_argument_error(
        arguments=arguments,
        required=required,
        properties=properties,
    )
    if structure_error:
        return structure_error
    return _argument_type_error(arguments=arguments, properties=properties)


def _input_schema_parts(
    selected_tool: Dict[str, Any],
) -> tuple[Dict[str, Any], list[str], str]:
    input_schema = selected_tool.get("inputSchema", {})
    if not isinstance(input_schema, dict):
        return {}, [], "mcp_tool_args_invalid:input_schema_not_object"
    properties = input_schema.get("properties", {})
    if not isinstance(properties, dict):
        properties = {}
    required = input_schema.get("required", [])
    if not isinstance(required, list):
        required = []
    required_names = [str(name) for name in required if isinstance(name, str)]
    return properties, required_names, ""


def _required_and_unknown_argument_error(
    *,
    arguments: Dict[str, Any],
    required: list[str],
    properties: Dict[str, Any],
) -> str:
    missing_required = [name for name in required if name not in arguments]
    if missing_required:
        return f"mcp_tool_args_missing_required:{','.join(sorted(missing_required))}"
    unknown = [name for name in arguments if properties and name not in properties]
    if unknown:
        return f"mcp_tool_args_unknown_arguments:{','.join(sorted(unknown))}"
    return ""


def _argument_type_error(*, arguments: Dict[str, Any], properties: Dict[str, Any]) -> str:
    for name, value in arguments.items():
        schema = properties.get(name, {})
        if not isinstance(schema, dict):
            continue
        expected_type = str(schema.get("type", "")).strip()
        if expected_type == "string" and not isinstance(value, str):
            return f"mcp_tool_args_invalid_type:{name}:expected_string"
        if expected_type == "array_string" and (
            not isinstance(value, list) or any(not isinstance(item, str) for item in value)
        ):
            return f"mcp_tool_args_invalid_type:{name}:expected_array_string"
    return ""


class McpJiraFlow:
    def __init__(
        self,
        jira_client: JiraSdkClient,
        gateway_url: str,
        config: McpModelConfig,
    ) -> None:
        self._jira_client = jira_client
        self._model_id = config.model_id
        self._region = config.region
        self._model_provider = config.model_provider
        self._provider_options = config.provider_options
        self._mcp_client = AgentCoreMcpClient(gateway_url=gateway_url, region=config.region)

    @staticmethod
    def _strip_target_prefix(tool_name: str) -> str:
        return strip_target_prefix(tool_name)

    def _scope_tools_for_intent(self, tools: List[Dict[str, Any]], intent: str) -> List[Dict[str, Any]]:
        try:
            return scope_tools_by_intent(tools=tools, intent=intent, scope_by_intent=TOOL_SCOPE_BY_INTENT)
        except RuntimeError as exc:
            raise McpSelectionError(f"No MCP tools available after scoping for intent={intent}") from exc

    def _build_scoped_catalog(self, intent: str) -> ScopedCatalog:
        all_tools = self._mcp_client.list_tools()
        scoped_tools = self._scope_tools_for_intent(all_tools, intent)
        return ScopedCatalog(
            intent=intent,
            all_tools=all_tools,
            scoped_tools=scoped_tools,
            tool_map={str(tool.get("name", "")): tool for tool in scoped_tools},
        )

    @staticmethod
    def _scope_context(catalog: ScopedCatalog) -> Dict[str, Any]:
        return {
            "intent": catalog.intent,
            "catalog_tool_count": len(catalog.all_tools),
            "scoped_tool_count": len(catalog.scoped_tools),
        }

    def _failure_result(self, failure: FailureInput) -> FailureResult:
        scope = (
            ToolFlowScope(
                intent=failure.catalog.intent,
                scoped_tool_count=len(failure.catalog.scoped_tools),
                catalog_tool_count=len(failure.catalog.all_tools),
            )
            if failure.catalog is not None
            else ToolFlowScope(intent=str(failure.intake.get("intent", "general_triage")), scoped_tool_count=0)
        )
        result: FailureResult = flow_failure(
            selection=failure.selection,
            issue_key=failure.intake["issue_key"],
            reason=failure.failure_reason,
            scope=scope,
        )
        if failure.catalog is None:
            result.pop("scope", None)
        else:
            result["scope"] = self._scope_context(failure.catalog)
        if failure.tool_payload is not None:
            result["tool_payload"] = failure.tool_payload
        return result

    def _select_tool(self, selection_input: SelectionInput) -> Dict[str, Any]:
        default_tool = str(selection_input.tools[0].get("name", "jira_get_issue_by_key")) if selection_input.tools else "jira_get_issue_by_key"
        default_args = _default_arguments(
            default_tool=selection_input.tools[0] if selection_input.tools else {},
            issue_key=selection_input.issue_key,
            request_text=selection_input.request_text,
        )
        if selection_input.dry_run:
            return {
                "tool": default_tool,
                "arguments": default_args,
                "reason": "dry_run",
            }

        prompt = (
            "You are a reasoning-scope orchestration agent selecting an MCP tool call.\n"
            "The tool catalog is pre-filtered by capability bindings and task scope.\n"
            f"Request: {selection_input.request_text}\n"
            f"Issue key: {selection_input.issue_key}\n"
            "Choose exactly one tool and construct a valid arguments object that matches the selected tool input schema.\n"
            'Return strict JSON only: {"tool":"<name>","arguments":{...},"reason":"<short reason>"}.\n'
            f"Previous attempt feedback: {selection_input.retry_feedback or 'none'}\n"
            "Scoped tool list with input schemas:\n"
            f"{_tool_prompt_lines(selection_input.tools)}"
        )
        raw = invoke_llm_gateway(
            model_id=self._model_id,
            prompt=prompt,
            region=self._region,
            provider=self._model_provider,
            provider_options=self._provider_options,
        )
        payload = _extract_json(raw)
        arguments = payload.get("arguments", {})
        return {
            "tool": str(payload.get("tool", "")),
            "arguments": arguments if isinstance(arguments, dict) else {},
            "reason": str(payload.get("reason", "")),
        }

    def _selection_resolution(self, intake: Dict[str, Any], catalog: ScopedCatalog, dry_run: bool) -> SelectionResolution:
        attempts = 0
        construction_failures = 0
        retry_feedback = ""
        last_selection: Dict[str, Any] = {"tool": "", "arguments": {}, "reason": ""}
        last_failure_reason = ""
        while attempts < _max_attempts():
            attempts += 1
            selection = self._select_tool(
                SelectionInput(
                    request_text=intake["request_text"],
                    issue_key=intake["issue_key"],
                    tools=catalog.scoped_tools,
                    dry_run=dry_run,
                    retry_feedback=retry_feedback,
                )
            )
            selected_tool = str(selection.get("tool", ""))
            selected_arguments = selection.get("arguments", {})
            if not isinstance(selected_arguments, dict):
                selected_arguments = {}
            last_selection = selection
            if selected_tool not in catalog.tool_map:
                construction_failures += 1
                last_failure_reason = f"selected_unknown_tool:{selected_tool}"
                retry_feedback = (
                    f"Previous attempt invalid: {last_failure_reason}. "
                    "Choose one tool from the scoped list and provide valid arguments."
                )
                continue

            validation_error = _validate_gateway_tool_arguments(
                selected_tool=catalog.tool_map[selected_tool],
                arguments=selected_arguments,
            )
            if validation_error:
                construction_failures += 1
                last_failure_reason = validation_error
                retry_feedback = (
                    f"Previous attempt invalid: {validation_error}. "
                    "Return arguments that match the tool input schema exactly."
                )
                continue

            selection["construction_attempts"] = attempts
            selection["construction_retries"] = max(0, attempts - 1)
            selection["construction_failures"] = construction_failures
            return SelectionResolution(
                selection=selection,
                selected_tool=selected_tool,
                selected_arguments=selected_arguments,
                attempts=attempts,
                construction_failures=construction_failures,
                failure_reason="",
            )

        last_selection["construction_attempts"] = attempts
        last_selection["construction_retries"] = max(0, attempts - 1)
        last_selection["construction_failures"] = construction_failures
        return SelectionResolution(
            selection=last_selection,
            selected_tool=str(last_selection.get("tool", "")),
            selected_arguments=last_selection.get("arguments", {}) if isinstance(last_selection.get("arguments", {}), dict) else {},
            attempts=attempts,
            construction_failures=construction_failures,
            failure_reason=last_failure_reason or "mcp_call_construction_retry_exhausted",
        )

    def fetch_issue_with_selection(self, intake: Dict[str, Any], dry_run: bool = False) -> Dict[str, Any]:
        intent = str(intake.get("intent", "general_triage"))
        try:
            catalog = self._build_scoped_catalog(intent=intent)
        except Exception as exc:  # noqa: BLE001 - failure should be scored, not throw
            failure_reason = f"mcp_catalog_error:{exc}"
            return self._failure_result(
                FailureInput(
                    intake=intake,
                    failure_reason=failure_reason,
                    selection={"tool": "", "reason": failure_reason},
                )
            )

        selection_resolution = self._selection_resolution(
            intake=intake,
            catalog=catalog,
            dry_run=dry_run,
        )
        if selection_resolution.failure_reason:
            return self._failure_result(
                FailureInput(
                    intake=intake,
                    failure_reason=selection_resolution.failure_reason,
                    selection=selection_resolution.selection,
                    catalog=catalog,
                )
            )

        try:
            call_result = self._mcp_client.call_tool(
                tool_name=selection_resolution.selected_tool,
                arguments=selection_resolution.selected_arguments,
            )
            tool_payload = self._mcp_client.extract_json_payload(call_result)
        except Exception as exc:  # noqa: BLE001 - failure should be scored, not throw
            return self._failure_result(
                FailureInput(
                    intake=intake,
                    failure_reason=f"mcp_invocation_error:{exc}",
                    selection=selection_resolution.selection,
                    catalog=catalog,
                )
            )

        issue = tool_payload.get("result", tool_payload)
        if not issue_payload_complete_for_tool(
            tool_result=issue if isinstance(issue, dict) else {},
            tool_name=self._strip_target_prefix(selection_resolution.selected_tool),
        ):
            return self._failure_result(
                FailureInput(
                    intake=intake,
                    failure_reason="mcp_missing_issue_payload",
                    selection=selection_resolution.selection,
                    catalog=catalog,
                    tool_payload=tool_payload,
                )
            )

        scope = ToolFlowScope(
            intent=catalog.intent,
            scoped_tool_count=len(catalog.scoped_tools),
            catalog_tool_count=len(catalog.all_tools),
        )
        success = flow_success(selection=selection_resolution.selection, issue=issue, scope=scope)
        success["scope"] = self._scope_context(catalog)
        return success
