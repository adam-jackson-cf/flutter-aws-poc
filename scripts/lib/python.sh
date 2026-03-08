#!/usr/bin/env bash

resolve_python_bin() {
  if [[ -n "${PYTHON_BIN:-}" ]]; then
    if command -v "$PYTHON_BIN" >/dev/null 2>&1; then
      printf '%s\n' "$PYTHON_BIN"
      return 0
    fi
    echo "Configured PYTHON_BIN is not executable on PATH: $PYTHON_BIN" >&2
    return 1
  fi

  if [[ -n "${UV_VENV_PYTHON_BIN:-}" ]]; then
    if [[ -x "$UV_VENV_PYTHON_BIN" ]]; then
      printf '%s\n' "$UV_VENV_PYTHON_BIN"
      return 0
    fi
    echo "Configured UV_VENV_PYTHON_BIN is not executable: $UV_VENV_PYTHON_BIN" >&2
    return 1
  fi

  if command -v python >/dev/null 2>&1; then
    command -v python
    return 0
  fi

  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return 0
  fi

  echo "Python interpreter not found. Set PYTHON_BIN or UV_VENV_PYTHON_BIN, or install 'python'/'python3' on PATH." >&2
  return 1
}

require_python_bin() {
  PYTHON_BIN="$(resolve_python_bin)"
  export PYTHON_BIN
}
