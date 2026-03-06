#!/usr/bin/env bash
set -euo pipefail

RUNNER_PATH="scripts/run-ci-quality-gates.sh"
MODE="check"
STAGE="false"
LANE="${QUALITY_GATES_LANE:-quality-gates-core}"
UV_BIN="${UV_BIN:-uv}"
UV_PYTHON_VERSION="${UV_PYTHON_VERSION:-3.12.7}"
UV_REQUIREMENTS_FILE="${UV_REQUIREMENTS_FILE:-requirements.txt}"
UV_VENV_PYTHON_BIN="${UV_VENV_PYTHON_BIN:-}"
PYTHON_RUNNER_RESOLUTION="unresolved"
PYTEST_COVERAGE_TARGET="${PYTEST_COVERAGE_TARGET:-100}"
COMPLEXITY_MAX="${COMPLEXITY_MAX:-10}"
LENGTH_MAX="${LENGTH_MAX:-80}"
PARAM_MAX="${PARAM_MAX:-5}"
HEADROOM_COMPLEXITY_WARN="${HEADROOM_COMPLEXITY_WARN:-9}"
HEADROOM_LENGTH_WARN="${HEADROOM_LENGTH_WARN:-70}"
HEADROOM_PARAM_WARN="${HEADROOM_PARAM_WARN:-4}"
FLUTTER_DESIGN_LINTER_SKIP="${FLUTTER_DESIGN_LINTER_SKIP:-R3,R4}"
RUN_DEPRECATED_LLM_GATEWAY_PARITY="${RUN_DEPRECATED_LLM_GATEWAY_PARITY:-0}"

print_lane_help() {
  cat <<'USAGE'
Quality gate lanes:
  preflight         Fast structural checks (parity guard, formatting, config sanity)
  fast-r1r2         PoC blocking lane (R1/R2 design + architecture + semantic guards)
  quality-gates-core Full PR lane (current default)
  extended-r3r4     Shadow lane for strict all-tier checks + waiver enforcement
  nightly-full      Strict full lane for scheduled quality and mutation checks
  release-hardening Strict full lane for release/tag pipelines
USAGE
}

print_usage() {
  cat <<'USAGE'
Usage:
  bash scripts/run-ci-quality-gates.sh [--lane=<lane>] [--fix] [--stage]
  bash scripts/run-ci-quality-gates.sh --list-lanes
  bash scripts/run-ci-quality-gates.sh --print-python-cmd
  bash scripts/run-ci-quality-gates.sh --help

Python runner resolution (uv default):
  - Runner command: UV_BIN (default: uv)
  - Pinned Python patch version: UV_PYTHON_VERSION (default: 3.12.7)
  - Dependency source: UV_REQUIREMENTS_FILE (default: requirements.txt)
  - Optional prebuilt environment python: UV_VENV_PYTHON_BIN
  - Gate Python commands run via:
      uv run --no-project --python <UV_PYTHON_VERSION> --with-requirements <UV_REQUIREMENTS_FILE> <python args>
  - No system python fallback path exists in this runner.

Examples:
  bash scripts/run-ci-quality-gates.sh --lane=fast-r1r2
  UV_PYTHON_VERSION=3.12.7 bash scripts/run-ci-quality-gates.sh --lane=preflight
  UV_BIN=uv bash scripts/run-ci-quality-gates.sh --print-python-cmd
  UV_VENV_PYTHON_BIN=.ci-venv/bin/python bash scripts/run-ci-quality-gates.sh --lane=quality-gates-core
USAGE
}

resolve_python_runner() {
  local full_version
  if [[ -n "$UV_VENV_PYTHON_BIN" ]]; then
    if [[ ! -x "$UV_VENV_PYTHON_BIN" ]]; then
      echo "Python runner resolution failed: UV_VENV_PYTHON_BIN '$UV_VENV_PYTHON_BIN' is not executable." >&2
      return 1
    fi
    full_version="$("$UV_VENV_PYTHON_BIN" -c 'import sys; print(".".join(str(part) for part in sys.version_info[:3]))')"
    if [[ "$full_version" != "$UV_PYTHON_VERSION" ]]; then
      echo "Python runner resolution failed: prebuilt env resolved Python ${full_version}, expected ${UV_PYTHON_VERSION}." >&2
      return 1
    fi
    PYTHON_RUNNER_RESOLUTION="venv(${UV_VENV_PYTHON_BIN} @ python ${full_version})"
    return 0
  fi

  if ! command -v "$UV_BIN" >/dev/null 2>&1; then
    echo "Python runner resolution failed: '$UV_BIN' is not installed or not on PATH." >&2
    return 1
  fi
  if [[ ! -f "$UV_REQUIREMENTS_FILE" ]]; then
    echo "Python runner resolution failed: requirements file '$UV_REQUIREMENTS_FILE' not found." >&2
    return 1
  fi
  full_version="$("$UV_BIN" run --no-project --python "$UV_PYTHON_VERSION" python -c 'import sys; print(".".join(str(part) for part in sys.version_info[:3]))')"
  if [[ "$full_version" != "$UV_PYTHON_VERSION" ]]; then
    echo "Python runner resolution failed: uv resolved Python ${full_version}, expected ${UV_PYTHON_VERSION}." >&2
    return 1
  fi
  PYTHON_RUNNER_RESOLUTION="uv(${UV_BIN} @ python ${full_version}, requirements=${UV_REQUIREMENTS_FILE})"
}

