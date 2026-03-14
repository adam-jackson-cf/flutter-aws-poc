# Tooling And Specialists

This file explains how workflows use MCP tools, RAG lookups, human review controls, and delegated specialist capabilities.

## What Counts As Tooling Here

Inside a Capability Definition, tooling is represented by `tool_bindings`.

Each binding declares:

- `tool_id`
- `kind`
- `action_class`
- `requires_identity_context`

Supported `kind` values are defined in the schema:

- `mcp`
- `rag`
- `human_review`
- `internal_event`

## What Counts As A Specialist

A specialist is another capability referenced through:

- `governance.execution_model.delegated_capability_refs`

Use a specialist when the orchestrator needs another capability to gather evidence or perform a bounded subtask.

## Where The Pieces Live

- bindings: `capability-definitions/*.json`
- adapter behavior: [`runtime/adapters.py`](../../../runtime/adapters.py)
- delegation and binding resolution: [`runtime/engine.py`](../../../runtime/engine.py)

## Existing Examples

### Player Protection

Orchestrator:

- [`capability-definitions/player-protection-case-orchestrator.json`](../../../capability-definitions/player-protection-case-orchestrator.json)

Specialist:

- [`capability-definitions/customer-360-specialist.json`](../../../capability-definitions/customer-360-specialist.json)

Bindings used:

- `customer-360-reader` as `mcp` `read`
- `rg-policy-search` as `rag` `read`
- `rg-intervention-write` as `mcp` `regulated_write`
- `compliance-review-gate` as `human_review` `control`

### SDLC PR Verifier

Orchestrator:

- [`capability-definitions/pr-verifier-orchestrator.json`](../../../capability-definitions/pr-verifier-orchestrator.json)

Specialist:

- [`capability-definitions/diff-review-specialist.json`](../../../capability-definitions/diff-review-specialist.json)

Bindings used:

- `github-diff-reader` as `mcp` `read`
- `engineering-standards-search` as `rag` `read`
- `pr-comment-writer` as `mcp` `internal_write`
- `engineering-review-gate` as `human_review` `control`

## How To Add A New Tool Binding

1. Add the binding to the Capability Definition.
2. Choose the right `kind`.
3. Choose the right `action_class`.
4. Ensure the runtime has adapter support for the `tool_id`.
5. Add or update tests and fixtures.

For fixture-backed local behavior, update:

- [`runtime/adapters.py`](../../../runtime/adapters.py)

## How To Add A New Specialist

1. Create the specialist Capability Definition.
2. Create or reuse its Safety Envelope.
3. Create its Evaluation Pack and dataset.
4. Add the specialist ref to the orchestrator’s `delegated_capability_refs`.
5. Update runtime execution logic if the shared runtime needs to call it.

## Common Mistakes

- adding a binding without adapter support
- forgetting the specialist’s own Evaluation Pack
- using the wrong `action_class`
- forgetting the human review control binding for a governed write path
