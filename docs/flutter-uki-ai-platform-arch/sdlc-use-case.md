# SDLC Use Case On The Flutter AI Platform

## Position

The Flutter design mentions `SDLC` in two places:

- IDE plugins surface `SDLC agents` such as PR review, test generation, and doc generation inline.
- SDLC is treated as a cross-cutting concern spanning CI/CD, lifecycle gates, and local development.

That is directionally valid, but it needs a sharper interpretation.

The platform narrative also says the platform is a **control plane**, not a productivity tool, and explicitly says it does not replace application logic or guarantee output quality. That means the design should **not** be read as “all agentic coding happens inside the hosted platform runtime.”

The coherent reading is:

- **local agentic coding loops stay local**
- **hosted SDLC agents on the platform provide governed review, verification, approval, and reusable engineering workflows**

That is the only SDLC interpretation that fits the rest of the platform design without stretching it into something it is not.

## What Should Stay Local Versus Hosted

| Activity | Best location | Why |
| --- | --- | --- |
| interactive code editing | local | fastest inner loop, developer-controlled context, no need for hosted governance path |
| repo navigation, search, patching, local test iteration | local | high-frequency, low-governance, workstation-centric tasks |
| ad hoc pair-coding | local | not a control-plane concern |
| PR review and verification | hosted | reusable, auditable, policy-governed, easy to share across teams |
| standards/compliance review | hosted | central policy and traceability fit the platform well |
| CI failure triage and test-plan generation | hosted | cross-team reuse and standardization are valuable |
| change approval workflow | hosted | HITL, audit, and process orchestration fit the platform design |
| direct autonomous code remediation | hybrid | candidate changes may be proposed locally or in ephemeral workspaces, but writeback should be governed |

## Recommended Hosted SDLC Pattern

The best SDLC use case for this platform is a **hosted PR review and verification workflow** rather than a full hosted coding loop.

Recommended capability:

- `pr-verifier-orchestrator`

Purpose:

- review a pull request or change set
- retrieve policy and engineering guidance
- reason over impact and likely defects
- run governed verification steps
- return structured findings, test recommendations, and status outputs

## Proposed Hosted Capability Topology

| Capability | Purpose | Execution model | Likely risk tier |
| --- | --- | --- | --- |
| `pr-verifier-orchestrator` | end-to-end review and synthesis | Reasoning + Coordination | `R0` for advisory-only mode, `R1` if posting comments/status |
| `diff-review-specialist` | detect code smells, regressions, logic issues | Reasoning | `R0` |
| `test-impact-specialist` | infer required tests and affected areas | Reasoning | `R0` |
| `engineering-standards-specialist` | check standards, architecture, policy, docs rules | Reasoning | `R0` |
| `ci-triage-specialist` | reason over failed jobs and logs | Reasoning | `R0` |

Potential extension:

- `remediation-orchestrator`

This would propose patches or controlled branch updates, but it should be treated as a later phase because it requires stronger workspace and writeback controls.

## Why This Fits The Platform

Hosted PR verification aligns with the platform’s strengths:

- identity and ABAC matter
- the workflow is reusable across teams
- auditability matters for write actions such as comments, checks, approvals, or issue updates
- policy and standards retrieval fit RAG well
- MCP tools fit GitHub, CI, issue tracker, docs, and artifact systems
- orchestrator plus specialist pattern fits the published coordination design

It does **not** require the platform to become a full remote IDE or replace local developer workflows.

## Proposed Runtime Flow

### Trigger

One of:

- GitHub PR opened or updated
- CI pipeline requests governed review
- developer invokes “Run governed review” from IDE plugin

### Inputs

- PR diff and metadata
- changed files list
- repository policy bundle
- test history / flaky-test information
- architecture and coding standards docs
- optional issue/ticket context

### MCP tools

Likely tool set:

- GitHub PR and file diff reader
- code search / repository metadata lookup
- CI logs and job status reader
- documentation / Confluence reader
- issue tracker reader
- optional status writer or PR comment writer

### RAG sources

Likely RAG set:

- engineering standards
- architecture patterns
- security rules
- language/framework guidance
- testing guidance

### Output contract

The output should be **structured**, not just prose.

Minimum structured review output:

```json
{
  "review_id": "uuid",
  "pr_ref": "org/repo#123",
  "summary": "short verdict",
  "findings": [
    {
      "file": "src/foo.py",
      "start_line": 42,
      "end_line": 47,
      "severity": "high",
      "category": "logic_bug",
      "title": "Null branch skipped",
      "rationale": "why this matters",
      "suggested_action": "what to change"
    }
  ],
  "test_recommendations": [
    {
      "target": "tests/test_foo.py",
      "reason": "branch not covered"
    }
  ],
  "status_recommendation": "pass_with_findings"
}
```

Without a strict schema, SDLC evaluation and success-rate claims are too subjective.

## Risk Tier Interpretation For SDLC

Using the Flutter risk model as written:

- `R0`: read-only advisory review, no external writes
- `R1`: writes to internal engineering systems such as PR comments, check runs, Jira updates, or release metadata
- `R2/R3`: generally not needed for normal SDLC unless the workflow is writing to regulated or customer-significant operational systems

That said, there is a design tension:

- GitHub comments and check-run writes fit `R1` by the current taxonomy
- but engineering-change blast radius can still be very high

