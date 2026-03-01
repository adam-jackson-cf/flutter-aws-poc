import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

# Ensure repository root is importable when running as `python3 evals/run_eval.py`.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evals.aws_pipeline_runner import AwsPipelineRunner, PipelineRunResult
from evals.cloudwatch_publish import publish_eval_summary_metrics
from evals.judge import BedrockJudge
from evals.metrics import (
    aggregate_case_metrics,
    aggregate_judge_metrics,
    build_overall_reflection,
    lexical_cosine_similarity,
)

REQUIRED_CASE_KEYS = {
    "case_id",
    "request_text",
    "expected_intent",
    "expected_issue_key",
    "expected_response_anchor",
    "expected_tool",
}

EXPECTED_TOOLS_BY_FLOW = {
    "native": {
        "jira_api_get_issue_by_key",
        "jira_api_get_issue_status_snapshot",
        "jira_api_get_issue_priority_context",
        "jira_api_get_issue_labels",
        "jira_api_get_issue_project_key",
        "jira_api_get_issue_update_timestamp",
    },
    "mcp": {
        "jira_get_issue_by_key",
        "jira_get_issue_status_snapshot",
        "jira_get_issue_priority_context",
        "jira_get_issue_labels",
        "jira_get_issue_project_key",
        "jira_get_issue_update_timestamp",
        "jira_get_issue_risk_flags",
    },
}

TOOL_COMPLETENESS_FIELDS_BY_OPERATION = {
    "get_issue_by_key": ["key", "summary", "status"],
    "get_issue_status_snapshot": ["key", "status", "updated"],
    "get_issue_priority_context": ["key", "priority"],
    "get_issue_labels": ["key", "labels"],
    "get_issue_project_key": ["key", "project_key"],
    "get_issue_update_timestamp": ["key", "updated"],
    "get_issue_risk_flags": ["key"],
}


@dataclass(frozen=True)
class CaseRunContext:
    flow: str
    scope: str
    iteration: int


@dataclass(frozen=True)
class EvaluationConfig:
    dry_run: bool
    scope: str
    iterations: int
    runner: AwsPipelineRunner
    judge: BedrockJudge | None


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
    parser.add_argument("--enable-judge", action="store_true")
    parser.add_argument("--judge-model-id", default=os.environ.get("BEDROCK_MODEL_ID", "eu.amazon.nova-lite-v1:0"))
    parser.add_argument("--judge-region", default=os.environ.get("BEDROCK_REGION", os.environ.get("AWS_REGION", "")))
    return parser.parse_args()


def utc_compact_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def sanitize_run_id(run_id: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "-", run_id.strip())
    return cleaned or utc_compact_now()


