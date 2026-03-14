#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
source "$REPO_ROOT/scripts/lib/python.sh"

usage() {
  cat <<'USAGE'
Usage:
  scripts/deploy/bootstrap-shared-sandbox.sh [options]

Options:
  --deployment-environment <sandbox|preprod|prod>      Default: sandbox
  --stack-name <name>                                   Default: FlutterAgentCorePocStack
  --runtime-bootstrap-stack-name <name>                 Default: <stack-name>-RuntimeBootstrap
  --region <value>                                      Default: eu-west-1
  --runtime-name <name>                                 Default: flutter_shared_platform_<deployment-environment>
  --runtime-id <id>                                     Use existing AgentCore runtime id
  --endpoint-name <name>                                Default: <deployment-environment>
  --expected-runtime-version <int>                      Enforce endpoint target runtime version
  --target-scope <account|org>                          Default: account
  --target-id <id>                                      Default: caller account id
  --guard-mode <detect|enforce>                         Default: enforce
  --wait-timeout-seconds <int>                          Default: 900
  --poll-interval-seconds <int>                         Default: 10

Runtime creation inputs (required only when runtime does not already exist):
  --runtime-role-arn <arn>
  --runtime-artifact-mode <code|container>              Default: code
  --runtime-code-s3-bucket <bucket>                     Auto-provisioned from IaC when omitted in code mode
  --runtime-code-s3-prefix <prefix>                     Default: agentcore/<deployment-environment>/shared-runtime.zip
  --runtime-code-s3-version-id <version-id>             Optional when artifact mode is code
  --runtime-code-entrypoint <csv>                       Default: runtime/agentcore_main.py
  --runtime-code-python-version <runtime>               Default: PYTHON_3_12
  --runtime-container-uri <uri>                         Required when artifact mode is container

Optional:
  --aws-profile <profile>                               Overrides AWS_PROFILE
  --guard-script-path <path>                            Default: scripts/guards/apply-flutter-design-aws-guards.sh
  --help
USAGE
}

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Missing required command: $cmd" >&2
    exit 2
  fi
}

validate_positive_int() {
  local value="$1"
  local field_name="$2"
  if [[ ! "$value" =~ ^[1-9][0-9]*$ ]]; then
    echo "Invalid $field_name: $value" >&2
    exit 2
  fi
}

validate_account_id() {
  local value="$1"
  local field_name="$2"
  if [[ ! "$value" =~ ^[0-9]{12}$ ]]; then
    echo "Invalid $field_name: $value" >&2
    exit 2
  fi
}

parse_runtime_payload() {
  local payload="$1"
  PAYLOAD="$payload" "$PYTHON_BIN" - <<'PY'
import json
import os

payload = json.loads(os.environ["PAYLOAD"])
print(
    "|".join(
        [
            str(payload.get("agentRuntimeId", "")).strip(),
            str(payload.get("agentRuntimeArn", "")).strip(),
            str(payload.get("agentRuntimeVersion", "")).strip(),
            str(payload.get("status", "")).strip(),
            str(payload.get("agentRuntimeName", "")).strip(),
        ]
    )
)
PY
}

parse_endpoint_payload() {
  local payload="$1"
  PAYLOAD="$payload" "$PYTHON_BIN" - <<'PY'
import json
import os

payload = json.loads(os.environ["PAYLOAD"])
live_version = str(payload.get("liveVersion", "")).strip()
target_version = str(payload.get("targetVersion", "")).strip() or live_version
print(
    "|".join(
        [
            str(payload.get("status", "")).strip(),
            live_version,
            target_version,
            str(payload.get("agentRuntimeEndpointArn", "")).strip(),
        ]
    )
)
PY
}

