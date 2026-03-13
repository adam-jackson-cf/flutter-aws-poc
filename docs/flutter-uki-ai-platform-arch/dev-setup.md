# Development Setup For The Flutter AI Platform Design

## Short Answer
There should be a local development environment for this design, but it is not a fully faithful local replica of the platform.

The right model is **hybrid**:

- **local-first for authoring, orchestration logic, contract testing, and fast feedback**
- **AWS sandbox for any capability that depends on managed AWS control-plane behavior or regulated governance claims**

For the example workflow in [a2a-mcp-end-to-end-brief.md](/Users/adamjackson/Projects/flutter-aws-poc/docs/flutter-uki-ai-platform-arch/a2a-mcp-end-to-end-brief.md), that means developers should be able to build and test most of the `player-protection-case-orchestrator` flow locally, but they should not claim the platform is working end to end until the same workflow has been exercised in a deployed AWS sandbox.

## Why A Hybrid Model Is Necessary

The design itself already points to a split:

- local dev exists as `Strands local mode with Docker Compose mocked L3 services`, a Registry mock, and sandbox MCP endpoints with fixture responses
- evaluation test invocations use a restricted IAM role with explicit deny on production writes
- runtime governance is still platform-enforced by AWS-hosted components such as AgentCore, Bedrock Guardrails, Step Functions, IAM Identity Center, CloudWatch, CloudTrail, and S3 Object Lock

That means:

- **capability logic can be developed locally**
- **platform guarantees must be proven in AWS**

## Recommended Development Modes

| Mode | Purpose | Where it runs | What it proves | What it does not prove |
| --- | --- | --- | --- | --- |
| `Mode 1: Local authoring loop` | Fast iteration on prompts, orchestration, tool schemas, and tests | Laptop + Docker Compose | Capability shape, orchestration behavior, contract correctness, Python code quality, prompt/test feedback | Real IAM identity propagation, Bedrock Guardrails behavior, AgentCore hosting, Step Functions semantics, CloudWatch/CloudTrail/Object Lock evidence |
| `Mode 2: Local + sandboxed AWS integration` | Validate the same workflow against real managed services without production blast radius | Laptop plus deployed AWS sandbox | Managed-service behavior, real runtime path, ABAC behavior, real audit/tracing/cost signals | Production-scale posture, cross-team reuse behavior at portfolio scale |
| `Mode 3: Full sandbox end-to-end` | Release-candidate validation for the exact governed workflow | Fully deployed AWS sandbox | The platform’s actual design claims for the thin slice | Nothing beyond that single validated slice |

## Component Split: Local Versus AWS Sandbox

| Component | Local version | AWS sandbox version | Recommendation |
| --- | --- | --- | --- |
| Capability authoring | Yes | Yes | Author locally first |
| Registry API | Mock or contract-test double | Real service | Mock locally, prove publish path in sandbox |
| Agent runtime | Strands local mode | AgentCore runtime | Use local for fast loops, AgentCore for real validation |
| LLM gateway | Local LiteLLM-compatible process or mock | Real LiteLLM gateway | Start local, prove quotas/routing/cost in sandbox |
| Guardrails | Stubbed/policy-test harness | Real Bedrock Guardrails path | Do not treat local guardrail tests as proof of runtime enforcement |
| MCP gateway | Local mock server + fixture endpoints | Real gateway + sandbox tools | Use local for schema and orchestration tests, sandbox for auth and tool routing |
| RAG/retrieval | Local fixtures or lightweight local index | Real OpenSearch / KB path | Keep local retrieval cheap; prove isolation and citations in sandbox |
| Workflow engine | Local workflow runner or thin simulation | Step Functions | Local simulation is useful, but only sandbox proves process semantics |
| HITL | Local stub callback | Real wait-for-task-token / reviewer path | Stub locally, prove approval path in sandbox |
| Identity | Local test principal / fake tags | IAM Identity Center + STS tags | Only sandbox proves real Identity Context propagation |
| Observability | Local logs, optional local Langfuse | CloudWatch, CloudTrail, Langfuse, Audit bucket | Local helps debugging, sandbox proves evidence model |
| Audit store | Local file/JSON artefact | S3 Object Lock-backed records | Local is for shape checks only; real immutability exists in AWS |
| Costing | Local counters or mocked telemetry | Real gateway attribution and alarms | Sandbox is required for real quota and budget behavior |

## What Should Be Fully Local

The following should work without deploying anything to AWS:

- authoring the orchestrator and specialist capability definitions
- prompt iteration
- tool schema definition and validation
- orchestration logic for `Reasoning` and `Coordination`
- mocked `MCP` tool calls with fixture responses
- mocked Registry discovery
- contract tests for capability shape, tool bindings, and workflow-contract shape
- Python unit tests, integration tests against mocks, and design-rule checks
- evaluation suites that do not require the real runtime path

