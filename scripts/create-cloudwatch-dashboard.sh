#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  scripts/create-cloudwatch-dashboard.sh --run-id <RUN_ID> [options]

Options:
  --run-id <value>          Required. Eval run id used in CloudWatch metric dimension RunId.
  --dashboard-name <value>  Dashboard name. Default: FlutterAgentCorePoc-Eval-<RUN_ID>
  --namespace <value>       Metrics namespace. Default: FlutterAgentCorePoc/Evals
  --dataset <value>         Dataset dimension value. Default: evals/golden/sop_cases.jsonl
  --scope <value>           Scope dimension value. Default: route
  --execution-mode <value>  ExecutionMode dimension. Default: route_parity
  --mcp-binding-mode <val>  McpBindingMode dimension. Default: model_constructed_schema_validated
  --llm-route-path <value>  LlmRoutePath dimension. Default: gateway_service
  --route-semantics-version <value> RouteSemanticsVersion dimension. Default: 2
  --region <value>          AWS region. Default: AWS_REGION or eu-west-1
  --profile <value>         AWS named profile. Default: AWS_PROFILE
  --help                    Show this help.
USAGE
}

RUN_ID=""
DASHBOARD_NAME=""
NAMESPACE="FlutterAgentCorePoc/Evals"
DATASET="evals/golden/sop_cases.jsonl"
SCOPE="route"
EXECUTION_MODE="route_parity"
MCP_BINDING_MODE="model_constructed_schema_validated"
LLM_ROUTE_PATH="gateway_service"
ROUTE_SEMANTICS_VERSION="2"
REGION="${AWS_REGION:-eu-west-1}"
PROFILE="${AWS_PROFILE:-}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-id)
      RUN_ID="${2:-}"
      shift 2
      ;;
    --dashboard-name)
      DASHBOARD_NAME="${2:-}"
      shift 2
      ;;
    --namespace)
      NAMESPACE="${2:-}"
      shift 2
      ;;
    --dataset)
      DATASET="${2:-}"
      shift 2
      ;;
    --scope)
      SCOPE="${2:-}"
      shift 2
      ;;
    --execution-mode)
      EXECUTION_MODE="${2:-}"
      shift 2
      ;;
    --mcp-binding-mode)
      MCP_BINDING_MODE="${2:-}"
      shift 2
      ;;
    --llm-route-path)
      LLM_ROUTE_PATH="${2:-}"
      shift 2
      ;;
    --route-semantics-version)
      ROUTE_SEMANTICS_VERSION="${2:-}"
      shift 2
      ;;
    --region)
      REGION="${2:-}"
      shift 2
      ;;
    --profile)
      PROFILE="${2:-}"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ -z "$RUN_ID" ]]; then
  echo "Error: --run-id is required." >&2
  usage
  exit 2
fi

if [[ -z "$DASHBOARD_NAME" ]]; then
  DASHBOARD_NAME="FlutterAgentCorePoc-Eval-${RUN_ID}"
fi

AWS_ARGS=(--region "$REGION")
if [[ -n "$PROFILE" ]]; then
  AWS_ARGS+=(--profile "$PROFILE")
fi

COMMON_ROUTE_DIMS="\"ExecutionMode\", \"$EXECUTION_MODE\", \"McpBindingMode\", \"$MCP_BINDING_MODE\", \"LlmRoutePath\", \"$LLM_ROUTE_PATH\", \"RouteSemanticsVersion\", \"$ROUTE_SEMANTICS_VERSION\""

echo "==> AWS identity preflight"
aws "${AWS_ARGS[@]}" sts get-caller-identity --query '{Account:Account,Arn:Arn}' --output table

BODY_FILE="$(mktemp -t cw-dashboard-body.XXXXXX.json)"
trap 'rm -f "$BODY_FILE"' EXIT

