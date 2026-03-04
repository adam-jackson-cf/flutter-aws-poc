import * as path from "path";
import {
  Duration,
  RemovalPolicy,
  Stack,
  StackProps,
  CfnOutput,
  DockerImage,
} from "aws-cdk-lib";
import { Construct } from "constructs";
import * as iam from "aws-cdk-lib/aws-iam";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as logs from "aws-cdk-lib/aws-logs";
import * as secretsmanager from "aws-cdk-lib/aws-secretsmanager";
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

const DEFAULT_BEDROCK_MODEL_ID = "eu.amazon.nova-lite-v1:0";
const DEFAULT_PRODUCTION_RUNTIME_VERSION = "2";

interface ModelGatewayEnvConfig {
  modelId: string;
  modelProvider: "auto" | "bedrock" | "openai";
  openAiApiKeySecretArn: string;
  openAiBaseUrl: string;
  openAiReasoningEffort: string;
  openAiTextVerbosity: string;
  openAiMaxOutputTokens: string;
}

interface SupportLambdas {
  llmGatewayLambda: lambda.Function;
  jiraToolLambda: lambda.Function;
}

interface RuntimeVersionConfig {
  productionRuntimeVersion: string;
}

interface RuntimeResources {
  runtime: agentcore.Runtime;
  runtimeEndpoint: ReturnType<agentcore.Runtime["addEndpoint"]>;
}

interface RuntimeResourceInputs {
  datasetBucket: s3.Bucket;
  gateway: agentcore.Gateway;
  llmGatewayLambda: lambda.Function;
  modelGatewayConfig: ModelGatewayEnvConfig;
  runtimeVersionConfig: RuntimeVersionConfig;
}

interface StackOutputResources {
  datasetBucket: s3.Bucket;
  runtimeResources: RuntimeResources;
  runtimeVersionConfig: RuntimeVersionConfig;
  gateway: agentcore.Gateway;
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
    const runtimeVersionConfig = this.runtimeVersionConfig();
    const datasetBucket = this.createDatasetBucket(lifecycleConfig.ephemeral);
    const supportLambdas = this.createSupportLambdas(
      lifecycleConfig.logRetention,
      modelGatewayConfig,
    );
    const gateway = this.createGateway(supportLambdas.jiraToolLambda);
    const runtimeResources = this.createRuntimeResources({
      datasetBucket,
      gateway,
      llmGatewayLambda: supportLambdas.llmGatewayLambda,
      modelGatewayConfig,
      runtimeVersionConfig,
    });

