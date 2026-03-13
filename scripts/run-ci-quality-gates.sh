#!/usr/bin/env bash
set -euo pipefail

RUNNER_PATH="scripts/run-ci-quality-gates.sh"
LANE="${QUALITY_GATES_LANE:-quality-gates-core}"
UV_BIN="${UV_BIN:-uv}"
UV_PYTHON_VERSION="${UV_PYTHON_VERSION:-3.12.7}"
UV_REQUIREMENTS_FILE="${UV_REQUIREMENTS_FILE:-requirements.txt}"
UV_VENV_PYTHON_BIN="${UV_VENV_PYTHON_BIN:-}"
DESIGN_REPO_ROOT="${DESIGN_REPO_ROOT:-$PWD}"
PYTEST_COVERAGE_TARGET="${PYTEST_COVERAGE_TARGET:-95}"
COMPLEXITY_MAX="${COMPLEXITY_MAX:-10}"
LENGTH_MAX="${LENGTH_MAX:-80}"
PARAM_MAX="${PARAM_MAX:-5}"
HEADROOM_COMPLEXITY_WARN="${HEADROOM_COMPLEXITY_WARN:-9}"
HEADROOM_LENGTH_WARN="${HEADROOM_LENGTH_WARN:-70}"
HEADROOM_PARAM_WARN="${HEADROOM_PARAM_WARN:-4}"
PYTHON_RUNNER_RESOLUTION="unresolved"

print_lane_help() {
  cat <<'USAGE'
Quality gate lanes:
  preflight          Fast structural checks (parity, syntax, formatting, infra typecheck)
  fast-r1r2          Fast contract enforcement lane (R1/R2 only)
  quality-gates-core Full contract-first PR lane (R1-R3 + tests + maintainability)
  strict-r3          Strict lane for R3 policy plus waiver governance
  nightly-full       Strict scheduled lane with synth and mutation checks
  release-hardening  Strict release lane with synth and mutation checks
USAGE
}

print_usage() {
  cat <<'USAGE'
Usage:
  bash scripts/run-ci-quality-gates.sh [--lane=<lane>]
  bash scripts/run-ci-quality-gates.sh --list-lanes
  bash scripts/run-ci-quality-gates.sh --print-python-cmd
  bash scripts/run-ci-quality-gates.sh --help

Python runner resolution:
  - UV_BIN defaults to `uv`
  - UV_PYTHON_VERSION defaults to `3.12.7`
  - UV_REQUIREMENTS_FILE defaults to `requirements.txt`
  - UV_VENV_PYTHON_BIN can point at a prebuilt environment python

Environment:
  - DESIGN_REPO_ROOT controls which artifact tree the Flutter design linter evaluates
  - PYTEST_COVERAGE_TARGET defaults to 95 for core enforcement logic

Examples:
  bash scripts/run-ci-quality-gates.sh --lane=fast-r1r2
  bash scripts/run-ci-quality-gates.sh --lane=quality-gates-core
  DESIGN_REPO_ROOT=tests/fixtures/flutter-design/valid-r2 bash scripts/run-ci-quality-gates.sh --lane=quality-gates-core
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
  mapfile -t prettier_files < <(
    rg --files \
      -g '*.json' \
      -g '*.md' \
      -g '*.yaml' \
      -g '*.yml' \
      -g '*.ts' \
      -g '!infra/cdk.out/**' \
      -g '!infra/node_modules/**' \
      -g '!node_modules/**'
  )
  if [[ "${#prettier_files[@]}" -eq 0 ]]; then
    return 0
  fi
  npm exec -- prettier --check "${prettier_files[@]}"
}

run_ruff_complexity_check() {
  run_python -m ruff check scripts tests --select C901,PLR0913 --config "lint.mccabe.max-complexity=$COMPLEXITY_MAX" --config "lint.pylint.max-args=$PARAM_MAX"
}

run_lizard_complexity_check() {
  run_python -m lizard -C "$COMPLEXITY_MAX" -L "$LENGTH_MAX" -a "$PARAM_MAX" scripts infra/bin infra/lib
}

