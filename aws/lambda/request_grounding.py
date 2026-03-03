import os
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Dict, List

from json_extract import extract_json_object
from llm_gateway_invoke_client import invoke_llm_gateway_with_usage
from quality_helpers import parse_positive_int, merge_usage as _quality_merge_usage, safe_int as _quality_safe_int

ALLOWED_INTENTS = ("bug_triage", "feature_request", "status_update", "general_triage")


@dataclass(frozen=True)
class GroundingLlmConfig:
    model_id: str
    region: str
    model_provider: str
    provider_options: Dict[str, Dict[str, Any]] | None


def _empty_usage() -> Dict[str, int]:
    return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}


def _safe_int(value: Any) -> int:
    return _quality_safe_int(value)


def _merge_usage(base: Dict[str, int], additional: Dict[str, int]) -> Dict[str, int]:
    return _quality_merge_usage(base, additional)


def _parse_max_attempts(value: str) -> int:
    return parse_positive_int(value, error_code="grounding_max_attempts_invalid")


def _max_grounding_attempts() -> int:
    raw = str(os.environ.get("GROUNDING_MAX_ATTEMPTS", "2")).strip() or "2"
    return _parse_max_attempts(raw)


def _grounding_response_schema(candidate_issue_keys: List[str]) -> Dict[str, Any]:
    issue_key_property: Dict[str, Any] = {"type": "string"}
    if candidate_issue_keys:
        issue_key_property["enum"] = candidate_issue_keys
    return {
        "type": "object",
        "properties": {
            "intent": {"type": "string", "enum": list(ALLOWED_INTENTS)},
            "issue_key": issue_key_property,
            "reason": {"type": "string"},
        },
        "required": ["intent", "issue_key", "reason"],
        "additionalProperties": False,
    }


