import json
import os
from typing import Any, Dict
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .network_security import validate_endpoint_url


def read_json_from_url(url: str) -> Dict[str, Any]:
    req = Request(url, headers={"Accept": "application/json", "User-Agent": "flutter-agentcore-poc/1.0"})
    with urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _coerced_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return str(value or "")


def fetch_jira_issue(issue_key: str, jira_base_url: str) -> Dict[str, Any]:
    validate_endpoint_url(
        url=jira_base_url,
        env_var_name="JIRA_ALLOWED_HOSTS",
        default_allowed_hosts="jira.atlassian.com",
        env_getter=os.environ.get,
    )
    fields = "summary,description,status,issuetype,priority,labels,comment,updated"
    url = f"{jira_base_url}/rest/api/2/issue/{issue_key}?fields={fields}"
    try:
        payload = read_json_from_url(url)
    except HTTPError as exc:
        raise RuntimeError(f"jira_http_error:{exc.code}") from exc
    except URLError as exc:
        raise RuntimeError("jira_url_error") from exc

    issue_fields = payload.get("fields", {})
    priority = issue_fields.get("priority") or {}
    status = issue_fields.get("status") or {}
    issue_type = issue_fields.get("issuetype") or {}
    comments = issue_fields.get("comment") or {}

    description = _coerced_text(issue_fields.get("description"))
    summary = _coerced_text(issue_fields.get("summary"))

    return {
        "key": payload.get("key", issue_key),
        "summary": summary[:300],
        "status": status.get("name", "Unknown"),
        "issue_type": issue_type.get("name", "Unknown"),
        "priority": priority.get("name", "None"),
        "labels": (issue_fields.get("labels", []) or [])[:10],
        "updated": issue_fields.get("updated", ""),
        "description": description[:600],
        "comment_count": comments.get("total", 0),
    }
