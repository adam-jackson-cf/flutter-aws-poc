# Example Brief: A2A-Orchestrated SDLC Verification Workflow Through the MCP Gateway

## Purpose
This brief defines one worked SDLC example that exercises the Flutter UKI Enterprise AI Platform design from authoring through production runtime, governance, evaluation, observability, costing, marketplace publication, and downstream team fork/reuse.

It does not introduce a new architecture. It is a source-backed alternative to the player-protection brief, using a software-development-lifecycle scenario that fits the platform’s hosted control-plane model more naturally.

## Example Summary
The Flutter Engineering Productivity team builds `pr-verifier-orchestrator`, a governed SDLC capability that reviews pull requests, gathers code and policy evidence, delegates specialist analysis, synthesizes findings, and optionally posts governed review outputs back to engineering systems.

This scenario is intentionally framed as **hosted verification and controlled engineering writeback**, not as a replacement for local coding loops.

The orchestrator:

- uses `Reasoning + Coordination + Process`
- delegates to specialist capabilities using A2A-compatible capability-to-capability invocation
- uses the `MCP Gateway` for GitHub, CI, issue-tracker, and documentation access
- uses RAG for engineering standards, architecture policy, and testing guidance
- uses optional HITL before sensitive engineering write actions such as remediation-branch proposal or required-status override
- produces nested traces, immutable audit records, and real-time cost attribution
- is later published to the marketplace and forked by another engineering team with repo-specific bindings

This is the smallest SDLC example that still exercises the maximum amount of the Flutter design.

## Dedicated Design Gap Callout

These are not gaps in the brief. They are the main gaps or ambiguities still present in the underlying Flutter design that affect this SDLC example directly.

| Gap | Current state in design | Why it matters for this example |
| --- | --- | --- |
| A2A operating contract | A2A is named strategically, but the docs define coordination mainly as agents-as-tools or LangGraph rather than a wire-level A2A contract | The orchestrator can describe delegation, but message shape, auth, retries, and compatibility rules are not yet fixed |
| Marketplace fork and rating model | Discovery, peer review, and version pinning are defined; fork lineage, ratings, and migration semantics are not | Cross-team reuse is central to the SDLC story, but the consuming-team operating model is only partially specified |
| Prompt immutability model | The docs describe both version-pinned capability prompts and runtime prompt-library retrieval/A-B testing | The platform needs one publish-time truth model to preserve `what was evaluated is what runs` |
| SDLC risk-tier fit | The generic `R0-R3` model fits business workflows better than engineering write workflows | PR comments and check-run writes fit `R1`, but repo-write and merge-adjacent actions may need a stricter SDLC control profile |
| Ephemeral code workspace capability | The design supports review and tool orchestration, but does not define a hosted code-workspace runner | Hosted verification is credible today; serious hosted remediation is not, unless an isolated workspace component is added |
| Cross-stack observability correlation | Langfuse, CloudWatch, CloudTrail, Audit Records, and Step Functions are all defined; OTEL/correlation standardization is still pending | This example spans review, CI, tool routing, and optional process execution, so investigation and export need one canonical correlation model |
| Evaluation evidence normalization | Multiple evaluation frameworks are allowed, but minimum evidence schema and tier thresholds are not unified | Review quality and runtime success need one platform-standard evidence contract |
| End-to-end FinOps model | LLM token cost attribution is strong; connector, workflow, and verification-run cost attribution are less defined | Full chargeback for hosted SDLC workflows is not yet complete |

## Capability Topology

| Capability | Owning team | Risk Tier | Execution Model | Purpose |
| --- | --- | --- | --- | --- |
| `pr-verifier-orchestrator` | Engineering Productivity | R1 | Reasoning + Coordination + Process | End-to-end PR review, specialist orchestration, controlled engineering writeback |
| `diff-review-specialist` | Engineering Productivity | R0 | Reasoning | Identifies code issues, regressions, and risky changes |
| `test-impact-specialist` | QE Platform | R0 | Reasoning | Infers impacted tests and missing coverage |
| `engineering-standards-specialist` | Architecture Enablement | R0 | Reasoning | Retrieves standards, policy, and architecture rules with citations |
| `ci-triage-specialist` | DevEx / CI Platform | R0 | Reasoning | Interprets CI failures and flaky-signal history |

Common design-time artefacts:

