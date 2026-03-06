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
  - `AGENT_RUNTIME_ARN`
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
- Scope note: this PoC intentionally stays in route scope for DSPy optimization and MCP-vs-native comparison, and does not implement full Flutter R2/R3 workflow-contract/HITL process-scope semantics.
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

## Command Reference (Developer Actions)

Use this as the authoritative command/action source before running operational or repo-wide tasks.

### Setup and deployment
- `./scripts/bootstrap-repo.sh`
- `./scripts/bootstrap-repo.sh --deploy-infra`
- `npm --prefix infra run cdk:diff`
- `npm --prefix infra run cdk:synth`
- `npm --prefix infra run cdk:deploy`

### Evaluation execution
- Dry run:
  - `PYTHONUNBUFFERED=1 python3 evals/run_eval.py --dataset evals/golden/sop_cases.jsonl --flow both --scope route --iterations 1 --run-id smoke --agent-runtime-arn "$AGENT_RUNTIME_ARN" --aws-region "$AWS_REGION" --dry-run`
- Baseline dry run:
  - `PYTHONUNBUFFERED=1 python3 evals/run_eval.py --dataset evals/golden/sop_cases.jsonl --flow both --scope route --iterations 5 --run-id 20260227T220000Z --agent-runtime-arn "$AGENT_RUNTIME_ARN" --aws-region "$AWS_REGION" --dry-run`
- Live benchmark:
  - `PYTHONUNBUFFERED=1 python3 evals/run_eval.py --dataset evals/golden/sop_cases.jsonl --flow both --scope route --iterations 10 --run-id 20260227T220000Z --agent-runtime-arn "$AGENT_RUNTIME_ARN" --aws-region "$AWS_REGION" --publish-cloudwatch`
- Adversarial point-1 stress:
  - `PYTHONUNBUFFERED=1 python3 evals/run_eval.py --dataset evals/golden/sop_cases_adversarial.jsonl --flow both --scope route --iterations 1 --run-id 20260302T220000Z --agent-runtime-arn "$AGENT_RUNTIME_ARN" --aws-region "$AWS_REGION"`
- Optional evaluator flags:
  - add `--enable-judge` for judge diagnostics
  - add `--publish-cloudwatch` for CloudWatch dashboard publishing
  - add `--model-id "<MODEL_ID>" --bedrock-region "$AWS_REGION"` for controlled model overrides
  - add `--model-provider auto|bedrock|openai`
  - add `--openai-reasoning-effort <low|medium|high> --openai-text-verbosity <low|medium|high> --openai-max-output-tokens <int>`
  - add `--price-input-per-1m-tokens-usd <float> --price-output-per-1m-tokens-usd <float>` for ad-hoc pricing overrides

### Quality gates
- `bash scripts/run-ci-quality-gates.sh --lane=preflight`
- `bash scripts/run-ci-quality-gates.sh --lane=fast-r1r2`
- `bash scripts/run-ci-quality-gates.sh --lane=quality-gates-core`
- `bash scripts/run-ci-quality-gates.sh --lane=extended-r3r4`
- `RUN_MUTATION_GATE=1 bash scripts/run-ci-quality-gates.sh --lane=nightly-full`
- `python3 scripts/linters/flutter-design/check-flutter-design-compliance.py --output json --timings --skip R3,R4`
- `python3 scripts/linters/flutter-design/check-flutter-design-waivers.py`
- `COMPLEXITY_MAX=10 bash scripts/run-ci-quality-gates.sh --lane=quality-gates-core`
- `RUN_DUPLICATION_SIGNALS=0 bash scripts/run-ci-quality-gates.sh --lane=quality-gates-core`
- `DUPLICATION_SIGNAL_MIN_SEVERITY=high bash scripts/run-ci-quality-gates.sh --lane=quality-gates-core`