run_python() {
  if [[ -n "$UV_VENV_PYTHON_BIN" ]]; then
    "$UV_VENV_PYTHON_BIN" "$@"
    return 0
  fi
  "$UV_BIN" run --no-project --python "$UV_PYTHON_VERSION" --with-requirements "$UV_REQUIREMENTS_FILE" "$@"
}

for arg in "$@"; do
  case "$arg" in
    --fix)
      MODE="fix"
      ;;
    --stage)
      STAGE="true"
      ;;
    --lane=*)
      LANE="${arg#*=}"
      ;;
    --list-lanes)
      print_lane_help
      exit 0
      ;;
    --print-python-cmd)
      resolve_python_runner
      if [[ -n "$UV_VENV_PYTHON_BIN" ]]; then
        echo "$UV_VENV_PYTHON_BIN"
      else
        echo "$UV_BIN run --no-project --python $UV_PYTHON_VERSION --with-requirements $UV_REQUIREMENTS_FILE python"
      fi
      exit 0
      ;;
    --help|-h)
      print_usage
      echo
      print_lane_help
      echo
      if resolve_python_runner; then
        echo "Resolved Python runner: ${PYTHON_RUNNER_RESOLUTION}"
      else
        echo "Resolved Python runner: unavailable" >&2
      fi
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      exit 2
      ;;
  esac
done

resolve_python_runner

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
  run_python -m ruff check aws/lambda evals runtime scripts --select C901,PLR0913 --config "lint.mccabe.max-complexity=$COMPLEXITY_MAX" --config "lint.pylint.max-args=$PARAM_MAX"
}

run_lizard_complexity_check() {
  run_python -m lizard -C "$COMPLEXITY_MAX" -L "$LENGTH_MAX" -a "$PARAM_MAX" aws/lambda evals runtime scripts infra/bin infra/lib
}

run_headroom_complexity_check() {
  run_python scripts/linters/complexity-headroom/check-complexity-headroom.py \
    --warn-ccn "$HEADROOM_COMPLEXITY_WARN" \
    --warn-length "$HEADROOM_LENGTH_WARN" \
    --warn-params "$HEADROOM_PARAM_WARN"
}

run_semantic_contract_ownership_check() {
  run_python scripts/linters/semantic-contract-ownership/check-semantic-contract-ownership.py
}

run_architecture_boundary_check() {
  run_python scripts/linters/architecture-boundaries/check-architecture-boundaries.py
}

run_llm_gateway_boundary_check() {
  run_python scripts/linters/llm-gateway-boundary/check-llm-gateway-boundary.py
}

run_flutter_design_waiver_check() {
  run_python scripts/linters/flutter-design/check-flutter-design-waivers.py
}

run_flutter_design_compliance_check() {
  local skip_tiers="${1:-}"
  local output_format="${2:-text}"
  local args=(
    "$UV_BIN"
    run
    --no-project
    --python
    "$UV_PYTHON_VERSION"
    --with-requirements
    "$UV_REQUIREMENTS_FILE"
    python
    scripts/linters/flutter-design/check-flutter-design-compliance.py
    --output
    "$output_format"
    --timings
  )
  if [[ -n "$skip_tiers" ]]; then
    args+=(--skip "$skip_tiers")
  fi
  "${args[@]}"
}

run_ci_python_syntax_guard() {
  mapfile -t py_files < <(git ls-files "*.py")
  if [[ "${#py_files[@]}" -eq 0 ]]; then
    return 0
  fi

  run_python -m py_compile "${py_files[@]}"
}

run_cdk_synth() {
  if [[ "${CI:-}" == "true" ]] && [[ -f "infra/package.json" ]] && grep -q '"cdk:synth:ci"' "infra/package.json"; then
    npm --prefix infra run cdk:synth:ci
    return 0
  fi
  npm --prefix infra run cdk:synth
}

