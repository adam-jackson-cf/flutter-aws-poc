import * as path from "path";
import {
  Duration,
  RemovalPolicy,
  Stack,
  StackProps,
  CfnOutput,
} from "aws-cdk-lib";
import { Construct } from "constructs";
import * as iam from "aws-cdk-lib/aws-iam";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as logs from "aws-cdk-lib/aws-logs";
import * as events from "aws-cdk-lib/aws-events";
import * as targets from "aws-cdk-lib/aws-events-targets";
import * as sfn from "aws-cdk-lib/aws-stepfunctions";
import * as sfnTasks from "aws-cdk-lib/aws-stepfunctions-tasks";
import * as agentcore from "@aws-cdk/aws-bedrock-agentcore-alpha";
import {
  ContractProperty,
  ContractSchema,
  GATEWAY_TOOLS,
} from "./generated/jira-tool-contract";

type InlineToolSchema = Parameters<typeof agentcore.ToolSchema.fromInline>[0];

type AgentCoreSchemaProperty =
  | {
      type: agentcore.SchemaDefinitionType.STRING;
      description?: string;
    }
  | {
      type: agentcore.SchemaDefinitionType.ARRAY;
      description?: string;
      items: {
        type: agentcore.SchemaDefinitionType.STRING;
      };
    };

type AgentCoreSchema = {
  type: agentcore.SchemaDefinitionType.OBJECT;
  properties: Record<string, AgentCoreSchemaProperty>;
  required: string[];
};

const toSchemaProperty = (
  property: ContractProperty,
): AgentCoreSchemaProperty => {
  const base = property.description
    ? { description: property.description }
    : {};
  if (property.type === "array_string") {
    return {
      ...base,
      type: agentcore.SchemaDefinitionType.ARRAY,
      items: { type: agentcore.SchemaDefinitionType.STRING },
    };
  }
  return {
    ...base,
    type: agentcore.SchemaDefinitionType.STRING,
  };
};

const toAgentCoreSchema = (schema: ContractSchema): AgentCoreSchema => ({
  type: agentcore.SchemaDefinitionType.OBJECT,
  properties: Object.fromEntries(
    Object.entries(schema.properties).map(([name, property]) => [
      name,
      toSchemaProperty(property),
    ]),
  ),
  required: [...schema.required],
});

const buildGatewayToolSchema = (): InlineToolSchema =>
  GATEWAY_TOOLS.map((tool) => ({
    name: tool.name,
    description: tool.description,
    inputSchema: toAgentCoreSchema(tool.input_schema),
    outputSchema: toAgentCoreSchema(tool.output_schema),
  }));

type LambdaFactory = (name: string, handler: string) => lambda.Function;

interface PipelineLambdas {
  parseLambda: lambda.Function;
  nativeLambda: lambda.Function;
  mcpLambda: lambda.Function;
  generateLambda: lambda.Function;
  evaluateLambda: lambda.Function;
  jiraToolLambda: lambda.Function;
}

interface RuntimeResources {
  runtime: agentcore.Runtime;
  runtimeEndpoint: ReturnType<agentcore.Runtime["addEndpoint"]>;
}

interface StackOutputResources {
  datasetBucket: s3.Bucket;
  runtimeResources: RuntimeResources;
  gateway: agentcore.Gateway;
  stateMachine: sfn.StateMachine;
}

export class FlutterAgentCorePocStack extends Stack {
  constructor(scope: Construct, id: string, props?: StackProps) {
    super(scope, id, props);

    const datasetBucket = this.createDatasetBucket();
    const makeLambda = this.createLambdaFactory(datasetBucket);
    const pipelineLambdas = this.createPipelineLambdas(makeLambda);
    const runtimeResources = this.createRuntimeResources();
    const gateway = this.createGateway(
      pipelineLambdas.jiraToolLambda,
      pipelineLambdas.mcpLambda,
    );
    const stateMachine = this.createStateMachine(pipelineLambdas);
    this.createNightlyEvaluationRule(stateMachine);
    this.emitOutputs({
      datasetBucket,
      runtimeResources,
      gateway,
      stateMachine,
    });
  }

  private createDatasetBucket(): s3.Bucket {
    return new s3.Bucket(this, "PocArtifactsBucket", {
      enforceSSL: true,
      versioned: true,
      removalPolicy: RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });
  }

