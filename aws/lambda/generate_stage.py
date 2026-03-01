import time
from typing import Any, Dict

from response_generation import generate_customer_response
from runtime_config import selected_model_id, selected_region
from stage_metrics import append_stage_metric


def handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    started = time.time()
    model_id = selected_model_id(event)
    region = selected_region(event)

    response = generate_customer_response(
        intake=event["intake"],
        tool_result=event["tool_result"],
        model_id=model_id,
        region=region,
        dry_run=bool(event.get("dry_run", False)),
    )

    event["generated_response"] = response

    return append_stage_metric(
        event,
        "generate_response",
        started,
        {"risk_level": response["risk_level"], "tool_failure": bool(event.get("tool_failure", False))},
    )
