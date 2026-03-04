from __future__ import annotations

from typing import Any, Dict

from ..stages.fetch_native_stage import handler as fetch_native_stage_handler


def execute_native_source(event: Dict[str, Any]) -> Dict[str, Any]:
    return fetch_native_stage_handler(event, None)
