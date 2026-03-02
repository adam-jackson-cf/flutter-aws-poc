# Risk Register (Current)

Scale:
- Severity: `Low` / `Medium` / `High` / `Critical`
- Likelihood: `Low` / `Medium` / `High`

| ID | Risk | Severity | Likelihood | Current evidence | Mitigation |
|---|---|---|---|---|---|
| R-01 | Scheduler contract regression (`expected_tool`) reappears | Medium | Low | Guard test enforces scheduler contract | Keep scheduler contract test mandatory in CI |
| R-02 | Eval payload schema drift corrupts metrics | Medium | Low | Artifact schema fail-fast checks are active | Keep `artifact_schema_invalid:*` hard fail behavior |
| R-03 | Tool-prefix normalization regression causes false mismatch scoring | Medium | Low | Prefix handling tests exist across lambda/runtime/eval layers | Keep normalization tests as required quality gate |
| R-04 | MCP write-tool alias mismatch persists | High | High | Latest run has 8 MCP failures from unknown write tools | Add alias normalization and scoped mapping for write tools |
| R-05 | MCP call-construction retries inflate latency and cost | High | Medium | `call_construction_failure_rate=0.0893`, latency and token deltas remain positive | Strengthen schema-aware retry feedback and argument validation prompts |
| R-06 | Architecture claims overstated vs Flutter target (workflow contract/HITL/immutable audit) | High | High | Current PoC still lacks these controls end-to-end | Keep claims scoped; execute dedicated conformance tranche |
| R-07 | Public runtime network posture conflicts with enterprise security narrative | High | Medium | Runtime remains `PUBLIC`; Jira over public egress | Define private-network target and migration plan |
| R-08 | Identity-context observability remains partial | Medium | Medium | No full ABAC lineage trace in run artifacts | Add identity-context decision trace instrumentation |
| R-09 | Comparative parity drift between gateway/runtime model settings | Medium | Low | Parity metadata now recorded per run | Enforce parity checks in pre-run validation and review |

## Risk ownership recommendation

- Platform engineering: R-01, R-02, R-03, R-04, R-05, R-09
- Security/governance: R-06, R-07, R-08
- Delivery/proposal lead: R-04, R-05, R-06
