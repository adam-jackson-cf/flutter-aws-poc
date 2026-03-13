# Flutter Design Validation

## Scope

This document validates the Flutter UKI AI platform design set under `docs/flutter-uki-ai-platform-arch` against the stated objective of delivering a governed, multi-tenant AI control plane that is safe, auditable, interoperable, reusable across brands, and operable in regulated environments.

Reviewed artefacts:

- `platform-narrative-v3.html`
- `architecture-overview-v9.html`
- `domain-model-v1.html`
- `hld-v4.html`
- `component-design-v2.html`
- `view-agent-lifecycle-v9.html`
- `view-orchestration-v5.html`
- `view-request-trace-v10.html`
- `view-security-identity-v7.html`
- `view-observability-v3.html`

## Ranking Method

- `Critical`: directly blocks the platform from proving its core governance, interoperability, or audit claims.
- `High`: materially weakens the design objective or creates a high risk of divergent implementation.
- `Medium`: does not block the objective immediately, but will create rework, operational ambiguity, or adoption drag.
- `Low`: secondary design debt or later-phase decision.

## Ranked Findings

| Rank | Risk     | Finding Type                               | Finding                                                                                                                                                                                                                                                                                                                                                                                                                   | Why it matters                                                                                                                                                                                                                                                                      | Source docs                                                                                                                                          |
| ---- | -------- | ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1    | Critical | Underspecified requirement / open decision | `A2A` is a strategic pillar, but there is no canonical operating contract. The docs describe coordination mainly as `agents-as-tools` or LangGraph rather than a concrete A2A invocation model.                                                                                                                                                                                                                           | Multi-agent interoperability, marketplace reuse, and future standards alignment are central to the objective. Without a defined contract, teams will build incompatible delegation patterns.                                                                                        | `platform-narrative-v3.html`, `architecture-overview-v9.html`, `view-orchestration-v5.html`                                                          |
| 2    | Critical | Contradiction                              | Publish immutability conflicts with runtime prompt-library retrieval and A/B testing. Some docs say prompts are version-pinned and immutable on publish; another says prompts are retrieved at runtime and can roll back without code deploy.                                                                                                                                                                             | This cuts directly across the claim that `what was evaluated is what runs`. If prompt behavior can drift after publish, auditability and evaluation evidence lose authority.                                                                                                        | `view-agent-lifecycle-v9.html`, `architecture-overview-v9.html`, `domain-model-v1.html`                                                              |
| 3    | Critical | Contradiction                              | The audit model is inconsistent. The domain model says one `Execution` produces one `Audit Record`, but the orchestration view says `R2/R3` audit records are written synchronously at each step.                                                                                                                                                                                                                         | Audit semantics are a core platform invariant. The platform cannot prove accountability until it decides whether process-scope runs create one audit artefact, step-level artefacts, or both.                                                                                       | `domain-model-v1.html`, `view-observability-v3.html`, `view-orchestration-v5.html`, `component-design-v2.html`                                       |
| 4    | High     | Contradiction / clarification needed       | The identity contract is inconsistent. The security view labels Flow 1 as `OIDC Authentication` but describes a SAML flow to IAM Identity Center. Tag schema also varies between `tenant_id, brand, role, use-case` and `tenant_id, brand, permission_scopes`.                                                                                                                                                            | Identity Context is the basis for ABAC, audit, and tool authorization. Conflicting auth protocol and tag-schema definitions will break enforcement and downstream policy design.                                                                                                    | `view-security-identity-v7.html`, `domain-model-v1.html`, `component-design-v2.html`, `architecture-overview-v9.html`, `view-request-trace-v10.html` |
| 5    | High     | Contradiction / underspecified requirement | MCP credential propagation is unclear. The design calls the tool auth step `RFC 8693 token exchange`, the security view shows OAuth token exchange semantics, and component design maps it to `sts.assume_role_with_web_identity` while also retrieving tool credentials from Secrets Manager.                                                                                                                            | Tool authorization is a non-negotiable boundary. The platform needs one precise credential chain so teams know what token is minted, what secret is used, and what the downstream system actually sees.                                                                             | `view-security-identity-v7.html`, `component-design-v2.html`, `domain-model-v1.html`                                                                 |
| 6    | High     | Gap / still to be decided                  | Non-Bedrock guardrail coverage is explicitly pending, even though multi-provider routing is a core design principle.                                                                                                                                                                                                                                                                                                      | The design cannot safely claim provider-agnostic routing for regulated workloads until control equivalence is defined provider by provider and risk tier by risk tier.                                                                                                              | `architecture-overview-v9.html`, `view-request-trace-v10.html`, `component-design-v2.html`, `hld-v4.html`                                            |
| 7    | High     | Gap                                        | The marketplace operating model is underspecified. The narrative promises discoverable, rated, shareable, forkable capabilities, but detailed views define only peer review, ABAC discovery/invocation, and version pinning.                                                                                                                                                                                              | Cross-brand reuse is one of the platform’s main strategic payoffs. Without fork, lineage, rating, and deprecation rules, the marketplace cannot operate as designed.                                                                                                                | `platform-narrative-v3.html`, `view-agent-lifecycle-v9.html`, `architecture-overview-v9.html`                                                        |
| 8    | High     | Underspecified requirement / gap           | The quality target itself is woolly. The docs set `Agent success rate >95%`, but do not define whether that means runtime completion, task-quality pass rate, benchmark recall, user satisfaction, or a composite metric.                                                                                                                                                                                                 | A target cannot govern delivery if teams can interpret it differently. This makes release gating, operational reporting, and optimisation claims non-comparable across capabilities.                                                                                                | `platform-narrative-v3.html`, `architecture-overview-v9.html`, `view-agent-lifecycle-v9.html`                                                        |
| 9    | High     | Gap                                        | The design mentions evaluation datasets, but does not define a dataset programme to achieve or sustain the claimed quality level. There is no canonical process for benchmark creation, curation, severity weighting, holdout sets, refresh cadence, or converting production misses into new regression cases.                                                                                                           | Without a dataset lifecycle, the platform has no credible path to optimise capabilities toward the stated quality target. Teams will default to ad hoc tests and reflective scoring rather than controlled benchmark improvement.                                                   | `component-design-v2.html`, `platform-narrative-v3.html`, `architecture-overview-v9.html`, `view-observability-v3.html`                              |
| 10   | High     | Underspecified requirement                 | The evaluation gate is not normalized enough. The docs allow Promptfoo, LangSmith, Bedrock Evaluation, and pytest, but do not define one required evidence schema or one threshold model by risk tier.                                                                                                                                                                                                                    | Governance depends on repeatable publish quality gates. If every team chooses a different evidence model, Registry approval is formally enforced but substantively inconsistent.                                                                                                    | `view-agent-lifecycle-v9.html`, `architecture-overview-v9.html`, `component-design-v2.html`, `domain-model-v1.html`                                  |
| 11   | High     | Gap / clarification needed                 | Risk-tier governance still relies heavily on team classification for `R1-R3`, and the docs explicitly state the platform cannot fully prevent misclassification beyond making it harder to do accidentally.                                                                                                                                                                                                               | Risk Tier drives every important control. If classification is the weakest part of the model, the platform’s regulatory safety claim is only as strong as manual team judgment.                                                                                                     | `domain-model-v1.html`, `platform-narrative-v3.html`, `view-agent-lifecycle-v9.html`                                                                 |
| 12   | Medium   | Contradiction                              | The provider catalogue is inconsistent across views. Some docs name Bedrock, Azure OpenAI, and Gemini; others name Bedrock, Anthropic direct, OpenAI, and Google/Vertex.                                                                                                                                                                                                                                                  | Teams cannot declare legal model routes or implement routing policy until the launch provider set is canonical. This also affects guardrail parity scope and Secrets Manager design.                                                                                                | `view-request-trace-v10.html`, `component-design-v2.html`, `hld-v4.html`, `architecture-overview-v9.html`                                            |
| 13   | Medium   | Still to be decided                        | Observability standardization is incomplete. Langfuse is described as the LLM trace authority, but OTEL integration is pending and cross-system correlation rules are not yet defined.                                                                                                                                                                                                                                    | The platform spans Langfuse, CloudWatch, CloudTrail, Step Functions, Splunk, and Audit Records. Without one correlation contract, incident response and evidence export will fragment quickly.                                                                                      | `architecture-overview-v9.html`, `view-observability-v3.html`, `hld-v4.html`, `component-design-v2.html`                                             |
| 14   | Medium   | Gap                                        | End-to-end FinOps and workflow viability are incomplete. Token attribution, budget caps, and quota controls are detailed, but connector/API cost, workflow cost, data-ingestion cost, and human-review cost are not first-class in the model, and there is no unit-economics framework defining what makes an agentic workflow viable, when optimisation is required, or when a workflow should not proceed beyond pilot. | The objective includes cost transparency, but metering spend is not the same as making good deployment decisions. For orchestrated enterprise workflows, teams need cost-per-successful-outcome measures, acceptable cost envelopes, and explicit optimisation/shutdown thresholds. | `view-observability-v3.html`, `architecture-overview-v9.html`, `component-design-v2.html`, `platform-narrative-v3.html`                              |
| 15   | Medium   | Clarification needed                       | Workflow Contract ownership is described as independently versioned and potentially compliance-owned, but compatibility, change control, and dependency pinning rules are not defined.                                                                                                                                                                                                                                    | Process scope is mandatory for `R2/R3`. If capability versions and workflow-contract versions evolve independently, teams need explicit compatibility and rollout rules.                                                                                                            | `domain-model-v1.html`, `view-agent-lifecycle-v9.html`, `view-orchestration-v5.html`, `architecture-overview-v9.html`                                |
| 16   | Medium   | Contradiction / clarification needed       | The networking story is imprecise. One view says there is no public internet egress from agents or MCP tool calls, while the HLD explicitly routes MCP tool calls and non-Bedrock provider traffic through central internet egress after firewall inspection.                                                                                                                                                             | This is likely reconcilable, but the docs need one precise statement: no direct public egress from workload VPCs versus no internet egress at all. The current wording can mislead implementation and security review.                                                              | `architecture-overview-v9.html`, `hld-v4.html`, `view-request-trace-v10.html`                                                                        |
| 17   | Medium   | Gap / still to be decided                  | Guided Assembly is part of the target platform shape, but the Assembly UI is still `planned` / `to be built`.                                                                                                                                                                                                                                                                                                             | Non-engineer authoring is part of the platform promise. If it remains undefined, delivery plans should treat it as a later phase, not an assumed MVP capability.                                                                                                                    | `architecture-overview-v9.html`, `view-agent-lifecycle-v9.html`                                                                                      |
| 18   | Low      | Still to be decided                        | The long-term vector-storage shape is not final. OpenSearch Serverless is primary, while `S3 Vectors` is evaluated positively but not committed.                                                                                                                                                                                                                                                                          | This does not block an MVP, but it does affect long-run cost, retention, and retrieval architecture. It should stay out of the first slice until a clear decision is needed.                                                                                                        | `architecture-overview-v9.html`                                                                                                                      |