    this.emitOutputs({
      datasetBucket,
      runtimeResources,
      runtimeVersionConfig,
      gateway,
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

  private runtimeVersionConfig(): RuntimeVersionConfig {
    const configuredValue = this.readTrimmed(
      "productionRuntimeVersion",
      "PRODUCTION_RUNTIME_VERSION",
      DEFAULT_PRODUCTION_RUNTIME_VERSION,
    );
    return {
      productionRuntimeVersion: this.resolveRuntimeVersion(configuredValue),
    };
  }

  private resolveRuntimeVersion(value: string): string {
    const parsed = value.trim() || DEFAULT_PRODUCTION_RUNTIME_VERSION;
    if (!/^[1-9]\d{0,4}$/.test(parsed)) {
      throw new Error(
        "productionRuntimeVersion/PRODUCTION_RUNTIME_VERSION must be an integer between 1 and 99999",
      );
    }
    return parsed;
  }

  private createSupportLambdas(
    logRetention: logs.RetentionDays,
    modelGatewayConfig: ModelGatewayEnvConfig,
  ): SupportLambdas {
    const llmGatewayLambda = this.createLambdaFunction(
      "LlmGatewayFn",
      "llm_gateway_stage.handler",
      logRetention,
      {
        BEDROCK_REGION: this.region,
        MODEL_ID: modelGatewayConfig.modelId,
        MODEL_PROVIDER: modelGatewayConfig.modelProvider,
        OPENAI_API_KEY_SECRET_ARN: modelGatewayConfig.openAiApiKeySecretArn,
        OPENAI_BASE_URL: modelGatewayConfig.openAiBaseUrl,
        OPENAI_REASONING_EFFORT: modelGatewayConfig.openAiReasoningEffort,
        OPENAI_TEXT_VERBOSITY: modelGatewayConfig.openAiTextVerbosity,
        OPENAI_MAX_OUTPUT_TOKENS: modelGatewayConfig.openAiMaxOutputTokens,
      },
    );
    this.grantGatewayModelProviderAccess(llmGatewayLambda);
    this.grantModelGatewaySecrets(
      llmGatewayLambda,
      modelGatewayConfig.openAiApiKeySecretArn,
    );

    const jiraToolLambda = this.createLambdaFunction(
      "JiraToolTargetFn",
      "jira_tool_target.handler",
      logRetention,
      {
        JIRA_BASE_URL: "https://jira.atlassian.com",
      },
    );
    return { llmGatewayLambda, jiraToolLambda };
  }

  private createLambdaFunction(
    name: string,
    handler: string,
    logRetention: logs.RetentionDays,
    environment: Record<string, string>,
  ): lambda.Function {
    const lambdaCodePath = path.join(__dirname, "../../aws/lambda");
    const lambdaLogGroup = new logs.LogGroup(this, `${name}LogGroup`, {
      retention: logRetention,
      removalPolicy: RemovalPolicy.RETAIN,
    });
    return new lambda.Function(this, name, {
      runtime: lambda.Runtime.PYTHON_3_12,
      architecture: lambda.Architecture.ARM_64,
      handler,
      code: lambda.Code.fromAsset(lambdaCodePath),
      timeout: Duration.minutes(2),
      memorySize: 512,
      environment,
      logGroup: lambdaLogGroup,
    });
  }

  private grantModelGatewaySecrets(
    llmGatewayLambda: lambda.Function,
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
    openAiApiKeySecret.grantRead(llmGatewayLambda);
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

  private createGateway(jiraToolLambda: lambda.Function): agentcore.Gateway {
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
    return gateway;
  }

  private runtimeArtifactExcludes(): string[] {
    return [
      ".coverage",
      ".DS_Store",
      ".git/**",
      ".github/**",
      ".vscode/**",
      ".venv/**",
      ".pytest_cache/**",
      ".mypy_cache/**",
      ".ruff_cache/**",
      ".tox/**",
      "contracts/**",
      "docs/**",
      "evals/**",
      "infra/**",
      "infra/cdk.out/**",
      "**/cdk.out/**",
      "**/.cache/**",
      "reports/**",
      "samples/**",
      "scripts/**",
      "tests/**",
      "runtime/sop_agent/tests/**",
      ".enaible/**",
      "node_modules/**",
      "**/__pycache__/**",
    ];
  }

  private runtimeBundlingCommand(): string {
    return [
      "set -euo pipefail",
      "mkdir -p /asset-output/aws /asset-output/runtime",
      "cp -R /asset-input/aws/. /asset-output/aws/",
      "cp -R /asset-input/runtime/. /asset-output/runtime/",
      "python -m pip install --no-cache-dir --disable-pip-version-check -r /asset-input/runtime/requirements-agentcore-runtime.txt -t /asset-output",
      "find /asset-output -type d -name '__pycache__' -prune -exec rm -rf {} +",
    ].join(" && ");
  }

  private createRuntimeArtifact(): agentcore.AgentRuntimeArtifact {
    return agentcore.AgentRuntimeArtifact.fromCodeAsset({
      path: path.join(__dirname, "../.."),
      exclude: this.runtimeArtifactExcludes(),
      bundling: {
        image: DockerImage.fromRegistry(
          "public.ecr.aws/docker/library/python:3.12",
        ),
        command: ["bash", "-lc", this.runtimeBundlingCommand()],
      },
      runtime: agentcore.AgentCoreRuntime.PYTHON_3_12,
      entrypoint: ["runtime/main.py"],
    });
  }

  private createRuntimeResources(
    inputs: RuntimeResourceInputs,
  ): RuntimeResources {
    const runtimeArtifact = this.createRuntimeArtifact();
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
        BEDROCK_REGION: this.region,
        MODEL_ID: inputs.modelGatewayConfig.modelId,
        MODEL_PROVIDER: inputs.modelGatewayConfig.modelProvider,
        OPENAI_REASONING_EFFORT:
          inputs.modelGatewayConfig.openAiReasoningEffort,
        OPENAI_TEXT_VERBOSITY: inputs.modelGatewayConfig.openAiTextVerbosity,
        OPENAI_MAX_OUTPUT_TOKENS:
          inputs.modelGatewayConfig.openAiMaxOutputTokens,
        MCP_GATEWAY_URL: inputs.gateway.gatewayUrl ?? "",
        LLM_GATEWAY_FUNCTION_NAME: inputs.llmGatewayLambda.functionName,
        RESULT_BUCKET: inputs.datasetBucket.bucketName,
        FAIL_ON_TOOL_FAILURE: "false",
      },
      authorizerConfiguration:
        agentcore.RuntimeAuthorizerConfiguration.usingIAM(),
      tags: { project: "flutter-agentcore-poc" },
    });

    inputs.datasetBucket.grantReadWrite(runtime);
    inputs.llmGatewayLambda.grantInvoke(runtime);
    inputs.gateway.grantInvoke(runtime);

    const runtimeEndpoint = runtime.addEndpoint("production", {
      version: inputs.runtimeVersionConfig.productionRuntimeVersion,
      description: "Stable endpoint for PoC orchestration runs",
    });
    return { runtime, runtimeEndpoint };
  }

