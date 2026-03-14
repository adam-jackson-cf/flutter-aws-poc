# Context Pack: Remaining blockers for PP and SDLC shared-platform completion

- Created: 2026-03-13
- Repo root: `/Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc`
- Target path: `.`
- Project mode: `brownfield`
- Artifact root: `/Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/.plan/create-execplan/20260313-remaining-blockers`
- Workspace root: `/Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/.plan/create-execplan/20260313-remaining-blockers/workspace`
- Related links:
  - `/Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/scripts/deploy/bootstrap-shared-sandbox.sh`
  - `/Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/scripts/guards/apply-flutter-design-aws-guards.sh`
  - `/Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/runtime/engine.py`

## Change Brief (1–3 paragraphs)

This is a brownfield close-out plan, not a fresh implementation design. The repository now contains the shared runtime, governed workflow artifacts, AWS bootstrap flow, strict quality gates, and a deployed sandbox for the two target workflows: player protection (`R3`) and SDLC PR verification (`R1 + Process`). The remaining work is to close the last live deployment gap and to capture the exact tasks and evidence needed so a later executor can finish the deployment cleanly without rediscovering the same AWS account boundary.

The blocker is specific: the shared sandbox deploy succeeds from member account `530267068969`, but live SCP enforcement cannot complete because the available local credentials do not have Organizations policy-management permissions in management account `023016403424`. The close-out plan therefore needs to treat management-account access as an explicit dependency, not an implied assumption.

One useful additional change belongs in the plan because it reduces repeat failure: thread management-account credentials through the shared bootstrap path so “deploy the shared platform” and “apply enforce-mode AWS guards” become one deterministic workflow. There is also a documentation knock-on effect: the repo now has a real runtime/bootstrap path, but the README still contains stale “not currently a working runtime implementation” wording that should be aligned during completion.

## Requirement Freeze (user-confirmed)

- R1: Record that the repo implementation is complete enough to pass `nightly-full` locally.
- R2: Record that the shared sandbox runtime, endpoint, bootstrap resources, artifact upload, and stack deployment have succeeded in AWS account `530267068969`.
- R3: Record that the remaining live blocker is enforced SCP guard application because the available local credentials do not have Organizations policy-management permissions for management account `023016403424`.
- R4: Record the exact follow-on tasks needed to complete deployment close-out once management-account access is available.
- R5: Keep the final completion path compatible with redeploying the same solution into a fresh environment by configuration and IaC rather than manual rebuild.
- R6: Make management-account profile or `--assume-role-arn` wiring an explicit completion item so deploy plus live guard enforcement can be run as one deterministic workflow.
- Confirmed by user at: 2026-03-14T00:08:39Z

## Discovery Inputs

- Intake artifact: `/Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/.plan/create-execplan/20260313-remaining-blockers/workspace/context-discovery.md`
- Evidence artifact: `/Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/.plan/create-execplan/20260313-remaining-blockers/workspace/context-evidence.json`
- Codemap artifact: `/Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/.plan/create-execplan/20260313-remaining-blockers/workspace/context-codemap.md`
- Requirements freeze artifact: `/Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/.plan/create-execplan/20260313-remaining-blockers/workspace/requirements-freeze.md`
- Notes:
  - Architecture decisions are already locked: one shared platform, two workflows, no extra scenario isolation.
  - This repo is beyond empty-contract baseline status; the plan must reflect implemented runtime and deploy code that already exists.
  - The live blocker is an AWS Organizations permission boundary, not a contract/runtime-design gap.

## Guardrails (must-follow)

- Quality gates:
  - `bash scripts/run-ci-quality-gates.sh --lane=nightly-full`
  - `python3 -m pytest -q tests/test_bootstrap_shared_sandbox_script.py tests/test_apply_flutter_design_aws_guards_script.py`
  - `npm --prefix infra run cdk:synth`
- Repo rules:
  - Use IaC and environment configuration only; no manual console-created dependencies for final completion.
  - Keep region pinned to `eu-west-1`.
  - Do not reopen the shared-platform architecture or introduce per-scenario isolation.
  - Do not weaken tests or gates to get past the AWS blocker.
- Prohibited actions:
  - No manual/scattered SCP setup outside a documented, repeatable deploy flow.
  - No fallback architecture that splits PP and SDLC into separate platforms just to avoid governance enforcement.

## Research Scope & Recency Policy

- Online research allowed: yes
- Approved source types: repository files, live AWS CLI state, official AWS surfaces already reachable via configured credentials
- Approved domains/APIs:
  - AWS CLI for STS, CloudFormation, AgentCore control plane, and Organizations
