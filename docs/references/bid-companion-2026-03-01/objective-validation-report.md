# Objective Validation Report (Post-Deploy Rebase)

Date: 2026-03-01  
Region: `eu-west-1`  
Assessment basis: latest deployed stack + live evaluation runs + current refactored source.

## 1. Access/Auth and Deployment Preflight

- AWS identity check passed (`sts:GetCallerIdentity`) in account `530267068969`.
- Target services available and healthy:
  - Step Functions state machine `ACTIVE`
  - AgentCore runtime `READY`
  - AgentCore gateway `READY`
- Nightly scheduler contract verified after deploy:
  - EventBridge target now includes required `expected_tool`.

## 2. Fresh Evidence Used

Primary post-deploy runs:
- Route run: `reports/runs/postdeploy-route-20260301T200250Z/eval/eval-both-route.json`
- Full run: `reports/runs/postdeploy-full-20260301T200729Z/eval/eval-both-full.json`

Supporting chart artifacts:
- `docs/references/bid-companion-2026-03-01/charts/postdeploy-comparison.md`
- `docs/references/bid-companion-2026-03-01/charts/postdeploy-comparison-kpis.json`
- `docs/references/bid-companion-2026-03-01/charts/postdeploy-comparison-kpis.csv`

Quality guard status:
- CI quality gates passed at commit time.
- New guardrails in place:
  - scheduler contract test (`expected_tool` present)
  - eval artifact schema fail-fast checks
  - MCP tool-name prefix normalization regression tests

## 3. Objective Verdicts

## Objective A
Surface MCP protocol tool-calling failure behavior versus native approaches.

Verdict: **PARTIALLY MET**

What is validated now:
- Comparative differential remains observable post-deploy.
  - Route run: native `tool_failure_rate=0.7000`, mcp `0.9333` (delta `+0.2333`)
  - Full run: native `0.7000`, mcp `0.9000` (delta `+0.2000`)
- MCP still underperforms native on key deterministic reliability metrics in this setup.

What changed from the previous (pre-deploy) analysis:
- Prior deployment/eval drift confounders were remediated (selection field drift now fail-fast instead of silent).
- Results now show both routes are currently weak, with MCP worse, rather than "native near-zero failures".

What still limits confidence:
- The experiment still bundles selector behavior + prompt/intake effects + interface effects.
- A protocol-only causality claim remains unsupported without ablation isolation.

## Objective B
Test AgentCore CDK (alpha) implementation in a working PoC.

Verdict: **PARTIALLY MET**

What is validated:
- Runtime, gateway, and state-machine resources deploy and run successfully.
- Post-deploy updates applied cleanly and resources remained operational.

What remains unvalidated:
- Structured alpha upgrade/rollback stress characterization.
- Production-governance behavior (R2/R3 workflow contract semantics, HITL, immutable audit) is still not represented by this PoC.

## 4. Status of Previously Raised Contradictions

1. Nightly `expected_tool` omission  
Status: **RESOLVED**

2. Deployed payload schema drift (`native_selection` absence)  
Status: **RESOLVED WITH FAIL-FAST GUARD**
- Eval now aborts with `artifact_schema_invalid:*` if deployed payload shape regresses.

3. MCP delimiter normalization (`___`)  
Status: **RESOLVED**
- Prefix handling now normalizes both `__` and `___` forms across runtime/lambda/eval paths.

## 5. New/Residual Concerns After Remediation

- Both routes have high wrong-tool selection rates on current dataset and scoring contract.
- MCP path shows additional gateway/catalog-related failure class (`mcp_gateway_unavailable:expected_gateway_tool_not_found:*`) in post-deploy runs.
- Comparative signal exists, but readiness signal is negative for both routes in current configuration.

## 6. Bid Narrative Recommendation (Updated)

Use this framing:

- The PoC now has materially better measurement integrity and contract enforcement than pre-deploy analysis.
- Current results indicate a reliability problem to solve, not just an MCP-vs-native ranking.
- Proposal should fund a focused optimization + ablation tranche before any architecture-level or protocol-level claims are treated as decision-grade.

