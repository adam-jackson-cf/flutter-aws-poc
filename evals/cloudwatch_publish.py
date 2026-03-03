from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Sequence, TypedDict

import boto3


class SummaryPayload(TypedDict):
    intent_accuracy: float
    issue_key_accuracy: float
    tool_match_rate: float
    tool_failure_rate: float
    business_success_rate: float
    issue_payload_completeness_rate: float
    issue_key_resolution_match_rate: float
    mean_latency_ms: float
    mean_latency_success_ms: float
    mean_latency_failure_ms: float
    mean_response_similarity: float
    tool_failure_ci95_low: float
    tool_failure_ci95_high: float
    grounding_failure_rate: float
    mean_grounding_attempts: float
    mean_grounding_retries: float
    call_construction_failure_rate: float
    mean_call_construction_attempts: float
    mean_call_construction_retries: float
    call_construction_recovery_rate: float
    write_case_count: float
    write_tool_selected_rate: float
    write_tool_match_rate: float
    total_llm_input_tokens: float
    total_llm_output_tokens: float
    total_llm_total_tokens: float
    mean_llm_input_tokens: float
    mean_llm_output_tokens: float
    mean_llm_total_tokens: float
    total_estimated_cost_usd: float
    mean_estimated_cost_usd: float


class JudgeSummaryPayload(TypedDict, total=False):
    evaluated_cases: int
    coverage_rate: float
    mean_tool_choice_score: float
    mean_execution_reliability_score: float
    mean_response_quality_score: float
    mean_overall_score: float
    pass_rate: float


class CompositeReflectionPayload(TypedDict, total=False):
    deterministic_release_score: float
    overall_reflection_score: float
    release_gate_pass: bool
    divergence_flag: bool
    judge_diagnostic_score: float
    divergence: float


class EvalSummaryRow(TypedDict, total=False):
    flow: str
    summary: SummaryPayload
    judge_summary: JudgeSummaryPayload
    composite_reflection: CompositeReflectionPayload


@dataclass(frozen=True)
class MetricContext:
    run_id: str
    flow: str
    scope: str
    dataset: str
    llm_route_path: str
    execution_mode: str
    mcp_binding_mode: str
    route_semantics_version: str


@dataclass(frozen=True)
class CloudWatchPublishConfig:
    namespace: str
    run_id: str
    dataset: str
    scope: str
    aws_region: str
    aws_profile: str | None = None
    llm_route_path: str = "gateway_service"
    execution_mode: str = "route_parity"
    mcp_binding_mode: str = "model_constructed_schema_validated"
    route_semantics_version: str = "2"


Dimensions = Sequence[Dict[str, str]]


def _chunk(items: List[Dict], size: int) -> List[List[Dict]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _build_dimensions(context: MetricContext) -> tuple[Dict[str, str], ...]:
    return (
        {"Name": "RunId", "Value": context.run_id},
        {"Name": "Flow", "Value": context.flow},
        {"Name": "Scope", "Value": context.scope},
        {"Name": "Dataset", "Value": context.dataset},
        {"Name": "LlmRoutePath", "Value": context.llm_route_path},
        {"Name": "ExecutionMode", "Value": context.execution_mode},
        {"Name": "McpBindingMode", "Value": context.mcp_binding_mode},
        {"Name": "RouteSemanticsVersion", "Value": context.route_semantics_version},
    )


def _normalized_float(source: Mapping[str, object], *, source_key: str, metric_name: str) -> float:
    if source_key not in source:
        raise ValueError(f"metric_value_missing:{metric_name}:{source_key}")
    try:
        return float(source[source_key])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"metric_value_invalid:{metric_name}:{source_key}") from exc


def _metric_datum(metric_name: str, value: float, dimensions: Dimensions, unit: str | None = None) -> Dict[str, Any]:
    metric: Dict[str, Any] = {
        "MetricName": metric_name,
        "Value": value,
        "Dimensions": dimensions,
    }
    if unit is not None:
        metric["Unit"] = unit
    return metric