wait_for_runtime_ready() {
  local runtime_id="$1"
  local timeout_seconds="$2"
  local poll_interval="$3"
  local started_at
  started_at="$(date +%s)"

  while true; do
    local runtime_payload
    runtime_payload="$(aws_cli bedrock-agentcore-control get-agent-runtime --agent-runtime-id "$runtime_id" --output json)"
    local runtime_values
    runtime_values="$(parse_runtime_payload "$runtime_payload")"
    local status
    IFS='|' read -r _ _ _ status _ <<< "$runtime_values"

    if [[ "$status" == "READY" ]]; then
      printf '%s\n' "$runtime_payload"
      return 0
    fi
    if [[ "$status" == "CREATE_FAILED" || "$status" == "UPDATE_FAILED" ]]; then
      echo "Runtime '$runtime_id' entered terminal status '$status'." >&2
      return 1
    fi

    local now
    now="$(date +%s)"
    if (( now - started_at >= timeout_seconds )); then
      echo "Timed out waiting for runtime '$runtime_id' to reach READY." >&2
      return 1
    fi

    sleep "$poll_interval"
  done
}

wait_for_endpoint_converged() {
  local runtime_id="$1"
  local endpoint_name="$2"
  local expected_version="$3"
  local timeout_seconds="$4"
  local poll_interval="$5"
  local started_at
  started_at="$(date +%s)"

  while true; do
    local endpoint_payload
    endpoint_payload="$(aws_cli bedrock-agentcore-control get-agent-runtime-endpoint --agent-runtime-id "$runtime_id" --endpoint-name "$endpoint_name" --output json)"
    local endpoint_values
    endpoint_values="$(parse_endpoint_payload "$endpoint_payload")"
    local status live_version target_version
    IFS='|' read -r status live_version target_version _ <<< "$endpoint_values"

    if [[ "$status" == "READY" && "$live_version" == "$target_version" ]]; then
      if [[ -n "$expected_version" && "$live_version" != "$expected_version" ]]; then
        echo "Endpoint '$endpoint_name' converged to version '$live_version', expected '$expected_version'." >&2
        return 1
      fi
      printf '%s\n' "$endpoint_payload"
      return 0
    fi

    if [[ "$status" == "CREATE_FAILED" || "$status" == "UPDATE_FAILED" ]]; then
      echo "Endpoint '$endpoint_name' entered terminal status '$status'." >&2
      return 1
    fi

    local now
    now="$(date +%s)"
    if (( now - started_at >= timeout_seconds )); then
      echo "Timed out waiting for endpoint '$endpoint_name' convergence." >&2
      return 1
    fi

    sleep "$poll_interval"
  done
}

resolve_stack_output() {
  local stack_name="$1"
  local output_key="$2"
  aws_cli cloudformation describe-stacks \
    --stack-name "$stack_name" \
    --query "Stacks[0].Outputs[?OutputKey==\`$output_key\`].OutputValue" \
    --output text
}

aws_cli() {
  if [[ -n "$AWS_PROFILE_NAME" ]]; then
    AWS_PROFILE="$AWS_PROFILE_NAME" AWS_REGION="$REGION" aws --region "$REGION" "$@"
    return
  fi
  AWS_REGION="$REGION" aws --region "$REGION" "$@"
}

