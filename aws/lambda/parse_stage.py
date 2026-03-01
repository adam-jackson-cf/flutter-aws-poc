import time
from typing import Any, Dict

from intake_domain import extract_intake
from stage_metrics import append_stage_metric, base_event_with_metrics


def handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    started = time.time()
    payload = base_event_with_metrics(event)

    intake = extract_intake(payload["request_text"])
    payload["intake"] = intake
    payload["flow"] = payload.get("flow", "native")

    return append_stage_metric(payload, "parse_nlp", started, {"intent": intake["intent"]})
