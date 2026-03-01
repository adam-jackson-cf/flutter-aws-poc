# Objective Validation Report (Rebased)

Date: 2026-03-01  
Scope: Post-refactor reassessment of Flutter AgentCore PoC against current repository + live AWS evidence in `eu-west-1`.

## 1. Access/Auth Preflight Outcome

- Credential status: valid at assessment time (`sts:GetCallerIdentity` succeeded).
- Active account/role: `530267068969` / `AWSReservedSSO_StandardAdmin_ff8ffd06b2aab23a`.
- Region pinning: all live checks and runs executed with `eu-west-1`.
- Required service probes: passed.
  - Step Functions state machine: `ACTIVE`.
  - AgentCore runtime: `READY`.
  - AgentCore gateway: `READY`.
  - Artifacts bucket: readable.

Conclusion: sufficient access rights were available for read and evaluation execution activities used in this report.

## 2. Fresh Evidence Regeneration

Regenerated on refactored repo using deployed pipeline:

- Route run (both flows, 2 iterations):  
  `reports/runs/rebased-live-route-20260301T193550Z/eval/eval-both-route.json`
- Full run (both flows, 1 iteration):  
  `reports/runs/rebased-live-full-20260301T193821Z/eval/eval-both-full.json`

Validation checks run locally on refactored code:

- `python3 -m pytest -q tests/test_evals_run_eval_full.py tests/test_metrics.py tests/test_metrics_edges.py tests/test_dataset_schema.py tests/test_tool_contract_snapshot.py`
- Result: `27 passed`.
- Architecture/contract quality checks:
  - `scripts/check-architecture-boundaries.py` passed.
  - `scripts/check-semantic-contract-ownership.py` passed.

## 3. Objective Verdicts

## Objective A
Surface MCP protocol tool-calling failure behavior versus native approaches.

Verdict: **PARTIALLY MET (with confounders)**

What is validated:
- Fresh route evidence still shows materially higher MCP tool-failure than native in this setup.
  - Route run: native `tool_failure_rate=0.0` vs mcp `tool_failure_rate=0.6`.
  - Full run: native `0.0` vs mcp `0.6`.
- Failure classes are explicit (`selected_wrong_tool:*`).

What limits confidence:
- Native eval path now reports `tool_match_rate=0.0` and `business_success_rate=0.0` despite artifact `run_metrics.business_success=True` in sampled native artifacts.
- Native artifacts from deployed pipeline do not contain `native_selection`, but current local refactored source expects this field to exist in persisted event payload.
- MCP wrong-tool classification includes delimiter-parsing edge cases (`jira-issue-tools___...`) that can label matches as mismatches.

Net: MCP-vs-native differential is still observable, but current measured effect is confounded by evaluation/schema/deployment drift and name-normalization behavior.

## Objective B
Test AgentCore CDK (alpha) implementation in a working PoC.

Verdict: **PARTIALLY MET**

What is validated:
- PoC deploys and runs real AgentCore alpha resources from CDK:
  - `AWS::BedrockAgentCore::Runtime`
  - `AWS::BedrockAgentCore::Gateway`
- Deployed resources are live (`READY`) and actively used by evaluation flow.
- Gateway protocol config and IAM authorizer are active.

What remains unvalidated:
- Alpha behavior under change/rollback pressure is not deeply characterized in this repo evidence set.
- No systematic evidence yet for failure handling at workflow-contract/HITL/compensation level tied to alpha platform behavior.

Net: PoC proves baseline deployability and runtime usage of AgentCore alpha constructs, but not production-grade operational confidence.

## 4. Stale Artifact Delta (Prior vs Current)

Compared prior artifacts (`reports/eval-comparison-live*.json`, `reports/runs/20260227T220500Z/...`) to fresh runs:

- Prior outputs missing current schema fields (`tool_match_rate`, `judge_summary`, `composite_reflection`).
- Fresh outputs include those fields, but reveal new consistency issues:
  - Native `tool_match_rate=0.0` and `business_success_rate=0.0` in eval summary while sampled artifact `run_metrics` indicate native business success.
- Prior conclusion "native business_success high" is now not directly reproducible from current eval pipeline output without resolving schema/path consistency.

Bid implication:
- Do not present older reports as directly comparable to current schema/results.
- Include run IDs and schema version context with any chart in proposal material.

## 5. Critical Contradictions and Knock-on Effects

1. Scheduled input contract contradiction:
- Deployed EventBridge nightly target omits `expected_tool`.
- Pipeline stages enforce `expected_tool` as required.
- Effect: scheduled runs can fail deterministically for contract reasons, contaminating trend signals.

2. Deployed/runtime drift contradiction:
- Local refactored code shape and deployed artifact payload shape are not fully aligned (`native_selection` absence in sampled native artifacts).
- Effect: eval metrics understate/misstate native path quality and weaken A/B fairness claims.

3. MCP name-normalization contradiction:
- Tool-name prefix normalization currently treats `__` delimiter while observed gateway names include `___` prefix pattern.
- Effect: false positives in wrong-tool classification and suppressed `tool_match_rate`.

## 6. Immediate Decision Guidance for Bid Narrative

Use this framing:

- The PoC currently validates that MCP-path routing reliability issues are observable in practice.
- The PoC does not yet validate full Flutter architecture contract behavior (identity propagation, risk-tier workflow contract, fail-closed audit semantics).
- A short follow-on validation tranche is required to remove confounders before claiming architecture-level comparative conclusions.

