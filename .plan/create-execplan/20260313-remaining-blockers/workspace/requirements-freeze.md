# Requirements Freeze

- Created: 2026-03-13
- Last updated: 2026-03-14T00:08:39Z

## Captured Inputs Playback

- Scope and user-visible outcomes:
  - Produce an execplan that captures the single remaining blocker and the follow-on tasks needed to complete the shared PP + SDLC platform implementation and deployment.
  - Make the blocker explicit enough that a later executor can finish the work without rediscovering the same AWS/account issues.
  - Include the additional suggested change: wire management-account access into the deployment/bootstrap path so SCP enforcement can become part of the deterministic deploy flow instead of a manual follow-up.
- Constraints and non-goals:
  - Keep to the already-selected architecture: one shared platform instance, two workflows, no extra scenario isolation.
  - Keep deployment IaC-first and `eu-west-1` only.
  - Do not reopen completed implementation work unless a remaining blocker proves it incomplete.
  - Non-goal: redesigning the platform, changing scenario scope, or introducing a second topology.
- User-provided artifacts and starting views:
  - Current working tree with implemented contracts, runtime, infra, deploy scripts, tests, and README guidance.
  - Live sandbox deployment outcome from the member account.
  - Prior session decisions on risk tiers, workflow scope, and shared-platform topology.
- Assumptions to validate with user:
  - The execplan should focus on close-out work only.
  - The remaining blocker is management-account SCP enforcement capability, not application/runtime correctness.
  - Follow-on tasks should include both technical completion and deployment-operational completion.

## Frozen Requirements

- R1: Record that the repo implementation is complete enough to pass `nightly-full` locally.
- R2: Record that the shared sandbox runtime, endpoint, bootstrap resources, artifact upload, and stack deployment have succeeded in AWS account `530267068969`.
- R3: Record that the remaining live blocker is enforced SCP guard application because the available local credentials do not have Organizations policy-management permissions for management account `023016403424`.
- R4: Record the exact follow-on tasks needed to complete deployment close-out once management-account access is available.
- R5: Keep the final completion path compatible with redeploying the same solution into a fresh environment by configuration and IaC rather than manual rebuild.
- R6: Make management-account profile or `--assume-role-arn` wiring an explicit completion item so deploy plus live guard enforcement can be run as one deterministic workflow.

## Verification Decision

- Existing verification present: yes
- If missing, user decision (`approved-change-scoped`|`declined-blocked`|`n/a-existing`): n/a-existing
- Minimum smoke gate command: `bash scripts/run-ci-quality-gates.sh --lane=nightly-full`

## Confirmation

- Confirmation prompt: Confirm the requirements playback in `workspace/requirements-freeze.md` is final and I should proceed to context analysis.
- Confirmed by user at: 2026-03-14T00:08:39Z
- User approval response (verbatim excerpt): `confirmed and include that additional suggested change`
- Confirmation note: Requirements freeze approved. Proceed to Step 2 brownfield context analysis and Step 3 draft creation without reopening settled architecture decisions.