  private createLambdaFactory(datasetBucket: s3.Bucket): LambdaFactory {
    const sharedLambdaEnv = {
      JIRA_BASE_URL: "https://jira.atlassian.com",
      BEDROCK_REGION: this.region,
      BEDROCK_MODEL_ID: "eu.amazon.nova-lite-v1:0",
      RESULT_BUCKET: datasetBucket.bucketName,
      FAIL_ON_TOOL_FAILURE: "false",
    };
    const lambdaCodePath = path.join(__dirname, "../../aws/lambda");
    return (name: string, handler: string): lambda.Function => {
      const lambdaLogGroup = new logs.LogGroup(this, `${name}LogGroup`, {
        retention: logs.RetentionDays.ONE_WEEK,
        removalPolicy: RemovalPolicy.DESTROY,
      });
      const fn = new lambda.Function(this, name, {
        runtime: lambda.Runtime.PYTHON_3_12,
        architecture: lambda.Architecture.ARM_64,
        handler,
        code: lambda.Code.fromAsset(lambdaCodePath),
        timeout: Duration.minutes(2),
        memorySize: 512,
        environment: sharedLambdaEnv,
        logGroup: lambdaLogGroup,
      });
      datasetBucket.grantReadWrite(fn);
      fn.addToRolePolicy(
        new iam.PolicyStatement({
          actions: ["bedrock:Converse", "bedrock:InvokeModel"],
          resources: ["*"],
        }),
      );
      return fn;
    };
  }

  private createPipelineLambdas(makeLambda: LambdaFactory): PipelineLambdas {
    return {
      parseLambda: makeLambda("ParseSopInputFn", "parse_stage.handler"),
      nativeLambda: makeLambda("RunNativeToolFn", "fetch_native_stage.handler"),
      mcpLambda: makeLambda("RunMcpToolFn", "fetch_mcp_stage.handler"),
      generateLambda: makeLambda(
        "GenerateResponseFn",
        "generate_stage.handler",
      ),
      evaluateLambda: makeLambda("EvaluateRunFn", "evaluate_stage.handler"),
      jiraToolLambda: makeLambda(
        "JiraToolTargetFn",
        "jira_tool_target.handler",
      ),
    };
  }

