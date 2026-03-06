# Flutter Design Control Ownership Matrix

This matrix defines the single active CI owner for each quality/design control. A control can be measured by multiple tools during migration windows, but only one owner can block CI.

| Control Area | Active CI Owner | Scope | Notes |
| --- | --- | --- | --- |
| LLM gateway non-bypass (R1) | `scripts/linters/flutter-design/check-flutter-design-compliance.py` | `R1-LLM-GATEWAY-NON-BYPASS` | Deprecated parity checker can run with `RUN_DEPRECATED_LLM_GATEWAY_PARITY=1` but is non-blocking ownership.
| MCP stage gateway usage (R1) | `scripts/linters/flutter-design/check-flutter-design-compliance.py` | `R1-MCP-GATEWAY-USAGE` | Adapter-based marker checks.
| MCP stage direct client bypass (R1) | `scripts/linters/flutter-design/check-flutter-design-compliance.py` | `R1-MCP-NO-DIRECT-SERVICE-CALL` | Adapter marker allow/deny.
| Region pinning (R1) | `scripts/linters/flutter-design/check-flutter-design-compliance.py` | `R1-REGION-PINNING` | Static pinning guard for defaults.
| Route metadata parity (R2) | `scripts/linters/flutter-design/check-flutter-design-compliance.py` | `R2-ROUTE-METADATA` | Route metadata marker integrity.
| Infra identity boundary (R2) | `scripts/linters/flutter-design/check-flutter-design-compliance.py` | `R2-INFRA-IDENTITY-BOUNDARY` | Runtime/gateway IAM path markers.
| Gateway host validation (R2) | `scripts/linters/flutter-design/check-flutter-design-compliance.py` | `R2-GATEWAY-HOST-VALIDATION` | Runtime config guard markers.
| Process scope drift (R3) | `scripts/linters/flutter-design/check-flutter-design-compliance.py` | `R3-PROCESS-SCOPE-DRIFT` | Enabled in strict lanes.
| Regulated scope drift (R4) | `scripts/linters/flutter-design/check-flutter-design-compliance.py` | `R4-REGULATED-SCOPE-DRIFT` | Enabled in strict lanes.
| Domain architecture boundaries | `scripts/linters/architecture-boundaries/check-architecture-boundaries.py` | Python import graph | Recursively scans nested modules.
| Semantic contract ownership | `scripts/linters/semantic-contract-ownership/check-semantic-contract-ownership.py` | Canonical symbol ownership | Domain-specific, stays standalone.
| Complexity headroom | `scripts/linters/complexity-headroom/check-complexity-headroom.py` | Maintainability budget | Quality signal, not Flutter-tier specific.
| Waiver expiry governance | `scripts/linters/flutter-design/check-flutter-design-waivers.py` | Waiver file validation | Blocks strict lanes on expired entries.

## Migration note

The legacy checker `scripts/linters/llm-gateway-boundary/check-llm-gateway-boundary.py` remains available for parity windows only. Remove it after at least one clean cycle of parity checks.
