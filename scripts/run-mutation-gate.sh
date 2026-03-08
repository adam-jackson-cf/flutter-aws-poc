#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/python.sh"
require_python_bin

"$PYTHON_BIN" scripts/run-mutation-gate.py
