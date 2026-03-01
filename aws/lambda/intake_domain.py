import re
from typing import Any, Dict, List

from contract_values import INTENT_KEYWORDS, RISK_HINT_TOKENS

ISSUE_KEY_PATTERN = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")


def classify_intent(request_text: str) -> str:
    text = request_text.lower()
    for intent in ("bug_triage", "feature_request", "status_update"):
        if any(token in text for token in INTENT_KEYWORDS[intent]):
            return intent
    return "general_triage"


def extract_risk_hints(request_text: str) -> List[str]:
    return [token for token in RISK_HINT_TOKENS if token in request_text.lower()]


def extract_intake(request_text: str) -> Dict[str, Any]:
    issue_keys = ISSUE_KEY_PATTERN.findall(request_text)
    if not issue_keys:
        raise ValueError("No issue key found in request_text. Include a Jira key like JRASERVER-79286.")
    return {
        "request_text": request_text,
        "issue_key": issue_keys[0],
        "intent": classify_intent(request_text),
        "risk_hints": extract_risk_hints(request_text),
    }
