# Flutter AgentCore PoC Assessment (2026-03-01)

## Scope

Assessed:
- Flutter solution design mini-site under `docs/flutter-uki-ai-platform-arch/`
- Current PoC implementation (`infra/`, `aws/lambda/`, `runtime/`, `evals/`, `reports/`)

Assessment objective:
1. Does the PoC meet its stated objective?
2. Does it misunderstand or misrepresent Flutter's architecture approach?
3. What expansion areas would add high-value validation/critique for a bid-support report?

Method used:
- Deep-topic-research style evidence pass: explicit questions, source-backed findings, repo-level verification, and contradiction/knock-on analysis.

---

## Executive Verdict

### Short answer

The PoC **partially meets** its objective.

- It **does** demonstrate a reproducible MCP-vs-native difference in tool-selection failure under the current evaluation setup.
- It **does** exercise AgentCore Gateway MCP and alpha CDK constructs.
- It **does not yet** validate key parts of Flutter's intended architecture contract (L3 non-bypass boundary, identity propagation model, risk-tier/workflow invariants, audit semantics).

For bid support, it is useful as a **targeted route-reliability experiment**, but not yet as a **platform-architecture validation**.

Confidence: **moderate-high** (code + test + existing run artifacts reviewed).

---

## What Is Proven Today

1. MCP-vs-native failure differential is observable in live runs.
   - `reports/eval-comparison-live-route-100.json` reports native `tool_failure_rate: 0.0` vs MCP `0.6`, with MCP failure reasons dominated by `selected_wrong_tool:*`.
2. Gateway path is real MCP protocol (not stubbed) in current implementation.
   - `aws/lambda/common.py` uses JSON-RPC `tools/list` and `tools/call` with SigV4 signing.
3. AgentCore alpha CDK resources are deployed in IaC.
   - Runtime + Gateway + endpoint are declared in stack.
4. Failure taxonomy is explicit and tested.
   - Unit tests assert `selected_wrong_tool`, `mcp_gateway_unavailable`, `mcp_tool_call_error`, etc.

---

## Where It Does Not Match Flutter Architecture Intent

### 1) L3 contract boundary is not represented end-to-end
Flutter design states L3 is non-bypassable and all model access routes through LiteLLM gateway.

Current PoC:
- Lambda stages call Bedrock directly (`boto3.client("bedrock-runtime")`) and perform tool selection/generation directly.
- This bypasses an explicit LLM gateway layer in the execution path.

Impact:
- Reliability outcomes currently blend tool-interface effects with architectural differences from Flutter's intended runtime boundary.

### 2) Process/Risk-Tier invariants are not modeled
Flutter design requires R2/R3 Workflow Contract, fail-closed semantics, and richer process controls.

Current PoC:
- Step Functions flow is parse -> fetch -> generate -> evaluate, no Workflow Contract enforcement, no compensation states, no HITL gate.
- No risk-tier declaration or policy behavior in runtime flow.

Impact:
- Results cannot be used to validate claims about R2/R3 governance behavior.

### 3) Identity model is materially simplified
Flutter design emphasizes IAM session tags as Identity Context, ABAC propagation, and RFC 8693 tool token exchange semantics.

Current PoC:
- Uses IAM-authenticated gateway invocation and host allowlisting, but does not model full Identity Context propagation, ABAC checks against Capability Definition, or token exchange observability in the experiment outputs.

Impact:
- Security/identity conclusions from this PoC should be scoped narrowly to connectivity and invocation behavior.

### 4) Audit semantics are not equivalent to design
Flutter design specifies synchronous, risk-tier-scaled Audit Record behavior and immutability posture.

Current PoC:
- Persists execution payload to S3, but bucket is configured with `RemovalPolicy.DESTROY` + `autoDeleteObjects: true`.
- No Object Lock / compliance retention behavior is represented.

Impact:
- The PoC does not validate the compliance-grade audit contract described in the solution design.

---

## Contradictions and Knock-on Effects

1. **Nightly rule likely fails by construction**
   - Nightly Step Functions input omits `expected_tool`, while both fetch stages treat it as required and fail when missing.
   - Knock-on: scheduled runs can create deterministic failure noise and weaken evidence quality.

2. **Evidence artifact schema drift risk**
   - Existing reports in `reports/` do not include fields now expected by current eval code path (`tool_match_rate`, `composite_reflection`), and native selected tools appear inconsistent with current dataset expectations.
   - Knock-on: bid reviewers may question reproducibility unless fresh runs are generated with a pinned commit + schema.

