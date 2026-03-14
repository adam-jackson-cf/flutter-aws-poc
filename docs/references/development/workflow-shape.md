# Workflow Shape

This file explains what a complete workflow looks like on this platform before you start writing any individual artifact.

## What You Are Building

A workflow on this platform is not one file. It is a governed package made up of:

- a Capability Definition
- a Safety Envelope
- a Workflow Contract when `Process` or higher-risk governance is involved
- an Evaluation Pack and datasets
- prompt metadata
- tool bindings and, when needed, delegated specialist capabilities
- runtime support if the shared runtime does not already know how to execute it

## Where The Pieces Live

- `capability-definitions/`
- `safety-envelopes/`
- `workflow-contracts/`
- `evaluation-packs/`
- `datasets/`
- `runtime/`
- `tests/fixtures/flutter-design/`

## Decide The Workflow Shape First

Before you create files, decide:

1. Is this an orchestrator or a specialist capability?
2. What is the workflow risk tier?
3. Does it need `Process` scope?
4. Does it read only, write internally, write to customer state, or perform regulated writes?
5. Does it call tools directly, delegate to specialists, or both?
6. Does the shared runtime already have a matching execution path?

## Examples

### Player Protection

Use Player Protection when you need the stricter example:

- orchestrator capability: [`capability-definitions/player-protection-case-orchestrator.json`](../../../capability-definitions/player-protection-case-orchestrator.json)
- delegated specialist: [`capability-definitions/customer-360-specialist.json`](../../../capability-definitions/customer-360-specialist.json)
- workflow contract: [`workflow-contracts/player-protection-case-handling.json`](../../../workflow-contracts/player-protection-case-handling.json)

This is `R3`, uses `Reasoning`, `Coordination`, and `Process`, and includes a regulated write path.

### SDLC PR Verifier

Use SDLC when you need the internal-write example:

- orchestrator capability: [`capability-definitions/pr-verifier-orchestrator.json`](../../../capability-definitions/pr-verifier-orchestrator.json)
- delegated specialist: [`capability-definitions/diff-review-specialist.json`](../../../capability-definitions/diff-review-specialist.json)
- workflow contract: [`workflow-contracts/pr-verification-review.json`](../../../workflow-contracts/pr-verification-review.json)

This is `R1`, still uses `Process`, and governs an internal engineering writeback path.

## Recommended Creation Order

For a brand new workflow, work in this order:

1. choose the orchestrator and any specialists
2. define the risk tier and action classes
3. create or reuse the Safety Envelope
4. create the Capability Definition
5. create the Workflow Contract if required
6. create the Evaluation Pack and dataset
7. add runtime support if needed
8. add fixture coverage
9. run the strict gate
10. deploy only if real sandbox proof is required
