import json
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Dict, Tuple

from json_extract import extract_json_object
from llm_gateway_invoke_client import invoke_llm_gateway_with_usage


@dataclass(frozen=True)
class ResponseGenerationConfig:
    model_id: str
    region: str
    dry_run: bool = False
    model_provider: str = "auto"
    provider_options: Dict[str, Any] | None = None


def _customer_response_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "customer_response": {"type": "string"},
            "internal_actions": {
                "type": "array",
                "items": {"type": "string"},
            },
            "risk_level": {"type": "string", "enum": ["low", "medium", "high"]},
        },
        "required": ["customer_response", "internal_actions", "risk_level"],
        "additionalProperties": False,
    }


def _provider_options_with_response_schema(provider_options: Dict[str, Any] | None) -> Dict[str, Any]:
    options: Dict[str, Any] = deepcopy(provider_options) if isinstance(provider_options, dict) else {}
    openai_options = options.get("openai")
    if not isinstance(openai_options, dict):
        openai_options = {}
    openai_options["response_json_schema"] = {
        "name": "customer_response",
        "schema": _customer_response_schema(),
        "strict": True,
    }
    options["openai"] = openai_options
    return options


def _empty_usage() -> Dict[str, int]:
    return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}


def generate_customer_response_with_usage(
    intake: Dict[str, Any],
    tool_result: Dict[str, Any],
    config: ResponseGenerationConfig,
) -> Tuple[Dict[str, Any], Dict[str, int]]:
    if config.dry_run:
        return (
            {
                "customer_response": f"Acknowledged {intake['issue_key']}. Current status is {tool_result.get('status', 'Unknown')}.",
                "internal_actions": ["Validate fix scope", "Confirm release timeline", "Prepare customer-safe update"],
                "risk_level": "medium" if intake.get("intent") == "bug_triage" else "low",
            },
            _empty_usage(),
        )

    prompt = (
        "You are an enterprise support SOP assistant.\n"
        "Generate a concise customer-safe update plus internal actions.\n"
        "Return strict JSON with keys: customer_response (string), internal_actions (array of strings), risk_level (low|medium|high).\n"
        f"Intake JSON: {json.dumps(intake)}\n"
        f"Tool JSON: {json.dumps(tool_result)}"
    )
    request_provider_options = _provider_options_with_response_schema(config.provider_options)

    raw, usage = invoke_llm_gateway_with_usage(
        model_id=config.model_id,
        prompt=prompt,
        region=config.region,
        provider=config.model_provider,
        provider_options=request_provider_options,
    )
    parsed = extract_json_object(raw)

    actions = parsed.get("internal_actions", [])
    if not isinstance(actions, list):
        raise ValueError("invalid_internal_actions")

    return (
        {
            "customer_response": str(parsed.get("customer_response", "")).strip(),
            "internal_actions": [str(item) for item in actions],
            "risk_level": str(parsed.get("risk_level", "medium")).lower(),
        },
        usage,
    )


def generate_customer_response(
    intake: Dict[str, Any],
    tool_result: Dict[str, Any],
    config: ResponseGenerationConfig,
) -> Dict[str, Any]:
    response, _usage = generate_customer_response_with_usage(
        intake=intake,
        tool_result=tool_result,
        config=config,
    )
    return response
