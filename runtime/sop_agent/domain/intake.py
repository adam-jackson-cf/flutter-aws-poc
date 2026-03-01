import re
from typing import Any, Dict, List

from .contracts import INTENT_KEYWORDS, ISSUE_KEY_PATTERN, RISK_HINT_TOKENS

_ISSUE_KEY_REGEX = re.compile(ISSUE_KEY_PATTERN)


def classify_intent(request_text: str) -> str:
    text = request_text.lower()
    for intent in ("bug_triage", "feature_request", "status_update"):
        if any(token in text for token in INTENT_KEYWORDS[intent]):
            return intent
    return "general_triage"


def extract_risk_hints(request_text: str) -> List[str]:
    text = request_text.lower()
    return [token for token in RISK_HINT_TOKENS if token in text]


def extract_intake(request_text: str) -> Dict[str, Any]:
    issue_keys = _ISSUE_KEY_REGEX.findall(request_text)
    if not issue_keys:
        raise ValueError("Request must include a Jira issue key, e.g. JRASERVER-79286")
    return {
        "request_text": request_text,
        "issue_key": issue_keys[0],
        "intent": classify_intent(request_text),
        "risk_hints": extract_risk_hints(request_text),
    }
