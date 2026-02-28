import json
import re
from typing import Any, Dict

import boto3


class GenerationError(RuntimeError):
    pass


def _extract_json(raw_text: str) -> Dict[str, Any]:
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise GenerationError("Model output did not include JSON object")
    candidate = raw_text[start : end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        repaired = re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", candidate)
        return json.loads(repaired)


def generate_response(
    intake: Dict[str, Any],
    issue: Dict[str, Any],
    model_id: str,
    region: str,
    dry_run: bool = False,
) -> Dict[str, Any]:
    if dry_run:
        return {
            "customer_response": f"We are tracking {issue.get('key', intake['issue_key'])} and will share the next update shortly.",
            "internal_actions": [
                "Confirm the latest status with the owning team",
                "Prepare a customer-safe update",
                "Document next checkpoint in support workflow",
            ],
            "risk_level": "medium" if intake["intent"] == "bug_triage" else "low",
        }

    prompt = (
        "You are a support SOP assistant for enterprise incident communications.\n"
        "Produce strict JSON with keys: customer_response (string), internal_actions (array of strings), risk_level (low|medium|high).\n"
        f"Intake data: {json.dumps(intake)}\n"
        f"Issue data: {json.dumps(issue)}"
    )

    client = boto3.client("bedrock-runtime", region_name=region)
    response = client.converse(
        modelId=model_id,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"temperature": 0.2, "maxTokens": 700},
    )

    text_parts = [chunk.get("text", "") for chunk in response["output"]["message"]["content"] if "text" in chunk]
    payload = _extract_json("\n".join(text_parts))

    if not isinstance(payload.get("internal_actions", []), list):
        raise GenerationError("internal_actions is not an array")

    return {
        "customer_response": str(payload.get("customer_response", "")).strip(),
        "internal_actions": [str(item) for item in payload.get("internal_actions", [])],
        "risk_level": str(payload.get("risk_level", "medium")).lower(),
    }
