# Sandbox Deploy And Verification

This file explains when a workflow change needs deployment and how to verify it.

## When To Stay Local

Stay local when you are only proving:

- artifact validity
- fixture coverage
- runtime logic
- adapter behavior
- prompt metadata changes
- gateway code changes that do not yet need environment proof

Primary local commands:

```bash
./scripts/bootstrap-repo.sh
bash scripts/run-ci-quality-gates.sh
```

## When To Deploy

Deploy when the change needs:

- real AgentCore runtime or endpoint behavior
- sandbox bootstrap proof
- AWS guard-policy proof
- environment-bound gateway/runtime wiring proof

Primary deploy script:

- [`scripts/deploy/bootstrap-shared-sandbox.sh`](../../../scripts/deploy/bootstrap-shared-sandbox.sh)

## How To Deploy The Shared Sandbox

Typical flow:

1. ensure your environment is configured through `.envrc`
2. run the local strict gate first
3. bootstrap or update the sandbox

```bash
./scripts/deploy/bootstrap-shared-sandbox.sh --deployment-environment sandbox
```

This deploys the shared platform sandbox. It is not a separate sandbox per workflow.

## How To Verify Your Workflow Is Included

Check:

- the capability exists in `capability-definitions/`
- its Evaluation Pack and dataset exist
- the runtime can load it
- the publication manifest includes it

Relevant files:

- [`runtime/repository.py`](../../../runtime/repository.py)
- [`runtime/bootstrap.py`](../../../runtime/bootstrap.py)

## What To Use As Examples

### Player Protection

Use PP when you need to understand deployed proof of:

- HITL path
- audit-before-write
- regulated write behavior

### SDLC PR Verifier

Use SDLC when you need to understand deployed proof of:

- governed internal writeback
- shared runtime routing
- structured review output at the endpoint boundary

## Common Mistakes

- deploying before local artifacts and tests are ready
- assuming each workflow needs a separate sandbox
- forgetting that AWS-only proof is the reason to deploy, not just habit
