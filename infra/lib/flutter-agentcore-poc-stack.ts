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

export class FlutterAgentCorePocStack extends Stack {
  constructor(scope: Construct, id: string, props?: StackProps) {
    super(scope, id, props);

    const datasetBucket = new s3.Bucket(this, "PocArtifactsBucket", {
      enforceSSL: true,
      versioned: true,
      removalPolicy: RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });

    const sharedLambdaEnv = {
      JIRA_BASE_URL: "https://jira.atlassian.com",
      BEDROCK_REGION: this.region,
      BEDROCK_MODEL_ID: "eu.amazon.nova-lite-v1:0",
      RESULT_BUCKET: datasetBucket.bucketName,
      FAIL_ON_TOOL_FAILURE: "false",
    };

    const lambdaCodePath = path.join(__dirname, "../../aws/lambda");

    const makeLambda = (name: string, handler: string): lambda.Function => {
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

    const parseLambda = makeLambda("ParseSopInputFn", "parse_stage.handler");
    const nativeLambda = makeLambda(
      "RunNativeToolFn",
      "fetch_native_stage.handler",
    );
    const mcpLambda = makeLambda("RunMcpToolFn", "fetch_mcp_stage.handler");
    const generateLambda = makeLambda(
      "GenerateResponseFn",
      "generate_stage.handler",
    );
    const evaluateLambda = makeLambda(
      "EvaluateRunFn",
      "evaluate_stage.handler",
    );
    const jiraToolLambda = makeLambda(
      "JiraToolTargetFn",
      "jira_tool_target.handler",
    );

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
      tags: {
        project: "flutter-agentcore-poc",
      },
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
      tags: {
        project: "flutter-agentcore-poc",
      },
    });

