# ExecPlan: Remaining blockers for PP and SDLC shared-platform completion

- Status: Finalized
- Start: 2026-03-13
- Last Updated: 2026-03-14T00:08:39Z
- Artifact root: `/Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/.plan/create-execplan/20260313-remaining-blockers/`
- Workspace root: `/Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/.plan/create-execplan/20260313-remaining-blockers/workspace/`
- Context Pack: `/Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/.plan/create-execplan/20260313-remaining-blockers/context-pack.md`
- Requirements Freeze artifact: `/Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/.plan/create-execplan/20260313-remaining-blockers/workspace/requirements-freeze.md`
- Draft Review artifact: `/Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/.plan/create-execplan/20260313-remaining-blockers/workspace/draft-review.md`
- Links:
  - `/Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/scripts/deploy/bootstrap-shared-sandbox.sh`
  - `/Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/scripts/guards/apply-flutter-design-aws-guards.sh`

## Executor Contract

- Allowed inputs: working tree + Context Pack + ExecPlan + AWS credentials/profile/role inputs
- Required output: completed close-out changes + updated ExecPlan + verification evidence + resolved SCP enforcement blocker
- Forbidden: undefined discovery tasks after requirements are frozen

## Requirements Freeze

- R1: Record that the repo implementation is complete enough to pass `nightly-full` locally.
- R2: Record that the shared sandbox runtime, endpoint, bootstrap resources, artifact upload, and stack deployment have succeeded in AWS account `530267068969`.
- R3: Record that the remaining live blocker is enforced SCP guard application because the available local credentials do not have Organizations policy-management permissions for management account `023016403424`.
- R4: Record the exact follow-on tasks needed to complete deployment close-out once management-account access is available.
- R5: Keep the final completion path compatible with redeploying the same solution into a fresh environment by configuration and IaC rather than manual rebuild.
- R6: Make management-account profile or `--assume-role-arn` wiring an explicit completion item so deploy plus live guard enforcement can be run as one deterministic workflow.
- Confirmed by user at: 2026-03-14T00:08:39Z

## Purpose / Big Picture

Complete the last operational gap in the already-implemented shared PP + SDLC platform by making live AWS guard enforcement executable from a fresh environment without tribal/manual steps. The repo already contains the shared runtime, workflow artifacts, deploy scripts, and tests; the remaining work is to finish the management-account guard path, capture end-to-end evidence for both workflows on the shared runtime, and align docs/runbooks to the brownfield reality.

The close-out work must preserve the existing architecture decisions: one shared platform deployment, two governed workflows, IaC-first deployment, and `eu-west-1` only. Nothing in this plan authorizes redesigning topology or weakening governance to get around the Organizations permission boundary.

## Success Criteria (how to prove “done”)

- [ ] Smoke: `bash scripts/run-ci-quality-gates.sh --lane=nightly-full` exits `0`.
- [ ] `python3 -m pytest -q tests/test_bootstrap_shared_sandbox_script.py tests/test_apply_flutter_design_aws_guards_script.py` exits `0`.
- [ ] `npm --prefix infra run cdk:synth` exits `0`.
- [ ] `./scripts/deploy/bootstrap-shared-sandbox.sh --deployment-environment sandbox --aws-profile 530267068969_AdministratorAccess --guard-assume-role-arn arn:aws:iam::023016403424:role/flutter-design-guards` completes with management-account auth wired in and no manual SCP step.
- [ ] `./scripts/guards/apply-flutter-design-aws-guards.sh --mode enforce ...` reports `G1_REGION_GUARD=PASS`, `G2_NON_BYPASS=PASS`, and `OVERALL_STATUS=PASS`.
- [ ] Live PP invocation against the shared runtime endpoint shows HITL-gated regulated write with audit evidence.
- [ ] Live SDLC invocation against the same shared runtime endpoint shows governed internal writeback only after human approval.
- [ ] Documentation/runbook text no longer contradicts the implemented runtime/bootstrap state.
- Non-Goals:
  - redesigning scenario topology
  - introducing a second sandbox/platform per workflow
  - changing risk-tier semantics
  - weakening guard or quality-gate behavior to pass without the required AWS permissions

