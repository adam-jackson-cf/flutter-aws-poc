# Development Setup For This Baseline

This repository is not a local runtime replica of the Flutter platform. It is the contract and governance baseline that future implementation must satisfy.

## What Exists Locally

- architecture source material in `docs/flutter-uki-ai-platform-arch/`
- contract schemas in `contracts/schemas/`
- artifact roots for authored contracts
- behavioral design linters and waiver checks
- CI, pre-commit, mutation testing, and complexity gates
- a minimal CDK scaffold pinned to `eu-west-1`

## What Does Not Exist

- no application runtime
- no route-scope PoC flow
- no evaluation harness
- no MCP or LLM gateway implementation
- no local mock stack that proves the platform

Those were intentionally removed. Do not infer their existence from preserved reference docs.

## Local Workflow

The local loop for this repo is:

1. author or change a contract artifact
2. add valid and invalid fixture coverage
3. run the design gates
4. only then add implementation work in a new task or slice

Recommended commands:

```bash
./scripts/bootstrap-repo.sh
bash scripts/run-ci-quality-gates.sh --lane=fast-r1r2
bash scripts/run-ci-quality-gates.sh --lane=quality-gates-core
python3 scripts/run-mutation-gate.py
```

## AWS Usage

AWS is only needed here for the retained scaffold stack and the external policy-guard automation. The presence of `infra/` does not mean the platform itself is implemented.

## Important Constraint

The current baseline is intentionally allowed to fail the compliance linter until the first real Capability Definitions, Safety Envelopes, Workflow Contracts, and Evaluation Packs are authored. Fix the missing contracts, not the gate strictness.
