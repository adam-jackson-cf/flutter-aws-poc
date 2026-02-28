import re
from typing import Any, Dict, List

ISSUE_KEY_PATTERN = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")


class IntakeError(ValueError):
    pass


def classify_intent(request_text: str) -> str:
    text = request_text.lower()
    if any(token in text for token in ["bug", "incident", "error", "outage", "failure", "broken"]):
        return "bug_triage"
    if any(token in text for token in ["feature", "suggestion", "roadmap", "improvement"]):
        return "feature_request"
    if any(token in text for token in ["status", "progress", "update", "latest"]):
        return "status_update"
    return "general_triage"


def extract_risk_hints(request_text: str) -> List[str]:
    text = request_text.lower()
    tokens = ["accessibility", "security", "compliance", "customer", "incident", "escalation"]
    return [token for token in tokens if token in text]


def run_intake(request_text: str) -> Dict[str, Any]:
    issue_keys = ISSUE_KEY_PATTERN.findall(request_text)
    if not issue_keys:
        raise IntakeError("Request must include a Jira issue key, e.g. JRASERVER-79286")

    return {
        "request_text": request_text,
        "issue_key": issue_keys[0],
        "intent": classify_intent(request_text),
        "risk_hints": extract_risk_hints(request_text),
    }
