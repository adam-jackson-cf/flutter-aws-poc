# Expansion Experiment Backlog (Post-Deploy)

Prioritization dimensions:
- Signal value: how much uncertainty it removes for bid/proposal decision.
- Effort: expected implementation + run effort.

## Completed Since Rebased Plan

- Scheduler input contract hardening (`expected_tool`) deployed.
- Eval artifact schema lock added (fail-fast on flow-specific payload drift).
- Tool-name normalization hardening for gateway prefixes (`__`, `___`) implemented and tested.

## Remaining Backlog

| Priority | Experiment | Signal value | Effort | Acceptance criteria |
|---|---|---|---|---|
| P1 | MCP/native fairness harness with seeded repeats and run metadata lock | High | Medium | Repeated runs produce stable confidence intervals for key KPIs |
| P1 | Unconfounded ablation matrix: native direct vs MCP deterministic-call vs MCP model-selection | High | Medium | Effect sizes separated for transport overhead vs selector error |
| P1 | Intent-to-tool-scope diagnostics for gateway expected-tool-not-found failures | High | Medium | Failures attributable to specific intent/catalog mismatch causes |
| P2 | Failure taxonomy expansion (timeout, malformed schema, gateway unavailable, auth drift, throttling) | High | Medium | Distinct error families emitted and tracked per flow |
| P2 | Operational SLO/cost pack (p50/p95/p99 latency, success, retry rate, cost-per-success/failure) | High | Medium | One report section with run IDs and confidence bands |
| P2 | Resilience drills with controlled fault injection | Medium | Medium | Recovery behavior measured and replayable |
| P2 | AgentCore alpha change-management drill (diff/deploy/rollback) | Medium | Medium | Measured rollback and recovery envelope documented |
| P3 | R2/R3 orchestration extension (workflow contract, compensation, HITL checkpoints) | High | High | End-to-end Process-scope scenario with explicit contract evidence |
| P3 | Identity/governance observability pack (session-tag lineage, ABAC decisions, scoped-token traces) | High | High | Per-execution trace shows identity and policy decision chain |
| P3 | Audit immutability tiered storage (transient eval vs compliance audit) | High | High | Compliance-mode audit path validated separately from transient store |

## Suggested execution order (4-6 weeks)

1. Week 1: P1 ablation + fairness harness + gateway scope diagnostics.
2. Week 2: P2 operational/failure taxonomy and resilience evidence.
3. Week 3: P2 alpha change-management drill.
4. Weeks 4-6: P3 architecture conformance evidence.

## Additional proposal-strengthening recommendation

- Add deployment parity checks that compare local commit SHA, deployed Lambda code SHA, and run metadata before every evaluation run.  
  Value: prevents analysis/deployment skew and raises review confidence.