- Recency expectation:
  - Live AWS state must be verified directly at execution time
  - Repo state comes from the current working tree
- Exception handling:
  - If Organizations state cannot be read from the current credential context, record the exact access failure and stop rather than infer SCP state

## Evidence Inventory

| Evidence ID | Type | Source | Published | Retrieved | Trust rationale |
| ----------- | ---- | ------ | --------- | --------- | --------------- |
| E1 | repo-file | `runtime/engine.py:27` | undated: current working tree | 2026-03-14 | Primary runtime implementation for both workflows on one shared runtime |
| E2 | repo-file | `runtime/agentcore_main.py:16` | undated: current working tree | 2026-03-14 | Primary HTTP surface for AgentCore direct-code deploy |
| E3 | repo-file | `scripts/run-ci-quality-gates.sh` | undated: current working tree | 2026-03-14 | Primary quality-gate entrypoint |
| E4 | repo-file | `scripts/deploy/bootstrap-shared-sandbox.sh:436` | undated: current working tree | 2026-03-14 | Primary deploy/bootstrap control flow |
| E5 | repo-file | `scripts/guards/apply-flutter-design-aws-guards.sh:420` | undated: current working tree | 2026-03-14 | Primary live guard enforcement logic |
| E6 | repo-file | `infra/runtime-bootstrap-resources.yaml:4` | undated: current working tree | 2026-03-14 | Primary IaC bootstrap resources for fresh-environment deployment |
| E7 | repo-file | `tests/test_bootstrap_shared_sandbox_script.py:164` | undated: current working tree | 2026-03-14 | Regression coverage for bootstrap flow |
| E8 | session-observation | current session deploy result | 2026-03-14 | 2026-03-14 | Direct evidence that shared sandbox runtime/endpoint/stack deploy succeeded |
| E9 | aws-cli-observation | `aws organizations describe-organization` | 2026-03-14 | 2026-03-14 | Direct evidence of org management account ID |
| E10 | aws-cli-observation | `aws organizations list-policies-for-target` | 2026-03-14 | 2026-03-14 | Direct evidence that available credentials cannot manage SCPs |
| E11 | repo-file | `tests/test_apply_flutter_design_aws_guards_script.py:268` | undated: current working tree | 2026-03-14 | Regression coverage for access-denied guard failure |
| E12 | repo-file | `README.md:14` and `README.md:58` | undated: current working tree | 2026-03-14 | Documents both the stale repo-status wording and the real bootstrap path |

## Verification Baseline & Strategy

- Verification scenario: `brownfield-existing`
- Existing verification commands:
  - `bash scripts/run-ci-quality-gates.sh --lane=nightly-full`
  - `python3 -m pytest -q tests/test_bootstrap_shared_sandbox_script.py tests/test_apply_flutter_design_aws_guards_script.py`
  - `npm --prefix infra run cdk:synth`
  - `./scripts/deploy/bootstrap-shared-sandbox.sh --deployment-environment sandbox`
- User decision when verification missing: `n/a-existing`
- Planned verification scope:
  - keep `nightly-full` as the repo baseline
  - add change-scoped bootstrap/guard tests for any management-account auth plumbed into deploy flow
  - run live enforce-mode guard completion with management-account access
  - run both PP and SDLC live scenario invocations against the same shared endpoint
  - prove redeployability by running the same bootstrap path against a fresh environment selection
- Mandatory smoke gate command:
  - `bash scripts/run-ci-quality-gates.sh --lane=nightly-full`
- Smoke gate expected success signal:
  - exit `0` with all strict repo gates passing before any live AWS close-out run

## Established Library Comparison (required for greenfield; optional for brownfield)

Not applicable. This is a brownfield close-out plan using existing repo implementation, existing AWS CLI entrypoints, and existing IaC.

## Existing Change Surface (required for brownfield; optional for greenfield)

