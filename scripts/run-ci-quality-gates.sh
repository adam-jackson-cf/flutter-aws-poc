#!/usr/bin/env bash
set -euo pipefail

RUNNER_PATH="scripts/run-ci-quality-gates.sh"
MODE="check"
STAGE="false"
PYTEST_COVERAGE_TARGET="${PYTEST_COVERAGE_TARGET:-100}"
RUN_DUPLICATION_SIGNALS="${RUN_DUPLICATION_SIGNALS:-1}"
DUPLICATION_SIGNAL_TARGET="${DUPLICATION_SIGNAL_TARGET:-.}"
DUPLICATION_SIGNAL_MIN_SEVERITY="${DUPLICATION_SIGNAL_MIN_SEVERITY:-medium}"
COMPLEXITY_MAX="${COMPLEXITY_MAX:-10}"
LENGTH_MAX="${LENGTH_MAX:-80}"
PARAM_MAX="${PARAM_MAX:-5}"
HEADROOM_COMPLEXITY_WARN="${HEADROOM_COMPLEXITY_WARN:-9}"
HEADROOM_LENGTH_WARN="${HEADROOM_LENGTH_WARN:-70}"
HEADROOM_PARAM_WARN="${HEADROOM_PARAM_WARN:-4}"
FLUTTER_DESIGN_LINTER_SKIP="${FLUTTER_DESIGN_LINTER_SKIP:-R3,R4}"

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

run_prettier_check() {
  npm exec -- prettier --check \
    package.json \
    infra/package.json \
    infra/tsconfig.json \
    infra/bin/app.ts \
    infra/lib/flutter-agentcore-poc-stack.ts \
    .pre-commit-config.yaml \
    .github/workflows/ci-quality-gates.yml
}

run_ruff_complexity_check() {
  python3 -m ruff check aws/lambda evals runtime scripts --select C901,PLR0913 --config "lint.mccabe.max-complexity=$COMPLEXITY_MAX" --config "lint.pylint.max-args=$PARAM_MAX"
}

run_lizard_complexity_check() {
  python3 -m lizard -C "$COMPLEXITY_MAX" -L "$LENGTH_MAX" -a "$PARAM_MAX" aws/lambda evals runtime scripts infra/bin infra/lib
}

run_headroom_complexity_check() {
  python3 scripts/linters/complexity-headroom/check-complexity-headroom.py \
    --warn-ccn "$HEADROOM_COMPLEXITY_WARN" \
    --warn-length "$HEADROOM_LENGTH_WARN" \
    --warn-params "$HEADROOM_PARAM_WARN"
}

run_semantic_contract_ownership_check() {
  python3 scripts/linters/semantic-contract-ownership/check-semantic-contract-ownership.py
}

run_architecture_boundary_check() {
  python3 scripts/linters/architecture-boundaries/check-architecture-boundaries.py
}

run_llm_gateway_boundary_check() {
  python3 scripts/linters/llm-gateway-boundary/check-llm-gateway-boundary.py
}

run_flutter_design_compliance_check() {
  local skip_tiers="${FLUTTER_DESIGN_LINTER_SKIP}"
  if [[ -n "$skip_tiers" ]]; then
    python3 scripts/linters/flutter-design/check-flutter-design-compliance.py --skip "$skip_tiers"
    return 0
  fi
  python3 scripts/linters/flutter-design/check-flutter-design-compliance.py
}

run_cdk_synth() {
  if [[ "${CI:-}" == "true" ]] && [[ -f "infra/package.json" ]] && grep -q '"cdk:synth:ci"' "infra/package.json"; then
    npm --prefix infra run cdk:synth:ci
    return 0
  fi
  npm --prefix infra run cdk:synth
}

build_duplication_artifact_root() {
  local ts
  ts="$(date -u +%Y%m%dT%H%M%SZ)"
  echo ".enaible/artifacts/ci-quality/duplication/$ts"
}

