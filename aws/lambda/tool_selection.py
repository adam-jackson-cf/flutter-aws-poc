from dataclasses import dataclass
from typing import Any, Dict, List

from bedrock_client import call_bedrock, extract_json_object
from tooling_domain import build_failure_issue, strip_gateway_tool_prefix


@dataclass(frozen=True)
class ToolSelectionRequest:
    request_text: str
    issue_key: str
    tools: List[Dict[str, Any]]
    default_tool: str
    selector_name: str = "agent_selector"


@dataclass(frozen=True)
class ToolSelectorConfig:
    model_id: str
    region: str
    dry_run: bool = False


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


def select_tool_with_model(selection: ToolSelectionRequest, config: ToolSelectorConfig) -> Dict[str, Any]:
    if config.dry_run:
        return {"selected_tool": selection.default_tool, "reason": "dry_run"}

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
    raw = call_bedrock(model_id=config.model_id, prompt=prompt, region=config.region)
    parsed = extract_json_object(raw)
    return {
        "selected_tool": str(parsed.get("tool", "")),
        "reason": str(parsed.get("reason", "")),
    }


def select_mcp_tool(selection: ToolSelectionRequest, config: ToolSelectorConfig) -> Dict[str, Any]:
    mcp_selection = ToolSelectionRequest(
        request_text=selection.request_text,
        issue_key=selection.issue_key,
        tools=selection.tools,
        default_tool=selection.default_tool,
        selector_name="mcp_gateway_selector",
    )
    return select_tool_with_model(
        selection=mcp_selection,
        config=config,
    )


def find_expected_gateway_tool(tools: List[Dict[str, Any]], unprefixed_tool_name: str = "jira_get_issue_by_key") -> str:
    for tool in tools:
        name = str(tool.get("name", ""))
        if strip_gateway_tool_prefix(name) == unprefixed_tool_name:
            return name
    raise RuntimeError(f"expected_gateway_tool_not_found:{unprefixed_tool_name}")


def build_gateway_tool_args(selected_tool: Dict[str, Any], issue_key: str, request_text: str) -> Dict[str, Any]:
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
