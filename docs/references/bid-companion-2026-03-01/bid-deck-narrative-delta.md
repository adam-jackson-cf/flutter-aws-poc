# Bid Deck Narrative Snapshot (Current)

Date: 2026-03-02
Run source: `reports/runs/nova-adv-large-postfix-20260302T214400Z/eval/eval-both-route.json`

## What changed in the evidence position

- The PoC is now evaluated against a model-driven adversarial dataset that stresses grounding ambiguity and MCP call-construction fragility.
- Latest run uses parity-pinned model settings (`gateway_model_id == runtime_bedrock_model_id == eu.amazon.nova-lite-v1:0`).
- Both routes now pass deterministic release threshold in this benchmark, but MCP retains measurable penalties.

## Current narrative for the deck

Use this framing:

- "In the latest adversarial benchmark, both native and MCP routes clear deterministic release threshold, so the baseline is now operationally useful."
- "MCP remains weaker on execution efficiency and call-construction reliability: higher failure incidence, retries, latency, and token/cost consumption."
- "The next tranche should target MCP write-tool alias hardening and call-construction reliability while keeping model/runtime parity controls in place."

## KPI deltas to cite (`mcp - native`)

- `tool_failure_rate`: `+0.0714`
- `call_construction_failure_rate`: `+0.0893`
- `mean_latency_ms`: `+527.66`
- `mean_llm_total_tokens`: `+389.05`
- `mean_estimated_cost_usd`: `+0.00003475`
- `selection_divergence_rate`: `0.1071` (`12 / 112`)

## Claims to avoid

- Avoid claiming full Flutter architecture conformance from this PoC alone.
- Avoid attributing all residual gap to protocol alone; selector/prompt and tool-alias design still influence outcomes.
