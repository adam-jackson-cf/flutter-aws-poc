from pathlib import Path


def _script_content() -> str:
    script_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "promote-runtime-endpoint.sh"
    )
    return script_path.read_text(encoding="utf-8")


def test_script_defaults_and_usage_contract() -> None:
    content = _script_content()

    assert "scripts/promote-runtime-endpoint.sh [options]" in content
    assert 'STACK_NAME="FlutterAgentCorePocStack"' in content
    assert 'REGION="eu-west-1"' in content
    assert 'ENDPOINT_NAME="production"' in content
    assert "--candidate-eval-cmd <command>" in content


def test_script_resolves_runtime_id_and_candidate_version() -> None:
    content = _script_content()

    assert "Outputs[?OutputKey==`RuntimeId`].OutputValue" in content
    assert "list-agent-runtime-versions" in content
    assert 'status", "")).strip() != "READY"' in content
    assert "print(max(ready))" in content


def test_script_promotes_and_waits_for_endpoint_convergence() -> None:
    content = _script_content()

    assert "update-agent-runtime-endpoint" in content
    assert "--target-version \"$CANDIDATE_VERSION\"" in content
    assert "get-agent-runtime-endpoint" in content
    assert "if [[ \"$status\" == \"READY\" && \"$live_version\" == \"$CANDIDATE_VERSION\" ]]; then" in content
    assert "Timed out waiting for endpoint promotion convergence." in content
