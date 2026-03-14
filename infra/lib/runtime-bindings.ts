import { CfnParameter, Stack } from "aws-cdk-lib";

export type RuntimeBindingParameters = {
  deploymentEnvironment: CfnParameter;
  runtimeId: CfnParameter;
  runtimeArn: CfnParameter;
  runtimeEndpointName: CfnParameter;
  runtimeEndpointArn: CfnParameter;
  runtimeEndpointStatus: CfnParameter;
};

export function createRuntimeBindingParameters(
  stack: Stack,
): RuntimeBindingParameters {
  return {
    deploymentEnvironment: new CfnParameter(stack, "DeploymentEnvironment", {
      type: "String",
      allowedValues: ["sandbox", "preprod", "prod"],
      default:
        process.env.FLUTTER_DEPLOYMENT_ENVIRONMENT ??
        stack.node.tryGetContext("deploymentEnvironment") ??
        "sandbox",
      description: "Deployment environment for shared platform infrastructure.",
    }),
    runtimeId: new CfnParameter(stack, "AgentRuntimeId", {
      type: "String",
      minLength: 3,
      description:
        "Existing AgentCore runtime id for the target deployment environment.",
    }),
    runtimeArn: new CfnParameter(stack, "AgentRuntimeArn", {
      type: "String",
      minLength: 20,
      description:
        "Existing AgentCore runtime ARN for the target deployment environment.",
    }),
    runtimeEndpointName: new CfnParameter(stack, "AgentRuntimeEndpointName", {
      type: "String",
      default:
        process.env.AGENT_RUNTIME_ENDPOINT_NAME ??
        stack.node.tryGetContext("agentRuntimeEndpointName") ??
        "sandbox",
      minLength: 1,
      maxLength: 64,
      allowedPattern: "^[A-Za-z0-9][A-Za-z0-9-]{0,63}$",
      description: "AgentCore runtime endpoint name for this environment.",
    }),
    runtimeEndpointArn: new CfnParameter(stack, "AgentRuntimeEndpointArn", {
      type: "String",
      minLength: 20,
      description:
        "AgentCore runtime endpoint ARN for the target deployment environment.",
    }),
    runtimeEndpointStatus: new CfnParameter(
      stack,
      "AgentRuntimeEndpointStatus",
      {
        type: "String",
        allowedValues: [
          "CREATING",
          "CREATE_FAILED",
          "UPDATING",
          "UPDATE_FAILED",
          "READY",
          "DELETING",
          "UNKNOWN",
        ],
        default:
          process.env.AGENT_RUNTIME_ENDPOINT_STATUS ??
          stack.node.tryGetContext("agentRuntimeEndpointStatus") ??
          "READY",
        description:
          "Most recent runtime endpoint status captured at deployment time.",
      },
    ),
  };
}
