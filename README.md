# Flutter AgentCore SOP PoC

This repository contains a proof-of-concept that compares two orchestration paths for the same Jira-backed support SOP:

- `native`: Python Strands agent using a robust Jira SDK tool.
- `mcp`: real AWS AgentCore Gateway MCP tool discovery + tool call path (no simulated tool execution).

It also includes AWS CDK infrastructure for:

- AgentCore Runtime (code deployment)
- AgentCore Gateway with Jira tool target
- Step Functions automation pipeline with scheduled execution

## Quick start

1. Install Python dependencies:
   - `python3 -m pip install -r requirements.txt`
2. Install infra dependencies:
   - `cd infra && npm install`
3. Load project AWS context:
   - `direnv allow` (uses `.envrc` with sandbox profile + Bedrock inference profile)
   - ensure `MCP_GATEWAY_URL` and `STATE_MACHINE_ARN` are set for live runs
4. Run synthesis:
   - `cd infra && npm run cdk:synth`
5. Run a dry-run evaluation through the deployed Step Functions pipeline:
   - `python3 evals/run_eval.py --dataset evals/golden/sop_cases.jsonl --flow both --scope route --iterations 5 --run-id 20260227T220000Z --state-machine-arn "$STATE_MACHINE_ARN" --aws-region "$AWS_REGION" --dry-run`
6. Run statistically meaningful live route evaluation and publish deterministic metrics to CloudWatch:
   - `python3 evals/run_eval.py --dataset evals/golden/sop_cases.jsonl --flow both --scope route --iterations 10 --run-id 20260227T220000Z --state-machine-arn "$STATE_MACHINE_ARN" --aws-region "$AWS_REGION" --publish-cloudwatch`

## AgentCore online evaluations setup

Create or update an AgentCore online evaluation config:

- `python3 scripts/configure-agentcore-online-eval.py --name flutter-sop-poc-online-eval --role-arn "<EVAL_EXECUTION_ROLE_ARN>" --log-group "/aws/bedrock-agentcore/runtimes/flutterSopPocRuntime" --service-name bedrock-agentcore --evaluator-id "<EVALUATOR_ID_1>" --evaluator-id "<EVALUATOR_ID_2>" --aws-region "$AWS_REGION"`

## Direct runtime usage

- Native flow:
  - `python3 -m runtime.sop_agent.main --flow native --input-file samples/case_001.json --dry-run`
- MCP flow:
  - `python3 -m runtime.sop_agent.main --flow mcp --input-file samples/case_001.json --dry-run`

## Notes

- The dataset uses publicly accessible Jira issues from `jira.atlassian.com`.
- Non-dry-run mode requires Bedrock inference profile access for tool selection (`mcp`) and generation stages (`eu.amazon.nova-lite-v1:0` by default).
- MCP flow requires a reachable, deployed AgentCore Gateway URL in `MCP_GATEWAY_URL`.
- If `--output` is omitted, eval results are written to `reports/runs/<RUN_ID>/eval/eval-<flow>-<scope>.json`.
- If `--publish-cloudwatch` is enabled, deterministic summary metrics are emitted to CloudWatch namespace `FlutterAgentCorePoc/Evals` (or `--cloudwatch-namespace` override).
- Eval output includes `failure_reasons`; payload-shape failures now appear as `mcp_missing_issue_payload` (runtime) or `mcp_gateway_missing_issue_payload` (Lambda pipeline stage).
