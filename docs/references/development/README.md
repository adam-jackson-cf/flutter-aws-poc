# Development Reference For Building New Agentic Workflows

This directory is the developer-facing reference for adding or extending workflows on the shared platform implementation in this repository.

If you are new to the project and want to create a new workflow, read these files in order:

1. [workflow-shape.md](./workflow-shape.md)
2. [capability-definition.md](./capability-definition.md)
3. [safety-envelope.md](./safety-envelope.md)
4. [workflow-contract.md](./workflow-contract.md)
5. [evaluation-pack-and-datasets.md](./evaluation-pack-and-datasets.md)
6. [prompts.md](./prompts.md)
7. [tooling-and-specialists.md](./tooling-and-specialists.md)
8. [runtime-implementation.md](./runtime-implementation.md)
9. [gateway-routing.md](./gateway-routing.md)
10. [sandbox-deploy-and-verification.md](./sandbox-deploy-and-verification.md)

## What A New Workflow Usually Needs

At minimum, a new workflow usually needs:

- one or more Capability Definitions in `capability-definitions/`
- a Safety Envelope in `safety-envelopes/`
- a Workflow Contract in `workflow-contracts/` when the workflow uses `Process` or higher-risk execution
- an Evaluation Pack in `evaluation-packs/`
- one or more datasets in `datasets/`
- prompt metadata in the capability, pinned by `prompt_ref` and `prompt_sha256`
- runtime support in [`runtime/engine.py`](../../../runtime/engine.py) if the shared runtime needs new execution logic
- fixture coverage in `tests/fixtures/flutter-design/`

## Existing Examples To Follow

Use these as the primary examples while reading the rest of this directory:

- Player Protection orchestrator: [`capability-definitions/player-protection-case-orchestrator.json`](../../../capability-definitions/player-protection-case-orchestrator.json)
- Player Protection workflow: [`workflow-contracts/player-protection-case-handling.json`](../../../workflow-contracts/player-protection-case-handling.json)
- Player Protection evaluation pack: [`evaluation-packs/player-protection-case-orchestrator.json`](../../../evaluation-packs/player-protection-case-orchestrator.json)
- SDLC PR verifier orchestrator: [`capability-definitions/pr-verifier-orchestrator.json`](../../../capability-definitions/pr-verifier-orchestrator.json)
- SDLC workflow: [`workflow-contracts/pr-verification-review.json`](../../../workflow-contracts/pr-verification-review.json)
- SDLC evaluation pack: [`evaluation-packs/pr-verifier-orchestrator.json`](../../../evaluation-packs/pr-verifier-orchestrator.json)

## Working Rule

The platform is shared. A new workflow is added as another governed workflow on the same implementation. Do not assume you need a separate stack, account, or scenario-specific platform unless a later requirement explicitly forces isolation.
