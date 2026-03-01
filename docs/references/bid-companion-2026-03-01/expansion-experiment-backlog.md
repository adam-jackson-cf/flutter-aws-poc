# Expansion Experiment Backlog

Prioritization dimensions:
- Signal value: how much uncertainty it removes for bid/proposal decision.
- Effort: expected implementation + run effort.

| Priority | Experiment | Signal value | Effort | Acceptance criteria |
|---|---|---|---|---|
| P1 | Scheduler input contract hardening | High | Low | Nightly input includes `expected_tool`; CI test fails on omission |
| P1 | Artifact schema lock test between deployed payload and eval parser | High | Medium | Eval run aborts early if required keys for selected flow are absent or shape-mismatched |
| P1 | MCP/native fairness harness (same prompts, pinned run config, repeated runs) | High | Medium | Repeated runs produce stable confidence intervals for key KPIs; run metadata captured |
| P1 | Tool-name normalization hardening for gateway prefixes (`___`, `__`, target prefixes) | High | Low | Wrong-tool false positives removed; regression tests cover observed gateway naming patterns |
| P1 | Unconfounded ablation matrix: native direct vs MCP deterministic-call vs MCP model-selection | High | Medium | Separate effect sizes reported for transport overhead and selector error |
| P2 | Failure taxonomy expansion (timeout, malformed schema, gateway unavailable, auth drift, throttling) | High | Medium | Distinct error families emitted and reported with per-family rates |
| P2 | Resilience drills with controlled fault injection | Medium | Medium | Recovery behavior measured (retry amplification, fail mode, user-visible outcome) |
| P2 | Operational SLO/cost pack (p50/p95/p99 latency, success, retry rate, cost-per-success/failure) | High | Medium | Single dashboard/report section with run ID and confidence bands |
| P2 | AgentCore alpha change-management drill (diff/deploy/rollback) | Medium | Medium | Documented upgrade path, rollback time, and breakpoints for proposal risk section |
| P3 | R2/R3 orchestration pattern extension (workflow contract, compensation, HITL checkpoints) | High | High | End-to-end Process-scope scenario with explicit contract artifacts and replay/compensation evidence |
| P3 | Identity/governance observability pack (session-tag lineage, ABAC decisions, scoped-token traces) | High | High | Per-execution trace includes identity context propagation and policy decision points |
| P3 | Audit immutability tiered storage (transient eval vs compliance audit) | High | High | Compliance-mode audit path validated separately from transient experiment artifacts |

## Suggested execution order (4-6 weeks)

1. Week 1: P1 contract and schema correctness (remove confounders first).
2. Week 2: P1 fairness + ablation runs; publish updated comparative truth.
3. Week 3: P2 operational/resilience evidence.
4. Weeks 4-6: P3 architecture-contract validation (workflow/identity/audit).

## Additional critique-worthy expansion not previously requested

- Add deployment parity checks that compare local commit SHA, deployed Lambda code SHA, and report run metadata before every evaluation run.  
  Value: prevents future "analysis on one version, execution on another" drift and significantly improves bid credibility.