### Dashboard and ops
- Recreate/run dashboard: `./scripts/create-cloudwatch-dashboard.sh --run-id <RUN_ID> --region "$AWS_REGION"`
- Configure AgentCore online eval: `python3 scripts/configure-agentcore-online-eval.py --name flutter-sop-poc-online-eval --role-arn "<EVAL_EXECUTION_ROLE_ARN>" --log-group "/aws/bedrock-agentcore/runtimes/flutterSopPocRuntime" --service-name bedrock-agentcore --evaluator-id "<EVALUATOR_ID_1>" --evaluator-id "<EVALUATOR_ID_2>" --aws-region "$AWS_REGION"`
- Invoke runtime benchmark path manually:
  - `PYTHONUNBUFFERED=1 python3 evals/run_eval.py --dataset evals/golden/sop_cases.jsonl --flow mcp --scope route --iterations 1 --run-id manual_run_001 --agent-runtime-arn "$AGENT_RUNTIME_ARN" --aws-region "$AWS_REGION"`

### Operational troubleshooting
- AWS auth failures (`ExpiredToken`, `aws_auth_preflight_failed`): refresh credentials for the active profile and re-run.
- Empty CloudWatch dashboard graphs: confirm run context (`RunId`, `Scope`, `Dataset`) matches `create-cloudwatch-dashboard.sh` args.
- Empty judge widgets: rerun eval with `--enable-judge`.
- Runtime payload shape is controlled by the caller (`run_eval` for benchmark runs, API caller for direct runtime paths).
- Missing optional request fields are validated as input defaults before runtime handlers are invoked.
- Re-run deterministic smoke before deeper incident debugging:
  - `PYTHONUNBUFFERED=1 python3 evals/run_eval.py --dataset evals/golden/sop_cases.jsonl --flow native --scope route --iterations 1 --run-id smoke --agent-runtime-arn "$AGENT_RUNTIME_ARN" --aws-region "$AWS_REGION" --dry-run`
- Recreate dashboard for a known run ID:
  - `./scripts/create-cloudwatch-dashboard.sh --run-id <RUN_ID> --region "$AWS_REGION"`
- Re-check planned infra changes before any deploy:
  - `npm --prefix infra run cdk:diff`

## Runtime/usage notes
- live evals through AgentCore runtime require `AGENT_RUNTIME_ARN`.
- direct runtime MCP checks require `MCP_GATEWAY_URL`.
- use `PYTHONUNBUFFERED=1` for streamed case-progress logs during long runs.
- non-dry-run evals run AWS identity preflight (`sts:GetCallerIdentity`).
- dataset rows require `expected_tool.native` and `expected_tool.mcp`; runtime invocation flow sees `expected_tool.<flow>`.
- eval artifacts validate schema per flow and fail fast on drift (`artifact_schema_invalid:*`).
- lambda and AgentCore runtime model calls route through LLM gateway (`MODEL_ID`, `MODEL_PROVIDER`).
- deployments must remain in eu-west-1; set `EPHEMERAL_STACK=false` for retained artifacts or `EPHEMERAL_STACK=true` for disposable stacks.
- for OpenAI deployed lambdas, set `OPENAI_API_KEY_SECRET_ARN` and redeploy infra.
- OpenAI defaults: `OPENAI_REASONING_EFFORT=medium`, `OPENAI_TEXT_VERBOSITY=medium`, `OPENAI_MAX_OUTPUT_TOKENS=2000`.
- model pricing snapshot source: `evals/model_pricing_usd_per_1m_tokens.json`; snapshots include catalog path/version/hash and per-1M rates.
- judge mode requires Bedrock (`BEDROCK_JUDGE_MODEL_ID`).

## Security Defaults
- Never print secret values in terminal output.
- Use presence checks for env/secrets; mask values if display is unavoidable.

## CloudWatch
- Dashboard namespace: `FlutterAgentCorePoc/Evals`
- Default metric dimensions: `RunId`, `Flow`, `Scope`, `Dataset`
