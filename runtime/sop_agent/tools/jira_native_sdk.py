import hashlib
from typing import Any, Dict

from jira import JIRA


class JiraSdkClient:
    def __init__(self, base_url: str) -> None:
        self._base_url = base_url
        self._client = JIRA(server=base_url, options={"verify": True})

    def get_issue(self, issue_key: str) -> Dict[str, Any]:
        issue = self._client.issue(
            issue_key,
            fields="summary,description,status,issuetype,priority,labels,comment,updated",
        )

        fields = issue.raw.get("fields", {})
        status = fields.get("status") or {}
        issue_type = fields.get("issuetype") or {}
        priority = fields.get("priority") or {}
        comments = fields.get("comment") or {}

        description = fields.get("description") or ""
        if not isinstance(description, str):
            description = str(description)

        summary = fields.get("summary", "")
        if not isinstance(summary, str):
            summary = str(summary)

        return {
            "key": issue.key,
            "summary": summary[:300],
            "status": status.get("name", "Unknown"),
            "issue_type": issue_type.get("name", "Unknown"),
            "priority": priority.get("name", "None"),
            "labels": (fields.get("labels", []) or [])[:10],
            "updated": fields.get("updated", ""),
            "description": description[:600],
            "comment_count": comments.get("total", 0),
        }

    def write_issue_followup_note(self, issue_key: str, note_text: str) -> Dict[str, Any]:
        issue = self._client.issue(issue_key, fields="summary")
        text = note_text.strip()
        if not text:
            raise ValueError("note_text_missing")
        comment = self._client.add_comment(issue, text)
        comment_id = str(getattr(comment, "id", "")).strip()
        if not comment_id:
            raise ValueError("comment_id_missing")
        issue_key_safe = str(issue.key).strip()
        artifact_uri = (
            f"{self._base_url.rstrip('/')}/browse/{issue_key_safe}?focusedCommentId={comment_id}"
        )
        return {
            "key": issue.key,
            "write_status": "committed",
            "note_digest": hashlib.sha256(text.encode("utf-8")).hexdigest()[:12],
            "comment_id": comment_id,
            "write_artifact_uri": artifact_uri,
        }
