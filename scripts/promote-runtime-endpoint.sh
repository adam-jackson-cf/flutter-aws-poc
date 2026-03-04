#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  scripts/promote-runtime-endpoint.sh [options]

Options:
  --runtime-id <value>              Runtime id (if omitted, resolved from stack output RuntimeId)
  --stack-name <value>              CloudFormation stack name (default: FlutterAgentCorePocStack)
  --endpoint-name <value>           Endpoint name to promote (default: production)
  --candidate-version <int>         Runtime version to promote (default: latest READY version)
  --candidate-eval-cmd <command>    Optional command to run against candidate before promote
  --region <value>                  AWS region (default: eu-west-1)
  --aws-profile <value>             AWS profile to use
  --wait-timeout-seconds <int>      Wait timeout for convergence (default: 900)
  --poll-interval-seconds <int>     Poll interval for endpoint status (default: 10)
  --help                            Show this help
USAGE
}

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Missing required command: $cmd" >&2
    exit 1
  fi
}

aws_cli() {
  if [[ -n "$AWS_PROFILE_NAME" ]]; then
    AWS_PROFILE="$AWS_PROFILE_NAME" AWS_REGION="$REGION" aws --region "$REGION" "$@"
    return
  fi
  AWS_REGION="$REGION" aws --region "$REGION" "$@"
}

resolve_runtime_id_from_stack() {
  aws_cli cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query 'Stacks[0].Outputs[?OutputKey==`RuntimeId`].OutputValue' \
    --output text
}

resolve_latest_ready_version() {
  local payload
  payload="$(
    aws_cli bedrock-agentcore-control list-agent-runtime-versions \
      --agent-runtime-id "$RUNTIME_ID" \
      --output json
  )"
  PAYLOAD="$payload" python3 - <<'PY'
import json
import os
import sys

payload = json.loads(os.environ["PAYLOAD"])
versions = payload.get("runtimeVersions", [])
ready = []
for entry in versions:
    if not isinstance(entry, dict):
        continue
    if str(entry.get("status", "")).strip() != "READY":
        continue
    candidate = str(entry.get("version", "")).strip()
    if candidate.isdigit() and int(candidate) > 0:
        ready.append(int(candidate))
if not ready:
    sys.exit(1)
print(max(ready))
PY
}

validate_positive_int() {
  local value="$1"
  local field_name="$2"
  if [[ ! "$value" =~ ^[1-9][0-9]*$ ]]; then
    echo "Invalid $field_name: $value" >&2
    exit 2
  fi
}

parse_endpoint_status() {
  local payload="$1"
  PAYLOAD="$payload" python3 - <<'PY'
import json
import os

payload = json.loads(os.environ["PAYLOAD"])
print(str(payload.get("status", "")).strip())
print(str(payload.get("liveVersion", "")).strip())
print(str(payload.get("targetVersion", "")).strip())
PY
}

STACK_NAME="FlutterAgentCorePocStack"
REGION="eu-west-1"
ENDPOINT_NAME="production"
RUNTIME_ID=""
CANDIDATE_VERSION=""
CANDIDATE_EVAL_CMD=""
AWS_PROFILE_NAME=""
WAIT_TIMEOUT_SECONDS="900"
POLL_INTERVAL_SECONDS="10"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --runtime-id)
      RUNTIME_ID="${2:-}"
      shift 2
      ;;
    --stack-name)
      STACK_NAME="${2:-}"
      shift 2
      ;;
    --endpoint-name)
      ENDPOINT_NAME="${2:-}"
      shift 2
      ;;
    --candidate-version)
      CANDIDATE_VERSION="${2:-}"
      shift 2
      ;;
    --candidate-eval-cmd)
      CANDIDATE_EVAL_CMD="${2:-}"
      shift 2
      ;;
    --region)
      REGION="${2:-}"
      shift 2
      ;;
    --aws-profile)
      AWS_PROFILE_NAME="${2:-}"
      shift 2
      ;;
    --wait-timeout-seconds)
      WAIT_TIMEOUT_SECONDS="${2:-}"
      shift 2
      ;;
    --poll-interval-seconds)
      POLL_INTERVAL_SECONDS="${2:-}"
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

