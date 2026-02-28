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
        "markdown": "# Flutter AgentCore Eval Dashboard\\nRunId: \`$RUN_ID\` | Scope: \`$SCOPE\` | Dataset: \`$DATASET\`\\nDeterministic metrics are release truth. Judge/composite metrics are diagnostics."
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
          [ "$NAMESPACE", "ToolFailureRate", "RunId", "$RUN_ID", "Flow", "native", "Scope", "$SCOPE", "Dataset", "$DATASET", { "label": "Native Tool Failure Rate" } ],
          [ "$NAMESPACE", "ToolFailureRate", "RunId", "$RUN_ID", "Flow", "mcp", "Scope", "$SCOPE", "Dataset", "$DATASET", { "label": "MCP Tool Failure Rate" } ],
          [ "$NAMESPACE", "BusinessSuccessRate", "RunId", "$RUN_ID", "Flow", "native", "Scope", "$SCOPE", "Dataset", "$DATASET", { "label": "Native Business Success" } ],
          [ "$NAMESPACE", "BusinessSuccessRate", "RunId", "$RUN_ID", "Flow", "mcp", "Scope", "$SCOPE", "Dataset", "$DATASET", { "label": "MCP Business Success" } ],
          [ "$NAMESPACE", "ToolMatchRate", "RunId", "$RUN_ID", "Flow", "native", "Scope", "$SCOPE", "Dataset", "$DATASET", { "label": "Native Tool Match" } ],
          [ "$NAMESPACE", "ToolMatchRate", "RunId", "$RUN_ID", "Flow", "mcp", "Scope", "$SCOPE", "Dataset", "$DATASET", { "label": "MCP Tool Match" } ]
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
          [ "$NAMESPACE", "MeanLatencyMs", "RunId", "$RUN_ID", "Flow", "native", "Scope", "$SCOPE", "Dataset", "$DATASET", { "label": "Native Mean Latency (ms)" } ],
          [ "$NAMESPACE", "MeanLatencyMs", "RunId", "$RUN_ID", "Flow", "mcp", "Scope", "$SCOPE", "Dataset", "$DATASET", { "label": "MCP Mean Latency (ms)" } ],
          [ "$NAMESPACE", "MeanLatencySuccessMs", "RunId", "$RUN_ID", "Flow", "native", "Scope", "$SCOPE", "Dataset", "$DATASET", { "label": "Native Success Latency (ms)" } ],
          [ "$NAMESPACE", "MeanLatencySuccessMs", "RunId", "$RUN_ID", "Flow", "mcp", "Scope", "$SCOPE", "Dataset", "$DATASET", { "label": "MCP Success Latency (ms)" } ]
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
          [ "$NAMESPACE", "JudgeMeanOverallScore", "RunId", "$RUN_ID", "Flow", "native", "Scope", "$SCOPE", "Dataset", "$DATASET", { "label": "Native Judge Mean Overall" } ],
          [ "$NAMESPACE", "JudgeMeanOverallScore", "RunId", "$RUN_ID", "Flow", "mcp", "Scope", "$SCOPE", "Dataset", "$DATASET", { "label": "MCP Judge Mean Overall" } ],
          [ "$NAMESPACE", "JudgePassRate", "RunId", "$RUN_ID", "Flow", "native", "Scope", "$SCOPE", "Dataset", "$DATASET", { "label": "Native Judge Pass Rate" } ],
          [ "$NAMESPACE", "JudgePassRate", "RunId", "$RUN_ID", "Flow", "mcp", "Scope", "$SCOPE", "Dataset", "$DATASET", { "label": "MCP Judge Pass Rate" } ]
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
          [ "$NAMESPACE", "DeterministicReleaseScore", "RunId", "$RUN_ID", "Flow", "native", "Scope", "$SCOPE", "Dataset", "$DATASET", { "label": "Native Deterministic Score" } ],
          [ "$NAMESPACE", "DeterministicReleaseScore", "RunId", "$RUN_ID", "Flow", "mcp", "Scope", "$SCOPE", "Dataset", "$DATASET", { "label": "MCP Deterministic Score" } ],
          [ "$NAMESPACE", "OverallReflectionScore", "RunId", "$RUN_ID", "Flow", "native", "Scope", "$SCOPE", "Dataset", "$DATASET", { "label": "Native Reflection Score" } ],
          [ "$NAMESPACE", "OverallReflectionScore", "RunId", "$RUN_ID", "Flow", "mcp", "Scope", "$SCOPE", "Dataset", "$DATASET", { "label": "MCP Reflection Score" } ],
          [ "$NAMESPACE", "DivergenceFlag", "RunId", "$RUN_ID", "Flow", "native", "Scope", "$SCOPE", "Dataset", "$DATASET", { "label": "Native Divergence Flag" } ],
          [ "$NAMESPACE", "DivergenceFlag", "RunId", "$RUN_ID", "Flow", "mcp", "Scope", "$SCOPE", "Dataset", "$DATASET", { "label": "MCP Divergence Flag" } ],
          [ "$NAMESPACE", "ReleaseGatePass", "RunId", "$RUN_ID", "Flow", "native", "Scope", "$SCOPE", "Dataset", "$DATASET", { "label": "Native Release Gate Pass" } ],
          [ "$NAMESPACE", "ReleaseGatePass", "RunId", "$RUN_ID", "Flow", "mcp", "Scope", "$SCOPE", "Dataset", "$DATASET", { "label": "MCP Release Gate Pass" } ]
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
