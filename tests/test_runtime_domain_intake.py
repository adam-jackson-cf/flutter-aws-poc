import pytest

from runtime.sop_agent.domain import intake as runtime_intake


def test_extract_intake_deduplicates_issue_keys() -> None:
    request = "Investigate JRASERVER-1234 and also JRASERVER-1234 again"
    payload = runtime_intake.extract_intake(request)

    assert payload["candidate_issue_keys"] == ["JRASERVER-1234"]


def test_extract_intake_rejects_missing_issue_key() -> None:
    with pytest.raises(ValueError, match="Request must include a Jira issue key"):
        runtime_intake.extract_intake("No Jira issue in this text")

