import importlib
import sys
from pathlib import Path
from typing import Any, Dict

import pytest


def _import_lambda_module(name: str) -> Any:
    lambda_path = Path(__file__).resolve().parents[1] / "aws" / "lambda"
    if str(lambda_path) not in sys.path:
        sys.path.insert(0, str(lambda_path))
    return importlib.import_module(name)


def test_jira_tool_target_helpers() -> None:
    jira_tool_target = _import_lambda_module("jira_tool_target")
    assert jira_tool_target._strip_target_prefix("x__jira_get_issue_by_key") == "jira_get_issue_by_key"
    assert jira_tool_target._strip_target_prefix("jira_get_issue_by_key") == "jira_get_issue_by_key"

    assert jira_tool_target._extract_tool_name({"toolName": "jira_get_issue_labels"}) == "jira_get_issue_labels"
    assert jira_tool_target._extract_tool_name({"params": {"name": "x__jira_get_issue_by_key"}}) == "jira_get_issue_by_key"
    assert jira_tool_target._extract_tool_name({}) == "jira_get_issue_by_key"

    assert jira_tool_target._extract_issue_key({"arguments": {"issue_key": "JRASERVER-1"}}) == "JRASERVER-1"
    assert jira_tool_target._extract_issue_key({"params": {"arguments": {"issue_key": "JRASERVER-2"}}}) == "JRASERVER-2"
    assert jira_tool_target._extract_issue_key({"arguments": '{"issue_key":"JRASERVER-3"}'}) == "JRASERVER-3"
    assert jira_tool_target._extract_issue_key({"issue_key": "JRASERVER-4"}) == "JRASERVER-4"
    assert jira_tool_target._extract_issue_key({"input": {"issue_key": "JRASERVER-5"}}) == "JRASERVER-5"
    with pytest.raises(ValueError):
        jira_tool_target._extract_issue_key({})

    assert jira_tool_target._derive_sentiment({"summary": "bug outage", "description": ""}) == "negative"
    assert jira_tool_target._derive_sentiment({"summary": "resolved", "description": ""}) == "positive"
    assert jira_tool_target._derive_sentiment({"summary": "plain", "description": ""}) == "neutral"


def test_jira_tool_target_result_variants() -> None:
    jira_tool_target = _import_lambda_module("jira_tool_target")
    issue = {
        "key": "JRASERVER-1",
        "status": "Done",
        "updated": "today",
        "priority": "High",
        "labels": ["security", "esc-risk"],
        "summary": "Fixed",
        "description": "all good",
    }
    assert jira_tool_target._build_tool_result("jira_get_issue_by_key", issue)["key"] == "JRASERVER-1"
    assert jira_tool_target._build_tool_result("jira_get_issue_status_snapshot", issue)["status"] == "Done"
    assert jira_tool_target._build_tool_result("jira_get_issue_priority_context", issue)["risk_band"] == "high"
    assert jira_tool_target._build_tool_result("jira_get_issue_labels", issue)["labels"] == ["security", "esc-risk"]
    assert jira_tool_target._build_tool_result("jira_get_issue_project_key", issue)["project_key"] == "JRASERVER"
    assert jira_tool_target._build_tool_result("jira_get_issue_update_timestamp", issue)["updated"] == "today"
    assert jira_tool_target._build_tool_result("jira_get_issue_risk_flags", issue)["risk_flags"] == ["security", "esc-risk"]
    assert jira_tool_target._build_tool_result("jira_get_customer_sentiment", issue)["sentiment"] == "positive"
    assert "seed_message" in jira_tool_target._build_tool_result("jira_get_issue_customer_message_seed", issue)
    assert jira_tool_target._build_tool_result("unsupported", issue)["error"].startswith("unsupported_tool")


def test_jira_tool_target_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    jira_tool_target = _import_lambda_module("jira_tool_target")
    monkeypatch.setattr(
        jira_tool_target,
        "fetch_jira_issue",
        lambda issue_key, jira_base_url: {
            "key": issue_key,
            "status": "Done",
            "updated": "now",
            "priority": "Low",
            "labels": [],
            "summary": "ok",
            "description": "",
        },
    )
    event = {"name": "x__jira_get_issue_status_snapshot", "arguments": {"issue_key": "JRASERVER-9"}}
    out = jira_tool_target.handler(event, None)
    assert out["tool"] == "jira_get_issue_status_snapshot"
    assert out["result"]["key"] == "JRASERVER-9"
