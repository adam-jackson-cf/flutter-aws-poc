import json
import os
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

ISSUE_KEY_PATTERN = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")

MCP_TOOL_SCOPE_BY_INTENT: Dict[str, List[str]] = {
    # Capability-style scoped tool bindings to minimize context bloat in Reasoning scope.
    "bug_triage": [
        "jira_get_issue_by_key",
        "jira_get_issue_priority_context",
        "jira_get_issue_risk_flags",
    ],
    "status_update": [
        "jira_get_issue_by_key",
        "jira_get_issue_status_snapshot",
        "jira_get_issue_update_timestamp",
    ],
    "feature_request": [
        "jira_get_issue_by_key",
        "jira_get_issue_labels",
        "jira_get_issue_project_key",
    ],
    "general_triage": [
        "jira_get_issue_by_key",
        "jira_get_issue_status_snapshot",
    ],
}

TOOL_COMPLETENESS_FIELDS_BY_OPERATION: Dict[str, List[str]] = {
    "get_issue_by_key": ["key", "summary", "status"],
    "get_issue_status_snapshot": ["key", "status", "updated"],
    "get_issue_priority_context": ["key", "priority"],
    "get_issue_labels": ["key", "labels"],
    "get_issue_project_key": ["key", "project_key"],
    "get_issue_update_timestamp": ["key", "updated"],
    "get_issue_risk_flags": ["key"],
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_token(value: str, fallback: str = "unknown") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "-", str(value or "").strip())
    return cleaned or fallback


def _is_allowed_host(host: str, allowed_hosts: List[str]) -> bool:
    for candidate in allowed_hosts:
        normalized = candidate.strip().lower()
        if not normalized:
            continue
        if normalized.startswith("."):
            if host.endswith(normalized):
                return True
            continue
        if host == normalized:
            return True
    return False


def _allowed_hosts_from_env(env_var_name: str, default_value: str) -> List[str]:
    raw = os.environ.get(env_var_name, default_value)
    return [entry.strip() for entry in raw.split(",") if entry.strip()]


