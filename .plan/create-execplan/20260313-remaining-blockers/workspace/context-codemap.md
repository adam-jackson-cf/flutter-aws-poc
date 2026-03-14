# Context Code Map

- Created: 2026-03-13
- Last updated: 2026-03-14T00:08:39Z

| Area | File anchor | Current behavior | Planned change |
| ---- | ----------- | ---------------- | -------------- |
| Shared bootstrap entrypoint | `scripts/deploy/bootstrap-shared-sandbox.sh:8` | Exposes environment-aware bootstrap flow for shared runtime, endpoint, stack deploy, and guard invocation. | Add explicit management-account role/profile plumbing and document one-command deploy plus enforce flow. |
| Runtime bootstrap resources | `infra/runtime-bootstrap-resources.yaml:4` | Provisions artifact bucket and AgentCore runtime role for fresh-environment deploys. | Reverify as the IaC bootstrap base for fresh environments; keep as deploy precondition in plan evidence. |
| Runtime creation and endpoint convergence | `scripts/deploy/bootstrap-shared-sandbox.sh:436` | Resolves or creates the shared runtime, then converges the named endpoint. | Preserve as the deterministic runtime bootstrap sequence; add management-account credential handoff before guard enforcement. |
| Stack deployment and guard call | `scripts/deploy/bootstrap-shared-sandbox.sh:540` | Deploys `FlutterAgentCorePocStack` and then invokes the AWS guard script. | Extend close-out tasks to pass management-account auth inputs through this call path. |
| Guard CLI contract | `scripts/guards/apply-flutter-design-aws-guards.sh:6` | Supports `--assume-role-arn`, org/account scope, JSON/text output, and runtime endpoint checks. | Make `--assume-role-arn` or profile-backed management access part of the documented deploy contract. |
| Guard identity and SCP enforcement | `scripts/guards/apply-flutter-design-aws-guards.sh:420` | Preflights caller identity, validates stack outputs and endpoint state, then enforces SCP guard policy when Organizations access exists. | Finish live enforcement from a management-account context and capture PASS evidence for `G1` and `G2`. |
| Shared runtime HTTP entrypoint | `runtime/agentcore_main.py:16` | Hosts `/ping` and `/invocations` for the shared PP + SDLC runtime. | Use as the runtime surface for live scenario evidence, not for new architectural work. |
| Shared workflow execution engine | `runtime/engine.py:27` | Executes both workflows on one runtime with audit, delegation, MCP, and RAG fixture adapters. | Use as proof that scenario separation is logical only; run live PP and SDLC evidence against the same runtime. |
| PP workflow contract | `workflow-contracts/player-protection-case-handling.json:10` | Encodes HITL before regulated write for the R3 PP flow. | Use in live PP evidence capture and completion criteria. |
| SDLC workflow contract | `workflow-contracts/pr-verification-review.json:10` | Encodes HITL before internal writeback for the R1 SDLC flow. | Use in live SDLC evidence capture and completion criteria. |
| PP capability definition | `capability-definitions/player-protection-case-orchestrator.json:12` | Declares `R3`, delegated specialist, and regulated-write bindings. | Treat as fixed brownfield artifact; verify deployment evidence rather than redesigning it. |
| SDLC capability definition | `capability-definitions/pr-verifier-orchestrator.json:12` | Declares `R1 + Process`, delegated specialist, and internal-write bindings. | Treat as fixed brownfield artifact; verify deployment evidence rather than redesigning it. |
| Bootstrap regression tests | `tests/test_bootstrap_shared_sandbox_script.py:164` | Covers runtime reuse, runtime creation, IaC bootstrap provisioning, endpoint fallback behavior, and region guards. | Extend only if new management-account bootstrap wiring changes CLI contract or behavior. |
| Guard regression tests | `tests/test_apply_flutter_design_aws_guards_script.py:211` | Covers detect-mode drift handling and access-denied enforcement failures. | Extend to cover management-account assume-role/profile plumbing and successful SCP enforcement path. |
| README deployment guidance | `README.md:14` | Still says repo is not currently a working runtime implementation, despite live runtime/bootstrap now existing. | Add docs-alignment close-out task so repo description matches implemented runtime/deploy state. |
