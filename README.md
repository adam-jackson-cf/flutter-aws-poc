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

## Risk Tiers, Layers, And Workflow Scope

Three different concepts in the Flutter design are easy to conflate:

- `L1-L5` are architecture layers every workflow uses
- `Reasoning / Coordination / Process` are execution-model scopes a capability may combine
- `R0-R3` is the single risk classification on a published capability version

A workflow does not pass through all `R` tiers at runtime. Instead, each published capability version declares one `Risk Tier`, and that tier drives its controls: evaluation rigor, workflow-contract requirement, HITL expectation, and audit behavior.

Examples:

- The player-protection orchestrator is `R3` because it can drive regulated writes and therefore needs the strictest governance. Its specialist capabilities can still be lower tier because they are read-only evidence gatherers.
- The SDLC PR verifier can be `R1 + Process` because it is an internal engineering verification flow with governed internal writeback such as review comments. It is not automatically `R2` or `R3` unless it gains customer-impacting or regulated actions.

The same business workflow can move between tiers over time, but only by publishing a new capability version with different permissions or action classes. It does not "traverse" `R1 -> R2 -> R3` during one execution.

This guidance explains the contract model only. It does not imply that the full runtime already exists in this repository today.

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

4. Bootstrap the shared sandbox with AWS CLI + IaC:

```bash
./scripts/deploy/bootstrap-shared-sandbox.sh --deployment-environment sandbox
```

The bootstrap flow is environment-driven. It binds to an existing AgentCore runtime when one already exists, or packages the shared runtime artifact and provisions the bootstrap resources needed to create one.

## Working In This Repo

Use `AGENTS.md` as the operational index for repository structure, AWS defaults, workflows, and command references.
