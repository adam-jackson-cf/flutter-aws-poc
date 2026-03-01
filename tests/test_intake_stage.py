import pytest

from runtime.sop_agent.stages.intake_stage import IntakeError, classify_intent, extract_risk_hints, run_intake


@pytest.mark.parametrize(
    ("request_text", "expected_intent"),
    [
        ("Customer reports bug and outage", "bug_triage"),
        ("Need feature improvement for roadmap", "feature_request"),
        ("Please provide latest status update", "status_update"),
        ("General question with no specific signal", "general_triage"),
    ],
)
def test_classify_intent(request_text: str, expected_intent: str) -> None:
    assert classify_intent(request_text) == expected_intent


def test_run_intake_extracts_key() -> None:
    intake = run_intake("Please triage JRASERVER-79286 and provide status")
    assert intake["issue_key"] == "JRASERVER-79286"
    assert intake["intent"] == "status_update"


def test_run_intake_requires_issue_key() -> None:
    with pytest.raises(IntakeError):
        run_intake("No issue key present in this request")


def test_extract_risk_hints() -> None:
    hints = extract_risk_hints("JRASERVER-1 security escalation for a customer")
    assert hints == ["security", "customer", "escalation"]
