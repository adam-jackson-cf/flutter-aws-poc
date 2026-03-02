import re
from typing import Any, Dict, List

from contract_values import INTENT_KEYWORDS, RISK_HINT_TOKENS

ISSUE_KEY_PATTERN = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")


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
    return [token for token in RISK_HINT_TOKENS if token in request_text.lower()]


def _dedupe_preserving_order(values: List[str]) -> List[str]:
    seen: set[str] = set()
    output: List[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        output.append(normalized)
    return output


def extract_intake(request_text: str) -> Dict[str, Any]:
    issue_keys = _dedupe_preserving_order(ISSUE_KEY_PATTERN.findall(request_text))
    if not issue_keys:
        raise ValueError("No issue key found in request_text. Include a Jira key like JRASERVER-79286.")
    return {
        "request_text": request_text,
        "candidate_issue_keys": issue_keys,
        "intent_hint": classify_intent(request_text),
        "risk_hints": extract_risk_hints(request_text),
    }
