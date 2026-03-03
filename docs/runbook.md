# Runbook

Primary documentation is the project README: [README.md](/Users/adamjackson/Projects/flutter-aws-poc/README.md).

This runbook is intentionally thin and only covers operational troubleshooting that complements the README.

## Operational troubleshooting
- AWS auth failures (`ExpiredToken`, `aws_auth_preflight_failed`): refresh credentials for the active profile, then re-run the command.
- Manual Step Functions payloads are shaped by your caller (`run_eval` for benchmark runs); missing optional fields in that caller are handled before Lambda handlers are invoked.
- Empty CloudWatch dashboard graphs: confirm `RunId`, `Scope`, and `Dataset` passed to `create-cloudwatch-dashboard.sh` exactly match eval publish dimensions.
- Judge widgets empty: run eval with `--enable-judge`.

## Recovery actions
- Re-run deterministic smoke first:
  - `python3 evals/run_eval.py --dataset evals/golden/sop_cases.jsonl --flow native --scope route --iterations 1 --run-id smoke --state-machine-arn "$STATE_MACHINE_ARN" --aws-region "$AWS_REGION" --dry-run`
- Recreate dashboard for known run:
  - `./scripts/create-cloudwatch-dashboard.sh --run-id <RUN_ID> --region "$AWS_REGION"`
- Re-check planned infra changes before deploy:
  - `npm --prefix infra run cdk:diff`
