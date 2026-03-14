# Handoff: Plan A Rewrite Of dev-setup.md Into A Practical Hybrid Development Guide

## Starting Prompt

You are continuing work in `/Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc`.

Your goal in this session is to create a plan for rewriting [dev-setup.md](/Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/docs/references/dev-setup.md), not to rewrite it yet.

The new document should stop reading like an early contract-only baseline note and instead become a conceptual developer guide for how to build, test, and iterate on agentic workflows in this repo using a hybrid model:

- as much local development/testing as possible for fast iteration
- deploy only for the AWS-specific/platform-specific parts that need a real environment

Shape the plan around common developer tasks for this project, using the two implemented scenarios as concrete examples:

- Player Protection workflow
- SDLC PR Verifier workflow

The planned doc should include Mermaid diagrams that show business/development flow at a conceptual level, not low-level implementation detail. It should explain how developers can iterate locally on:

- capability definitions
- workflow contracts
- safety envelopes
- evaluation packs and fixtures
- agent/system prompts
- tooling capabilities via MCP gateway or equivalent
- adding or changing providers in the LLM gateway
- expanding an existing workflow versus creating a new one

Constraints:

- keep the planned document conceptual, not overly granular
- use links to implementation/code for deeper detail instead of duplicating repo internals
- use the two scenarios to illustrate the development model and common feature requests
- focus on developer workflow and mental model, not a deep architecture spec
- do not ignore that the repo has moved beyond the older baseline assumptions in `dev-setup.md`

Important current state:

- the repo now contains a shared runtime, shared PP + SDLC workflow execution, gateway/deploy/bootstrap logic, and stricter default local gates
- default local quality gate behavior now runs `nightly-full`
- test coverage target is now 100%
- pre-commit now follows the default strict gate path
- latest commits:
  - `a3a8c4f` `test: enforce nightly-full by default and reach 100 coverage`
  - `d99025e` `feat: add shared pp and sdlc e2e platform flow`

What to do first:

1. Read `docs/references/dev-setup.md`, `README.md`, and `AGENTS.md`.
2. Compare the current hybrid development model in the repo against what `dev-setup.md` currently says.
3. Produce a plan for the new doc structure, section-by-section.
4. Include suggested Mermaid diagrams and what each diagram should communicate.
5. Call out where the planned doc should link to code instead of restating implementation detail.

Do not start by editing the doc itself unless explicitly asked after the plan is reviewed.

## Relevant Files

- [dev-setup.md](/Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/docs/references/dev-setup.md)
  Current document to be replaced conceptually.
- [README.md](/Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/README.md)
  Current top-level repo narrative; partially stale relative to implementation.
- [AGENTS.md](/Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/AGENTS.md)
  Current operational guidance, including updated strict-gate defaults.
- [run-ci-quality-gates.sh](/Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/scripts/run-ci-quality-gates.sh)
  Shows the enforced local gate model and default `nightly-full`.
- [.pre-commit-config.yaml](/Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/.pre-commit-config.yaml)
  Confirms pre-commit now follows the default strict gate path.
- [engine.py](/Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/runtime/engine.py)
  Shared runtime execution path for both scenarios; useful for linking from the planned doc.
- [agentcore_main.py](/Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/runtime/agentcore_main.py)
  Runtime entrypoint; useful for explaining what is locally testable versus deployed.
- [bootstrap-shared-sandbox.sh](/Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/scripts/deploy/bootstrap-shared-sandbox.sh)
  Current deploy/bootstrap path; important for the “what must be deployed” boundary.
- [shared-gateway.ts](/Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/infra/lib/shared-gateway.ts)
  LLM gateway implementation surface; relevant for provider/gateway discussion.
- [player-protection-case-orchestrator.json](/Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/capability-definitions/player-protection-case-orchestrator.json)
  PP scenario example.
- [pr-verifier-orchestrator.json](/Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/capability-definitions/pr-verifier-orchestrator.json)
  SDLC scenario example.

## Key Context

- The current `dev-setup.md` is stale if read literally, but its intended hybrid development philosophy still mostly aligns with the repo.
- The repo now supports more local iteration than `dev-setup.md` implies:
  - local contract authoring
  - local fixture-driven validation
  - local runtime logic testing
  - local strict quality gates
- The deployed boundary is now narrower and more specific:
  - AgentCore runtime/endpoint lifecycle
  - AWS guard enforcement
  - sandbox bootstrap/deploy verification
- The strongest docs gap is that the repo now needs one coherent “hybrid local + deployed development workflow” story across `dev-setup.md`, `README.md`, and `AGENTS.md`.
- The next session should plan a replacement doc that helps developers handle common requests such as:
  - add a new workflow
  - expand PP or SDLC behavior
  - change prompts
  - add MCP-backed capabilities
  - extend gateway/provider support
- Keep the planned doc conceptual and task-oriented. Prefer linking to code for implementation details instead of embedding detailed code walkthroughs.
