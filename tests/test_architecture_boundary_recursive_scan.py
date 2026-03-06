from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "linters" / "architecture-boundaries" / "check-architecture-boundaries.py"


def test_architecture_boundary_checker_scans_nested_modules() -> None:
    content = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "DOMAIN_ROOT.rglob(\"*.py\")" in content
    assert "LAMBDA_ROOT.rglob(\"*.py\")" in content
