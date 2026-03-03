# Flutter Architect Call Context (03-04-2026)

## Call Metadata

- Timestamp in notes: Tue, 03 Mar 2026
- Participants:
  - chris.osullivan@flutteruki.com
  - grahamb@flutterint.com
  - adam.jackson@createfuture.com
  - shane_murray@flutterint.com

## Current AI Platform Status

- Existing AI chat platform running across 3 divisions.
- 1,800 users launched over 5 weeks.
- 400+ daily unique users.
- 12,000 prompts weekly.

### Current codebase problems

- Built on AWS Bedrock Chat as a throwaway solution.
- "Hunger Games situation": divisions taking cuts of each other's code.
- No clear maintainers or ownership.
- Connectors (Jira, Confluence) being added without sufficient structure.

## Proposed New Platform Architecture

- Move away from current codebase to a purpose-built platform.
- Key components discussed:
  - Agent marketplace with Python runtime, with potential extensibility to other languages.
  - MCP tool gateway for governance and identity control.
  - AWS Agent Core as underlying runtime.

### Primary focus areas

- Security and governance, with priority higher than feature breadth.
- Observability and audit capabilities.
- Standardized capability definitions and risk profiles.

### Specific architecture challenge

- Identity management in multi-agent workflows.
- Delegated authority model is not trivial when Agent A calls B/C/D/E.
- Service-account-only model is insufficient; finer-grained control needed.

## Technical Concerns and Considerations

- MCP protocol implementation concerns:
  - Potential 40% cost overhead from tool failure rates.
  - Trade-off between governance benefits and retry costs.
  - Need to monitor retry and stale argument rates.
- CDK pipeline support is in alpha, but working in PoC.
- Performance and failover strategies not yet defined.
- Architecture is very early, released only 4-5 days before call.

## Use Case and Evaluation Challenges

- No concrete starting use case identified yet.
- Candidate ideas:
  - Conversational bot builder with Andrei.
  - Incident commander PoC with AWS.
  - Existing disconnected PoCs across trading and customer support.
- Need for golden datasets and performance evaluation:
  - 95% accuracy standard with 5% error margin.
  - Hybrid strategy: semantic search for 85% of cases, LLM for nuanced 15%.
  - Programmatic prompt optimization via DSPy.
- Business analysis is required to map business processes to agent workflows.

## Next Steps from the Call

- CreateFuture to send capability overview, including:
  - Two relevant examples (Bedrock and Agent Core).
  - Rate card and package costs for core engineering team.
  - Optional product manager/business analyst pricing.
- AWS deep-dive session (2.5 hours) scheduled for the same afternoon.
- Identify suitable use case for platform testing.
- Account for political considerations with existing automation team.
