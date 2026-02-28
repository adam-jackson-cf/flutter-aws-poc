import pytest

from runtime.sop_agent.stages.intake_stage import IntakeError, classify_intent, run_intake


def test_classify_intent_bug() -> None:
    assert classify_intent("Customer reports bug and outage") == "bug_triage"


def test_classify_intent_feature() -> None:
    assert classify_intent("Need feature improvement for roadmap") == "feature_request"


def test_run_intake_extracts_key() -> None:
    intake = run_intake("Please triage JRASERVER-79286 and provide status")
    assert intake["issue_key"] == "JRASERVER-79286"
    assert intake["intent"] == "status_update"


def test_run_intake_requires_issue_key() -> None:
    with pytest.raises(IntakeError):
        run_intake("No issue key present in this request")
