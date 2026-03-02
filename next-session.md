# Handoff: Improve Native/MCP Failure Rates + 3-Model Benchmark

## Starting Prompt

Continue from commit `e8883cc` + `f13f992` with post-deploy evidence now in place.

Goal:
1. Discuss and define next implementation steps to reduce failure rates for both `native` and `mcp` routes.
2. Review and align the bid support deck narrative with the latest post-deploy findings.
3. Run a controlled 3-model comparison under identical conditions:
   - current default Bedrock model (`eu.amazon.nova-lite-v1:0`)
   - GPT-5
   - GPT-5 Codex High

Constraints:
- Keep region pinned to `eu-west-1`.
- Keep dataset, scope, iterations, and run conditions identical across all 3 runs.
- Do not claim protocol-only causality unless ablation/isolation evidence supports it.
- Preserve current quality gates and contract tests.

What to do first:
1. Reconfirm baseline from:
   - `reports/runs/postdeploy-route-20260301T200250Z/eval/eval-both-route.json`
   - `reports/runs/postdeploy-full-20260301T200729Z/eval/eval-both-full.json`
2. Review bid companion docs/charts and prepare a “narrative delta” for the bid support deck.
3. Validate model execution path for GPT-5 and GPT-5 Codex High:
   - check whether they are callable in current stack path (current code uses Bedrock runtime clients).
   - if not directly available, define minimal integration change needed while preserving run parity.
4. Execute 3 benchmark runs and generate updated comparison artifacts in `docs/references/bid-companion-2026-03-01/charts/`.
5. Propose prioritized engineering changes to reduce wrong-tool selection for both routes (native + mcp), with expected impact and test plan.

Output expected:
- Updated KPI JSON/CSV/MD charts for all 3 models.
- Short recommendation note for next implementation tranche (top 3 interventions).
- Bid support deck review note highlighting what changed in evidence and narrative.

## Relevant Files

- `README.md` — current operational notes and eval contract expectations.
- `docs/references/bid-companion-2026-03-01/objective-validation-report.md` — current post-deploy verdicts.
- `docs/references/bid-companion-2026-03-01/charts/postdeploy-comparison.md` — latest chart summary.
- `docs/references/bid-companion-2026-03-01/charts/postdeploy-comparison-kpis.json` — chart source metrics.
- `docs/references/bid-companion-2026-03-01/risk-register.md` — current residual risks.
- `evals/run_eval.py` — eval orchestration and output schema.
- `evals/aws_pipeline_runner.py` — artifact schema fail-fast validation.
- `aws/lambda/runtime_config.py` — model/region override path (`model_id`, `bedrock_region`).
- `aws/lambda/fetch_native_stage.py` — native tool-selection flow.
- `aws/lambda/fetch_mcp_stage.py` — MCP tool-selection flow.
- `aws/lambda/tooling_domain.py` and `runtime/sop_agent/domain/tooling.py` — tool-name normalization logic (`__` / `___`).
- `infra/lib/flutter-agentcore-poc-stack.ts` — scheduler contract (`expected_tool`) and runtime config.

## Key Context

- Previously identified drift issues were fixed:
  - Nightly scheduler now includes `expected_tool`.
  - Eval now fails fast on artifact schema drift (`artifact_schema_invalid:*`).
  - MCP delimiter normalization fixed for both `__` and `___`.
- Post-deploy runs are now the authoritative baseline:
  - route run id: `postdeploy-route-20260301T200250Z`
  - full run id: `postdeploy-full-20260301T200729Z`
- Current reliability is still poor for both paths (mcp worse than native), so next work should focus on reducing wrong-tool selection and isolating causes.
- Historical assessment file is retained only for traceability:
  - `docs/references/flutter-agentcore-poc-architecture-assessment-2026-03-01.md`