require_cmd aws
require_cmd python3

validate_positive_int "$WAIT_TIMEOUT_SECONDS" "wait-timeout-seconds"
validate_positive_int "$POLL_INTERVAL_SECONDS" "poll-interval-seconds"

echo "Validating AWS identity..."
aws_cli sts get-caller-identity --query "Arn" --output text >/dev/null

if [[ -z "$RUNTIME_ID" ]]; then
  RUNTIME_ID="$(resolve_runtime_id_from_stack)"
fi
if [[ -z "$RUNTIME_ID" || "$RUNTIME_ID" == "None" ]]; then
  echo "RuntimeId not resolved. Pass --runtime-id or check stack output RuntimeId." >&2
  exit 1
fi

if [[ -n "$CANDIDATE_VERSION" ]]; then
  validate_positive_int "$CANDIDATE_VERSION" "candidate-version"
else
  CANDIDATE_VERSION="$(resolve_latest_ready_version || true)"
  if [[ -z "$CANDIDATE_VERSION" ]]; then
    echo "Could not resolve latest READY runtime version for runtime '$RUNTIME_ID'." >&2
    exit 1
  fi
fi

echo "RuntimeId: $RUNTIME_ID"
echo "EndpointName: $ENDPOINT_NAME"
echo "Region: $REGION"
echo "CandidateVersion: $CANDIDATE_VERSION"

if [[ -n "$CANDIDATE_EVAL_CMD" ]]; then
  echo "Running candidate eval command..."
  if ! AGENT_RUNTIME_QUALIFIER="$CANDIDATE_VERSION" \
    AWS_REGION="$REGION" \
    BEDROCK_REGION="$REGION" \
    PROMOTION_RUNTIME_ID="$RUNTIME_ID" \
    PROMOTION_REGION="$REGION" \
    PROMOTION_ENDPOINT_NAME="$ENDPOINT_NAME" \
    PROMOTION_TARGET_VERSION="$CANDIDATE_VERSION" \
    /bin/bash -lc "$CANDIDATE_EVAL_CMD"; then
    echo "Candidate eval hook failed; aborting promotion." >&2
    exit 1
  fi
fi

echo "Updating endpoint target version..."
aws_cli bedrock-agentcore-control update-agent-runtime-endpoint \
  --agent-runtime-id "$RUNTIME_ID" \
  --endpoint-name "$ENDPOINT_NAME" \
  --target-version "$CANDIDATE_VERSION" \
  --output json >/dev/null

deadline_epoch=$((SECONDS + WAIT_TIMEOUT_SECONDS))
while true; do
  endpoint_payload="$(
    aws_cli bedrock-agentcore-control get-agent-runtime-endpoint \
      --agent-runtime-id "$RUNTIME_ID" \
      --endpoint-name "$ENDPOINT_NAME" \
      --output json
  )"
  mapfile -t endpoint_status < <(parse_endpoint_status "$endpoint_payload")
  status="${endpoint_status[0]:-}"
  live_version="${endpoint_status[1]:-}"
  target_version="${endpoint_status[2]:-}"

  echo "EndpointStatus=$status LiveVersion=$live_version TargetVersion=$target_version"

  if [[ "$status" == "READY" && "$live_version" == "$CANDIDATE_VERSION" ]]; then
    echo "Promotion complete."
    exit 0
  fi

  if [[ "$status" == "FAILED" ]]; then
    echo "Promotion failed: endpoint status is FAILED." >&2
    exit 1
  fi

  if (( SECONDS >= deadline_epoch )); then
    echo "Timed out waiting for endpoint promotion convergence." >&2
    exit 1
  fi

  sleep "$POLL_INTERVAL_SECONDS"
done
