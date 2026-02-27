# Runbook

## Objective

Provision and run the Flutter AgentCore SOP PoC, then compare MCP-style and Strands-native orchestration quality.

## Prerequisites

- AWS profile with permissions for AgentCore, Lambda, Step Functions, EventBridge, S3, IAM.
- Node.js and npm.
- Python 3.12.

## Environment

- Load `.envrc` (recommended):
  - `direnv allow`
- Effective defaults:
  - `AWS_PROFILE=530267068969_StandardAdmin`
  - `AWS_REGION=eu-west-1`
  - `BEDROCK_MODEL_ID=eu.amazon.nova-lite-v1:0`
  - `MCP_GATEWAY_URL=<deployed_gateway_url>`
  - `STATE_MACHINE_ARN=<deployed_state_machine_arn>`

## Infrastructure deployment

1. Install dependencies:
   - `cd infra && npm install`
2. Validate generated stack:
   - `npm run cdk:synth`
3. Inspect planned changes:
   - `npm run cdk:diff`
4. Deploy:
   - `npm run cdk:deploy`

If deploy fails on AgentCore runtime entrypoint validation, confirm runtime artifact entrypoint is a plain file name (`main.py`) and not a path.

## Local evaluation

1. Install Python dependencies:
   - `python3 -m pip install -r requirements.txt`
2. Run both flows against golden set via deployed Step Functions pipeline:
   - `python3 evals/run_eval.py --dataset evals/golden/sop_cases.jsonl --flow both --scope route --iterations 10 --run-id 20260227T220000Z --state-machine-arn "$STATE_MACHINE_ARN" --aws-region "$AWS_REGION"`
3. For CI smoke without Bedrock generation:
   - `python3 evals/run_eval.py --dataset evals/golden/sop_cases.jsonl --flow native --scope route --iterations 1 --run-id 20260227T220000Z --state-machine-arn "$STATE_MACHINE_ARN" --aws-region "$AWS_REGION" --dry-run`
4. Publish deterministic summary metrics to CloudWatch:
   - append `--publish-cloudwatch` (optionally `--cloudwatch-namespace "<namespace>"`)

Default output path format (if `--output` is not supplied):

- `reports/runs/<RUN_ID>/eval/eval-<flow>-<scope>.json`

## Pipeline invocation

Run the state machine manually with a case payload:

```bash
aws stepfunctions start-execution \
  --state-machine-arn "<STATE_MACHINE_ARN>" \
  --input '{"flow":"mcp","request_text":"Need customer sentiment and status update for JRASERVER-79286 before escalation.","case_id":"manual_run_001"}'
```

## AgentCore online evaluations

Create or update online evaluation configuration:

```bash
python3 scripts/configure-agentcore-online-eval.py \
  --name flutter-sop-poc-online-eval \
  --role-arn "<EVAL_EXECUTION_ROLE_ARN>" \
  --log-group "/aws/bedrock-agentcore/runtimes/flutterSopPocRuntime" \
  --service-name bedrock-agentcore \
  --evaluator-id "<EVALUATOR_ID_1>" \
  --evaluator-id "<EVALUATOR_ID_2>" \
  --aws-region "$AWS_REGION"
```

This keeps quality results in the AgentCore/CloudWatch evaluation surfaces while deterministic KPIs remain in `evals/run_eval.py` output and CloudWatch custom metrics.

## Evaluation interpretation

- `tool_failure_rate`: key signal for MCP vs native reliability comparison.
- `tool_failure_ci95_low/high`: confidence interval for observed tool failure rate.
- `mean_latency_ms`: orchestration overhead comparison.
- `mean_response_similarity`: only meaningful in `--scope full`; route scope keeps this at zero.
- `failure_reasons`: frequency map of normalized failure reason strings.

### Failure reason taxonomy

- `selected_wrong_tool:<tool_name>`: LLM selected a non-primary MCP tool from the gateway catalog.
- `selected_unknown_tool:<tool_name>`: LLM returned a tool name not present in the current gateway catalog.
- `mcp_catalog_error:<detail>` or `mcp_gateway_error:<detail>`: MCP `tools/list` failed.
- `mcp_invocation_error:<detail>` or `mcp_tool_call_error:<detail>`: MCP `tools/call` failed.
- `mcp_missing_issue_payload`: runtime MCP flow received a payload without a valid issue object.
- `mcp_gateway_missing_issue_payload`: Lambda MCP stage received a payload without a valid issue object.

## Recovery / rollback

- If deployment drift is suspected: `cd infra && npm run cdk:diff`.
- If runtime behavior regresses, re-run dry-run eval before non-dry-run.
- For stack teardown in sandbox, use standard CDK destroy only with explicit operator approval.
