#!/usr/bin/env python3
import argparse
import os
from typing import Any, Dict, List, Optional

import boto3


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create or update an AgentCore online evaluation config")
    parser.add_argument("--name", required=True, help="Online evaluation config name")
    parser.add_argument("--role-arn", required=True, help="IAM role ARN used by online evaluation execution")
    parser.add_argument("--log-group", action="append", required=True, help="CloudWatch log group name (repeatable)")
    parser.add_argument("--service-name", action="append", default=[], help="CloudWatch service name filter (repeatable)")
    parser.add_argument("--evaluator-id", action="append", required=True, help="Evaluator ID to include (repeatable)")
    parser.add_argument("--sampling-percentage", type=float, default=100.0)
    parser.add_argument("--session-timeout-minutes", type=int, default=60)
    parser.add_argument("--description", default="Online evaluation for flutter-agentcore-poc")
    parser.add_argument("--execution-status", choices=["ENABLED", "DISABLED"], default="ENABLED")
    parser.add_argument("--aws-profile", default=os.environ.get("AWS_PROFILE", ""))
    parser.add_argument("--aws-region", default=os.environ.get("AWS_REGION", ""))
    return parser.parse_args()


def _build_session(profile: Optional[str], region: str) -> boto3.Session:
    if not region:
        raise ValueError("AWS region is required (set AWS_REGION or pass --aws-region)")
    kwargs: Dict[str, str] = {"region_name": region}
    if profile:
        kwargs["profile_name"] = profile
    return boto3.Session(**kwargs)


def _find_config_id(client: Any, name: str) -> Optional[str]:
    next_token: Optional[str] = None
    while True:
        kwargs: Dict[str, Any] = {}
        if next_token:
            kwargs["nextToken"] = next_token
        response = client.list_online_evaluation_configs(**kwargs)
        for item in response.get("onlineEvaluationConfigs", []):
            if item.get("onlineEvaluationConfigName") == name:
                return item.get("onlineEvaluationConfigId")
        next_token = response.get("nextToken")
        if not next_token:
            return None


def _request_body(args: argparse.Namespace) -> Dict[str, Any]:
    service_names = args.service_name or ["bedrock-agentcore"]
    return {
        "description": args.description,
        "rule": {
            "samplingConfig": {"samplingPercentage": args.sampling_percentage},
            "sessionConfig": {"sessionTimeoutMinutes": args.session_timeout_minutes},
        },
        "dataSourceConfig": {
            "cloudWatchLogs": {
                "logGroupNames": args.log_group,
                "serviceNames": service_names,
            }
        },
        "evaluators": [{"evaluatorId": evaluator_id} for evaluator_id in args.evaluator_id],
        "evaluationExecutionRoleArn": args.role_arn,
    }


def main() -> int:
    args = parse_args()
    session = _build_session(profile=args.aws_profile or None, region=args.aws_region)
    client = session.client("bedrock-agentcore-control")

    body = _request_body(args)
    existing_id = _find_config_id(client=client, name=args.name)
    if existing_id:
        response = client.update_online_evaluation_config(
            onlineEvaluationConfigId=existing_id,
            executionStatus=args.execution_status,
            **body,
        )
        action = "UPDATED"
    else:
        response = client.create_online_evaluation_config(
            onlineEvaluationConfigName=args.name,
            enableOnCreate=(args.execution_status == "ENABLED"),
            **body,
        )
        action = "CREATED"

    print(f"ACTION={action}")
    print(f"ONLINE_EVAL_CONFIG_ID={response['onlineEvaluationConfigId']}")
    print(f"ONLINE_EVAL_CONFIG_ARN={response['onlineEvaluationConfigArn']}")
    print(f"STATUS={response.get('status', '')}")
    print(f"EXECUTION_STATUS={response.get('executionStatus', '')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