  private createRuntimeResources(): RuntimeResources {
    const runtimeArtifact = agentcore.AgentRuntimeArtifact.fromCodeAsset({
      path: path.join(__dirname, "../../runtime"),
      runtime: agentcore.AgentCoreRuntime.PYTHON_3_12,
      entrypoint: ["main.py"],
    });
    const runtime = new agentcore.Runtime(this, "SopAgentRuntime", {
      runtimeName: "flutterSopPocRuntime",
      description:
        "SOP runtime for native vs MCP Jira orchestration comparison",
      agentRuntimeArtifact: runtimeArtifact,
      networkConfiguration:
        agentcore.RuntimeNetworkConfiguration.usingPublicNetwork(),
      lifecycleConfiguration: {
        idleRuntimeSessionTimeout: Duration.minutes(15),
        maxLifetime: Duration.hours(8),
      },
      environmentVariables: {
        JIRA_BASE_URL: "https://jira.atlassian.com",
        BEDROCK_MODEL_ID: "eu.amazon.nova-lite-v1:0",
      },
      authorizerConfiguration:
        agentcore.RuntimeAuthorizerConfiguration.usingIAM(),
      tags: { project: "flutter-agentcore-poc" },
    });
    runtime.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ["bedrock:Converse", "bedrock:InvokeModel"],
        resources: ["*"],
      }),
    );
    const runtimeEndpoint = runtime.addEndpoint("production", {
      version: "1",
      description: "Stable endpoint for PoC orchestration runs",
    });
    return { runtime, runtimeEndpoint };
  }

  private createGateway(
    jiraToolLambda: lambda.Function,
    mcpLambda: lambda.Function,
  ): agentcore.Gateway {
    const gateway = new agentcore.Gateway(this, "SopGateway", {
      gatewayName: "flutter-sop-poc-gateway",
      description: "MCP gateway exposing Jira issue lookup tool for PoC",
      protocolConfiguration: new agentcore.McpProtocolConfiguration({
        instructions:
          "Use Jira issue tools for case triage and customer response SOP tasks",
        searchType: agentcore.McpGatewaySearchType.SEMANTIC,
        supportedVersions: [agentcore.MCPProtocolVersion.MCP_2025_03_26],
      }),
      authorizerConfiguration: agentcore.GatewayAuthorizer.usingAwsIam(),
      exceptionLevel: agentcore.GatewayExceptionLevel.DEBUG,
      tags: { project: "flutter-agentcore-poc" },
    });
    gateway.addLambdaTarget("JiraIssueLookupTarget", {
      gatewayTargetName: "jira-issue-tools",
      description: "Anonymous Jira issue retrieval target for evaluation flow",
      lambdaFunction: jiraToolLambda,
      toolSchema: agentcore.ToolSchema.fromInline(buildGatewayToolSchema()),
    });
    gateway.grantInvoke(mcpLambda);
    mcpLambda.addEnvironment("MCP_GATEWAY_URL", gateway.gatewayUrl ?? "");
    return gateway;
  }

  private createStateMachine(lambdas: PipelineLambdas): sfn.StateMachine {
    const parseTask = new sfnTasks.LambdaInvoke(this, "ParseNlpStage", {
      lambdaFunction: lambdas.parseLambda,
      payloadResponseOnly: true,
    });
    const nativeTask = new sfnTasks.LambdaInvoke(this, "FetchJiraNativeStage", {
      lambdaFunction: lambdas.nativeLambda,
      payloadResponseOnly: true,
    });
    const mcpTask = new sfnTasks.LambdaInvoke(this, "FetchJiraMcpStage", {
      lambdaFunction: lambdas.mcpLambda,
      payloadResponseOnly: true,
    });
    const nativeGenerateTask = new sfnTasks.LambdaInvoke(
      this,
      "GenerateCustomerResponseNativeStage",
      { lambdaFunction: lambdas.generateLambda, payloadResponseOnly: true },
    );
    const nativeEvaluateTask = new sfnTasks.LambdaInvoke(
      this,
      "EvaluateExecutionNativeStage",
      { lambdaFunction: lambdas.evaluateLambda, payloadResponseOnly: true },
    );
    const mcpGenerateTask = new sfnTasks.LambdaInvoke(
      this,
      "GenerateCustomerResponseMcpStage",
      { lambdaFunction: lambdas.generateLambda, payloadResponseOnly: true },
    );
    const mcpEvaluateTask = new sfnTasks.LambdaInvoke(
      this,
      "EvaluateExecutionMcpStage",
      { lambdaFunction: lambdas.evaluateLambda, payloadResponseOnly: true },
    );
    const nativeChain = nativeTask
      .next(nativeGenerateTask)
      .next(nativeEvaluateTask);
    const mcpChain = mcpTask.next(mcpGenerateTask).next(mcpEvaluateTask);
    const definition = parseTask.next(
      new sfn.Choice(this, "SelectToolFlow")
        .when(sfn.Condition.stringEquals("$.flow", "mcp"), mcpChain)
        .otherwise(nativeChain),
    );
    return new sfn.StateMachine(this, "SopAutomationPipeline", {
      definitionBody: sfn.DefinitionBody.fromChainable(definition),
      timeout: Duration.minutes(10),
      logs: {
        destination: new logs.LogGroup(this, "SopPipelineLogGroup", {
          retention: logs.RetentionDays.ONE_WEEK,
          removalPolicy: RemovalPolicy.DESTROY,
        }),
        level: sfn.LogLevel.ALL,
      },
      tracingEnabled: true,
    });
  }

  private createNightlyEvaluationRule(stateMachine: sfn.StateMachine): void {
    new events.Rule(this, "NightlyEvaluationRule", {
      schedule: events.Schedule.cron({ minute: "15", hour: "1" }),
      targets: [
        new targets.SfnStateMachine(stateMachine, {
          input: events.RuleTargetInput.fromObject({
            flow: "mcp",
            request_text:
              "Please triage JRASERVER-79286 and draft a customer-safe response update.",
            case_id: "scheduled_jira_case",
            expected_tool: "jira_get_issue_priority_context",
          }),
        }),
      ],
    });
  }

  private emitOutputs(resources: StackOutputResources): void {
    new CfnOutput(this, "RuntimeId", {
      value: resources.runtimeResources.runtime.agentRuntimeId,
    });
    new CfnOutput(this, "RuntimeEndpointArn", {
      value: resources.runtimeResources.runtimeEndpoint.agentRuntimeEndpointArn,
    });
    new CfnOutput(this, "GatewayId", { value: resources.gateway.gatewayId });
    new CfnOutput(this, "GatewayUrl", {
      value: resources.gateway.gatewayUrl ?? "",
    });
    new CfnOutput(this, "StateMachineArn", {
      value: resources.stateMachine.stateMachineArn,
    });
    new CfnOutput(this, "ArtifactsBucketName", {
      value: resources.datasetBucket.bucketName,
    });
  }
}