## Follow-Up Questions

### Governance, lifecycle, and release

1. What is the single canonical `Capability Definition` schema, including prompt reference, workflow-contract reference, specialist bindings, HITL conditions, and model policy?
2. What exact artefacts must be attached for a capability to move from `Draft` to `Review` and from `Review` to `Published`?
3. What is the minimum evidence contract for the evaluation gate by risk tier?
4. What pass/fail thresholds are mandatory for `R0`, `R1`, `R2`, and `R3`?
5. What exactly does `Agent success rate >95%` mean for the platform: runtime completion, benchmark case pass rate, weighted task-quality score, user satisfaction, or a composite SLI/SLO?
6. Is the `>95%` target universal, or does each capability type and risk tier need its own quality metric and threshold?
7. What compensating controls exist for `R1 -> R2` or `R2 -> R3` misclassification?
8. Who has authority to approve a risk-tier declaration, and is that authority the same for production and marketplace tracks?
9. What is the required relationship between capability version, prompt version, workflow-contract version, and specialist-capability versions?
10. What is the deprecation and migration model for dependent capabilities when a specialist or contract version is retired?

### A2A, orchestration, and execution model

11. Is A2A an internal capability-to-capability contract, an external protocol, or both?
12. What is the canonical A2A message envelope: identity claims, correlation ID, capability ID/version, tool context, response shape, and error shape?
13. Does every delegated specialist call create a new `Execution` with its own audit record, or is delegation folded into a parent execution record?
14. For Process scope, is there one audit artefact per top-level execution, one per step, or both?
15. When should teams use `agents-as-tools` versus LangGraph?
16. Is the choice between LLM-driven coordination and graph-driven coordination a build-time decision, a runtime decision, or both?
17. What is the minimum supported topology for the first multi-agent release: one orchestrator plus one specialist, or something richer?
18. Can a tenant directly invoke another team’s published capability in marketplace mode, or must it fork first?