- a `Capability Definition` for each capability
- a `Safety Envelope` version for each published capability
- one `Workflow Contract` for the orchestrator, because this SDLC variant deliberately uses Process scope for governed writeback and approval flow
- `Tool Bindings` for MCP tools and `RAG Source` bindings for engineering standards and internal docs
- `HITL Conditions` for the orchestrator
- attached `evaluation_results` before publish
- tenant budget and quota configuration in the LLM Gateway

## End-to-End Lifecycle

### 1. Authoring and workflow definition
Engineering Productivity engineers use the pro-code path in the IDE plugin to define the orchestrator and four specialists. Registry discovery supplies approved tool schemas, MCP servers, and RAG sources. A platform engineering reviewer or compliance-minded SDLC owner uses Workflow Studio to define the `Workflow Contract` for the orchestrator path: correlation ID, idempotency key, compensation path, ABAC boundary per step, and replay guarantees.

The resulting orchestrator definition contains, at minimum:

- system prompt reference/version
- specialist agent bindings
- tool bindings for GitHub, CI, issue tracker, and documentation operations
- standards and policy knowledge sources
- `Risk Tier = R1`
- `Execution Model = [Reasoning, Coordination, Process]`
- `Workflow Contract` reference
- `HITL Conditions`
- allowed model selection

### 2. Local development and safe test execution
Teams develop in Strands local mode with mocked L3 services, Registry discovery mocks, and sandbox MCP endpoints returning fixture responses. Test invocations run under a restricted IAM role with explicit deny on production engineering-system writes. This local path validates orchestration logic, tool schemas, structured review output, and benchmark scoring without side effects.

### 3. Evaluation and review
The pipeline moves the capability from `Draft` to `Review` only when evaluation evidence is attached. For this example, the minimum evaluation pack should include:

- Promptfoo regression suites for structured review output, known-issue detection, and false-positive control
- benchmark cases using seeded known issues, clean PR controls, and multi-file interaction cases
- pytest or Registry API contract tests for capability shape and publish rules
- workflow validation for idempotency, compensation, and HITL path correctness
- optional runtime dry-run evidence for the hosted path using sandbox MCP fixtures

For this SDLC case, the key publish metric should be **case pass rate**, not a vague narrative success score. A case passes only if the runtime succeeds, the schema is valid, required findings are present, and false positives stay below threshold.

### 4. Registry publish gate
The Registry enforces the platform invariants before publication:

- `I1`: nothing executes unless it is `Published`
- `I2`: no publish without `Safety Envelope` and `Risk Tier`
- `I3`: no tool invocation outside `Identity Context`
- `I4`: if Process scope is used, the workflow contract must be valid
- `I5`: every execution produces an `Audit Record`
- `I6`: `Safety Envelope` is immutable on publish

For this example, publication fails if any of the following are missing:

- declared `R1` risk tier
- attached workflow contract for the Process-scope variant
- attached evaluation results
- valid tool bindings
- valid safety envelope

### 5. Release tracks
The same published definition can go down two tracks:

- `Production`: used by engineering teams through IDE plugin, CI, or API clients
- `Marketplace`: published as a reusable capability for cross-team consumption

The production track is approved by the team’s delivery process. The marketplace track adds peer review outside the authoring team and uses version pinning for consuming capabilities.

## Runtime Execution Walkthrough

### 1. Identity establishment
A developer or CI service invokes governed review from the IDE plugin, CI, or API. Authentication flows through `Okta -> IAM Identity Center -> STS session tags`. The Lambda Authorizer validates the session with `GetCallerIdentity` and extracts the immutable `Identity Context`:

- `tenant_id`
- `brand`
- `role`
- `use-case`

For SDLC, the tenant/brand dimensions can map to an engineering org, business unit, or internal platform tenancy model rather than a consumer brand.

### 2. LLM Gateway entry and cost tagging
The request enters the `LLM Gateway`, which is the mandatory model boundary. The gateway:

- tags the request with `tenant_id`, `capability_id`, and `session_id`
- checks burst and sustained quota
- opens the cost record
- checks prompt cache
- routes to the permitted provider

This is where spend attribution starts.

### 3. Guardrails enforcement
The `Guardrails Service` enforces the published `Safety Envelope` on input before reasoning begins and again on output before the response is returned. For this workflow, that includes secrets/credential leakage prevention, prompt injection detection, repository-content policy limits, and output DLP. Guardrail outcomes become part of the immutable audit trail.

### 4. Capability resolution and agent start
The `Agent Runtime` resolves the exact published orchestrator version from the `Capability Registry`. No runtime override is allowed. The runtime loads:

- orchestrator capability version
- safety envelope version
- risk tier
- workflow contract reference
- specialist bindings
- model permissions

