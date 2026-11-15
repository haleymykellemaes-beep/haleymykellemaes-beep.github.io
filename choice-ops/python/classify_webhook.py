#!/usr/bin/env python3
"""Map a webhook or batch-reject code to an ops label.

Labels only. This script does not retry, refund, or edit a recipient.
A retry label still has to pass reprocess.py before anyone plans a send.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

import cases
import common

ACTIONS = (
    "retry",
    "do_not_retry",
    "fix_recipient_data",
    "wait_for_return_window",
    "escalate_to_engineering",
)

FIX_CODES = {"R02", "R03", "R04", "BATCH_REJECT"}
RETRY_CODES = {"91", "96"}


def classify(event: dict) -> str | None:
    """Return an ops label for terminal webhooks, batch rejects, and bad JSON."""
    if event.get("type") not in {"webhook", "batch.reject"} and not event.get("parse_error"):
        return None
    if event.get("parse_error"):
        return "escalate_to_engineering"
    code = (event.get("processor_code") or "").upper()
    status = (event.get("status") or "").lower()
    if code in FIX_CODES:
        return "fix_recipient_data"
    if common.is_return_code(code):
        return "wait_for_return_window"
    if code in RETRY_CODES:
        return "retry"
    if status in {"settled", "posted"}:
        return "do_not_retry"
    if code == "00" and status in {"submitted", "pending"}:
        return "do_not_retry"
    return "escalate_to_engineering"


def planted_actions() -> dict[str, str]:
    return {event["event_id"]: event["action"] for event in cases.EVENTS if event.get("action")}


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify webhook codes into ops labels.")
    parser.add_argument("--events", default=str(common.EVENTS_PATH), help="JSONL log to read.")
    parser.add_argument("--self-check", action="store_true", help="Always on for the seeded log.")
    args = parser.parse_args()
    path = Path(args.events)
    if not path.exists():
        print("Missing event log. From the portfolio folder run: python3 choice-ops/python/seed.py")
        return 1
    events = common.load_events(path)
    counts: Counter[str] = Counter()
    decided = []
    for event in sorted(events, key=lambda item: (item["at"], item["event_id"])):
        action = classify(event)
        if action is None:
            continue
        counts[action] += 1
        decided.append((event, action))
        code = event.get("processor_code") or "(none)"
        status = event.get("status") or "(none)"
        print(f"{event['event_id']:<16} {event['type']:<12} code {code:<12} status {status:<10} {action}")
    print()
    print("By action")
    for action in ACTIONS:
        print(f"  {action:<28} {counts[action]:>3}")
    print()
    print("Labels only. Nothing was sent, queued, or edited.")

    expected = planted_actions()
    by_id = {event["event_id"]: action for event, action in decided}
    problems = []
    for event_id, action in expected.items():
        actual = by_id.get(event_id)
        if actual != action:
            problems.append(f"{event_id} labeled {actual}; planted label is {action}")
    for action in ACTIONS:
        if counts[action] < 1:
            problems.append(f"No event received the label {action}")
    if problems:
        print("SELF-CHECK FAILED")
        for problem in problems:
            print(f"  {problem}")
        return 1
    print(f"SELF-CHECK OK. {len(expected)} planted webhook labels matched, including all 5 actions.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
