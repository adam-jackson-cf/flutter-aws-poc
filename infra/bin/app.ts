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

new FlutterAgentCorePocStack(app, "FlutterAgentCorePocStack", {
  env: { account, region },
  description:
    "Flutter design baseline stack for build and governance scaffolding",
});
