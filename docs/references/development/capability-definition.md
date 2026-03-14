# Capability Definition

This is the core artifact for a workflow component. Every workflow starts here.

## What It Is

A Capability Definition declares:

- the capability identity and version
- the prompt reference and prompt hash
- the risk tier
- the safety envelope
- the workflow contract reference when required
- the execution scopes
- delegated specialist references
- the LLM routing choice
- the required identity tags
- the tool bindings
- the evaluation pack reference

Schema source:

- [`contracts/schemas/capability-definition.schema.json`](../../../contracts/schemas/capability-definition.schema.json)

Artifact location:

- `capability-definitions/<capability-id>.json`

## What You Need Before You Create One

Have these decisions ready first:

- `capability_id`
- semantic version
- lifecycle state
- `risk_tier`
- prompt reference and immutable hash
- safety envelope reference
- workflow contract reference if the capability needs one
- scopes such as `Reasoning`, `Coordination`, `Process`
- tool bindings and their `action_class`
- evaluation pack reference

## How To Create It

1. Pick whether this file is an orchestrator or a specialist.
2. Set `metadata.capability_id`, `version`, and `lifecycle_state`.
3. Fill `prompt.prompt_ref` and `prompt.prompt_sha256`.
4. Set `governance.risk_tier`.
5. Reference a Safety Envelope with `governance.safety_envelope_ref`.
6. Add `governance.workflow_contract_ref` when `Process` or higher-risk governance requires it.
7. Set `execution_model.scopes`.
8. Add `delegated_capability_refs` if this capability calls specialists.
9. Keep `routing.llm_route` as `llm_gateway`.
10. Declare `allowed_model_families`.
11. Declare the required identity tags.
12. Add each tool binding with `tool_id`, `kind`, `action_class`, and `requires_identity_context`.
13. Reference the Evaluation Pack.

## Examples To Follow

### Player Protection Orchestrator

- file: [`capability-definitions/player-protection-case-orchestrator.json`](../../../capability-definitions/player-protection-case-orchestrator.json)
- use this when you need:
  - delegated specialists
  - `Process`
  - a workflow contract
  - `regulated_write`
  - a human review control binding

### SDLC PR Verifier Orchestrator

- file: [`capability-definitions/pr-verifier-orchestrator.json`](../../../capability-definitions/pr-verifier-orchestrator.json)
- use this when you need:
  - delegated specialists
  - `Process`
  - `internal_write`
  - a human review control binding

### Specialists

- Player Protection specialist: [`capability-definitions/customer-360-specialist.json`](../../../capability-definitions/customer-360-specialist.json)
- SDLC specialist: [`capability-definitions/diff-review-specialist.json`](../../../capability-definitions/diff-review-specialist.json)

Use these when you need a simpler read-oriented capability with `R0` and no workflow contract.

## Common Mistakes

- forgetting `prompt_sha256`
- using the wrong `action_class` for the chosen risk tier
- omitting the workflow contract when `Process` is present
- declaring delegation in the runtime but not in `delegated_capability_refs`
- creating tool bindings without matching runtime or adapter support

## What To Do Next

After the Capability Definition exists, move to:

- [safety-envelope.md](./safety-envelope.md)
- [workflow-contract.md](./workflow-contract.md)
- [evaluation-pack-and-datasets.md](./evaluation-pack-and-datasets.md)
