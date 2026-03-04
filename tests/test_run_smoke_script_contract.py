from pathlib import Path


def _script_content() -> str:
    script_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "run-smoke-euw1.sh"
    )
    return script_path.read_text(encoding="utf-8")


def test_script_exposes_runtime_qualifier_option() -> None:
    content = _script_content()

    assert "--agent-runtime-qualifier <v> Default: production" in content
    assert 'AGENT_RUNTIME_QUALIFIER="production"' in content
    assert "--agent-runtime-qualifier)" in content
    assert 'AGENT_RUNTIME_QUALIFIER="${2:-}"' in content


def test_script_passes_runtime_qualifier_to_eval_command() -> None:
    content = _script_content()

    assert "--agent-runtime-qualifier \"$AGENT_RUNTIME_QUALIFIER\"" in content