run_pytest_coverage_gate() {
  run_python -m pytest \
    --cov=evals \
    --cov=runtime \
    --cov=aws/lambda \
    --cov-config=.coveragerc \
    --cov-report=term-missing \
    --cov-fail-under="$PYTEST_COVERAGE_TARGET"
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

run_typescript_lint_if_present() {
  if [[ -f "infra/package.json" ]] && grep -q '"lint"' "infra/package.json"; then
    run_step "TypeScript lint (infra)" npm --prefix infra run lint
  fi

  if [[ -f "infra/package.json" ]] && grep -q '"lint:eslint"' "infra/package.json"; then
    run_step "TypeScript complexity lint (eslint <= ${COMPLEXITY_MAX})" npm --prefix infra run lint:eslint
  fi
}

run_pytest_if_configured() {
  if [[ -d "tests" ]] && [[ -f "requirements.txt" ]] && grep -qi '^pytest' "requirements.txt"; then
    run_step "Python tests + coverage gate (${PYTEST_COVERAGE_TARGET}%)" run_pytest_coverage_gate
  fi
}

run_mutation_if_configured() {
  if [[ -d "tests" ]] && [[ -x "scripts/run-mutation-gate.sh" ]]; then
    run_step "Python mutation gate" bash scripts/run-mutation-gate.sh
  fi
}

run_common_static_suite() {
  run_step "Prettier formatting check" run_prettier_check
  run_typescript_lint_if_present
  run_step "Python complexity lint (ruff <= ${COMPLEXITY_MAX})" run_ruff_complexity_check
  run_step \
    "Complexity headroom guard (cc >= ${HEADROOM_COMPLEXITY_WARN}, length >= ${HEADROOM_LENGTH_WARN}, params >= ${HEADROOM_PARAM_WARN})" \
    run_headroom_complexity_check
  run_step "Cross-runtime complexity lint (cc <= ${COMPLEXITY_MAX}, length <= ${LENGTH_MAX}, params <= ${PARAM_MAX})" run_lizard_complexity_check
  run_step "Semantic contract ownership guard" run_semantic_contract_ownership_check
  run_step "Architecture boundary guard" run_architecture_boundary_check
}

run_lane_preflight() {
  run_step "Parity guard" parity_guard
  run_step "Python syntax guard (uv pinned ${UV_PYTHON_VERSION})" run_ci_python_syntax_guard
  run_step "Prettier formatting check" run_prettier_check
  run_typescript_lint_if_present
}

run_lane_fast_r1r2() {
  run_step "Parity guard" parity_guard
  run_step "Python syntax guard (uv pinned ${UV_PYTHON_VERSION})" run_ci_python_syntax_guard
  run_step "Python complexity lint (ruff <= ${COMPLEXITY_MAX})" run_ruff_complexity_check
  run_step "Semantic contract ownership guard" run_semantic_contract_ownership_check
  run_step "Architecture boundary guard" run_architecture_boundary_check
  run_step "Flutter solution design compliance linter (R1/R2)" run_flutter_design_compliance_check "R3,R4"
}

run_lane_quality_gates_core() {
  run_step "Parity guard" parity_guard
  run_common_static_suite
  run_step "Flutter solution design compliance linter (default scope)" run_flutter_design_compliance_check "$FLUTTER_DESIGN_LINTER_SKIP"

  if [[ "$RUN_DEPRECATED_LLM_GATEWAY_PARITY" == "1" ]]; then
    run_step "Deprecated LLM gateway parity check" run_llm_gateway_boundary_check
  fi

  run_pytest_if_configured
}

run_lane_extended_r3r4() {
  run_step "Parity guard" parity_guard
  run_step "Flutter waiver governance" run_flutter_design_waiver_check
  run_step "Flutter solution design compliance linter (R1-R4 strict)" run_flutter_design_compliance_check ""

  run_pytest_if_configured
}

run_lane_nightly_full() {
  run_step "Parity guard" parity_guard
  run_common_static_suite
  run_step "Flutter waiver governance" run_flutter_design_waiver_check
  run_step "Flutter solution design compliance linter (R1-R4 strict)" run_flutter_design_compliance_check ""

  if [[ -f "infra/package.json" ]] && grep -q '"cdk:synth"' "infra/package.json"; then
    run_step "CDK synth (infra)" run_cdk_synth
  fi

  run_pytest_if_configured
  run_mutation_if_configured
}

run_lane_release_hardening() {
  run_step "Parity guard" parity_guard
  run_common_static_suite
  run_step "Flutter waiver governance" run_flutter_design_waiver_check
  run_step "Flutter solution design compliance linter (R1-R4 strict)" run_flutter_design_compliance_check ""
  run_pytest_if_configured
  run_mutation_if_configured
}

run_lane() {
  case "$LANE" in
    preflight)
      run_lane_preflight
      ;;
    fast-r1r2)
      run_lane_fast_r1r2
      ;;
    quality-gates-core)
      run_lane_quality_gates_core
      ;;
    extended-r3r4)
      run_lane_extended_r3r4
      ;;
    nightly-full)
      run_lane_nightly_full
      ;;
    release-hardening)
      run_lane_release_hardening
      ;;
    *)
      echo "Unknown quality gate lane: $LANE" >&2
      print_lane_help
      exit 2
      ;;
  esac
}

echo "Quality gate lane: $LANE"
run_lane

if [[ "$MODE" == "fix" ]]; then
  echo "Fix mode enabled: no auto-fixers are configured for this stack."
fi

if [[ "$MODE" == "fix" ]] && [[ "$STAGE" == "true" ]]; then
  echo "Stage mode enabled: no files to stage because no auto-fixers ran."
fi