So for SDLC use cases, Flutter may need either:

- a stricter `R1` template for repository write actions, or
- an SDLC-specific control profile layered on top of the general risk-tier model

Otherwise, the current risk taxonomy may understate engineering-governance risk.

## If They Want Hosted Coding, Not Just Hosted Review

Hosted coding can work, but only with an additional platform component that the current design does not really define: an **ephemeral code workspace runner**.

That component would need to provide:

- short-lived isolated workspace per execution
- repo clone at pinned commit
- search/read/build/test/apply-patch tools
- no production credentials
- network egress restrictions
- full audit of every file mutation and command
- governed writeback to GitHub only through approved tools

Without this component, the platform can credibly host **review and verification** but not a serious autonomous coding loop.

## Recommended Phased SDLC Use Case

### Phase 1: Advisory PR review

Capabilities:

- read PR diff
- read standards and docs
- return structured findings and test recommendations

Why first:

- fully aligned to `R0`
- easy to benchmark
- no write-path risk

### Phase 2: Governed internal write actions

Add:

- PR comments
- check-run status updates
- Jira ticket annotations

Risk profile:

- `R1`

Why second:

- tests hosted workflow value without introducing autonomous remediation

### Phase 3: Hosted verification with ephemeral workspace

Add:

- build/test execution in isolated workspace
- richer triage and evidence capture

Why third:

- requires stronger runtime controls than the current design clearly spells out

### Phase 4: Proposed remediation

Add:

- patch generation
- branch update proposal
- mandatory human approval before any merge or protected-branch write

Why last:

- this is the first point where hosted SDLC starts to resemble autonomous coding rather than review

## Evaluation Model For An SDLC Review Agent

The design’s `>95% success rate` target should **not** be interpreted as “the review agent finds 95% of all possible defects.”

For code review, use three separate metrics.

### 1. Runtime Success Rate

This is the platform/SLO-style metric.

A run counts as successful only if:

- the execution completes without timeout or runtime failure
- all required tool calls succeed
- the output matches the required schema
- no policy or guardrail failure invalidates the review
- the review artefacts are fully traceable and auditable

Metric:

- `runtime_success_rate = successful_executions / total_executions`

Target:

- `>= 95%`

### 2. Review Quality Metrics

This measures whether the review agent is good at review.

Use a benchmark set of PRs/diffs with:

- seeded known issues
- historical PRs with previously confirmed defects
- clean PR controls
- false-positive trap cases
- multi-file and interaction-heavy changes

Primary quality metrics:

- `critical_high_recall`
- `overall_weighted_recall`
- `false_positive_rate`
- `clean_pr_pass_rate`
- `severity_accuracy`
- `line_reference_accuracy`

Suggested launch targets:

- `critical/high recall >= 95%`
- `overall weighted recall >= 90%`
- `clean PR pass rate >= 90%`
- `schema validity = 100%`

### 3. Case Pass Rate

This is the metric that should be used for publish gating.

A benchmark case passes only if:

- the runtime execution succeeds
- the schema is valid
- all required critical/high findings are detected
- false positives stay below threshold
- output points at the correct file/line location within tolerance

Metric:

- `case_pass_rate = passed_cases / total_cases`

Target:

- `>= 95%`

This is the closest defensible interpretation of the Flutter-style success requirement for an SDLC review agent.

## How Promptfoo And Runtime Evals Should Work Together

### Promptfoo in CI

Use Promptfoo for fast, repeatable capability-quality gates.

Each case should include:

- PR diff or code snapshot
- tool fixtures
- expected findings manifest
- forbidden findings for clean cases
- optional required tool-use expectations

Promptfoo should enforce:

- output schema validity
- expected finding match
- severity weighting
- clean-case false-positive limits

Use LLM-as-judge only as a secondary signal for rationale clarity, not as the primary pass/fail mechanism.

### Hosted Runtime Evals In Sandbox

Run the same benchmark through the deployed runtime for the hosted path.

This validates:

- orchestrator behavior under the real runtime
- MCP tool routing
- trace and audit generation
- latency and timeout behavior
- cost attribution and quotas
- hosted output quality under the real runtime path

The release truth for the hosted SDLC capability should come from:

1. Promptfoo benchmark pass in CI
2. sandbox runtime benchmark pass
3. sampled human review of outputs on held-out cases

## Suggested Benchmark Composition

Minimum benchmark set:

- at least `200` cases

Recommended mix:

- `40%` seeded bug/security/regression cases
- `20%` missing-test or weak-test cases
- `20%` clean PR controls
- `20%` multi-file, noisy, or edge-case changes

Also require:

- a held-out set that prompt tuning is not optimized against
- periodic refresh from real historical PRs
- explicit negative controls to prevent reward hacking through over-reporting

## Final Recommendation

The best SDLC use case for this platform is:

- **hosted PR review, verification, and governed engineering workflow orchestration**

The platform should **not** be positioned as:

- a replacement for local agentic coding loops
- a remote IDE
- a general-purpose autonomous coding environment

If Flutter wants hosted coding later, it needs to add an ephemeral workspace execution component and much tighter writeback controls.

Until then, the credible near-term SDLC story is:

- local coding
- hosted verification
- governed write actions
- strong benchmarked evaluation

That interpretation fits the platform design materially better than trying to force the entire software development lifecycle into the hosted runtime.
