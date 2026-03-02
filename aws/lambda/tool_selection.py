from dataclasses import dataclass
from copy import deepcopy
from typing import Any, Dict, List

from bedrock_client import extract_json_object
from llm_gateway_client import call_llm_gateway_with_usage
from tooling_domain import build_failure_issue


@dataclass(frozen=True)
class ToolSelectionRequest:
    request_text: str
    issue_key: str
    tools: List[Dict[str, Any]]
    default_tool: str
    selector_name: str = "agent_selector"
    retry_feedback: str = ""


@dataclass(frozen=True)
class ToolSelectorConfig:
    model_id: str
    region: str
    dry_run: bool = False
    model_provider: str = "auto"
    provider_options: Dict[str, Any] | None = None


@dataclass(frozen=True)
class StageToolScope:
    intent: str
    scoped_tool_count: int
    catalog_tool_count: int = 0


@dataclass(frozen=True)
class StageToolOutcome:
    selection: Dict[str, Any]
    tool_failure: bool
    tool_result: Dict[str, Any]
    scope: StageToolScope


def _tool_prompt_lines(tools: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for tool in tools:
        tool_name = str(tool.get("name", ""))
        tool_description = str(tool.get("description", "")).strip()
        lines.append(f"- {tool_name}: {tool_description[:220]}")
    return "\n".join(lines)


def _selection_response_schema(tool_names: List[str]) -> Dict[str, Any]:
    tool_property: Dict[str, Any] = {"type": "string"}
    if tool_names:
        tool_property["enum"] = tool_names
    return {
        "type": "object",
        "properties": {
            "tool": tool_property,
            "reason": {"type": "string"},
        },
        "required": ["tool", "reason"],
        "additionalProperties": False,
    }


def _mcp_call_response_schema(tool_names: List[str]) -> Dict[str, Any]:
    tool_property: Dict[str, Any] = {"type": "string"}
    if tool_names:
        tool_property["enum"] = tool_names
    return {
        "type": "object",
        "properties": {
            "tool": tool_property,
            "arguments": {"type": "object", "additionalProperties": True},
            "reason": {"type": "string"},
        },
        "required": ["tool", "arguments", "reason"],
        "additionalProperties": False,
    }


def _provider_options_with_json_schema(
    provider_options: Dict[str, Any] | None,
    *,
    schema_name: str,
    response_schema: Dict[str, Any],
) -> Dict[str, Any]:
    options: Dict[str, Any] = deepcopy(provider_options) if isinstance(provider_options, dict) else {}
    openai_options = options.get("openai")
    if not isinstance(openai_options, dict):
        openai_options = {}
    openai_options["response_json_schema"] = {
        "name": schema_name,
        "schema": response_schema,
        "strict": True,
    }
    options["openai"] = openai_options
    return options


def _empty_usage() -> Dict[str, int]:
    return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}


def select_tool_with_model(selection: ToolSelectionRequest, config: ToolSelectorConfig) -> Dict[str, Any]:
    if config.dry_run:
        return {
            "selected_tool": selection.default_tool,
            "reason": "dry_run",
            "llm_usage": _empty_usage(),
        }

    prompt = (
        "You are a reasoning-scope orchestration agent.\n"
        "The tool catalog is pre-filtered by capability bindings and task scope.\n"
        f"Selector: {selection.selector_name}\n"
        f"Request: {selection.request_text}\n"
        f"Issue key: {selection.issue_key}\n"
        "Choose exactly one tool name from the provided list.\n"
        'Return strict JSON only: {"tool":"<name>","reason":"<short reason>"}.\n'
        "Scoped tool list:\n"
        f"{_tool_prompt_lines(selection.tools)}"
    )
    tool_names = [str(tool.get("name", "")).strip() for tool in selection.tools if str(tool.get("name", "")).strip()]
    provider_options = _provider_options_with_json_schema(
        config.provider_options,
        schema_name="tool_selection",
        response_schema=_selection_response_schema(tool_names),
    )
    raw, llm_usage = call_llm_gateway_with_usage(
        model_id=config.model_id,
        prompt=prompt,
        region=config.region,
        provider=config.model_provider,
        provider_options=provider_options,
    )
    parsed = extract_json_object(raw)
    return {
        "selected_tool": str(parsed.get("tool", "")),
        "reason": str(parsed.get("reason", "")),
        "llm_usage": llm_usage,
    }


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


