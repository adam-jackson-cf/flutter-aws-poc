import time
from typing import Any, Dict

from ..domain import extract_intake
from ..tools.request_grounding import GroundingLlmConfig, resolve_request_grounding
from ..tools.runtime_config import selected_model_id, selected_model_provider, selected_provider_options, selected_region
from .stage_metrics import append_stage_metric, base_event_with_metrics


def handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    started = time.time()
    payload = base_event_with_metrics(event)

    intake_seed = extract_intake(payload["request_text"])
    grounding = resolve_request_grounding(
        intake_seed=intake_seed,
        dry_run=bool(payload.get("dry_run", False)),
        llm_config=GroundingLlmConfig(
            model_id=selected_model_id(payload),
            region=selected_region(payload),
            model_provider=selected_model_provider(payload),
            provider_options=selected_provider_options(payload),
        ),
    )
    intake = {
        "request_text": intake_seed["request_text"],
        "candidate_issue_keys": list(intake_seed["candidate_issue_keys"]),
        "issue_key": str(grounding.get("issue_key", "")),
        "intent_hint": str(intake_seed.get("intent_hint", "general_triage")),
        "intent": str(grounding.get("intent", "")),
        "risk_hints": list(intake_seed.get("risk_hints", [])),
    }
    payload["intake"] = intake
    payload["grounding"] = grounding
    payload.setdefault("llm_usage", {})
    payload["llm_usage"]["parse_grounding"] = grounding.get(
        "llm_usage",
        {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
    )
    payload["flow"] = payload.get("flow", "native")

    return append_stage_metric(
        payload,
        "parse_nlp",
        started,
        {
            "intent": intake["intent"],
            "issue_key": intake["issue_key"],
            "candidate_issue_key_count": len(intake["candidate_issue_keys"]),
            "grounding_attempts": int(grounding.get("attempts", 0)),
            "grounding_retries": int(grounding.get("retries", 0)),
            "grounding_failures": int(grounding.get("failures", 0)),
            "grounding_failure_reason": str(grounding.get("failure_reason", "")),
        },
    )
