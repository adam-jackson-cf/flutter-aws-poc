# Recommendation: Next Implementation Tranche (Top 3)

Date: 2026-03-01

## Prioritized interventions

| Priority | Intervention | Why this is first | Expected impact (directional) | Test plan |
|---|---|---|---|---|
| 1 | Add deterministic tool-selection contract enforcement in selection stage | The dominant failure class in both routes remains wrong-tool selection (`*_get_issue_by_key` over-selection and status-snapshot confusion). | Reduce wrong-tool errors by ~20-35% relative from current baseline by rejecting out-of-contract choices and forcing one constrained retry. | Add unit tests for selector output validation + retry behavior, then run route eval (`iterations=3`) and compare failure reason counts before/after. |
| 2 | Strengthen intent-to-tool disambiguation prompt with explicit negative examples | Current intent classes (`status_update`, `feature_request`, `bug_triage`) still collide on tool choice even with scoped catalogs. | Improve `tool_match_rate` by ~10-20 points on both routes if ambiguity is reduced in first-pass selection. | Add deterministic fixtures per intent pair conflict, replay full golden set, and require non-regression in `tool_match_rate` + `business_success_rate`. |
| 3 | Add MCP catalog preflight assertion for required tools per intent before selection | MCP still emits gateway-availability failures (`expected_gateway_tool_not_found`) and remains worse than native. | Remove avoidable MCP-specific catalog misses and reduce false protocol-attribution risk. | Introduce catalog-coverage contract test against required intent scopes, fail fast pre-selection, rerun route eval and confirm zero catalog-missing failures. |

## Why this sequencing

- It targets the highest-volume failure mode first.
- It improves both routes before protocol-specific claims.
- It preserves current quality/contract gate posture and uses the existing eval harness for verification.

## Explicit non-claim guard

- Do not claim MCP protocol causality from current data.
- Only claim protocol-level effects after ablation controls isolate selector/prompt changes from transport/interface changes.
