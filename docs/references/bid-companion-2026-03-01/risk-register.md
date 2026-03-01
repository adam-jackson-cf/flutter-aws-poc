# Risk Register

Scale:
- Severity: `Low` / `Medium` / `High` / `Critical`
- Likelihood: `Low` / `Medium` / `High`

| ID | Risk | Severity | Likelihood | Evidence | Mitigation |
|---|---|---|---|---|---|
| R-01 | Scheduler contract break (`expected_tool` missing) causes deterministic failed scheduled runs | High | High | Deployed EventBridge target input omits `expected_tool`; pipeline stages require it | Add `expected_tool` in nightly target; add scheduler-contract test; fail fast in preflight |
| R-02 | Eval signal confounded by deployed schema drift (`native_selection` absent in native artifacts) | Critical | High | Native summary shows `business_success_rate=0.0` with `tool_failure_rate=0.0`; sampled artifact `run_metrics.business_success=True` | Re-deploy refactored stack; add artifact schema assertion in eval harness; block report publication if schema mismatch |
| R-03 | MCP wrong-tool rates inflated by delimiter normalization edge (`___`) | High | Medium | Observed selected tools with `jira-issue-tools___...`; wrong-tool includes cases where suffix equals expected | Harden tool-name normalization (`___` + `__` + prefix mapping); add regression tests on gateway name forms |
| R-04 | Architecture claims overstated versus Flutter design (workflow contract/HITL/audit semantics) | High | High | Current state machine lacks compensation/HITL and risk-tier branching; audit retention not immutable | Scope claims explicitly to route-reliability experiment; implement R2/R3 workflow contract tranche before production claims |
| R-05 | Public network runtime conflicts with enterprise security narrative | High | Medium | AgentCore runtime `networkMode=PUBLIC`; public Jira egress | Add private networking path (where supported), controlled egress policy, and explicit exception rationale in proposal |
| R-06 | Artifact retention posture not compliance-ready | High | Medium | S3 bucket has no Object Lock and stack destroy/autodelete semantics | Separate immutable audit store from transient eval store; enable Object Lock in compliance tier |
| R-07 | Alpha CDK operational risk under change pressure not fully characterized | Medium | Medium | Alpha constructs are used and running, but no structured upgrade/rollback drill evidence | Add upgrade/diff/rollback drills and capture time-to-recover, breakpoints, and mitigations |
| R-08 | Proposal reviewers challenge causality of MCP-vs-native conclusions | High | Medium | Comparison currently bundles protocol + selector + naming effects | Run ablation matrix isolating transport vs selector behavior and publish confidence intervals |

## Risk ownership recommendation

- Platform engineering: R-01, R-02, R-03, R-06, R-07
- Security/governance: R-04, R-05, R-06
- Delivery/proposal lead: R-04, R-08

