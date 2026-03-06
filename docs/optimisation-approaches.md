# Optimisation Approaches For Agent Workflows

## Purpose
This report captures the discussion on how to iterate and evaluate agent workflows in the Flutter platform design, with and without DSPy plus a representative golden dataset.

## Artefacts
- Visual explainer diagram: `docs/flutter-jira-rag-agentcore-eval-flow.html`

## Questions Asked And Answers

### 1) If DSPy plus a golden dataset is not used, how can workflows be iterated in Flutter's design?
Answer:
- Use the publish-time Evaluation Gate path and runtime feedback loop together.
- Publish-time gate: run evaluation suites (Promptfoo, LangSmith, Bedrock Evaluation, pytest) before Registry publish; block promotion on failure.
- Runtime loop: use Langfuse sampled LLM-as-judge scoring, CloudWatch operational metrics, Audit Record evidence, and incident triage to identify regressions.
- Improvement loop: create a new capability version, re-run gate, and republish. No runtime override path should be relied on for permanent fixes.
- Optional operational extension: AgentCore online evaluation configuration over CloudWatch logs and evaluator IDs.

### 2) Via this alternative evaluation path, is a representative golden dataset still required?
Answer:
- Not strictly required for runtime sampled evaluation.
- Still strongly recommended for deterministic release and regression control.
- Without a representative fixed set, promotion confidence degrades because sampled runtime data is noisy and distribution-shifted.

### 3) Can we model a multi-step Jira workflow with RAG in a business flow and show platform component placement, evaluation, and feedback?
Answer:
- Yes. The diagram in `docs/flutter-jira-rag-agentcore-eval-flow.html` shows:
- Request path through AgentCore ReAct loop.
- RAG retrieval and Jira ticket-creation tool execution.
- LLM Gateway plus Guardrails plus Audit Record points.
- Evaluation loops (pre-publish and runtime sampled/online).
- Feedback path back into versioned workflow improvements.

### 4) What are strengths and weaknesses of this evaluation approach vs DSPy plus golden dataset?
Answer summary:
- Platform-native loop is stronger on governance fit and runtime fidelity.
- DSPy plus golden is stronger on deterministic optimization, controlled regression testing, and iteration speed.
- A hybrid approach is usually strongest.

## Option Set

## Option A: Platform-native evaluation loop only
Scope:
- Evaluation Gate before publish.
- Runtime sampled evaluation and operations signals.

Strengths:
- Aligned to platform lifecycle and governance controls.
- Uses real runtime behavior across auth, tooling, latency, and cost.
- Captures drift and operational incidents quickly.

Weaknesses:
- Less deterministic for promotion decisions by itself.
- Slower root-cause isolation for quality regressions without fixed baselines.
- Sampled signals can miss low-frequency failures.

## Option B: DSPy plus representative golden dataset only
Scope:
- Offline optimization and regression scoring on fixed datasets.

Strengths:
- Deterministic and repeatable comparisons.
- Fast optimization cycles.
- Strong release-gate confidence when data is representative.

Weaknesses:
- Risk of dataset overfitting.
- Can miss runtime and integration failure modes.
- Dataset authoring and maintenance overhead.

## Option C: Hybrid (recommended)
Scope:
- DSPy plus golden for controlled optimization and release gates.
- Platform-native runtime evaluation for drift detection and production realism.

Strengths:
- Combines deterministic offline control with runtime truth.
- Better balance of promotion confidence and live quality monitoring.

Weaknesses:
- Highest setup and operating complexity.
- Requires explicit governance for metric ownership and triage process.

## Comparison Matrix

| Dimension | Platform-native loop | DSPy + golden dataset | Hybrid |
|---|---|---|---|
| Governance and lifecycle alignment | Strong | Medium unless integrated | Strong |
| Runtime fidelity | Strong | Medium | Strong |
| Determinism and reproducibility | Medium to weak | Strong | Strong |
| Optimization speed | Medium | Strong | Strong |
| Regression protection | Medium alone | Strong | Strong |
| Drift detection in production | Strong | Weak to medium | Strong |
| Setup and maintenance effort | Medium | Medium to high | High |

## Key Contradictions And Knock-on Effects
- If deterministic promotion quality is required but no fixed representative regression set exists, that is a control contradiction.
- If Jira ticket creation is customer-adjacent or regulated, workflow may need R2/R3 controls (Process scope, Workflow Contract, HITL), not just a reasoning-only flow.
- If model providers vary, guardrail coverage equivalence can affect score comparability and triage confidence.

## Recommended Direction
- Adopt Option C (Hybrid).
- Keep a small versioned release-canary golden suite for deterministic regression checks.
- Continue runtime sampled evaluation and online evaluators for drift and incident detection.
- Route runtime regressions into Jira improvements and versioned capability updates.

## References Used In The Discussion
- `docs/flutter-uki-ai-platform-arch/view-agent-lifecycle-v9.html` (evaluation gate and publish requirements)
- `docs/flutter-uki-ai-platform-arch/architecture-overview-v9.html` (team-defined framework and lifecycle controls)
- `docs/flutter-uki-ai-platform-arch/component-design-v2.html` (Evaluation Gate Service responsibilities)
- `docs/flutter-uki-ai-platform-arch/view-observability-v3.html` (LLM-as-judge, operational signals)
- `docs/flutter-uki-ai-platform-arch/view-request-trace-v10.html` (ReAct loop, RAG, Jira/tool path)
- `docs/flutter-uki-ai-platform-arch/view-orchestration-v5.html` (R2/R3 process and workflow contract)
- `docs/flutter-uki-ai-platform-arch/platform-narrative-v3.html` (runtime quality non-goal statement)
- `AGENTS.md` (AgentCore online eval configuration command)
