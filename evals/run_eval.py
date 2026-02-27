import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

# Ensure repository root is importable when running as `python3 evals/run_eval.py`.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evals.aws_pipeline_runner import AwsPipelineRunner
from evals.cloudwatch_publish import publish_eval_summary_metrics
from evals.metrics import aggregate_case_metrics, lexical_cosine_similarity


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run SOP evaluation through deployed AWS pipeline")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--flow", choices=["native", "mcp", "both"], required=True)
    parser.add_argument("--output", default="")
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--scope", choices=["route", "full"], default="route")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--state-machine-arn", default=os.environ.get("STATE_MACHINE_ARN", ""))
    parser.add_argument("--aws-profile", default=os.environ.get("AWS_PROFILE", ""))
    parser.add_argument("--aws-region", default=os.environ.get("AWS_REGION", ""))
    parser.add_argument("--poll-interval-seconds", type=float, default=2.0)
    parser.add_argument("--execution-timeout-seconds", type=int, default=900)
    parser.add_argument("--publish-cloudwatch", action="store_true")
    parser.add_argument("--cloudwatch-namespace", default="FlutterAgentCorePoc/Evals")
    return parser.parse_args()


def utc_compact_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def sanitize_run_id(run_id: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "-", run_id.strip())
    return cleaned or utc_compact_now()


