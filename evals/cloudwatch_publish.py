from typing import Dict, List, Optional

import boto3


def _chunk(items: List[Dict], size: int) -> List[List[Dict]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def publish_eval_summary_metrics(
    *,
    summaries: List[Dict[str, object]],
    namespace: str,
    run_id: str,
    dataset: str,
    scope: str,
    aws_region: str,
    aws_profile: Optional[str] = None,
) -> None:
    if not summaries:
        raise ValueError("summaries must not be empty")
    if not namespace:
        raise ValueError("namespace is required")
    if not aws_region:
        raise ValueError("aws_region is required")

    session_kwargs = {"region_name": aws_region}
    if aws_profile:
        session_kwargs["profile_name"] = aws_profile
    session = boto3.Session(**session_kwargs)
    cloudwatch = session.client("cloudwatch")

    metric_data: List[Dict] = []
    for row in summaries:
        flow = str(row["flow"])
        summary = row["summary"]
        if not isinstance(summary, dict):
            raise ValueError("summary must be a dict")
        judge_summary = row.get("judge_summary")
        composite_reflection = row.get("composite_reflection")

        dimensions = [
            {"Name": "RunId", "Value": run_id},
            {"Name": "Flow", "Value": flow},
            {"Name": "Scope", "Value": scope},
            {"Name": "Dataset", "Value": dataset},
        ]

        metric_data.extend(
            [
                {"MetricName": "IntentAccuracy", "Value": float(summary["intent_accuracy"]), "Dimensions": dimensions},
                {"MetricName": "IssueKeyAccuracy", "Value": float(summary["issue_key_accuracy"]), "Dimensions": dimensions},
                {"MetricName": "ToolMatchRate", "Value": float(summary["tool_match_rate"]), "Dimensions": dimensions},
                {"MetricName": "ToolFailureRate", "Value": float(summary["tool_failure_rate"]), "Dimensions": dimensions},
                {"MetricName": "BusinessSuccessRate", "Value": float(summary["business_success_rate"]), "Dimensions": dimensions},
                {"MetricName": "IssuePayloadCompletenessRate", "Value": float(summary["issue_payload_completeness_rate"]), "Dimensions": dimensions},
                {"MetricName": "MeanLatencyMs", "Value": float(summary["mean_latency_ms"]), "Unit": "Milliseconds", "Dimensions": dimensions},
                {
                    "MetricName": "MeanLatencySuccessMs",
                    "Value": float(summary["mean_latency_success_ms"]),
                    "Unit": "Milliseconds",
                    "Dimensions": dimensions,
                },
                {
                    "MetricName": "MeanLatencyFailureMs",
                    "Value": float(summary["mean_latency_failure_ms"]),
                    "Unit": "Milliseconds",
                    "Dimensions": dimensions,
                },
                {"MetricName": "MeanResponseSimilarity", "Value": float(summary["mean_response_similarity"]), "Dimensions": dimensions},
                {"MetricName": "ToolFailureCi95Low", "Value": float(summary["tool_failure_ci95_low"]), "Dimensions": dimensions},
                {"MetricName": "ToolFailureCi95High", "Value": float(summary["tool_failure_ci95_high"]), "Dimensions": dimensions},
            ]
        )

        if isinstance(judge_summary, dict) and int(judge_summary.get("evaluated_cases", 0)) > 0:
            metric_data.extend(
                [
                    {"MetricName": "JudgeCoverageRate", "Value": float(judge_summary["coverage_rate"]), "Dimensions": dimensions},
                    {"MetricName": "JudgeMeanToolChoiceScore", "Value": float(judge_summary["mean_tool_choice_score"]), "Dimensions": dimensions},
                    {
                        "MetricName": "JudgeMeanExecutionReliabilityScore",
                        "Value": float(judge_summary["mean_execution_reliability_score"]),
                        "Dimensions": dimensions,
                    },
                    {
                        "MetricName": "JudgeMeanResponseQualityScore",
                        "Value": float(judge_summary["mean_response_quality_score"]),
                        "Dimensions": dimensions,
                    },
                    {"MetricName": "JudgeMeanOverallScore", "Value": float(judge_summary["mean_overall_score"]), "Dimensions": dimensions},
                    {"MetricName": "JudgePassRate", "Value": float(judge_summary["pass_rate"]), "Dimensions": dimensions},
                ]
            )

        if isinstance(composite_reflection, dict):
            metric_data.extend(
                [
                    {
                        "MetricName": "DeterministicReleaseScore",
                        "Value": float(composite_reflection["deterministic_release_score"]),
                        "Dimensions": dimensions,
                    },
                    {
                        "MetricName": "OverallReflectionScore",
                        "Value": float(composite_reflection["overall_reflection_score"]),
                        "Dimensions": dimensions,
                    },
                    {
                        "MetricName": "ReleaseGatePass",
                        "Value": 1.0 if bool(composite_reflection["release_gate_pass"]) else 0.0,
                        "Dimensions": dimensions,
                    },
                    {
                        "MetricName": "DivergenceFlag",
                        "Value": 1.0 if bool(composite_reflection["divergence_flag"]) else 0.0,
                        "Dimensions": dimensions,
                    },
                ]
            )

            judge_diagnostic_score = composite_reflection.get("judge_diagnostic_score")
            if judge_diagnostic_score is not None:
                metric_data.append(
                    {
                        "MetricName": "JudgeDiagnosticScore",
                        "Value": float(judge_diagnostic_score),
                        "Dimensions": dimensions,
                    }
                )

            divergence = composite_reflection.get("divergence")
            if divergence is not None:
                metric_data.append(
                    {
                        "MetricName": "ScoreDivergence",
                        "Value": float(divergence),
                        "Dimensions": dimensions,
                    }
                )

    for batch in _chunk(metric_data, 20):
        cloudwatch.put_metric_data(Namespace=namespace, MetricData=batch)
