import { Duration, Stack } from "aws-cdk-lib";
import {
  Effect,
  ManagedPolicy,
  PolicyStatement,
  Role,
  ServicePrincipal,
} from "aws-cdk-lib/aws-iam";
import {
  Code,
  Function,
  FunctionUrl,
  FunctionUrlAuthType,
  Runtime,
} from "aws-cdk-lib/aws-lambda";
import { RuntimeBindingParameters } from "./runtime-bindings";

export function createGatewayRole(stack: Stack): Role {
  const llmGatewayRole = new Role(stack, "LlmGatewayRole", {
    assumedBy: new ServicePrincipal("lambda.amazonaws.com"),
    description: "Execution role for LLM gateway control-plane function.",
  });

  llmGatewayRole.addManagedPolicy(
    ManagedPolicy.fromAwsManagedPolicyName(
      "service-role/AWSLambdaBasicExecutionRole",
    ),
  );
  llmGatewayRole.addToPolicy(
    new PolicyStatement({
      sid: "AllowGatewayBedrockRouting",
      effect: Effect.ALLOW,
      actions: [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream",
        "bedrock:Converse",
        "bedrock:ConverseStream",
      ],
      resources: ["*"],
    }),
  );
  return llmGatewayRole;
}

export function createGatewayUrl(
  stack: Stack,
  llmGatewayRole: Role,
  runtimeBindings: RuntimeBindingParameters,
): FunctionUrl {
  const llmGatewayFn = new Function(stack, "LlmGatewayFn", {
    runtime: Runtime.NODEJS_20_X,
    handler: "index.handler",
    timeout: Duration.seconds(15),
    role: llmGatewayRole,
    environment: {
      DEPLOYMENT_ENVIRONMENT:
        runtimeBindings.deploymentEnvironment.valueAsString,
      AGENT_RUNTIME_ID: runtimeBindings.runtimeId.valueAsString,
      AGENT_RUNTIME_ARN: runtimeBindings.runtimeArn.valueAsString,
      AGENT_RUNTIME_ENDPOINT_NAME:
        runtimeBindings.runtimeEndpointName.valueAsString,
    },
    code: Code.fromInline(
      [
        "exports.handler = async function handler(event) {",
        "  const response = {",
        "    status: 'ok',",
        "    environment: process.env.DEPLOYMENT_ENVIRONMENT || 'unknown',",
        "    runtimeIdPresent: Boolean(process.env.AGENT_RUNTIME_ID),",
        "    endpointName: process.env.AGENT_RUNTIME_ENDPOINT_NAME || 'unknown',",
        "  };",
        "  return {",
        "    statusCode: 200,",
        "    headers: { 'content-type': 'application/json' },",
        "    body: JSON.stringify(response),",
        "  };",
        "};",
      ].join("\n"),
    ),
    description: "Shared platform LLM gateway control-plane entrypoint.",
  });

  return llmGatewayFn.addFunctionUrl({
    authType: FunctionUrlAuthType.AWS_IAM,
  });
}
