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


def test_runtime_model_binding_uses_bedrock_specific_setting() -> None:
    stack_file = (
        Path(__file__).resolve().parents[1]
        / "infra"
        / "lib"
        / "flutter-agentcore-poc-stack.ts"
    )
    content = stack_file.read_text(encoding="utf-8")

    assert "runtimeBedrockModelConfig" in content
    assert "BEDROCK_MODEL_ID: runtimeBedrockModelId" in content
    assert "createRuntimeResources(" in content
    assert "runtimeBedrockModelConfig.modelId" in content


def test_openai_requires_explicit_runtime_bedrock_model() -> None:
    stack_file = (
        Path(__file__).resolve().parents[1]
        / "infra"
        / "lib"
        / "flutter-agentcore-poc-stack.ts"
    )
    content = stack_file.read_text(encoding="utf-8")

    assert "MODEL_PROVIDER=openai requires explicit BEDROCK_MODEL_ID/runtimeBedrockModelId" in content
    assert "runtimeBedrockModelConfig.isExplicit" in content


def test_stack_does_not_hardcode_non_eu_region_model_guard() -> None:
    stack_file = (
        Path(__file__).resolve().parents[1]
        / "infra"
        / "lib"
        / "flutter-agentcore-poc-stack.ts"
    )
    content = stack_file.read_text(encoding="utf-8")

    assert 'this.region !== "eu-west-1"' not in content
    assert "Deployments outside eu-west-1 require explicit MODEL_ID and BEDROCK_MODEL_ID/runtimeBedrockModelId" not in content


def test_stack_lifecycle_config_controls_ephemeral_behavior() -> None:
    stack_file = (
        Path(__file__).resolve().parents[1]
        / "infra"
        / "lib"
        / "flutter-agentcore-poc-stack.ts"
    )
    content = stack_file.read_text(encoding="utf-8")

    assert "EPHEMERAL_STACK" in content
    assert "createDatasetBucket(lifecycleConfig.ephemeral)" in content
    assert "RemovalPolicy.RETAIN" in content