### Identity, security, and MCP

19. Is the canonical session-establishment protocol SAML, OIDC, or a hybrid, and which document should be treated as authoritative?
20. What exact session-tag schema is canonical for `Identity Context`?
21. Are `role` and `use-case` required tags, or are they represented inside `permission_scopes`?
22. What exact mechanism implements the so-called `RFC 8693` exchange?
23. Does the platform mint an OAuth token, an AWS role session, or a compound credential chain?
24. What credentials are stored in Secrets Manager for MCP tools: exchange client credentials, API keys, mTLS material, or all of the above?
25. What credential does the downstream MCP server receive and validate?
26. What does the downstream target system see: scoped token only, service principal, or a transformed delegation identity?
27. What is the canonical ABAC policy shape for tool discovery, tool invocation, and marketplace discovery?

### Prompts, guardrails, and model routing

28. What prompt manager is canonical for launch?
29. Does the capability definition store full prompt text, prompt reference, or prompt reference plus content hash?
30. Under what conditions, if any, are prompt A/B tests allowed on a published capability?
31. What is the launch provider catalogue for Bedrock and non-Bedrock routes?
32. Are Azure OpenAI and OpenAI treated as distinct supported routes, and if so, where is that made canonical?
33. Is phase-1 implementation Bedrock-only until non-Bedrock guardrail parity is proven?
34. What control-equivalence checklist must a non-Bedrock provider satisfy before it is allowed for each risk tier?