3. **Current comparison may over-attribute failures to MCP protocol**
   - The experiment currently tests a broader bundle: naming/prefix patterns, catalog shape, and selector behavior in addition to protocol transport.
   - Knock-on: if presented as "protocol-only", conclusions may be challenged as confounded.

---

## Does It Misunderstand or Misrepresent Flutter Design?

### Misunderstandings
- No major conceptual misunderstanding of "MCP can be less reliable under ambiguous tool catalogs"; this is a valid hypothesis.

### Misrepresentation risk
- Claiming strong alignment to Flutter's architecture is currently overstated.
- The PoC aligns to **one slice** (tool-routing reliability), not to the full L3/L2/L1 governance-security-observability contract described in the docs.

Recommended framing in proposal:
- "This PoC validates MCP-vs-native tool-selection reliability under controlled SOP tasks, and identifies protocol-adjacent failure patterns. It does not yet claim full validation of Flutter's production governance model."

---

## High-Value Expansion Areas (for bid-quality evidence)

Priority 1 (must-have for credible architecture critique)
1. Add **runtime-path parity experiment**:
   - Route both arms through deployed AgentCore runtime endpoint, not only Lambda stages.
   - Keep same task/model/tools, vary only interface/transport dimension.
2. Add **unconfounded ablation matrix**:
   - A: native direct tools
   - B: MCP transport with deterministic tool choice (no model selection)
   - C: MCP transport with model tool selection
   - This separates protocol overhead from selector behavior.
3. Fix **nightly input contract** (`expected_tool`) and add contract test to prevent recurrence.

Priority 2 (architecture-alignment validation)
4. Introduce **risk-tier scenarios (R1 vs R2)** with explicit workflow contract-like checks and at least one compensation/HITL path.
5. Add **identity-context observability assertions** in artifacts (tenant/brand/role lineage, policy decision logs per call).
6. Add **audit immutability mode** for evaluation artifacts (Object Lock-like posture, write semantics by tier).

Priority 3 (proposal-strengthening critique depth)
7. Expand datasets to include:
   - semantically-equivalent tool choices,
   - ambiguous intents,
   - multi-step tasks requiring >1 tool.
8. Add statistical treatment:
   - confidence intervals already present for failure rate; extend with significance tests per arm and per intent bucket.
9. Add cost + latency decomposition:
   - protocol/list/call latencies separately, plus per-success cost and per-failure cost.

---

## Suggested Bid Attachment Structure

1. Objective and hypothesis
2. Experimental design (what was controlled vs varied)
3. Findings (with confidence + limits)
4. Architecture alignment gaps vs Flutter target model
5. Risk register (what remains unvalidated)
6. 4-6 week validation plan to close gaps before production design freeze

---

## Key Evidence References

Design intent:
- `docs/flutter-uki-ai-platform-arch/platform-narrative-v3.html`
- `docs/flutter-uki-ai-platform-arch/view-orchestration-v5.html`
- `docs/flutter-uki-ai-platform-arch/view-security-identity-v7.html`
- `docs/flutter-uki-ai-platform-arch/view-observability-v3.html`
- `docs/flutter-uki-ai-platform-arch/domain-model-v1.html`
- `docs/flutter-uki-ai-platform-arch/view-request-trace-v10.html`

PoC implementation and evaluation:
- `README.md`
- `infra/lib/flutter-agentcore-poc-stack.ts`
- `infra/package.json`
- `aws/lambda/common.py`
- `aws/lambda/fetch_native_stage.py`
- `aws/lambda/fetch_mcp_stage.py`
- `aws/lambda/evaluate_stage.py`
- `runtime/sop_agent/tools/agentcore_mcp_client.py`
- `runtime/sop_agent/tools/strands_native_flow.py`
- `runtime/sop_agent/tools/jira_mcp_flow.py`
- `evals/run_eval.py`
- `evals/golden/sop_cases.jsonl`
- `reports/eval-comparison-live-route-100.json`
- `reports/eval-mcp-check.json`
- `reports/eval-smoke-agentcore-refactor.json`

---

## Verification Notes

- Test run on this repo at assessment time: `python3 -m pytest -q` -> `64 passed`.
- CDK synth completes, with non-blocking environment warnings about expired credentials during account lookup.
