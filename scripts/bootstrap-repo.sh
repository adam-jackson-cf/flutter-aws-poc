#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  scripts/bootstrap-repo.sh [--deploy-infra]

Options:
  --deploy-infra   Run `cdk deploy` after dependency install and synth.
  --help           Show this help message.
USAGE
}

DEPLOY_INFRA="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --deploy-infra)
      DEPLOY_INFRA="true"
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

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Missing required command: $cmd" >&2
    exit 1
  fi
}

run_step() {
  local step="$1"
  shift
  echo "==> $step"
  "$@"
}

require_cmd python3
require_cmd npm
require_cmd aws

run_step "Install Python dependencies" python3 -m pip install -r requirements.txt
run_step "Install root Node dependencies" npm install
run_step "Install infra dependencies" npm --prefix infra install
run_step "CDK synth" npm --prefix infra run cdk:synth

if [[ "$DEPLOY_INFRA" == "true" ]]; then
  run_step "AWS identity preflight" aws sts get-caller-identity --query '{Account:Account,Arn:Arn}' --output table
  run_step "CDK diff" npm --prefix infra run cdk:diff
  run_step "CDK deploy" npm --prefix infra run cdk:deploy
fi

echo "Bootstrap complete."
