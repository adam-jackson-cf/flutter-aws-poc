from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "run-ci-quality-gates.sh"


def test_quality_gate_runner_exposes_lane_model() -> None:
    content = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "--lane=" in content
    assert "run_lane_fast_r1r2" in content
    assert "run_lane_extended_r3r4" in content
    assert "run_lane_nightly_full" in content


def test_duplicate_llm_gateway_invocation_not_in_default_core_lane() -> None:
    content = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "Deprecated LLM gateway parity check" in content
    assert "RUN_DEPRECATED_LLM_GATEWAY_PARITY" in content
    assert "run_step \"LLM gateway non-bypass guard\"" not in content
