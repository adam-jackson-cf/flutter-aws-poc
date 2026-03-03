import os
from dataclasses import dataclass
from typing import Any, Dict, List

from ..tools.llm_gateway_invoke_client import invoke_llm_gateway
from .generation_stage import _extract_json

ALLOWED_INTENTS = ("bug_triage", "feature_request", "status_update", "general_triage")


@dataclass(frozen=True)
class GroundingConfig:
    model_id: str
    region: str
    model_provider: str
    provider_options: Dict[str, Any] | None
    dry_run: bool = False


def _max_attempts() -> int:
    raw = str(os.environ.get("GROUNDING_MAX_ATTEMPTS", "2")).strip() or "2"
    try:
        parsed = int(raw)
    except ValueError as exc:
        raise ValueError("grounding_max_attempts_invalid") from exc
    if parsed < 1:
        raise ValueError("grounding_max_attempts_invalid")
    return parsed


def _validation_error(intent: str, issue_key: str, candidate_issue_keys: List[str]) -> str:
    if intent not in ALLOWED_INTENTS:
        return f"grounding_invalid_intent:{intent}"
    if issue_key not in candidate_issue_keys:
        return f"grounding_invalid_issue_key:{issue_key}"
    return ""


def _grounding_prompt(
    *,
    intake_seed: Dict[str, Any],
    candidate_issue_keys: List[str],
    intent_hint: str,
    retry_feedback: str,
) -> str:
    return (
        "You are a request-grounding agent for Jira support automation.\n"
        "Resolve the final intent and issue_key from the request.\n"
        f"Request: {intake_seed.get('request_text', '')}\n"
        f"Candidate issue keys: {candidate_issue_keys}\n"
        f"Intent hint: {intent_hint}\n"
        f"Previous attempt feedback: {retry_feedback or 'none'}\n"
        "Return strict JSON only with keys intent, issue_key, reason.\n"
        "Constraints:\n"
        "- issue_key must be one of candidate issue keys.\n"
        "- intent must be one of bug_triage, feature_request, status_update, general_triage.\n"
    )


def _grounding_attempt(
    *,
    intake_seed: Dict[str, Any],
    config: GroundingConfig,
    candidate_issue_keys: List[str],
    intent_hint: str,
    retry_feedback: str,
) -> tuple[str, str, str, str]:
    try:
        raw = invoke_llm_gateway(
            model_id=config.model_id,
            prompt=_grounding_prompt(
                intake_seed=intake_seed,
                candidate_issue_keys=candidate_issue_keys,
                intent_hint=intent_hint,
                retry_feedback=retry_feedback,
            ),
            region=config.region,
            provider=config.model_provider,
            provider_options=config.provider_options,
        )
        parsed = _extract_json(raw)
        selected_intent = str(parsed.get("intent", "")).strip()
        selected_issue_key = str(parsed.get("issue_key", "")).strip()
        reason = str(parsed.get("reason", "")).strip()
        error = _validation_error(selected_intent, selected_issue_key, candidate_issue_keys)
        return selected_intent, selected_issue_key, reason, error
    except Exception as exc:  # noqa: BLE001 - grounding retries are first-class behavior
        return "", "", "", f"grounding_response_invalid:{exc}"


def resolve_request_grounding(intake_seed: Dict[str, Any], config: GroundingConfig) -> Dict[str, Any]:
    candidate_issue_keys = [str(value).strip() for value in intake_seed.get("candidate_issue_keys", []) if str(value).strip()]
    if not candidate_issue_keys:
        raise ValueError("grounding_candidate_issue_keys_missing")
    intent_hint = str(intake_seed.get("intent_hint", "general_triage")).strip() or "general_triage"
    if config.dry_run:
        return {
            "intent": intent_hint,
            "issue_key": candidate_issue_keys[0],
            "reason": "dry_run",
            "attempts": 1,
            "retries": 0,
            "failures": 0,
            "failure_reason": "",
        }

    attempts = 0
    failures = 0
    retry_feedback = ""
    last_failure_reason = ""

    while attempts < _max_attempts():
        attempts += 1
        selected_intent, selected_issue_key, reason, error = _grounding_attempt(
            intake_seed=intake_seed,
            config=config,
            candidate_issue_keys=candidate_issue_keys,
            intent_hint=intent_hint,
            retry_feedback=retry_feedback,
        )

        if not error:
            return {
                "intent": selected_intent,
                "issue_key": selected_issue_key,
                "reason": reason,
                "attempts": attempts,
                "retries": max(0, attempts - 1),
                "failures": failures,
                "failure_reason": "",
            }

        failures += 1
        last_failure_reason = error
        retry_feedback = (
            f"Previous grounding attempt invalid: {error}. "
            "Resolve with one valid issue key from the candidate set and one valid intent."
        )

    return {
        "intent": "",
        "issue_key": "",
        "reason": "",
        "attempts": attempts,
        "retries": max(0, attempts - 1),
        "failures": failures,
        "failure_reason": last_failure_reason or "grounding_retry_exhausted",
    }
