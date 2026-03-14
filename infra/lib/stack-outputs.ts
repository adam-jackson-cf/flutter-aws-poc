import { CfnOutput, Stack } from "aws-cdk-lib";
import { FunctionUrl } from "aws-cdk-lib/aws-lambda";
import { RuntimeBindingParameters } from "./runtime-bindings";

export function emitStackOutputs(
  stack: Stack,
  runtimeBindings: RuntimeBindingParameters,
  gatewayUrl: FunctionUrl,
): void {
  new CfnOutput(stack, "BaselineStatus", {
    value: "READY_SHARED_PLATFORM_CONTRACT",
    description:
      "Indicates that the shared platform deployment contract is healthy.",
  });
  new CfnOutput(stack, "CanonicalRegion", {
    value: "eu-west-1",
    description: "Pinned region for the Flutter design baseline.",
  });
  new CfnOutput(stack, "DeploymentEnvironmentOutput", {
    value: runtimeBindings.deploymentEnvironment.valueAsString,
    description: "Active deployment environment for this stack instance.",
  });
  new CfnOutput(stack, "RuntimeArn", {
    value: runtimeBindings.runtimeArn.valueAsString,
    description:
      "AgentCore runtime ARN bound to this shared platform deployment.",
  });
  new CfnOutput(stack, "RuntimeId", {
    value: runtimeBindings.runtimeId.valueAsString,
    description:
      "AgentCore runtime id bound to this shared platform deployment.",
  });
  new CfnOutput(stack, "GatewayUrl", {
    value: gatewayUrl.url,
    description: "Gateway URL for the shared LLM entrypoint.",
  });
  new CfnOutput(stack, "RuntimeEndpointArn", {
    value: runtimeBindings.runtimeEndpointArn.valueAsString,
    description: "AgentCore runtime endpoint ARN for this deployment.",
  });
  new CfnOutput(stack, "RuntimeEndpointStatus", {
    value: runtimeBindings.runtimeEndpointStatus.valueAsString,
    description:
      "AgentCore runtime endpoint status captured at deployment time.",
  });
}
