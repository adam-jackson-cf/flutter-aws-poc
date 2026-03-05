#!/usr/bin/env python3
"""Build deterministic failure-path check reports from eval artifacts."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from eval_report_utils import (
    EvalInputSelector,
    OutputPathRequest,
    default_report_output_paths,
    load_json_object,
    resolve_eval_input_paths,
    write_json,
    write_markdown,
)


SCHEMA_INVALID_MARKERS = (
    "artifact_schema_invalid:",
    "schema_invalid:",
    "contract_version_mismatch",
    "contract_version_missing",
)

MCP_UNAVAILABLE_MARKERS = (
    "mcp_gateway_unavailable",
    "selected_unknown_tool",
    "mcp_tool_call_error",
)

TRANSIENT_FAILURE_MARKERS = (
    "llm_gateway_invoke_status:429",
    "llm_gateway_invoke_status:500",
    "llm_gateway_invoke_status:502",
    "llm_gateway_invoke_status:503",
    "llm_gateway_invoke_status:504",
    "openai_gateway_error:timeout",
    "openai_gateway_error:network",
    "openai_gateway_error:http_5",
)


@dataclass(frozen=True)
class CaseRecord:
    source: str
    flow: str
    case_id: str
    iteration: int
    failure_reason: str
    business_success: bool
    call_construction_retries: int
    grounding_retry_count: int


@dataclass(frozen=True)
class CheckDefinition:
    name: str
    case_predicate: Callable[[CaseRecord], bool]
    value_predicate: Callable[[str], bool]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate failure-path acceptance checks from eval artifacts.")
    parser.add_argument("--eval-path", action="append", default=[], help="Path to an eval JSON artifact (repeatable).")
    parser.add_argument(
        "--run-id",
        action="append",
        default=[],
        help="Run id to resolve reports/runs/<RUN_ID>/eval/eval-<flow>-<scope>.json (repeatable).",
    )
    parser.add_argument("--flow", default="both", choices=["native", "mcp", "both", "dspy_opt"])
    parser.add_argument("--scope", default="route", choices=["route", "full"])
    parser.add_argument("--output-json", default="")
    parser.add_argument("--output-md", default="")
    parser.add_argument("--output-run-id", default="", help="Optional run id used for default output location.")
    parser.add_argument("--fail-on-missing", action="store_true", help="Exit non-zero when any required check is missing.")
    return parser.parse_args()


def _string_value(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _int_value(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    return 0


def _dict_value(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return value


def _record_from_payload(source: Path, payload: dict[str, Any]) -> CaseRecord:
    metrics = _dict_value(payload.get("metrics", {}))
    return CaseRecord(
        source=str(source),
        flow=_string_value(payload.get("flow", "")),
        case_id=_string_value(payload.get("case_id", "")),
        iteration=max(0, _int_value(payload.get("iteration", 0))),
        failure_reason=_string_value(metrics.get("failure_reason", "")),
        business_success=bool(metrics.get("business_success", False)),
        call_construction_retries=max(0, _int_value(metrics.get("call_construction_retries", 0))),
        grounding_retry_count=max(0, _int_value(metrics.get("grounding_retry_count", 0))),
    )


def _records_from_eval_payload(payload: dict[str, Any], source: Path) -> list[CaseRecord]:
    records: list[CaseRecord] = []
    results = payload.get("results", [])
    if not isinstance(results, list):
        return records
    for result in results:
        result_payload = _dict_value(result)
        flow = _string_value(result_payload.get("flow", ""))
        cases = result_payload.get("cases", [])
        if not isinstance(cases, list):
            continue
        for case in cases:
            case_payload = _dict_value(case)
            metrics = _dict_value(case_payload.get("metrics", {}))
            records.append(
                _record_from_payload(
                    source,
                    {
                        "flow": flow,
                        "case_id": case_payload.get("case_id", ""),
                        "iteration": case_payload.get("iteration", 0),
                        "metrics": metrics,
                    },
                )
            )
    return records


def _records_from_single_artifact_payload(payload: dict[str, Any], source: Path) -> list[CaseRecord]:
    metrics = _dict_value(payload.get("run_metrics", {}))
    tool_result = _dict_value(payload.get("tool_result", {}))
    if not metrics and not tool_result:
        return []
    merged = dict(metrics)
    if _string_value(merged.get("failure_reason", "")) == "":
        merged["failure_reason"] = _string_value(tool_result.get("failure_reason", ""))
    return [
        _record_from_payload(
            source,
            {
                "flow": payload.get("flow", ""),
                "case_id": payload.get("case_id", ""),
                "iteration": payload.get("iteration", 1),
                "metrics": merged,
            },
        )
    ]


def _iter_string_values(value: Any) -> list[str]:
    values: list[str] = []
    if isinstance(value, str):
        normalized = value.strip()
        if normalized:
            values.append(normalized)
        return values
    if isinstance(value, list):
        for item in value:
            values.extend(_iter_string_values(item))
        return values
    if isinstance(value, dict):
        for item in value.values():
            values.extend(_iter_string_values(item))
        return values
    return values


def _records_from_payload(payload: dict[str, Any], source: Path) -> list[CaseRecord]:
    eval_records = _records_from_eval_payload(payload, source)
    if eval_records:
        return eval_records
    return _records_from_single_artifact_payload(payload, source)


def _starts_with_any(value: str, prefixes: tuple[str, ...]) -> bool:
    return any(value.startswith(prefix) for prefix in prefixes)


def _contains_any(value: str, markers: tuple[str, ...]) -> bool:
    return any(marker in value for marker in markers)


def _is_schema_invalid_record(record: CaseRecord) -> bool:
    return _contains_any(record.failure_reason, SCHEMA_INVALID_MARKERS)


def _is_mcp_unavailable_record(record: CaseRecord) -> bool:
    return _starts_with_any(record.failure_reason, MCP_UNAVAILABLE_MARKERS)


def _is_transient_failure_reason(reason: str) -> bool:
    return _contains_any(reason, TRANSIENT_FAILURE_MARKERS)


def _is_transient_handling_record(record: CaseRecord) -> bool:
    retries_observed = record.call_construction_retries > 0 or record.grounding_retry_count > 0
    return retries_observed or _is_transient_failure_reason(record.failure_reason)


def _build_check_result(records: list[CaseRecord], marker_values: list[str], definition: CheckDefinition) -> dict[str, Any]:
    matched_records = [record for record in records if definition.case_predicate(record)]
    matched_strings = [value for value in marker_values if definition.value_predicate(value)]
    return {
        "status": "pass" if matched_records or matched_strings else "missing",
        "matched_case_records": len(matched_records),
        "matched_string_values": len(matched_strings),
        "sample_case_records": [asdict(record) for record in matched_records[:5]],
        "sample_string_values": matched_strings[:5],
    }


def build_report(input_paths: list[Path]) -> dict[str, Any]:
    all_records: list[CaseRecord] = []
    all_strings: list[str] = []
    for input_path in input_paths:
        payload = load_json_object(input_path)
        all_records.extend(_records_from_payload(payload, input_path))
        all_strings.extend(_iter_string_values(payload))

    check_definitions = (
        CheckDefinition(
            name="schema_invalid_model_package",
            case_predicate=_is_schema_invalid_record,
            value_predicate=lambda value: _contains_any(value, SCHEMA_INVALID_MARKERS),
        ),
        CheckDefinition(
            name="mcp_tool_unavailable",
            case_predicate=_is_mcp_unavailable_record,
            value_predicate=lambda value: _starts_with_any(value, MCP_UNAVAILABLE_MARKERS),
        ),
        CheckDefinition(
            name="llm_gateway_transient_handling",
            case_predicate=_is_transient_handling_record,
            value_predicate=_is_transient_failure_reason,
        ),
    )
    checks = {definition.name: _build_check_result(all_records, all_strings, definition) for definition in check_definitions}
    missing_checks = sorted([check_name for check_name, result in checks.items() if result["status"] != "pass"])
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_files": [str(path) for path in input_paths],
        "case_records_scanned": len(all_records),
        "missing_checks": missing_checks,
        "checks": checks,
    }


def _summary_lines(report: dict[str, Any]) -> list[str]:
    return [
        "# Failure Path Check Report",
        "",
        f"- Generated at: {report['generated_at']}",
        f"- Case records scanned: {report['case_records_scanned']}",
        f"- Input artifacts: {len(report['input_files'])}",
        "",
        "| Check | Status | Case Matches | String Matches |",
        "| --- | --- | ---: | ---: |",
    ]


def _check_table_lines(checks: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for check_name in sorted(checks):
        result = _dict_value(checks.get(check_name, {}))
        lines.append(
            f"| `{check_name}` | {result.get('status', 'missing')} | "
            f"{_int_value(result.get('matched_case_records', 0))} | "
            f"{_int_value(result.get('matched_string_values', 0))} |"
        )
    lines.append("")
    return lines


def _missing_check_lines(missing_checks: Any) -> list[str]:
    if not isinstance(missing_checks, list) or not missing_checks:
        return []
    lines = ["Missing checks:"]
    for check_name in sorted(str(item) for item in missing_checks):
        lines.append(f"- `{check_name}`")
    lines.append("")
    return lines


def _sample_record_lines(checks: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for check_name in sorted(checks):
        result = _dict_value(checks.get(check_name, {}))
        sample_records = result.get("sample_case_records", [])
        if not isinstance(sample_records, list) or not sample_records:
            continue
        lines.append(f"## {check_name} sample case records")
        for sample in sample_records:
            sample_payload = _dict_value(sample)
            lines.append(
                "- "
                f"{sample_payload.get('source', '')} "
                f"flow={sample_payload.get('flow', '')} "
                f"case_id={sample_payload.get('case_id', '')} "
                f"iteration={sample_payload.get('iteration', 0)} "
                f"failure_reason={sample_payload.get('failure_reason', '')} "
                f"call_construction_retries={sample_payload.get('call_construction_retries', 0)} "
                f"grounding_retry_count={sample_payload.get('grounding_retry_count', 0)} "
                f"business_success={sample_payload.get('business_success', False)}"
            )
        lines.append("")
    return lines


def render_markdown(report: dict[str, Any]) -> str:
    lines = _summary_lines(report)
    checks = _dict_value(report.get("checks", {}))
    lines.extend(_check_table_lines(checks))
    lines.extend(_missing_check_lines(report.get("missing_checks", [])))
    lines.extend(_sample_record_lines(checks))
    return "\n".join(lines).strip() + "\n"


def main() -> int:
    try:
        args = parse_args()
        input_paths = resolve_eval_input_paths(
            EvalInputSelector(
                eval_paths=[str(value) for value in args.eval_path],
                run_ids=[str(value) for value in args.run_id],
                eval_file_name=f"eval-{args.flow}-{args.scope}.json",
            )
        )
        report = build_report(input_paths)
        output_json_path, output_md_path = default_report_output_paths(
            OutputPathRequest(
                output_json=str(args.output_json),
                output_md=str(args.output_md),
                output_run_id=str(args.output_run_id),
                input_paths=input_paths,
                report_stem="failure-path-check-report",
            )
        )
        write_json(output_json_path, report)
        write_markdown(output_md_path, render_markdown(report))
        print(f"WROTE_FAILURE_PATH_REPORT_JSON={output_json_path}")
        print(f"WROTE_FAILURE_PATH_REPORT_MD={output_md_path}")

        if args.fail_on_missing and report["missing_checks"]:
            missing = ",".join(report["missing_checks"])
            print(f"FAILURE_PATH_CHECKS_MISSING={missing}")
            return 1
        return 0
    except ValueError as exc:
        print(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