def _mcp_tool_prompt_lines(tools: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for tool in tools:
        tool_name = str(tool.get("name", ""))
        tool_description = str(tool.get("description", "")).strip()
        schema_summary = _tool_input_schema_summary(tool)
        lines.append(f"- {tool_name}: {tool_description[:220]} ({schema_summary})")
    return "\n".join(lines)


def _default_mcp_arguments(default_tool: Dict[str, Any], issue_key: str, request_text: str) -> Dict[str, Any]:
    input_schema = default_tool.get("inputSchema", {})
    required = input_schema.get("required", []) if isinstance(input_schema, dict) else []
    if not isinstance(required, list):
        required = []
    args: Dict[str, Any] = {}
    if "issue_key" in required:
        args["issue_key"] = issue_key
    if "query" in required:
        args["query"] = request_text
    return args


def select_mcp_tool_call(selection: ToolSelectionRequest, config: ToolSelectorConfig) -> Dict[str, Any]:
    tool_map = {
        str(tool.get("name", "")).strip(): tool
        for tool in selection.tools
        if str(tool.get("name", "")).strip()
    }
    default_tool = tool_map.get(selection.default_tool, {})
    if config.dry_run:
        return {
            "selected_tool": selection.default_tool,
            "arguments": _default_mcp_arguments(default_tool, selection.issue_key, selection.request_text),
            "reason": "dry_run",
            "llm_usage": _empty_usage(),
        }

    prompt = (
        "You are a reasoning-scope orchestration agent selecting an MCP tool call.\n"
        "The tool catalog is pre-filtered by capability bindings and task scope.\n"
        f"Selector: mcp_gateway_selector\n"
        f"Request: {selection.request_text}\n"
        f"Issue key: {selection.issue_key}\n"
        "Choose exactly one tool and construct a valid arguments object that matches the selected tool input schema.\n"
        'Return strict JSON only: {"tool":"<name>","arguments":{...},"reason":"<short reason>"}.\n'
        f"Previous attempt feedback: {selection.retry_feedback or 'none'}\n"
        "Scoped tool list with input schemas:\n"
        f"{_mcp_tool_prompt_lines(selection.tools)}"
    )
    provider_options = _provider_options_with_json_schema(
        config.provider_options,
        schema_name="mcp_tool_call",
        response_schema=_mcp_call_response_schema(list(tool_map.keys())),
    )
    raw, llm_usage = call_llm_gateway_with_usage(
        model_id=config.model_id,
        prompt=prompt,
        region=config.region,
        provider=config.model_provider,
        provider_options=provider_options,
    )
    parsed = extract_json_object(raw)
    arguments = parsed.get("arguments", {})
    return {
        "selected_tool": str(parsed.get("tool", "")),
        "arguments": arguments if isinstance(arguments, dict) else {},
        "reason": str(parsed.get("reason", "")),
        "llm_usage": llm_usage,
    }


def validate_gateway_tool_arguments(selected_tool: Dict[str, Any], arguments: Dict[str, Any]) -> str:
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
    normalized_required = [str(name) for name in required if isinstance(name, str)]
    return properties, normalized_required, ""


def _required_and_unknown_argument_error(
    *,
    arguments: Dict[str, Any],
    required: list[str],
    properties: Dict[str, Any],
) -> str:
    missing_required = [name for name in required if name not in arguments]
    if missing_required:
        return f"mcp_tool_args_missing_required:{','.join(sorted(missing_required))}"
    unknown_arguments = [name for name in arguments if properties and name not in properties]
    if unknown_arguments:
        return f"mcp_tool_args_unknown_arguments:{','.join(sorted(unknown_arguments))}"
    return ""


def _argument_type_error(*, arguments: Dict[str, Any], properties: Dict[str, Any]) -> str:
    for name, value in arguments.items():
        property_schema = properties.get(name, {})
        if not isinstance(property_schema, dict):
            continue
        expected_type = str(property_schema.get("type", "")).strip()
        if expected_type == "string" and not isinstance(value, str):
            return f"mcp_tool_args_invalid_type:{name}:expected_string"
        if expected_type == "array_string":
            if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                return f"mcp_tool_args_invalid_type:{name}:expected_array_string"
    return ""


def stage_tool_failure(issue_key: str, reason: str, selection: Dict[str, Any], scope: StageToolScope) -> StageToolOutcome:
    return StageToolOutcome(
        selection=selection,
        tool_failure=True,
        tool_result=build_failure_issue(issue_key=issue_key, failure_reason=reason),
        scope=scope,
    )


def stage_tool_success(tool_result: Dict[str, Any], selection: Dict[str, Any], scope: StageToolScope) -> StageToolOutcome:
    return StageToolOutcome(
        selection=selection,
        tool_failure=False,
        tool_result=tool_result,
        scope=scope,
    )