### Audit, observability, and costing

35. What is the canonical correlation ID that links Langfuse, CloudWatch, Audit Records, CloudTrail, Step Functions, and Splunk?
36. Will OTEL be adopted, bridged, or explicitly left out of scope?
37. What is the minimum audit-record schema for Reasoning-only, Coordination, and Process executions?
38. How are orchestrator cost, specialist cost, tool cost, and workflow cost rolled up for reporting and budget enforcement?
39. Are MCP/API charges, Step Functions charges, data-ingestion charges, and human-review effort part of chargeback?
40. What is the canonical unit-economics measure for a workflow: cost per execution, cost per successful case, cost per approved decision, or cost per business outcome?
41. What thresholds determine that a workflow is economically viable for pilot, scale-up, or shutdown/re-design?
42. What optimisation levers are expected before declaring a workflow non-viable: prompt caching, smaller models, specialist decomposition, tool-call limits, retrieval pruning, batching, or higher HITL routing?
43. Who owns the go/no-go decision when a workflow passes quality and safety gates but fails cost/value thresholds?
44. What evidence must be exportable for compliance review versus operational incident review?

### Marketplace and adoption

45. What is a marketplace fork technically: a copy, a derived capability with inheritance, or a new lineage with provenance metadata?
46. What metadata must survive the fork: origin capability, version lineage, dependency pins, evaluation pack, ratings?
47. Who can rate or review a marketplace capability, and what makes a rating trustworthy?
48. What is the difference between marketplace approval for direct consumption versus approval for forking?
49. What is the marketplace deprecation policy for capabilities already consumed by other teams?

### Delivery and rollout

50. Which authoring surfaces are mandatory for MVP, and which are explicitly post-MVP?
51. Is Guided Assembly part of the first production milestone or a later adoption phase?
52. What is the one acceptance workflow the platform must prove before expanding scope?
53. What measurable evidence will prove that the first workflow validated the platform objective rather than just demonstrating a happy path?
54. What benchmark datasets must exist for each capability type before the publish gate is considered real rather than reflective-only?
55. Who owns dataset creation, labelling, severity weighting, holdout management, and refresh cadence?
56. How are runtime misses, human corrections, and incident findings converted into new regression cases for the next release?

## Suggested Phased Implementation Approach

### Recommended Single Workflow

Use one workflow end to end: `player-protection-case-review`.

Why this workflow:

- it naturally needs orchestration, policy retrieval, live tool access, and durable governance
- it can start read-only and then be promoted to `R2`, then optionally `R3`, without changing the business narrative
- it exercises the platform’s core value proposition better than a generic FAQ or toy workflow

Recommended thin-slice shape:

- one orchestrator capability
- one specialist capability
- one RAG source
- one MCP read tool
- one MCP write tool
- one human approval gate
- one consumer surface
- one model provider for launch

### Phase 0: Contract Closure Before Build

Objective:
Freeze the platform contracts that are currently contradictory or still pending.

Close these findings first:

