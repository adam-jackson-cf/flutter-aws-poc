import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Protocol

# Ensure repository root is importable when running as `python3 evals/run_eval.py`.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evals.aws_pipeline_runner import (
    AgentCoreRuntimeRunner,
    AgentCoreRuntimeRunnerConfig,
    PipelineRunRequest,
    PipelineRunResult,
)
from evals.cloudwatch_publish import CloudWatchPublishConfig, publish_eval_summary_metrics
from evals.judge import BedrockJudge
from evals.metrics import (
    aggregate_case_metrics,
    aggregate_judge_metrics,
    build_overall_reflection,
    lexical_cosine_similarity,
)
from runtime.sop_agent.domain.contracts import CONTRACT_VERSION as TOOL_CONTRACT_VERSION
from runtime.sop_agent.domain.tooling import (
    canonical_tool_operation as _domain_canonical_tool_operation,
    issue_payload_complete_for_tool as _domain_issue_payload_complete_for_tool,
    strip_target_prefix as _domain_strip_target_prefix,
)

REQUIRED_CASE_KEYS = {
    "case_id",
    "request_text",
    "expected_intent",
    "expected_issue_key",
    "expected_response_anchor",
    "expected_tool",
}

EXPECTED_TOOLS_BY_FLOW = {
    "native": {
        "jira_api_get_issue_by_key",
        "jira_api_get_issue_status_snapshot",
        "jira_api_get_issue_priority_context",
        "jira_api_get_issue_labels",
        "jira_api_get_issue_project_key",
        "jira_api_get_issue_update_timestamp",
        "jira_api_write_issue_followup_note",
    },
    "mcp": {
        "jira_get_issue_by_key",
        "jira_get_issue_status_snapshot",
        "jira_get_issue_priority_context",
        "jira_get_issue_labels",
        "jira_get_issue_project_key",
        "jira_get_issue_update_timestamp",
        "jira_write_issue_followup_note",
        "jira_get_issue_risk_flags",
    },
}


class PipelineRunner(Protocol):
    def preflight_identity(self) -> Dict[str, str]:
        ...

    def run_case(self, request: PipelineRunRequest) -> PipelineRunResult:
        ...


@dataclass(frozen=True)
class CaseRunContext:
    flow: str
    scope: str
    iteration: int


@dataclass(frozen=True)
class EvaluationConfig:
    dry_run: bool
    scope: str
    iterations: int
    model_id: str
    runtime_model_id: str
    bedrock_region: str
    model_provider: str
    runner: PipelineRunner
    judge: BedrockJudge | None
    openai_reasoning_effort: str = "medium"
    openai_text_verbosity: str = "medium"
    openai_max_output_tokens: int = 2000
    pricing_input_per_1m_tokens_usd: float = 0.0
    pricing_output_per_1m_tokens_usd: float = 0.0
    llm_route_path: str = "gateway_service"
    execution_mode: str = "route_parity"
    mcp_binding_mode: str = "model_constructed_schema_validated"
    route_semantics_version: str = "2"


@dataclass(frozen=True)
class RunPayloadContext:
    pricing_snapshot: Dict[str, Any]
    evaluation: EvaluationConfig
    aws_identity: Dict[str, str]


@dataclass(frozen=True)
class ActualPayloadInput:
    intent_actual: str
    issue_key_actual: str
    selected_tool: str
    tool: str
    failure_reason: str
    generated_response: str
    run: PipelineRunResult


@dataclass(frozen=True)
class CaseMetricsPayloadInput:
    intent_match: bool
    issue_key_match: bool
    issue_key_resolution_match: bool
    tool_failure: bool
    tool_match: bool
    issue_payload_complete: bool
    business_success: bool
    failure_reason: str
    total_latency_ms: float
    response_similarity: float
    call_construction_failure: bool
    call_construction_attempts: int
    call_construction_retries: int
    call_construction_recovered: bool
    grounding_failure: bool
    grounding_attempts: int
    grounding_retries: int
    write_case: bool
    write_tool_selected: bool
    write_tool_match: bool
    llm_input_tokens: int
    llm_output_tokens: int
    llm_total_tokens: int


@dataclass(frozen=True)
class CaseOutcome:
    intent_actual: str
    issue_key_actual: str
    selected_tool: str
    tool: str
    failure_reason: str
    issue_payload_complete: bool
    tool_failure: bool
    intent_match: bool
    issue_key_match: bool
    issue_key_resolution_match: bool
    tool_match: bool
    business_success: bool
    total_latency_ms: float
    response_similarity: float
    call_construction_failure: bool
    call_construction_attempts: int
    call_construction_retries: int
    call_construction_recovered: bool
    grounding_failure: bool
    grounding_attempts: int
    grounding_retries: int
    write_case: bool
    write_tool_selected: bool
    write_tool_match: bool
    llm_input_tokens: int
    llm_output_tokens: int
    llm_total_tokens: int


@dataclass(frozen=True)
class CaseOutcomeInput:
    case: Dict[str, Any]
    context: CaseRunContext
    run_payload: Dict[str, Any]
    run_metrics: Dict[str, Any]
    tool_result: Dict[str, Any]
    expected_tool: str
    total_latency_ms: float
    response_similarity: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run SOP evaluation through deployed AgentCore runtime")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--flow", choices=["native", "mcp", "both"], required=True)
    parser.add_argument("--output", default="")
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--scope", choices=["route", "full"], default="route")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--agent-runtime-arn",
        default=os.environ.get("AGENT_RUNTIME_ARN", os.environ.get("AGENTCORE_RUNTIME_ARN", "")),
    )
    parser.add_argument("--agent-runtime-qualifier", default=os.environ.get("AGENT_RUNTIME_QUALIFIER", "production"))
    parser.add_argument("--aws-profile", default=os.environ.get("AWS_PROFILE", ""))
    parser.add_argument("--aws-region", default=os.environ.get("AWS_REGION", ""))
    parser.add_argument("--poll-interval-seconds", type=float, default=2.0)
    parser.add_argument("--execution-timeout-seconds", type=int, default=900)
    parser.add_argument("--model-id", default=os.environ.get("MODEL_ID", "eu.amazon.nova-lite-v1:0"))
    parser.add_argument(
        "--runtime-model-id",
        default=os.environ.get("RUNTIME_MODEL_ID", os.environ.get("MODEL_ID", "eu.amazon.nova-lite-v1:0")),
    )
    parser.add_argument("--bedrock-region", default=os.environ.get("BEDROCK_REGION", os.environ.get("AWS_REGION", "")))
    parser.add_argument("--model-provider", choices=["auto", "bedrock", "openai"], default=os.environ.get("MODEL_PROVIDER", "auto"))
    parser.add_argument("--openai-reasoning-effort", default=os.environ.get("OPENAI_REASONING_EFFORT", "medium"))
    parser.add_argument("--openai-text-verbosity", default=os.environ.get("OPENAI_TEXT_VERBOSITY", "medium"))
    parser.add_argument("--openai-max-output-tokens", type=int, default=int(os.environ.get("OPENAI_MAX_OUTPUT_TOKENS", "2000")))
    parser.add_argument(
        "--model-pricing-catalog",
        default=os.environ.get("MODEL_PRICING_CATALOG", "evals/model_pricing_usd_per_1m_tokens.json"),
    )
    parser.add_argument("--price-input-per-1m-tokens-usd", default=os.environ.get("PRICE_INPUT_PER_1M_TOKENS_USD", ""))
    parser.add_argument("--price-output-per-1m-tokens-usd", default=os.environ.get("PRICE_OUTPUT_PER_1M_TOKENS_USD", ""))
    parser.add_argument("--publish-cloudwatch", action="store_true")
    parser.add_argument("--cloudwatch-namespace", default="FlutterAgentCorePoc/Evals")
    parser.add_argument("--execution-mode", default=os.environ.get("EXECUTION_MODE", "route_parity"))
    parser.add_argument(
        "--mcp-binding-mode",
        default=os.environ.get("MCP_BINDING_MODE", "model_constructed_schema_validated"),
    )
    parser.add_argument(
        "--route-semantics-version",
        default=os.environ.get("ROUTE_SEMANTICS_VERSION", "2"),
    )
    parser.add_argument("--enable-judge", action="store_true")
    parser.add_argument(
        "--judge-model-id",
        default=os.environ.get(
            "BEDROCK_JUDGE_MODEL_ID",
            os.environ.get("BEDROCK_MODEL_ID", "eu.amazon.nova-lite-v1:0"),
        ),
    )
    parser.add_argument("--judge-region", default=os.environ.get("BEDROCK_REGION", os.environ.get("AWS_REGION", "")))
    return parser.parse_args()


