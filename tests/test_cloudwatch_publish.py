from typing import Any, Dict, List

import pytest

from evals.cloudwatch_publish import publish_eval_summary_metrics


class _DummyCloudWatch:
    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    def put_metric_data(self, Namespace: str, MetricData: List[Dict[str, Any]]) -> None:  # noqa: N803
        self.calls.append({"Namespace": Namespace, "MetricData": MetricData})


class _DummySession:
    def __init__(self) -> None:
        self.cloudwatch = _DummyCloudWatch()

    def client(self, service_name: str) -> _DummyCloudWatch:
        assert service_name == "cloudwatch"
        return self.cloudwatch


def test_publish_eval_summary_metrics_includes_judge_and_composite(monkeypatch: Any) -> None:
    created: Dict[str, Any] = {}

    def _fake_session(**kwargs: Any) -> _DummySession:
        created["kwargs"] = kwargs
        created["session"] = _DummySession()
        return created["session"]

    monkeypatch.setattr("evals.cloudwatch_publish.boto3.Session", _fake_session)

    publish_eval_summary_metrics(
        summaries=[
            {
                "flow": "native",
                "summary": {
                    "intent_accuracy": 1.0,
                    "issue_key_accuracy": 1.0,
                    "tool_match_rate": 1.0,
                    "tool_failure_rate": 0.0,
                    "business_success_rate": 1.0,
                    "issue_payload_completeness_rate": 1.0,
                    "mean_latency_ms": 100.0,
                    "mean_latency_success_ms": 100.0,
                    "mean_latency_failure_ms": 0.0,
                    "mean_response_similarity": 0.8,
                    "tool_failure_ci95_low": 0.0,
                    "tool_failure_ci95_high": 0.1,
                },
                "judge_summary": {
                    "evaluated_cases": 2,
                    "coverage_rate": 1.0,
                    "mean_tool_choice_score": 0.9,
                    "mean_execution_reliability_score": 0.85,
                    "mean_response_quality_score": 0.8,
                    "mean_overall_score": 0.87,
                    "pass_rate": 0.5,
                },
                "composite_reflection": {
                    "deterministic_release_score": 0.95,
                    "judge_diagnostic_score": 0.87,
                    "divergence": 0.08,
                    "divergence_flag": False,
                    "overall_reflection_score": 0.91,
                    "release_gate_pass": True,
                    "status": "pass",
                    "release_gate_threshold": 0.85,
                },
            }
        ],
        namespace="FlutterAgentCorePoc/Evals",
        run_id="run-1",
        dataset="evals/golden/sop_cases.jsonl",
        scope="route",
        aws_region="eu-west-1",
        aws_profile="profile-a",
    )

    assert created["kwargs"]["region_name"] == "eu-west-1"
    assert created["kwargs"]["profile_name"] == "profile-a"

    all_metric_names = [
        metric["MetricName"]
        for call in created["session"].cloudwatch.calls
        for metric in call["MetricData"]
    ]
    expected_names = {
        "IntentAccuracy",
        "ToolMatchRate",
        "ToolFailureRate",
        "JudgeMeanOverallScore",
        "JudgePassRate",
        "DeterministicReleaseScore",
        "JudgeDiagnosticScore",
        "ScoreDivergence",
        "OverallReflectionScore",
        "ReleaseGatePass",
        "DivergenceFlag",
    }
    assert expected_names.issubset(set(all_metric_names))


def test_publish_eval_summary_metrics_skips_judge_metrics_when_no_cases(monkeypatch: Any) -> None:
    created: Dict[str, Any] = {}

    def _fake_session(**_kwargs: Any) -> _DummySession:
        created["session"] = _DummySession()
        return created["session"]

    monkeypatch.setattr("evals.cloudwatch_publish.boto3.Session", _fake_session)

    publish_eval_summary_metrics(
        summaries=[
            {
                "flow": "native",
                "summary": {
                    "intent_accuracy": 1.0,
                    "issue_key_accuracy": 1.0,
                    "tool_match_rate": 1.0,
                    "tool_failure_rate": 0.0,
                    "business_success_rate": 1.0,
                    "issue_payload_completeness_rate": 1.0,
                    "mean_latency_ms": 100.0,
                    "mean_latency_success_ms": 100.0,
                    "mean_latency_failure_ms": 0.0,
                    "mean_response_similarity": 0.8,
                    "tool_failure_ci95_low": 0.0,
                    "tool_failure_ci95_high": 0.1,
                },
                "judge_summary": {
                    "evaluated_cases": 0,
                    "coverage_rate": 1.0,
                    "mean_tool_choice_score": 0.9,
                    "mean_execution_reliability_score": 0.85,
                    "mean_response_quality_score": 0.8,
                    "mean_overall_score": 0.87,
                    "pass_rate": 0.5,
                },
            }
        ],
        namespace="FlutterAgentCorePoc/Evals",
        run_id="run-1",
        dataset="evals/golden/sop_cases.jsonl",
        scope="route",
        aws_region="eu-west-1",
    )

    all_metric_names = [
        metric["MetricName"]
        for call in created["session"].cloudwatch.calls
        for metric in call["MetricData"]
    ]
    assert "JudgeCoverageRate" not in all_metric_names


def test_publish_eval_summary_metrics_rejects_missing_metric_field(monkeypatch: Any) -> None:
    monkeypatch.setattr("evals.cloudwatch_publish.boto3.Session", lambda **_kwargs: _DummySession())

    with pytest.raises(ValueError, match="metric_value_missing:ToolFailureCi95High:tool_failure_ci95_high"):
        publish_eval_summary_metrics(
            summaries=[
                {
                    "flow": "native",
                    "summary": {
                        "intent_accuracy": 1.0,
                        "issue_key_accuracy": 1.0,
                        "tool_match_rate": 1.0,
                        "tool_failure_rate": 0.0,
                        "business_success_rate": 1.0,
                        "issue_payload_completeness_rate": 1.0,
                        "mean_latency_ms": 100.0,
                        "mean_latency_success_ms": 100.0,
                        "mean_latency_failure_ms": 0.0,
                        "mean_response_similarity": 0.8,
                        "tool_failure_ci95_low": 0.0,
                    },
                }
            ],
            namespace="FlutterAgentCorePoc/Evals",
            run_id="run-1",
            dataset="evals/golden/sop_cases.jsonl",
            scope="route",
            aws_region="eu-west-1",
        )


def test_publish_eval_summary_metrics_rejects_invalid_metric_value(monkeypatch: Any) -> None:
    monkeypatch.setattr("evals.cloudwatch_publish.boto3.Session", lambda **_kwargs: _DummySession())

    with pytest.raises(ValueError, match="metric_value_invalid:IntentAccuracy:intent_accuracy"):
        publish_eval_summary_metrics(
            summaries=[
                {
                    "flow": "native",
                    "summary": {
                        "intent_accuracy": "invalid",
                        "issue_key_accuracy": 1.0,
                        "tool_match_rate": 1.0,
                        "tool_failure_rate": 0.0,
                        "business_success_rate": 1.0,
                        "issue_payload_completeness_rate": 1.0,
                        "mean_latency_ms": 100.0,
                        "mean_latency_success_ms": 100.0,
                        "mean_latency_failure_ms": 0.0,
                        "mean_response_similarity": 0.8,
                        "tool_failure_ci95_low": 0.0,
                        "tool_failure_ci95_high": 0.1,
                    },
                }
            ],
            namespace="FlutterAgentCorePoc/Evals",
            run_id="run-1",
            dataset="evals/golden/sop_cases.jsonl",
            scope="route",
            aws_region="eu-west-1",
        )