cat >"$BODY_FILE" <<EOF
{
  "widgets": [
    {
      "type": "text",
      "x": 0,
      "y": 0,
      "width": 24,
      "height": 3,
      "properties": {
        "markdown": "# Flutter AgentCore Eval Dashboard\\nRunId: \`$RUN_ID\` | Scope: \`$SCOPE\` | Dataset: \`$DATASET\`\\nExecutionMode: \`$EXECUTION_MODE\` | MCP Binding: \`$MCP_BINDING_MODE\` | LLM Route: \`$LLM_ROUTE_PATH\` | Route Semantics: \`$ROUTE_SEMANTICS_VERSION\`\\nDeterministic metrics are release truth. Judge/composite metrics are diagnostics. DSPy route adds objective-slice dual scoring."
      }
    },
    {
      "type": "metric",
      "x": 0,
      "y": 3,
      "width": 12,
      "height": 6,
      "properties": {
        "title": "Reliability (Native vs MCP)",
        "view": "timeSeries",
        "stacked": false,
        "region": "$REGION",
        "stat": "Average",
        "period": 300,
        "yAxis": {
          "left": { "min": 0, "max": 1 }
        },
        "metrics": [
          [ "$NAMESPACE", "ToolFailureRate", "RunId", "$RUN_ID", "Flow", "native", "Scope", "$SCOPE", "Dataset", "$DATASET", $COMMON_ROUTE_DIMS, { "label": "Native Tool Failure Rate" } ],
          [ "$NAMESPACE", "ToolFailureRate", "RunId", "$RUN_ID", "Flow", "mcp", "Scope", "$SCOPE", "Dataset", "$DATASET", $COMMON_ROUTE_DIMS, { "label": "MCP Tool Failure Rate" } ],
          [ "$NAMESPACE", "BusinessSuccessRate", "RunId", "$RUN_ID", "Flow", "native", "Scope", "$SCOPE", "Dataset", "$DATASET", $COMMON_ROUTE_DIMS, { "label": "Native Business Success" } ],
          [ "$NAMESPACE", "BusinessSuccessRate", "RunId", "$RUN_ID", "Flow", "mcp", "Scope", "$SCOPE", "Dataset", "$DATASET", $COMMON_ROUTE_DIMS, { "label": "MCP Business Success" } ],
          [ "$NAMESPACE", "ToolMatchRate", "RunId", "$RUN_ID", "Flow", "native", "Scope", "$SCOPE", "Dataset", "$DATASET", $COMMON_ROUTE_DIMS, { "label": "Native Tool Match" } ],
          [ "$NAMESPACE", "ToolMatchRate", "RunId", "$RUN_ID", "Flow", "mcp", "Scope", "$SCOPE", "Dataset", "$DATASET", $COMMON_ROUTE_DIMS, { "label": "MCP Tool Match" } ]
        ]
      }
    },
    {
      "type": "metric",
      "x": 12,
      "y": 3,
      "width": 12,
      "height": 6,
      "properties": {
        "title": "Latency (Native vs MCP)",
        "view": "timeSeries",
        "stacked": false,
        "region": "$REGION",
        "stat": "Average",
        "period": 300,
        "metrics": [
          [ "$NAMESPACE", "MeanLatencyMs", "RunId", "$RUN_ID", "Flow", "native", "Scope", "$SCOPE", "Dataset", "$DATASET", $COMMON_ROUTE_DIMS, { "label": "Native Mean Latency (ms)" } ],
          [ "$NAMESPACE", "MeanLatencyMs", "RunId", "$RUN_ID", "Flow", "mcp", "Scope", "$SCOPE", "Dataset", "$DATASET", $COMMON_ROUTE_DIMS, { "label": "MCP Mean Latency (ms)" } ],
          [ "$NAMESPACE", "MeanLatencySuccessMs", "RunId", "$RUN_ID", "Flow", "native", "Scope", "$SCOPE", "Dataset", "$DATASET", $COMMON_ROUTE_DIMS, { "label": "Native Success Latency (ms)" } ],
          [ "$NAMESPACE", "MeanLatencySuccessMs", "RunId", "$RUN_ID", "Flow", "mcp", "Scope", "$SCOPE", "Dataset", "$DATASET", $COMMON_ROUTE_DIMS, { "label": "MCP Success Latency (ms)" } ]
        ]
      }
    },
    {
      "type": "metric",
      "x": 0,
      "y": 9,
      "width": 12,
      "height": 6,
      "properties": {
        "title": "Judge Diagnostics (Native vs MCP)",
        "view": "timeSeries",
        "stacked": false,
        "region": "$REGION",
        "stat": "Average",
        "period": 300,
        "yAxis": {
          "left": { "min": 0, "max": 1 }
        },
        "metrics": [
          [ "$NAMESPACE", "JudgeMeanOverallScore", "RunId", "$RUN_ID", "Flow", "native", "Scope", "$SCOPE", "Dataset", "$DATASET", $COMMON_ROUTE_DIMS, { "label": "Native Judge Mean Overall" } ],
          [ "$NAMESPACE", "JudgeMeanOverallScore", "RunId", "$RUN_ID", "Flow", "mcp", "Scope", "$SCOPE", "Dataset", "$DATASET", $COMMON_ROUTE_DIMS, { "label": "MCP Judge Mean Overall" } ],
          [ "$NAMESPACE", "JudgePassRate", "RunId", "$RUN_ID", "Flow", "native", "Scope", "$SCOPE", "Dataset", "$DATASET", $COMMON_ROUTE_DIMS, { "label": "Native Judge Pass Rate" } ],
          [ "$NAMESPACE", "JudgePassRate", "RunId", "$RUN_ID", "Flow", "mcp", "Scope", "$SCOPE", "Dataset", "$DATASET", $COMMON_ROUTE_DIMS, { "label": "MCP Judge Pass Rate" } ]
        ]
      }
    },
    {
      "type": "metric",
      "x": 12,
      "y": 9,
      "width": 12,
      "height": 6,
      "properties": {
        "title": "Composite Reflection + Gate (Native vs MCP)",
        "view": "timeSeries",
        "stacked": false,
        "region": "$REGION",
        "stat": "Average",
        "period": 300,
        "yAxis": {
          "left": { "min": 0, "max": 1 }
        },
        "metrics": [
          [ "$NAMESPACE", "DeterministicReleaseScore", "RunId", "$RUN_ID", "Flow", "native", "Scope", "$SCOPE", "Dataset", "$DATASET", $COMMON_ROUTE_DIMS, { "label": "Native Deterministic Score" } ],
          [ "$NAMESPACE", "DeterministicReleaseScore", "RunId", "$RUN_ID", "Flow", "mcp", "Scope", "$SCOPE", "Dataset", "$DATASET", $COMMON_ROUTE_DIMS, { "label": "MCP Deterministic Score" } ],
          [ "$NAMESPACE", "OverallReflectionScore", "RunId", "$RUN_ID", "Flow", "native", "Scope", "$SCOPE", "Dataset", "$DATASET", $COMMON_ROUTE_DIMS, { "label": "Native Reflection Score" } ],
          [ "$NAMESPACE", "OverallReflectionScore", "RunId", "$RUN_ID", "Flow", "mcp", "Scope", "$SCOPE", "Dataset", "$DATASET", $COMMON_ROUTE_DIMS, { "label": "MCP Reflection Score" } ],
          [ "$NAMESPACE", "DivergenceFlag", "RunId", "$RUN_ID", "Flow", "native", "Scope", "$SCOPE", "Dataset", "$DATASET", $COMMON_ROUTE_DIMS, { "label": "Native Divergence Flag" } ],
          [ "$NAMESPACE", "DivergenceFlag", "RunId", "$RUN_ID", "Flow", "mcp", "Scope", "$SCOPE", "Dataset", "$DATASET", $COMMON_ROUTE_DIMS, { "label": "MCP Divergence Flag" } ],
          [ "$NAMESPACE", "ReleaseGatePass", "RunId", "$RUN_ID", "Flow", "native", "Scope", "$SCOPE", "Dataset", "$DATASET", $COMMON_ROUTE_DIMS, { "label": "Native Release Gate Pass" } ],
          [ "$NAMESPACE", "ReleaseGatePass", "RunId", "$RUN_ID", "Flow", "mcp", "Scope", "$SCOPE", "Dataset", "$DATASET", $COMMON_ROUTE_DIMS, { "label": "MCP Release Gate Pass" } ]
        ]
      }
    },
    {
      "type": "metric",
      "x": 0,
      "y": 15,
      "width": 24,
      "height": 6,
      "properties": {
        "title": "Estimated Cost (Native vs MCP, USD)",
        "view": "timeSeries",
        "stacked": false,
        "region": "$REGION",
        "stat": "Average",
        "period": 300,
        "metrics": [
          [ "$NAMESPACE", "MeanEstimatedCostUsd", "RunId", "$RUN_ID", "Flow", "native", "Scope", "$SCOPE", "Dataset", "$DATASET", $COMMON_ROUTE_DIMS, { "id": "n_mean_cost", "label": "Native Mean Cost (USD)" } ],
          [ "$NAMESPACE", "MeanEstimatedCostUsd", "RunId", "$RUN_ID", "Flow", "mcp", "Scope", "$SCOPE", "Dataset", "$DATASET", $COMMON_ROUTE_DIMS, { "id": "m_mean_cost", "label": "MCP Mean Cost (USD)" } ],
          [ { "expression": "m_mean_cost-n_mean_cost", "label": "Mean Cost Delta MCP-Native (USD)", "id": "mean_cost_delta" } ],
          [ "$NAMESPACE", "TotalEstimatedCostUsd", "RunId", "$RUN_ID", "Flow", "native", "Scope", "$SCOPE", "Dataset", "$DATASET", $COMMON_ROUTE_DIMS, { "id": "n_total_cost", "label": "Native Total Cost (USD)" } ],
          [ "$NAMESPACE", "TotalEstimatedCostUsd", "RunId", "$RUN_ID", "Flow", "mcp", "Scope", "$SCOPE", "Dataset", "$DATASET", $COMMON_ROUTE_DIMS, { "id": "m_total_cost", "label": "MCP Total Cost (USD)" } ],
          [ { "expression": "m_total_cost-n_total_cost", "label": "Total Cost Delta MCP-Native (USD)", "id": "total_cost_delta" } ]
        ]
      }
    },
    {
      "type": "metric",
      "x": 0,
      "y": 21,
      "width": 12,
      "height": 6,
      "properties": {
        "title": "DSPy Dual Scores",
        "view": "timeSeries",
        "stacked": false,
        "region": "$REGION",
        "stat": "Average",
        "period": 300,
        "yAxis": {
          "left": { "min": 0, "max": 1 }
        },
        "metrics": [
          [ "$NAMESPACE", "AgentQualityScore", "RunId", "$RUN_ID", "Flow", "dspy_opt", "Scope", "$SCOPE", "Dataset", "$DATASET", $COMMON_ROUTE_DIMS, "ObjectiveSlice", "all", { "label": "Agent Quality Score" } ],
          [ "$NAMESPACE", "McpFailureCostScore", "RunId", "$RUN_ID", "Flow", "dspy_opt", "Scope", "$SCOPE", "Dataset", "$DATASET", $COMMON_ROUTE_DIMS, "ObjectiveSlice", "all", { "label": "MCP Failure Cost Score" } ]
        ]
      }
    },
    {
      "type": "metric",
      "x": 12,
      "y": 21,
      "width": 12,
      "height": 6,
      "properties": {
        "title": "DSPy Objective Slices",
        "view": "timeSeries",
        "stacked": false,
        "region": "$REGION",
        "stat": "Average",
        "period": 300,
        "yAxis": {
          "left": { "min": 0, "max": 1 }
        },
        "metrics": [
          [ "$NAMESPACE", "SliceBusinessSuccessRate", "RunId", "$RUN_ID", "Flow", "dspy_opt", "Scope", "$SCOPE", "Dataset", "$DATASET", $COMMON_ROUTE_DIMS, "ObjectiveSlice", "optimization", { "label": "Optimization Business Success" } ],
          [ "$NAMESPACE", "SliceToolFailureRate", "RunId", "$RUN_ID", "Flow", "dspy_opt", "Scope", "$SCOPE", "Dataset", "$DATASET", $COMMON_ROUTE_DIMS, "ObjectiveSlice", "stress", { "label": "Stress Tool Failure Rate" } ],
          [ "$NAMESPACE", "SliceMeanEstimatedCostUsd", "RunId", "$RUN_ID", "Flow", "dspy_opt", "Scope", "$SCOPE", "Dataset", "$DATASET", $COMMON_ROUTE_DIMS, "ObjectiveSlice", "stress", { "label": "Stress Mean Cost (USD)" } ],
          [ "$NAMESPACE", "SliceMeanLlmTotalTokens", "RunId", "$RUN_ID", "Flow", "dspy_opt", "Scope", "$SCOPE", "Dataset", "$DATASET", $COMMON_ROUTE_DIMS, "ObjectiveSlice", "stress", { "label": "Stress Mean Tokens" } ]
        ]
      }
    }
  ]
}
EOF

echo "==> Creating/updating dashboard: $DASHBOARD_NAME"
MESSAGES="$(aws "${AWS_ARGS[@]}" cloudwatch put-dashboard \
  --dashboard-name "$DASHBOARD_NAME" \
  --dashboard-body "file://$BODY_FILE" \
  --query 'DashboardValidationMessages[*].Message' \
  --output text)"

if [[ -n "$MESSAGES" && "$MESSAGES" != "None" ]]; then
  echo "Dashboard validation warnings/errors: $MESSAGES" >&2
  exit 1
fi

echo "Dashboard updated successfully."
echo "Console URL:"
echo "https://${REGION}.console.aws.amazon.com/cloudwatch/home?region=${REGION}#dashboards:name=${DASHBOARD_NAME}"
