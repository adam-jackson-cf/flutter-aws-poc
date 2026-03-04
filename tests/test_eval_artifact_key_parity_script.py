import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "eval_artifact_key_parity.py"


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


def _eval_payload(*, actual_payload: dict, include_model_parity: bool = True) -> dict:
    payload = {
        "run_id": "run",
        "results": [
            {
                "flow": "native",
                "summary": {"tool_failure_rate": 0.0},
                "cases": [
                    {
                        "iteration": 1,
                        "case_id": "C-1",
                        "expected": {"intent": "bug_triage", "tool": "jira_get_issue_by_key"},
                        "actual": actual_payload,
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
    }
    if include_model_parity:
        payload["model_parity"] = {"gateway_model_id": "eu.amazon.nova-lite-v1:0"}
    return payload


def test_artifact_key_parity_detects_drift_and_fails_when_requested(tmp_path: Path) -> None:
    old_eval = tmp_path / "old.json"
    runtime_eval = tmp_path / "runtime.json"
    output_json = tmp_path / "parity.json"
    output_md = tmp_path / "parity.md"

    _write_json(
        old_eval,
        _eval_payload(
            actual_payload={
                "tool": "jira_get_issue_by_key",
                "selected_tool": "jira_get_issue_by_key",
                "artifact_s3_uri": "s3://bucket/key",
            },
            include_model_parity=True,
        ),
    )
    _write_json(
        runtime_eval,
        _eval_payload(
            actual_payload={
                "tool": "jira_get_issue_by_key",
                "execution_ref": "agent-runtime://native/C-1",
            },
            include_model_parity=False,
        ),
    )

    completed = _run(
        [
            "--old-eval-path",
            str(old_eval),
            "--runtime-eval-path",
            str(runtime_eval),
            "--output-json",
            str(output_json),
            "--output-md",
            str(output_md),
            "--fail-on-drift",
        ]
    )

    assert completed.returncode == 1
    report = json.loads(output_json.read_text(encoding="utf-8"))
    assert report["overall"]["has_drift"] is True
    section_map = {entry["name"]: entry for entry in report["sections"]}
    assert "selected_tool" in section_map["case_actual"]["missing_in_runtime"]
    assert "execution_ref" in section_map["case_actual"]["extra_in_runtime"]
    markdown = output_md.read_text(encoding="utf-8")
    assert "Old-vs-Runtime Artifact Key Parity" in markdown
    assert "`case_actual`" in markdown


def test_artifact_key_parity_default_output_path_uses_runtime_eval_dir(tmp_path: Path) -> None:
    old_eval = tmp_path / "reports" / "runs" / "old-run" / "eval" / "eval-both-route.json"
    runtime_eval = tmp_path / "reports" / "runs" / "runtime-run" / "eval" / "eval-both-route.json"
    payload = _eval_payload(actual_payload={"tool": "jira_get_issue_by_key", "selected_tool": "jira_get_issue_by_key"})
    _write_json(old_eval, payload)
    _write_json(runtime_eval, payload)

    completed = _run(
        [
            "--old-eval-path",
            str(old_eval),
            "--runtime-eval-path",
            str(runtime_eval),
            "--fail-on-drift",
        ]
    )

    assert completed.returncode == 0
    output_json = runtime_eval.parent / "old-vs-runtime-artifact-key-parity.json"
    output_md = runtime_eval.parent / "old-vs-runtime-artifact-key-parity.md"
    report = json.loads(output_json.read_text(encoding="utf-8"))
    assert report["overall"]["has_drift"] is False
    assert output_md.exists()