DEPLOYMENT_ENVIRONMENT="${FLUTTER_DEPLOYMENT_ENVIRONMENT:-sandbox}"
STACK_NAME="${STACK_NAME:-FlutterAgentCorePocStack}"
RUNTIME_BOOTSTRAP_STACK_NAME=""
REGION="${AWS_REGION:-eu-west-1}"
AWS_PROFILE_NAME="${AWS_PROFILE:-}"
RUNTIME_NAME=""
RUNTIME_ID=""
ENDPOINT_NAME=""
EXPECTED_RUNTIME_VERSION=""
TARGET_SCOPE="account"
TARGET_ID=""
GUARD_MODE="enforce"
WAIT_TIMEOUT_SECONDS="900"
POLL_INTERVAL_SECONDS="10"
GUARD_SCRIPT_PATH="$REPO_ROOT/scripts/guards/apply-flutter-design-aws-guards.sh"
RUNTIME_ROLE_ARN=""
RUNTIME_ARTIFACT_MODE="code"
RUNTIME_CODE_S3_BUCKET=""
RUNTIME_CODE_S3_PREFIX=""
RUNTIME_CODE_S3_VERSION_ID=""
RUNTIME_CODE_ENTRYPOINT="runtime/agentcore_main.py"
RUNTIME_CODE_PYTHON_VERSION="PYTHON_3_12"
RUNTIME_CONTAINER_URI=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --deployment-environment)
      DEPLOYMENT_ENVIRONMENT="${2:-}"
      shift 2
      ;;
    --stack-name)
      STACK_NAME="${2:-}"
      shift 2
      ;;
    --runtime-bootstrap-stack-name)
      RUNTIME_BOOTSTRAP_STACK_NAME="${2:-}"
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
    --runtime-name)
      RUNTIME_NAME="${2:-}"
      shift 2
      ;;
    --runtime-id)
      RUNTIME_ID="${2:-}"
      shift 2
      ;;
    --endpoint-name)
      ENDPOINT_NAME="${2:-}"
      shift 2
      ;;
    --expected-runtime-version)
      EXPECTED_RUNTIME_VERSION="${2:-}"
      shift 2
      ;;
    --target-scope)
      TARGET_SCOPE="${2:-}"
      shift 2
      ;;
    --target-id)
      TARGET_ID="${2:-}"
      shift 2
      ;;
    --guard-mode)
      GUARD_MODE="${2:-}"
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
    --guard-script-path)
      GUARD_SCRIPT_PATH="${2:-}"
      shift 2
      ;;
    --runtime-role-arn)
      RUNTIME_ROLE_ARN="${2:-}"
      shift 2
      ;;
    --runtime-artifact-mode)
      RUNTIME_ARTIFACT_MODE="${2:-}"
      shift 2
      ;;
    --runtime-code-s3-bucket)
      RUNTIME_CODE_S3_BUCKET="${2:-}"
      shift 2
      ;;
    --runtime-code-s3-prefix)
      RUNTIME_CODE_S3_PREFIX="${2:-}"
      shift 2
      ;;
    --runtime-code-s3-version-id)
      RUNTIME_CODE_S3_VERSION_ID="${2:-}"
      shift 2
      ;;
    --runtime-code-entrypoint)
      RUNTIME_CODE_ENTRYPOINT="${2:-}"
      shift 2
      ;;
    --runtime-code-python-version)
      RUNTIME_CODE_PYTHON_VERSION="${2:-}"
      shift 2
      ;;
    --runtime-container-uri)
      RUNTIME_CONTAINER_URI="${2:-}"
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

if [[ "$DEPLOYMENT_ENVIRONMENT" != "sandbox" && "$DEPLOYMENT_ENVIRONMENT" != "preprod" && "$DEPLOYMENT_ENVIRONMENT" != "prod" ]]; then
  echo "--deployment-environment must be sandbox, preprod, or prod." >&2
  exit 2
fi
if [[ -z "$RUNTIME_NAME" ]]; then
  RUNTIME_NAME="flutter_shared_platform_$DEPLOYMENT_ENVIRONMENT"
fi
if [[ -z "$RUNTIME_BOOTSTRAP_STACK_NAME" ]]; then
  RUNTIME_BOOTSTRAP_STACK_NAME="${STACK_NAME}-RuntimeBootstrap"
fi
if [[ -z "$ENDPOINT_NAME" ]]; then
  ENDPOINT_NAME="$DEPLOYMENT_ENVIRONMENT"
fi
if [[ -z "$RUNTIME_CODE_S3_PREFIX" ]]; then
  RUNTIME_CODE_S3_PREFIX="agentcore/$DEPLOYMENT_ENVIRONMENT/shared-runtime.zip"
fi
if [[ "$REGION" != "eu-west-1" ]]; then
  echo "Region must be eu-west-1. Received: $REGION" >&2
  exit 2
fi
if [[ "$TARGET_SCOPE" != "account" && "$TARGET_SCOPE" != "org" ]]; then
  echo "--target-scope must be account or org." >&2
  exit 2
fi
if [[ "$GUARD_MODE" != "detect" && "$GUARD_MODE" != "enforce" ]]; then
  echo "--guard-mode must be detect or enforce." >&2
  exit 2
fi
if [[ -n "$EXPECTED_RUNTIME_VERSION" ]]; then
  validate_positive_int "$EXPECTED_RUNTIME_VERSION" "expected-runtime-version"
fi
validate_positive_int "$WAIT_TIMEOUT_SECONDS" "wait-timeout-seconds"
validate_positive_int "$POLL_INTERVAL_SECONDS" "poll-interval-seconds"
if [[ ! -x "$GUARD_SCRIPT_PATH" ]]; then
  echo "Guard script is not executable: $GUARD_SCRIPT_PATH" >&2
  exit 2
