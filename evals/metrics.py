import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional


TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+")


def _tokenize(text: str) -> List[str]:
    return [token.lower() for token in TOKEN_PATTERN.findall(text)]


def lexical_cosine_similarity(text_a: str, text_b: str) -> float:
    vec_a = Counter(_tokenize(text_a))
    vec_b = Counter(_tokenize(text_b))

    if not vec_a or not vec_b:
        return 0.0

    intersection = set(vec_a).intersection(vec_b)
    numerator = sum(vec_a[token] * vec_b[token] for token in intersection)
    norm_a = math.sqrt(sum(value * value for value in vec_a.values()))
    norm_b = math.sqrt(sum(value * value for value in vec_b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return numerator / (norm_a * norm_b)


def safe_mean(values: Iterable[float]) -> float:
    values = list(values)
    if not values:
        return 0.0
    return sum(values) / len(values)


def wilson_interval(successes: int, total: int, z: float = 1.96) -> Dict[str, float]:
    if total <= 0:
        return {"low": 0.0, "high": 0.0}
    p = successes / total
    denominator = 1 + (z * z) / total
    center = (p + (z * z) / (2 * total)) / denominator
    margin = (z * math.sqrt((p * (1 - p) + (z * z) / (4 * total)) / total)) / denominator
    return {"low": max(0.0, center - margin), "high": min(1.0, center + margin)}


@dataclass
class CaseMetricsAccumulator:
    intent_hits: int = 0
    issue_hits: int = 0
    tool_match_hits: int = 0
    tool_failures: int = 0
    issue_payload_complete_hits: int = 0
    issue_key_resolution_match_hits: int = 0
    business_success_hits: int = 0
    call_construction_failure_hits: int = 0
    call_construction_recovered_hits: int = 0
    grounding_failure_hits: int = 0
    write_case_count: int = 0
    write_tool_selected_hits: int = 0
    write_tool_match_hits: int = 0
    latencies: List[float] | None = None
    success_latencies: List[float] | None = None
    failed_latencies: List[float] | None = None
    similarities: List[float] | None = None
    grounding_attempts: List[float] | None = None
    grounding_retries: List[float] | None = None
    call_construction_attempts: List[float] | None = None
    call_construction_retries: List[float] | None = None
    llm_input_tokens: List[float] | None = None
    llm_output_tokens: List[float] | None = None
    llm_total_tokens: List[float] | None = None

    def __post_init__(self) -> None:
        self.latencies = []
        self.success_latencies = []
        self.failed_latencies = []
        self.similarities = []
        self.grounding_attempts = []
        self.grounding_retries = []
        self.call_construction_attempts = []
        self.call_construction_retries = []
        self.llm_input_tokens = []
        self.llm_output_tokens = []
        self.llm_total_tokens = []


def _empty_case_metrics_summary() -> Dict[str, float]:
    return {
        "total_cases": 0,
        "intent_accuracy": 0.0,
        "issue_key_accuracy": 0.0,
        "tool_match_rate": 0.0,
        "tool_failure_rate": 0.0,
        "tool_failure_ci95_low": 0.0,
        "tool_failure_ci95_high": 0.0,
        "issue_payload_completeness_rate": 0.0,
        "issue_key_resolution_match_rate": 0.0,
        "business_success_rate": 0.0,
        "mean_latency_ms": 0.0,
        "mean_latency_success_ms": 0.0,
        "mean_latency_failure_ms": 0.0,
        "mean_response_similarity": 0.0,
        "grounding_failure_rate": 0.0,
        "mean_grounding_attempts": 0.0,
        "mean_grounding_retries": 0.0,
        "call_construction_failure_rate": 0.0,
        "mean_call_construction_attempts": 0.0,
        "mean_call_construction_retries": 0.0,
        "call_construction_recovery_rate": 0.0,
        "write_case_count": 0,
        "write_tool_selected_rate": 0.0,
        "write_tool_match_rate": 0.0,
        "total_llm_input_tokens": 0.0,
        "total_llm_output_tokens": 0.0,
        "total_llm_total_tokens": 0.0,
        "mean_llm_input_tokens": 0.0,
        "mean_llm_output_tokens": 0.0,
        "mean_llm_total_tokens": 0.0,
    }


def _update_accumulator(acc: CaseMetricsAccumulator, case: Dict[str, Any]) -> None:
    metrics = case["metrics"]
    _update_match_counters(acc, metrics)
    _update_grounding_and_construction(acc, metrics)
    _update_write_metrics(acc, metrics)
    _update_token_metrics(acc, metrics)
    _update_latency_metrics(acc, metrics)


def _update_match_counters(acc: CaseMetricsAccumulator, metrics: Dict[str, Any]) -> None:
    if metrics["intent_match"]:
        acc.intent_hits += 1
    if metrics["issue_key_match"]:
        acc.issue_hits += 1
    if metrics.get("tool_match", False):
        acc.tool_match_hits += 1
    if metrics["tool_failure"]:
        acc.tool_failures += 1
    if metrics.get("issue_payload_complete", False):
        acc.issue_payload_complete_hits += 1
    if metrics.get("issue_key_resolution_match", False):
        acc.issue_key_resolution_match_hits += 1
    if metrics.get("business_success", False):
        acc.business_success_hits += 1


def _update_grounding_and_construction(
    acc: CaseMetricsAccumulator,
    metrics: Dict[str, Any],
) -> None:
    if metrics.get("grounding_failure", False):
        acc.grounding_failure_hits += 1
    acc.grounding_attempts.append(float(metrics.get("grounding_attempts", 0.0)))
    acc.grounding_retries.append(float(metrics.get("grounding_retry_count", 0.0)))
    if metrics.get("call_construction_failure", False):
        acc.call_construction_failure_hits += 1
        if metrics.get("call_construction_recovered", False):
            acc.call_construction_recovered_hits += 1
    acc.call_construction_attempts.append(float(metrics.get("call_construction_attempts", 0.0)))
    acc.call_construction_retries.append(float(metrics.get("call_construction_retries", 0.0)))


def _update_write_metrics(acc: CaseMetricsAccumulator, metrics: Dict[str, Any]) -> None:
    if metrics.get("write_case", False):
        acc.write_case_count += 1
        if metrics.get("write_tool_selected", False):
            acc.write_tool_selected_hits += 1
        if metrics.get("write_tool_match", False):
            acc.write_tool_match_hits += 1


def _update_token_metrics(acc: CaseMetricsAccumulator, metrics: Dict[str, Any]) -> None:
    acc.llm_input_tokens.append(float(metrics.get("llm_input_tokens", 0.0)))
    acc.llm_output_tokens.append(float(metrics.get("llm_output_tokens", 0.0)))
    acc.llm_total_tokens.append(float(metrics.get("llm_total_tokens", 0.0)))


def _update_latency_metrics(acc: CaseMetricsAccumulator, metrics: Dict[str, Any]) -> None:
    latency_value = float(metrics["latency_ms"])
    acc.latencies.append(latency_value)
    if metrics.get("business_success", False):
        acc.success_latencies.append(latency_value)
    else:
        acc.failed_latencies.append(latency_value)
    acc.similarities.append(float(metrics["response_similarity"]))


def _summary_from_accumulator(acc: CaseMetricsAccumulator, total: int) -> Dict[str, float]:
    tool_failure_ci = wilson_interval(successes=acc.tool_failures, total=total)
    call_construction_recovery_rate = (
        acc.call_construction_recovered_hits / acc.call_construction_failure_hits
        if acc.call_construction_failure_hits > 0
        else 0.0
    )
    write_tool_selected_rate = (
        acc.write_tool_selected_hits / acc.write_case_count if acc.write_case_count > 0 else 0.0
    )
    write_tool_match_rate = (
        acc.write_tool_match_hits / acc.write_case_count if acc.write_case_count > 0 else 0.0
    )
    return {
        "total_cases": total,
        "intent_accuracy": acc.intent_hits / total,
        "issue_key_accuracy": acc.issue_hits / total,
        "tool_match_rate": acc.tool_match_hits / total,
        "tool_failure_rate": acc.tool_failures / total,
        "tool_failure_ci95_low": tool_failure_ci["low"],
        "tool_failure_ci95_high": tool_failure_ci["high"],
        "issue_payload_completeness_rate": acc.issue_payload_complete_hits / total,
        "issue_key_resolution_match_rate": acc.issue_key_resolution_match_hits / total,
        "business_success_rate": acc.business_success_hits / total,
        "mean_latency_ms": safe_mean(acc.latencies),
        "mean_latency_success_ms": safe_mean(acc.success_latencies),
        "mean_latency_failure_ms": safe_mean(acc.failed_latencies),
        "mean_response_similarity": safe_mean(acc.similarities),
        "grounding_failure_rate": acc.grounding_failure_hits / total,
        "mean_grounding_attempts": safe_mean(acc.grounding_attempts),
        "mean_grounding_retries": safe_mean(acc.grounding_retries),
        "call_construction_failure_rate": acc.call_construction_failure_hits / total,
        "mean_call_construction_attempts": safe_mean(acc.call_construction_attempts),
        "mean_call_construction_retries": safe_mean(acc.call_construction_retries),
        "call_construction_recovery_rate": call_construction_recovery_rate,
        "write_case_count": acc.write_case_count,
        "write_tool_selected_rate": write_tool_selected_rate,
        "write_tool_match_rate": write_tool_match_rate,
        "total_llm_input_tokens": sum(acc.llm_input_tokens),
        "total_llm_output_tokens": sum(acc.llm_output_tokens),
        "total_llm_total_tokens": sum(acc.llm_total_tokens),
        "mean_llm_input_tokens": safe_mean(acc.llm_input_tokens),
        "mean_llm_output_tokens": safe_mean(acc.llm_output_tokens),
        "mean_llm_total_tokens": safe_mean(acc.llm_total_tokens),
    }


def aggregate_case_metrics(case_results: List[Dict]) -> Dict[str, float]:
    total = len(case_results)
    if total == 0:
        return _empty_case_metrics_summary()
    accumulator = CaseMetricsAccumulator()
    for case in case_results:
        _update_accumulator(accumulator, case)
    return _summary_from_accumulator(accumulator, total)


def aggregate_judge_metrics(case_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    judge_rows = [case.get("judge") for case in case_results if isinstance(case.get("judge"), dict)]
    total = len(case_results)
    evaluated = len(judge_rows)
    if evaluated == 0:
        return {
            "evaluated_cases": 0,
            "coverage_rate": 0.0,
            "mean_tool_choice_score": 0.0,
            "mean_execution_reliability_score": 0.0,
            "mean_response_quality_score": 0.0,
            "mean_overall_score": 0.0,
            "pass_rate": 0.0,
        }

    pass_count = 0
    tool_choice: List[float] = []
    execution_reliability: List[float] = []
    response_quality: List[float] = []
    overall: List[float] = []
    for row in judge_rows:
        if str(row.get("label", "")).lower() == "pass":
            pass_count += 1
        tool_choice.append(float(row.get("tool_choice_score", 0.0)))
        execution_reliability.append(float(row.get("execution_reliability_score", 0.0)))
        response_quality.append(float(row.get("response_quality_score", 0.0)))
        overall.append(float(row.get("overall_score", 0.0)))

    return {
        "evaluated_cases": evaluated,
        "coverage_rate": evaluated / total if total > 0 else 0.0,
        "mean_tool_choice_score": safe_mean(tool_choice),
        "mean_execution_reliability_score": safe_mean(execution_reliability),
        "mean_response_quality_score": safe_mean(response_quality),
        "mean_overall_score": safe_mean(overall),
        "pass_rate": pass_count / evaluated,
    }


def deterministic_release_score(summary: Dict[str, float]) -> float:
    # Deterministic gate remains authoritative for release decisions.
    score = (
        0.35 * float(summary.get("business_success_rate", 0.0))
        + 0.20 * (1.0 - float(summary.get("tool_failure_rate", 0.0)))
        + 0.15 * float(summary.get("intent_accuracy", 0.0))
        + 0.15 * float(summary.get("issue_key_accuracy", 0.0))
        + 0.15 * float(summary.get("tool_match_rate", 0.0))
    )
    return max(0.0, min(1.0, score))


def build_overall_reflection(
    *,
    summary: Dict[str, float],
    judge_summary: Dict[str, Any],
    release_gate_threshold: float = 0.85,
) -> Dict[str, Any]:
    deterministic_score = deterministic_release_score(summary)
    judge_score: Optional[float] = None
    if int(judge_summary.get("evaluated_cases", 0)) > 0:
        judge_score = float(judge_summary.get("mean_overall_score", 0.0))

    divergence = abs(deterministic_score - judge_score) if judge_score is not None else None
    if judge_score is None:
        overall_score = deterministic_score
        divergence_flag = False
    else:
        base = 0.7 * deterministic_score + 0.3 * judge_score
        divergence_penalty = 0.15 * divergence
        overall_score = max(0.0, min(1.0, base - divergence_penalty))
        divergence_flag = bool(divergence is not None and divergence > 0.2)

    release_gate_pass = deterministic_score >= release_gate_threshold
    if not release_gate_pass:
        status = "fail_gate"
    elif divergence_flag:
        status = "review_divergence"
    elif overall_score >= release_gate_threshold:
        status = "pass"
    else:
        status = "review"

    return {
        "deterministic_release_score": deterministic_score,
        "judge_diagnostic_score": judge_score,
        "divergence": divergence,
        "divergence_flag": divergence_flag,
        "overall_reflection_score": overall_score,
        "release_gate_pass": release_gate_pass,
        "status": status,
        "release_gate_threshold": release_gate_threshold,
    }
