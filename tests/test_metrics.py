import pytest

from evals.metrics import (
    aggregate_case_metrics,
    aggregate_judge_metrics,
    build_overall_reflection,
    deterministic_release_score,
    lexical_cosine_similarity,
)


def test_cosine_similarity_positive() -> None:
    score = lexical_cosine_similarity("tracking JRASERVER-1 update", "tracking JRASERVER-1 customer update")
    assert score > 0.5


def test_aggregate_metrics() -> None:
    rows = [
        {
            "metrics": {
                "intent_match": True,
                "issue_key_match": True,
                "tool_match": True,
                "tool_failure": False,
                "latency_ms": 120.0,
                "response_similarity": 0.9,
            }
        },
        {
            "metrics": {
                "intent_match": False,
                "issue_key_match": True,
                "tool_match": False,
                "tool_failure": True,
                "latency_ms": 180.0,
                "response_similarity": 0.4,
            }
        },
    ]
    summary = aggregate_case_metrics(rows)
    assert summary["total_cases"] == 2
    assert summary["intent_accuracy"] == 0.5
    assert summary["tool_match_rate"] == 0.5
    assert summary["tool_failure_rate"] == 0.5


def test_judge_aggregation_and_reflection() -> None:
    rows = [
        {
            "metrics": {
                "intent_match": True,
                "issue_key_match": True,
                "tool_match": True,
                "tool_failure": False,
                "issue_payload_complete": True,
                "business_success": True,
                "latency_ms": 120.0,
                "response_similarity": 0.9,
            },
            "judge": {
                "tool_choice_score": 1.0,
                "execution_reliability_score": 0.9,
                "response_quality_score": 0.8,
                "overall_score": 0.9,
                "label": "pass",
            },
        },
        {
            "metrics": {
                "intent_match": True,
                "issue_key_match": True,
                "tool_match": True,
                "tool_failure": False,
                "issue_payload_complete": True,
                "business_success": True,
                "latency_ms": 110.0,
                "response_similarity": 0.8,
            },
            "judge": {
                "tool_choice_score": 0.8,
                "execution_reliability_score": 0.7,
                "response_quality_score": 0.9,
                "overall_score": 0.8,
                "label": "review",
            },
        },
    ]
    summary = aggregate_case_metrics(rows)
    judge_summary = aggregate_judge_metrics(rows)
    reflection = build_overall_reflection(summary=summary, judge_summary=judge_summary)

    assert deterministic_release_score(summary) >= 0.9
    assert judge_summary["evaluated_cases"] == 2
    assert judge_summary["mean_overall_score"] == pytest.approx(0.85)
    assert reflection["release_gate_pass"] is True
    assert reflection["status"] in {"pass", "review_divergence"}
