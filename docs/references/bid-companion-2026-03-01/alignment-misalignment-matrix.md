# Alignment / Misalignment Matrix (Post-Deploy)

Legend: `Accurate` = implemented and evidenced; `Partial` = some implementation but incomplete against design claim; `Misrepresented` = materially diverges from design claim.

| Design claim (Flutter docs) | Repo/deployed evidence | Status | Why it matters |
|---|---|---|---|
| L3 is non-bypassable model boundary (LiteLLM/gateway path) | Lambda stages and runtime flows call Bedrock directly; no LiteLLM boundary in PoC execution path | Misrepresented | Reliability outcomes are not isolated to Flutter’s intended non-bypass boundary |
| Identity Context immutable and ABAC-propagated across all calls | IAM auth is used for gateway/runtime, but no full identity-context lineage and ABAC decision trace in eval outputs | Partial | Security/governance claims remain only partially evidenced |
| RFC 8693 token exchange per tool call | Design docs require this; PoC does not produce end-to-end RFC 8693 trace evidence in run artifacts | Partial | Identity-isolation claim strength remains limited |
| R2/R3 must include Workflow Contract, compensation, replay guarantees | State machine remains parse -> fetch -> generate -> evaluate with no compensation/HITL branches | Misrepresented | Process-scope governance cannot be validated from current PoC |
| HITL mandatory/non-waivable for high-risk paths | No HITL gate state in deployed state machine | Misrepresented | Critical control behavior untested |
| Synchronous immutable audit with risk-tier semantics | Artifacts persist to S3, but no Object Lock compliance posture; bucket lifecycle is still non-compliance style | Misrepresented | Compliance-grade audit contract remains unrepresented |
| Private/no-direct-agent egress for tool path | Runtime network mode remains `PUBLIC`; Jira access over public endpoint | Misrepresented | Network-isolation narrative mismatch persists |
| MCP path exists and is exercised through AgentCore Gateway | Gateway is deployed/READY and used by mcp flow in post-deploy runs | Accurate | Confirms real AgentCore MCP integration is under test |
| Native vs MCP route parity with same core task/model | Same dataset and harness used for both; post-deploy contract drift fixes are in place | Partial | Comparison integrity improved, but causal isolation still incomplete |
| Deterministic metrics + diagnostics model | Current eval outputs include `tool_match_rate`, `judge_summary`, `composite_reflection`; schema drift now fails fast | Accurate | Measurement integrity materially improved |
| Contract governance across layers | Generated contract artifacts and semantic ownership checks exist and pass | Accurate | Refactor quality controls are real and sustained |
| Scheduler input respects required execution contract | Nightly EventBridge target now includes `expected_tool`; scheduler guard test added | Accurate | Scheduled evidence quality no longer fails by construction on this contract |

## High-priority notes

- Alignment improved in experiment integrity and contract enforcement.
- Core architecture misalignments remain in orchestration governance, audit immutability, and security/network posture.
- Post-deploy runs indicate reliability issues in both routes, so next work should focus on controlled optimization and ablation.