## Constraints & Guardrails

- Region is fixed to `eu-west-1`.
- Final completion must be IaC-driven and environment-configurable.
- Shared-platform topology is already decided and must not be revisited.
- Guard enforcement must remain real; no detect-mode substitution for final completion.
- If management-account access is missing, stop and escalate instead of inferring SCP state.
- Update docs if runtime/deploy reality changed; leaving contradictory repo guidance is a known knock-on risk.

## Verification Strategy

- Scenario: `brownfield-existing`
- Existing verification reused:
  - `bash scripts/run-ci-quality-gates.sh --lane=nightly-full`
  - `python3 -m pytest -q tests/test_bootstrap_shared_sandbox_script.py tests/test_apply_flutter_design_aws_guards_script.py`
  - `npm --prefix infra run cdk:synth`
- Added verification scope:
  - management-account bootstrap/guard auth path
  - live enforce-mode SCP completion
  - live PP + SDLC invocations against the same runtime endpoint
  - doc/runbook alignment for brownfield runtime status
- Minimum smoke gate command:
  - `bash scripts/run-ci-quality-gates.sh --lane=nightly-full`
- If verification is missing, user decision: `n/a-existing`

## Dependency Preconditions

| Dependency | Check command | Install command | Source | Hard-fail behavior |
| ---------- | ------------- | --------------- | ------ | ------------------ |
| AWS CLI | `aws --version` | workstation-managed install | local workstation | stop and escalate on missing CLI |
| npm/CDK runtime | `npm --version` | workstation-managed install | local workstation | stop and escalate on missing npm |
| Python 3 | `python3 --version` | workstation-managed install | local workstation | stop and escalate on missing Python |
| Member-account deploy access | `aws sts get-caller-identity --query Account --output text` | configure AWS profile in `.envrc` or shell env | AWS account `530267068969` | stop if shared stack cannot be deployed/read |
| Management-account access | `aws sts get-caller-identity --query Account --output text` or successful `sts assume-role` | configure management-account profile or role ARN | AWS org management account `023016403424` | stop if enforce-mode SCP operations cannot run |

## Plan Overview (phases)

- Phase 1: Reconfirm brownfield baseline and keep the repo green. Proof: strict quality gates, targeted tests, and synth all pass before live AWS work.
- Phase 2: Make management-account auth explicit in the shared bootstrap/guard path. Proof: bootstrap and guard tests cover the new contract, and live enforce-mode guard application succeeds without a manual second workflow.
- Phase 3: Capture live shared-runtime evidence for both workflows. Proof: PP and SDLC both execute against the same endpoint with the expected governance behaviors and audit traces.
- Phase 4: Close redeployability and docs gaps. Proof: fresh-environment deployment/runbook inputs are explicit, and repo docs no longer contradict the implemented runtime/bootstrap state.

## Task Table (single source of truth)

Status keys:

- `@` = in progress
- `X` = done
- `!` = blocked
- blank = not started