def _build_base_summary_metrics(summary: Mapping[str, object], dimensions: Dimensions) -> List[Dict[str, Any]]:
    metric_specs: List[tuple[str, str, str | None]] = [
        ("IntentAccuracy", "intent_accuracy", None),
        ("IssueKeyAccuracy", "issue_key_accuracy", None),
        ("ToolMatchRate", "tool_match_rate", None),
        ("ToolFailureRate", "tool_failure_rate", None),
        ("BusinessSuccessRate", "business_success_rate", None),
        ("IssuePayloadCompletenessRate", "issue_payload_completeness_rate", None),
        ("IssueKeyResolutionMatchRate", "issue_key_resolution_match_rate", None),
        ("MeanLatencyMs", "mean_latency_ms", "Milliseconds"),
        ("MeanLatencySuccessMs", "mean_latency_success_ms", "Milliseconds"),
        ("MeanLatencyFailureMs", "mean_latency_failure_ms", "Milliseconds"),
        ("MeanResponseSimilarity", "mean_response_similarity", None),
        ("ToolFailureCi95Low", "tool_failure_ci95_low", None),
        ("ToolFailureCi95High", "tool_failure_ci95_high", None),
    ]
    return [
        _metric_datum(
            metric_name=metric_name,
            value=_normalized_float(summary, source_key=source_key, metric_name=metric_name),
            dimensions=dimensions,
            unit=unit,
        )
        for metric_name, source_key, unit in metric_specs
    ]


def _build_extended_summary_metrics(summary: Mapping[str, object], dimensions: Dimensions) -> List[Dict[str, Any]]:
    metric_specs: List[tuple[str, str, str | None]] = [
        ("GroundingFailureRate", "grounding_failure_rate", None),
        ("MeanGroundingAttempts", "mean_grounding_attempts", "Count"),
        ("MeanGroundingRetries", "mean_grounding_retries", "Count"),
        ("CallConstructionFailureRate", "call_construction_failure_rate", None),
        ("MeanCallConstructionAttempts", "mean_call_construction_attempts", "Count"),
        ("MeanCallConstructionRetries", "mean_call_construction_retries", "Count"),
        ("CallConstructionRecoveryRate", "call_construction_recovery_rate", None),
        ("WriteCaseCount", "write_case_count", "Count"),
        ("WriteToolSelectedRate", "write_tool_selected_rate", None),
        ("WriteToolMatchRate", "write_tool_match_rate", None),
        ("TotalLlmInputTokens", "total_llm_input_tokens", "Count"),
        ("TotalLlmOutputTokens", "total_llm_output_tokens", "Count"),
        ("TotalLlmTotalTokens", "total_llm_total_tokens", "Count"),
        ("MeanLlmInputTokens", "mean_llm_input_tokens", "Count"),
        ("MeanLlmOutputTokens", "mean_llm_output_tokens", "Count"),
        ("MeanLlmTotalTokens", "mean_llm_total_tokens", "Count"),
        ("TotalEstimatedCostUsd", "total_estimated_cost_usd", None),
        ("MeanEstimatedCostUsd", "mean_estimated_cost_usd", None),
    ]
    return [
        _metric_datum(
            metric_name=metric_name,
            value=_normalized_float(summary, source_key=source_key, metric_name=metric_name),
            dimensions=dimensions,
            unit=unit,
        )
        for metric_name, source_key, unit in metric_specs
    ]


def _build_judge_metrics(judge_summary: object, dimensions: Dimensions) -> List[Dict[str, Any]]:
    if not isinstance(judge_summary, dict):
        return []
    if int(judge_summary.get("evaluated_cases", 0)) <= 0:
        return []
    metric_specs: List[tuple[str, str]] = [
        ("JudgeCoverageRate", "coverage_rate"),
        ("JudgeMeanToolChoiceScore", "mean_tool_choice_score"),
        ("JudgeMeanExecutionReliabilityScore", "mean_execution_reliability_score"),
        ("JudgeMeanResponseQualityScore", "mean_response_quality_score"),
        ("JudgeMeanOverallScore", "mean_overall_score"),
        ("JudgePassRate", "pass_rate"),
    ]
    return [
        _metric_datum(
            metric_name=metric_name,
            value=_normalized_float(judge_summary, source_key=source_key, metric_name=metric_name),
            dimensions=dimensions,
        )
        for metric_name, source_key in metric_specs
    ]


