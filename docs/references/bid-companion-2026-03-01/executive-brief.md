# Executive Brief (Current)

Date: 2026-03-02  
Run source: `nova-adv-large-postfix-20260302T214400Z`

## Current position

The PoC now has a stable and useful baseline on adversarial evaluation:

- Native and MCP both pass deterministic release threshold.
- Native remains stronger on reliability and efficiency.
- MCP still shows measurable call-construction fragility and higher cost/latency.

## Latest benchmark summary

| Flow | Cases | Tool Failure Rate | Tool Match Rate | Business Success Rate | Mean Latency (ms) | Mean LLM Total Tokens | Mean Estimated Cost (USD) | Deterministic Release Score |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| native | 112 | 0.0000 | 0.9643 | 0.8571 | 1639.62 | 650.89 | 0.00007385 | 0.9125 |
| mcp | 112 | 0.0714 | 0.8929 | 0.8214 | 2167.28 | 1040.84 | 0.00010860 | 0.8911 |

## What this PoC can credibly claim now

- Real AgentCore Gateway MCP route and native route are both running under one deterministic harness.
- Model/runtime parity is auditable in artifacts (`gateway_model_id`, `runtime_bedrock_model_id`).
- MCP penalties are measurable and attributable in metrics (`call_construction_failure_rate`, retries, latency, tokens, cost).

## What remains out of scope

- Full Flutter architecture conformance (workflow contract, HITL controls, immutable audit semantics, full identity-context observability).

## Recommendation

Proceed with a focused hardening tranche targeting MCP write-call construction and alias normalization while preserving the current parity and evaluation controls.
