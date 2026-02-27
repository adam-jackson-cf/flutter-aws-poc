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

    for batch in _chunk(metric_data, 20):
        cloudwatch.put_metric_data(Namespace=namespace, MetricData=batch)