def load_dataset(path: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for index, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        parsed = json.loads(line)
        if not isinstance(parsed, dict):
            raise ValueError(f"dataset row {index} must be an object")

        missing = REQUIRED_CASE_KEYS.difference(parsed.keys())
        if missing:
            raise ValueError(f"dataset row {index} missing required keys: {sorted(missing)}")

        expected_tool = parsed.get("expected_tool")
        if not isinstance(expected_tool, dict):
            raise ValueError(f"dataset row {index} expected_tool must be an object with native/mcp")

        for flow in ("native", "mcp"):
            selected = str(expected_tool.get(flow, "")).strip()
            if not selected:
                raise ValueError(f"dataset row {index} expected_tool.{flow} is required")
            if selected not in EXPECTED_TOOLS_BY_FLOW[flow]:
                raise ValueError(f"dataset row {index} expected_tool.{flow} is not supported: {selected}")
        rows.append(parsed)
    return rows


def _strip_gateway_tool_prefix(tool_name: str) -> str:
    if "__" not in tool_name:
        return tool_name
    return re.split(r"__+", tool_name, maxsplit=1)[1]


def _canonical_tool_operation(tool_name: str) -> str:
    name = _strip_gateway_tool_prefix(tool_name).strip()
    if name.startswith("jira_api_"):
        return name[len("jira_api_") :]
    if name.startswith("jira_"):
        return name[len("jira_") :]
    return name


def _issue_payload_complete_for_tool(tool_result: Dict[str, Any], tool_name: str) -> bool:
    if not isinstance(tool_result, dict):
        return False

    operation = _canonical_tool_operation(tool_name)
    required_fields = TOOL_COMPLETENESS_FIELDS_BY_OPERATION.get(operation, ["key"])
    for field in required_fields:
        value = tool_result.get(field)
        if field == "labels":
            if not isinstance(value, list):
                return False
            continue

        text = str(value).strip()
        if not text:
            return False
        if field == "status" and text.lower() in {"unknown", "none"}:
            return False
    return True


def expected_tool_for_flow(case: Dict[str, Any], flow: str) -> str:
    selected = str(case["expected_tool"][flow]).strip()
    if flow == "mcp":
        selected = _strip_gateway_tool_prefix(selected)
    return selected


def _selected_tool_for_flow(flow: str, run_payload: Dict[str, Any]) -> str:
    if flow == "mcp":
        return str(run_payload.get("mcp_selection", {}).get("selected_tool", ""))
    if flow == "native":
        return str(run_payload.get("native_selection", {}).get("selected_tool", ""))
    return "jira_get_issue_by_key"


def _total_latency_ms(run_payload: Dict[str, Any], run_metrics: Dict[str, Any]) -> float:
    total_latency_ms = float(run_metrics.get("total_latency_ms", 0.0) or 0.0)
    if total_latency_ms > 0:
        return total_latency_ms

    stage_entries = run_payload.get("metrics", {}).get("stages", [])
    return sum(float(entry.get("latency_ms", 0.0)) for entry in stage_entries if isinstance(entry, dict))


def _response_text_and_similarity(scope: str, generated_response: Dict[str, Any], expected_response_anchor: str) -> tuple[str, float]:
    if scope != "full":
        return "", 0.0
    generated = str(generated_response.get("customer_response", ""))
    return generated, lexical_cosine_similarity(generated, expected_response_anchor)


def _expected_payload(case: Dict[str, Any], expected_tool: str) -> Dict[str, str]:
    return {
        "intent": case["expected_intent"],
        "issue_key": case["expected_issue_key"],
        "tool": expected_tool,
        "response_anchor": case["expected_response_anchor"],
    }


def _actual_payload(
    intent_actual: str,
    issue_key_actual: str,
    selected_tool: str,
    failure_reason: str,
    generated: str,
    run: PipelineRunResult,
) -> Dict[str, str]:
    return {
        "intent": intent_actual,
        "issue_key": issue_key_actual,
        "selected_tool": selected_tool,
        "failure_reason": failure_reason,
        "customer_response": generated,
        "execution_arn": run.execution_arn,
        "artifact_s3_uri": run.artifact_s3_uri,
    }


def _case_metrics_payload(
    intent_match: bool,
    issue_key_match: bool,
    tool_failure: bool,
    tool_match: bool,
    issue_payload_complete: bool,
    business_success: bool,
    failure_reason: str,
    total_latency_ms: float,
    similarity: float,
) -> Dict[str, Any]:
    return {
        "intent_match": intent_match,
        "issue_key_match": issue_key_match,
        "tool_failure": tool_failure,
        "tool_match": tool_match,
        "issue_payload_complete": issue_payload_complete,
        "business_success": business_success,
        "failure_reason": failure_reason,
        "latency_ms": total_latency_ms,
        "response_similarity": similarity,
    }


def _case_result_from_payload(case: Dict[str, Any], run: PipelineRunResult, context: CaseRunContext) -> Dict[str, Any]:
    run_payload = run.payload
    intake = run_payload.get("intake", {})
    tool_result = run_payload.get("tool_result", {})
    generated_response = run_payload.get("generated_response", {})
    run_metrics = run_payload.get("run_metrics", {})

    expected_tool = expected_tool_for_flow(case, context.flow)
    generated, similarity = _response_text_and_similarity(
        scope=context.scope,
        generated_response=generated_response,
        expected_response_anchor=case["expected_response_anchor"],
    )

    failure_reason = str(tool_result.get("failure_reason", ""))
    issue_payload_complete = _issue_payload_complete_for_tool(tool_result, expected_tool)
    tool_failure = bool(run_payload.get("tool_failure", run_metrics.get("tool_failure", False)))

    intent_actual = str(intake.get("intent", ""))
    issue_key_actual = str(tool_result.get("key", ""))
    intent_match = intent_actual == case["expected_intent"]
    issue_key_match = issue_key_actual == case["expected_issue_key"]
    selected_tool = _selected_tool_for_flow(context.flow, run_payload)
    tool_match = _canonical_tool_operation(selected_tool) == _canonical_tool_operation(expected_tool)
    business_success = bool((not tool_failure) and issue_payload_complete and intent_match and issue_key_match and tool_match)
    total_latency_ms = _total_latency_ms(run_payload, run_metrics)

    return {
        "iteration": context.iteration,
        "case_id": case["case_id"],
        "request_text": case["request_text"],
        "expected": _expected_payload(case=case, expected_tool=expected_tool),
        "actual": _actual_payload(
            intent_actual=intent_actual,
            issue_key_actual=issue_key_actual,
            selected_tool=selected_tool,
            failure_reason=failure_reason,
            generated=generated,
            run=run,
        ),
        "metrics": _case_metrics_payload(
            intent_match=intent_match,
            issue_key_match=issue_key_match,
            tool_failure=tool_failure,
            tool_match=tool_match,
            issue_payload_complete=issue_payload_complete,
            business_success=business_success,
            failure_reason=failure_reason,
            total_latency_ms=total_latency_ms,
            similarity=similarity,
        ),
    }


def _evaluate_single_case(
    flow: str,
    case: Dict[str, Any],
    iteration: int,
    config: EvaluationConfig,
) -> Dict[str, Any]:
    case_id = f"{case['case_id']}_it{iteration}"
    run = config.runner.run_case(
        flow=flow,
        request_text=case["request_text"],
        case_id=case_id,
        expected_tool=expected_tool_for_flow(case, flow),
        dry_run=config.dry_run,
    )
    context = CaseRunContext(flow=flow, scope=config.scope, iteration=iteration)
    result = _case_result_from_payload(case=case, run=run, context=context)
    if config.judge is not None:
        result["judge"] = config.judge.score_case(result, scope=config.scope)
        result["metrics"]["judge_overall_score"] = float(result["judge"]["overall_score"])
    return result


def _count_failure_reasons(results: List[Dict[str, Any]]) -> Dict[str, int]:
    failure_reason_counts: Dict[str, int] = {}
    for row in results:
        reason = str(row["metrics"].get("failure_reason", "")).strip()
        if not reason:
            continue
        failure_reason_counts[reason] = failure_reason_counts.get(reason, 0) + 1
    return failure_reason_counts


def evaluate_flow(flow: str, cases: List[Dict[str, Any]], config: EvaluationConfig) -> Dict[str, Any]:
    results = []

    for iteration in range(config.iterations):
        for case in cases:
            results.append(
                _evaluate_single_case(
                    flow=flow,
                    case=case,
                    iteration=iteration + 1,
                    config=config,
                )
            )

    summary = aggregate_case_metrics(results)
    judge_summary = aggregate_judge_metrics(results)
    composite_reflection = build_overall_reflection(summary=summary, judge_summary=judge_summary)
    failure_reason_counts = _count_failure_reasons(results)

    return {
        "flow": flow,
        "scope": config.scope,
        "iterations": config.iterations,
        "summary": summary,
        "judge_summary": judge_summary,
        "composite_reflection": composite_reflection,
        "failure_reasons": failure_reason_counts,
        "cases": results,
    }


def _validate_runtime_args(args: argparse.Namespace) -> None:
    if not args.state_machine_arn:
        raise ValueError("STATE_MACHINE_ARN is required (set env var or pass --state-machine-arn)")
    if not args.aws_region:
        raise ValueError("AWS_REGION is required (set env var or pass --aws-region)")
    if args.enable_judge and not args.judge_region:
        raise ValueError("judge region is required when --enable-judge is set")


def _build_runner(args: argparse.Namespace) -> AwsPipelineRunner:
    return AwsPipelineRunner(
        state_machine_arn=args.state_machine_arn,
        aws_region=args.aws_region,
        aws_profile=args.aws_profile or None,
        poll_interval_seconds=args.poll_interval_seconds,
        execution_timeout_seconds=args.execution_timeout_seconds,
    )


def _resolve_aws_identity(runner: AwsPipelineRunner, dry_run: bool) -> Dict[str, str]:
    if dry_run:
        return {}
    try:
        identity = runner.preflight_identity()
    except Exception as exc:  # noqa: BLE001 - this is a preflight for clearer operator feedback
        raise RuntimeError("aws_auth_preflight_failed:refresh_credentials_and_retry") from exc
    if not identity.get("account") or not identity.get("arn"):
        raise RuntimeError("aws_auth_preflight_incomplete_identity")
    return identity


def _selected_flows(flow: str) -> List[str]:
    return [flow] if flow != "both" else ["native", "mcp"]


def _build_comparison_payload(results: List[Dict[str, Any]]) -> Dict[str, float]:
    native_summary = results[0]["summary"]
    mcp_summary = results[1]["summary"]
    native_composite = results[0]["composite_reflection"]
    mcp_composite = results[1]["composite_reflection"]
    return {
        "tool_failure_delta": mcp_summary["tool_failure_rate"] - native_summary["tool_failure_rate"],
        "latency_delta_ms": mcp_summary["mean_latency_ms"] - native_summary["mean_latency_ms"],
        "response_similarity_delta": mcp_summary["mean_response_similarity"] - native_summary["mean_response_similarity"],
        "deterministic_release_score_delta": mcp_composite["deterministic_release_score"] - native_composite["deterministic_release_score"],
        "judge_diagnostic_score_delta": float(mcp_composite["judge_diagnostic_score"] or 0.0)
        - float(native_composite["judge_diagnostic_score"] or 0.0),
        "overall_reflection_score_delta": mcp_composite["overall_reflection_score"] - native_composite["overall_reflection_score"],
    }


def _write_eval_payload(payload: Dict[str, Any], output_path: str) -> None:
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _maybe_add_comparison(payload: Dict[str, Any], selected_flow: str) -> None:
    if selected_flow != "both":
        return
    payload["comparison"] = _build_comparison_payload(payload["results"])


def _maybe_publish_cloudwatch(args: argparse.Namespace, payload: Dict[str, Any], run_id: str) -> None:
    if not args.publish_cloudwatch:
        return
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


def _emit_run_output(output_path: str, dry_run: bool) -> None:
    print(f"WROTE_EVAL={output_path}")
    if dry_run:
        print("SMOKE_OK")


def main() -> int:
    args = parse_args()
    _validate_runtime_args(args)

    dataset = load_dataset(args.dataset)
    flows = _selected_flows(args.flow)
    run_id = sanitize_run_id(args.run_id) if args.run_id else utc_compact_now()

    runner = _build_runner(args)
    aws_identity = _resolve_aws_identity(runner=runner, dry_run=args.dry_run)
    judge = BedrockJudge(model_id=args.judge_model_id, region=args.judge_region) if args.enable_judge else None
    evaluation = EvaluationConfig(
        dry_run=args.dry_run,
        scope=args.scope,
        iterations=args.iterations,
        runner=runner,
        judge=judge,
    )

    payload = {
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": args.dataset,
        "dry_run": args.dry_run,
        "scope": args.scope,
        "iterations": args.iterations,
        "state_machine_arn": args.state_machine_arn,
        "aws_region": args.aws_region,
        "aws_identity": aws_identity,
        "judge": {
            "enabled": bool(args.enable_judge),
            "model_id": args.judge_model_id if args.enable_judge else "",
            "region": args.judge_region if args.enable_judge else "",
        },
        "results": [
            evaluate_flow(
                flow=flow,
                cases=dataset,
                config=evaluation,
            )
            for flow in flows
        ],
    }

    _maybe_add_comparison(payload=payload, selected_flow=args.flow)

    default_output = f"reports/runs/{run_id}/eval/eval-{args.flow}-{args.scope}.json"
    output_path = args.output or default_output
    _write_eval_payload(payload=payload, output_path=output_path)
    _maybe_publish_cloudwatch(args=args, payload=payload, run_id=run_id)
    _emit_run_output(output_path=output_path, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
