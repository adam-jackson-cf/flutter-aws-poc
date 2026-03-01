from pathlib import Path


def test_nightly_rule_includes_expected_tool_input() -> None:
    stack_file = (
        Path(__file__).resolve().parents[1]
        / "infra"
        / "lib"
        / "flutter-agentcore-poc-stack.ts"
    )
    content = stack_file.read_text(encoding="utf-8")

    assert "createNightlyEvaluationRule" in content
    assert 'flow: "mcp"' in content
    assert "expected_tool" in content
    assert 'expected_tool: "jira_get_issue_priority_context"' in content
