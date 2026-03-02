# Bid Support Deck: Narrative Delta (Post 3-Model Attempt)

Date: 2026-03-01

## What changed in evidence

1. Controlled rerun under pinned conditions completed for current default model (`eu.amazon.nova-lite-v1:0`) with route scope parity preserved.
2. Requested GPT-5 and GPT-5 Codex High runs were attempted in the same path and failed immediately with Bedrock `ValidationException` (`provided model identifier is invalid`).
3. Bedrock model probe in `eu-west-1` did not show GPT-5/Codex entries; OpenAI GPT-OSS variants are available instead.

## Narrative update for deck

Use this updated framing:

- "We completed a controlled benchmark harness run and confirmed reliability remains weak for both routes under the current default model, with MCP still worse than native."
- "We attempted the planned GPT-5 and GPT-5 Codex High comparison in the same execution path, but those identifiers are not currently executable in the pinned Bedrock region/path."
- "The next decision-critical step is provider-path enablement (or approved equivalent model substitution) plus a rerun of identical benchmark conditions."

## KPI deltas to cite (default model rerun vs previous post-deploy route)

- Native `tool_failure_rate`: unchanged at `0.7000`.
- MCP `tool_failure_rate`: `0.9333 -> 0.9000` (still materially worse than native).
- MCP minus native latency delta: `+307.88ms -> +364.93ms`.

## Claims to avoid

- Avoid any statement that protocol/interface is the sole cause of reliability gaps.
- Avoid implying GPT-5/Codex results exist in this benchmark tranche.

## Immediate deck edits

- Replace "3-model results" section with "3-model execution status + blocker evidence".
- Add one slide for "Model-path readiness" as an explicit gating dependency.
- Keep recommendation focused on wrong-tool mitigation and ablation-backed causality.