| Status | Phase # | Task # | Type | Description |
| ------ | ------- | ------ | ---- | ----------- |
| pending | 1 | 1 | Read | Read `/Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/.plan/create-execplan/20260313-remaining-blockers/context-pack.md` and confirm frozen constraints before touching code. |
| pending | 1 | 2 | Gate | Run `bash scripts/run-ci-quality-gates.sh --lane=nightly-full` from repo root and record the exit code and any deltas in Artifacts & Notes. |
| pending | 1 | 3 | Gate | Run `python3 -m pytest -q tests/test_bootstrap_shared_sandbox_script.py tests/test_apply_flutter_design_aws_guards_script.py` and `npm --prefix infra run cdk:synth`; if either fails, stop and fix before live AWS work. |
| pending | 2 | 4 | Read | Inspect `/Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/scripts/deploy/bootstrap-shared-sandbox.sh:8`, `/Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/scripts/deploy/bootstrap-shared-sandbox.sh:540`, `/Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/scripts/guards/apply-flutter-design-aws-guards.sh:6`, and `/Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/scripts/guards/apply-flutter-design-aws-guards.sh:420` to confirm where management-account auth inputs must be added or forwarded. |
| pending | 2 | 5 | Code | Edit `/Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/scripts/deploy/bootstrap-shared-sandbox.sh:8` and related argument parsing so bootstrap accepts explicit management-account profile or `--assume-role-arn` inputs and forwards them into the guard invocation at `/Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/scripts/deploy/bootstrap-shared-sandbox.sh:553`. |
| pending | 2 | 6 | Code | Edit `/Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/tests/test_bootstrap_shared_sandbox_script.py:164` and `/Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/tests/test_apply_flutter_design_aws_guards_script.py:268` to cover the new auth wiring and a successful enforce-mode path when valid management-account auth is available. |
| pending | 2 | 7 | Gate | Verify management-account auth before live enforcement using `aws sts get-caller-identity --query Account --output text` or the configured assume-role path. If the result cannot reach `023016403424` or valid temp creds, mark Blocked and stop. |
| pending | 2 | 8 | Action | Run `./scripts/deploy/bootstrap-shared-sandbox.sh --deployment-environment sandbox --aws-profile 530267068969_AdministratorAccess --guard-assume-role-arn arn:aws:iam::023016403424:role/flutter-design-guards` and confirm the flow completes end-to-end without a separate manual SCP step. Record runtime id, endpoint name, and guard PASS output. |
| pending | 3 | 9 | Action | Invoke the shared runtime endpoint for `player-protection-case-orchestrator@1.0.0` and confirm PP evidence shows audit before regulated write plus HITL-gated execution, using `/Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/runtime/engine.py:128` and `/Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/workflow-contracts/player-protection-case-handling.json:10` as behavior anchors. |
| pending | 3 | 10 | Action | Invoke the same shared runtime endpoint for `pr-verifier-orchestrator@1.0.0` and confirm SDLC evidence shows governed internal writeback only after human approval, using `/Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/runtime/engine.py:172` and `/Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/workflow-contracts/pr-verification-review.json:10` as behavior anchors. |
| pending | 3 | 11 | Test | Re-run `python3 -m pytest -q tests/test_bootstrap_shared_sandbox_script.py tests/test_apply_flutter_design_aws_guards_script.py tests/test_shared_workflow_runtime.py tests/test_agentcore_main.py` after live close-out changes to catch regression in deploy/runtime surfaces. |
| pending | 4 | 12 | Code | Align repository docs/runbook text by updating `/Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/README.md:14` and any bootstrap guidance needed so the repo description matches the implemented shared runtime/bootstrap state and the management-account deploy contract. |
| pending | 4 | 13 | Action | Document fresh-environment inputs and the one-command completion path in `/Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/.plan/create-execplan/20260313-remaining-blockers/execplan.md:167`, including which values are environment-specific versus code-fixed (`eu-west-1`, stack name, runtime name pattern, endpoint name). |
| pending | 4 | 14 | Gate | Run the final proof set: `bash scripts/run-ci-quality-gates.sh --lane=nightly-full`, `npm --prefix infra run cdk:synth`, and the bootstrap command with management-account auth, then capture PASS evidence for repo gates, synth, runtime endpoint readiness, and SCP guards. |

## Progress Log (running)

- (2026-03-14T00:08:39Z) Requirements freeze confirmed by user; brownfield context pack and draft execplan updated to capture the management-account auth wiring suggestion and the README/docs alignment knock-on task.

## Decision Log

- Decision: Keep the scope as brownfield close-out, not architecture redesign.
  - Rationale: The repo already contains the shared runtime, workflow artifacts, bootstrap scripts, tests, and deployed sandbox; only operational completion remains.
  - Date: 2026-03-14
- Decision: Treat management-account access as a hard dependency.
  - Rationale: The live blocker is an Organizations permission boundary; it cannot be solved by repo-only changes or by weakening guard enforcement.
  - Date: 2026-03-14
- Decision: Add docs-alignment as a required completion task.
  - Rationale: README runtime-status wording now contradicts the implemented runtime/bootstrap state and would mislead later executors.
  - Date: 2026-03-14

## Execution Findings

