# Example Brief: A2A-Orchestrated Player Protection Workflow Through the MCP Gateway

## Purpose
This brief defines one worked example that exercises the Flutter UKI Enterprise AI Platform design from authoring through production runtime, governance, evaluation, observability, costing, marketplace publication, and downstream team fork/reuse.

It does not introduce a new architecture. It is a source-backed example mapped onto the current design set under [`docs/flutter-uki-ai-platform-arch`](./).

## Example Summary
Paddy Power builds `player-protection-case-orchestrator`, a regulated `R3` capability that helps a safer-gambling operator review a player-protection case, gather evidence, obtain human approval, and execute an approved intervention.

The orchestrator:

- uses `Reasoning + Coordination + Process`
- delegates to specialist capabilities using A2A-compatible capability-to-capability invocation
- uses the `MCP Gateway` for live operational reads and writes
- uses RAG for policy and knowledge retrieval
- pauses on a mandatory HITL gate before any regulated write
- produces nested traces, immutable audit records, and real-time cost attribution
- is later published to the marketplace and forked by Betfair with brand-specific bindings

This is the smallest single example that touches the maximum amount of the Flutter design.

## Dedicated Design Gap Callout

These are not gaps in the brief. They are the main gaps or ambiguities still present in the underlying Flutter design that affect this example directly.

| Gap | Current state in design | Why it matters for this example |
| --- | --- | --- |
| A2A operating contract | A2A is named strategically, but the docs define coordination mainly as agents-as-tools or LangGraph rather than a wire-level A2A contract | The orchestrator can describe delegation, but message shape, auth, retries, and compatibility rules are not yet fixed |
| Marketplace fork and rating model | Discovery, peer review, and version pinning are defined; fork lineage, ratings, and migration semantics are not | Cross-brand reuse is central to the example, but the consuming-team operating model is only partially specified |
| Prompt immutability model | The docs describe both version-pinned capability prompts and runtime prompt-library retrieval/A-B testing | The platform needs one publish-time truth model to preserve `what was evaluated is what runs` |
| Non-Bedrock guardrail equivalence | Bedrock guardrails are concrete; non-Bedrock equivalence is still pending | Risk-tier approval for multi-provider routing is incomplete without provider-by-provider control mapping |
| Cross-stack observability correlation | Langfuse, CloudWatch, CloudTrail, Audit Records, and Step Functions are all defined; OTEL/correlation standardization is still pending | This example spans all five layers, so investigation and export contracts need one canonical correlation model |
| Evaluation evidence normalization | Multiple evaluation frameworks are allowed, but minimum evidence schema and tier thresholds are not unified | Publish rigor is risk-tier-driven, but teams do not yet have one platform-standard evidence contract |
| End-to-end FinOps model | LLM token cost attribution is strong; connector, workflow, and HITL cost attribution are less defined | Full chargeback for orchestrated regulated workflows is not yet complete |
| Guided Assembly operating model | Guided Assembly exists architecturally, but the detailed workflow is still planned | The non-engineer authoring story is part of the platform promise, but not yet operationally complete |

## Capability Topology

| Capability | Owning team | Risk Tier | Execution Model | Purpose |
| --- | --- | --- | --- | --- |
| `player-protection-case-orchestrator` | Paddy Power Safer Gambling | R3 | Reasoning + Coordination + Process | End-to-end case handling, approval flow, and regulated action execution |
| `customer-360-specialist` | Paddy Power Customer Ops | R0 | Reasoning | Reads account, activity, KYC, and support context |
| `rg-policy-specialist` | Central Compliance | R0 | Reasoning | Retrieves policy and control guidance with citations |
| `affordability-signals-specialist` | Risk Ops | R0 | Reasoning | Reads affordability and exposure signals |

Common design-time artefacts:

- a `Capability Definition` for each capability
- a `Safety Envelope` version for each published capability
- one `Workflow Contract` for the `R3` orchestrator
- `Tool Bindings` for MCP tools and `RAG Source` bindings for policy and brand knowledge
- `HITL Conditions` for the orchestrator
- attached `evaluation_results` before publish
- tenant budget and quota configuration in the LLM Gateway

## End-to-End Lifecycle

### 1. Authoring and workflow definition
Paddy Power engineers use the pro-code path in the IDE plugin to define the orchestrator and the three specialists. Registry discovery supplies approved tool schemas, MCP servers, and RAG sources. The safer-gambling compliance architect uses Workflow Studio to define the `Workflow Contract` for the `R3` orchestration path: correlation ID, idempotency key, compensation path, ABAC boundary per step, and replay guarantees.

The resulting orchestrator definition contains, at minimum:

