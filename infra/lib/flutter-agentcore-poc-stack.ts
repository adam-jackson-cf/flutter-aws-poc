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
import * as secretsmanager from "aws-cdk-lib/aws-secretsmanager";
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
const DEFAULT_BEDROCK_MODEL_ID = "eu.amazon.nova-lite-v1:0";

interface ModelGatewayEnvConfig {
  modelId: string;
  isExplicitModelId: boolean;
  modelProvider: string;
  openAiApiKeySecretArn: string;
  openAiBaseUrl: string;
  openAiReasoningEffort: string;
  openAiTextVerbosity: string;
  openAiMaxOutputTokens: string;
}

interface PipelineLambdas {
  llmGatewayLambda: lambda.Function;
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

interface StackLifecycleConfig {
  ephemeral: boolean;
  logRetention: logs.RetentionDays;
}

export class FlutterAgentCorePocStack extends Stack {
  constructor(scope: Construct, id: string, props?: StackProps) {
    super(scope, id, props);

    const lifecycleConfig = this.stackLifecycleConfig();
    const modelGatewayConfig = this.modelGatewayConfig();
    const datasetBucket = this.createDatasetBucket(lifecycleConfig.ephemeral);
    const makeLambda = this.createLambdaFactory(
      datasetBucket,
      modelGatewayConfig,
      lifecycleConfig.logRetention,
    );
    const pipelineLambdas = this.createPipelineLambdas(
      makeLambda,
      modelGatewayConfig,
    );
    const runtimeResources = this.createRuntimeResources(
      modelGatewayConfig,
      pipelineLambdas.llmGatewayLambda,
    );
    const gateway = this.createGateway(
      pipelineLambdas.jiraToolLambda,
      pipelineLambdas.mcpLambda,
    );
    const stateMachine = this.createStateMachine(
      pipelineLambdas,
      lifecycleConfig.logRetention,
    );
    this.createNightlyEvaluationRule(stateMachine);
    this.emitOutputs({
      datasetBucket,
      runtimeResources,
      gateway,
      stateMachine,
    });
  }

  private stackLifecycleConfig(): StackLifecycleConfig {
    const rawEphemeral = String(
      this.node.tryGetContext("ephemeral") ??
        process.env.EPHEMERAL_STACK ??
        "false",
    )
      .trim()
      .toLowerCase();
    const ephemeral = rawEphemeral === "true" || rawEphemeral === "1";
    return {
      ephemeral,
      logRetention: ephemeral
        ? logs.RetentionDays.ONE_WEEK
        : logs.RetentionDays.ONE_MONTH,
    };
  }

  private createDatasetBucket(ephemeral: boolean): s3.Bucket {
    return new s3.Bucket(this, "PocArtifactsBucket", {
      enforceSSL: true,
      versioned: true,
      removalPolicy: ephemeral ? RemovalPolicy.DESTROY : RemovalPolicy.RETAIN,
      autoDeleteObjects: ephemeral,
    });
  }

  private modelGatewayConfig(): ModelGatewayEnvConfig {
    const modelIdSource = this.readTrimmed("modelId", "MODEL_ID", "");
    const modelId = modelIdSource || DEFAULT_BEDROCK_MODEL_ID;
    const modelProvider = this.resolveModelProvider(
      this.readTrimmed("modelProvider", "MODEL_PROVIDER", "auto"),
    );
    return {
      modelId,
      isExplicitModelId: modelIdSource.length > 0,
      modelProvider,
      openAiApiKeySecretArn: this.readTrimmed(
        "openAiApiKeySecretArn",
        "OPENAI_API_KEY_SECRET_ARN",
        "",
      ),
      openAiBaseUrl: this.readTrimmed(
        "openAiBaseUrl",
        "OPENAI_BASE_URL",
        "https://api.openai.com/v1",
      ),
      openAiReasoningEffort: this.readTrimmed(
        "openAiReasoningEffort",
        "OPENAI_REASONING_EFFORT",
        "medium",
      ),
      openAiTextVerbosity: this.readTrimmed(
        "openAiTextVerbosity",
        "OPENAI_TEXT_VERBOSITY",
        "medium",
      ),
      openAiMaxOutputTokens: this.readTrimmed(
        "openAiMaxOutputTokens",
        "OPENAI_MAX_OUTPUT_TOKENS",
        "2000",
      ),
    };
  }

  private readTrimmed(
    contextKey: string,
    envKey: string,
    fallback: string,
  ): string {
    return String(
      this.node.tryGetContext(contextKey) ?? process.env[envKey] ?? fallback,
    ).trim();
  }

  private resolveModelProvider(value: string): "auto" | "bedrock" | "openai" {
    if (value === "bedrock" || value === "openai") {
      return value;
    }
    return "auto";
  }

