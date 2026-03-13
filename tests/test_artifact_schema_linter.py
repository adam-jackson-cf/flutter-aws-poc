import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "linters" / "flutter-design" / "check-artifact-schemas.py"
ADAPTER_PATH = REPO_ROOT / "scripts" / "linters" / "flutter-design" / "flutter-design-linter-profile.json"
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "flutter-design"


def _run(repo_root: Path, *artifact_types: str) -> subprocess.CompletedProcess[str]:
    cmd = [
        sys.executable,
        str(SCRIPT_PATH),
        "--repo-root",
        str(repo_root),
        "--adapter",
        str(ADAPTER_PATH),
    ]
    for artifact_type in artifact_types:
        cmd.extend(["--artifact-type", artifact_type])
    return subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )


def test_schema_linter_accepts_valid_r1_fixture() -> None:
    completed = _run(FIXTURE_ROOT / "valid-r1")

    assert completed.returncode == 0
    assert "PASS capability_definitions" in completed.stdout
    assert "PASS safety_envelopes" in completed.stdout
    assert "PASS evaluation_packs" in completed.stdout


def test_schema_linter_accepts_valid_r2_fixture_with_optional_workflow_contracts() -> None:
    completed = _run(FIXTURE_ROOT / "valid-r2")

    assert completed.returncode == 0
    assert "PASS workflow_contracts" in completed.stdout


def test_schema_linter_rejects_invalid_capability_definition() -> None:
    completed = _run(FIXTURE_ROOT / "invalid-schema", "capability_definitions")

    assert completed.returncode == 1
    assert "safety_envelope_ref" in completed.stdout


def test_schema_linter_requires_capabilities_in_empty_repo(tmp_path: Path) -> None:
    empty_root = tmp_path / "empty"
    empty_root.mkdir()
    for folder_name in ("capability-definitions", "safety-envelopes", "evaluation-packs", "workflow-contracts"):
        (empty_root / folder_name).mkdir(exist_ok=True)

    completed = _run(empty_root)

    assert completed.returncode == 1
    assert "expected at least one JSON artefact" in completed.stdout