def _provider_options_with_json_schema(
    provider_options: Dict[str, Dict[str, Any]] | None,
    *,
    schema_name: str,
    response_schema: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    options: Dict[str, Dict[str, Any]] = deepcopy(provider_options) if isinstance(provider_options, dict) else {}
    openai_options = options.get("openai")
    if not isinstance(openai_options, dict):
        openai_options = {}
    openai_options["response_json_schema"] = {
        "name": schema_name,
        "schema": response_schema,
        "strict": True,
    }
    options["openai"] = openai_options
    return options


def _grounding_prompt(
    *,
    request_text: str,
    candidate_issue_keys: List[str],
    intent_hint: str,
    retry_feedback: str,
) -> str:
    return (
        "You are a request-grounding agent for Jira support automation.\n"
        "Resolve the final intent and issue_key from the request.\n"
        f"Request: {request_text}\n"
        f"Candidate issue keys: {candidate_issue_keys}\n"
        f"Intent hint: {intent_hint}\n"
        f"Previous attempt feedback: {retry_feedback or 'none'}\n"
        "Return strict JSON only with keys intent, issue_key, reason.\n"
        "Constraints:\n"
        "- issue_key must be one of candidate issue keys.\n"
        "- intent must be one of bug_triage, feature_request, status_update, general_triage.\n"
    )


def _validation_error(intent: str, issue_key: str, candidate_issue_keys: List[str]) -> str:
    if intent not in ALLOWED_INTENTS:
        return f"grounding_invalid_intent:{intent}"
    if issue_key not in candidate_issue_keys:
        return f"grounding_invalid_issue_key:{issue_key}"
    return ""


def _normalized_candidate_issue_keys(intake_seed: Dict[str, Any]) -> List[str]:
    candidate_issue_keys = intake_seed.get("candidate_issue_keys", [])
    if not isinstance(candidate_issue_keys, list) or not candidate_issue_keys:
        raise ValueError("grounding_candidate_issue_keys_missing")
    normalized = [str(value).strip() for value in candidate_issue_keys if str(value).strip()]
    if not normalized:
        raise ValueError("grounding_candidate_issue_keys_missing")
    return normalized


def _dry_run_grounding_result(
    *,
    intent_hint: str,
    issue_key: str,
) -> Dict[str, Any]:
    return {
        "intent": intent_hint,
        "issue_key": issue_key,
        "reason": "dry_run",
        "attempts": 1,
        "retries": 0,
        "failures": 0,
        "failure_reason": "",
        "llm_usage": _empty_usage(),
        "attempt_trace": [
            {
                "attempt": 1,
                "intent": intent_hint,
                "issue_key": issue_key,
                "validation_error": "",
                "status": "valid",
            }
        ],
    }


def _grounding_attempt_payload(
    *,
    intake_seed: Dict[str, Any],
    llm_config: GroundingLlmConfig,
    candidate_issue_keys: List[str],
    intent_hint: str,
    retry_feedback: str,
) -> tuple[str, str, str, str, Dict[str, int]]:
    prompt = _grounding_prompt(
        request_text=str(intake_seed.get("request_text", "")),
        candidate_issue_keys=candidate_issue_keys,
        intent_hint=intent_hint,
        retry_feedback=retry_feedback,
    )
    provider_options_with_schema = _provider_options_with_json_schema(
        llm_config.provider_options,
        schema_name="request_grounding",
        response_schema=_grounding_response_schema(candidate_issue_keys),
    )
    raw, usage = invoke_llm_gateway_with_usage(
        model_id=llm_config.model_id,
        prompt=prompt,
        region=llm_config.region,
        provider=llm_config.model_provider,
        provider_options=provider_options_with_schema,
    )
    parsed = extract_json_object(raw)
    selected_intent = str(parsed.get("intent", "")).strip()
    selected_issue_key = str(parsed.get("issue_key", "")).strip()
    reason = str(parsed.get("reason", "")).strip()
    validation_error = _validation_error(selected_intent, selected_issue_key, candidate_issue_keys)
    return selected_intent, selected_issue_key, reason, validation_error, usage


def _grounding_success_result(
    *,
    selected_intent: str,
    selected_issue_key: str,
    reason: str,
    state: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "intent": selected_intent,
        "issue_key": selected_issue_key,
        "reason": reason,
        "attempts": int(state.get("attempts", 0)),
        "retries": max(0, int(state.get("attempts", 0)) - 1),
        "failures": int(state.get("failures", 0)),
        "failure_reason": "",
        "llm_usage": state.get("usage_totals", _empty_usage()),
        "attempt_trace": state.get("attempt_trace", []),
    }


def _grounding_exhausted_result(
    *,
    attempts: int,
    failures: int,
    last_failure_reason: str,
    usage_totals: Dict[str, int],
    attempt_trace: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "intent": "",
        "issue_key": "",
        "reason": "",
        "attempts": attempts,
        "retries": max(0, attempts - 1),
        "failures": failures,
        "failure_reason": last_failure_reason or "grounding_retry_exhausted",
        "llm_usage": usage_totals,
        "attempt_trace": attempt_trace,
    }


def resolve_request_grounding(
    *,
    intake_seed: Dict[str, Any],
    dry_run: bool,
    llm_config: GroundingLlmConfig,
) -> Dict[str, Any]:
    candidate_issue_keys = _normalized_candidate_issue_keys(intake_seed)
    intent_hint = str(intake_seed.get("intent_hint", "general_triage")).strip() or "general_triage"
    if dry_run:
        return _dry_run_grounding_result(intent_hint=intent_hint, issue_key=candidate_issue_keys[0])

    max_attempts = _max_grounding_attempts()
    attempts = 0
    failures = 0
    retry_feedback = ""
    usage_totals = _empty_usage()
    last_failure_reason = ""
    attempt_trace: List[Dict[str, Any]] = []

    while attempts < max_attempts:
        attempts += 1
        try:
            selected_intent, selected_issue_key, reason, validation_error, usage = _grounding_attempt_payload(
                intake_seed=intake_seed,
                llm_config=llm_config,
                candidate_issue_keys=candidate_issue_keys,
                intent_hint=intent_hint,
                retry_feedback=retry_feedback,
            )
            usage_totals = _merge_usage(usage_totals, usage)
        except Exception as exc:  # noqa: BLE001 - retries are first-class for grounding robustness
            selected_intent = ""
            selected_issue_key = ""
            reason = ""
            validation_error = f"grounding_response_invalid:{exc}"

        attempt_trace.append(
            {
                "attempt": attempts,
                "intent": selected_intent,
                "issue_key": selected_issue_key,
                "validation_error": validation_error,
                "status": "invalid" if validation_error else "valid",
            }
        )
        if not validation_error:
            return _grounding_success_result(
                selected_intent=selected_intent,
                selected_issue_key=selected_issue_key,
                reason=reason,
                state={
                    "attempts": attempts,
                    "failures": failures,
                    "usage_totals": usage_totals,
                    "attempt_trace": attempt_trace,
                },
            )

        failures += 1
        last_failure_reason = validation_error
        retry_feedback = (
            f"Previous grounding attempt invalid: {validation_error}. "
            "Resolve with one valid issue key from the candidate set and one valid intent."
        )

    return _grounding_exhausted_result(
        attempts=attempts,
        failures=failures,
        last_failure_reason=last_failure_reason,
        usage_totals=usage_totals,
        attempt_trace=attempt_trace,
    )
