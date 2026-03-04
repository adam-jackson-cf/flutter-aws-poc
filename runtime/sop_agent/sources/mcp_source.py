from __future__ import annotations

from typing import Any, Dict

from ..stages.fetch_mcp_stage import handler as fetch_mcp_stage_handler


def execute_mcp_source(event: Dict[str, Any]) -> Dict[str, Any]:
    return fetch_mcp_stage_handler(event, None)
