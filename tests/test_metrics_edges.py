import pytest

from evals import metrics


def test_lexical_cosine_similarity_zero_norm_paths() -> None:
    assert metrics.lexical_cosine_similarity("", "abc") == 0.0
    assert metrics.lexical_cosine_similarity("abc", "") == 0.0
    assert metrics.lexical_cosine_similarity("abc", "abc") > 0.0


def test_lexical_cosine_similarity_norm_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(metrics, "_tokenize", lambda _text: ["a"])
    monkeypatch.setattr(metrics.math, "sqrt", lambda _v: 0.0)
    assert metrics.lexical_cosine_similarity("a", "a") == 0.0


def test_wilson_interval_zero_total() -> None:
    assert metrics.wilson_interval(0, 0) == {"low": 0.0, "high": 0.0}


def test_aggregate_case_metrics_empty() -> None:
    summary = metrics.aggregate_case_metrics([])
    assert summary["total_cases"] == 0
    assert summary["business_success_rate"] == 0.0


def test_aggregate_judge_metrics_empty() -> None:
    summary = metrics.aggregate_judge_metrics([{"metrics": {}}, {"metrics": {}}])
    assert summary["evaluated_cases"] == 0
    assert summary["coverage_rate"] == 0.0


def test_build_overall_reflection_statuses() -> None:
    summary = {
        "business_success_rate": 1.0,
        "tool_failure_rate": 0.0,
        "intent_accuracy": 1.0,
        "issue_key_accuracy": 1.0,
        "tool_match_rate": 1.0,
    }
    judge_summary = {"evaluated_cases": 0, "mean_overall_score": 0.0}
    out = metrics.build_overall_reflection(summary=summary, judge_summary=judge_summary, release_gate_threshold=0.9)
    assert out["status"] == "pass"

    summary_fail = {**summary, "business_success_rate": 0.0, "tool_failure_rate": 1.0, "intent_accuracy": 0.0, "issue_key_accuracy": 0.0, "tool_match_rate": 0.0}
    out_fail = metrics.build_overall_reflection(summary=summary_fail, judge_summary={"evaluated_cases": 1, "mean_overall_score": 0.1}, release_gate_threshold=0.9)
    assert out_fail["status"] == "fail_gate"

    out_div = metrics.build_overall_reflection(summary=summary, judge_summary={"evaluated_cases": 1, "mean_overall_score": 0.0}, release_gate_threshold=0.5)
    assert out_div["status"] == "review_divergence"

    out_review = metrics.build_overall_reflection(
        summary={**summary, "business_success_rate": 0.9, "tool_failure_rate": 0.0, "intent_accuracy": 0.9, "issue_key_accuracy": 0.9, "tool_match_rate": 0.9},
        judge_summary={"evaluated_cases": 1, "mean_overall_score": 0.75},
        release_gate_threshold=0.85,
    )
    assert out_review["status"] == "review"
