from typing import Any, Dict, Tuple

import boto3
from json_extract import extract_json_object
from quality_helpers import safe_int as _quality_safe_int


def _safe_int(value: Any) -> int:
    return _quality_safe_int(value)


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
