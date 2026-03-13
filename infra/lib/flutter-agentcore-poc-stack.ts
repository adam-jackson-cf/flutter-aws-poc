import { CfnOutput, Stack, StackProps } from "aws-cdk-lib";
import { Construct } from "constructs";

export class FlutterAgentCorePocStack extends Stack {
  constructor(scope: Construct, id: string, props?: StackProps) {
    super(scope, id, props);

    new CfnOutput(this, "BaselineStatus", {
      value: "READY",
      description: "Indicates that the scaffold stack is healthy.",
    });

    new CfnOutput(this, "CanonicalRegion", {
      value: "eu-west-1",
      description: "Pinned region for the Flutter design baseline.",
    });
  }
}
