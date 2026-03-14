# Evaluation Pack And Datasets

This file explains how you prove a workflow is ready to publish and run.

## What It Is

An Evaluation Pack records the release-gate evidence for a capability version and points at the datasets used to support that evidence.

Schema source:

- [`contracts/schemas/evaluation-pack.schema.json`](../../../contracts/schemas/evaluation-pack.schema.json)

Artifact locations:

- `evaluation-packs/<pack-id>.json`
- `datasets/*.jsonl`

## What You Need Before You Create One

Have these ready:

- the `capability_ref` this pack belongs to
- the release-gate metrics relevant to the workflow
- one or more datasets
- the dataset role, usually `release_gate`

## How To Create It

1. Create `evaluation-packs/<pack-id>.json`.
2. Set `metadata.pack_id` and `version`.
3. Set `capability_ref` to the exact versioned capability.
4. Fill `release_gate.status`.
5. Add the metrics that matter for your workflow.
6. Add dataset entries with `dataset_id`, `path`, and `role`.
7. Create the dataset file in `datasets/`.
8. Reference the pack from the Capability Definition.

## Existing Examples

### Player Protection

- pack: [`evaluation-packs/player-protection-case-orchestrator.json`](../../../evaluation-packs/player-protection-case-orchestrator.json)
- dataset: [`datasets/golden-player-protection-case.jsonl`](../../../datasets/golden-player-protection-case.jsonl)

PP is the example for metrics such as:

- `hitl_path_pass_rate`
- `audit_before_write_pass_rate`

### SDLC PR Verifier

- pack: [`evaluation-packs/pr-verifier-orchestrator.json`](../../../evaluation-packs/pr-verifier-orchestrator.json)
- dataset: [`datasets/golden-pr-verifier.jsonl`](../../../datasets/golden-pr-verifier.jsonl)

SDLC is the example for metrics such as:

- `case_pass_rate`
- `clean_run_pass_rate`
- `false_positive_rate`
- `structured_output_schema_valid`

### Specialists

- Player Protection specialist pack: [`evaluation-packs/customer-360-specialist.json`](../../../evaluation-packs/customer-360-specialist.json)
- SDLC specialist pack: [`evaluation-packs/diff-review-specialist.json`](../../../evaluation-packs/diff-review-specialist.json)

## Where To Put Datasets

Main workflow datasets live at the repository root in `datasets/`.

Fixture-only datasets for linter tests live under:

- `tests/fixtures/flutter-design/.../datasets/`

If you are creating a real workflow in the repo, add the real dataset to `datasets/` and add fixture coverage separately under `tests/fixtures/flutter-design/`.

## Common Mistakes

- forgetting to create the dataset file referenced by the pack
- pointing `capability_ref` at the wrong version
- copying PP metrics into a non-PP workflow without changing them
- skipping fixture coverage for invalid cases

## What To Do Next

After the Evaluation Pack exists, continue with:

- [prompts.md](./prompts.md)
- [runtime-implementation.md](./runtime-implementation.md)
