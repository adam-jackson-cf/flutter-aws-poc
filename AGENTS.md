# AGENTS.md

Project-specific defaults for AI agents working in this repository.

## Region And Deployment Defaults
- Canonical AWS region is `eu-west-1` only.
- Always pin all region flags/env vars together:
  - `AWS_REGION=eu-west-1`
  - `BEDROCK_REGION=eu-west-1`
  - `CDK_DEFAULT_REGION=eu-west-1`
- Treat any deployment or metrics in `us-east-1` as drift/superseded.
- Preferred stack is `FlutterAgentCorePocStack` in `eu-west-1`.

## Environment Source Of Truth
- Use `.envrc` (and `.envrc.example`) for local configuration.
- Do not introduce `.env` or `.env.example` flows.
- Required runtime/eval values are expected via env:
  - `AWS_PROFILE`
  - `AWS_REGION`
  - `BEDROCK_REGION`
  - `STATE_MACHINE_ARN`
  - `MCP_GATEWAY_URL`

## LLM Routing And Parity Defaults
- All model calls must go through the LLM gateway boundary (non-bypass).
- Keep Lambda pipeline and runtime semantics aligned.
- For controlled Nova baseline runs:
  - `MODEL_PROVIDER=bedrock`
  - `MODEL_ID=eu.amazon.nova-lite-v1:0`
- Record and preserve route metadata in eval artifacts:
  - `llm_route_path=gateway_service`
  - `execution_mode=route_parity`
  - `mcp_binding_mode=model_constructed_schema_validated`
  - `route_semantics_version=2`

## Eval Defaults
- Default stress dataset: `evals/golden/sop_cases_adversarial.jsonl`.
- Default comparison mode: `--flow both --scope route`.
- Full baseline cadence: `--iterations 4`.
- CloudWatch namespace: `FlutterAgentCorePoc/Evals`.
- Always pass explicit region flags to avoid drift:
  - `--aws-region eu-west-1 --bedrock-region eu-west-1`
- Run artifacts are written under:
  - `reports/runs/<RUN_ID>/eval/eval-both-route.json`

## Dashboard Defaults
- Use `scripts/create-cloudwatch-dashboard.sh` with:
  - `--region eu-west-1`
  - `--namespace FlutterAgentCorePoc/Evals`
  - `--dataset evals/golden/sop_cases_adversarial.jsonl`
  - `--scope route`
- Existing dashboard in use:
  - `FlutterAgentCorePoc-Eval-20260227T220500Z`

## Quality Gate Defaults
- Before commit or handoff, run:
  - `scripts/run-ci-quality-gates.sh`

## Security Defaults
- Never print secret values in terminal output.
- Use presence checks for env/secrets; mask values if display is unavoidable.
