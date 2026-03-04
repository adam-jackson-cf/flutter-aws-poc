from pathlib import Path


def _stack_content() -> str:
    stack_file = (
        Path(__file__).resolve().parents[1]
        / "infra"
        / "lib"
        / "flutter-agentcore-poc-stack.ts"
    )
    return stack_file.read_text(encoding="utf-8")


def test_no_nightly_evaluation_rule_configured() -> None:
    content = _stack_content()

    assert "createNightlyEvaluationRule" not in content
    assert "NightlyEvaluationRule" not in content


def test_runtime_model_binding_uses_gateway_model_setting() -> None:
    content = _stack_content()

    assert "modelGatewayConfig.modelId" in content
    assert "MODEL_ID: modelGatewayConfig.modelId" in content


def test_stack_has_no_openai_runtime_bedrock_guard() -> None:
    content = _stack_content()

    assert "MODEL_PROVIDER=openai requires explicit BEDROCK_MODEL_ID/runtimeBedrockModelId" not in content
    assert "runtimeBedrockModelConfig.isExplicit" not in content


def test_stack_does_not_hardcode_non_eu_region_model_guard() -> None:
    content = _stack_content()

    assert 'this.region !== "eu-west-1"' not in content
    assert "Deployments outside eu-west-1 require explicit MODEL_ID and BEDROCK_MODEL_ID/runtimeBedrockModelId" not in content


def test_stack_lifecycle_config_controls_ephemeral_behavior() -> None:
    content = _stack_content()

    assert "EPHEMERAL_STACK" in content
    assert "createDatasetBucket(lifecycleConfig.ephemeral)" in content
    assert "RemovalPolicy.RETAIN" in content


def test_stack_contract_is_runtime_owned_not_state_machine_owned() -> None:
    content = _stack_content()

    assert "new agentcore.Runtime(this, \"SopAgentRuntime\"" in content
    assert 'entrypoint: ["runtime/main.py"]' in content
    assert "gateway.grantInvoke(runtime);" in content
    assert "createStateMachine(" not in content
    assert "StateMachineArn" not in content
    assert "RunMcpToolFn" not in content
    assert "RunNativeToolFn" not in content


def test_runtime_artifact_packaging_excludes_large_non_runtime_paths() -> None:
    content = _stack_content()

    assert 'path: path.join(__dirname, "../..")' in content
    assert '"infra/**"' in content
    assert '"infra/cdk.out/**"' in content
    assert '"**/cdk.out/**"' in content
    assert '"**/.cache/**"' in content
    assert '"node_modules/**"' in content
    assert '"docs/**"' in content
    assert '"evals/**"' in content
    assert '"tests/**"' in content
    assert "bundling:" in content
    assert "requirements-agentcore-runtime.txt" in content


def test_runtime_endpoint_version_is_configurable_from_context_or_env() -> None:
    content = _stack_content()

    assert 'DEFAULT_PRODUCTION_RUNTIME_VERSION = "2"' in content
    assert '"productionRuntimeVersion"' in content
    assert '"PRODUCTION_RUNTIME_VERSION"' in content
    assert "resolveRuntimeVersion(" in content
    assert "version: inputs.runtimeVersionConfig.productionRuntimeVersion" in content
    assert 'version: "2"' not in content


def test_stack_outputs_runtime_and_gateway_contracts() -> None:
    content = _stack_content()

    assert "new CfnOutput(this, \"RuntimeArn\"" in content
    assert "new CfnOutput(this, \"RuntimeVersion\"" in content
    assert "new CfnOutput(this, \"RuntimeStatus\"" in content
    assert "new CfnOutput(this, \"RuntimeEndpointConfiguredVersion\"" in content
    assert "new CfnOutput(this, \"RuntimeEndpointLiveVersion\"" in content
    assert "new CfnOutput(this, \"RuntimeEndpointTargetVersion\"" in content
    assert "new CfnOutput(this, \"RuntimeEndpointStatus\"" in content
    assert "new CfnOutput(this, \"RuntimeEndpointConfiguredTargetVersion\"" in content
    assert "new CfnOutput(this, \"GatewayUrl\"" in content
    assert "new CfnOutput(this, \"ArtifactsBucketName\"" in content
