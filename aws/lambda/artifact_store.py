import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

import boto3

from stage_metrics import utc_now


def safe_token(value: str, fallback: str = "unknown") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "-", str(value or "").strip())
    return cleaned or fallback


def persist_artifact(bucket_name: str, payload: Dict[str, Any], prefix: str = "pipeline-results") -> str:
    run_at = safe_token(payload.get("started_at", utc_now()).replace(":", "").replace("+00:00", "Z"), "run")
    flow = safe_token(payload.get("flow", "unknown"))
    case_id = safe_token(payload.get("case_id", "unknown"))
    key = (
        f"{prefix}/{datetime.now(timezone.utc).strftime('%Y/%m/%d')}/"
        f"{run_at}__{flow}__{case_id}__{uuid.uuid4()}.json"
    )
    s3_client = boto3.client("s3")
    s3_client.put_object(Bucket=bucket_name, Key=key, Body=json.dumps(payload, indent=2).encode("utf-8"), ContentType="application/json")
    return key