    gateway.addLambdaTarget("JiraIssueLookupTarget", {
      gatewayTargetName: "jira-issue-tools",
      description: "Anonymous Jira issue retrieval target for evaluation flow",
      lambdaFunction: jiraToolLambda,
      toolSchema: agentcore.ToolSchema.fromInline([
        {
          name: "jira_get_issue_by_key",
          description:
            "Fetch a public Jira issue by key, including summary, status, priority and labels.",
          inputSchema: {
            type: agentcore.SchemaDefinitionType.OBJECT,
            properties: {
              issue_key: {
                type: agentcore.SchemaDefinitionType.STRING,
                description: "Issue key such as JRASERVER-79286",
              },
            },
            required: ["issue_key"],
          },
          outputSchema: {
            type: agentcore.SchemaDefinitionType.OBJECT,
            properties: {
              key: { type: agentcore.SchemaDefinitionType.STRING },
              summary: { type: agentcore.SchemaDefinitionType.STRING },
              status: { type: agentcore.SchemaDefinitionType.STRING },
            },
            required: ["key", "summary", "status"],
          },
        },
        {
          name: "jira_get_issue_status_snapshot",
          description: "Get current status and update timestamp for an issue.",
          inputSchema: {
            type: agentcore.SchemaDefinitionType.OBJECT,
            properties: {
              issue_key: {
                type: agentcore.SchemaDefinitionType.STRING,
                description: "Issue key such as JRASERVER-79286",
              },
            },
            required: ["issue_key"],
          },
          outputSchema: {
            type: agentcore.SchemaDefinitionType.OBJECT,
            properties: {
              key: { type: agentcore.SchemaDefinitionType.STRING },
              status: { type: agentcore.SchemaDefinitionType.STRING },
              updated: { type: agentcore.SchemaDefinitionType.STRING },
            },
            required: ["key", "status", "updated"],
          },
        },
        {
          name: "jira_get_issue_priority_context",
          description: "Get issue priority and derived risk band.",
          inputSchema: {
            type: agentcore.SchemaDefinitionType.OBJECT,
            properties: {
              issue_key: {
                type: agentcore.SchemaDefinitionType.STRING,
                description: "Issue key such as JRASERVER-79286",
              },
            },
            required: ["issue_key"],
          },
          outputSchema: {
            type: agentcore.SchemaDefinitionType.OBJECT,
            properties: {
              key: { type: agentcore.SchemaDefinitionType.STRING },
              priority: { type: agentcore.SchemaDefinitionType.STRING },
              risk_band: { type: agentcore.SchemaDefinitionType.STRING },
            },
            required: ["key", "priority", "risk_band"],
          },
        },
        {
          name: "jira_get_issue_labels",
          description: "Get labels attached to an issue.",
          inputSchema: {
            type: agentcore.SchemaDefinitionType.OBJECT,
            properties: {
              issue_key: {
                type: agentcore.SchemaDefinitionType.STRING,
                description: "Issue key such as JRASERVER-79286",
              },
            },
            required: ["issue_key"],
          },
          outputSchema: {
            type: agentcore.SchemaDefinitionType.OBJECT,
            properties: {
              key: { type: agentcore.SchemaDefinitionType.STRING },
              labels: {
                type: agentcore.SchemaDefinitionType.ARRAY,
                items: { type: agentcore.SchemaDefinitionType.STRING },
              },
            },
            required: ["key", "labels"],
          },
        },
        {
          name: "jira_get_issue_project_key",
          description: "Get the Jira project key extracted from an issue key.",
          inputSchema: {
            type: agentcore.SchemaDefinitionType.OBJECT,
            properties: {
              issue_key: {
                type: agentcore.SchemaDefinitionType.STRING,
                description: "Issue key such as JRASERVER-79286",
              },
            },
            required: ["issue_key"],
          },
          outputSchema: {
            type: agentcore.SchemaDefinitionType.OBJECT,
            properties: {
              key: { type: agentcore.SchemaDefinitionType.STRING },
              project_key: { type: agentcore.SchemaDefinitionType.STRING },
            },
            required: ["key", "project_key"],
          },
        },
        {
          name: "jira_get_issue_update_timestamp",
          description: "Get the most recent update timestamp for an issue.",
          inputSchema: {
            type: agentcore.SchemaDefinitionType.OBJECT,
            properties: {
              issue_key: {
                type: agentcore.SchemaDefinitionType.STRING,
                description: "Issue key such as JRASERVER-79286",
              },
            },
            required: ["issue_key"],
          },
          outputSchema: {
            type: agentcore.SchemaDefinitionType.OBJECT,
            properties: {
              key: { type: agentcore.SchemaDefinitionType.STRING },
              updated: { type: agentcore.SchemaDefinitionType.STRING },
            },
            required: ["key", "updated"],
          },
        },
        {
          name: "jira_get_issue_risk_flags",
          description: "Get risk-related flags derived from issue labels.",
          inputSchema: {
            type: agentcore.SchemaDefinitionType.OBJECT,
            properties: {
              issue_key: {
                type: agentcore.SchemaDefinitionType.STRING,
                description: "Issue key such as JRASERVER-79286",
              },
            },
            required: ["issue_key"],
          },
          outputSchema: {
            type: agentcore.SchemaDefinitionType.OBJECT,
            properties: {
              key: { type: agentcore.SchemaDefinitionType.STRING },
              risk_flags: {
                type: agentcore.SchemaDefinitionType.ARRAY,
                items: { type: agentcore.SchemaDefinitionType.STRING },
              },
            },
            required: ["key", "risk_flags"],
          },
        },
        {
          name: "jira_get_customer_sentiment",
          description:
            "Get a sentiment signal for customer communication readiness.",
          inputSchema: {
            type: agentcore.SchemaDefinitionType.OBJECT,
            properties: {
              issue_key: {
                type: agentcore.SchemaDefinitionType.STRING,
                description: "Issue key such as JRASERVER-79286",
              },
            },
            required: ["issue_key"],
          },
          outputSchema: {
            type: agentcore.SchemaDefinitionType.OBJECT,
            properties: {
              key: { type: agentcore.SchemaDefinitionType.STRING },
              sentiment: { type: agentcore.SchemaDefinitionType.STRING },
              status: { type: agentcore.SchemaDefinitionType.STRING },
            },
            required: ["key", "sentiment", "status"],
          },
        },
        {
          name: "jira_get_issue_customer_message_seed",
          description: "Get a short message seed based on the issue summary.",
          inputSchema: {
            type: agentcore.SchemaDefinitionType.OBJECT,
            properties: {
              issue_key: {
                type: agentcore.SchemaDefinitionType.STRING,
                description: "Issue key such as JRASERVER-79286",
              },
            },
            required: ["issue_key"],
          },
          outputSchema: {
            type: agentcore.SchemaDefinitionType.OBJECT,
            properties: {
              key: { type: agentcore.SchemaDefinitionType.STRING },
              seed_message: { type: agentcore.SchemaDefinitionType.STRING },
            },
            required: ["key", "seed_message"],
          },
        },
      ]),
    });