  private emitOutputs(resources: StackOutputResources): void {
    new CfnOutput(this, "RuntimeArn", {
      value: resources.runtimeResources.runtime.agentRuntimeArn,
    });
    new CfnOutput(this, "RuntimeId", {
      value: resources.runtimeResources.runtime.agentRuntimeId,
    });
    new CfnOutput(this, "RuntimeVersion", {
      value: resources.runtimeResources.runtime.agentRuntimeVersion ?? "",
    });
    new CfnOutput(this, "RuntimeStatus", {
      value: resources.runtimeResources.runtime.agentStatus ?? "",
    });
    new CfnOutput(this, "RuntimeEndpointArn", {
      value: resources.runtimeResources.runtimeEndpoint.agentRuntimeEndpointArn,
    });
    new CfnOutput(this, "RuntimeEndpointConfiguredVersion", {
      value: resources.runtimeResources.runtimeEndpoint.agentRuntimeVersion,
    });
    new CfnOutput(this, "RuntimeEndpointLiveVersion", {
      value: resources.runtimeResources.runtimeEndpoint.liveVersion ?? "",
    });
    new CfnOutput(this, "RuntimeEndpointTargetVersion", {
      value: resources.runtimeResources.runtimeEndpoint.targetVersion ?? "",
    });
    new CfnOutput(this, "RuntimeEndpointStatus", {
      value: resources.runtimeResources.runtimeEndpoint.status ?? "",
    });
    new CfnOutput(this, "RuntimeEndpointConfiguredTargetVersion", {
      value: resources.runtimeVersionConfig.productionRuntimeVersion,
    });
    new CfnOutput(this, "GatewayId", { value: resources.gateway.gatewayId });
    new CfnOutput(this, "GatewayUrl", {
      value: resources.gateway.gatewayUrl ?? "",
    });
    new CfnOutput(this, "ArtifactsBucketName", {
      value: resources.datasetBucket.bucketName,
    });
  }
}
