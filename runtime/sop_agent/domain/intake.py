import re
from typing import Any, Dict, List

from .contracts import INTENT_KEYWORDS, ISSUE_KEY_PATTERN, RISK_HINT_TOKENS

_ISSUE_KEY_REGEX = re.compile(ISSUE_KEY_PATTERN)


def classify_intent(request_text: str) -> str:
    text = request_text.lower()
    scores = {
        intent: sum(1 for token in tokens if token in text)
        for intent, tokens in INTENT_KEYWORDS.items()
    }
    best_score = max(scores.values(), default=0)
    if best_score > 0:
        for intent in ("bug_triage", "feature_request", "status_update"):
            if scores.get(intent, 0) == best_score:
                return intent
    return "general_triage"


def extract_risk_hints(request_text: str) -> List[str]:
    text = request_text.lower()
    return [token for token in RISK_HINT_TOKENS if token in text]


def extract_intake(request_text: str) -> Dict[str, Any]:
    issue_keys = _ISSUE_KEY_REGEX.findall(request_text)
    deduped: List[str] = []
    seen: set[str] = set()
    for key in issue_keys:
        normalized = key.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    if not deduped:
        raise ValueError("Request must include a Jira issue key, e.g. JRASERVER-79286")
    return {
        "request_text": request_text,
        "candidate_issue_keys": deduped,
        "intent_hint": classify_intent(request_text),
        "risk_hints": extract_risk_hints(request_text),
    }
