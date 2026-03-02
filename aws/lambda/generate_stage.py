import time
from typing import Any, Dict

from response_generation import (
    ResponseGenerationConfig,
    generate_customer_response_with_usage,
)
from runtime_config import selected_model_id, selected_model_provider, selected_provider_options, selected_region
from stage_metrics import append_stage_metric


def handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    started = time.time()
    model_id = selected_model_id(event)
    model_provider = selected_model_provider(event)
    provider_options = selected_provider_options(event)
    region = selected_region(event)

    response, llm_usage = generate_customer_response_with_usage(
        intake=event["intake"],
        tool_result=event["tool_result"],
        config=ResponseGenerationConfig(
            model_id=model_id,
            region=region,
            dry_run=bool(event.get("dry_run", False)),
            model_provider=model_provider,
            provider_options=provider_options,
        ),
    )

    event["generated_response"] = response
    event.setdefault("llm_usage", {})
    event["llm_usage"]["generate_response"] = llm_usage

    return append_stage_metric(
        event,
        "generate_response",
        started,
        {
            "risk_level": response["risk_level"],
            "tool_failure": bool(event.get("tool_failure", False)),
            "llm_input_tokens": int(llm_usage.get("input_tokens", 0)),
            "llm_output_tokens": int(llm_usage.get("output_tokens", 0)),
            "llm_total_tokens": int(llm_usage.get("total_tokens", 0)),
        },
    )
