# Evidence Index (Current)

## Source anchors

- Stack and deployment topology: `infra/lib/flutter-agentcore-poc-stack.ts`
- Eval harness + schema expectations: `evals/run_eval.py`, `evals/metrics.py`, `evals/aws_pipeline_runner.py`
- Stage contracts: `runtime/sop_agent/stages/fetch_native_stage.py`, `runtime/sop_agent/stages/fetch_mcp_stage.py`, `runtime/sop_agent/stages/evaluate_stage.py`
- Runtime workflow stages: `runtime/sop_agent/stages/parse_stage.py`, `runtime/sop_agent/stages/fetch_native_stage.py`, `runtime/sop_agent/stages/fetch_mcp_stage.py`, `runtime/sop_agent/stages/generate_stage.py`, `runtime/sop_agent/stages/evaluate_stage.py`
- Contract governance checks: `scripts/check-architecture-boundaries.py`, `scripts/check-semantic-contract-ownership.py`

## Design anchors

- `docs/flutter-uki-ai-platform-arch/architecture-overview-v9.html`
- `docs/flutter-uki-ai-platform-arch/view-orchestration-v5.html`
- `docs/flutter-uki-ai-platform-arch/view-security-identity-v7.html`
- `docs/flutter-uki-ai-platform-arch/view-request-trace-v10.html`
- `docs/flutter-uki-ai-platform-arch/component-design-v2.html`

## Latest run artifact used for conclusions

- `reports/runs/nova-adv-large-postfix-20260302T214400Z/eval/eval-both-route.json`

## Current chart artifacts

- `docs/references/bid-companion-2026-03-01/charts/latest-adversarial-route-comparison.md`
- `docs/references/bid-companion-2026-03-01/charts/latest-adversarial-route-comparison-kpis.json`
- `docs/references/bid-companion-2026-03-01/charts/latest-adversarial-route-comparison-kpis.csv`

## Decision notes

- `docs/references/bid-companion-2026-03-01/executive-brief.md`
- `docs/references/bid-companion-2026-03-01/objective-validation-report.md`
- `docs/references/bid-companion-2026-03-01/implementation-tranche-recommendation.md`
- `docs/references/bid-companion-2026-03-01/risk-register.md`