fi

require_cmd aws
require_cmd npm
require_python_bin

if [[ "${AWS_REGION:-eu-west-1}" != "eu-west-1" ]]; then
  echo "AWS_REGION must be eu-west-1." >&2
  exit 2
fi
if [[ -n "${BEDROCK_REGION:-}" && "${BEDROCK_REGION:-}" != "eu-west-1" ]]; then
  echo "BEDROCK_REGION must be eu-west-1 when set." >&2
  exit 2
fi
if [[ -n "${CDK_DEFAULT_REGION:-}" && "${CDK_DEFAULT_REGION:-}" != "eu-west-1" ]]; then
  echo "CDK_DEFAULT_REGION must be eu-west-1 when set." >&2
  exit 2
fi

export AWS_REGION="eu-west-1"
export BEDROCK_REGION="eu-west-1"
export CDK_DEFAULT_REGION="eu-west-1"
export FLUTTER_DEPLOYMENT_ENVIRONMENT="$DEPLOYMENT_ENVIRONMENT"

package_runtime_if_needed() {
  local bucket="$1"
  local object_key="$2"
  local package_dir="$REPO_ROOT/build/agentcore-runtime/$DEPLOYMENT_ENVIRONMENT"
  local package_zip="$package_dir/shared-runtime.zip"
  mkdir -p "$package_dir"
  "$PYTHON_BIN" "$REPO_ROOT/scripts/deploy/package-shared-runtime.py" \
    --repo-root "$REPO_ROOT" \
    --output-zip "$package_zip" >/dev/null
  aws_cli s3 cp "$package_zip" "s3://$bucket/$object_key"
}

ensure_runtime_bootstrap_resources() {
  if [[ -n "$RUNTIME_ROLE_ARN" && -n "$RUNTIME_CODE_S3_BUCKET" ]]; then
    return 0
  fi
  aws_cli cloudformation deploy \
    --stack-name "$RUNTIME_BOOTSTRAP_STACK_NAME" \
    --template-file "$REPO_ROOT/infra/runtime-bootstrap-resources.yaml" \
    --capabilities CAPABILITY_NAMED_IAM \
    --parameter-overrides "DeploymentEnvironment=$DEPLOYMENT_ENVIRONMENT" >/dev/null
  if [[ -z "$RUNTIME_CODE_S3_BUCKET" ]]; then
    RUNTIME_CODE_S3_BUCKET="$(resolve_stack_output "$RUNTIME_BOOTSTRAP_STACK_NAME" "RuntimeArtifactsBucketName")"
  fi
  if [[ -z "$RUNTIME_ROLE_ARN" ]]; then
    RUNTIME_ROLE_ARN="$(resolve_stack_output "$RUNTIME_BOOTSTRAP_STACK_NAME" "RuntimeExecutionRoleArn")"
  fi
}

echo "==> AWS identity preflight"
CALLER_ACCOUNT_ID="$(aws_cli sts get-caller-identity --query Account --output text)"
if [[ -z "$TARGET_ID" ]]; then
  TARGET_ID="$CALLER_ACCOUNT_ID"
fi
if [[ "$TARGET_SCOPE" == "account" ]]; then
  validate_account_id "$TARGET_ID" "target-id"
fi

echo "==> Resolve or create AgentCore runtime"
if [[ -n "$RUNTIME_ID" ]]; then
  runtime_payload="$(aws_cli bedrock-agentcore-control get-agent-runtime --agent-runtime-id "$RUNTIME_ID" --output json)"
