# PoC Approach: DSPy + GEPA + Capability Definition + MCP Validation

## Purpose
Define a practical, low-friction PoC approach that:

1. Identifies one concrete use case and builds a golden dataset.
2. Uses DSPy + GEPA to optimize agent system prompt behavior against that dataset.
3. Publishes the resulting agent capability into the Flutter marketplace.
4. Quantifies MCP Tool Gateway reliability and cost impacts when models construct tool payloads.

## Why DSPy + GEPA fits Flutter's architecture

1. Flutter already treats system prompts as versioned and immutable at publish, so optimized prompts can be treated as governed build artifacts.
2. Flutter already requires evaluation evidence before publish, which matches DSPy optimization and validation loops.
3. Marketplace distribution already assumes versioned capability artifacts; DSPy outputs fit naturally into that lifecycle.
4. MCP tool calls are model-driven, so prompt optimization directly targets tool selection and argument quality, where cost and failure risk concentrate.
5. Runtime governance controls (ABAC, RFC 8693, audit) remain in Flutter's platform layer; DSPy improves quality without weakening platform controls.

## Recommended PoC flow

1. Choose one R1 use case first to exercise tool calling while avoiding R2/R3 workflow overhead in the first iteration.
2. Build a golden dataset with strong coverage of normal, edge, and failure-prone scenarios.
3. Implement baseline agent behavior and benchmark on held-out test data.
4. Run DSPy + GEPA optimization on train/validation splits only.
5. Re-run benchmark on untouched test split and compare quality, reliability, and cost.
6. Package optimized prompt and evidence into Capability Definition metadata.
7. Publish to marketplace through Flutter lifecycle gates.
8. Run post-publish MCP experiments in staging/controlled production traffic.

## Golden dataset design

### Use-case selection criteria

1. Requires at least one MCP tool call.
2. Has clear expected outcome and measurable success criteria.
3. Includes moderate ambiguity so prompt quality materially matters.
4. Can be evaluated without legal or privacy blockers.

### Example dataset schema

| Field | Purpose |
| --- | --- |
| `example_id` | Stable identifier |
| `tenant_id`, `brand`, `risk_tier` | Context constraints |
| `user_input` | Prompt text |
| `conversation_context` | Prior turns, if relevant |
| `allowed_tools` | Tool scope for the test case |
| `expected_tool_plan` | Expected tool(s) and sequence |
| `expected_tool_args` | Canonical argument payload(s) |
| `expected_response` | Reference response intent/content |
| `policy_labels` | Safety/compliance tags |
| `cost_budget` | Token/tool call budget guardrails |
| `score_rubric` | Deterministic scoring criteria |

### Dataset composition

1. Normal path examples.
2. Ambiguous intent examples.
3. Missing/partial input examples.
4. Adversarial and prompt-injection-like examples.
5. Tool schema edge cases (enums, nested args, date/time formats, ranges).
6. Multi-step state carryover examples to catch stale argument issues.

### Splits

1. `train`: optimization only.
2. `val`: optimizer selection and tuning.
3. `test`: untouched until final comparison.

## DSPy + GEPA optimization workflow

1. Define DSPy program signature for response and tool behavior.
2. Define composite metric function that scores:
   1. Outcome correctness.
   2. Tool argument validity.
   3. Policy compliance.
   4. Cost efficiency.
3. Run baseline on validation and test.
4. Run GEPA optimization (`compile`) on train/validation.
5. Freeze optimized prompt candidate and compare against baseline on test.
6. Keep optimization run metadata for reproducibility.

## Capability Definition integration pattern

Keep DSPy runtime in agent development environment. Deploy only finalized artifacts and evidence.

### Proposed metadata extension (conceptual)

```json
{
  "prompt_optimization": {
    "method": "dspy_gepa",
    "optimizer_version": "x.y.z",
    "prompt_artifact_ref": "s3://.../system_prompt.txt",
    "prompt_artifact_sha256": "....",
    "dataset_hashes": {
      "train": "....",
      "val": "....",
      "test": "...."
    },
    "metric_version": "v1",
    "optimization_run_id": "run-....",
    "tool_schema_snapshot_hash": "....",
    "evaluation_report_ref": "s3://.../eval-report.json"
  }
}
```

### Publish gate checks

1. Prompt artifact hash present and immutable.
2. Dataset and metric versions pinned.
3. Test-set performance threshold met.
4. Cost and failure thresholds met.
5. Tool schema snapshot matches release schema.

## MCP Gateway experiment framework

### Goal

Quantify governance-vs-cost tradeoff under model-generated tool payloads.

### Experiment axes

1. Schema complexity: simple to deeply nested payloads.
2. Context size: compact descriptors vs larger schema context.
3. Multi-step depth: single call vs chained calls.
4. Retry policy: model-only retries vs hybrid deterministic normalization.
5. Model/provider variation.
6. Traffic profile: low concurrency vs burst.

### Core metrics

1. `invalid_params_rate = invalid_params_calls / total_tool_calls`
2. `auto_recover_rate = recovered_failures / total_failures`
3. `stale_argument_rate = stale_argument_failures / multi_step_tool_calls`
4. `tool_success_rate = successful_tool_calls / total_tool_calls`
5. `retry_cost_overhead = (retry_tokens + retry_tool_calls_cost) / successful_executions`
6. `cost_per_successful_execution`
7. `p95_tool_call_latency`
8. `p95_end_to_end_latency`

### Useful outputs

1. Thresholds by risk tier.
2. Trigger point for adding deterministic argument normalization.
3. Cost impact curve as failure rates rise.

## Minimal-complexity recommendation

1. Keep DSPy + GEPA as offline optimization and evaluation tooling.
2. Keep Flutter runtime path unchanged: Capability Definition + Registry + MCP + Guardrails + Audit.
3. Publish optimized prompt plus evidence as versioned artifacts.
4. Treat marketplace performance monitoring as post-publish governance, not live prompt training.

## Risks and mitigations

1. Tool schema drift can invalidate optimized prompt behavior.
   1. Mitigation: pin schema snapshot hash and trigger retraining on schema changes.
2. Optimization can improve quality while increasing cost.
   1. Mitigation: include cost penalty in objective function.
3. Cross-tenant distribution shift can reduce marketplace transferability.
   1. Mitigation: include cross-tenant examples in validation/test.
4. Overfitting to narrow golden data can hide production failure modes.
   1. Mitigation: keep adversarial and out-of-distribution slices in test set.

## Immediate next actions

1. Select one R1 PoC use case with at least one MCP tool call.
2. Draft v1 golden dataset schema and sampling plan.
3. Define v1 scoring rubric and pass thresholds.
4. Build baseline agent and benchmark.
5. Run GEPA optimization and produce delta report.
6. Publish as marketplace candidate with pinned artifacts and monitor MCP metrics.