run_headroom_complexity_check() {
  run_python scripts/linters/complexity-headroom/check-complexity-headroom.py \
    --warn-ccn "$HEADROOM_COMPLEXITY_WARN" \
    --warn-length "$HEADROOM_LENGTH_WARN" \
    --warn-params "$HEADROOM_PARAM_WARN"
}

run_flutter_design_waiver_check() {
  run_python scripts/linters/flutter-design/check-flutter-design-waivers.py
}

run_flutter_design_compliance_check() {
  local skip_tiers="${1:-}"
  local args=(
    python
    scripts/linters/flutter-design/check-flutter-design-compliance.py
    --repo-root
    "$DESIGN_REPO_ROOT"
    --output
    text
    --timings
  )
  if [[ -n "$skip_tiers" ]]; then
    args+=(--skip "$skip_tiers")
  fi
  run_python "${args[@]}"
}

run_ci_python_syntax_guard() {
  mapfile -t py_files < <(rg --files -g '*.py' -g '!infra/cdk.out/**' -g '!node_modules/**' -g '!infra/node_modules/**')
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
    --cov=scripts/linters/flutter_design_support \
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
    run_step "TypeScript complexity lint (infra)" npm --prefix infra run lint:eslint
  fi
}

run_common_static_suite() {
  run_step "Parity guard" parity_guard
  run_step "Python syntax guard (uv pinned ${UV_PYTHON_VERSION})" run_ci_python_syntax_guard
  run_step "Prettier formatting check" run_prettier_check
  run_typescript_lint_if_present
  run_step "Python complexity lint (ruff <= ${COMPLEXITY_MAX})" run_ruff_complexity_check
  run_step \
    "Complexity headroom guard (cc >= ${HEADROOM_COMPLEXITY_WARN}, length >= ${HEADROOM_LENGTH_WARN}, params >= ${HEADROOM_PARAM_WARN})" \
    run_headroom_complexity_check
  run_step "Cross-runtime complexity lint (cc <= ${COMPLEXITY_MAX}, length <= ${LENGTH_MAX}, params <= ${PARAM_MAX})" run_lizard_complexity_check
}

run_lane_preflight() {
  run_step "Parity guard" parity_guard
  run_step "Python syntax guard (uv pinned ${UV_PYTHON_VERSION})" run_ci_python_syntax_guard
  run_step "Prettier formatting check" run_prettier_check
  run_typescript_lint_if_present
}

run_lane_fast_r1r2() {
  run_lane_preflight
  run_step "Flutter solution design compliance linter (R1/R2)" run_flutter_design_compliance_check "R3"
}

run_lane_quality_gates_core() {
  run_common_static_suite
  run_step "Flutter solution design compliance linter (R1-R3)" run_flutter_design_compliance_check ""
  run_step "Python tests + coverage gate (${PYTEST_COVERAGE_TARGET}%)" run_pytest_coverage_gate
}

run_lane_strict_r3() {
  run_step "Parity guard" parity_guard
  run_step "Flutter waiver governance" run_flutter_design_waiver_check
  run_step "Flutter solution design compliance linter (R1-R3 strict)" run_flutter_design_compliance_check ""
  run_step "Python tests + coverage gate (${PYTEST_COVERAGE_TARGET}%)" run_pytest_coverage_gate
}

run_lane_nightly_full() {
  run_lane_quality_gates_core
  run_step "Flutter waiver governance" run_flutter_design_waiver_check
  run_step "CDK synth (infra)" run_cdk_synth
  run_step "Python mutation gate" run_python scripts/run-mutation-gate.py
}

run_lane_release_hardening() {
  run_lane_quality_gates_core
  run_step "Flutter waiver governance" run_flutter_design_waiver_check
  run_step "CDK synth (infra)" run_cdk_synth
  run_step "Python mutation gate" run_python scripts/run-mutation-gate.py
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
    strict-r3)
      run_lane_strict_r3
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
echo "Resolved Python runner: $PYTHON_RUNNER_RESOLUTION"
echo "Design repo root: $DESIGN_REPO_ROOT"
run_lane
