# Alignment / Misalignment Matrix

Legend: `Accurate` = implemented and evidenced; `Partial` = some implementation but incomplete against design claim; `Misrepresented` = materially diverges from design claim.

| Design claim (Flutter docs) | Repo/deployed evidence | Status | Why it matters |
|---|---|---|---|
| L3 is non-bypassable model boundary (LiteLLM/gateway path) | Lambda stages and runtime flows call Bedrock directly; no LiteLLM boundary in PoC execution path | Misrepresented | Reliability results are not isolated to the full intended production routing boundary |
| Identity Context immutable and ABAC-propagated across all calls | IAM auth is used for gateway/runtime, but no full session-tag lineage and ABAC decision trace in eval artifacts | Partial | Security/governance claims cannot be proven from this PoC output alone |
| RFC 8693 token exchange per tool call | Design docs require this; PoC uses IAM-authenticated gateway and MCP calls without end-to-end RFC 8693 observability evidence | Partial | Limits strength of identity-isolation validation claims |
| R2/R3 must include Workflow Contract, compensation, replay guarantees | State machine is parse -> fetch -> generate -> evaluate with flow choice only; no compensation/HITL branch model | Misrepresented | PoC cannot substantiate process-scope orchestration guarantees from Flutter model |
| HITL mandatory/non-waivable for high-risk paths | No HITL gate state in deployed state machine | Misrepresented | Governance and control claims are untested |
| Synchronous immutable audit with risk-tier semantics | Artifacts written to S3, but bucket lacks Object Lock and stack uses destroy/autodelete semantics | Misrepresented | Compliance-grade audit posture is not represented |
| Private/no-direct-agent egress for tool path | Agent runtime network mode is `PUBLIC`; Jira base URL direct public endpoint | Misrepresented | Network isolation claims are overstated if inferred from this PoC |
| MCP path exists and is exercised through AgentCore Gateway | Gateway is deployed/READY and used by mcp flow in live runs | Accurate | Confirms PoC does test real AgentCore MCP integration |
| Native vs MCP route parity with same core task/model | Same dataset and run harness are used, but metric parity currently confounded by schema/drift issues | Partial | Comparative conclusions are directionally useful but not yet decision-grade |
| Deterministic metrics + diagnostics model | Refactored code and fresh outputs include `tool_match_rate`/`composite_reflection`/judge structures | Accurate | Good foundation for release-style evaluation once confounders are fixed |
| Contract governance across layers | Generated contract artifacts and semantic ownership checks exist and pass | Accurate | Refactor materially improved maintainability and drift prevention in source |
| Scheduler input respects required execution contract | Nightly EventBridge target omits required `expected_tool` | Misrepresented | Scheduled evidence can fail for configuration reasons, not behavior reasons |

## High-priority matrix notes

- The strongest current alignment is around tool contract governance and MCP gateway integration.
- The strongest current misalignments are around workflow-contract semantics, immutable audit posture, and network/security model.
- The current comparative eval signal is still useful, but not architecture-complete.