For the example workflow, the minimum local slice should be:

- `player-protection-case-orchestrator`
- one specialist capability
- one RAG fixture set
- one mocked MCP read tool
- one mocked MCP write tool
- a simulated HITL callback

That is enough to validate most of the developer-facing workflow before touching AWS.

## What Must Be Proven In AWS Sandbox

The following should be treated as **sandbox-only proof points**:

- IAM Identity Center login and STS session-tag propagation
- ABAC enforcement at the Registry and MCP boundary
- AgentCore-hosted execution
- Bedrock Guardrails enforcement
- Step Functions process semantics
- wait-for-task-token HITL flow
- CloudWatch metrics and alarms
- CloudTrail identity and API evidence
- S3 Object Lock audit behavior
- real LLM cost attribution, quotas, and circuit-breaker behavior

For the example workflow, the first time the team can claim the platform slice is working is when the same workflow runs in sandbox with:

- published capability definitions
- attached evaluation evidence
- real identity context
- real audit artefacts
- real traces and metrics
- real sandbox MCP endpoints

## Recommended Local Development Environment

This is the ideal **developer workstation** setup for the design, independent of the current repo layout:

- Python `3.12`
- Node.js LTS for infra and UI tooling
- Docker Compose for mocked L3 services and fixture endpoints
- local Strands runtime for agent execution
- local LiteLLM-compatible gateway process or test double
- local prompt artefacts or prompt references
- local fixture corpus for RAG
- local Langfuse optional for trace inspection
- AWS CLI and sandbox credentials available, but not required for every edit-test cycle

The local stack should expose one command for each loop:

- `start-local-stack`
- `run-unit-tests`
- `run-contract-tests`
- `run-evals-dry`
- `run-quality-gates`
- `deploy-sandbox-slice`

The exact commands can vary by repo. The loop itself should not.

## Recommended AWS Sandbox Environment

The sandbox should be a **real but minimal** slice of the platform in `eu-west-1`, with separate identities, audit storage, cost controls, and tool endpoints that are safe for testing.

Minimum sandbox components for the example workflow:

- AgentCore runtime
- LLM Gateway
- Guardrails path
- Capability Registry
- MCP Gateway
- sandbox MCP tools
- Step Functions
- HITL callback path
- OpenSearch/KB or equivalent managed retrieval path
- Langfuse
- CloudWatch and CloudTrail
- audit bucket with correct retention behavior for the slice being tested

Recommended sandbox rules:

- use sandbox-only tool endpoints and test data
- enforce explicit deny on production data stores
- isolate costs and quotas per sandbox tenant
- treat sandbox evidence as release truth for the slice under test

## How The Example Workflow Should Move Through The Environments

### Stage A: Local-only
The orchestrator and specialist run in local Strands mode. Registry is mocked. MCP calls go to fixture servers. HITL is simulated. The goal is fast feedback on orchestration, tool usage, and workflow shape.

### Stage B: Hybrid integration
The same workflow definition is published into a sandbox Registry and executed through sandbox AgentCore and LLM Gateway, but still uses sandbox MCP tools and non-production data. This is where identity, ABAC, guardrails, workflow execution, and cost attribution are validated.

### Stage C: Full sandbox release-candidate
The workflow is treated as if it were production-ready inside sandbox. Evaluation evidence, audit, observability, and failure-path tests all have to pass. This is the first point at which the team should rely on the platform’s governance claims.

## Quality Gates To Keep

Even in an idealized setup, the current quality-gate posture should remain. The design benefits from having strong local and CI reinforcement before sandbox promotion.

Keep these gate layers conceptually:

- design compliance checks
- Python linting and formatting
- Python type and unit/integration tests
- contract and snapshot tests for schemas and orchestration payloads
- evaluation dry runs for capability behavior
- stricter extended gates for higher-risk workflow changes

When working in this repository specifically, preserve the existing quality-gate lanes and handoff expectation before commit or handoff.

## Practical Recommendation

The correct default is **not** “always deploy to AWS for every change”.

The correct default is:

1. build and iterate locally
2. keep the local stack realistic enough to exercise the example workflow shape
3. promote to AWS sandbox as soon as the work depends on platform enforcement rather than capability logic
4. treat sandbox evidence, not local mocks, as proof of the platform’s design claims

## Decision

For this design, there **is** a local version, but it is a **development and pre-integration environment**, not a production-faithful platform replica.

The ideal setup is therefore:

- **local-first for speed**
- **sandbox-required for truth**

That is the only setup that matches both the Flutter design and the `a2a-mcp-end-to-end-brief` workflow without either over-deploying too early or over-claiming what local mocks prove.
