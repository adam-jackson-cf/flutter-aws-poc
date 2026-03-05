import pytest

from evals.metrics import (
    aggregate_case_metrics,
    aggregate_case_metrics_by_slice,
    aggregate_judge_metrics,
    build_overall_reflection,
    compute_dspy_opt_dual_scores,
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
                "llm_input_tokens": 100,
                "llm_output_tokens": 30,
                "llm_total_tokens": 130,
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
                "llm_input_tokens": 140,
                "llm_output_tokens": 40,
                "llm_total_tokens": 180,
            }
        },
    ]
    summary = aggregate_case_metrics(rows)
    assert summary["total_cases"] == 2
    assert summary["intent_accuracy"] == 0.5
    assert summary["tool_match_rate"] == 0.5
    assert summary["tool_failure_rate"] == 0.5
    assert summary["total_llm_total_tokens"] == 310
    assert summary["mean_llm_total_tokens"] == 155


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


def test_slice_aggregation_and_dual_scores_include_unspecified_bucket() -> None:
    rows = [
        {
            "expected": {"objective_slice": "optimization"},
            "metrics": {
                "intent_match": True,
                "issue_key_match": True,
                "tool_match": True,
                "tool_failure": False,
                "issue_key_resolution_match": True,
                "business_success": True,
                "latency_ms": 100.0,
                "response_similarity": 1.0,
                "llm_total_tokens": 100,
            },
        },
        {
            "expected": {},
            "metrics": {
                "intent_match": False,
                "issue_key_match": False,
                "tool_match": False,
                "tool_failure": True,
                "issue_key_resolution_match": False,
                "business_success": False,
                "latency_ms": 100.0,
                "response_similarity": 0.0,
                "llm_total_tokens": 200,
            },
        },
    ]
    by_slice = aggregate_case_metrics_by_slice(rows)
    assert "unspecified" in by_slice

    dual = compute_dspy_opt_dual_scores(rows)
    assert "agent_quality_score" in dual
    assert "mcp_failure_cost_score" in dual
