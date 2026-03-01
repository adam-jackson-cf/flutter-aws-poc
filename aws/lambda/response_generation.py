import json
from typing import Any, Dict

from bedrock_client import call_bedrock, extract_json_object


def generate_customer_response(
    intake: Dict[str, Any],
    tool_result: Dict[str, Any],
    model_id: str,
    region: str,
    dry_run: bool = False,
) -> Dict[str, Any]:
    if dry_run:
        return {
            "customer_response": f"Acknowledged {intake['issue_key']}. Current status is {tool_result.get('status', 'Unknown')}.",
            "internal_actions": ["Validate fix scope", "Confirm release timeline", "Prepare customer-safe update"],
            "risk_level": "medium" if intake.get("intent") == "bug_triage" else "low",
        }

    prompt = (
        "You are an enterprise support SOP assistant.\n"
        "Generate a concise customer-safe update plus internal actions.\n"
        "Return strict JSON with keys: customer_response (string), internal_actions (array of strings), risk_level (low|medium|high).\n"
        f"Intake JSON: {json.dumps(intake)}\n"
        f"Tool JSON: {json.dumps(tool_result)}"
    )

    raw = call_bedrock(model_id=model_id, prompt=prompt, region=region)
    parsed = extract_json_object(raw)

    actions = parsed.get("internal_actions", [])
    if not isinstance(actions, list):
        raise ValueError("invalid_internal_actions")

    return {
        "customer_response": str(parsed.get("customer_response", "")).strip(),
        "internal_actions": [str(item) for item in actions],
        "risk_level": str(parsed.get("risk_level", "medium")).lower(),
    }