else
  runtime_payload="$(aws_cli bedrock-agentcore-control list-agent-runtimes \
    --query "agentRuntimes[?agentRuntimeName==\`$RUNTIME_NAME\`] | [0]" \
    --output json)"
fi

if [[ -n "$runtime_payload" && "$runtime_payload" != "null" && "$runtime_payload" != "None" ]]; then
  runtime_values="$(parse_runtime_payload "$runtime_payload")"
  IFS='|' read -r RUNTIME_ID RUNTIME_ARN _ _ _ <<< "$runtime_values"
fi

if [[ -z "$RUNTIME_ID" ]]; then
  if [[ -z "$RUNTIME_ARTIFACT_MODE" ]]; then
    echo "Runtime not found. Provide --runtime-artifact-mode to create one." >&2
    exit 1
  fi
  if [[ "$RUNTIME_ARTIFACT_MODE" != "code" && "$RUNTIME_ARTIFACT_MODE" != "container" ]]; then
    echo "--runtime-artifact-mode must be code or container." >&2
    exit 2
  fi

  artifact_value=""
  if [[ "$RUNTIME_ARTIFACT_MODE" == "code" ]]; then
    ensure_runtime_bootstrap_resources
    if [[ -z "$RUNTIME_CODE_S3_VERSION_ID" ]]; then
      package_runtime_if_needed "$RUNTIME_CODE_S3_BUCKET" "$RUNTIME_CODE_S3_PREFIX"
    fi
    IFS=',' read -r -a entry_point_parts <<< "$RUNTIME_CODE_ENTRYPOINT"
    if (( ${#entry_point_parts[@]} == 0 || ${#entry_point_parts[@]} > 2 )); then
      echo "--runtime-code-entrypoint must contain one or two comma-separated entries." >&2
      exit 2
    fi
    entry_point_value="[$(printf '%s,' "${entry_point_parts[@]}" | sed 's/,$//')]"
    artifact_value="codeConfiguration={code={s3={bucket=$RUNTIME_CODE_S3_BUCKET,prefix=$RUNTIME_CODE_S3_PREFIX}},runtime=$RUNTIME_CODE_PYTHON_VERSION,entryPoint=$entry_point_value}"
    if [[ -n "$RUNTIME_CODE_S3_VERSION_ID" ]]; then
      artifact_value="codeConfiguration={code={s3={bucket=$RUNTIME_CODE_S3_BUCKET,prefix=$RUNTIME_CODE_S3_PREFIX,versionId=$RUNTIME_CODE_S3_VERSION_ID}},runtime=$RUNTIME_CODE_PYTHON_VERSION,entryPoint=$entry_point_value}"
    fi
  else
    if [[ -z "$RUNTIME_ROLE_ARN" ]]; then
      ensure_runtime_bootstrap_resources
    fi
    if [[ -z "$RUNTIME_CONTAINER_URI" ]]; then
      echo "Container artifact mode requires --runtime-container-uri." >&2
      exit 2
    fi
    artifact_value="containerConfiguration={containerUri=$RUNTIME_CONTAINER_URI}"
  fi

  create_args=(
    bedrock-agentcore-control
    create-agent-runtime
    --agent-runtime-name "$RUNTIME_NAME"
    --role-arn "$RUNTIME_ROLE_ARN"
    --network-configuration "networkMode=PUBLIC"
    --protocol-configuration "serverProtocol=A2A"
    --agent-runtime-artifact "$artifact_value"
    --output json
  )

  runtime_payload="$(aws_cli "${create_args[@]}")"
  runtime_values="$(parse_runtime_payload "$runtime_payload")"
  IFS='|' read -r RUNTIME_ID RUNTIME_ARN _ _ _ <<< "$runtime_values"
fi

runtime_ready_payload="$(wait_for_runtime_ready "$RUNTIME_ID" "$WAIT_TIMEOUT_SECONDS" "$POLL_INTERVAL_SECONDS")"
runtime_ready_values="$(parse_runtime_payload "$runtime_ready_payload")"
IFS='|' read -r _ RUNTIME_ARN RUNTIME_VERSION _ _ <<< "$runtime_ready_values"

echo "==> Resolve or create AgentCore runtime endpoint"
endpoint_payload="$(aws_cli bedrock-agentcore-control get-agent-runtime-endpoint \
  --agent-runtime-id "$RUNTIME_ID" \
  --endpoint-name "$ENDPOINT_NAME" \
  --output json 2>/dev/null || true)"
if [[ -z "$endpoint_payload" || "$endpoint_payload" == "None" || "$endpoint_payload" == "null" ]]; then
  create_endpoint_args=(
    bedrock-agentcore-control
    create-agent-runtime-endpoint
    --agent-runtime-id "$RUNTIME_ID"
    --name "$ENDPOINT_NAME"
    --output json
  )
  if [[ -n "$RUNTIME_VERSION" ]]; then
    create_endpoint_args+=(--agent-runtime-version "$RUNTIME_VERSION")
  fi
  endpoint_payload="$(aws_cli "${create_endpoint_args[@]}")"
fi

endpoint_values="$(parse_endpoint_payload "$endpoint_payload")"
IFS='|' read -r endpoint_status _ endpoint_target_version _ <<< "$endpoint_values"
if [[ -n "$EXPECTED_RUNTIME_VERSION" && "$endpoint_target_version" != "$EXPECTED_RUNTIME_VERSION" ]]; then
  aws_cli bedrock-agentcore-control update-agent-runtime-endpoint \
    --agent-runtime-id "$RUNTIME_ID" \
    --endpoint-name "$ENDPOINT_NAME" \
    --agent-runtime-version "$EXPECTED_RUNTIME_VERSION" \
    --output json >/dev/null
fi

endpoint_converged_payload="$(wait_for_endpoint_converged "$RUNTIME_ID" "$ENDPOINT_NAME" "$EXPECTED_RUNTIME_VERSION" "$WAIT_TIMEOUT_SECONDS" "$POLL_INTERVAL_SECONDS")"
endpoint_converged_values="$(parse_endpoint_payload "$endpoint_converged_payload")"
IFS='|' read -r endpoint_status endpoint_live_version endpoint_target_version endpoint_arn <<< "$endpoint_converged_values"

echo "==> Deploy shared platform stack"
(
  cd "$REPO_ROOT/infra"
  npm exec -- cdk deploy "$STACK_NAME" \
    --require-approval never \
    --parameters "DeploymentEnvironment=$DEPLOYMENT_ENVIRONMENT" \
    --parameters "AgentRuntimeArn=$RUNTIME_ARN" \
    --parameters "AgentRuntimeId=$RUNTIME_ID" \
    --parameters "AgentRuntimeEndpointName=$ENDPOINT_NAME" \
    --parameters "AgentRuntimeEndpointArn=$endpoint_arn" \
    --parameters "AgentRuntimeEndpointStatus=$endpoint_status"
)

echo "==> Apply AWS guard policy"
guard_args=(
  --mode "$GUARD_MODE"
  --target-scope "$TARGET_SCOPE"
  --target-id "$TARGET_ID"
  --stack-name "$STACK_NAME"
  --region "eu-west-1"
  --runtime-id "$RUNTIME_ID"
  --endpoint-name "$ENDPOINT_NAME"
)
if [[ -n "$EXPECTED_RUNTIME_VERSION" ]]; then
  guard_args+=(--expected-runtime-version "$EXPECTED_RUNTIME_VERSION")
fi
"$GUARD_SCRIPT_PATH" "${guard_args[@]}"

echo "==> Final endpoint verification"
final_endpoint_payload="$(aws_cli bedrock-agentcore-control get-agent-runtime-endpoint \
  --agent-runtime-id "$RUNTIME_ID" \
  --endpoint-name "$ENDPOINT_NAME" \
  --output json)"
final_endpoint_values="$(parse_endpoint_payload "$final_endpoint_payload")"
IFS='|' read -r final_status final_live_version final_target_version _ <<< "$final_endpoint_values"
if [[ "$final_status" != "READY" || "$final_live_version" != "$final_target_version" ]]; then
  echo "Endpoint '$ENDPOINT_NAME' is not converged after deployment. status=$final_status live=$final_live_version target=$final_target_version" >&2
  exit 1
fi
if [[ -n "$EXPECTED_RUNTIME_VERSION" && "$final_live_version" != "$EXPECTED_RUNTIME_VERSION" ]]; then
  echo "Endpoint '$ENDPOINT_NAME' is READY but version '$final_live_version' does not match expected '$EXPECTED_RUNTIME_VERSION'." >&2
  exit 1
fi

echo "Shared platform bootstrap completed for deployment environment '$DEPLOYMENT_ENVIRONMENT'."
echo "RuntimeId=$RUNTIME_ID"
echo "EndpointName=$ENDPOINT_NAME"
echo "EndpointVersion=$endpoint_live_version"
