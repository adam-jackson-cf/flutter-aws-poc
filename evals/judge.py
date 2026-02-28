import json
import re
from typing import Any, Dict

import boto3


class JudgeError(RuntimeError):
    pass


def _extract_json_object(raw_text: str) -> Dict[str, Any]:
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise JudgeError("judge_response_missing_json")
    candidate = raw_text[start : end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        repaired = re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", candidate)
        return json.loads(repaired)


def _bounded_score(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = 0.0
    return max(0.0, min(1.0, parsed))


class BedrockJudge:
    def __init__(self, model_id: str, region: str) -> None:
        if not model_id:
            raise ValueError("judge model_id is required")
        if not region:
            raise ValueError("judge region is required")
        self._model_id = model_id
        self._region = region
        self._client = boto3.client("bedrock-runtime", region_name=region)

    def score_case(self, case_result: Dict[str, Any], scope: str) -> Dict[str, Any]:
        payload = {
            "request_text": case_result["request_text"],
            "expected": case_result["expected"],
            "actual": case_result["actual"],
            "deterministic_metrics": case_result["metrics"],
            "scope": scope,
        }
        prompt = (
            "You are an evaluation judge for an enterprise support agent workflow.\n"
            "Score operational behavior, not prose style.\n"
            "Scoring rubric:\n"
            "- tool_choice_score (0..1): correct tool selected for the request objective.\n"
            "- execution_reliability_score (0..1): output payload validity and failure handling.\n"
            "- response_quality_score (0..1): customer response usefulness/safety if provided; 0 when absent.\n"
            "- overall_score (0..1): weighted blend (tool_choice 0.45, execution_reliability 0.4, response_quality 0.15).\n"
            "Label rules:\n"
            "- pass: overall >= 0.85 and no critical reliability concerns.\n"
            "- review: 0.65 <= overall < 0.85 or mixed signal.\n"
            "- fail: overall < 0.65 or critical operational issue.\n"
            "Return strict JSON only with keys:\n"
            "tool_choice_score, execution_reliability_score, response_quality_score, overall_score, label, rationale.\n"
            f"Case JSON: {json.dumps(payload)}"
        )
        response = self._client.converse(
            modelId=self._model_id,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"temperature": 0.0, "maxTokens": 500},
        )
        content = response["output"]["message"]["content"]
        text = "\n".join([part.get("text", "") for part in content if "text" in part])
        parsed = _extract_json_object(text)

        tool_choice_score = _bounded_score(parsed.get("tool_choice_score"))
        execution_reliability_score = _bounded_score(parsed.get("execution_reliability_score"))
        response_quality_score = _bounded_score(parsed.get("response_quality_score"))
        overall_score = _bounded_score(parsed.get("overall_score"))
        label = str(parsed.get("label", "review")).strip().lower() or "review"
        if label not in {"pass", "review", "fail"}:
            label = "review"
        rationale = str(parsed.get("rationale", "")).strip()

        return {
            "tool_choice_score": tool_choice_score,
            "execution_reliability_score": execution_reliability_score,
            "response_quality_score": response_quality_score,
            "overall_score": overall_score,
            "label": label,
            "rationale": rationale,
        }
