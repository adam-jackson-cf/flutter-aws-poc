#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/lib/python.sh"

usage() {
  cat <<'USAGE'
Usage:
  scripts/guards/apply-flutter-design-aws-guards.sh [options]

Required options:
  --mode <detect|enforce>
  --target-scope <account|org>
  --target-id <id>
  --stack-name <name>
  --region <value>

Optional options:
  --aws-profile <profile>
  --assume-role-arn <arn>
  --runtime-id <id>
  --endpoint-name <value>                Default: production
  --expected-runtime-version <int>
  --allow-global-services <csv>          Default: iam,organizations,route53,cloudfront,support,sts
  --allowed-bedrock-caller-arns <csv>    Extra principal ARN allowlist for Bedrock direct actions
  --org-management-account-id <id>       Required for --target-scope org
  --scp-policy-name <name>               Default: FlutterDesignAwsGuards
  --wait-timeout-seconds <int>           Default: 900
  --poll-interval-seconds <int>          Default: 10
  --output <text|json>                   Default: text
  --fail-on-drift                        Default behavior
  --allow-drift                          Detect mode can return success with drift
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

aws_cli() {
  if [[ -n "$AWS_PROFILE_NAME" ]]; then
    AWS_PROFILE="$AWS_PROFILE_NAME" AWS_REGION="$REGION" aws --region "$REGION" "$@"
    return
  fi
  AWS_REGION="$REGION" aws --region "$REGION" "$@"
}

add_check() {
  local check_id="$1"
  local status="$2"
  local message="$3"
  printf '%s\t%s\t%s\n' "$check_id" "$status" "$message" >> "$CHECKS_FILE"
}

add_change() {
  local message="$1"
  printf '%s\n' "$message" >> "$CHANGES_FILE"
}

split_csv_to_quoted_json_list() {
  local csv="$1"
  CSV_VALUE="$csv" "$PYTHON_BIN" - <<'PY'
import json
import os

raw = os.environ.get("CSV_VALUE", "")
items = [item.strip() for item in raw.split(",") if item.strip()]
print(json.dumps(items))
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
print(str(payload.get("status", "")).strip())
print(live_version)
print(target_version)
PY
}

json_hash() {
  local payload="$1"
  PAYLOAD="$payload" "$PYTHON_BIN" - <<'PY'
import hashlib
import json
import os

payload = json.loads(os.environ["PAYLOAD"])
canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
print(hashlib.sha256(canonical.encode("utf-8")).hexdigest())
PY
}

build_policy_document() {
  local gateway_role_arn="$1"
  local extra_allowed_arns_json="$2"
  local allowed_global_actions_json="$3"

  GATEWAY_ROLE_ARN="$gateway_role_arn" \
  EXTRA_ALLOWED_ARNS_JSON="$extra_allowed_arns_json" \
  ALLOWED_GLOBAL_ACTIONS_JSON="$allowed_global_actions_json" \
  TARGET_REGION="$REGION" "$PYTHON_BIN" - <<'PY'
import json
import os

gateway_role = os.environ["GATEWAY_ROLE_ARN"]
extra_allowed_arns = json.loads(os.environ["EXTRA_ALLOWED_ARNS_JSON"])
allowed_global_actions = json.loads(os.environ["ALLOWED_GLOBAL_ACTIONS_JSON"])
region = os.environ["TARGET_REGION"]

principal_arns = [gateway_role, *extra_allowed_arns]

policy = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "DenyOutsideEuWest1",
            "Effect": "Deny",
            "NotAction": allowed_global_actions,
            "Resource": "*",
            "Condition": {
                "StringNotEquals": {
                    "aws:RequestedRegion": region
                }
            },
        },
        {
            "Sid": "DenyDirectBedrockInvocationOutsideGateway",
            "Effect": "Deny",
            "Action": [
                "bedrock:InvokeModel",
                "bedrock:InvokeModelWithResponseStream",
                "bedrock:Converse",
                "bedrock:ConverseStream",
            ],
            "Resource": "*",
            "Condition": {
                "ArnNotLike": {
                    "aws:PrincipalArn": principal_arns
                }
            },
        },
    ],
}

