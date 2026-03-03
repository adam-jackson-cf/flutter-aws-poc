# Handoff: Reconcile MCP Evaluation Path with Flutter Design and Validate Nova Both-Flow Adversarial Run

## Starting Prompt

Goal:
Align the PoC to a single, design-faithful MCP execution path (guided by Flutter architecture HTML docs), keep the adversarial benchmark meaningful, and then run a post-fix Nova both-flow adversarial eval with CloudWatch publishing.

Context and constraints:
- Treat Flutter HTML docs as the architectural source of truth:
  - docs/flutter-uki-ai-platform-arch/platform-narrative-v3.html
  - docs/flutter-uki-ai-platform-arch/view-orchestration-v5.html
  - docs/flutter-uki-ai-platform-arch/view-request-trace-v10.html
  - docs/flutter-uki-ai-platform-arch/view-security-identity-v7.html
  - docs/flutter-uki-ai-platform-arch/domain-model-v1.html
  - docs/flutter-uki-ai-platform-arch/component-design-v2.html
- Preserve adversarial testing intent (MCP call-construction fragility under scoped toolsets).
- Do not run full suites until path consistency is confirmed with targeted checks.
- Keep comparisons auditable with parity metadata and pricing snapshot.
- Continue using `.envrc`-based local config and Secrets Manager for API credentials.

What to do first:
1. Compare runtime vs lambda benchmark paths and document exact behavioral differences that affect fairness (tool selection, argument construction, retries, expected_tool handling, normalization).
2. Decide and implement one canonical MCP route behavior across benchmarked paths so the eval matches intended Flutter usage and removes mixed legacy assumptions.
3. Verify deterministic/native and MCP flows with small targeted cases (including write-tool and adversarial argument-bait cases).
4. Confirm eval output includes:
   - tool selection correctness
   - call-construction attempts/retries/failures
   - write-tool match metrics
   - token usage
   - estimated cost
   - model + pricing snapshot metadata
5. If targeted checks pass, run full adversarial both-flow with Nova and publish to CloudWatch.
6. Produce a concise results note focused on reliability, latency, token, and cost deltas plus top remaining failure reasons.

Definition of done:
- One consistent MCP evaluation path in active benchmark flow.
- Adversarial eval artifacts show the full metric set above.
- A fresh Nova both-flow adversarial run is available with CloudWatch metrics.
- README and bid companion docs describe only current architecture/behavior and current results.

## Relevant Files

- README.md
- evals/run_eval.py
- evals/aws_pipeline_runner.py
- evals/golden/sop_cases_adversarial.jsonl
- evals/model_pricing_usd_per_1m_tokens.json
- aws/lambda/fetch_mcp_stage.py
- aws/lambda/fetch_native_stage.py
- aws/lambda/tooling_domain.py
- aws/lambda/contract_values.py
- aws/lambda/runtime_config.py
- runtime/sop_agent/tools/jira_mcp_flow.py
- runtime/sop_agent/tools/strands_native_flow.py
- runtime/sop_agent/domain/contracts.py
- infra/lib/flutter-agentcore-poc-stack.ts
- docs/flutter-uki-ai-platform-arch/platform-narrative-v3.html
- docs/flutter-uki-ai-platform-arch/view-orchestration-v5.html
- docs/flutter-uki-ai-platform-arch/view-request-trace-v10.html
- docs/flutter-uki-ai-platform-arch/view-security-identity-v7.html
- docs/flutter-uki-ai-platform-arch/domain-model-v1.html
- docs/flutter-uki-ai-platform-arch/component-design-v2.html
- docs/references/bid-companion-2026-03-01/objective-validation-report.md
- docs/references/bid-companion-2026-03-01/alignment-misalignment-matrix.md

## Key Context

- The repo now has stronger parity controls and pricing/cost instrumentation, but there is still concern that mixed runtime-vs-lambda MCP behavior can confound conclusions.
- Current README states grounding is model-driven (not deterministic first-key extraction), and latest adversarial snapshot shows MCP worse than native on failure/latency/token/cost, but user concern remains that failure patterns may still be partially masked by implementation choices.
- Important contradiction to manage: objective is apples-to-apples process comparison, while provider/model comparisons (Nova vs GPT-5.2 Codex) are intentionally cross-model and should be treated as separate experiments from route-only parity tests.
- Pending execution intent from latest session: run a full Nova adversarial both-flow benchmark with CloudWatch publication after credential refresh, but only after route consistency checks are confirmed.
- Beneficial next improvement after this run: add a single explicit `execution_mode`/`mcp_binding_mode` field to all artifacts and CloudWatch dimensions to make route semantics auditable across runs.
