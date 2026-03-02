# Evidence Index (Post-Deploy)

## Refactored source anchors

- Stack and deployment topology: `infra/lib/flutter-agentcore-poc-stack.ts`
- Eval harness + schema expectations: `evals/run_eval.py`, `evals/metrics.py`, `evals/aws_pipeline_runner.py`
- Stage contracts: `aws/lambda/fetch_native_stage.py`, `aws/lambda/fetch_mcp_stage.py`, `aws/lambda/evaluate_stage.py`
- Runtime tool flows: `runtime/sop_agent/tools/strands_native_flow.py`, `runtime/sop_agent/tools/jira_mcp_flow.py`
- Contract governance checks: `scripts/check-architecture-boundaries.py`, `scripts/check-semantic-contract-ownership.py`

## Design anchors

- `docs/flutter-uki-ai-platform-arch/architecture-overview-v9.html`
- `docs/flutter-uki-ai-platform-arch/view-orchestration-v5.html`
- `docs/flutter-uki-ai-platform-arch/view-security-identity-v7.html`
- `docs/flutter-uki-ai-platform-arch/view-request-trace-v10.html`
- `docs/flutter-uki-ai-platform-arch/component-design-v2.html`

## Current local run artifacts used for conclusions (workspace snapshot)

- `reports/runs/nova20-write-retry-final-20260302T114512Z/eval/eval-both-route.json`

## Historical 2026-03-01 run evidence in this repo snapshot

- Narrative and KPI summaries remain in:
  - `docs/references/bid-companion-2026-03-01/objective-validation-report.md`
  - `docs/references/bid-companion-2026-03-01/charts/postdeploy-comparison.md`
  - `docs/references/bid-companion-2026-03-01/charts/postdeploy-comparison-kpis.json`
  - `docs/references/bid-companion-2026-03-01/charts/postdeploy-comparison-kpis.csv`

## Chart artifacts

- `docs/references/bid-companion-2026-03-01/charts/postdeploy-comparison.md`
- `docs/references/bid-companion-2026-03-01/charts/postdeploy-comparison-kpis.json`
- `docs/references/bid-companion-2026-03-01/charts/postdeploy-comparison-kpis.csv`
- `docs/references/bid-companion-2026-03-01/charts/three-model-route-comparison.md`
- `docs/references/bid-companion-2026-03-01/charts/three-model-route-comparison-kpis.json`
- `docs/references/bid-companion-2026-03-01/charts/three-model-route-comparison-kpis.csv`

## Decision notes

- `docs/references/bid-companion-2026-03-01/bid-deck-narrative-delta.md`
- `docs/references/bid-companion-2026-03-01/implementation-tranche-recommendation.md`

## Historical snapshots retained for traceability

- `docs/references/flutter-agentcore-poc-architecture-assessment-2026-03-01.md`
- `docs/references/flutter-agentcore-poc-architecture-assessment-2026-03-01-rebased.md`

## Live AWS probe classes executed

- STS identity check (`aws sts get-caller-identity`) in `eu-west-1`
- Step Functions state machine status/definition inspection
- EventBridge nightly rule target inspection
- AgentCore runtime and gateway status/details inspection
- S3 Object Lock configuration check on artifact bucket
- Lambda function metadata inspection (LastModified/CodeSha256)
