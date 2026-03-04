#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  scripts/run-smoke-euw1.sh [options]

Options:
  --run-id <value>              Optional run id. Default: nova-smoke-euw1-<utc timestamp>
  --dataset <path>              Default: evals/golden/sop_cases_adversarial.jsonl
  --iterations <int>            Default: 1
  --scope <route|full>          Default: route
  --model-id <value>            Default: eu.amazon.nova-lite-v1:0
  --model-provider <value>      Default: bedrock
  --agent-runtime-qualifier <v> Default: production
  --cloudwatch-namespace <val>  Default: FlutterAgentCorePoc/Evals
  --publish-cloudwatch          Publish summary metrics to CloudWatch
  --update-dashboard            Rebuild CloudWatch dashboard for this run id
  --dashboard-name <value>      Optional dashboard name override
  --skip-deploy                 Skip CDK deploy and run smoke only
  --help                        Show this help

Scope note:
  This PoC intentionally stays in route scope for DSPy optimization and
  MCP-vs-native comparison, and does not implement full Flutter R2/R3
  workflow-contract/HITL process-scope semantics.
USAGE
}

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Missing required command: $cmd" >&2
    exit 1
  fi
}

RUN_ID=""
DATASET="evals/golden/sop_cases_adversarial.jsonl"
ITERATIONS="1"
SCOPE="route"
MODEL_ID="eu.amazon.nova-lite-v1:0"
MODEL_PROVIDER="bedrock"
AGENT_RUNTIME_QUALIFIER="production"
CLOUDWATCH_NAMESPACE="FlutterAgentCorePoc/Evals"
PUBLISH_CLOUDWATCH="false"
UPDATE_DASHBOARD="false"
DASHBOARD_NAME=""
SKIP_DEPLOY="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-id)
      RUN_ID="${2:-}"
      shift 2
      ;;
    --dataset)
      DATASET="${2:-}"
      shift 2
      ;;
    --iterations)
      ITERATIONS="${2:-}"
      shift 2
      ;;
    --scope)
      SCOPE="${2:-}"
      shift 2
      ;;
    --model-id)
      MODEL_ID="${2:-}"
      shift 2
      ;;
    --model-provider)
      MODEL_PROVIDER="${2:-}"
      shift 2
      ;;
    --agent-runtime-qualifier)
      AGENT_RUNTIME_QUALIFIER="${2:-}"
      shift 2
      ;;
    --cloudwatch-namespace)
      CLOUDWATCH_NAMESPACE="${2:-}"
      shift 2
      ;;
    --publish-cloudwatch)
      PUBLISH_CLOUDWATCH="true"
      shift
      ;;
    --update-dashboard)
      UPDATE_DASHBOARD="true"
      shift
      ;;
    --dashboard-name)
      DASHBOARD_NAME="${2:-}"
      shift 2
      ;;
    --skip-deploy)
      SKIP_DEPLOY="true"
      shift
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
  RUN_ID="nova-smoke-euw1-$(date -u +%Y%m%dT%H%M%SZ)"
fi

if [[ "$SCOPE" != "route" && "$SCOPE" != "full" ]]; then
  echo "Invalid --scope value: $SCOPE" >&2
  exit 2
fi

if [[ ! -f "$DATASET" ]]; then
  echo "Dataset file not found: $DATASET" >&2
  exit 1
fi

if [[ "$ITERATIONS" =~ [^0-9] || "$ITERATIONS" -lt 1 ]]; then
  echo "Invalid --iterations value: $ITERATIONS" >&2
  exit 2
fi

if [[ "$MODEL_PROVIDER" != "auto" && "$MODEL_PROVIDER" != "bedrock" && "$MODEL_PROVIDER" != "openai" ]]; then
  echo "Invalid --model-provider value: $MODEL_PROVIDER" >&2
  exit 2
fi

require_cmd aws
require_cmd npm
require_cmd uv

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STACK_NAME="FlutterAgentCorePocStack"
REGION="eu-west-1"

echo "==> Region preflight"
echo "Pinned region: $REGION"

echo "==> AWS identity preflight"
aws --region "$REGION" sts get-caller-identity --query '{Account:Account,Arn:Arn}' --output table

if [[ "$SKIP_DEPLOY" == "false" ]]; then
  echo "==> CDK deploy ($STACK_NAME, $REGION)"
  (
    cd "$ROOT_DIR/infra"
    AWS_REGION="$REGION" BEDROCK_REGION="$REGION" CDK_DEFAULT_REGION="$REGION" \
      npx cdk deploy "$STACK_NAME" --require-approval never --context defaultRegion="$REGION"
  )
else
  echo "==> Skipping deploy (--skip-deploy)"
fi

echo "==> Resolve runtime ARN from stack outputs"
AGENT_RUNTIME_ARN="$(
  aws --region "$REGION" cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query 'Stacks[0].Outputs[?OutputKey==`RuntimeArn`].OutputValue' \
    --output text
)"

if [[ -z "$AGENT_RUNTIME_ARN" || "$AGENT_RUNTIME_ARN" == "None" ]]; then
  echo "Could not resolve RuntimeArn from stack outputs." >&2
  exit 1
fi

echo "==> Run smoke eval"
echo "Using live eval logging (PYTHONUNBUFFERED=1)"
EVAL_CMD=(
  uv run evals/run_eval.py
  --dataset "$DATASET"
  --flow both
  --iterations "$ITERATIONS"
  --scope "$SCOPE"
  --aws-region "$REGION"
  --bedrock-region "$REGION"
  --agent-runtime-arn "$AGENT_RUNTIME_ARN"
  --agent-runtime-qualifier "$AGENT_RUNTIME_QUALIFIER"
  --model-id "$MODEL_ID"
  --model-provider "$MODEL_PROVIDER"
  --run-id "$RUN_ID"
)

if [[ "$PUBLISH_CLOUDWATCH" == "true" ]]; then
  EVAL_CMD+=(--publish-cloudwatch --cloudwatch-namespace "$CLOUDWATCH_NAMESPACE")
fi

(
  cd "$ROOT_DIR"
  PYTHONUNBUFFERED=1 "${EVAL_CMD[@]}"
)

EVAL_PATH="$ROOT_DIR/reports/runs/$RUN_ID/eval/eval-both-route.json"

if [[ "$UPDATE_DASHBOARD" == "true" ]]; then
  echo "==> Update CloudWatch dashboard"
  DASH_CMD=(
    "$ROOT_DIR/scripts/create-cloudwatch-dashboard.sh"
    --run-id "$RUN_ID"
    --namespace "$CLOUDWATCH_NAMESPACE"
    --dataset "$DATASET"
    --scope "$SCOPE"
    --region "$REGION"
  )
  if [[ -n "$DASHBOARD_NAME" ]]; then
    DASH_CMD+=(--dashboard-name "$DASHBOARD_NAME")
  fi
  "${DASH_CMD[@]}"
fi

echo "Smoke run complete."
echo "RUN_ID=$RUN_ID"
echo "EVAL_PATH=$EVAL_PATH"
