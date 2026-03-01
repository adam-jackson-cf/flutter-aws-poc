# Risk Register (Post-Deploy)

Scale:
- Severity: `Low` / `Medium` / `High` / `Critical`
- Likelihood: `Low` / `Medium` / `High`

| ID | Risk | Severity | Likelihood | Evidence | Mitigation |
|---|---|---|---|---|---|
| R-01 | Scheduler contract regression (`expected_tool`) reappears in future edits | Medium | Low | Nightly target now includes `expected_tool`; guard test exists | Keep scheduler contract test mandatory in CI; add stack-level synth assertion if needed |
| R-02 | Eval payload schema drift silently corrupts comparative metrics | Medium | Low | Eval now fails fast on missing flow-specific selection payloads | Keep `artifact_schema_invalid:*` hard fail behavior; document runbook recovery path |
| R-03 | MCP prefix/normalization regression causes false wrong-tool scoring | Medium | Low | `___` and `__` handling now covered by tests across runtime/lambda/eval | Keep normalization tests as required gate; avoid ad-hoc delimiter parsing elsewhere |
| R-04 | Architecture claims remain overstated vs Flutter target (workflow contract/HITL/audit semantics) | High | High | Current state machine still lacks R2/R3 workflow-contract semantics and HITL branches | Scope claims explicitly; deliver dedicated R2/R3 conformance tranche |
| R-05 | Public runtime network posture conflicts with enterprise security narrative | High | Medium | AgentCore runtime still `PUBLIC`; public Jira egress retained | Define private-network target architecture and migration plan |
| R-06 | Audit retention posture not compliance-ready | High | Medium | No Object Lock compliance mode in current artifact path | Separate transient eval artifacts from immutable audit store |
| R-07 | Alpha CDK operational risk under upgrade/rollback scenarios under-tested | Medium | Medium | Deploy/update works, but no structured rollback drill evidence | Add upgrade/diff/rollback drill pack with measured recovery outcomes |
| R-08 | Reliability remains low in both routes, reducing confidence for production adoption | Critical | High | Post-deploy route run: native failure `0.7000`, mcp `0.9333`; full run: native `0.7000`, mcp `0.9000` | Execute optimization + ablation tranche before architecture sign-off |
| R-09 | MCP-specific gateway/catalog failure class persists (`expected_gateway_tool_not_found`) | High | Medium | Seen in post-deploy mcp failures (`mcp_gateway_unavailable:*`) | Add intent-to-tool-scope diagnostics and catalog coverage tests |

## Risk ownership recommendation

- Platform engineering: R-01, R-02, R-03, R-07, R-08, R-09
- Security/governance: R-04, R-05, R-06
- Delivery/proposal lead: R-04, R-08

