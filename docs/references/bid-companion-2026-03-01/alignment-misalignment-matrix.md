# Alignment / Misalignment Matrix (Current PoC)

Legend: `Accurate` = implemented and evidenced; `Partial` = some implementation but incomplete against design claim; `Misrepresented` = materially diverges from design claim.

| Design claim (Flutter docs) | Repo/deployed evidence | Status | Why it matters |
|---|---|---|---|
| L3 is non-bypassable model boundary (LiteLLM/gateway path) | Lambda stages and runtime flows call Bedrock/OpenAI directly through PoC gateway client; no LiteLLM service boundary in execution path | Misrepresented | Reliability outcomes are not isolated to Flutter's intended non-bypass model boundary |
| Identity Context immutable and ABAC-propagated across all calls | IAM auth is used for runtime/gateway, but no full identity-context lineage and ABAC decision trace in eval artifacts | Partial | Security/governance claims are only partially evidenced |
| RFC 8693 token exchange per tool call | Design docs require this; PoC does not emit end-to-end RFC 8693 trace evidence in run artifacts | Partial | Identity-isolation claim strength remains limited |
| R2/R3 workflow-contract semantics (compensation/replay/HITL) | State machine is parse -> fetch -> generate -> evaluate with no compensation/HITL branches | Misrepresented | Process-scope governance is not validated in this PoC |
| HITL mandatory/non-waivable for high-risk paths | No HITL gate state in deployed state machine | Misrepresented | Critical control behavior is untested |
| Immutable synchronous audit semantics | Artifacts are persisted to S3, but no immutable Object Lock compliance-mode evidence path is shown | Misrepresented | Compliance-grade audit claim is not supported |
| Private/no-direct-agent egress | Runtime network mode remains `PUBLIC`; Jira access is public endpoint egress | Misrepresented | Network-isolation narrative mismatch remains |
| MCP path exists and is exercised through AgentCore Gateway | Gateway is deployed/READY and used by `mcp` flow in live evaluations | Accurate | Confirms real AgentCore MCP integration is under test |
| Native vs MCP route parity with same task/model | Same dataset/harness and parity metadata (`gateway_model_id`, `runtime_bedrock_model_id`) are recorded per run | Accurate | Comparison integrity is auditable and reproducible |
| Deterministic metrics are release truth | `tool_failure_rate`, `business_success_rate`, `call_construction_*`, token/cost metrics, and release score are persisted per flow | Accurate | Decision signal is measurable and deterministic |
| Contract governance across layers | Contract artifacts and semantic ownership checks run in quality gates | Accurate | Contract drift is less likely to pass silently |
| Scheduler respects required execution contract | Nightly EventBridge input includes `expected_tool`; guard test enforces this | Accurate | Scheduled runs do not fail by construction on missing contract fields |

## High-priority notes

- Latest adversarial both-flow run (`nova-adv-large-postfix-20260302T214400Z`) passes deterministic release gate for both routes.
- MCP still carries measurable interface-specific penalties versus native in this run: higher call-construction failure rate, higher latency, and higher token/cost usage.
- Architecture-level conformance gaps remain governance and security controls, not baseline route viability.