print(json.dumps(policy, indent=2, sort_keys=True))
PY
}

resolve_stack_output() {
  local output_key="$1"
  aws_cli cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query "Stacks[0].Outputs[?OutputKey==\`$output_key\`].OutputValue" \
    --output text
}

resolve_gateway_role_arn() {
  local function_name
  function_name="$(aws_cli cloudformation describe-stack-resources \
    --stack-name "$STACK_NAME" \
    --query "StackResources[?ResourceType==\`AWS::Lambda::Function\` && starts_with(LogicalResourceId, \`LlmGatewayFn\`)] | [0].PhysicalResourceId" \
    --output text 2>/dev/null || true)"

  if [[ -z "$function_name" || "$function_name" == "None" || "$function_name" == "null" ]]; then
    echo ""
    return
  fi

  aws_cli lambda get-function \
    --function-name "$function_name" \
    --query "Configuration.Role" \
    --output text
}

resolve_existing_policy_id() {
  aws_cli organizations list-policies-for-target \
    --target-id "$TARGET_ID" \
    --filter SERVICE_CONTROL_POLICY \
    --query "Policies[?Name=='$SCP_POLICY_NAME'].Id | [0]" \
    --output text
}

resolve_policy_content() {
  local policy_id="$1"
  aws_cli organizations describe-policy \
    --policy-id "$policy_id" \
    --query "Policy.Content" \
    --output text
}

is_org_available() {
  aws_cli organizations describe-organization --output json >/dev/null 2>&1
}

assume_role_if_requested() {
  if [[ -z "$ASSUME_ROLE_ARN" ]]; then
    return
  fi

  local payload
  payload="$(aws_cli sts assume-role \
    --role-arn "$ASSUME_ROLE_ARN" \
    --role-session-name "flutter-design-guards" \
    --output json)"

  local creds=()
  while IFS= read -r line; do
    creds+=("$line")
  done < <(PAYLOAD="$payload" "$PYTHON_BIN" - <<'PY'
import json
import os

payload = json.loads(os.environ["PAYLOAD"])
creds = payload.get("Credentials", {})
print(str(creds.get("AccessKeyId", "")))
print(str(creds.get("SecretAccessKey", "")))
print(str(creds.get("SessionToken", "")))
PY
)

  if [[ -z "${creds[0]:-}" || -z "${creds[1]:-}" || -z "${creds[2]:-}" ]]; then
    echo "Failed to assume role: missing temporary credentials." >&2
    exit 1
  fi

  export AWS_ACCESS_KEY_ID="${creds[0]}"
  export AWS_SECRET_ACCESS_KEY="${creds[1]}"
  export AWS_SESSION_TOKEN="${creds[2]}"
}

MODE=""
TARGET_SCOPE=""
TARGET_ID=""
STACK_NAME=""
REGION="${AWS_REGION:-eu-west-1}"
AWS_PROFILE_NAME="${AWS_PROFILE:-}"
ASSUME_ROLE_ARN=""
RUNTIME_ID=""
ENDPOINT_NAME="production"
EXPECTED_RUNTIME_VERSION=""
ALLOW_GLOBAL_SERVICES="iam,organizations,route53,cloudfront,support,sts"
ALLOWED_BEDROCK_CALLER_ARNS=""
ORG_MANAGEMENT_ACCOUNT_ID=""
SCP_POLICY_NAME="FlutterDesignAwsGuards"
WAIT_TIMEOUT_SECONDS="900"
POLL_INTERVAL_SECONDS="10"
OUTPUT_FORMAT="text"
FAIL_ON_DRIFT="true"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      MODE="${2:-}"
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
    --stack-name)
      STACK_NAME="${2:-}"
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
    --assume-role-arn)
      ASSUME_ROLE_ARN="${2:-}"
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
    --allow-global-services)
      ALLOW_GLOBAL_SERVICES="${2:-}"
      shift 2
      ;;
    --allowed-bedrock-caller-arns)
      ALLOWED_BEDROCK_CALLER_ARNS="${2:-}"
      shift 2
      ;;
    --org-management-account-id)
      ORG_MANAGEMENT_ACCOUNT_ID="${2:-}"
      shift 2
      ;;
    --scp-policy-name)
      SCP_POLICY_NAME="${2:-}"
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
    --output)
      OUTPUT_FORMAT="${2:-}"
      shift 2
      ;;
    --fail-on-drift)
      FAIL_ON_DRIFT="true"
      shift
      ;;
    --allow-drift)
      FAIL_ON_DRIFT="false"
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

if [[ "$MODE" != "detect" && "$MODE" != "enforce" ]]; then
  echo "--mode must be detect or enforce" >&2
  exit 2
fi
if [[ "$TARGET_SCOPE" != "account" && "$TARGET_SCOPE" != "org" ]]; then
  echo "--target-scope must be account or org" >&2
  exit 2
fi
if [[ -z "$TARGET_ID" ]]; then
  echo "--target-id is required" >&2
  exit 2
fi
if [[ -z "$STACK_NAME" ]]; then
  echo "--stack-name is required" >&2
  exit 2
fi
if [[ "$REGION" != "eu-west-1" ]]; then
  echo "Region must be eu-west-1. Received: $REGION" >&2
  exit 2
fi
if [[ "$OUTPUT_FORMAT" != "text" && "$OUTPUT_FORMAT" != "json" ]]; then
  echo "--output must be text or json" >&2
  exit 2
fi
if [[ "$TARGET_SCOPE" == "org" ]]; then
  if [[ -z "$ORG_MANAGEMENT_ACCOUNT_ID" ]]; then
    echo "--org-management-account-id is required for --target-scope org" >&2
    exit 2
  fi
  validate_account_id "$ORG_MANAGEMENT_ACCOUNT_ID" "org-management-account-id"
fi
if [[ "$TARGET_SCOPE" == "account" ]]; then
  validate_account_id "$TARGET_ID" "target-id"
fi
if [[ -n "$EXPECTED_RUNTIME_VERSION" ]]; then
  validate_positive_int "$EXPECTED_RUNTIME_VERSION" "expected-runtime-version"
fi
validate_positive_int "$WAIT_TIMEOUT_SECONDS" "wait-timeout-seconds"
validate_positive_int "$POLL_INTERVAL_SECONDS" "poll-interval-seconds"

require_cmd aws
require_python_bin

TMP_DIR="$(mktemp -d -t flutter-design-guards.XXXXXX)"
CHECKS_FILE="$TMP_DIR/checks.tsv"
CHANGES_FILE="$TMP_DIR/changes.txt"
trap 'rm -rf "$TMP_DIR"' EXIT

touch "$CHECKS_FILE" "$CHANGES_FILE"

echo "==> AWS identity preflight"
assume_role_if_requested
CALLER_ACCOUNT_ID="$(aws_cli sts get-caller-identity --query Account --output text)"
CALLER_ARN="$(aws_cli sts get-caller-identity --query Arn --output text)"

if [[ "$TARGET_SCOPE" == "account" && "$CALLER_ACCOUNT_ID" != "$TARGET_ID" && -z "$ASSUME_ROLE_ARN" ]]; then
  echo "Caller account ($CALLER_ACCOUNT_ID) does not match target account ($TARGET_ID). Use --assume-role-arn." >&2
  exit 2
fi

if [[ "$TARGET_SCOPE" == "org" && "$CALLER_ACCOUNT_ID" != "$ORG_MANAGEMENT_ACCOUNT_ID" ]]; then
  echo "Warning: caller account does not match --org-management-account-id. Continuing with caller account permissions." >&2
fi

RUNTIME_ARN="$(resolve_stack_output "RuntimeArn" || true)"
STACK_RUNTIME_ID="$(resolve_stack_output "RuntimeId" || true)"
GATEWAY_URL="$(resolve_stack_output "GatewayUrl" || true)"
RUNTIME_ENDPOINT_ARN="$(resolve_stack_output "RuntimeEndpointArn" || true)"
RUNTIME_ENDPOINT_STATUS_OUTPUT="$(resolve_stack_output "RuntimeEndpointStatus" || true)"

missing_outputs=()
for value_key in RUNTIME_ARN STACK_RUNTIME_ID GATEWAY_URL RUNTIME_ENDPOINT_ARN RUNTIME_ENDPOINT_STATUS_OUTPUT; do
  value="${!value_key}"
  if [[ -z "$value" || "$value" == "None" || "$value" == "null" ]]; then
    missing_outputs+=("$value_key")
  fi
done

if [[ "${#missing_outputs[@]}" -gt 0 ]]; then
  add_check "G4_STACK_CONTRACT" "ERROR" "Missing required stack outputs: ${missing_outputs[*]}"
else
  add_check "G4_STACK_CONTRACT" "PASS" "Required stack outputs are present"
fi

if [[ -z "$RUNTIME_ID" ]]; then
  RUNTIME_ID="$STACK_RUNTIME_ID"
fi

if [[ -z "$RUNTIME_ID" || "$RUNTIME_ID" == "None" || "$RUNTIME_ID" == "null" ]]; then
  add_check "G3_RUNTIME_ENDPOINT" "ERROR" "RuntimeId could not be resolved"
else
  endpoint_payload="$(aws_cli bedrock-agentcore-control get-agent-runtime-endpoint \
    --agent-runtime-id "$RUNTIME_ID" \
    --endpoint-name "$ENDPOINT_NAME" \
    --output json 2>/dev/null || true)"

  if [[ -z "$endpoint_payload" ]]; then
    add_check "G3_RUNTIME_ENDPOINT" "ERROR" "Runtime endpoint not found for runtime '$RUNTIME_ID' endpoint '$ENDPOINT_NAME'"
  else
    endpoint_values=()
    while IFS= read -r line; do
      endpoint_values+=("$line")
    done < <(parse_endpoint_payload "$endpoint_payload")
    endpoint_status="${endpoint_values[0]:-}"
    live_version="${endpoint_values[1]:-}"
    target_version="${endpoint_values[2]:-}"

    if [[ "$MODE" == "enforce" && -n "$EXPECTED_RUNTIME_VERSION" && "$target_version" != "$EXPECTED_RUNTIME_VERSION" ]]; then
      aws_cli bedrock-agentcore-control update-agent-runtime-endpoint \
        --agent-runtime-id "$RUNTIME_ID" \
        --endpoint-name "$ENDPOINT_NAME" \
        --target-version "$EXPECTED_RUNTIME_VERSION" \
        --output json >/dev/null
      add_change "Updated runtime endpoint '$ENDPOINT_NAME' target version to $EXPECTED_RUNTIME_VERSION"

      deadline_epoch=$((SECONDS + WAIT_TIMEOUT_SECONDS))
      while true; do
        endpoint_payload="$(aws_cli bedrock-agentcore-control get-agent-runtime-endpoint \
          --agent-runtime-id "$RUNTIME_ID" \
          --endpoint-name "$ENDPOINT_NAME" \
          --output json)"
        endpoint_values=()
        while IFS= read -r line; do
          endpoint_values+=("$line")
        done < <(parse_endpoint_payload "$endpoint_payload")
        endpoint_status="${endpoint_values[0]:-}"
        live_version="${endpoint_values[1]:-}"
        target_version="${endpoint_values[2]:-}"

        if [[ "$endpoint_status" == "READY" && "$live_version" == "$target_version" ]]; then
          break
        fi
        if [[ "$endpoint_status" == "FAILED" ]]; then
          add_check "G3_RUNTIME_ENDPOINT" "ERROR" "Runtime endpoint status is FAILED after update"
          break
        fi
        if (( SECONDS >= deadline_epoch )); then
          add_check "G3_RUNTIME_ENDPOINT" "ERROR" "Timed out waiting for runtime endpoint convergence"
          break
        fi
        sleep "$POLL_INTERVAL_SECONDS"
      done
    fi

    if ! grep -q '^G3_RUNTIME_ENDPOINT\t' "$CHECKS_FILE"; then
      if [[ "$endpoint_status" != "READY" ]]; then
        add_check "G3_RUNTIME_ENDPOINT" "DRIFT" "Runtime endpoint status is '$endpoint_status'"
      elif [[ "$live_version" != "$target_version" ]]; then
        add_check "G3_RUNTIME_ENDPOINT" "DRIFT" "Runtime endpoint liveVersion ($live_version) != targetVersion ($target_version)"
      elif [[ -n "$EXPECTED_RUNTIME_VERSION" && "$live_version" != "$EXPECTED_RUNTIME_VERSION" ]]; then
        add_check "G3_RUNTIME_ENDPOINT" "DRIFT" "Runtime endpoint version '$live_version' != expected '$EXPECTED_RUNTIME_VERSION'"
      else
        add_check "G3_RUNTIME_ENDPOINT" "PASS" "Runtime endpoint '$ENDPOINT_NAME' is READY and converged"
      fi
    fi
  fi
fi

org_available="false"
if is_org_available; then
  org_available="true"
fi

gateway_role_arn="$(resolve_gateway_role_arn || true)"
if [[ -z "$gateway_role_arn" || "$gateway_role_arn" == "None" || "$gateway_role_arn" == "null" ]]; then
  add_check "G2_NON_BYPASS" "ERROR" "Could not resolve gateway Lambda execution role ARN"
fi

allowed_global_actions_json="$(split_csv_to_quoted_json_list "$ALLOW_GLOBAL_SERVICES")"
extra_allowed_arns_json="$(split_csv_to_quoted_json_list "$ALLOWED_BEDROCK_CALLER_ARNS")"
org_policy_lookup_error=""
policy_id=""

if [[ "$org_available" == "true" ]]; then
  if ! policy_id="$(resolve_existing_policy_id 2>&1)"; then
    org_policy_lookup_error="$(printf '%s' "$policy_id" | tr '\n' ' ' | sed 's/[[:space:]]\+/ /g')"
    policy_id=""
  fi
fi

if [[ "$org_available" != "true" ]]; then
  if [[ "$MODE" == "enforce" ]]; then
    add_check "G1_REGION_GUARD" "ERROR" "Organizations API unavailable; cannot enforce SCP region guard"
    add_check "G2_NON_BYPASS" "ERROR" "Organizations API unavailable; cannot enforce SCP non-bypass guard"
  else
    add_check "G1_REGION_GUARD" "DRIFT" "Organizations API unavailable; SCP region guard cannot be validated in standalone detect mode"
    if ! grep -q '^G2_NON_BYPASS\t' "$CHECKS_FILE"; then
      add_check "G2_NON_BYPASS" "DRIFT" "Organizations API unavailable; SCP non-bypass guard cannot be validated in standalone detect mode"
    fi
  fi
elif [[ -n "$org_policy_lookup_error" ]]; then
  add_check "G1_REGION_GUARD" "ERROR" "Organizations SCP policy lookup denied: $org_policy_lookup_error"
  if ! grep -q '^G2_NON_BYPASS\t' "$CHECKS_FILE"; then
    add_check "G2_NON_BYPASS" "ERROR" "Organizations SCP policy lookup denied: $org_policy_lookup_error"
  fi
else
  if ! grep -q '^G2_NON_BYPASS\t' "$CHECKS_FILE"; then
    desired_policy="$(build_policy_document "$gateway_role_arn" "$extra_allowed_arns_json" "$allowed_global_actions_json")"
    desired_hash="$(json_hash "$desired_policy")"
    if [[ -z "$policy_id" || "$policy_id" == "None" || "$policy_id" == "null" ]]; then
      if [[ "$MODE" == "enforce" ]]; then
        created_payload="$(aws_cli organizations create-policy \
          --content "$desired_policy" \
          --description "Flutter design AWS guards" \
          --name "$SCP_POLICY_NAME" \
          --type SERVICE_CONTROL_POLICY \
          --output json)"
        policy_id="$(PAYLOAD="$created_payload" "$PYTHON_BIN" - <<'PY'
import json
import os

payload = json.loads(os.environ["PAYLOAD"])
print(payload.get("Policy", {}).get("PolicySummary", {}).get("Id", ""))
PY
)"
        add_change "Created SCP policy '$SCP_POLICY_NAME' ($policy_id)"
      else
        add_check "G1_REGION_GUARD" "DRIFT" "SCP policy '$SCP_POLICY_NAME' not attached to target"
        add_check "G2_NON_BYPASS" "DRIFT" "SCP policy '$SCP_POLICY_NAME' not attached to target"
      fi
    fi

    if [[ -n "$policy_id" && "$policy_id" != "None" && "$policy_id" != "null" ]]; then
      current_policy="$(resolve_policy_content "$policy_id")"
      current_hash="$(json_hash "$current_policy")"

      if [[ "$current_hash" != "$desired_hash" ]]; then
        if [[ "$MODE" == "enforce" ]]; then
          aws_cli organizations update-policy \
            --policy-id "$policy_id" \
            --content "$desired_policy" >/dev/null
          add_change "Updated SCP policy '$SCP_POLICY_NAME' content"
          current_hash="$desired_hash"
        else
          add_check "G1_REGION_GUARD" "DRIFT" "SCP policy content drift detected for region guard"
          add_check "G2_NON_BYPASS" "DRIFT" "SCP policy content drift detected for non-bypass guard"
        fi
      fi

      attachment_id="$(aws_cli organizations list-targets-for-policy \
        --policy-id "$policy_id" \
        --query "Targets[?TargetId=='$TARGET_ID'].TargetId | [0]" \
        --output text || true)"

      if [[ -z "$attachment_id" || "$attachment_id" == "None" || "$attachment_id" == "null" ]]; then
        if [[ "$MODE" == "enforce" ]]; then
          aws_cli organizations attach-policy \
            --policy-id "$policy_id" \
            --target-id "$TARGET_ID" >/dev/null
          add_change "Attached SCP policy '$SCP_POLICY_NAME' to target '$TARGET_ID'"
        else
          if ! grep -q '^G1_REGION_GUARD\t' "$CHECKS_FILE"; then
            add_check "G1_REGION_GUARD" "DRIFT" "SCP policy '$SCP_POLICY_NAME' is not attached to target '$TARGET_ID'"
          fi
          if ! grep -q '^G2_NON_BYPASS\t' "$CHECKS_FILE"; then
            add_check "G2_NON_BYPASS" "DRIFT" "SCP policy '$SCP_POLICY_NAME' is not attached to target '$TARGET_ID'"
          fi
        fi
      fi

      if ! grep -q '^G1_REGION_GUARD\t' "$CHECKS_FILE"; then
        add_check "G1_REGION_GUARD" "PASS" "Region deny guard policy hash: $current_hash"
      fi
      if ! grep -q '^G2_NON_BYPASS\t' "$CHECKS_FILE"; then
        add_check "G2_NON_BYPASS" "PASS" "Bedrock non-bypass guard policy hash: $current_hash"
      fi
      POLICY_ID_VALUE="$policy_id"
      POLICY_HASH_VALUE="$current_hash"
    fi
  fi
fi

if [[ -z "${POLICY_ID_VALUE:-}" ]]; then
  POLICY_ID_VALUE=""
fi
if [[ -z "${POLICY_HASH_VALUE:-}" ]]; then
  POLICY_HASH_VALUE=""
fi

error_count="$(awk -F '\t' '$2 == "ERROR" {count++} END {print count+0}' "$CHECKS_FILE")"
drift_count="$(awk -F '\t' '$2 == "DRIFT" {count++} END {print count+0}' "$CHECKS_FILE")"

if [[ "$error_count" != "0" ]]; then
  OVERALL_STATUS="ERROR"
  EXIT_CODE=1
elif [[ "$drift_count" != "0" ]]; then
  OVERALL_STATUS="DRIFT"
  if [[ "$FAIL_ON_DRIFT" == "true" ]]; then
    EXIT_CODE=3
  else
    EXIT_CODE=0
  fi
else
  OVERALL_STATUS="PASS"
  EXIT_CODE=0
fi

if [[ "$OUTPUT_FORMAT" == "json" ]]; then
  CHECKS_PATH="$CHECKS_FILE" \
  CHANGES_PATH="$CHANGES_FILE" \
  MODE_VALUE="$MODE" \
  TARGET_SCOPE_VALUE="$TARGET_SCOPE" \
  TARGET_ID_VALUE="$TARGET_ID" \
  OVERALL_STATUS_VALUE="$OVERALL_STATUS" \
  POLICY_ID_VALUE="$POLICY_ID_VALUE" \
  POLICY_HASH_VALUE="$POLICY_HASH_VALUE" \
  CALLER_ARN_VALUE="$CALLER_ARN" \
  EXIT_CODE_VALUE="$EXIT_CODE" "$PYTHON_BIN" - <<'PY'
import datetime as dt
import json
import os

checks = []
with open(os.environ["CHECKS_PATH"], "r", encoding="utf-8") as handle:
    for raw in handle:
        raw = raw.rstrip("\n")
        if not raw:
            continue
        check_id, status, message = raw.split("\t", 2)
        checks.append(
            {
                "id": check_id,
                "status": status,
                "message": message,
            }
        )

changes = []
with open(os.environ["CHANGES_PATH"], "r", encoding="utf-8") as handle:
    for raw in handle:
        value = raw.strip()
        if value:
            changes.append(value)

payload = {
    "timestamp_utc": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
    "mode": os.environ["MODE_VALUE"],
    "target": {
        "scope": os.environ["TARGET_SCOPE_VALUE"],
        "id": os.environ["TARGET_ID_VALUE"],
    },
    "caller_arn": os.environ["CALLER_ARN_VALUE"],
    "policy_id": os.environ["POLICY_ID_VALUE"],
    "policy_hash": os.environ["POLICY_HASH_VALUE"],
    "checks": checks,
    "changes": changes,
    "overall_status": os.environ["OVERALL_STATUS_VALUE"],
    "exit_code": int(os.environ["EXIT_CODE_VALUE"]),
}
print(json.dumps(payload, indent=2, sort_keys=True))
PY
else
  echo "Mode: $MODE"
  echo "TargetScope: $TARGET_SCOPE"
  echo "TargetId: $TARGET_ID"
  echo "Region: $REGION"
  echo "CallerArn: $CALLER_ARN"
  echo "PolicyId: ${POLICY_ID_VALUE:-}"
  echo "PolicyHash: ${POLICY_HASH_VALUE:-}"
  echo
  while IFS=$'\t' read -r check_id check_status check_message; do
    [[ -z "$check_id" ]] && continue
    echo "${check_id}=${check_status} ${check_message}"
  done < "$CHECKS_FILE"

  if [[ -s "$CHANGES_FILE" ]]; then
    echo
    echo "Applied changes:"
    while IFS= read -r change_entry; do
      [[ -z "$change_entry" ]] && continue
      echo "- $change_entry"
    done < "$CHANGES_FILE"
  fi

  echo
  echo "OVERALL_STATUS=$OVERALL_STATUS"
fi

exit "$EXIT_CODE"
