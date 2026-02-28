import math
import re
from collections import Counter
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


def aggregate_case_metrics(case_results: List[Dict]) -> Dict[str, float]:
    total = len(case_results)
    if total == 0:
        return {
            "total_cases": 0,
            "intent_accuracy": 0.0,
            "issue_key_accuracy": 0.0,
            "tool_failure_rate": 0.0,
            "tool_failure_ci95_low": 0.0,
            "tool_failure_ci95_high": 0.0,
            "issue_payload_completeness_rate": 0.0,
            "business_success_rate": 0.0,
            "mean_latency_ms": 0.0,
            "mean_latency_success_ms": 0.0,
            "mean_latency_failure_ms": 0.0,
            "mean_response_similarity": 0.0,
        }

    intent_hits = 0
    issue_hits = 0
    tool_failures = 0
    issue_payload_complete_hits = 0
    business_success_hits = 0
    latencies: List[float] = []
    success_latencies: List[float] = []
    failed_latencies: List[float] = []
    similarities: List[float] = []

    for case in case_results:
        if case["metrics"]["intent_match"]:
            intent_hits += 1
        if case["metrics"]["issue_key_match"]:
            issue_hits += 1
        if case["metrics"]["tool_failure"]:
            tool_failures += 1
        if case["metrics"].get("issue_payload_complete", False):
            issue_payload_complete_hits += 1
        if case["metrics"].get("business_success", False):
            business_success_hits += 1

        latency_value = float(case["metrics"]["latency_ms"])
        latencies.append(latency_value)
        if case["metrics"].get("business_success", False):
            success_latencies.append(latency_value)
        else:
            failed_latencies.append(latency_value)
        similarities.append(float(case["metrics"]["response_similarity"]))

    tool_failure_ci = wilson_interval(successes=tool_failures, total=total)

    return {
        "total_cases": total,
        "intent_accuracy": intent_hits / total,
        "issue_key_accuracy": issue_hits / total,
        "tool_failure_rate": tool_failures / total,
        "tool_failure_ci95_low": tool_failure_ci["low"],
        "tool_failure_ci95_high": tool_failure_ci["high"],
        "issue_payload_completeness_rate": issue_payload_complete_hits / total,
        "business_success_rate": business_success_hits / total,
        "mean_latency_ms": safe_mean(latencies),
        "mean_latency_success_ms": safe_mean(success_latencies),
        "mean_latency_failure_ms": safe_mean(failed_latencies),
        "mean_response_similarity": safe_mean(similarities),
    }


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
        0.45 * float(summary.get("business_success_rate", 0.0))
        + 0.25 * (1.0 - float(summary.get("tool_failure_rate", 0.0)))
        + 0.15 * float(summary.get("intent_accuracy", 0.0))
        + 0.15 * float(summary.get("issue_key_accuracy", 0.0))
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
