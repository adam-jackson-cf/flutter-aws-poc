# Executive Brief (Post-Deploy)

The PoC has improved evidence integrity, but current reliability outcomes are still below production expectations.

## What this PoC can credibly claim now

- It runs a real AgentCore MCP gateway path and a native path on the same evaluation harness.
- It deploys and updates AgentCore alpha CDK resources successfully in `eu-west-1`.
- Earlier contract/drift issues have been remediated:
  - nightly scheduler now includes `expected_tool`
  - eval runner now fails fast on artifact schema drift
  - MCP delimiter normalization regression fixed (`__` and `___`)

## What remains true

- Full Flutter architecture conformance is still not validated (workflow-contract semantics, HITL, immutable audit, end-to-end identity/ABAC observability).
- Protocol-only causality remains unproven without ablation.

## Current blocker profile

- Reliability is low in both routes on post-deploy runs.
  - Native tool failure remains high.
  - MCP tool failure remains higher and includes catalog/availability-related failure classes.

## Bid recommendation

Propose a two-phase follow-on:

1. **Reliability optimization + ablation (short tranche):**
   - isolate selector vs transport effects
   - reduce wrong-tool failures on both paths
   - produce confidence-bounded comparative metrics
2. **Architecture-conformance tranche:**
   - implement and evidence R2/R3 workflow contract semantics (compensation/HITL)
   - add immutable audit posture and identity-context observability proofs

This positions current work as a solid measurement foundation while keeping architecture claims technically accurate.

