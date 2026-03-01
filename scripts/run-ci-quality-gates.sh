#!/usr/bin/env bash
set -euo pipefail

RUNNER_PATH="scripts/run-ci-quality-gates.sh"
MODE="check"
STAGE="false"
PYTEST_COVERAGE_TARGET="${PYTEST_COVERAGE_TARGET:-100}"

for arg in "$@"; do
  case "$arg" in
    --fix)
      MODE="fix"
      ;;
    --stage)
      STAGE="true"
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      exit 2
      ;;
  esac
done

run_step() {
  local step="$1"
  shift
  echo "==> $step"
  "$@"
}

parity_guard() {
  if [[ ! -f ".pre-commit-config.yaml" ]]; then
    echo "Parity guard failed: .pre-commit-config.yaml not found" >&2
    return 1
  fi
  if [[ ! -f ".github/workflows/ci-quality-gates.yml" ]]; then
    echo "Parity guard failed: .github/workflows/ci-quality-gates.yml not found" >&2
    return 1
  fi
  if ! grep -q "$RUNNER_PATH" ".pre-commit-config.yaml"; then
    echo "Parity guard failed: pre-commit does not reference $RUNNER_PATH" >&2
    return 1
  fi
  if ! grep -q "$RUNNER_PATH" ".github/workflows/ci-quality-gates.yml"; then
    echo "Parity guard failed: CI does not reference $RUNNER_PATH" >&2
    return 1
  fi
}

run_step "Parity guard" parity_guard

if [[ -f "infra/package.json" ]] && grep -q '"lint"' "infra/package.json"; then
  run_step "TypeScript lint (infra)" npm --prefix infra run lint
fi

if [[ -f "infra/package.json" ]] && grep -q '"cdk:synth"' "infra/package.json"; then
  run_step "CDK synth (infra)" npm --prefix infra run cdk:synth
fi

if [[ -d "tests" ]] && [[ -f "requirements.txt" ]] && grep -qi '^pytest' "requirements.txt"; then
  run_step \
    "Python tests + coverage gate (${PYTEST_COVERAGE_TARGET}%)" \
    python3 -m pytest \
      --cov=evals \
      --cov=runtime \
      --cov=aws/lambda \
      --cov-report=term-missing \
      --cov-fail-under="$PYTEST_COVERAGE_TARGET"
fi

if [[ "$MODE" == "fix" ]]; then
  echo "Fix mode enabled: no auto-fixers are configured for this stack."
fi

if [[ "$MODE" == "fix" ]] && [[ "$STAGE" == "true" ]]; then
  echo "Stage mode enabled: no files to stage because no auto-fixers ran."
fi
