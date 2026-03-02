import json
import re
from typing import Any, Dict, Tuple

import boto3


def extract_json_object(raw_text: str) -> dict:
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("model_response_missing_json")
    candidate = raw_text[start : end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        repaired = re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", candidate)
        return json.loads(repaired)


def _safe_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return 0
    return 0


def _bedrock_usage(response: Dict[str, Any]) -> Dict[str, int]:
    usage = response.get("usage", {})
    if not isinstance(usage, dict):
        usage = {}
    input_tokens = _safe_int(usage.get("inputTokens", 0))
    output_tokens = _safe_int(usage.get("outputTokens", 0))
    total_tokens = _safe_int(usage.get("totalTokens", input_tokens + output_tokens))
    return {
        "input_tokens": max(0, input_tokens),
        "output_tokens": max(0, output_tokens),
        "total_tokens": max(0, total_tokens),
    }


def call_bedrock_with_usage(
    model_id: str,
    prompt: str,
    region: str,
) -> Tuple[str, Dict[str, int]]:
    client = boto3.client("bedrock-runtime", region_name=region)
    response = client.converse(
        modelId=model_id,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"temperature": 0.2, "maxTokens": 700},
    )
    content = response["output"]["message"]["content"]
    parts = [part.get("text", "") for part in content if "text" in part]
    return "\n".join(parts), _bedrock_usage(response)


def call_bedrock(model_id: str, prompt: str, region: str) -> str:
    text, _usage = call_bedrock_with_usage(model_id=model_id, prompt=prompt, region=region)
    return text
