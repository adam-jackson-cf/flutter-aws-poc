# Flutter Design Control Ownership Matrix

This matrix defines the single blocking owner for each active control in the contract-first baseline.

| Control Area                             | Active CI Owner                                                     | Scope                             | Notes                                                                             |
| ---------------------------------------- | ------------------------------------------------------------------- | --------------------------------- | --------------------------------------------------------------------------------- |
| Capability Definition schema             | `scripts/linters/flutter-design/check-flutter-design-compliance.py` | `R1-CAPABILITY-DEFINITION-SCHEMA` | Enforced against `capability-definitions/` via JSON Schema                        |
| Safety Envelope schema                   | `scripts/linters/flutter-design/check-flutter-design-compliance.py` | `R1-SAFETY-ENVELOPE-SCHEMA`       | Enforced against `safety-envelopes/` via JSON Schema                              |
| Identity context and LLM gateway routing | `scripts/linters/flutter-design/check-flutter-design-compliance.py` | `R1-IDENTITY-CONTEXT-CONTRACT`    | Requires declared identity tags, gateway routing, and identity-safe tool bindings |
| Evaluation Pack schema                   | `scripts/linters/flutter-design/check-flutter-design-compliance.py` | `R2-EVALUATION-PACK-SCHEMA`       | Enforced against `evaluation-packs/` via JSON Schema                              |
| Publish readiness                        | `scripts/linters/flutter-design/check-flutter-design-compliance.py` | `R2-PUBLISH-READYNESS`            | Cross-checks capability, envelope, evaluation pack, release gate, and datasets    |
| Workflow Contract schema                 | `scripts/linters/flutter-design/check-flutter-design-compliance.py` | `R3-WORKFLOW-CONTRACT-SCHEMA`     | Enforced against `workflow-contracts/` via JSON Schema                            |
| Process contract requirement             | `scripts/linters/flutter-design/check-flutter-design-compliance.py` | `R3-PROCESS-CONTRACT-REQUIRED`    | Required for process-scoped or higher-risk capability definitions                 |
| Waiver expiry governance                 | `scripts/linters/flutter-design/check-flutter-design-waivers.py`    | Waiver file validation            | Blocks `strict-r3`, `nightly-full`, and `release-hardening` on expired waivers    |
| Complexity headroom                      | `scripts/linters/complexity-headroom/check-complexity-headroom.py`  | Maintainability budget            | Applies to scripts, tests, and infra scaffold                                     |
| Mutation resistance                      | `scripts/run-mutation-gate.py`                                      | Core enforcement logic            | Targets `artifacts.py` and `publish_readiness.py`, not wrapper CLIs               |
| AWS design guard policy automation       | `scripts/guards/apply-flutter-design-aws-guards.sh`                 | Region and non-bypass governance  | External governance support, not a substitute for repo contract checks            |

## Notes

- Deleted PoC-specific architecture-boundary and semantic-ownership scanners are no longer control owners.
- If new controls are introduced, add them here only when they become the blocking CI owner for that concern.