| Area | File anchor | Current behavior | Integration concern | Evidence IDs |
| ---- | ----------- | ---------------- | ------------------- | ------------ |
| Deploy bootstrap | /Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/scripts/deploy/bootstrap-shared-sandbox.sh:232 | Parses environment, runtime, endpoint, guard, and artifact options for the shared sandbox deploy. | Management-account auth is not yet surfaced in the top-level bootstrap interface. | E4 |
| Runtime creation and endpoint convergence | /Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/scripts/deploy/bootstrap-shared-sandbox.sh:436 | Creates or reuses the shared runtime and endpoint deterministically. | Must remain unchanged in behavior while auth wiring is added for guard completion. | E4,E7 |
| Guard enforcement | /Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/scripts/guards/apply-flutter-design-aws-guards.sh:420 | Enforces stack-output, endpoint, and SCP guard checks. | Live SCP enforcement only succeeds from a management-account permission context. | E5,E10,E11 |
| Shared runtime | /Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/runtime/engine.py:48 | Executes both workflows from one runtime with audit, delegation, and tool adapters. | Live completion should prove both workflows against the same runtime, not split deployment topology. | E1,E8 |
| Runtime bootstrap IaC | /Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/infra/runtime-bootstrap-resources.yaml:13 | Supplies minimal fresh-environment runtime artifact bucket and role. | Must stay the source of truth for redeployability; no console-created replacements. | E6 |
| Documentation | /Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/README.md:14 | Claims repo is not currently a working runtime implementation. | Statement now lags implemented runtime/bootstrap state and could mislead later executors. | E12 |

## Repo Facts (execution-relevant only)

- Languages/frameworks:
  - Python 3.12 runtime and tests
  - Bash deploy/guard automation
  - TypeScript CDK scaffold
- Package manager(s):
  - `npm` for infra
- Build tooling:
  - AWS CDK via `npm --prefix infra`
  - Python packaging script for shared runtime artifact
- Test tooling:
  - `pytest`
  - repo quality-gate shell lane
- Key environment variables/config files:
  - `.envrc`
  - `AWS_REGION=eu-west-1`
  - `BEDROCK_REGION=eu-west-1`
  - `CDK_DEFAULT_REGION=eu-west-1`
  - AWS profile or assume-role inputs for deployment

## Dependency Preconditions

| Dependency | Purpose | Check command | Install command | Source | Expected success signal |
| ---------- | ------- | ------------- | --------------- | ------ | ----------------------- |
| `aws` CLI | Live deploy, runtime, endpoint, and Organizations checks | `aws --version` | use workstation-managed AWS CLI install | workstation / AWS | CLI available and callable |
| `npm` | CDK synth/deploy | `npm --version` | use workstation-managed Node/npm install | workstation | CLI available and callable |
| Python 3.12 | Quality gates, packaging, tests | `python3 --version` | use workstation-managed Python install | workstation | Python available and callable |
| Member-account deploy profile | Deploy shared stack/runtime in `530267068969` | `aws sts get-caller-identity --query Account --output text` | configure in `.envrc` or shell profile | AWS account access | returns `530267068969` when using deploy profile |
| Management-account access | Enforce SCP guards in org management account `023016403424` | `aws sts get-caller-identity --query Account --output text` after profile/assume-role switch | configure management-account profile or assumable role | AWS Organizations management account | returns management account or successful `sts assume-role` path |

## Execution Command Catalog

| Purpose | Command | Expected success signal |
| ------- | ------- | ----------------------- |
| Smoke baseline | `bash scripts/run-ci-quality-gates.sh --lane=nightly-full` | exit `0` |
| Change-scoped bootstrap tests | `python3 -m pytest -q tests/test_bootstrap_shared_sandbox_script.py` | targeted bootstrap tests pass |
| Change-scoped guard tests | `python3 -m pytest -q tests/test_apply_flutter_design_aws_guards_script.py` | targeted guard tests pass |
| Infra synth | `npm --prefix infra run cdk:synth` | synth succeeds |
| Shared bootstrap deploy | `./scripts/deploy/bootstrap-shared-sandbox.sh --deployment-environment sandbox` | runtime + endpoint + stack deploy complete |
| Live enforce-mode guards | `./scripts/guards/apply-flutter-design-aws-guards.sh --mode enforce --target-scope account --target-id 530267068969 --stack-name FlutterAgentCorePocStack --region eu-west-1 --runtime-id <runtime-id> --endpoint-name sandbox` | `G1=PASS`, `G2=PASS`, `OVERALL_STATUS=PASS` |
| Live scenario invocation | call `/invocations` against the shared runtime endpoint for each capability | PP and SDLC responses succeed with governed behavior and audit evidence |

## Code Map (line-numbered)

