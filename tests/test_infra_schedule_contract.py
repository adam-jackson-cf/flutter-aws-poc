from pathlib import Path


def test_no_nightly_evaluation_rule_configured() -> None:
    stack_file = (
        Path(__file__).resolve().parents[1]
        / "infra"
        / "lib"
        / "flutter-agentcore-poc-stack.ts"
    )
    content = stack_file.read_text(encoding="utf-8")

    assert "createNightlyEvaluationRule" not in content
    assert "NightlyEvaluationRule" not in content


def test_runtime_model_binding_uses_gateway_model_setting() -> None:
    stack_file = (
        Path(__file__).resolve().parents[1]
        / "infra"
        / "lib"
        / "flutter-agentcore-poc-stack.ts"
    )
    content = stack_file.read_text(encoding="utf-8")

    assert "modelGatewayConfig.modelId" in content
    assert "MODEL_ID: modelGatewayConfig.modelId" in content


def test_stack_has_no_openai_runtime_bedrock_guard() -> None:
    stack_file = (
        Path(__file__).resolve().parents[1]
        / "infra"
        / "lib"
        / "flutter-agentcore-poc-stack.ts"
    )
    content = stack_file.read_text(encoding="utf-8")

    assert "MODEL_PROVIDER=openai requires explicit BEDROCK_MODEL_ID/runtimeBedrockModelId" not in content
    assert "runtimeBedrockModelConfig.isExplicit" not in content


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