### 5. A2A-compatible coordination
The orchestrator reasons about what evidence it needs and delegates to specialists:

- `diff-review-specialist` inspects the code diff and change topology
- `test-impact-specialist` identifies missing or required tests
- `engineering-standards-specialist` retrieves policy and architecture guidance with citations
- `ci-triage-specialist` reasons over recent failed jobs and flaky-signal history

The current design describes this most concretely as `agents-as-tools` or LangGraph coordination. In this brief, those delegated invocations are treated as the platform’s intended A2A-compatible pattern. Each delegated execution carries:

- stable subject identity
- `acting_as_capability_id`
- `invocation_chain`

Each specialist is still a separately governed published capability with its own definition, safety envelope, and audit trail.

### 6. MCP and RAG access inside the execution
The specialists and orchestrator use two context paths:

- `RAG`: engineering standards, coding guidelines, security rules, test policy, and architecture docs
- `MCP`: live reads and controlled writes against GitHub, CI, issue tracker, and documentation systems

Every tool call flows through the `MCP Gateway`. The gateway:

- validates ABAC against the `Identity Context` and active tool bindings
- performs RFC 8693 token exchange
- issues a fresh tool-scoped credential per call
- routes the call under PrivateLink-controlled or centrally governed egress
- writes tool activity into traces and audit

The downstream tool never sees the user’s raw identity. It sees only the scoped token for that operation.

### 7. Process scope, HITL, and controlled engineering writeback
Because this variant deliberately uses Process scope, the outer flow is executed by `Step Functions` using the published workflow contract. The durable workflow:

- persists correlation and state between steps
- checks idempotency before write actions
- supports compensation if a later step fails
- pauses at `waitForTaskToken` when the workflow is configured to post high-impact engineering outputs, such as remediation-branch proposals or merge-blocking status overrides

Once the reviewer approves, the orchestrator can execute controlled internal write actions such as:

- posting PR review comments
- publishing a check-run status
- annotating a Jira ticket with findings
- recording a remediation proposal artifact

For normal SDLC review flows this remains `R1`, but the platform may still choose to enforce stronger HITL than the base risk model requires.

### 8. Response, close, and evidence
The final response is returned to the IDE, CI, or API caller as a structured review package. The execution closes only after:

- output guardrails complete
- audit writes succeed
- Step Functions state is updated
- cost is finalized
- traces are closed

## Observability, Audit, and Costing

This example deliberately exercises all five observability layers defined in the design.

| Layer | What this example produces |
| --- | --- |
| Langfuse | nested trace tree: orchestrator span -> specialist spans -> tool spans -> LLM spans |
| CloudWatch | latency, error rate, tool failures, quota state, circuit breaker state, per-capability cost |
| CloudTrail | proof of AssumeRole/session tags, Registry publish events, audit-store events, KMS usage |
| Audit Record | immutable execution fact set with capability version, safety version, tool calls, guardrails, cost, delegation chain |
| Step Functions history | full workflow graph, HITL decision record when used, compensation path for failed writeback |

For this example, the audit record should include:

- `execution_id`
- `correlation_id`
- `identity_context`
- `capability_version` and SHA-256
- `safety_envelope_version`
- full `invocation_chain`
- tool parameters and response hashes
- `hitl_record` when approval is required
- token counts and attributed cost
- structured review output hash

Costing is tracked in real time at the `tenant_id / capability_id / session_id` level. The example therefore supports:

- quota enforcement before model spend occurs
- prompt-cache savings visibility
- per-capability and per-team spend dashboards
- hard budget caps with a tenant circuit breaker
- immutable cost evidence in the audit record

## Marketplace Publication and Consuming-Team Fork

After proving the orchestrator in Engineering Productivity production, the team publishes it to the marketplace as a reusable capability package.

The Sportsbook Platform team then forks it to create `sportsbook-pr-verifier-orchestrator`. The consuming-team workflow should be:

1. Discover the published capability through marketplace/registry access controlled by ABAC.
2. Fork the capability into a new team-owned definition and version lineage.
3. Rebind repo-specific RAG sources, engineering policies, and tool policies.
4. Keep specialist dependencies explicitly version-pinned.
5. Re-run evaluation and publish through the same Registry gate.
6. Release through that team’s chosen surfaces: IDE plugin, CI, or API clients.

This gives Flutter the reuse path the narrative is aiming for: one governed SDLC pattern, multiple governed engineering-team deployments.

## Coverage Against the Flutter Design