| Area | File anchor | What it contains | Why it matters | Planned change |
| ---- | ----------- | ---------------- | -------------- | -------------- |
| Bootstrap options | /Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/scripts/deploy/bootstrap-shared-sandbox.sh:8 | CLI interface for shared deploy flow | This is where management-account auth should become part of the deploy contract | Add explicit management-account profile/assume-role inputs and forwarding |
| Bootstrap runtime and deploy flow | /Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/scripts/deploy/bootstrap-shared-sandbox.sh:436 | Runtime/endpoint resolution, stack deploy, and guard invocation | Main live completion path | Preserve behavior, extend auth plumb-through, capture evidence |
| Guard options | /Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/scripts/guards/apply-flutter-design-aws-guards.sh:6 | Guard CLI interface and usage | Already supports assume-role; plan must standardize how deploy uses it | Strengthen documented contract and test coverage |
| Guard enforcement core | /Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/scripts/guards/apply-flutter-design-aws-guards.sh:528 | SCP drift/enforce logic | Final blocker sits here | Run successfully from management-account context and capture proof |
| Shared runtime API | /Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/runtime/agentcore_main.py:24 | `/ping` and `/invocations` handler | Live scenario close-out uses this surface | No redesign; only evidence capture |
| Shared workflow engine | /Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/runtime/engine.py:128 | PP and SDLC execution logic | Proves both workflows live on one runtime | Use for shared-endpoint scenario evidence |
| Bootstrap tests | /Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/tests/test_bootstrap_shared_sandbox_script.py:164 | Script behavior regression tests | Protect new bootstrap auth contract | Extend if new CLI/env options are added |
| Guard tests | /Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/tests/test_apply_flutter_design_aws_guards_script.py:268 | Guard error-path regression tests | Protect auth and SCP enforcement behavior | Add success-path coverage with management-account auth wiring |
| Runtime bootstrap IaC | /Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/infra/runtime-bootstrap-resources.yaml:13 | Fresh-environment resources | Redeployability depends on this | Reuse unchanged, verify as part of completion evidence |
| README docs | /Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/README.md:18 | Risk-tier guidance plus bootstrap instructions | Repo status wording now conflicts with implementation reality | Align docs with brownfield reality during close-out |

## Requirement to Evidence Traceability

| Requirement ID | Requirement | Evidence IDs | Context section(s) | Planned ExecPlan linkage |
| -------------- | ----------- | ------------ | ------------------ | ------------------------ |
| R1 | `nightly-full` passes locally | E1,E2,E3,E11 | Guardrails, Verification Baseline | Phase 1 / Tasks 1-3 |
| R2 | Shared sandbox runtime/endpoint/stack deployed | E4,E5,E6,E7,E8 | Existing Change Surface, Command Catalog | Phase 2 / Tasks 4-6 |
| R3 | Remaining blocker is management-account SCP enforcement | E8,E9,E10 | Change Brief, Evidence Inventory | Phase 2 / Tasks 4-6 |
| R4 | Exact follow-on completion tasks are defined | E4,E5,E7,E8,E12 | Code Map, Risk Register | All phases |
| R5 | Completion path stays redeployable via IaC + config | E4,E6,E12 | Guardrails, Dependency Preconditions | Phase 4 / Tasks 10-12 |
| R6 | Management-account auth is explicit in deploy path | E4,E5,E10,E12 | Existing Change Surface, Command Catalog | Phase 2 / Tasks 4-6 |

## Contracts & Interfaces

- CLI commands and arguments:
  - `scripts/deploy/bootstrap-shared-sandbox.sh`
  - `scripts/guards/apply-flutter-design-aws-guards.sh`
- Runtime API:
  - `/ping`
  - `/invocations`
- Governed workflow artifacts:
  - `capability-definitions/player-protection-case-orchestrator.json`
  - `capability-definitions/pr-verifier-orchestrator.json`
  - `workflow-contracts/player-protection-case-handling.json`
  - `workflow-contracts/pr-verification-review.json`

## Risk Register

| Risk | Impact | Mitigation | Verification command | Evidence IDs |
| ---- | ------ | ---------- | -------------------- | ------------ |
| Management-account access is still unavailable at execution time | Live guard completion cannot be finished | Make management-account profile or assume-role a hard dependency with explicit failure mode | `aws sts get-caller-identity --query Account --output text` and SCP lookup | E5,E9,E10 |
| Deploy path stays split between member-account deploy and separate guard operation | Fresh-environment promotion remains partially tribal/manual | Wire management-account auth into shared bootstrap command and document it | bootstrap command plus enforce-mode guard pass | E4,E5 |
| Documentation stays stale about runtime status | Later executors under-scope or mistrust brownfield implementation | Add docs-alignment task during close-out | doc diff review plus bootstrap/runbook validation | E12 |
| Executor reopens architecture instead of closing deployment | Wastes time and risks regressions | Freeze topology decisions in Context Pack and ExecPlan | review plan tasks against frozen requirements | E1,E4,E12 |
