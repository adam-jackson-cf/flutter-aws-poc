# Workflow Contract

This file explains the durable process contract for workflows that need it.

## What It Is

A Workflow Contract declares the governed process shape for a capability. It is required when the workflow uses `Process` scope or higher-risk governance rules require it.

The contract defines:

- workflow identity and version
- workflow risk tier
- ordered steps
- which steps are automated or human-reviewed
- idempotency key path
- whether compensation is required

Schema source:

- [`contracts/schemas/workflow-contract.schema.json`](../../../contracts/schemas/workflow-contract.schema.json)

Artifact location:

- `workflow-contracts/<workflow-id>.json`

## What You Need Before You Create One

Decide:

- whether the capability truly needs `Process`
- the workflow risk tier
- the ordered steps
- where human review must happen
- whether compensation is needed
- what request field provides idempotency

## How To Create It

1. Create `workflow-contracts/<workflow-id>.json`.
2. Set `metadata.workflow_id` and `version`.
3. Set `governance.risk_tier`.
4. Add ordered `steps`.
5. Mark each step as `automated`, `human_review`, or `compensation`.
6. Set `idempotency.key_path`.
7. Set `compensation.required`.
8. Reference the contract from the Capability Definition.

## Existing Examples

### Player Protection

- file: [`workflow-contracts/player-protection-case-handling.json`](../../../workflow-contracts/player-protection-case-handling.json)

Use this example when you need:

- an `R3` process
- an explicit human approval step before a regulated write
- compensation enabled

### SDLC PR Verifier

- file: [`workflow-contracts/pr-verification-review.json`](../../../workflow-contracts/pr-verification-review.json)

Use this example when you need:

- an `R1` process
- a human approval step before an internal write
- no compensation requirement

## How It Connects To The Workflow

The Workflow Contract is not standalone. It must line up with:

- the capability risk tier
- the tool binding action classes
- the Safety Envelope
- the runtime behavior

If your capability has a write step but your workflow has no human review step, the governance checks should reject it.

## Common Mistakes

- forgetting the workflow contract when `Process` is declared
- misaligning the workflow risk tier with the capability risk tier
- forgetting the human review step for a governed write path
- setting the wrong idempotency path

## What To Do Next

After the contract exists, continue with:

- [evaluation-pack-and-datasets.md](./evaluation-pack-and-datasets.md)
- [runtime-implementation.md](./runtime-implementation.md)
