#!/usr/bin/env node
import "source-map-support/register";
import * as cdk from "aws-cdk-lib";
import { FlutterAgentCorePocStack } from "../lib/flutter-agentcore-poc-stack";

const app = new cdk.App();
const account = process.env.CDK_DEFAULT_ACCOUNT;
const region =
  process.env.CDK_DEFAULT_REGION ??
  app.node.tryGetContext("defaultRegion") ??
  "eu-west-1";
const deploymentEnvironment =
  process.env.FLUTTER_DEPLOYMENT_ENVIRONMENT ??
  app.node.tryGetContext("deploymentEnvironment") ??
  "sandbox";

if (region !== "eu-west-1") {
  throw new Error(
    `FlutterAgentCorePocStack is pinned to eu-west-1. Received: ${region}`,
  );
}

new FlutterAgentCorePocStack(app, "FlutterAgentCorePocStack", {
  env: { account, region },
  description: `Flutter shared platform deployment (${deploymentEnvironment}) for build and governance scaffolding`,
});
