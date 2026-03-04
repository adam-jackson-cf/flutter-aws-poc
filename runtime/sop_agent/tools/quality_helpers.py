from __future__ import annotations

from typing import Any, Dict


def safe_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return 0
    return 0


def parse_positive_int(value: str, *, error_code: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(error_code) from exc
    if parsed < 1:
        raise ValueError(error_code)
    return parsed


def merge_usage(base: Dict[str, int], additional: Dict[str, int]) -> Dict[str, int]:
    return {
        "input_tokens": max(0, safe_int(base.get("input_tokens", 0)) + safe_int(additional.get("input_tokens", 0))),
        "output_tokens": max(0, safe_int(base.get("output_tokens", 0)) + safe_int(additional.get("output_tokens", 0))),
        "total_tokens": max(0, safe_int(base.get("total_tokens", 0)) + safe_int(additional.get("total_tokens", 0))),
    }


def selection_llm_usage(source: Dict[str, Any], *, usage_key: str = "llm_usage") -> Dict[str, int]:
    usage = source.get(usage_key, {})
    if not isinstance(usage, dict):
        usage = {}
    return {
        "input_tokens": max(0, safe_int(usage.get("input_tokens", 0))),
        "output_tokens": max(0, safe_int(usage.get("output_tokens", 0))),
        "total_tokens": max(0, safe_int(usage.get("total_tokens", 0))),
    }


def extract_failure_reason(payload: Dict[str, Any], *, container: str, field: str = "failure_reason") -> str:
    nested = payload.get(container, {})
    if not isinstance(nested, dict):
        return ""
    return str(nested.get(field, "")).strip()