def load_dataset(path: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def _case_result_from_payload(
    flow: str,
    case: Dict[str, Any],
    run_payload: Dict[str, Any],
    scope: str,
    iteration: int,
    execution_arn: str,
    artifact_s3_uri: str,
) -> Dict[str, Any]:
    intake = run_payload.get("intake", {})
    tool_result = run_payload.get("tool_result", {})
    generated_response = run_payload.get("generated_response", {})
    run_metrics = run_payload.get("run_metrics", {})

    generated = ""
    similarity = 0.0
    if scope == "full":
        generated = str(generated_response.get("customer_response", ""))
        similarity = lexical_cosine_similarity(generated, case["expected_response_anchor"])

    failure_reason = str(tool_result.get("failure_reason", ""))
    issue_payload_complete = bool(str(tool_result.get("summary", "")).strip()) and str(tool_result.get("status", "")).strip().lower() not in {
        "",
        "unknown",
        "none",
    }
    tool_failure = bool(run_payload.get("tool_failure", run_metrics.get("tool_failure", False)))

    intent_actual = str(intake.get("intent", ""))
    issue_key_actual = str(tool_result.get("key", ""))
    intent_match = intent_actual == case["expected_intent"]
    issue_key_match = issue_key_actual == case["expected_issue_key"]
    business_success = bool((not tool_failure) and issue_payload_complete and intent_match and issue_key_match)

    selected_tool = "jira_get_issue_by_key"
    if flow == "mcp":
        selected_tool = str(run_payload.get("mcp_selection", {}).get("selected_tool", ""))

    total_latency_ms = float(run_metrics.get("total_latency_ms", 0.0) or 0.0)
    if total_latency_ms <= 0:
        stage_latencies = [float(entry.get("latency_ms", 0.0)) for entry in run_payload.get("metrics", {}).get("stages", [])]
        total_latency_ms = sum(stage_latencies)

    return {
        "iteration": iteration,
        "case_id": case["case_id"],
        "request_text": case["request_text"],
        "expected": {
            "intent": case["expected_intent"],
            "issue_key": case["expected_issue_key"],
            "response_anchor": case["expected_response_anchor"],
        },
        "actual": {
            "intent": intent_actual,
            "issue_key": issue_key_actual,
            "selected_tool": selected_tool,
            "failure_reason": failure_reason,
            "customer_response": generated,
            "execution_arn": execution_arn,
            "artifact_s3_uri": artifact_s3_uri,
        },
        "metrics": {
            "intent_match": intent_match,
            "issue_key_match": issue_key_match,
            "tool_failure": tool_failure,
            "issue_payload_complete": issue_payload_complete,
            "business_success": business_success,
            "failure_reason": failure_reason,
            "latency_ms": total_latency_ms,
            "response_similarity": similarity,
        },
    }


def evaluate_flow(
    flow: str,
    cases: List[Dict[str, Any]],
    dry_run: bool,
    iterations: int,
    scope: str,
    runner: AwsPipelineRunner,
) -> Dict[str, Any]:
    results = []

    for iteration in range(iterations):
        for case in cases:
            case_id = f"{case['case_id']}_it{iteration + 1}"
            run = runner.run_case(
                flow=flow,
                request_text=case["request_text"],
                case_id=case_id,
                dry_run=dry_run,
            )
            results.append(
                _case_result_from_payload(
                    flow=flow,
                    case=case,
                    run_payload=run.payload,
                    scope=scope,
                    iteration=iteration + 1,
                    execution_arn=run.execution_arn,
                    artifact_s3_uri=run.artifact_s3_uri,
                )
            )

    summary = aggregate_case_metrics(results)
    failure_reason_counts: Dict[str, int] = {}
    for row in results:
        reason = str(row["metrics"].get("failure_reason", "")).strip()
        if not reason:
            continue
        failure_reason_counts[reason] = failure_reason_counts.get(reason, 0) + 1

    return {
        "flow": flow,
        "scope": scope,
        "iterations": iterations,
        "summary": summary,
        "failure_reasons": failure_reason_counts,
        "cases": results,
    }


def main() -> int:
    args = parse_args()
    if not args.state_machine_arn:
        raise ValueError("STATE_MACHINE_ARN is required (set env var or pass --state-machine-arn)")
    if not args.aws_region:
        raise ValueError("AWS_REGION is required (set env var or pass --aws-region)")

    dataset = load_dataset(args.dataset)
    flows = [args.flow] if args.flow != "both" else ["native", "mcp"]
    run_id = sanitize_run_id(args.run_id) if args.run_id else utc_compact_now()

    runner = AwsPipelineRunner(
        state_machine_arn=args.state_machine_arn,
        aws_region=args.aws_region,
        aws_profile=args.aws_profile or None,
        poll_interval_seconds=args.poll_interval_seconds,
        execution_timeout_seconds=args.execution_timeout_seconds,
    )

    run_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "run_id": run_id,
        "generated_at": run_at,
        "dataset": args.dataset,
        "dry_run": args.dry_run,
        "scope": args.scope,
        "iterations": args.iterations,
        "state_machine_arn": args.state_machine_arn,
        "aws_region": args.aws_region,
        "results": [
            evaluate_flow(
                flow=flow,
                cases=dataset,
                dry_run=args.dry_run,
                iterations=args.iterations,
                scope=args.scope,
                runner=runner,
            )
            for flow in flows
        ],
    }

    if args.flow == "both":
        native_summary = payload["results"][0]["summary"]
        mcp_summary = payload["results"][1]["summary"]
        payload["comparison"] = {
            "tool_failure_delta": mcp_summary["tool_failure_rate"] - native_summary["tool_failure_rate"],
            "latency_delta_ms": mcp_summary["mean_latency_ms"] - native_summary["mean_latency_ms"],
            "response_similarity_delta": mcp_summary["mean_response_similarity"] - native_summary["mean_response_similarity"],
        }

    default_output = f"reports/runs/{run_id}/eval/eval-{args.flow}-{args.scope}.json"
    output_path = args.output or default_output
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if args.publish_cloudwatch:
        publish_eval_summary_metrics(
            summaries=payload["results"],
            namespace=args.cloudwatch_namespace,
            run_id=run_id,
            dataset=args.dataset,
            scope=args.scope,
            aws_region=args.aws_region,
            aws_profile=args.aws_profile or None,
        )
        print(f"PUBLISHED_CLOUDWATCH_NAMESPACE={args.cloudwatch_namespace}")

    print(f"WROTE_EVAL={output_path}")
    if args.dry_run:
        print("SMOKE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
