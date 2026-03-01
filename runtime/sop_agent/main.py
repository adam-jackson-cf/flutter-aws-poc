import argparse
import json
from pathlib import Path
from typing import Any, Dict

from .config import DEFAULT_CONFIG
from .pipeline import SopPipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Flutter SOP pipeline")
    parser.add_argument("--flow", choices=["native", "mcp"], required=True)
    parser.add_argument("--request-text", default="")
    parser.add_argument("--input-file", default="")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def load_request_text(args: argparse.Namespace) -> str:
    if args.request_text:
        return args.request_text

    if args.input_file:
        payload = json.loads(Path(args.input_file).read_text(encoding="utf-8"))
        return str(payload["request_text"])

    raise ValueError("Provide --request-text or --input-file")


def run_from_cli() -> Dict[str, Any]:
    args = parse_args()
    request_text = load_request_text(args)

    pipeline = SopPipeline(config=DEFAULT_CONFIG)
    result = pipeline.run(request_text=request_text, flow=args.flow, dry_run=args.dry_run)

    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":  # pragma: no cover
    run_from_cli()
