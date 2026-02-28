import json
from pathlib import Path


REQUIRED_KEYS = {
    "case_id",
    "request_text",
    "expected_intent",
    "expected_issue_key",
    "expected_response_anchor",
    "expected_tool",
}


def test_dataset_schema() -> None:
    dataset_path = Path("evals/golden/sop_cases.jsonl")
    lines = [line.strip() for line in dataset_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) >= 8

    for line in lines:
        item = json.loads(line)
        assert REQUIRED_KEYS.issubset(item.keys())
        assert isinstance(item["expected_tool"], dict)
        assert {"native", "mcp"}.issubset(item["expected_tool"].keys())
        assert isinstance(item["expected_tool"]["native"], str)
        assert isinstance(item["expected_tool"]["mcp"], str)