  private createLambdaFactory(
    datasetBucket: s3.Bucket,
    modelGatewayConfig: ModelGatewayEnvConfig,
    logRetention: logs.RetentionDays,
  ): LambdaFactory {
    const sharedLambdaEnv = {
      JIRA_BASE_URL: "https://jira.atlassian.com",
      BEDROCK_REGION: this.region,
      MODEL_ID: modelGatewayConfig.modelId,
      MODEL_PROVIDER: modelGatewayConfig.modelProvider,
      OPENAI_API_KEY_SECRET_ARN: modelGatewayConfig.openAiApiKeySecretArn,
      OPENAI_BASE_URL: modelGatewayConfig.openAiBaseUrl,
      OPENAI_REASONING_EFFORT: modelGatewayConfig.openAiReasoningEffort,
      OPENAI_TEXT_VERBOSITY: modelGatewayConfig.openAiTextVerbosity,
      OPENAI_MAX_OUTPUT_TOKENS: modelGatewayConfig.openAiMaxOutputTokens,
      RESULT_BUCKET: datasetBucket.bucketName,
      FAIL_ON_TOOL_FAILURE: "false",
    };
    const lambdaCodePath = path.join(__dirname, "../../aws/lambda");
    return (name: string, handler: string): lambda.Function => {
      const lambdaLogGroup = new logs.LogGroup(this, `${name}LogGroup`, {
        retention: logRetention,
        removalPolicy: RemovalPolicy.RETAIN,
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
      return fn;
    };
  }

  private createPipelineLambdas(
    makeLambda: LambdaFactory,
    modelGatewayConfig: ModelGatewayEnvConfig,
  ): PipelineLambdas {
    const lambdas = {
      llmGatewayLambda: makeLambda("LlmGatewayFn", "llm_gateway_stage.handler"),
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
    this.grantGatewayModelProviderAccess(lambdas.llmGatewayLambda);
    this.configureLlmGatewayRouting(lambdas);
    this.grantModelGatewaySecrets(
      lambdas,
      modelGatewayConfig.openAiApiKeySecretArn,
    );
    return lambdas;
  }

  private grantModelGatewaySecrets(
    lambdas: PipelineLambdas,
    openAiApiKeySecretArn: string,
  ): void {
    if (!openAiApiKeySecretArn) {
      return;
    }
    const openAiApiKeySecret = secretsmanager.Secret.fromSecretCompleteArn(
      this,
      "OpenAiApiKeySecret",
      openAiApiKeySecretArn,
    );
    openAiApiKeySecret.grantRead(lambdas.llmGatewayLambda);
  }

  private grantGatewayModelProviderAccess(
    llmGatewayLambda: lambda.Function,
  ): void {
    llmGatewayLambda.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ["bedrock:Converse", "bedrock:InvokeModel"],
        resources: ["*"],
      }),
    );
  }

  private configureLlmGatewayRouting(lambdas: PipelineLambdas): void {
    const gatewayFunctionName = lambdas.llmGatewayLambda.functionName;
    const callers = [
      lambdas.parseLambda,
      lambdas.nativeLambda,
      lambdas.mcpLambda,
      lambdas.generateLambda,
    ];
    callers.forEach((caller) => {
      caller.addEnvironment("LLM_GATEWAY_FUNCTION_NAME", gatewayFunctionName);
      lambdas.llmGatewayLambda.grantInvoke(caller);
    });
  }

  private createRuntimeResources(
    modelGatewayConfig: ModelGatewayEnvConfig,
    llmGatewayLambda: lambda.Function,
  ): RuntimeResources {
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
        MODEL_ID: modelGatewayConfig.modelId,
        BEDROCK_REGION: this.region,
        MODEL_PROVIDER: modelGatewayConfig.modelProvider,
        OPENAI_REASONING_EFFORT: modelGatewayConfig.openAiReasoningEffort,
        OPENAI_TEXT_VERBOSITY: modelGatewayConfig.openAiTextVerbosity,
        OPENAI_MAX_OUTPUT_TOKENS: modelGatewayConfig.openAiMaxOutputTokens,
        LLM_GATEWAY_FUNCTION_NAME: llmGatewayLambda.functionName,
      },
      authorizerConfiguration:
        agentcore.RuntimeAuthorizerConfiguration.usingIAM(),
      tags: { project: "flutter-agentcore-poc" },
    });
    llmGatewayLambda.grantInvoke(runtime);
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

  private createStateMachine(
    lambdas: PipelineLambdas,
    logRetention: logs.RetentionDays,
  ): sfn.StateMachine {
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
          retention: logRetention,
          removalPolicy: RemovalPolicy.RETAIN,
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
