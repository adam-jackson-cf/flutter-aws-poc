from typing import Any, Dict, List

from ..domain import classify_intent as _classify_intent
from ..domain import extract_intake as _extract_intake
from ..domain import extract_risk_hints as _extract_risk_hints


class IntakeError(ValueError):
    pass


def classify_intent(request_text: str) -> str:
    return _classify_intent(request_text)


def extract_risk_hints(request_text: str) -> List[str]:
    return _extract_risk_hints(request_text)


def run_intake(request_text: str) -> Dict[str, Any]:
    try:
        return _extract_intake(request_text)
    except ValueError as exc:
        raise IntakeError(str(exc)) from exc
