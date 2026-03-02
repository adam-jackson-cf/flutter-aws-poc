# Expansion Experiment Backlog (Current)

Prioritization dimensions:
- Signal value: uncertainty removed for architecture and bid decisions.
- Effort: expected implementation + run effort.

## Priority backlog

| Priority | Experiment | Signal value | Effort | Acceptance criteria |
|---|---|---|---|---|
| P1 | MCP write-tool alias normalization (`jira_write_issue_followup_note` vs gateway-prefixed variants) | High | Low | Zero `selected_unknown_tool:*write*` failures in adversarial write vectors |
| P1 | MCP call-construction contract hardening (schema-aware corrective retry prompt) | High | Medium | `call_construction_failure_rate` reduced with no regression in native metrics |
| P1 | Selection divergence diagnostics | High | Medium | `selection_divergence_rate` traced to explicit cause families with remediation status |
| P2 | Cost/latency SLO pack | High | Medium | p50/p95 latency and cost-per-success available per flow and per adversarial vector |
| P2 | Fault-injection resilience drill (gateway unavailable, schema invalid, timeout) | Medium | Medium | Recovery behavior and retry envelopes are reproducible and evidenced |
| P3 | Workflow-contract + HITL tranche | High | High | End-to-end process-scope scenario including compensation/HITL evidence |
| P3 | Immutable audit and identity-context lineage tranche | High | High | Execution-level identity and immutable audit proofs included in artifacts |

## Suggested execution order (4-6 weeks)

1. Week 1: P1 alias + call-construction hardening and rerun adversarial both-flow benchmark.
2. Week 2: P1 divergence diagnostics plus P2 SLO pack publication.
3. Week 3: P2 resilience drill and evidence packaging.
4. Weeks 4-6: P3 architecture-conformance controls.
