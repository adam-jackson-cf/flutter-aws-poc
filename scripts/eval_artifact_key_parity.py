#!/usr/bin/env python3
"""Build deterministic old-vs-runtime artifact key parity reports."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from eval_report_utils import (
    EvalInputSelector,
    OutputPathRequest,
    default_report_output_paths,
    load_json_object,
    resolve_eval_input_paths,
    write_json,
    write_markdown,
)


@dataclass(frozen=True)
class ParityInputSpec:
    eval_path: str
    run_id: str
    flow: str
    scope: str
    label: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate old-vs-runtime artifact key parity report.")
    parser.add_argument("--old-eval-path", default="")
    parser.add_argument("--old-run-id", default="")
    parser.add_argument("--runtime-eval-path", default="")
    parser.add_argument("--runtime-run-id", default="")
    parser.add_argument("--flow", default="both", choices=["native", "mcp", "both"])
    parser.add_argument("--scope", default="route", choices=["route", "full"])
    parser.add_argument("--output-json", default="")
    parser.add_argument("--output-md", default="")
    parser.add_argument("--output-run-id", default="", help="Optional run id used for default output location.")
    parser.add_argument("--max-diff-keys", type=int, default=200, help="Maximum diff keys listed per section.")
    parser.add_argument("--fail-on-drift", action="store_true", help="Exit non-zero when any key drift is found.")
    return parser.parse_args()


def _dict_value(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return value


def _flatten_key_paths(value: Any, prefix: str = "") -> set[str]:
    if isinstance(value, dict):
        paths: set[str] = set()
        for key in sorted(value):
            child_prefix = key if not prefix else f"{prefix}.{key}"
            paths.add(child_prefix)
            paths.update(_flatten_key_paths(value[key], child_prefix))
        return paths
    if isinstance(value, list):
        list_prefix = "[]" if not prefix else f"{prefix}[]"
        paths: set[str] = {list_prefix}
        for item in value:
            paths.update(_flatten_key_paths(item, list_prefix))
        return paths
    if prefix:
        return {prefix}
    return set()


def _is_eval_payload(payload: dict[str, Any]) -> bool:
    return isinstance(payload.get("results"), list)


def _top_level_paths(payload: dict[str, Any]) -> set[str]:
    trimmed = {key: value for key, value in payload.items() if key != "results"}
    return _flatten_key_paths(trimmed)


def _iter_result_entries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("results", [])
    if not isinstance(rows, list):
        return []
    output: list[dict[str, Any]] = []
    for entry in rows:
        parsed = _dict_value(entry)
        if parsed:
            output.append(parsed)
    return output


def _result_entry_paths(payload: dict[str, Any]) -> set[str]:
    paths: set[str] = set()
    for entry in _iter_result_entries(payload):
        trimmed = {key: value for key, value in entry.items() if key != "cases"}
        paths.update(_flatten_key_paths(trimmed))
    return paths


def _iter_case_entries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for entry in _iter_result_entries(payload):
        entry_cases = entry.get("cases", [])
        if not isinstance(entry_cases, list):
            continue
        for case in entry_cases:
            parsed = _dict_value(case)
            if parsed:
                cases.append(parsed)
    return cases


def _case_entry_paths(payload: dict[str, Any]) -> set[str]:
    paths: set[str] = set()
    for entry in _iter_case_entries(payload):
        trimmed = {
            key: value
            for key, value in entry.items()
            if key not in {"expected", "actual", "metrics", "judge"}
        }
        paths.update(_flatten_key_paths(trimmed))
    return paths


def _case_field_paths(payload: dict[str, Any], field_name: str) -> set[str]:
    paths: set[str] = set()
    for entry in _iter_case_entries(payload):
        paths.update(_flatten_key_paths(_dict_value(entry.get(field_name, {}))))
    return paths


def _build_sections(payload: dict[str, Any]) -> dict[str, set[str]]:
    if _is_eval_payload(payload):
        return {
            "top_level": _top_level_paths(payload),
            "model_parity": _flatten_key_paths(_dict_value(payload.get("model_parity", {}))),
            "flow_result": _result_entry_paths(payload),
            "case_entry": _case_entry_paths(payload),
            "case_expected": _case_field_paths(payload, "expected"),
            "case_actual": _case_field_paths(payload, "actual"),
            "case_metrics": _case_field_paths(payload, "metrics"),
        }
    return {"artifact_top_level": _flatten_key_paths(payload)}


def _truncate(items: list[str], max_items: int) -> tuple[list[str], int]:
    safe_max = max(1, max_items)
    if len(items) <= safe_max:
        return items, 0
    return items[:safe_max], len(items) - safe_max


def _compare_section(name: str, key_sets: tuple[set[str], set[str]], max_diff_keys: int) -> dict[str, Any]:
    old_keys, runtime_keys = key_sets
    shared = old_keys.intersection(runtime_keys)
    union = old_keys.union(runtime_keys)
    missing_in_runtime = sorted(old_keys.difference(runtime_keys))
    extra_in_runtime = sorted(runtime_keys.difference(old_keys))
    missing_sample, missing_truncated = _truncate(missing_in_runtime, max_diff_keys)
    extra_sample, extra_truncated = _truncate(extra_in_runtime, max_diff_keys)
    return {
        "name": name,
        "old_key_count": len(old_keys),
        "runtime_key_count": len(runtime_keys),
        "shared_key_count": len(shared),
        "parity_rate": (len(shared) / len(union)) if union else 1.0,
        "missing_in_runtime_count": len(missing_in_runtime),
        "missing_in_runtime": missing_sample,
        "missing_in_runtime_truncated_count": missing_truncated,
        "extra_in_runtime_count": len(extra_in_runtime),
        "extra_in_runtime": extra_sample,
        "extra_in_runtime_truncated_count": extra_truncated,
    }


def build_report(
    *,
    old_path: Path,
    runtime_path: Path,
    max_diff_keys: int,
) -> dict[str, Any]:
    old_payload = load_json_object(old_path)
    runtime_payload = load_json_object(runtime_path)
    old_sections = _build_sections(old_payload)
    runtime_sections = _build_sections(runtime_payload)
    section_names = sorted(set(old_sections.keys()).union(runtime_sections.keys()))

    sections: list[dict[str, Any]] = []
    overall_missing = 0
    overall_extra = 0
    for name in section_names:
        section = _compare_section(
            name=name,
            key_sets=(old_sections.get(name, set()), runtime_sections.get(name, set())),
            max_diff_keys=max_diff_keys,
        )
        overall_missing += int(section["missing_in_runtime_count"])
        overall_extra += int(section["extra_in_runtime_count"])
        sections.append(section)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "old_input_file": str(old_path),
        "runtime_input_file": str(runtime_path),
        "overall": {
            "sections_compared": len(sections),
            "missing_in_runtime_total": overall_missing,
            "extra_in_runtime_total": overall_extra,
            "has_drift": bool(overall_missing or overall_extra),
        },
        "sections": sections,
    }


def _section_summary_row(section: dict[str, Any]) -> str:
    return (
        f"| `{section.get('name', '')}` | {section.get('old_key_count', 0)} | "
        f"{section.get('runtime_key_count', 0)} | {section.get('shared_key_count', 0)} | "
        f"{float(section.get('parity_rate', 0.0)):.4f} | {section.get('missing_in_runtime_count', 0)} | "
        f"{section.get('extra_in_runtime_count', 0)} |"
    )


def _append_key_list(lines: list[str], heading: str, listing: dict[str, Any]) -> None:
    keys = listing.get("keys", [])
    if not isinstance(keys, list) or not keys:
        return
    lines.append(heading)
    for key in keys:
        lines.append(f"- `{key}`")
    truncated_count = int(listing.get("truncated_count", 0))
    if truncated_count > 0:
        lines.append(f"- ... plus {truncated_count} more")


def _drift_section_lines(section: dict[str, Any]) -> list[str]:
    if int(section.get("missing_in_runtime_count", 0)) == 0 and int(section.get("extra_in_runtime_count", 0)) == 0:
        return []
    lines = [f"## {section.get('name', '')}"]
    missing = section.get("missing_in_runtime", [])
    if isinstance(missing, list):
        _append_key_list(
            lines,
            "Missing in runtime:",
            {
                "keys": [str(value) for value in missing],
                "truncated_count": int(section.get("missing_in_runtime_truncated_count", 0)),
            },
        )
    extra = section.get("extra_in_runtime", [])
    if isinstance(extra, list):
        _append_key_list(
            lines,
            "Extra in runtime:",
            {
                "keys": [str(value) for value in extra],
                "truncated_count": int(section.get("extra_in_runtime_truncated_count", 0)),
            },
        )
    lines.append("")
    return lines


def render_markdown(report: dict[str, Any]) -> str:
    overall = _dict_value(report.get("overall", {}))
    lines = [
        "# Old-vs-Runtime Artifact Key Parity",
        "",
        f"- Generated at: {report.get('generated_at', '')}",
        f"- Old input: {report.get('old_input_file', '')}",
        f"- Runtime input: {report.get('runtime_input_file', '')}",
        f"- Sections compared: {overall.get('sections_compared', 0)}",
        f"- Missing-in-runtime keys: {overall.get('missing_in_runtime_total', 0)}",
        f"- Extra-in-runtime keys: {overall.get('extra_in_runtime_total', 0)}",
        "",
        "| Section | Old Keys | Runtime Keys | Shared Keys | Parity | Missing | Extra |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    sections = report.get("sections", [])
    if isinstance(sections, list):
        for section in sections:
            lines.append(_section_summary_row(_dict_value(section)))
    lines.append("")

    if isinstance(sections, list):
        for section in sections:
            lines.extend(_drift_section_lines(_dict_value(section)))

    return "\n".join(lines).strip() + "\n"


def _resolve_single_eval_path(spec: ParityInputSpec) -> Path:
    paths = resolve_eval_input_paths(
        EvalInputSelector(
            eval_paths=[spec.eval_path] if spec.eval_path.strip() else [],
            run_ids=[spec.run_id] if spec.run_id.strip() else [],
            eval_file_name=f"eval-{spec.flow}-{spec.scope}.json",
        )
    )
    if len(paths) != 1:
        raise ValueError(f"{spec.label}_input_ambiguous")
    return paths[0]


def main() -> int:
    try:
        args = parse_args()
        old_path = _resolve_single_eval_path(
            ParityInputSpec(
                eval_path=str(args.old_eval_path),
                run_id=str(args.old_run_id),
                flow=str(args.flow),
                scope=str(args.scope),
                label="old",
            )
        )
        runtime_path = _resolve_single_eval_path(
            ParityInputSpec(
                eval_path=str(args.runtime_eval_path),
                run_id=str(args.runtime_run_id),
                flow=str(args.flow),
                scope=str(args.scope),
                label="runtime",
            )
        )
        report = build_report(old_path=old_path, runtime_path=runtime_path, max_diff_keys=max(1, int(args.max_diff_keys)))
        output_json_path, output_md_path = default_report_output_paths(
            OutputPathRequest(
                output_json=str(args.output_json),
                output_md=str(args.output_md),
                output_run_id=str(args.output_run_id or args.runtime_run_id),
                input_paths=[runtime_path],
                report_stem="old-vs-runtime-artifact-key-parity",
            )
        )
        write_json(output_json_path, report)
        write_markdown(output_md_path, render_markdown(report))
        print(f"WROTE_ARTIFACT_PARITY_REPORT_JSON={output_json_path}")
        print(f"WROTE_ARTIFACT_PARITY_REPORT_MD={output_md_path}")

        if args.fail_on_drift and bool(_dict_value(report.get("overall", {})).get("has_drift", False)):
            print("ARTIFACT_KEY_PARITY_DRIFT=detected")
            return 1
        return 0
    except ValueError as exc:
        print(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
