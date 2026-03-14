# Safety Envelope

This file explains the safety policy object attached to a capability.

## What It Is

A Safety Envelope captures the base operational constraints for a capability:

- allowed data classes
- guardrail profile
- prompt injection protection
- whether human review is required

Schema source:

- [`contracts/schemas/safety-envelope.schema.json`](../../../contracts/schemas/safety-envelope.schema.json)

Artifact location:

- `safety-envelopes/<envelope-id>.json`

## What You Need Before You Create One

Decide:

- what data classes the workflow is allowed to touch
- whether human review must always be present
- which guardrail profile name best fits the workflow
- whether an existing envelope already matches your use case

In many cases, you should reuse an existing Safety Envelope instead of creating a new one.

## Existing Examples

- `R3` regulated writes: [`safety-envelopes/default-r3-regulated-write.json`](../../../safety-envelopes/default-r3-regulated-write.json)
- `R1` internal writes: [`safety-envelopes/default-r1-internal-write.json`](../../../safety-envelopes/default-r1-internal-write.json)
- `R0` readonly specialists: [`safety-envelopes/default-r0-readonly.json`](../../../safety-envelopes/default-r0-readonly.json)

## How To Create Or Reuse One

1. Check whether one of the existing envelopes already matches your workflow.
2. If not, create a new file in `safety-envelopes/`.
3. Set `metadata.envelope_id` and `version`.
4. Fill `constraints.allowed_data_classes`.
5. Set `constraints.guardrail_profile`.
6. Set `prompt_injection_protection`.
7. Set `human_review_required`.
8. Reference the envelope from the Capability Definition.

## How The Current Scenarios Use Them

### Player Protection

PP uses [`default-r3-regulated-write.json`](../../../safety-envelopes/default-r3-regulated-write.json) because:

- the data class is `restricted`
- human review is required
- the workflow includes regulated writes

### SDLC PR Verifier

SDLC uses [`default-r1-internal-write.json`](../../../safety-envelopes/default-r1-internal-write.json) because:

- the data class is `internal`
- human review is still required
- the write is internal engineering writeback, not regulated action

### Specialists

Both existing specialists use [`default-r0-readonly.json`](../../../safety-envelopes/default-r0-readonly.json) because they are read-oriented helpers.

## Common Mistakes

- creating a new envelope when an existing one should be reused
- marking a write path as readonly
- setting `human_review_required` inconsistently with the workflow and tool bindings

## What To Do Next

Once the envelope is chosen, continue with:

- [capability-definition.md](./capability-definition.md)
- [workflow-contract.md](./workflow-contract.md)
