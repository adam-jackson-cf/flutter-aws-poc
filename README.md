# Flutter Design Contract Baseline

This repository is a fresh starting point for rebuilding the Flutter solution design. The old PoC runtime, route logic, and evaluation harness have been removed. What remains is the contract baseline, governance tooling, and a minimal infra scaffold in `eu-west-1`.

## Concept

This repo is for defining and validating the governed artefacts that future implementation must satisfy:

- Capability Definitions
- Safety Envelopes
- Workflow Contracts
- Evaluation Packs

The architecture reference lives in `docs/flutter-uki-ai-platform-arch/`. The repository-specific interpretation of that design lives in `docs/references/`. This repo is not currently a working runtime implementation of the platform.

The empty baseline is intentionally allowed to fail design compliance until real contracts are authored. That is the expected starting state, not a reason to weaken the gates.

## Setup

1. Configure the local environment:

```bash
cp .envrc.example .envrc
direnv allow
```

2. Bootstrap dependencies and synthesize the scaffold stack:

```bash
./scripts/bootstrap-repo.sh
```

3. Optional: deploy the minimal infra shell:

```bash
./scripts/bootstrap-repo.sh --deploy-infra
```

## Working In This Repo

Use `AGENTS.md` as the operational index for repository structure, AWS defaults, workflows, and command references.