- Finding: Shared sandbox deployment is already successful from member account `530267068969`; live completion is blocked only at SCP enforcement.
- Evidence: `/Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/.plan/create-execplan/20260313-remaining-blockers/workspace/context-evidence.json`
- Decision link: Management-account access is a hard dependency
- User approval (required if this introduces new discovery scope): not required; within frozen close-out scope

## Test Plan

| Scenario ID | Req IDs | Priority | Given | When | Then | Evidence Command | Task Ref |
| ----------- | ------- | -------- | ----- | ---- | ---- | ---------------- | -------- |
| S1 | R1 | P0 | smoke baseline exists in the brownfield repo | `nightly-full` is run from repo root | smoke validation proves the strict repo baseline is still green before AWS close-out work | `bash scripts/run-ci-quality-gates.sh --lane=nightly-full` | P1-T2 |
| S2 | R6,R3 | P0 | management-account auth wiring is added to bootstrap | the shared bootstrap is run with management-account auth inputs | live SCP enforcement passes without a manual second workflow | `./scripts/deploy/bootstrap-shared-sandbox.sh --deployment-environment sandbox --aws-profile 530267068969_AdministratorAccess --guard-assume-role-arn arn:aws:iam::023016403424:role/flutter-design-guards` | P2-T8 |
| S3 | R2,R4 | P0 | the shared runtime endpoint is READY | PP orchestrator is invoked through `/invocations` | HITL-gated regulated write occurs only with audit evidence on the shared runtime | `curl -sS -X POST "$GATEWAY_URL/invocations" -H 'content-type: application/json' --data @build/e2e/pp-invocation.json` | P3-T9 |
| S4 | R2,R4 | P0 | the same shared runtime endpoint is READY | SDLC orchestrator is invoked through `/invocations` | internal writeback occurs only after human approval and remains on the shared runtime | `curl -sS -X POST "$GATEWAY_URL/invocations" -H 'content-type: application/json' --data @build/e2e/sdlc-invocation.json` | P3-T10 |
| S5 | R5 | P1 | docs and deploy contract are aligned | the final close-out proof set is run | repo docs and one-command deploy evidence support fresh-environment redeployability | `bash scripts/run-ci-quality-gates.sh --lane=nightly-full && npm --prefix infra run cdk:synth` | P4-T12,P4-T14 |

## Quality Gates

| Gate | Command | Expectation |
| ---- | ------- | ----------- |
| Smoke | `bash scripts/run-ci-quality-gates.sh --lane=nightly-full` | strict repo baseline passes |
| Lint/Test | `python3 -m pytest -q tests/test_bootstrap_shared_sandbox_script.py tests/test_apply_flutter_design_aws_guards_script.py tests/test_shared_workflow_runtime.py tests/test_agentcore_main.py` | targeted deploy/runtime regressions pass |
| Infra | `npm --prefix infra run cdk:synth` | synth passes in `eu-west-1` |
| Live Deploy | `./scripts/deploy/bootstrap-shared-sandbox.sh --deployment-environment sandbox --aws-profile 530267068969_AdministratorAccess --guard-assume-role-arn arn:aws:iam::023016403424:role/flutter-design-guards` | runtime endpoint converges and guard enforcement passes |

## Idempotence & Recovery

- Safe to re-run:
  - `nightly-full`
  - targeted pytest commands
  - `npm --prefix infra run cdk:synth`
  - bootstrap script against the same deployment environment when the runtime/endpoint already exist
- Recovery behavior:
  - If management-account auth fails, stop before attempting enforce-mode SCP mutation and record the exact failure.
  - If bootstrap deploy succeeds but guard enforcement fails, treat it as incomplete close-out and do not declare deployment complete.
  - Do not perform manual console changes to “patch” drift; update the scripted deploy contract instead.

## Artifacts & Notes

- Context Pack: `/Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/.plan/create-execplan/20260313-remaining-blockers/context-pack.md`
- Evidence: `/Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/.plan/create-execplan/20260313-remaining-blockers/workspace/context-evidence.json`
- Draft review notes: `/Users/adamjackson/.codex/worktrees/a425/flutter-aws-poc/.plan/create-execplan/20260313-remaining-blockers/workspace/draft-review.md`
- Live completion cannot be signed off until management-account auth is available and the guard script reports `PASS` for both SCP controls.