def _build_composite_reflection_metrics(composite_reflection: object, dimensions: Dimensions) -> List[Dict[str, Any]]:
    if not isinstance(composite_reflection, dict):
        return []

    metrics: List[Dict[str, Any]] = [
        _metric_datum(
            metric_name="DeterministicReleaseScore",
            value=_normalized_float(
                composite_reflection,
                source_key="deterministic_release_score",
                metric_name="DeterministicReleaseScore",
            ),
            dimensions=dimensions,
        ),
        _metric_datum(
            metric_name="OverallReflectionScore",
            value=_normalized_float(
                composite_reflection,
                source_key="overall_reflection_score",
                metric_name="OverallReflectionScore",
            ),
            dimensions=dimensions,
        ),
        _metric_datum(
            metric_name="ReleaseGatePass",
            value=1.0 if bool(composite_reflection["release_gate_pass"]) else 0.0,
            dimensions=dimensions,
        ),
        _metric_datum(
            metric_name="DivergenceFlag",
            value=1.0 if bool(composite_reflection["divergence_flag"]) else 0.0,
            dimensions=dimensions,
        ),
    ]

    judge_diagnostic_score = composite_reflection.get("judge_diagnostic_score")
    if judge_diagnostic_score is not None:
        metrics.append(
            _metric_datum(
                metric_name="JudgeDiagnosticScore",
                value=_normalized_float(
                    composite_reflection,
                    source_key="judge_diagnostic_score",
                    metric_name="JudgeDiagnosticScore",
                ),
                dimensions=dimensions,
            )
        )

    divergence = composite_reflection.get("divergence")
    if divergence is not None:
        metrics.append(
            _metric_datum(
                metric_name="ScoreDivergence",
                value=_normalized_float(composite_reflection, source_key="divergence", metric_name="ScoreDivergence"),
                dimensions=dimensions,
            )
        )

    return metrics


def publish_eval_summary_metrics(
    *,
    summaries: List[EvalSummaryRow],
    config: CloudWatchPublishConfig,
) -> None:
    if not summaries:
        raise ValueError("summaries must not be empty")
    if not config.namespace:
        raise ValueError("namespace is required")
    if not config.aws_region:
        raise ValueError("aws_region is required")

    session_kwargs = {"region_name": config.aws_region}
    if config.aws_profile:
        session_kwargs["profile_name"] = config.aws_profile
    session = boto3.Session(**session_kwargs)
    cloudwatch = session.client("cloudwatch")

    metric_data: List[Dict[str, Any]] = []
    for row in summaries:
        flow = str(row["flow"])
        summary = row["summary"]
        if not isinstance(summary, dict):
            raise ValueError("summary must be a dict")
        dimensions = _build_dimensions(
            MetricContext(
                run_id=config.run_id,
                flow=flow,
                scope=config.scope,
                dataset=config.dataset,
                llm_route_path=config.llm_route_path,
                execution_mode=config.execution_mode,
                mcp_binding_mode=config.mcp_binding_mode,
                route_semantics_version=config.route_semantics_version,
            )
        )
        metric_data.extend(_build_base_summary_metrics(summary=summary, dimensions=dimensions))
        metric_data.extend(_build_extended_summary_metrics(summary=summary, dimensions=dimensions))
        metric_data.extend(_build_judge_metrics(judge_summary=row.get("judge_summary"), dimensions=dimensions))
        metric_data.extend(
            _build_composite_reflection_metrics(
                composite_reflection=row.get("composite_reflection"),
                dimensions=dimensions,
            )
        )

    for batch in _chunk(metric_data, 20):
        cloudwatch.put_metric_data(Namespace=config.namespace, MetricData=batch)
