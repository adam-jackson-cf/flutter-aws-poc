import time
from datetime import datetime, timezone
from typing import Any, Dict


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def base_event_with_metrics(event: Dict[str, Any]) -> Dict[str, Any]:
    enriched = dict(event)
    enriched.setdefault("metrics", {})
    enriched["metrics"].setdefault("stages", [])
    enriched["started_at"] = enriched.get("started_at") or utc_now()
    return enriched


def append_stage_metric(event: Dict[str, Any], stage: str, started: float, extra: Dict[str, Any]) -> Dict[str, Any]:
    elapsed_ms = round((time.time() - started) * 1000, 2)
    event["metrics"]["stages"].append({"stage": stage, "latency_ms": elapsed_ms, **extra})
    event["metrics"][f"{stage}_latency_ms"] = elapsed_ms
    return event
