# SDLC Use Case For This Baseline

The Flutter architecture supports agentic SDLC workflows, but this repository currently enforces only the contract and governance side of that model.

## Current Repo Role

This repo is the place to define and verify:

- Capability Definitions for SDLC agents
- Safety Envelopes for engineering write actions
- Workflow Contracts for governed review or approval flows
- Evaluation Packs that prove publish readiness

It is not yet the place where the SDLC agent runtime exists.

## Best-Fit First Use Case

The best first governed SDLC slice remains a review and verification workflow, for example:

- `pr-verifier-orchestrator`
- `diff-review-specialist`
- `test-impact-specialist`
- `engineering-standards-specialist`

That aligns with the architecture docs and with the retained repo controls:

- contract schemas define the publishable unit
- identity requirements enforce tenant-safe tool usage
- workflow contracts become mandatory at higher risk tiers
- evaluation packs provide publish evidence

## What This Baseline Should Enforce

Before any SDLC agent implementation is considered valid, the repo should be able to reject:

- missing identity tags
- direct non-gateway model routing
- published capabilities with no evaluation evidence
- process or higher-risk capabilities with no workflow contract
- contract sets whose datasets or references do not resolve

That is why the baseline is built around fixture-driven behavioral tests instead of source-code markers.

## Practical Implication

If a future SDLC slice wants to add runtime code, it should follow this order:

1. define the contracts
2. add invalid fixtures that prove the guards fail
3. add valid fixtures that prove the publish path
4. only then implement runtime behavior

This keeps the repo aligned with the architecture’s agentic-development posture instead of drifting back into an implementation-first PoC.
