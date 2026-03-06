from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "run-ci-quality-gates.sh"
PRE_COMMIT_CONFIG_PATH = REPO_ROOT / ".pre-commit-config.yaml"
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci-quality-gates.yml"


def test_quality_gate_runner_exposes_lane_model() -> None:
    content = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "--lane=" in content
    assert "run_lane_fast_r1r2" in content
    assert "run_lane_extended_r3r4" in content
    assert "run_lane_nightly_full" in content
    assert "run_ci_python_syntax_guard" in content
    assert "UV_PYTHON_VERSION" in content
    assert "UV_REQUIREMENTS_FILE" in content
    assert "UV_VENV_PYTHON_BIN" in content
    assert "resolve_python_runner" in content
    assert "run_python" in content
    assert "--print-python-cmd" in content
    assert "--help|-h" in content


def test_duplicate_llm_gateway_invocation_not_in_default_core_lane() -> None:
    content = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "Deprecated LLM gateway parity check" in content
    assert "RUN_DEPRECATED_LLM_GATEWAY_PARITY" in content
    assert "run_step \"LLM gateway non-bypass guard\"" not in content


def test_duplication_analyzer_removed_from_quality_gates() -> None:
    content = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "quality:jscpd" not in content
    assert "run_duplication_signals" not in content
    assert "RUN_DUPLICATION_SIGNALS" not in content
    assert "DUPLICATION_SIGNAL_" not in content


def test_cdk_synth_runs_only_in_nightly_lane() -> None:
    content = SCRIPT_PATH.read_text(encoding="utf-8")
    assert 'run_step "CDK synth (infra)" run_cdk_synth' in content

    core_block = content.split("run_lane_quality_gates_core() {", maxsplit=1)[1].split(
        "run_lane_extended_r3r4() {", maxsplit=1
    )[0]
    extended_block = content.split("run_lane_extended_r3r4() {", maxsplit=1)[1].split(
        "run_lane_nightly_full() {", maxsplit=1
    )[0]
    nightly_block = content.split("run_lane_nightly_full() {", maxsplit=1)[1].split(
        "run_lane_release_hardening() {", maxsplit=1
    )[0]
    release_block = content.split("run_lane_release_hardening() {", maxsplit=1)[1].split(
        "run_lane() {", maxsplit=1
    )[0]

    assert 'run_step "CDK synth (infra)" run_cdk_synth' not in core_block
    assert 'run_step "CDK synth (infra)" run_cdk_synth' not in extended_block
    assert 'run_step "CDK synth (infra)" run_cdk_synth' in nightly_block
    assert 'run_step "CDK synth (infra)" run_cdk_synth' not in release_block


def test_pre_commit_pins_ci_python_parser_version() -> None:
    content = PRE_COMMIT_CONFIG_PATH.read_text(encoding="utf-8")
    assert "UV_PYTHON_VERSION=3.12.7" in content
    assert "UV_REQUIREMENTS_FILE=requirements.txt" in content


def test_ci_workflow_uses_uv_pinned_python() -> None:
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert 'UV_PYTHON_VERSION: "3.12.7"' in content
    assert "astral-sh/setup-uv@v4" in content
    assert "actions/cache@v4" in content
    assert "Build uv gate environment" in content
    assert "UV_VENV_PYTHON_BIN=.ci-venv/bin/python" in content
    assert "uv pip install --python .ci-venv/bin/python -r \"$UV_REQUIREMENTS_FILE\"" in content
    assert 'python-version: "3.12.7"' in content
    assert "python -m pip install -r requirements.txt" not in content
