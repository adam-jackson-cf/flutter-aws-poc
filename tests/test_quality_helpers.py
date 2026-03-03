from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any, Dict


def _import_lambda_module(name: str) -> Any:
    lambda_path = Path(__file__).resolve().parents[1] / "aws" / "lambda"
    if str(lambda_path) not in sys.path:
        sys.path.insert(0, str(lambda_path))
    return importlib.import_module(name)


def test_quality_helpers_basic_branches() -> None:
    quality_helpers = _import_lambda_module("quality_helpers")

    assert quality_helpers.safe_int(True) == 1
    assert quality_helpers.safe_int("7") == 7
    assert quality_helpers.safe_int("bad") == 0
    assert quality_helpers.safe_int(None) == 0

    assert quality_helpers.parse_positive_int("3", error_code="bad_value") == 3
    with __import__("pytest").raises(ValueError, match="bad_value"):
        quality_helpers.parse_positive_int("0", error_code="bad_value")
    with __import__("pytest").raises(ValueError, match="bad_value"):
        quality_helpers.parse_positive_int("x", error_code="bad_value")


def test_quality_helpers_merge_and_accessors() -> None:
    quality_helpers = _import_lambda_module("quality_helpers")

    usage = quality_helpers.merge_usage(
        {"input_tokens": 2, "output_tokens": 1, "total_tokens": 3},
        {"input_tokens": 3, "output_tokens": -5, "total_tokens": 4},
    )
    assert usage == {"input_tokens": 5, "output_tokens": 0, "total_tokens": 7}

    assert quality_helpers.selection_llm_usage({}) == {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }
    assert quality_helpers.selection_llm_usage({"llm_usage": {"input_tokens": 5, "output_tokens": 4}}) == {
        "input_tokens": 5,
        "output_tokens": 4,
        "total_tokens": 0,
    }
    assert quality_helpers.selection_llm_usage({"llm_usage": "bad"}) == {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }

    assert quality_helpers.extract_failure_reason({"result": {"failure_reason": "  bad data  "}}, container="result") == "bad data"
    assert quality_helpers.extract_failure_reason({"result": "bad"}, container="result") == ""
    assert quality_helpers.extract_failure_reason({}, container="result") == ""
