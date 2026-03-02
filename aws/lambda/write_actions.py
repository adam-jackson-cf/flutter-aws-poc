import hashlib
import json
import time
import uuid
from typing import Any, Dict

import boto3


def _note_digest(note_text: str) -> str:
    return hashlib.sha256(note_text.encode("utf-8")).hexdigest()


def _write_key(issue_key: str) -> str:
    timestamp_ms = int(time.time() * 1000)
    suffix = uuid.uuid4().hex[:10]
    return f"writes/{issue_key}/{timestamp_ms}-{suffix}.json"


def write_issue_followup_note(issue: Dict[str, Any], note_text: str, result_bucket: str) -> Dict[str, Any]:
    normalized_note = str(note_text).strip()
    if not normalized_note:
        raise ValueError("note_text_missing")
    if not result_bucket:
        raise RuntimeError("result_bucket_missing_for_write_tool")

    issue_key = str(issue.get("key", "")).strip()
    if not issue_key:
        raise ValueError("issue_key_missing_for_write_tool")

    artifact_key = _write_key(issue_key)
    payload = {
        "issue_key": issue_key,
        "note_text": normalized_note,
        "written_at_ms": int(time.time() * 1000),
    }
    boto3.client("s3").put_object(
        Bucket=result_bucket,
        Key=artifact_key,
        Body=json.dumps(payload).encode("utf-8"),
        ContentType="application/json",
    )
    return {
        "key": issue_key,
        "write_status": "committed",
        "write_artifact_s3_uri": f"s3://{result_bucket}/{artifact_key}",
        "note_digest": _note_digest(normalized_note),
    }
