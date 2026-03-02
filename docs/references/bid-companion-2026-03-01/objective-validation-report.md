# Objective Validation Report (Current)

Date: 2026-03-02  
Region: `eu-west-1`  
Assessment basis: latest deployed stack and latest post-fix adversarial both-flow run.

## 1. Access/Auth and Deployment Preflight

- AWS identity preflight is passed in non-dry-run evaluations.
- Deployed execution path remains active for both routes (`native`, `mcp`).
- Run artifacts include model/runtime parity metadata and pricing snapshot metadata.

## 2. Latest Evidence Used

Primary run:
- `reports/runs/nova-adv-large-postfix-20260302T214400Z/eval/eval-both-route.json`

Supporting chart artifacts:
- `docs/references/bid-companion-2026-03-01/charts/latest-adversarial-route-comparison.md`
- `docs/references/bid-companion-2026-03-01/charts/latest-adversarial-route-comparison-kpis.json`
- `docs/references/bid-companion-2026-03-01/charts/latest-adversarial-route-comparison-kpis.csv`

## 3. Objective Verdicts

### Objective A
Surface MCP protocol tool-calling failure behavior versus native approaches.

Verdict: **MET (with bounded causality)**

What is validated in the latest run:
- Native: `tool_failure_rate=0.0000`, `business_success_rate=0.8571`
- MCP: `tool_failure_rate=0.0714`, `business_success_rate=0.8214`
- MCP call-construction pressure is non-zero and measurable:
  - `call_construction_failure_rate=0.0893`
  - `mean_call_construction_attempts=1.0893`
  - `call_construction_recovery_rate=0.2000`
- Efficiency deltas remain clear (`mcp - native`):
  - latency `+527.66ms`
  - mean LLM tokens `+389.05`
  - mean estimated cost `+0.00003475 USD`

Bounded interpretation:
- Current evidence shows persistent MCP interface penalties in this PoC.
- Protocol-only causality is still bounded by selector/prompt/tool-alias effects.

### Objective B
Test AgentCore CDK (alpha) implementation in a working PoC.

Verdict: **PARTIALLY MET**

What is validated:
- Deployed runtime/gateway/state-machine path executes the benchmark harness reliably.
- Contract and schema guardrails are active in quality gates and run-time validation.

What remains unvalidated:
- Full workflow-contract/HITL compensation semantics.
- Immutable audit and full identity-context governance path.

## 4. Current blocker profile

- MCP write-path alias mismatch remains the largest explicit failure family:
  - `selected_unknown_tool:jira_write_issue_followup_note` (4)
  - `selected_unknown_tool:jira-issue-tools___jira_create_comment` (4)
- Both routes pass deterministic gate, so blocker focus has shifted from baseline viability to targeted MCP hardening and architecture-conformance controls.
