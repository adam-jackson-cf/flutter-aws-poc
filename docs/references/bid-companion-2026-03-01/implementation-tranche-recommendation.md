# Recommendation: Next Implementation Tranche (Top 3)

Date: 2026-03-02
Run source: `nova-adv-large-postfix-20260302T214400Z`

## Prioritized interventions

| Priority | Intervention | Why this is first | Expected impact (directional) | Test plan |
|---|---|---|---|---|
| 1 | Normalize MCP write-tool aliases and scoped naming map | Latest failures are concentrated in `selected_unknown_tool:*write*` (`8/112` MCP cases) | Remove dominant MCP failure family in current run | Add contract + stage tests for write aliases; rerun adversarial both-flow (`iterations=4`) and require zero write alias failures |
| 2 | Strengthen MCP call-construction corrective feedback on schema mismatch | MCP still has non-zero `call_construction_failure_rate` and retries | Reduce retries/failures and narrow latency/token gap | Add targeted vectors for wrong arg names/unknown args and require lower `call_construction_failure_rate` with no native regression |
| 3 | Add vector-level guardrails for high-divergence prompts | Selection divergence remains `12/112` and can hide brittle behavior | Improve tool consistency under adversarial phrasing | Track divergence by vector and require reduced divergence on rerun while preserving business success |

## Why this sequencing

- It addresses the largest currently observed MCP-specific failure cause first.
- It directly targets measurable deltas already present in deterministic metrics.
- It preserves current parity controls and keeps comparisons apples-to-apples.

## Explicit non-claim guard

- Do not claim full architecture conformance from this tranche.
- Do not claim protocol-only causality until alias and call-construction remediations are applied and rerun.
