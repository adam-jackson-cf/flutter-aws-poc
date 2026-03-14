# Prompts

This file explains how prompts are represented in the workflow model.

## What They Are On This Platform

Prompts are not first-class files in a `prompts/` directory in this repository today. Instead, capabilities pin prompt metadata through:

- `prompt_ref`
- `prompt_sha256`

That means the workflow contract records:

- which prompt is intended
- which exact prompt hash the published capability was validated against

## Where Prompt Data Appears

Prompt metadata lives inside the Capability Definition:

- [`capability-definitions/player-protection-case-orchestrator.json`](../../../capability-definitions/player-protection-case-orchestrator.json)
- [`capability-definitions/pr-verifier-orchestrator.json`](../../../capability-definitions/pr-verifier-orchestrator.json)
- [`capability-definitions/customer-360-specialist.json`](../../../capability-definitions/customer-360-specialist.json)
- [`capability-definitions/diff-review-specialist.json`](../../../capability-definitions/diff-review-specialist.json)

The runtime and publication manifest also surface the prompt metadata:

- [`runtime/repository.py`](../../../runtime/repository.py)
- [`runtime/engine.py`](../../../runtime/engine.py)

## What You Need Before You Update A Prompt

Decide:

- whether the prompt change belongs to an existing capability or a new one
- what the new prompt reference should be
- how the prompt will be versioned and hashed
- whether the prompt change requires new evaluation evidence

## How To Action A Prompt Change

1. Update `prompt_ref` in the Capability Definition if the prompt identity changed.
2. Update `prompt_sha256` to the exact hash of the prompt version you intend to publish.
3. Re-run the local tests and quality gates.
4. If the change affects workflow behavior materially, update the Evaluation Pack evidence expectations.
5. Deploy only if you need real endpoint or provider proof.

## Examples

### Player Protection

PP uses a dedicated prompt reference because the orchestrator must reason about intervention and regulated-write handling.

### SDLC PR Verifier

SDLC uses its own prompt reference because the output contract is a structured engineering review rather than a regulated intervention decision.

## Common Mistakes

- changing prompt behavior but forgetting to update `prompt_sha256`
- reusing the wrong prompt reference across unrelated capabilities
- treating prompts as optional metadata

## Important Constraint

Because prompt bodies are not stored as local first-class artifacts in this repo today, a new developer should treat `prompt_ref` and `prompt_sha256` as the authoritative contract surface in-repo. If prompt storage is managed externally, the capability must still pin the exact published prompt identity and hash.