def validate_endpoint_url(url: str, env_var_name: str, default_allowed_hosts: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise RuntimeError(f"invalid_url_scheme:{env_var_name}")
    host = (parsed.hostname or "").lower().strip()
    if not host:
        raise RuntimeError(f"invalid_url_host:{env_var_name}")
    allowed_hosts = _allowed_hosts_from_env(env_var_name=env_var_name, default_value=default_allowed_hosts)
    if not _is_allowed_host(host, allowed_hosts):
        raise RuntimeError(f"disallowed_url_host:{env_var_name}:{host}")


def _read_json_from_url(url: str) -> Dict[str, Any]:
    req = Request(url, headers={"Accept": "application/json", "User-Agent": "flutter-agentcore-poc/1.0"})
    with urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_jira_issue(issue_key: str, jira_base_url: str) -> Dict[str, Any]:
    validate_endpoint_url(
        url=jira_base_url,
        env_var_name="JIRA_ALLOWED_HOSTS",
        default_allowed_hosts="jira.atlassian.com",
    )
    fields = "summary,description,status,issuetype,priority,labels,comment,updated"
    url = f"{jira_base_url}/rest/api/2/issue/{issue_key}?fields={fields}"
    try:
        payload = _read_json_from_url(url)
    except HTTPError as exc:
        raise RuntimeError(f"jira_http_error:{exc.code}") from exc
    except URLError as exc:
        raise RuntimeError("jira_url_error") from exc

    issue_fields = payload.get("fields", {})
    priority = issue_fields.get("priority") or {}
    status = issue_fields.get("status") or {}
    issue_type = issue_fields.get("issuetype") or {}
    comments = issue_fields.get("comment") or {}

    description = issue_fields.get("description") or ""
    if not isinstance(description, str):
        description = str(description)

    summary = issue_fields.get("summary", "")
    if not isinstance(summary, str):
        summary = str(summary)

    return {
        "key": payload.get("key", issue_key),
        "summary": summary[:300],
        "status": status.get("name", "Unknown"),
        "issue_type": issue_type.get("name", "Unknown"),
        "priority": priority.get("name", "None"),
        "labels": (issue_fields.get("labels", []) or [])[:10],
        "updated": issue_fields.get("updated", ""),
        "description": description[:600],
        "comment_count": comments.get("total", 0),
    }


def classify_intent(request_text: str) -> str:
    text = request_text.lower()
    if any(token in text for token in ["bug", "incident", "error", "outage", "failure", "broken"]):
        return "bug_triage"
    if any(token in text for token in ["feature", "suggestion", "roadmap", "improvement"]):
        return "feature_request"
    if any(token in text for token in ["status", "progress", "update", "latest"]):
        return "status_update"
    return "general_triage"


def extract_intake(request_text: str) -> Dict[str, Any]:
    issue_keys = ISSUE_KEY_PATTERN.findall(request_text)
    if not issue_keys:
        raise ValueError("No issue key found in request_text. Include a Jira key like JRASERVER-79286.")

    return {
        "request_text": request_text,
        "issue_key": issue_keys[0],
        "intent": classify_intent(request_text),
        "risk_hints": [
            token
            for token in ["accessibility", "security", "compliance", "customer", "incident", "escalation"]
            if token in request_text.lower()
        ],
    }


def _extract_json_object(raw_text: str) -> Dict[str, Any]:
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("model_response_missing_json")
    candidate = raw_text[start : end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        repaired = re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", candidate)
        return json.loads(repaired)


def _call_bedrock(model_id: str, prompt: str, region: str) -> str:
    client = boto3.client("bedrock-runtime", region_name=region)
    response = client.converse(
        modelId=model_id,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"temperature": 0.2, "maxTokens": 700},
    )
    content = response["output"]["message"]["content"]
    parts = [part.get("text", "") for part in content if "text" in part]
    return "\n".join(parts)


def _mcp_signed_post(gateway_url: str, region: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = AWSRequest(
        method="POST",
        url=gateway_url,
        data=body,
        headers={"Content-Type": "application/json"},
    )
    credentials = boto3.Session(region_name=region).get_credentials()
    if credentials is None:
        raise RuntimeError("missing_aws_credentials_for_mcp")
    SigV4Auth(credentials.get_frozen_credentials(), "bedrock-agentcore", region).add_auth(request)
    signed_headers = dict(request.headers.items())
    http_request = Request(gateway_url, data=body, headers=signed_headers, method="POST")
    with urlopen(http_request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def list_gateway_tools(gateway_url: str, region: str) -> List[Dict[str, Any]]:
    response = _mcp_signed_post(
        gateway_url=gateway_url,
        region=region,
        payload={"jsonrpc": "2.0", "id": "tools-list", "method": "tools/list"},
    )
    tools = response.get("result", {}).get("tools", [])
    if not isinstance(tools, list):
        raise RuntimeError("invalid_tools_list_payload")
    return tools


def call_gateway_tool(gateway_url: str, region: str, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    return _mcp_signed_post(
        gateway_url=gateway_url,
        region=region,
        payload={
            "jsonrpc": "2.0",
            "id": "tools-call",
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        },
    )


def extract_gateway_tool_payload(call_response: Dict[str, Any]) -> Dict[str, Any]:
    content = call_response.get("result", {}).get("content", [])
    if not isinstance(content, list) or not content:
        raise RuntimeError("invalid_gateway_tool_response_content")
    text = content[0].get("text", "")
    if not text:
        raise RuntimeError("empty_gateway_tool_response_content")
    return json.loads(text)


def strip_gateway_tool_prefix(tool_name: str) -> str:
    if "__" not in tool_name:
        return tool_name
    return re.split(r"__+", tool_name, maxsplit=1)[1]


def canonical_tool_operation(tool_name: str) -> str:
    name = strip_gateway_tool_prefix(tool_name).strip()
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


def scoped_tool_suffixes_for_intent(intent: str) -> List[str]:
    return MCP_TOOL_SCOPE_BY_INTENT.get(intent, MCP_TOOL_SCOPE_BY_INTENT["general_triage"])


def scope_gateway_tools_by_intent(tools: List[Dict[str, Any]], intent: str) -> List[Dict[str, Any]]:
    allowed_suffixes = set(scoped_tool_suffixes_for_intent(intent))
    scoped = [tool for tool in tools if strip_gateway_tool_prefix(str(tool.get("name", ""))) in allowed_suffixes]
    if not scoped:
        raise RuntimeError(f"empty_scoped_tool_catalog:intent={intent}")
    return scoped


def build_failure_issue(issue_key: str, failure_reason: str) -> Dict[str, Any]:
    return {
        "key": issue_key,
        "summary": "",
        "status": "Unknown",
        "issue_type": "Unknown",
        "priority": "None",
        "labels": [],
        "updated": "",
        "description": "",
        "comment_count": 0,
        "failure_reason": failure_reason,
    }


def _tool_prompt_lines(tools: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for tool in tools:
        tool_name = str(tool.get("name", ""))
        tool_description = str(tool.get("description", "")).strip()
        lines.append(f"- {tool_name}: {tool_description[:220]}")
    return "\n".join(lines)


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
        "Return strict JSON only: {\"tool\":\"<name>\",\"reason\":\"<short reason>\"}.\n"
        "Scoped tool list:\n"
        f"{_tool_prompt_lines(selection.tools)}"
    )
    raw = _call_bedrock(model_id=config.model_id, prompt=prompt, region=config.region)
    parsed = _extract_json_object(raw)
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


def generate_customer_response(
    intake: Dict[str, Any],
    tool_result: Dict[str, Any],
    model_id: str,
    region: str,
    dry_run: bool = False,
) -> Dict[str, Any]:
    if dry_run:
        return {
            "customer_response": f"Acknowledged {intake['issue_key']}. Current status is {tool_result.get('status', 'Unknown')}.",
            "internal_actions": ["Validate fix scope", "Confirm release timeline", "Prepare customer-safe update"],
            "risk_level": "medium" if intake.get("intent") == "bug_triage" else "low",
        }

    prompt = (
        "You are an enterprise support SOP assistant.\n"
        "Generate a concise customer-safe update plus internal actions.\n"
        "Return strict JSON with keys: customer_response (string), internal_actions (array of strings), risk_level (low|medium|high).\n"
        f"Intake JSON: {json.dumps(intake)}\n"
        f"Tool JSON: {json.dumps(tool_result)}"
    )

    raw = _call_bedrock(model_id=model_id, prompt=prompt, region=region)
    parsed = _extract_json_object(raw)

    actions = parsed.get("internal_actions", [])
    if not isinstance(actions, list):
        raise ValueError("invalid_internal_actions")

    return {
        "customer_response": str(parsed.get("customer_response", "")).strip(),
        "internal_actions": [str(item) for item in actions],
        "risk_level": str(parsed.get("risk_level", "medium")).lower(),
    }


def persist_artifact(bucket_name: str, payload: Dict[str, Any], prefix: str = "pipeline-results") -> str:
    run_at = _safe_token(payload.get("started_at", utc_now()).replace(":", "").replace("+00:00", "Z"), "run")
    flow = _safe_token(payload.get("flow", "unknown"))
    case_id = _safe_token(payload.get("case_id", "unknown"))
    key = (
        f"{prefix}/{datetime.now(timezone.utc).strftime('%Y/%m/%d')}/"
        f"{run_at}__{flow}__{case_id}__{uuid.uuid4()}.json"
    )
    s3_client = boto3.client("s3")
    s3_client.put_object(Bucket=bucket_name, Key=key, Body=json.dumps(payload, indent=2).encode("utf-8"), ContentType="application/json")
    return key


def base_event_with_metrics(event: Dict[str, Any]) -> Dict[str, Any]:
    enriched = dict(event)
    enriched.setdefault("metrics", {})
    enriched["metrics"].setdefault("stages", [])
    enriched["started_at"] = enriched.get("started_at") or utc_now()
    return enriched


def append_stage_metric(event: Dict[str, Any], stage: str, started: float, extra: Dict[str, Any]) -> Dict[str, Any]:
    elapsed_ms = round((time.time() - started) * 1000, 2)
    event["metrics"]["stages"].append({"stage": stage, "latency_ms": elapsed_ms, **extra})
    event["metrics"][f"{stage}_latency_ms"] = elapsed_ms
    return event


def selected_model_id(event: Dict[str, Any]) -> str:
    return event.get("model_id") or os.environ.get("BEDROCK_MODEL_ID", "eu.amazon.nova-lite-v1:0")


def selected_region(event: Dict[str, Any]) -> str:
    return event.get("bedrock_region") or os.environ.get("BEDROCK_REGION", os.environ.get("AWS_REGION", "eu-west-1"))


def selected_gateway_url(event: Dict[str, Any]) -> str:
    gateway_url = event.get("mcp_gateway_url") or os.environ.get("MCP_GATEWAY_URL", "")
    if not gateway_url:
        raise RuntimeError("MCP_GATEWAY_URL is required for MCP flow")
    validate_endpoint_url(
        url=gateway_url,
        env_var_name="MCP_GATEWAY_ALLOWED_HOSTS",
        default_allowed_hosts=".gateway.bedrock-agentcore.eu-west-1.amazonaws.com",
    )
    return gateway_url
