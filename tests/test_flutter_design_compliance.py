import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "linters" / "flutter-design" / "check-flutter-design-compliance.py"
ADAPTER_PATH = REPO_ROOT / "scripts" / "linters" / "flutter-design" / "flutter-design-linter-profile.json"
POLICY_PATH = REPO_ROOT / "scripts" / "linters" / "flutter-design" / "policy" / "flutter-design-policy.json"
WAIVER_SCRIPT = REPO_ROOT / "scripts" / "linters" / "flutter-design" / "check-flutter-design-waivers.py"
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "flutter-design"


def _run(repo_root: Path, *, skip: str | None = None) -> subprocess.CompletedProcess[str]:
    cmd = [
        sys.executable,
        str(SCRIPT_PATH),
        "--repo-root",
        str(repo_root),
        "--policy",
        str(POLICY_PATH),
        "--adapter",
        str(ADAPTER_PATH),
        "--output",
        "json",
        "--timings",
    ]
    if skip is not None:
        cmd.extend(["--skip", skip])
    return subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )


def test_compliance_passes_valid_r1_fixture_for_r1_r2_scope() -> None:
    completed = _run(FIXTURE_ROOT / "valid-r1", skip="R3")

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["policy"] == "flutter-design-contract-policy"
    assert payload["adapter"] == "flutter-design-contract-baseline"
    assert payload["summary"]["fail"] == 0


def test_compliance_passes_valid_r2_fixture() -> None:
    completed = _run(FIXTURE_ROOT / "valid-r2")

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["summary"]["fail"] == 0


def test_compliance_passes_valid_r1_process_fixture() -> None:
    completed = _run(FIXTURE_ROOT / "valid-r1-process")

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["summary"]["fail"] == 0


def test_compliance_fails_missing_publish_requirements() -> None:
    completed = _run(FIXTURE_ROOT / "invalid-missing-eval", skip="R3")

    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    failing_rule_ids = {rule["rule_id"] for rule in payload["rules"] if rule["status"] == "FAIL"}
    assert "R2-PUBLISH-READYNESS" in failing_rule_ids


def test_compliance_fails_invalid_r2_process_contract() -> None:
    completed = _run(FIXTURE_ROOT / "invalid-r2-no-workflow")

    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    failing_rule_ids = {rule["rule_id"] for rule in payload["rules"] if rule["status"] == "FAIL"}
    assert "R2-PROCESS-CONTRACT-GOVERNANCE" in failing_rule_ids


def test_compliance_fails_r1_customer_write_governance() -> None:
    completed = _run(FIXTURE_ROOT / "invalid-r1-customer-write")

    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    failing_rule_ids = {rule["rule_id"] for rule in payload["rules"] if rule["status"] == "FAIL"}
    assert "R2-PUBLISH-READYNESS" in failing_rule_ids


def test_waiver_validator_detects_expired_entries(tmp_path: Path) -> None:
    waivers_path = tmp_path / "waivers.json"
    waivers_path.write_text(
        json.dumps(
            {
                "name": "test-waivers",
                "waivers": [
                    {
                        "rule_id": "R2-PROCESS-CONTRACT-GOVERNANCE",
                        "owner": "platform@example.com",
                        "reason": "Temporary migration window",
                        "issue": "POC-123",
                        "expires_on": "2000-01-01"
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [sys.executable, str(WAIVER_SCRIPT), "--waivers", str(waivers_path)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 1
    assert "expired entries" in completed.stdout