| Design area | Covered by this example |
| --- | --- |
| L5 surfaces | IDE plugin, CI, and API use for runtime; IDE plugin and Workflow Studio for authoring; marketplace for reuse |
| L4 authoring | Pro-code orchestrator/specialists; workflow authoring for process contract; constrained reuse/fork path for consuming teams |
| L3 contract boundary | LLM Gateway, Guardrails, Agent Runtime, MCP Gateway, Capability Registry, Workflow Engine, HITL, Audit |
| L2 data and knowledge | Engineering-policy retrieval plus live GitHub/CI/internal-doc connectors |
| L1 foundations | Okta, IAM Identity Center, STS session tags, KMS, Secrets Manager, VPC/PrivateLink, CloudWatch, CloudTrail |
| Governance | Risk tiering, safety envelope, workflow contract, lifecycle gate, publish invariants, version pinning |
| Security | immutable identity context, ABAC, RFC 8693 token exchange, scoped tool credentials |
| Observability | Langfuse, CloudWatch, CloudTrail, Audit Records, Step Functions history |
| FinOps | real-time token attribution, quota enforcement, circuit breaker, spend dashboards |
| Cross-team reuse | marketplace publication, peer review, discovery, fork, consuming-team deployment |

## Detailed Gap Notes

The design set is strong on invariants and runtime control points, but it is not gap-free. These items should be resolved before this example is treated as a reference operating model.

### 1. A2A is named strategically but not specified operationally
The docs clearly define coordination through `agents-as-tools` and LangGraph, but they do not define a wire-level A2A contract. The design needs one explicit answer to the following:

- is A2A an internal capability-invocation contract, an external protocol, or both
- what is the message schema
- how are auth, correlation IDs, retries, timeouts, and error semantics propagated
- how versioning works for agent-to-agent compatibility

### 2. Marketplace fork, rating, and consumption rules are underspecified
The narrative promises capabilities that are discoverable, rated, versioned, shareable, and forkable across teams. The detailed views only define peer review, ABAC-based discovery/invocation, and version pinning. The design still needs:

- fork inheritance rules
- provenance and lineage rules
- rating/review semantics
- approval rules for a fork versus a direct invoke
- deprecation and migration UX for consuming teams

### 3. Prompt immutability needs a single source-of-truth model
One part of the design treats `System Prompt` as a field of the `Capability Definition`, while another says prompts are never hardcoded in capability definitions and are retrieved from a prompt library with versioning and A/B testing. To preserve `what was evaluated is what runs`, the platform should define one explicit model:

- prompt reference stored in the capability definition
- prompt content hash pinned at publish
- A/B experiments only allowed when the experiment set itself is versioned and evaluated

Without that, prompt A/B testing conflicts with publish immutability.

### 4. SDLC use cases need a clearer control profile
The base `R0-R3` taxonomy can host SDLC review and internal engineering writes, but it does not yet cleanly express engineering-governance risk. The design should clarify:

- whether PR comments, check-run writes, and branch-update proposals all remain `R1`
- whether SDLC workflows need a stricter engineering-specific approval profile
- when optional Process scope and HITL should be mandatory for engineering writeback

### 5. Hosted remediation needs an ephemeral workspace runner
Hosted verification is supported by the current design shape. Hosted code remediation is not well-defined without an isolated code-workspace component providing:

- repo clone at pinned commit
- file read/search/build/test/apply-patch tools
- no production credentials
- governed writeback only through approved repo tools

### 6. Evaluation evidence is not normalized enough
The design allows Promptfoo, LangSmith, Bedrock Evaluation, and pytest, but it does not define the minimum evidence schema or the publish thresholds by risk tier. For SDLC agents, the platform should standardize:

- structured review output schema
- case pass-rate rules
- false-positive limits
- known-issue benchmark composition
- storage shape for attached evaluation evidence

### 7. End-to-end FinOps for SDLC is stronger for tokens than for full review workflow cost
The LLM cost model is well-defined. The design is much less explicit on:

- GitHub/API cost attribution
- CI-log and artifact retrieval cost attribution
- Step Functions and reviewer-cost attribution
- ephemeral-workspace execution cost attribution if hosted remediation is added

## Recommended Next Step
Treat this example as the SDLC reference acceptance scenario for the platform and convert it into a formal conformance pack:

- golden capability definitions for orchestrator and specialists
- a workflow contract specimen
- a structured review output schema
- a seeded PR benchmark set
- Promptfoo and runtime-eval acceptance tests
- a marketplace fork acceptance checklist

That would turn the SDLC architecture story from a plausible extension into a testable platform contract.
