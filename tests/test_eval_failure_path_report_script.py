import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "eval_failure_path_report.py"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        cwd=str(REPO_ROOT),
        check=False,
        capture_output=True,
        text=True,
    )


def _eval_payload_with_failure_paths() -> dict:
    return {
        "run_id": "r1",
        "results": [
            {
                "flow": "native",
                "cases": [
                    {
                        "iteration": 1,
                        "case_id": "schema-invalid-case",
                        "metrics": {
                            "failure_reason": "artifact_schema_invalid:contract_version_missing",
                            "business_success": False,
                            "call_construction_retries": 0,
                            "grounding_retry_count": 0,
                        },
                    },
                    {
                        "iteration": 1,
                        "case_id": "transient-recovered-case",
                        "metrics": {
                            "failure_reason": "",
                            "business_success": True,
                            "call_construction_retries": 1,
                            "grounding_retry_count": 0,
                        },
                    },
                ],
            },
            {
                "flow": "mcp",
                "cases": [
                    {
                        "iteration": 1,
                        "case_id": "mcp-unavailable-case",
                        "metrics": {
                            "failure_reason": "mcp_gateway_unavailable:offline",
                            "business_success": False,
                            "call_construction_retries": 0,
                            "grounding_retry_count": 0,
                        },
                    }
                ],
            },
        ],
    }


def test_failure_path_report_detects_required_checks(tmp_path: Path) -> None:
    input_path = tmp_path / "eval.json"
    output_json = tmp_path / "failure-path.json"
    output_md = tmp_path / "failure-path.md"
    _write_json(input_path, _eval_payload_with_failure_paths())

    completed = _run(
        [
            "--eval-path",
            str(input_path),
            "--output-json",
            str(output_json),
            "--output-md",
            str(output_md),
        ]
    )

    assert completed.returncode == 0
    report = json.loads(output_json.read_text(encoding="utf-8"))
    checks = report["checks"]
    assert report["case_records_scanned"] == 3
    assert report["missing_checks"] == []
    assert checks["schema_invalid_model_package"]["status"] == "pass"
    assert checks["mcp_tool_unavailable"]["status"] == "pass"
    assert checks["llm_gateway_transient_handling"]["status"] == "pass"
    markdown = output_md.read_text(encoding="utf-8")
    assert "`schema_invalid_model_package`" in markdown
    assert "`mcp_tool_unavailable`" in markdown
    assert "`llm_gateway_transient_handling`" in markdown


def test_failure_path_report_fail_on_missing_returns_nonzero(tmp_path: Path) -> None:
    input_path = tmp_path / "eval-empty.json"
    output_json = tmp_path / "failure-path-empty.json"
    output_md = tmp_path / "failure-path-empty.md"
    _write_json(
        input_path,
        {
            "run_id": "r2",
            "results": [
                {
                    "flow": "native",
                    "cases": [
                        {
                            "iteration": 1,
                            "case_id": "baseline",
                            "metrics": {
                                "failure_reason": "",
                                "business_success": True,
                                "call_construction_retries": 0,
                                "grounding_retry_count": 0,
                            },
                        }
                    ],
                }
            ],
        },
    )

    completed = _run(
        [
            "--eval-path",
            str(input_path),
            "--output-json",
            str(output_json),
            "--output-md",
            str(output_md),
            "--fail-on-missing",
        ]
    )

    assert completed.returncode == 1
    assert "FAILURE_PATH_CHECKS_MISSING=" in completed.stdout
    report = json.loads(output_json.read_text(encoding="utf-8"))
    assert sorted(report["missing_checks"]) == [
        "llm_gateway_transient_handling",
        "mcp_tool_unavailable",
        "schema_invalid_model_package",
    ]
