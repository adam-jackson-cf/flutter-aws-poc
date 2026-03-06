import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
LINTER_SCRIPT = REPO_ROOT / "scripts" / "linters" / "flutter-design" / "check-flutter-design-compliance.py"
WAIVER_SCRIPT = REPO_ROOT / "scripts" / "linters" / "flutter-design" / "check-flutter-design-waivers.py"


def test_flutter_design_linter_supports_json_output_with_timings() -> None:
    completed = subprocess.run(
        [
            "python3",
            str(LINTER_SCRIPT),
            "--output",
            "json",
            "--timings",
            "--skip",
            "R3,R4",
        ],
        cwd=str(REPO_ROOT),
        check=False,
        text=True,
        capture_output=True,
    )

    assert completed.returncode in {0, 1}
    payload = json.loads(completed.stdout)
    assert payload["policy"] == "flutter-design-core-policy"
    assert payload["adapter"] == "flutter-design-poc-route-adapter"
    assert isinstance(payload["rules"], list) and payload["rules"]
    for rule in payload["rules"]:
        assert isinstance(rule["duration_ms"], int)
        assert rule["status"] in {"PASS", "FAIL", "SKIP"}


def test_waiver_validator_detects_expired_entries(tmp_path: Path) -> None:
    waivers_path = tmp_path / "waivers.json"
    waivers_path.write_text(
        json.dumps(
            {
                "name": "test-waivers",
                "waivers": [
                    {
                        "rule_id": "R3-PROCESS-SCOPE-DRIFT",
                        "owner": "platform@example.com",
                        "reason": "Temporary migration window",
                        "issue": "POC-123",
                        "expires_on": "2000-01-01",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        ["python3", str(WAIVER_SCRIPT), "--waivers", str(waivers_path)],
        cwd=str(REPO_ROOT),
        check=False,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 1
    assert "expired entries" in completed.stdout
