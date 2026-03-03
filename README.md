
# Flutter AgentCore SOP PoC

## Installation

- Prerequisites: Python 3.12+, Node.js + npm, and AWS CLI with a configured named profile.
- Use [.envrc.example](./.envrc.example) as the local environment template and load it via your workflow tooling before running commands.
- Bootstrap and dependency setup is handled by `./scripts/bootstrap-repo.sh`; command matrix, deployment, benchmark, and troubleshooting steps are in [`AGENTS.md`](./AGENTS.md).

## Purpose

- This PoC compares native tool invocation and MCP call-construction paths under a shared model family, same contract set, and common KPI expectations.
- It is designed to produce deterministic release-truth metrics (`tool_failure_rate`, `business_success_rate`, latency, and token/cost deltas) while also surfacing MCP-specific construction diagnostics.
- The primary usage is to validate route parity decisions before promoting to full production flow design.

## Usage

- Prepare local configuration, bootstrap dependencies and infra, then run benchmark workflows against the deployed Step Functions state machine.
- Use the adversarial dataset to stress MCP call-construction and tool-selection edge cases while keeping the remaining pipeline contract stable.
- For troubleshooting and step-by-step action guidance, refer to [`AGENTS.md`](./AGENTS.md), which is the single source of developer command actions.

## Business flow

```mermaid
flowchart TD
    A["Support lead defines SOP scenarios and success criteria"]
    B["Dataset row includes expected_intent expected_issue_key expected_tool.native expected_tool.mcp"]
    C["Eval run preflight: STS identity + deployed state machine contract checks"]
    D["Parse stage extracts candidate keys and risk hints then model grounds intent plus issue key"]
    E{"Select tool flow"}

    subgraph N["Native route"]
      N1["Build intent-scoped native tool catalog from contract"]
      N2["LLM selects native tool via gateway client (same model family as MCP arm)"]
      N3["Invoke Jira API style tool or write_followup_note action"]
      N4["Validate tool payload completeness for selected operation"]
      N1 --> N2 --> N3 --> N4
    end

    subgraph M["MCP route"]
      M1["List AgentCore gateway tools and scope by intent"]
      M2["LLM selects tool plus arguments with construction retries"]
      M3["Validate selected tool and arguments against gateway schema"]
      M4["Call MCP gateway tool and normalize payload"]
      M5["Validate tool payload completeness for selected operation"]
      M1 --> M2 --> M3 --> M4 --> M5
    end

    F["Generate customer safe response"]
    G["Evaluate and persist artifact"]
    H["Deterministic KPIs: tool_failure_rate tool_match_rate issue_key_resolution_match grounding_failure business_success_rate latency call_construction write_tool_match llm_tokens"]
    I["Optional judge diagnostics + composite_reflection divergence signal"]
    J["Publish eval summary to CloudWatch and AgentCore views"]
    K{"Deterministic release gate passed?"}
    L["Recommend route and next tranche"]
    R["Hold release and run remediation experiments"]

    subgraph Y["PoC hypotheses under test"]
      Y1["H1: native has lower tool_failure_rate than mcp under same task/model"]
      Y2["H2: intent-scoped catalogs and stricter selection raise tool_match_rate and business_success_rate"]
      Y3["H3: MCP call-construction failures are measurable and partly recoverable through retries"]
      Y4["H4: deterministic metrics remain release truth while judge adds diagnostic context"]
      Y5["H5: current signal (2026-03-02): both routes pass deterministic gate in adversarial run, but mcp remains slower and more expensive with measurable call-construction failures"]
    end

    A --> B --> C --> D --> E
    E -->|native| N1
    E -->|mcp| M1
    N4 --> F
    M5 --> F
    F --> G --> H --> I --> J --> K
    K -->|Yes| L
    K -->|No| R

    Y1 -.validated by.-> H
    Y2 -.validated by.-> H
    Y3 -.validated by.-> H
    Y4 -.validated by.-> I
    Y5 -.bounded by.-> L
```

## References

- Reference artifacts and architecture assessments: `docs/references/bid-companion-2026-03-01/`
- Generated eval outputs: `reports/runs/<RUN_ID>/...`
- Test quality checklist for test-harness debt and complexity guardrails: `docs/test-quality-checklist.md`
