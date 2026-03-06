#!/usr/bin/env python3
"""Validate Flutter design waiver records and fail on expired entries."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_WAIVERS_PATH = REPO_ROOT / "scripts" / "linters" / "flutter-design" / "waivers.json"
REQUIRED_FIELDS = ("rule_id", "owner", "reason", "issue", "expires_on")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate Flutter design waiver records.")
    parser.add_argument(
        "--waivers",
        default=str(DEFAULT_WAIVERS_PATH),
        help="Path to waiver JSON file.",
    )
    parser.add_argument(
        "--output",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    return parser.parse_args()


def load_waivers(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        raise FileNotFoundError(f"waiver file not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("waiver file must contain a JSON object")
    waivers = payload.get("waivers", [])
    if not isinstance(waivers, list):
        raise ValueError("waiver file 'waivers' field must be an array")
    validated: list[dict[str, object]] = []
    for entry in waivers:
        if not isinstance(entry, dict):
            raise ValueError("each waiver entry must be an object")
        missing = [field for field in REQUIRED_FIELDS if not str(entry.get(field, "")).strip()]
        if missing:
            raise ValueError(f"waiver entry missing required fields: {missing}")
        validated.append(entry)
    return validated


def parse_expiry(raw_value: str) -> dt.date:
    try:
        return dt.date.fromisoformat(raw_value)
    except ValueError as exc:
        raise ValueError(f"invalid expires_on value '{raw_value}' (expected YYYY-MM-DD)") from exc


def evaluate_waivers(waivers: list[dict[str, object]]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    today = dt.date.today()
    active: list[dict[str, str]] = []
    expired: list[dict[str, str]] = []

    for waiver in waivers:
        record = {
            "rule_id": str(waiver["rule_id"]),
            "owner": str(waiver["owner"]),
            "issue": str(waiver["issue"]),
            "expires_on": str(waiver["expires_on"]),
            "reason": str(waiver["reason"]),
        }
        expiry = parse_expiry(record["expires_on"])
        if expiry < today:
            expired.append(record)
        else:
            active.append(record)

    return active, expired


def print_text(*, active: list[dict[str, str]], expired: list[dict[str, str]]) -> None:
    if expired:
        print("Flutter design waiver violations detected (expired entries):")
        for waiver in expired:
            print(
                f"- {waiver['rule_id']} owner={waiver['owner']} issue={waiver['issue']} expires_on={waiver['expires_on']}"
            )
    else:
        print("Flutter design waivers are valid (no expired entries).")

    print(f"Active waivers: {len(active)}")
    print(f"Expired waivers: {len(expired)}")


def print_json(*, active: list[dict[str, str]], expired: list[dict[str, str]]) -> None:
    payload = {
        "active": active,
        "expired": expired,
        "summary": {
            "active": len(active),
            "expired": len(expired),
        },
    }
    print(json.dumps(payload, indent=2, sort_keys=True))


def main() -> int:
    args = parse_args()
    waivers = load_waivers(Path(args.waivers).resolve())
    active, expired = evaluate_waivers(waivers)

    if args.output == "json":
        print_json(active=active, expired=expired)
    else:
        print_text(active=active, expired=expired)

    return 1 if expired else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(2)
