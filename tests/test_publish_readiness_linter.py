import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "linters" / "flutter-design" / "check-publish-readiness.py"
ADAPTER_PATH = REPO_ROOT / "scripts" / "linters" / "flutter-design" / "flutter-design-linter-profile.json"
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "flutter-design"


def _run(repo_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--repo-root",
            str(repo_root),
            "--adapter",
            str(ADAPTER_PATH),
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )


def test_publish_readiness_accepts_valid_r1_fixture() -> None:
    completed = _run(FIXTURE_ROOT / "valid-r1")

    assert completed.returncode == 0
    assert "publish readiness checks passed" in completed.stdout


def test_publish_readiness_accepts_valid_r2_fixture() -> None:
    completed = _run(FIXTURE_ROOT / "valid-r2")

    assert completed.returncode == 0
    assert "publish readiness checks passed" in completed.stdout


def test_publish_readiness_rejects_missing_evaluation_pack() -> None:
    completed = _run(FIXTURE_ROOT / "invalid-missing-eval")

    assert completed.returncode == 1
    assert "referenced evaluation pack" in completed.stdout


def test_publish_readiness_rejects_coordination_without_delegates() -> None:
    completed = _run(FIXTURE_ROOT / "invalid-coordination")

    assert completed.returncode == 1
    assert "Coordination scope requires delegated_capability_ids" in completed.stdout


def test_publish_readiness_rejects_r2_without_workflow_contract() -> None:
    completed = _run(FIXTURE_ROOT / "invalid-r2-no-workflow")

    assert completed.returncode == 1
    assert "requires workflow_contract_ref" in completed.stdout
