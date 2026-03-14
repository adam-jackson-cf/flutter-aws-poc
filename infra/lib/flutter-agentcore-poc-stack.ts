import { Stack, StackProps } from "aws-cdk-lib";
import { Construct } from "constructs";
import { emitStackOutputs } from "./stack-outputs";
import {
  RuntimeBindingParameters,
  createRuntimeBindingParameters,
} from "./runtime-bindings";
import { createGatewayRole, createGatewayUrl } from "./shared-gateway";

export class FlutterAgentCorePocStack extends Stack {
  constructor(scope: Construct, id: string, props?: StackProps) {
    super(scope, id, props);

    const runtimeBindings = createRuntimeBindingParameters(this);
    const llmGatewayRole = createGatewayRole(this);
    const gatewayUrl = createGatewayUrl(this, llmGatewayRole, runtimeBindings);
    emitStackOutputs(this, runtimeBindings, gatewayUrl);
  }
}