- system prompt reference/version
- specialist agent bindings
- tool bindings for read and write MCP operations
- policy and brand knowledge sources
- `Risk Tier = R3`
- `Execution Model = [Reasoning, Coordination, Process]`
- `Workflow Contract` reference
- `HITL Conditions`
- allowed model selection

### 2. Local development and safe test execution
Teams develop in Strands local mode with mocked L3 services, Registry discovery mocks, and sandbox MCP endpoints returning fixture responses. Test invocations run under a restricted IAM role with explicit deny on production writes. This is the design-time path that lets teams validate orchestration logic and tool schemas without side effects.

### 3. Evaluation and review
The pipeline moves the capability from `Draft` to `Review` only when evaluation evidence is attached. For this example, the minimum evaluation pack should include:

- Promptfoo regression suites for behavior, jailbreak resistance, and delegation quality
- Bedrock Evaluation for RAG faithfulness and citation quality
- pytest or Registry API contract tests for capability shape and publish rules
- R3-specific legal, compliance, and write-ahead audit validation
- workflow validation for idempotency, compensation, and HITL path correctness

The design is explicit that runtime guardrails do not replace capability-quality evaluation. They are separate controls.

### 4. Registry publish gate
The Registry enforces the platform invariants before publication:

- `I1`: nothing executes unless it is `Published`
- `I2`: no publish without `Safety Envelope` and `Risk Tier`
- `I3`: no tool invocation outside `Identity Context`
- `I4`: `R2/R3` requires a valid `Workflow Contract`
- `I5`: every execution produces an `Audit Record`
- `I6`: `Safety Envelope` is immutable on publish

For this example, publication fails if any of the following are missing:

- declared `R3` risk tier
- attached workflow contract
- attached evaluation results
- valid tool bindings
- valid safety envelope

### 5. Release tracks
The same published definition can go down two tracks:

- `Production`: used by Paddy Power through Chat UI, Slack/Teams, or API clients
- `Marketplace`: published as a reusable capability for cross-brand consumption

The production track is approved by the team’s delivery process. The marketplace track adds peer review outside the authoring team and uses version pinning for consuming capabilities.

## Runtime Execution Walkthrough

### 1. Identity establishment
An operator opens the safer-gambling case tool in Chat UI or Slack. Authentication flows through `Okta -> IAM Identity Center -> STS session tags`. The Lambda Authorizer validates the session with `GetCallerIdentity` and extracts the immutable `Identity Context`:

- `tenant_id`
- `brand`
- `role`
- `use-case`

This context becomes the ABAC input for the entire execution.

### 2. LLM Gateway entry and cost tagging
The request enters the `LLM Gateway`, which is the mandatory model boundary. The gateway:

- tags the request with `tenant_id`, `capability_id`, and `session_id`
- checks burst and sustained quota
- opens the cost record
- checks prompt cache
- routes to the permitted provider

This is where spend attribution starts.

### 3. Guardrails enforcement
The `Guardrails Service` enforces the published `Safety Envelope` on input before reasoning begins and again on output before the response is returned. For this workflow, that includes PII handling, denied topics, prompt injection detection, and DLP on output. Guardrail outcomes become part of the immutable audit trail.

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

- `customer-360-specialist` gathers account and interaction context
- `rg-policy-specialist` retrieves policy rationale and citations
- `affordability-signals-specialist` gathers supporting risk signals

The current design describes this most concretely as `agents-as-tools` or LangGraph coordination. In this brief, those delegated invocations are treated as the platform’s intended A2A-compatible pattern. Each delegated execution carries:

- stable subject identity
- `acting_as_capability_id`
- `invocation_chain`

Each specialist is still a separately governed published capability with its own definition, safety envelope, and audit trail.

### 6. MCP and RAG access inside the execution
The specialists and orchestrator use two context paths:

- `RAG`: policy documents, operating procedures, and brand knowledge retrieved with tenant filters enforced at query time
- `MCP`: live reads and writes against approved operational systems

Every tool call flows through the `MCP Gateway`. The gateway:

- validates ABAC against the `Identity Context` and active tool bindings
- performs RFC 8693 token exchange
- issues a fresh tool-scoped credential per call
- routes the call under PrivateLink-controlled egress
- writes tool activity into traces and audit

The downstream tool never sees the user’s raw identity. It sees only the scoped token for that operation.

### 7. Process scope, HITL, and regulated write
Because this is `R3`, the outer flow is executed by `Step Functions` using the published workflow contract. The durable workflow:

- persists correlation and state between steps
- checks idempotency before state-changing work
- supports compensation if a later step fails
- pauses at `waitForTaskToken` for the mandatory HITL review