def utc_compact_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def sanitize_run_id(run_id: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "-", run_id.strip())
    return cleaned or utc_compact_now()


def load_dataset(path: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for index, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        parsed = json.loads(line)
        if not isinstance(parsed, dict):
            raise ValueError(f"dataset row {index} must be an object")

        missing = REQUIRED_CASE_KEYS.difference(parsed.keys())
        if missing:
            raise ValueError(f"dataset row {index} missing required keys: {sorted(missing)}")

        expected_tool = parsed.get("expected_tool")
        if not isinstance(expected_tool, dict):
            raise ValueError(f"dataset row {index} expected_tool must be an object with native/mcp")

        for flow in ("native", "mcp"):
            selected = str(expected_tool.get(flow, "")).strip()
            if not selected:
                raise ValueError(f"dataset row {index} expected_tool.{flow} is required")
            if selected not in EXPECTED_TOOLS_BY_FLOW[flow]:
                raise ValueError(f"dataset row {index} expected_tool.{flow} is not supported: {selected}")
        rows.append(parsed)
    return rows


def _strip_gateway_tool_prefix(tool_name: str) -> str:
    return _domain_strip_target_prefix(tool_name)


def _canonical_tool_operation(tool_name: str) -> str:
    return _domain_canonical_tool_operation(tool_name)


def _issue_payload_complete_for_tool(tool_result: Dict[str, Any], tool_name: str) -> bool:
    return _domain_issue_payload_complete_for_tool(tool_result=tool_result, tool_name=tool_name)


def expected_tool_for_flow(case: Dict[str, Any], flow: str) -> str:
    selected = str(case["expected_tool"][flow]).strip()
    if flow == "mcp":
        selected = _strip_gateway_tool_prefix(selected)
    return selected


def _string_value(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _actual_tool_fields(run_payload: Dict[str, Any]) -> tuple[str, str]:
    actual_payload = run_payload.get("actual")
    if not isinstance(actual_payload, dict):
        return "", ""
    return (
        _string_value(actual_payload.get("selected_tool")),
        _string_value(actual_payload.get("tool")),
    )


def _selection_payload_tool(flow: str, run_payload: Dict[str, Any]) -> str:
    selection_key = {"native": "native_selection", "mcp": "mcp_selection"}.get(flow)
    if not selection_key:
        return ""
    selection_payload = run_payload.get(selection_key)
    if not isinstance(selection_payload, dict):
        return ""
    return _string_value(selection_payload.get("selected_tool"))


def _selected_tool_for_flow(flow: str, run_payload: Dict[str, Any]) -> str:
    selection_tool = _selection_payload_tool(flow, run_payload)
    if selection_tool:
        return selection_tool
    actual_selected_tool, actual_tool = _actual_tool_fields(run_payload)
    if actual_selected_tool:
        return actual_selected_tool
    if actual_tool:
        return actual_tool
    if flow in {"native", "mcp"}:
        return ""
    return "jira_get_issue_by_key"


def _actual_tool_for_flow(run_payload: Dict[str, Any], selected_tool: str) -> str:
    actual_selected_tool, actual_tool = _actual_tool_fields(run_payload)
    if actual_tool:
        return actual_tool
    if actual_selected_tool:
        return actual_selected_tool
    return selected_tool


def _total_latency_ms(run_payload: Dict[str, Any], run_metrics: Dict[str, Any]) -> float:
    total_latency_ms = float(run_metrics.get("total_latency_ms", 0.0) or 0.0)
    if total_latency_ms > 0:
        return total_latency_ms

    stage_entries = run_payload.get("metrics", {}).get("stages", [])
    return sum(float(entry.get("latency_ms", 0.0)) for entry in stage_entries if isinstance(entry, dict))


def _response_text_and_similarity(scope: str, generated_response: Dict[str, Any], expected_response_anchor: str) -> tuple[str, float]:
    if scope != "full":
        return "", 0.0
    generated = str(generated_response.get("customer_response", ""))
    return generated, lexical_cosine_similarity(generated, expected_response_anchor)


def _expected_payload(case: Dict[str, Any], expected_tool: str) -> Dict[str, str]:
    payload = {
        "intent": case["expected_intent"],
        "issue_key": case["expected_issue_key"],
        "tool": expected_tool,
        "response_anchor": case["expected_response_anchor"],
    }
    adversarial_vector = str(case.get("adversarial_vector", "")).strip()
    if adversarial_vector:
        payload["adversarial_vector"] = adversarial_vector
    return payload


def _actual_payload(payload_input: ActualPayloadInput) -> Dict[str, str]:
    tool_name = payload_input.tool or payload_input.selected_tool
    return {
        "intent": payload_input.intent_actual,
        "issue_key": payload_input.issue_key_actual,
        "selected_tool": payload_input.selected_tool,
        "tool": tool_name,
        "failure_reason": payload_input.failure_reason,
        "customer_response": payload_input.generated_response,
        "execution_arn": payload_input.run.execution_arn,
        "artifact_s3_uri": payload_input.run.artifact_s3_uri,
    }


def _case_metrics_payload(payload_input: CaseMetricsPayloadInput) -> Dict[str, Any]:
    business_success = bool(payload_input.business_success)
    return {
        "intent_match": payload_input.intent_match,
        "issue_key_match": payload_input.issue_key_match,
        "issue_key_resolution_match": payload_input.issue_key_resolution_match,
        "tool_failure": payload_input.tool_failure,
        "tool_match": payload_input.tool_match,
        "issue_payload_complete": payload_input.issue_payload_complete,
        "business_success": business_success,
        "success": business_success,
        "failure_reason": payload_input.failure_reason,
        "latency_ms": payload_input.total_latency_ms,
        "response_similarity": payload_input.response_similarity,
        "call_construction_failure": payload_input.call_construction_failure,
        "call_construction_attempts": payload_input.call_construction_attempts,
        "call_construction_retries": payload_input.call_construction_retries,
        "call_construction_recovered": payload_input.call_construction_recovered,
        "grounding_failure": payload_input.grounding_failure,
        "grounding_attempts": payload_input.grounding_attempts,
        "grounding_retry_count": payload_input.grounding_retries,
        "write_case": payload_input.write_case,
        "write_tool_selected": payload_input.write_tool_selected,
        "write_tool_match": payload_input.write_tool_match,
        "llm_input_tokens": payload_input.llm_input_tokens,
        "llm_output_tokens": payload_input.llm_output_tokens,
        "llm_total_tokens": payload_input.llm_total_tokens,
    }


def _to_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    return 0


def _to_float(value: Any) -> float:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _parse_positive_float(raw: str, *, field_name: str) -> float:
    value = raw.strip()
    if not value:
        raise ValueError(f"{field_name}_missing")
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(f"{field_name}_invalid") from exc
    if parsed <= 0:
        raise ValueError(f"{field_name}_must_be_positive")
    return parsed


def _estimate_cost_usd(
    *,
    llm_input_tokens: float,
    llm_output_tokens: float,
    input_per_1m_tokens_usd: float,
    output_per_1m_tokens_usd: float,
) -> float:
    normalized_input = max(0.0, llm_input_tokens)
    normalized_output = max(0.0, llm_output_tokens)
    return (normalized_input / 1_000_000.0) * input_per_1m_tokens_usd + (normalized_output / 1_000_000.0) * output_per_1m_tokens_usd


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _pricing_override_values(args: argparse.Namespace) -> tuple[str, str]:
    input_override_raw = str(getattr(args, "price_input_per_1m_tokens_usd", "")).strip()
    output_override_raw = str(getattr(args, "price_output_per_1m_tokens_usd", "")).strip()
    if bool(input_override_raw) != bool(output_override_raw):
        raise ValueError("pricing_override_incomplete:set_both_input_and_output_overrides")
    return input_override_raw, output_override_raw


def _pricing_context(args: argparse.Namespace) -> tuple[str, str, str]:
    catalog_path = str(
        getattr(args, "model_pricing_catalog", "evals/model_pricing_usd_per_1m_tokens.json")
    ).strip()
    model_id = str(args.model_id).strip()
    reasoning_effort = str(getattr(args, "openai_reasoning_effort", "")).strip().lower()
    return catalog_path, model_id, reasoning_effort


def _pricing_snapshot_from_overrides(
    *,
    catalog_path: str,
    model_id: str,
    reasoning_effort: str,
    input_override_raw: str,
    output_override_raw: str,
) -> Dict[str, Any]:
    input_price = _parse_positive_float(
        input_override_raw,
        field_name="price_input_per_1m_tokens_usd",
    )
    output_price = _parse_positive_float(
        output_override_raw,
        field_name="price_output_per_1m_tokens_usd",
    )
    return {
        "source": "cli_override",
        "catalog_path": catalog_path,
        "catalog_version": "",
        "catalog_sha256": "",
        "model_id": model_id,
        "pricing_model_key": model_id,
        "reasoning_effort": reasoning_effort,
        "input_per_1m_tokens_usd": input_price,
        "output_per_1m_tokens_usd": output_price,
    }


def _resolve_pricing_catalog_path(catalog_path: str) -> Path:
    if not catalog_path:
        raise ValueError("model_pricing_catalog_missing")
    resolved = (REPO_ROOT / catalog_path).resolve() if not Path(catalog_path).is_absolute() else Path(catalog_path)
    if not resolved.exists():
        raise ValueError(f"model_pricing_catalog_missing:{resolved}")
    return resolved


def _load_pricing_catalog(path: Path) -> tuple[str, Dict[str, Any]]:
    catalog_raw = path.read_text(encoding="utf-8")
    try:
        catalog = json.loads(catalog_raw)
    except json.JSONDecodeError as exc:
        raise ValueError("model_pricing_catalog_invalid_json") from exc
    if not isinstance(catalog, dict):
        raise ValueError("model_pricing_catalog_invalid_object")
    return catalog_raw, catalog


def _pricing_model_entry(
    *,
    models: Dict[str, Any],
    model_id: str,
    reasoning_effort: str,
) -> tuple[str, Dict[str, Any]]:
    pricing_model_key = model_id
    reasoning_model_key = f"{model_id}:reasoning-{reasoning_effort}" if reasoning_effort else ""
    if reasoning_model_key and isinstance(models.get(reasoning_model_key), dict):
        pricing_model_key = reasoning_model_key
    model_entry = models.get(pricing_model_key)
    if not isinstance(model_entry, dict):
        raise ValueError(f"model_pricing_missing_for_model:{model_id}")
    return pricing_model_key, model_entry


def _valid_pricing_pair(model_id: str, model_entry: Dict[str, Any]) -> tuple[float, float]:
    input_price = _to_float(model_entry.get("input_per_1m_tokens_usd", 0.0))
    output_price = _to_float(model_entry.get("output_per_1m_tokens_usd", 0.0))
    if input_price <= 0 or output_price <= 0:
        raise ValueError(f"model_pricing_invalid_for_model:{model_id}")
    return input_price, output_price


def _pricing_snapshot_for_model(args: argparse.Namespace) -> Dict[str, Any]:
    input_override_raw, output_override_raw = _pricing_override_values(args)
    catalog_path, model_id, reasoning_effort = _pricing_context(args)
    if input_override_raw and output_override_raw:
        return _pricing_snapshot_from_overrides(
            catalog_path=catalog_path,
            model_id=model_id,
            reasoning_effort=reasoning_effort,
            input_override_raw=input_override_raw,
            output_override_raw=output_override_raw,
        )
    resolved_catalog_path = _resolve_pricing_catalog_path(catalog_path)
    catalog_raw, catalog = _load_pricing_catalog(resolved_catalog_path)
    models = catalog.get("models", {})
    if not isinstance(models, dict):
        raise ValueError("model_pricing_catalog_invalid_models")
    pricing_model_key, model_entry = _pricing_model_entry(
        models=models,
        model_id=model_id,
        reasoning_effort=reasoning_effort,
    )
    input_price, output_price = _valid_pricing_pair(model_id, model_entry)

    return {
        "source": "catalog",
        "catalog_path": str(resolved_catalog_path),
        "catalog_version": str(catalog.get("version", "")).strip(),
        "catalog_sha256": hashlib.sha256(catalog_raw.encode("utf-8")).hexdigest(),
        "model_id": model_id,
        "pricing_model_key": pricing_model_key,
        "reasoning_effort": reasoning_effort,
        "input_per_1m_tokens_usd": input_price,
        "output_per_1m_tokens_usd": output_price,
    }


def _derive_case_outcome(payload_input: CaseOutcomeInput) -> CaseOutcome:
    failure_reason = str(payload_input.tool_result.get("failure_reason", ""))
    issue_payload_complete = _issue_payload_complete_for_tool(payload_input.tool_result, payload_input.expected_tool)
    tool_failure = bool(payload_input.run_payload.get("tool_failure", payload_input.run_metrics.get("tool_failure", False)))
    intent_actual = str(payload_input.run_payload.get("intake", {}).get("intent", ""))
    issue_key_actual = str(payload_input.tool_result.get("key", ""))
    intake_issue_key = str(payload_input.run_payload.get("intake", {}).get("issue_key", ""))
    selected_tool = _selected_tool_for_flow(payload_input.context.flow, payload_input.run_payload)
    tool_name = _actual_tool_for_flow(payload_input.run_payload, selected_tool)
    intent_match = intent_actual == payload_input.case["expected_intent"]
    issue_key_match = issue_key_actual == payload_input.case["expected_issue_key"]
    issue_key_resolution_match = intake_issue_key == payload_input.case["expected_issue_key"]
    selected_operation = _canonical_tool_operation(selected_tool)
    expected_operation = _canonical_tool_operation(payload_input.expected_tool)
    tool_match = selected_operation == expected_operation
    business_success = bool((not tool_failure) and issue_payload_complete and intent_match and issue_key_match and tool_match)
    call_construction_attempts = _to_int(payload_input.run_metrics.get("call_construction_attempts", 0))
    call_construction_retries = _to_int(payload_input.run_metrics.get("call_construction_retries", 0))
    call_construction_failure = bool(payload_input.run_metrics.get("call_construction_failure", False))
    call_construction_recovered = bool(payload_input.run_metrics.get("call_construction_recovered", False))
    grounding_failure = bool(payload_input.run_metrics.get("grounding_failure", False))
    grounding_attempts = _to_int(payload_input.run_metrics.get("grounding_attempts", 0))
    grounding_retries = _to_int(payload_input.run_metrics.get("grounding_retry_count", 0))
    write_case = expected_operation.startswith("write_")
    write_tool_selected = selected_operation.startswith("write_")
    write_tool_match = bool(write_case and tool_match)
    llm_input_tokens = _to_int(payload_input.run_metrics.get("llm_input_tokens", 0))
    llm_output_tokens = _to_int(payload_input.run_metrics.get("llm_output_tokens", 0))
    llm_total_tokens = _to_int(payload_input.run_metrics.get("llm_total_tokens", 0))
    return CaseOutcome(
        intent_actual=intent_actual,
        issue_key_actual=issue_key_actual,
        selected_tool=selected_tool,
        tool=tool_name,
        failure_reason=failure_reason,
        issue_payload_complete=issue_payload_complete,
        tool_failure=tool_failure,
        intent_match=intent_match,
        issue_key_match=issue_key_match,
        issue_key_resolution_match=issue_key_resolution_match,
        tool_match=tool_match,
        business_success=business_success,
        total_latency_ms=payload_input.total_latency_ms,
        response_similarity=payload_input.response_similarity,
        call_construction_failure=call_construction_failure,
        call_construction_attempts=call_construction_attempts,
        call_construction_retries=call_construction_retries,
        call_construction_recovered=call_construction_recovered,
        grounding_failure=grounding_failure,
        grounding_attempts=grounding_attempts,
        grounding_retries=grounding_retries,
        write_case=write_case,
        write_tool_selected=write_tool_selected,
        write_tool_match=write_tool_match,
        llm_input_tokens=llm_input_tokens,
        llm_output_tokens=llm_output_tokens,
        llm_total_tokens=llm_total_tokens,
    )


def _case_result_from_payload(case: Dict[str, Any], run: PipelineRunResult, context: CaseRunContext) -> Dict[str, Any]:
    run_payload = run.payload
    tool_result = run_payload.get("tool_result", {})
    generated_response = run_payload.get("generated_response", {})
    run_metrics = run_payload.get("run_metrics", {})

    expected_tool = expected_tool_for_flow(case, context.flow)
    generated, similarity = _response_text_and_similarity(
        scope=context.scope,
        generated_response=generated_response,
        expected_response_anchor=case["expected_response_anchor"],
    )

    total_latency_ms = _total_latency_ms(run_payload, run_metrics)
    outcome = _derive_case_outcome(
        CaseOutcomeInput(
            case=case,
            context=context,
            run_payload=run_payload,
            run_metrics=run_metrics,
            tool_result=tool_result,
            expected_tool=expected_tool,
            total_latency_ms=total_latency_ms,
            response_similarity=similarity,
        )
    )

    return {
        "iteration": context.iteration,
        "case_id": case["case_id"],
        "request_text": case["request_text"],
        "success": bool(outcome.business_success),
        "expected": _expected_payload(case=case, expected_tool=expected_tool),
        "actual": _actual_payload(
            ActualPayloadInput(
                intent_actual=outcome.intent_actual,
                issue_key_actual=outcome.issue_key_actual,
                selected_tool=outcome.selected_tool,
                tool=outcome.tool,
                failure_reason=outcome.failure_reason,
                generated_response=generated,
                run=run,
            )
        ),
        "metrics": _case_metrics_payload(
            CaseMetricsPayloadInput(
                intent_match=outcome.intent_match,
                issue_key_match=outcome.issue_key_match,
                issue_key_resolution_match=outcome.issue_key_resolution_match,
                tool_failure=outcome.tool_failure,
                tool_match=outcome.tool_match,
                issue_payload_complete=outcome.issue_payload_complete,
                business_success=outcome.business_success,
                failure_reason=outcome.failure_reason,
                total_latency_ms=outcome.total_latency_ms,
                response_similarity=outcome.response_similarity,
                call_construction_failure=outcome.call_construction_failure,
                call_construction_attempts=outcome.call_construction_attempts,
                call_construction_retries=outcome.call_construction_retries,
                call_construction_recovered=outcome.call_construction_recovered,
                grounding_failure=outcome.grounding_failure,
                grounding_attempts=outcome.grounding_attempts,
                grounding_retries=outcome.grounding_retries,
                write_case=outcome.write_case,
                write_tool_selected=outcome.write_tool_selected,
                write_tool_match=outcome.write_tool_match,
                llm_input_tokens=outcome.llm_input_tokens,
                llm_output_tokens=outcome.llm_output_tokens,
                llm_total_tokens=outcome.llm_total_tokens,
            )
        ),
    }


def _evaluate_single_case(
    flow: str,
    case: Dict[str, Any],
    iteration: int,
    config: EvaluationConfig,
) -> Dict[str, Any]:
    case_id = f"{case['case_id']}_it{iteration}"
    run = config.runner.run_case(
        PipelineRunRequest(
            flow=flow,
            request_text=case["request_text"],
            case_id=case_id,
            expected_tool=expected_tool_for_flow(case, flow),
            dry_run=config.dry_run,
            model_id=config.model_id,
            runtime_model_id=config.runtime_model_id,
            bedrock_region=config.bedrock_region,
            model_provider=config.model_provider,
            openai_reasoning_effort=config.openai_reasoning_effort,
            openai_text_verbosity=config.openai_text_verbosity,
            openai_max_output_tokens=config.openai_max_output_tokens,
            llm_route_path=config.llm_route_path,
            execution_mode=config.execution_mode,
            mcp_binding_mode=config.mcp_binding_mode,
            route_semantics_version=config.route_semantics_version,
        )
    )
    context = CaseRunContext(flow=flow, scope=config.scope, iteration=iteration)
    result = _case_result_from_payload(case=case, run=run, context=context)
    if config.judge is not None:
        result["judge"] = config.judge.score_case(result, scope=config.scope)
        result["metrics"]["judge_overall_score"] = float(result["judge"]["overall_score"])
    return result


def _count_failure_reasons(results: List[Dict[str, Any]]) -> Dict[str, int]:
    failure_reason_counts: Dict[str, int] = {}
    for row in results:
        reason = str(row["metrics"].get("failure_reason", "")).strip()
        if not reason:
            continue
        failure_reason_counts[reason] = failure_reason_counts.get(reason, 0) + 1
    return failure_reason_counts


def _intent_usage_bucket_template() -> Dict[str, float | int]:
    return {
        "case_count": 0,
        "business_success_count": 0,
        "total_llm_input_tokens": 0.0,
        "total_llm_output_tokens": 0.0,
        "total_llm_total_tokens": 0.0,
    }


def _accumulate_intent_usage_bucket(
    totals: Dict[str, Dict[str, float | int]],
    row: Dict[str, Any],
) -> None:
    expected = row.get("expected", {})
    metrics = row.get("metrics", {})
    intent = str(expected.get("intent", "")).strip() or "unknown"
    bucket = totals.setdefault(intent, _intent_usage_bucket_template())
    bucket["case_count"] = int(bucket["case_count"]) + 1
    if bool(metrics.get("business_success", False)):
        bucket["business_success_count"] = int(bucket["business_success_count"]) + 1
    bucket["total_llm_input_tokens"] = float(bucket["total_llm_input_tokens"]) + _to_float(metrics.get("llm_input_tokens", 0.0))
    bucket["total_llm_output_tokens"] = float(bucket["total_llm_output_tokens"]) + _to_float(metrics.get("llm_output_tokens", 0.0))
    bucket["total_llm_total_tokens"] = float(bucket["total_llm_total_tokens"]) + _to_float(metrics.get("llm_total_tokens", 0.0))


def _intent_usage_bucket_output(
    bucket: Dict[str, float | int],
    *,
    pricing_input_per_1m_tokens_usd: float,
    pricing_output_per_1m_tokens_usd: float,
) -> Dict[str, float | int]:
    case_count = int(bucket["case_count"])
    success_count = int(bucket["business_success_count"])
    total_input = float(bucket["total_llm_input_tokens"])
    total_output = float(bucket["total_llm_output_tokens"])
    total_tokens = float(bucket["total_llm_total_tokens"])
    return {
        "case_count": case_count,
        "business_success_rate": _safe_ratio(float(success_count), float(case_count)),
        "total_llm_input_tokens": total_input,
        "total_llm_output_tokens": total_output,
        "total_llm_total_tokens": total_tokens,
        "mean_llm_input_tokens": _safe_ratio(total_input, float(case_count)),
        "mean_llm_output_tokens": _safe_ratio(total_output, float(case_count)),
        "mean_llm_total_tokens": _safe_ratio(total_tokens, float(case_count)),
        "total_estimated_cost_usd": _estimate_cost_usd(
            llm_input_tokens=total_input,
            llm_output_tokens=total_output,
            input_per_1m_tokens_usd=pricing_input_per_1m_tokens_usd,
            output_per_1m_tokens_usd=pricing_output_per_1m_tokens_usd,
        ),
        "mean_estimated_cost_usd": _estimate_cost_usd(
            llm_input_tokens=_safe_ratio(total_input, float(case_count)),
            llm_output_tokens=_safe_ratio(total_output, float(case_count)),
            input_per_1m_tokens_usd=pricing_input_per_1m_tokens_usd,
            output_per_1m_tokens_usd=pricing_output_per_1m_tokens_usd,
        ),
    }


def _token_usage_by_intent(
    results: List[Dict[str, Any]],
    *,
    pricing_input_per_1m_tokens_usd: float,
    pricing_output_per_1m_tokens_usd: float,
) -> Dict[str, Dict[str, float | int]]:
    totals: Dict[str, Dict[str, float | int]] = {}
    for row in results:
        _accumulate_intent_usage_bucket(totals, row)

    output: Dict[str, Dict[str, float | int]] = {}
    for intent in sorted(totals):
        output[intent] = _intent_usage_bucket_output(
            totals[intent],
            pricing_input_per_1m_tokens_usd=pricing_input_per_1m_tokens_usd,
            pricing_output_per_1m_tokens_usd=pricing_output_per_1m_tokens_usd,
        )
    return output


def _adversarial_vector_breakdown(
    results: List[Dict[str, Any]],
    *,
    pricing_input_per_1m_tokens_usd: float,
    pricing_output_per_1m_tokens_usd: float,
) -> Dict[str, Dict[str, float | int]]:
    totals: Dict[str, Dict[str, float | int]] = {}
    for row in results:
        expected = row.get("expected", {})
        metrics = row.get("metrics", {})
        vector = str(expected.get("adversarial_vector", "")).strip()
        if not vector:
            continue
        bucket = totals.setdefault(vector, _adversarial_bucket_template())
        _accumulate_adversarial_bucket(bucket, metrics)

    output: Dict[str, Dict[str, float | int]] = {}
    for vector in sorted(totals):
        output[vector] = _adversarial_bucket_output(
            bucket=totals[vector],
            pricing_input_per_1m_tokens_usd=pricing_input_per_1m_tokens_usd,
            pricing_output_per_1m_tokens_usd=pricing_output_per_1m_tokens_usd,
        )
    return output


def _adversarial_bucket_template() -> Dict[str, float | int]:
    return {
        "case_count": 0,
        "business_success_count": 0,
        "tool_failure_count": 0,
        "tool_match_count": 0,
        "issue_key_resolution_match_count": 0,
        "grounding_failure_count": 0,
        "call_construction_failure_count": 0,
        "write_case_count": 0,
        "write_tool_match_count": 0,
        "total_latency_ms": 0.0,
        "total_llm_input_tokens": 0.0,
        "total_llm_output_tokens": 0.0,
        "total_llm_total_tokens": 0.0,
    }


def _accumulate_adversarial_bucket(
    bucket: Dict[str, float | int],
    metrics: Dict[str, Any],
) -> None:
    bucket["case_count"] = int(bucket["case_count"]) + 1
    if bool(metrics.get("business_success", False)):
        bucket["business_success_count"] = int(bucket["business_success_count"]) + 1
    if bool(metrics.get("tool_failure", False)):
        bucket["tool_failure_count"] = int(bucket["tool_failure_count"]) + 1
    if bool(metrics.get("tool_match", False)):
        bucket["tool_match_count"] = int(bucket["tool_match_count"]) + 1
    if bool(metrics.get("issue_key_resolution_match", False)):
        bucket["issue_key_resolution_match_count"] = int(bucket["issue_key_resolution_match_count"]) + 1
    if bool(metrics.get("grounding_failure", False)):
        bucket["grounding_failure_count"] = int(bucket["grounding_failure_count"]) + 1
    if bool(metrics.get("call_construction_failure", False)):
        bucket["call_construction_failure_count"] = int(bucket["call_construction_failure_count"]) + 1
    if bool(metrics.get("write_case", False)):
        bucket["write_case_count"] = int(bucket["write_case_count"]) + 1
        if bool(metrics.get("write_tool_match", False)):
            bucket["write_tool_match_count"] = int(bucket["write_tool_match_count"]) + 1
    bucket["total_latency_ms"] = float(bucket["total_latency_ms"]) + _to_float(metrics.get("latency_ms", 0.0))
    bucket["total_llm_input_tokens"] = float(bucket["total_llm_input_tokens"]) + _to_float(metrics.get("llm_input_tokens", 0.0))
    bucket["total_llm_output_tokens"] = float(bucket["total_llm_output_tokens"]) + _to_float(metrics.get("llm_output_tokens", 0.0))
    bucket["total_llm_total_tokens"] = float(bucket["total_llm_total_tokens"]) + _to_float(metrics.get("llm_total_tokens", 0.0))


def _adversarial_bucket_output(
    *,
    bucket: Dict[str, float | int],
    pricing_input_per_1m_tokens_usd: float,
    pricing_output_per_1m_tokens_usd: float,
) -> Dict[str, float | int]:
    case_count = int(bucket["case_count"])
    business_success_count = int(bucket["business_success_count"])
    tool_failure_count = int(bucket["tool_failure_count"])
    tool_match_count = int(bucket["tool_match_count"])
    issue_key_resolution_match_count = int(bucket["issue_key_resolution_match_count"])
    grounding_failure_count = int(bucket["grounding_failure_count"])
    call_construction_failure_count = int(bucket["call_construction_failure_count"])
    write_case_count = int(bucket["write_case_count"])
    write_tool_match_count = int(bucket["write_tool_match_count"])
    total_latency_ms = float(bucket["total_latency_ms"])
    total_llm_input_tokens = float(bucket["total_llm_input_tokens"])
    total_llm_output_tokens = float(bucket["total_llm_output_tokens"])
    total_llm_total_tokens = float(bucket["total_llm_total_tokens"])
    return {
        "case_count": case_count,
        "business_success_rate": _safe_ratio(float(business_success_count), float(case_count)),
        "tool_failure_rate": _safe_ratio(float(tool_failure_count), float(case_count)),
        "tool_match_rate": _safe_ratio(float(tool_match_count), float(case_count)),
        "issue_key_resolution_match_rate": _safe_ratio(float(issue_key_resolution_match_count), float(case_count)),
        "grounding_failure_rate": _safe_ratio(float(grounding_failure_count), float(case_count)),
        "call_construction_failure_rate": _safe_ratio(float(call_construction_failure_count), float(case_count)),
        "write_case_count": write_case_count,
        "write_tool_match_rate": _safe_ratio(float(write_tool_match_count), float(write_case_count)),
        "mean_latency_ms": _safe_ratio(total_latency_ms, float(case_count)),
        "total_llm_input_tokens": total_llm_input_tokens,
        "total_llm_output_tokens": total_llm_output_tokens,
        "mean_llm_total_tokens": _safe_ratio(total_llm_total_tokens, float(case_count)),
        "total_llm_total_tokens": total_llm_total_tokens,
        "total_estimated_cost_usd": _estimate_cost_usd(
            llm_input_tokens=total_llm_input_tokens,
            llm_output_tokens=total_llm_output_tokens,
            input_per_1m_tokens_usd=pricing_input_per_1m_tokens_usd,
            output_per_1m_tokens_usd=pricing_output_per_1m_tokens_usd,
        ),
        "mean_estimated_cost_usd": _estimate_cost_usd(
            llm_input_tokens=_safe_ratio(total_llm_input_tokens, float(case_count)),
            llm_output_tokens=_safe_ratio(total_llm_output_tokens, float(case_count)),
            input_per_1m_tokens_usd=pricing_input_per_1m_tokens_usd,
            output_per_1m_tokens_usd=pricing_output_per_1m_tokens_usd,
        ),
    }


def _selection_divergence_metrics(native_result: Dict[str, Any], mcp_result: Dict[str, Any]) -> Dict[str, float]:
    native_rows = native_result.get("cases", [])
    mcp_rows = mcp_result.get("cases", [])
    if not isinstance(native_rows, list) or not isinstance(mcp_rows, list):
        return {"selection_divergence_rate": 0.0, "selection_divergence_count": 0.0, "selection_divergence_compared_cases": 0.0}
    native_map = _rows_by_case_key(native_rows)
    mcp_map = _rows_by_case_key(mcp_rows)
    shared_case_keys = sorted(set(native_map.keys()).intersection(mcp_map.keys()))
    compared_cases = len(shared_case_keys)
    if compared_cases == 0:
        return {"selection_divergence_rate": 0.0, "selection_divergence_count": 0.0, "selection_divergence_compared_cases": 0.0}

    divergence_count = 0
    for case_key in shared_case_keys:
        if _selected_operation(native_map[case_key]) != _selected_operation(mcp_map[case_key]):
            divergence_count += 1

    return {
        "selection_divergence_rate": divergence_count / compared_cases,
        "selection_divergence_count": float(divergence_count),
        "selection_divergence_compared_cases": float(compared_cases),
    }


def _case_key(row: Dict[str, Any]) -> tuple[int, str]:
    iteration_value = row.get("iteration", 0)
    if isinstance(iteration_value, bool):
        iteration = int(iteration_value)
    elif isinstance(iteration_value, (int, float)):
        iteration = int(iteration_value)
    else:
        iteration = 0
    case_id = str(row.get("case_id", ""))
    return (iteration, case_id)


def _rows_by_case_key(rows: List[Dict[str, Any]]) -> Dict[tuple[int, str], Dict[str, Any]]:
    mapped: Dict[tuple[int, str], Dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        case_key = _case_key(row)
        if case_key[1]:
            mapped[case_key] = row
    return mapped


def _selected_operation(row: Dict[str, Any]) -> str:
    actual_payload = row.get("actual", {})
    if not isinstance(actual_payload, dict):
        return _canonical_tool_operation("")
    selected_tool = _string_value(actual_payload.get("selected_tool")) or _string_value(actual_payload.get("tool"))
    return _canonical_tool_operation(selected_tool)


def evaluate_flow(flow: str, cases: List[Dict[str, Any]], config: EvaluationConfig) -> Dict[str, Any]:
    results = []

    for iteration in range(config.iterations):
        for case in cases:
            results.append(
                _evaluate_single_case(
                    flow=flow,
                    case=case,
                    iteration=iteration + 1,
                    config=config,
                )
            )

    summary = aggregate_case_metrics(results)
    summary = {
        **summary,
        "total_estimated_cost_usd": _estimate_cost_usd(
            llm_input_tokens=float(summary.get("total_llm_input_tokens", 0.0)),
            llm_output_tokens=float(summary.get("total_llm_output_tokens", 0.0)),
            input_per_1m_tokens_usd=config.pricing_input_per_1m_tokens_usd,
            output_per_1m_tokens_usd=config.pricing_output_per_1m_tokens_usd,
        ),
        "mean_estimated_cost_usd": _estimate_cost_usd(
            llm_input_tokens=float(summary.get("mean_llm_input_tokens", 0.0)),
            llm_output_tokens=float(summary.get("mean_llm_output_tokens", 0.0)),
            input_per_1m_tokens_usd=config.pricing_input_per_1m_tokens_usd,
            output_per_1m_tokens_usd=config.pricing_output_per_1m_tokens_usd,
        ),
    }
    judge_summary = aggregate_judge_metrics(results)
    composite_reflection = build_overall_reflection(summary=summary, judge_summary=judge_summary)
    failure_reason_counts = _count_failure_reasons(results)

    return {
        "flow": flow,
        "scope": config.scope,
        "iterations": config.iterations,
        "summary": summary,
        "judge_summary": judge_summary,
        "composite_reflection": composite_reflection,
        "failure_reasons": failure_reason_counts,
        "token_usage_by_intent": _token_usage_by_intent(
            results,
            pricing_input_per_1m_tokens_usd=config.pricing_input_per_1m_tokens_usd,
            pricing_output_per_1m_tokens_usd=config.pricing_output_per_1m_tokens_usd,
        ),
        "adversarial_vector_summary": _adversarial_vector_breakdown(
            results,
            pricing_input_per_1m_tokens_usd=config.pricing_input_per_1m_tokens_usd,
            pricing_output_per_1m_tokens_usd=config.pricing_output_per_1m_tokens_usd,
        ),
        "cases": results,
    }


def _validate_runtime_args(args: argparse.Namespace) -> None:
    _require_non_empty_arg(
        getattr(args, "agent_runtime_arn", ""),
        "AGENT_RUNTIME_ARN is required (set env var or pass --agent-runtime-arn)",
    )
    _require_non_empty_arg(args.aws_region, "AWS_REGION is required (set env var or pass --aws-region)")
    _require_non_empty_arg(args.model_id, "model_id is required (set MODEL_ID or pass --model-id)")
    _require_non_empty_arg(
        args.runtime_model_id,
        "runtime model id is required (set RUNTIME_MODEL_ID or pass --runtime-model-id)",
    )
    _require_non_empty_arg(args.bedrock_region, "bedrock region is required (set BEDROCK_REGION or pass --bedrock-region)")
    _validate_judge_args(args)
    if int(args.openai_max_output_tokens) < 64:
        raise ValueError("openai max output tokens must be >= 64")


def _require_non_empty_arg(value: Any, message: str) -> None:
    if not value:
        raise ValueError(message)


def _validate_judge_args(args: argparse.Namespace) -> None:
    if not args.enable_judge:
        return
    _require_non_empty_arg(args.judge_region, "judge region is required when --enable-judge is set")
    if _is_bedrock_model_identifier(str(args.judge_model_id)):
        return
    raise ValueError(
        "judge model id must be a Bedrock model identifier or Bedrock ARN when --enable-judge is set"
    )


def _is_bedrock_model_identifier(model_id: str) -> bool:
    candidate = model_id.strip()
    if not candidate:
        return False
    if candidate.startswith("arn:aws:bedrock:"):
        return True
    if candidate.startswith("arn:aws-us-gov:bedrock:"):
        return True
    if candidate.startswith("arn:aws-cn:bedrock:"):
        return True
    return bool(re.fullmatch(r"[a-z]+(?:\.[a-z0-9-]+)+(?::[0-9]+)?", candidate))


def _build_runner(args: argparse.Namespace) -> PipelineRunner:
    runtime_qualifier = _runtime_qualifier(args)
    return AgentCoreRuntimeRunner(
        AgentCoreRuntimeRunnerConfig(
            agent_runtime_arn=getattr(args, "agent_runtime_arn", ""),
            aws_region=args.aws_region,
            aws_profile=args.aws_profile or None,
            expected_contract_version=TOOL_CONTRACT_VERSION,
            qualifier=runtime_qualifier,
        )
    )


def _runtime_qualifier(args: argparse.Namespace) -> str:
    qualifier = str(getattr(args, "agent_runtime_qualifier", "")).strip()
    scope = str(getattr(args, "scope", "route")).strip().lower()
    if scope == "route" and not qualifier:
        return "production"
    return qualifier


def _resolve_aws_identity(runner: PipelineRunner, dry_run: bool) -> Dict[str, str]:
    if dry_run:
        return {}
    try:
        identity = runner.preflight_identity()
    except Exception as exc:  # noqa: BLE001 - this is a preflight for clearer operator feedback
        raise RuntimeError("aws_auth_preflight_failed:refresh_credentials_and_retry") from exc
    if not identity.get("account") or not identity.get("arn"):
        raise RuntimeError("aws_auth_preflight_incomplete_identity")
    return identity


def _selected_flows(flow: str) -> List[str]:
    return [flow] if flow != "both" else ["native", "mcp"]


def _build_comparison_payload(results: List[Dict[str, Any]]) -> Dict[str, float]:
    native_result = results[0]
    mcp_result = results[1]
    native_summary = native_result["summary"]
    mcp_summary = mcp_result["summary"]
    native_composite = native_result["composite_reflection"]
    mcp_composite = mcp_result["composite_reflection"]
    comparison = {
        "tool_failure_delta": float(mcp_summary.get("tool_failure_rate", 0.0)) - float(native_summary.get("tool_failure_rate", 0.0)),
        "latency_delta_ms": float(mcp_summary.get("mean_latency_ms", 0.0)) - float(native_summary.get("mean_latency_ms", 0.0)),
        "response_similarity_delta": float(mcp_summary.get("mean_response_similarity", 0.0))
        - float(native_summary.get("mean_response_similarity", 0.0)),
        "issue_key_resolution_match_delta": float(mcp_summary.get("issue_key_resolution_match_rate", 0.0))
        - float(native_summary.get("issue_key_resolution_match_rate", 0.0)),
        "grounding_failure_delta": float(mcp_summary.get("grounding_failure_rate", 0.0))
        - float(native_summary.get("grounding_failure_rate", 0.0)),
        "grounding_retries_delta": float(mcp_summary.get("mean_grounding_retries", 0.0))
        - float(native_summary.get("mean_grounding_retries", 0.0)),
        "call_construction_failure_delta": float(mcp_summary.get("call_construction_failure_rate", 0.0))
        - float(native_summary.get("call_construction_failure_rate", 0.0)),
        "call_construction_retries_delta": float(mcp_summary.get("mean_call_construction_retries", 0.0))
        - float(native_summary.get("mean_call_construction_retries", 0.0)),
        "write_tool_match_delta": float(mcp_summary.get("write_tool_match_rate", 0.0))
        - float(native_summary.get("write_tool_match_rate", 0.0)),
        "llm_total_tokens_delta": float(mcp_summary.get("mean_llm_total_tokens", 0.0))
        - float(native_summary.get("mean_llm_total_tokens", 0.0)),
        "llm_input_tokens_delta": float(mcp_summary.get("mean_llm_input_tokens", 0.0))
        - float(native_summary.get("mean_llm_input_tokens", 0.0)),
        "llm_output_tokens_delta": float(mcp_summary.get("mean_llm_output_tokens", 0.0))
        - float(native_summary.get("mean_llm_output_tokens", 0.0)),
        "estimated_cost_usd_delta": float(mcp_summary.get("mean_estimated_cost_usd", 0.0))
        - float(native_summary.get("mean_estimated_cost_usd", 0.0)),
        "total_estimated_cost_usd_delta": float(mcp_summary.get("total_estimated_cost_usd", 0.0))
        - float(native_summary.get("total_estimated_cost_usd", 0.0)),
        "deterministic_release_score_delta": mcp_composite["deterministic_release_score"] - native_composite["deterministic_release_score"],
        "judge_diagnostic_score_delta": float(mcp_composite["judge_diagnostic_score"] or 0.0)
        - float(native_composite["judge_diagnostic_score"] or 0.0),
        "overall_reflection_score_delta": mcp_composite["overall_reflection_score"] - native_composite["overall_reflection_score"],
    }
    comparison.update(_selection_divergence_metrics(native_result, mcp_result))
    return comparison


def _write_eval_payload(payload: Dict[str, Any], output_path: str) -> None:
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _maybe_add_comparison(payload: Dict[str, Any], selected_flow: str) -> None:
    if selected_flow != "both":
        return
    payload["comparison"] = _build_comparison_payload(payload["results"])


def _route_semantics_args(args: argparse.Namespace) -> Dict[str, str]:
    return {
        "llm_route_path": "gateway_service",
        "execution_mode": str(getattr(args, "execution_mode", "route_parity")).strip()
        or "route_parity",
        "mcp_binding_mode": str(
            getattr(args, "mcp_binding_mode", "model_constructed_schema_validated")
        ).strip()
        or "model_constructed_schema_validated",
        "route_semantics_version": str(getattr(args, "route_semantics_version", "2")).strip() or "2",
    }


def _maybe_publish_cloudwatch(args: argparse.Namespace, payload: Dict[str, Any], run_id: str) -> None:
    if not args.publish_cloudwatch:
        return
    route_semantics = _route_semantics_args(args)
    publish_eval_summary_metrics(
        summaries=payload["results"],
        config=CloudWatchPublishConfig(
            namespace=args.cloudwatch_namespace,
            run_id=run_id,
            dataset=args.dataset,
            scope=args.scope,
            aws_region=args.aws_region,
            aws_profile=args.aws_profile or None,
            llm_route_path=route_semantics["llm_route_path"],
            execution_mode=route_semantics["execution_mode"],
            mcp_binding_mode=route_semantics["mcp_binding_mode"],
            route_semantics_version=route_semantics["route_semantics_version"],
        ),
    )
    print(f"PUBLISHED_CLOUDWATCH_NAMESPACE={args.cloudwatch_namespace}")


def _emit_run_output(output_path: str, dry_run: bool) -> None:
    print(f"WROTE_EVAL={output_path}")
    if dry_run:
        print("SMOKE_OK")


def _build_evaluation_config(
    *,
    args: argparse.Namespace,
    runner: PipelineRunner,
    judge: BedrockJudge | None,
    pricing_snapshot: Dict[str, Any],
) -> EvaluationConfig:
    route_semantics = _route_semantics_args(args)
    return EvaluationConfig(
        dry_run=args.dry_run,
        scope=args.scope,
        iterations=args.iterations,
        model_id=args.model_id,
        runtime_model_id=args.runtime_model_id,
        bedrock_region=args.bedrock_region,
        model_provider=args.model_provider,
        runner=runner,
        judge=judge,
        openai_reasoning_effort=str(args.openai_reasoning_effort).strip().lower() or "medium",
        openai_text_verbosity=str(args.openai_text_verbosity).strip().lower() or "medium",
        openai_max_output_tokens=int(args.openai_max_output_tokens),
        pricing_input_per_1m_tokens_usd=float(pricing_snapshot["input_per_1m_tokens_usd"]),
        pricing_output_per_1m_tokens_usd=float(pricing_snapshot["output_per_1m_tokens_usd"]),
        llm_route_path=route_semantics["llm_route_path"],
        execution_mode=route_semantics["execution_mode"],
        mcp_binding_mode=route_semantics["mcp_binding_mode"],
        route_semantics_version=route_semantics["route_semantics_version"],
    )


def _payload_model_section(args: argparse.Namespace, evaluation: EvaluationConfig) -> Dict[str, Any]:
    return {
        "model_id": args.model_id,
        "runtime_model_id": args.runtime_model_id,
        "bedrock_region": args.bedrock_region,
        "provider": args.model_provider,
        "openai_reasoning_effort": evaluation.openai_reasoning_effort,
        "openai_text_verbosity": evaluation.openai_text_verbosity,
        "openai_max_output_tokens": evaluation.openai_max_output_tokens,
        "pricing_input_per_1m_tokens_usd": evaluation.pricing_input_per_1m_tokens_usd,
        "pricing_output_per_1m_tokens_usd": evaluation.pricing_output_per_1m_tokens_usd,
    }


def _payload_pricing_snapshot_section(args: argparse.Namespace, pricing_snapshot: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "source": str(pricing_snapshot["source"]),
        "catalog_path": str(pricing_snapshot["catalog_path"]),
        "catalog_version": str(pricing_snapshot["catalog_version"]),
        "catalog_sha256": str(pricing_snapshot["catalog_sha256"]),
        "gateway_model_id": args.model_id,
        "pricing_model_key": str(pricing_snapshot["pricing_model_key"]),
        "reasoning_effort": str(pricing_snapshot["reasoning_effort"]),
        "runtime_model_id": args.runtime_model_id,
        "provider": args.model_provider,
        "pricing_unit": "usd_per_1m_tokens",
        "input_per_1m_tokens_usd": float(pricing_snapshot["input_per_1m_tokens_usd"]),
        "output_per_1m_tokens_usd": float(pricing_snapshot["output_per_1m_tokens_usd"]),
    }


def _build_run_payload(
    args: argparse.Namespace,
    run_id: str,
    results: List[Dict[str, Any]],
    context: RunPayloadContext,
) -> Dict[str, Any]:
    route_semantics = _route_semantics_args(args)
    return {
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": args.dataset,
        "dry_run": args.dry_run,
        "scope": args.scope,
        "iterations": args.iterations,
        "agent_runtime_arn": str(getattr(args, "agent_runtime_arn", "")),
        "aws_region": args.aws_region,
        "model": _payload_model_section(args, context.evaluation),
        "tool_contract_version": TOOL_CONTRACT_VERSION,
        "route_semantics": route_semantics,
        "model_pricing_snapshot": _payload_pricing_snapshot_section(args, context.pricing_snapshot),
        "model_parity": {
            "gateway_model_id": args.model_id,
            "runtime_model_id": args.runtime_model_id,
            "judge_model_id": args.judge_model_id if args.enable_judge else "",
            "provider": args.model_provider,
            "bedrock_region": args.bedrock_region,
            "llm_route_path": route_semantics["llm_route_path"],
            "execution_mode": route_semantics["execution_mode"],
            "mcp_binding_mode": route_semantics["mcp_binding_mode"],
            "route_semantics_version": route_semantics["route_semantics_version"],
            "tool_contract_version": TOOL_CONTRACT_VERSION,
        },
        "aws_identity": context.aws_identity,
        "judge": {
            "enabled": bool(args.enable_judge),
            "model_id": args.judge_model_id if args.enable_judge else "",
            "region": args.judge_region if args.enable_judge else "",
        },
        "results": results,
    }


def main() -> int:
    args = parse_args()
    _validate_runtime_args(args)
    pricing_snapshot = _pricing_snapshot_for_model(args)
    dataset = load_dataset(args.dataset)
    flows = _selected_flows(args.flow)
    run_id = sanitize_run_id(args.run_id) if args.run_id else utc_compact_now()
    runner = _build_runner(args)
    aws_identity = _resolve_aws_identity(runner=runner, dry_run=args.dry_run)
    judge = BedrockJudge(model_id=args.judge_model_id, region=args.judge_region) if args.enable_judge else None
    evaluation = _build_evaluation_config(
        args=args,
        runner=runner,
        judge=judge,
        pricing_snapshot=pricing_snapshot,
    )
    results = [evaluate_flow(flow=flow, cases=dataset, config=evaluation) for flow in flows]
    payload = _build_run_payload(
        args,
        run_id,
        results,
        RunPayloadContext(
            pricing_snapshot=pricing_snapshot,
            evaluation=evaluation,
            aws_identity=aws_identity,
        ),
    )
    _maybe_add_comparison(payload=payload, selected_flow=args.flow)
    default_output = f"reports/runs/{run_id}/eval/eval-{args.flow}-{args.scope}.json"
    output_path = args.output or default_output
    _write_eval_payload(payload=payload, output_path=output_path)
    _maybe_publish_cloudwatch(args=args, payload=payload, run_id=run_id)
    _emit_run_output(output_path=output_path, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
