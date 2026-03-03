from dataclasses import dataclass
from typing import Any, Dict, List

from ..domain import classify_intent as _classify_intent
from ..domain import extract_intake as _extract_intake
from ..domain import extract_risk_hints as _extract_risk_hints
from .request_grounding_stage import GroundingConfig, resolve_request_grounding


class IntakeError(ValueError):
    pass


@dataclass(frozen=True)
class IntakeModelConfig:
    model_id: str
    region: str
    model_provider: str = "auto"
    provider_options: Dict[str, Any] | None = None
    dry_run: bool = False


def classify_intent(request_text: str) -> str:
    return _classify_intent(request_text)


def extract_risk_hints(request_text: str) -> List[str]:
    return _extract_risk_hints(request_text)


def run_intake(
    request_text: str,
    config: IntakeModelConfig,
) -> Dict[str, Any]:
    try:
        intake_seed = _extract_intake(request_text)
        grounding = resolve_request_grounding(
            intake_seed=intake_seed,
            config=GroundingConfig(
                model_id=config.model_id,
                region=config.region,
                model_provider=config.model_provider,
                provider_options=config.provider_options,
                dry_run=config.dry_run,
            ),
        )
        failure_reason = str(grounding.get("failure_reason", "")).strip()
        if failure_reason:
            raise ValueError(f"grounding_resolution_failed:{failure_reason}")
        return {
            "request_text": intake_seed["request_text"],
            "candidate_issue_keys": list(intake_seed["candidate_issue_keys"]),
            "issue_key": str(grounding.get("issue_key", "")),
            "intent_hint": str(intake_seed.get("intent_hint", "general_triage")),
            "intent": str(grounding.get("intent", "")),
            "risk_hints": list(intake_seed.get("risk_hints", [])),
        }
    except ValueError as exc:
        raise IntakeError(str(exc)) from exc