run_duplication_signals() {
  if ! command -v enaible >/dev/null 2>&1; then
    echo "Skipping duplication signals: enaible not installed."
    return 0
  fi

  local artifact_root
  artifact_root="$(build_duplication_artifact_root)"
  mkdir -p "$artifact_root"

  local audit_out="$artifact_root/duplication-audit.json"
  local audit_summary="$artifact_root/duplication-audit-summary.json"
  local code_out="$artifact_root/duplication-code-only.json"
  local code_summary="$artifact_root/duplication-code-only-summary.json"

  local common_excludes=(
    --exclude "dist/"
    --exclude "build/"
    --exclude "node_modules/"
    --exclude "__pycache__/"
    --exclude ".next/"
    --exclude "vendor/"
    --exclude ".venv/"
    --exclude ".mypy_cache/"
    --exclude ".ruff_cache/"
    --exclude ".pytest_cache/"
    --exclude ".gradle/"
    --exclude "target/"
    --exclude "bin/"
    --exclude "obj/"
    --exclude "coverage/"
    --exclude ".turbo/"
    --exclude ".svelte-kit/"
    --exclude ".cache/"
    --exclude ".enaible/artifacts/"
    --exclude ".enaible/"
  )
  local code_only_excludes=(
    --exclude "package-lock.json"
    --exclude "infra/package-lock.json"
    --exclude "docs/flutter-uki-ai-platform-arch/**"
    --exclude "*.html"
  )

  ENAIBLE_REPO_ROOT="$(pwd)" enaible analyzers run quality:jscpd \
    --target "$DUPLICATION_SIGNAL_TARGET" \
    --min-severity "$DUPLICATION_SIGNAL_MIN_SEVERITY" \
    --out "$audit_out" \
    --summary-out "$audit_summary" \
    "${common_excludes[@]}"

  ENAIBLE_REPO_ROOT="$(pwd)" enaible analyzers run quality:jscpd \
    --target "$DUPLICATION_SIGNAL_TARGET" \
    --min-severity "$DUPLICATION_SIGNAL_MIN_SEVERITY" \
    --out "$code_out" \
    --summary-out "$code_summary" \
    "${common_excludes[@]}" \
    "${code_only_excludes[@]}"

  echo "DUPLICATION_AUDIT_SUMMARY=$audit_summary"
  echo "DUPLICATION_CODE_ONLY_SUMMARY=$code_summary"
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

run_step "Prettier formatting check" run_prettier_check

if [[ -f "infra/package.json" ]] && grep -q '"lint"' "infra/package.json"; then
  run_step "TypeScript lint (infra)" npm --prefix infra run lint
fi

if [[ -f "infra/package.json" ]] && grep -q '"lint:eslint"' "infra/package.json"; then
  run_step "TypeScript complexity lint (eslint <= ${COMPLEXITY_MAX})" npm --prefix infra run lint:eslint
fi

run_step "Python complexity lint (ruff <= ${COMPLEXITY_MAX})" run_ruff_complexity_check

run_step \
  "Complexity headroom guard (cc >= ${HEADROOM_COMPLEXITY_WARN}, length >= ${HEADROOM_LENGTH_WARN}, params >= ${HEADROOM_PARAM_WARN})" \
  run_headroom_complexity_check

run_step "Cross-runtime complexity lint (cc <= ${COMPLEXITY_MAX}, length <= ${LENGTH_MAX}, params <= ${PARAM_MAX})" run_lizard_complexity_check

run_step "Semantic contract ownership guard" run_semantic_contract_ownership_check

run_step "Architecture boundary guard" run_architecture_boundary_check

run_step "LLM gateway non-bypass guard" run_llm_gateway_boundary_check

run_step "Flutter solution design compliance linter" run_flutter_design_compliance_check

if [[ -f "infra/package.json" ]] && grep -q '"cdk:synth"' "infra/package.json"; then
  run_step "CDK synth (infra)" run_cdk_synth
fi

if [[ -d "tests" ]] && [[ -f "requirements.txt" ]] && grep -qi '^pytest' "requirements.txt"; then
  run_step \
    "Python tests + coverage gate (${PYTEST_COVERAGE_TARGET}%)" \
    python3 -m pytest \
      --cov=evals \
      --cov=runtime \
      --cov=aws/lambda \
      --cov-config=.coveragerc \
      --cov-report=term-missing \
      --cov-fail-under="$PYTEST_COVERAGE_TARGET"
fi

if [[ -d "tests" ]] && [[ -x "scripts/run-mutation-gate.sh" ]]; then
  if [[ "${CI:-}" == "true" || "${RUN_MUTATION_GATE:-0}" == "1" ]]; then
    run_step "Python mutation gate" bash scripts/run-mutation-gate.sh
  else
    echo "Skipping mutation gate (set RUN_MUTATION_GATE=1 to run locally)."
  fi
fi

if [[ "$RUN_DUPLICATION_SIGNALS" == "1" ]]; then
  run_step "Duplication signals (audit + code-only)" run_duplication_signals
fi

if [[ "$MODE" == "fix" ]]; then
  echo "Fix mode enabled: no auto-fixers are configured for this stack."
fi

if [[ "$MODE" == "fix" ]] && [[ "$STAGE" == "true" ]]; then
  echo "Stage mode enabled: no files to stage because no auto-fixers ran."
fi
