# Evidence Index

## Refactored source anchors

- Stack and deployment topology: `infra/lib/flutter-agentcore-poc-stack.ts`
- Eval harness + schema expectations: `evals/run_eval.py`, `evals/metrics.py`, `evals/aws_pipeline_runner.py`
- Stage contracts: `aws/lambda/fetch_native_stage.py`, `aws/lambda/fetch_mcp_stage.py`, `aws/lambda/evaluate_stage.py`
- Runtime tool flows: `runtime/sop_agent/tools/strands_native_flow.py`, `runtime/sop_agent/tools/jira_mcp_flow.py`
- Contract governance checks: `scripts/check-architecture-boundaries.py`, `scripts/check-semantic-contract-ownership.py`

## Design anchors

- `docs/flutter-uki-ai-platform-arch/architecture-overview-v9.html`
- `docs/flutter-uki-ai-platform-arch/view-orchestration-v5.html`
- `docs/flutter-uki-ai-platform-arch/view-security-identity-v7.html`
- `docs/flutter-uki-ai-platform-arch/view-request-trace-v10.html`
- `docs/flutter-uki-ai-platform-arch/component-design-v2.html`

## Fresh run artifacts

- Route run: `reports/runs/rebased-live-route-20260301T193550Z/eval/eval-both-route.json`
- Full run: `reports/runs/rebased-live-full-20260301T193821Z/eval/eval-both-full.json`

## Prior artifacts used for stale-delta analysis

- `reports/eval-comparison-live-route-100.json`
- `reports/eval-comparison-live.json`
- `reports/runs/20260227T220500Z/eval/eval-both-route.json`

## Live AWS read probes executed

- STS identity check (`aws sts get-caller-identity`) in `eu-west-1`
- Step Functions state machine status/definition inspection
- EventBridge nightly rule target inspection
- AgentCore runtime and gateway status/details inspection
- S3 object lock configuration check on artifact bucket
- Lambda function metadata inspection (LastModified/CodeSha256)