- A2A operating contract
- prompt immutability model
- audit granularity model
- identity/auth protocol and tag schema
- MCP credential chain
- launch provider catalogue
- evaluation evidence schema
- success metric semantics
- benchmark dataset lifecycle
- workflow unit-economics and optimisation policy

Deliverables:

- canonical `Capability Definition` schema
- canonical `Workflow Contract` schema
- A2A contract note
- identity and credential-sequence note
- evaluation evidence schema and thresholds
- benchmark dataset specification and ownership model
- unit-economics model and viability thresholds for the first workflow
- launch-provider policy and risk-tier matrix

Exit criteria:

- all critical findings and the high-risk evaluation/governance findings listed above have a decided target state
- the `>95%` target has a precise metric definition and benchmark method
- the first workflow has a defined unit-economics measure and optimisation/go-no-go threshold
- all source docs can be updated to one consistent story

### Phase 1: Bedrock-Only Read Slice of the Workflow

Objective:
Build the smallest governed path of `player-protection-case-review` as a read-only workflow.

Scope:

- Bedrock-only routing
- one orchestrator plus one specialist
- RAG for policy lookup
- one MCP read tool for player context
- Registry, LLM Gateway, Guardrails, Agent Runtime, MCP Gateway
- Langfuse, CloudWatch, Audit Record, CloudTrail
- one benchmark dataset with pass/fail grading for the workflow
- one explicit unit-economics measure for the workflow

Why this is the first slice:

- it proves the control-plane skeleton without taking write-path or provider-parity risk too early
- it validates identity propagation, MCP invocation, delegation, benchmarked evaluation, tracing, cost attribution, and a first unit-economics baseline

Exit criteria:

- capability can be authored, evaluated, published, invoked, and investigated end to end
- identity context is visible in audit and tool policy enforcement
- spend is attributed per tenant/capability/session
- benchmark case pass rate is measured against a fixed dataset rather than reflective scoring alone
- cost per successful workflow case is measured against a defined viability threshold

### Phase 2: Promote the Same Workflow to `R2`

Objective:
Turn the same workflow into the thinnest governed write path.

Scope:

- add one customer-adjacent write tool
- add `Workflow Contract`
- add Step Functions process execution
- add HITL threshold and approval callback
- enforce fail-closed audit semantics

Why `R2` before `R3`:

- it proves durable workflow governance, compensation, and HITL with lower regulatory blast radius
- it validates most of the platform’s process-scope claims before the strictest `R3` controls are introduced

Exit criteria:

- write path cannot execute without approved workflow contract and HITL rule
- process execution is observable in Step Functions, Langfuse, Audit Record, and CloudWatch
- compensation and replay are demonstrated in a forced-failure test

### Phase 3: Marketplace and Fork Validation in Non-Prod

Objective:
Prove the reuse model on the same workflow before broad rollout.

Scope:

- publish the `R2` workflow to marketplace
- fork it into a second tenant/brand in a controlled environment
- rebind brand-specific RAG source and tool policy
- verify version pinning, lineage, and approval semantics

Exit criteria:

- second team can discover, fork, evaluate, and publish the workflow without bypassing governance
- dependency versioning and deprecation behavior are understood in practice

### Phase 4: Multi-Provider and Observability Hardening

Objective:
Expand only after the control-equivalence decisions are made.

Scope:

- add one non-Bedrock route
- implement the provider-approval matrix
- finalize correlation strategy across Langfuse, CloudWatch, Audit, and CloudTrail
- decide OTEL posture

Exit criteria:

- the same workflow can run on at least two approved providers with known guardrail coverage
- incident investigation follows one documented correlation path

### Phase 5: Optional `R3` Hardening of the Same Workflow

Objective:
Prove the strictest governance path only after the platform is already stable at `R2`.

Scope:

- promote the workflow to a true regulated write path if the business case requires it
- enforce non-waivable HITL
- enforce write-ahead audit semantics
- test failure behavior for audit outage and compensation

Exit criteria:

- regulated write path halts correctly on audit failure
- write-ahead evidence is provable
- the platform can demonstrate its strongest governance claims under failure conditions

## Recommended Implementation Principle

Do not start with the full platform promise. Start with one Bedrock-only workflow, one canonical schema set, and one correlation model. Expand only after the contracts that carry governance meaning are made internally consistent.

That is the thinnest path that tests the platform objective without hiding unresolved design risk behind implementation effort.