Once the reviewer approves, the orchestrator executes the regulated MCP write to the RG platform and any linked CRM update. For `R3`, the audit behavior is `write-ahead`: the audit record must commit before the state-changing tool call executes.

### 8. Response, close, and evidence
The final response is streamed back with citations. The execution closes only after:

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
| CloudTrail | proof of AssumeRole/session tags, Registry publish events, S3 Object Lock events, KMS usage |
| Audit Record | immutable execution fact set with capability version, safety version, tool calls, guardrails, cost, delegation chain |
| Step Functions history | full R3 workflow graph, HITL decision record, compensation path |

For this example, the `R3` audit record should include:

- `execution_id`
- `correlation_id`
- `idempotency_key`
- `identity_context`
- `capability_version` and SHA-256
- `safety_envelope_version`
- full `invocation_chain`
- tool parameters and response hashes
- `hitl_record`
- `write-ahead` marker for regulated writes
- token counts and attributed cost

Costing is tracked in real time at the `tenant_id / capability_id / session_id` level. The example therefore supports:

- quota enforcement before model spend occurs
- prompt-cache savings visibility
- per-capability and per-brand spend dashboards
- hard budget caps with a tenant circuit breaker
- immutable cost evidence in the audit record

## Marketplace Publication and Consuming-Team Fork

After proving the orchestrator in Paddy Power production, the team publishes it to the marketplace as a reusable capability package.

Betfair then forks it to create `betfair-player-protection-case-orchestrator`. The consuming-team workflow should be:

1. Discover the published capability through marketplace/registry access controlled by ABAC.
2. Fork the capability into a new team-owned definition and version lineage.
3. Rebind brand-specific RAG sources, tool policies, and tenant identifiers.
4. Keep specialist dependencies explicitly version-pinned.
5. Re-run evaluation and publish through the same Registry gate.
6. Release through Betfair’s chosen surfaces: Chat UI, Slack/Teams, or API clients.

This gives Flutter the reuse path the narrative is aiming for: one governed pattern, multiple governed brand deployments.

## Coverage Against the Flutter Design

| Design area | Covered by this example |
| --- | --- |
| L5 surfaces | Chat UI or Slack for runtime use; IDE plugin and Workflow Studio for authoring; marketplace for reuse |
| L4 authoring | Pro-code orchestrator/specialists; workflow authoring for process contract; constrained reuse/fork path for consuming teams |
| L3 contract boundary | LLM Gateway, Guardrails, Agent Runtime, MCP Gateway, Capability Registry, Workflow Engine, HITL, Audit |
| L2 data and knowledge | OpenSearch/knowledge retrieval plus live operational connectors |
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
The narrative promises capabilities that are discoverable, rated, versioned, shareable, and forkable across brands. The detailed views only define peer review, ABAC-based discovery/invocation, and version pinning. The design still needs:

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

### 4. Non-Bedrock guardrail equivalence is still pending
The Bedrock path is concrete. The non-Bedrock path is not. The design needs a control-by-control equivalence matrix for Azure OpenAI, Gemini, Anthropic direct, and any other routed provider so teams know which providers are legal for which risk tiers.

### 5. Observability standardization is incomplete
Langfuse is the LLM trace authority, CloudWatch is the metrics authority, CloudTrail is the compliance authority, and OTEL integration is still pending. The design should define a single correlation contract across all three so investigation tooling and downstream exports do not drift.

### 6. Evaluation evidence is not normalized enough
The design allows Promptfoo, LangSmith, Bedrock Evaluation, and pytest, but it does not define the minimum evidence schema or the publish thresholds by risk tier. The platform should standardize:

- mandatory score dimensions per tier
- pass/fail thresholds
- required negative tests
- storage shape for attached evaluation evidence

### 7. FinOps coverage is stronger for tokens than for end-to-end workflow cost
The LLM cost model is well-defined. The design is much less explicit on:

- MCP connector/API cost attribution
- data ingestion cost attribution
- Step Functions and human-review cost attribution

If the platform wants full workflow-level chargeback, those costs need a first-class model too.

### 8. Guided Assembly remains planned rather than defined end-to-end
The business-user path is present architecturally but not operationally. If non-engineer authoring is a committed workflow, the platform still needs the concrete authoring, review, and fork UX for that surface.

## Recommended Next Step
Treat this example as the reference acceptance scenario for the platform and convert it into a formal conformance pack:

- golden capability definitions for orchestrator and specialists
- a workflow contract specimen
- publish-gate acceptance tests
- a required trace/audit evidence set
- a marketplace fork acceptance checklist

That would turn the current architecture from a strong design narrative into a testable platform contract.
