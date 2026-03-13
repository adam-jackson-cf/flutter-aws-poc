# AGENTS.md

Project-specific operational defaults for agents and developers working in this repository. Repository purpose and setup live in `README.md`.

## Working Values

- Contracts before implementation.
- Behavioral enforcement before marker scans.
- No backwards compatibility for deleted PoC behavior.
- Do not recreate deleted PoC runtime, eval, route-scope, or gateway implementations unless a task explicitly defines a new supported replacement.
- Treat empty artifact roots and failing compliance as a valid starting state.

## Project Index

- `capability-definitions/`: Capability Definitions
- `safety-envelopes/`: Safety Envelopes
- `workflow-contracts/`: Workflow Contracts
- `evaluation-packs/`: Evaluation Packs
- `contracts/schemas/`: canonical JSON Schemas
- `scripts/linters/flutter-design/`: CLI enforcement entrypoints
- `scripts/linters/flutter_design_support/`: core rule logic
- `tests/fixtures/flutter-design/`: valid and invalid fixture corpora
- `docs/flutter-uki-ai-platform-arch/`: architecture source material
- `docs/references/`: repository-specific enforcement and workflow notes
- `infra/`: minimal build/deploy scaffold only

## AWS And Environment Defaults

- Canonical AWS region is `eu-west-1` only.
- Pin these together:
  - `AWS_REGION=eu-west-1`
  - `BEDROCK_REGION=eu-west-1`
  - `CDK_DEFAULT_REGION=eu-west-1`
- Use `.envrc` and `.envrc.example` as the environment source of truth.
- Do not introduce `.env` or `.env.example`.
- The retained stack is `FlutterAgentCorePocStack`. It is a scaffold, not proof of platform implementation.

## Working Rules

- Prefer fixture-driven tests with real valid and invalid contracts.
- Do not use placeholder baseline packages, marker scans, or string-presence checks as proof of design compliance.
- Mutation testing must stay focused on the core enforcement modules.
- Do not describe reference docs as implemented runtime behavior unless the corresponding repo slice now exists.

## Operational Commands

Initial setup and bootstrap live in `README.md`. Use the commands below for ongoing work.

### Governance And Linting

- `bash scripts/run-ci-quality-gates.sh --lane=preflight`
- `bash scripts/run-ci-quality-gates.sh --lane=fast-r1r2`
- `bash scripts/run-ci-quality-gates.sh --lane=quality-gates-core`
- `bash scripts/run-ci-quality-gates.sh --lane=strict-r3`
- `bash scripts/run-ci-quality-gates.sh --lane=nightly-full`
- `python3 scripts/linters/flutter-design/check-flutter-design-compliance.py --output json --timings`
- `python3 scripts/linters/flutter-design/check-flutter-design-waivers.py`
- `python3 scripts/run-mutation-gate.py`

### Infra Scaffold

- `npm --prefix infra run cdk:synth`
- `npm --prefix infra run cdk:diff`
- `npm --prefix infra run cdk:deploy`

### Governance Support Scripts

- `scripts/guards/apply-flutter-design-aws-guards.sh --help`

## Security Defaults

- Never print secret values in terminal output.
- Use presence checks for env and secrets; mask values if display is unavoidable.