    gateway.grantInvoke(mcpLambda);
    mcpLambda.addEnvironment("MCP_GATEWAY_URL", gateway.gatewayUrl ?? "");

    const parseTask = new sfnTasks.LambdaInvoke(this, "ParseNlpStage", {
      lambdaFunction: parseLambda,
      payloadResponseOnly: true,
    });

    const nativeTask = new sfnTasks.LambdaInvoke(this, "FetchJiraNativeStage", {
      lambdaFunction: nativeLambda,
      payloadResponseOnly: true,
    });

    const mcpTask = new sfnTasks.LambdaInvoke(this, "FetchJiraMcpStage", {
      lambdaFunction: mcpLambda,
      payloadResponseOnly: true,
    });

    const nativeGenerateTask = new sfnTasks.LambdaInvoke(
      this,
      "GenerateCustomerResponseNativeStage",
      {
        lambdaFunction: generateLambda,
        payloadResponseOnly: true,
      },
    );

    const nativeEvaluateTask = new sfnTasks.LambdaInvoke(
      this,
      "EvaluateExecutionNativeStage",
      {
        lambdaFunction: evaluateLambda,
        payloadResponseOnly: true,
      },
    );

    const mcpGenerateTask = new sfnTasks.LambdaInvoke(
      this,
      "GenerateCustomerResponseMcpStage",
      {
        lambdaFunction: generateLambda,
        payloadResponseOnly: true,
      },
    );

    const mcpEvaluateTask = new sfnTasks.LambdaInvoke(
      this,
      "EvaluateExecutionMcpStage",
      {
        lambdaFunction: evaluateLambda,
        payloadResponseOnly: true,
      },
    );

    const nativeChain = nativeTask
      .next(nativeGenerateTask)
      .next(nativeEvaluateTask);
    const mcpChain = mcpTask.next(mcpGenerateTask).next(mcpEvaluateTask);

    const chooseToolFlow = new sfn.Choice(this, "SelectToolFlow")
      .when(sfn.Condition.stringEquals("$.flow", "mcp"), mcpChain)
      .otherwise(nativeChain);

    const definition = parseTask.next(chooseToolFlow);

    const stateMachine = new sfn.StateMachine(this, "SopAutomationPipeline", {
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

    new events.Rule(this, "NightlyEvaluationRule", {
      schedule: events.Schedule.cron({ minute: "15", hour: "1" }),
      targets: [
        new targets.SfnStateMachine(stateMachine, {
          input: events.RuleTargetInput.fromObject({
            flow: "mcp",
            request_text:
              "Please triage JRASERVER-79286 and draft a customer-safe response update.",
            case_id: "scheduled_jira_case",
          }),
        }),
      ],
    });

    new CfnOutput(this, "RuntimeId", { value: runtime.agentRuntimeId });
    new CfnOutput(this, "RuntimeEndpointArn", {
      value: runtimeEndpoint.agentRuntimeEndpointArn,
    });
    new CfnOutput(this, "GatewayId", { value: gateway.gatewayId });
    new CfnOutput(this, "GatewayUrl", { value: gateway.gatewayUrl ?? "" });
    new CfnOutput(this, "StateMachineArn", {
      value: stateMachine.stateMachineArn,
    });
    new CfnOutput(this, "ArtifactsBucketName", {
      value: datasetBucket.bucketName,
    });
  }
}
