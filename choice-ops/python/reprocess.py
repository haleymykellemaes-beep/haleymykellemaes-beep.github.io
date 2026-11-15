#!/usr/bin/env python3
"""Decide which failed disbursements are safe to plan for reprocess.

Dry-run is the default. --execute inserts a row into reprocess_queue only.
It does not insert a disbursement and it does not call a processor.

A row is safe only when all of these hold:
  status is failed, or pending older than the window in settings
  no settled/posted row already has this idempotency key
  no return is on the row or in the log
  no webhook already says settled
  every log amount matches the ledger amount
  the trace number is not already on another disbursement
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict

import cases
import common

FIX_RECIPIENT_CODES = {"R02", "R03", "R04"}


def events_for(events: list[dict], disbursement_id: str) -> list[dict]:
    return [event for event in events if event["disbursement_id"] == disbursement_id]


def return_code(row, log_events) -> str | None:
    if common.is_return_code(row["processor_code"]):
        return row["processor_code"]
    for event in log_events:
        if common.is_return_code(event.get("processor_code")):
            return event["processor_code"]
    return None


def settled_webhook(log_events) -> bool:
    return any(
        event.get("type") == "webhook" and event.get("status") in common.TERMINAL_OK
        for event in log_events
    )


def amount_changed(row, log_events) -> bool:
    for event in log_events:
        amount = event.get("amount_cents")
        if amount is not None and amount != row["amount_cents"]:
            return True
    return False


def decision(row, log_events, key_rows, trace_rows, cutoff: str) -> str:
    others_key = [item for item in key_rows if item["disbursement_id"] != row["disbursement_id"]]
    if any(item["status"] in common.TERMINAL_OK for item in others_key):
        return "idempotency_already_settled"
    others_trace = [item for item in trace_rows if item["disbursement_id"] != row["disbursement_id"]]
    if row["trace_number"] and others_trace:
        return "duplicate_trace"
    code = return_code(row, log_events)
    if row["status"] == "returned" or any(common.is_return_event(event) for event in log_events):
        if code in FIX_RECIPIENT_CODES:
            return "fix_recipient_data"
        return "return_already_received"
    if settled_webhook(log_events) and row["status"] not in common.TERMINAL_OK:
        return "webhook_already_settled"
    if amount_changed(row, log_events):
        return "amount_changed"
    if row["status"] == "rejected":
        return "fix_before_retry"
    if row["status"] == "pending":
        if row["updated_at"] > cutoff:
            return "pending_inside_window"
        return "safe"
    if row["status"] == "submitted":
        return "still_in_flight"
    if row["status"] == "failed":
        return "safe"
    return "status_not_retriable"


def plan_reason(row) -> str:
    if row["status"] == "pending":
        return "stale_pending"
    if row["processor_code"]:
        return f"processor_{row['processor_code']}"
    return "failed_no_conflict"


def index_rows(conn, queries):
    rows = conn.execute(
        """
        SELECT disbursement_id, client_id, recipient_id, method, amount_cents,
               status, idempotency_key, trace_number, processor_code,
               created_at, updated_at
        FROM disbursements
        ORDER BY disbursement_id
        """
    ).fetchall()
    by_key = defaultdict(list)
    by_trace = defaultdict(list)
    for row in rows:
        by_key[row["idempotency_key"]].append(row)
        if row["trace_number"]:
            by_trace[row["trace_number"]].append(row)
    return rows, by_key, by_trace


def evaluate_all(conn, queries, events, cutoff: str):
    rows, by_key, by_trace = index_rows(conn, queries)
    evaluated = []
    for row in rows:
        if row["status"] not in common.CANDIDATE_STATUSES:
            continue
        log_events = events_for(events, row["disbursement_id"])
        reason = decision(
            row,
            log_events,
            by_key[row["idempotency_key"]],
            by_trace.get(row["trace_number"], []),
            cutoff,
        )
        evaluated.append((row, reason))
    return evaluated


def still_safe(conn, row) -> str | None:
    settled = conn.execute(
        """
        SELECT disbursement_id FROM disbursements
        WHERE idempotency_key = ?
          AND status IN ('settled', 'posted')
          AND disbursement_id <> ?
        """,
        (row["idempotency_key"], row["disbursement_id"]),
    ).fetchone()
    if settled:
        return f"{row['disbursement_id']} shares a settled idempotency key with {settled['disbursement_id']}"
    current = conn.execute(
        "SELECT status, amount_cents FROM disbursements WHERE disbursement_id = ?",
        (row["disbursement_id"],),
    ).fetchone()
    if current is None:
        return f"{row['disbursement_id']} disappeared"
    if current["status"] in common.TERMINAL_OK:
        return f"{row['disbursement_id']} is already {current['status']}"
    if current["amount_cents"] != row["amount_cents"]:
        return f"{row['disbursement_id']} amount changed before the plan was written"
    return None


def write_plans(conn, safe_rows, planned_at: str) -> tuple[int, int]:
    before = {
        row["disbursement_id"]
        for row in conn.execute("SELECT disbursement_id FROM reprocess_queue")
    }
    live_before = conn.execute("SELECT COUNT(*) AS n FROM disbursements").fetchone()["n"]
    for row, _reason in safe_rows:
        refusal = still_safe(conn, row)
        if refusal:
            raise SystemExit(f"Refusing to plan. {refusal}")
        conn.execute(
            """
            INSERT INTO reprocess_queue (
              disbursement_id, idempotency_key, amount_cents, plan_reason, planned_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(disbursement_id) DO NOTHING
            """,
            (
                row["disbursement_id"],
                row["idempotency_key"],
                row["amount_cents"],
                plan_reason(row),
                planned_at,
            ),
        )
    conn.commit()
    live_after = conn.execute("SELECT COUNT(*) AS n FROM disbursements").fetchone()["n"]
    if live_after != live_before:
        raise SystemExit("Stopped. disbursements changed size. That must not happen.")
    after = {
        row["disbursement_id"]
        for row in conn.execute("SELECT disbursement_id FROM reprocess_queue")
    }
    return len(after - before), len(before & {row["disbursement_id"] for row, _reason in safe_rows})


def self_check(evaluated) -> list[str]:
    found = {row["disbursement_id"]: reason for row, reason in evaluated}
    problems = []
    if set(found) != set(cases.REPROCESS_EXPECT):
        missing = set(cases.REPROCESS_EXPECT) - set(found)
        extra = set(found) - set(cases.REPROCESS_EXPECT)
        if missing:
            problems.append("Missing from the scan: " + ", ".join(sorted(missing)))
        if extra:
            problems.append("Unexpected candidates: " + ", ".join(sorted(extra)))
    for disbursement_id, expected in cases.REPROCESS_EXPECT.items():
        actual = found.get(disbursement_id)
        if actual is not None and actual != expected:
            problems.append(f"{disbursement_id} is {actual}; planted decision is {expected}")
    return problems


def print_report(evaluated, *, execute: bool, inserted: int, already: int, as_of: str, window: int) -> None:
    safe = [(row, reason) for row, reason in evaluated if reason == "safe"]
    blocked = [(row, reason) for row, reason in evaluated if reason != "safe"]
    safe_cents = sum(row["amount_cents"] for row, _reason in safe)
    blocked_cents = sum(row["amount_cents"] for row, _reason in blocked)
    mode = "execute" if execute else "dry run"
    print(f"As of {as_of}. Pending window {window}h. Mode: {mode}.")
    print(f"Safe to plan:  {len(safe):>3}   {common.money(safe_cents)}")
    print(f"Blocked:       {len(blocked):>3}   {common.money(blocked_cents)}")
    print()
    print("Safe")
    if not safe:
        print("  (none)")
    for row, _reason in safe:
        print(
            f"  {row['disbursement_id']}  {row['method']:<8} {row['status']:<8} "
            f"{common.money(row['amount_cents']):>10}  {plan_reason(row)}"
        )
    print()
    print("Blocked")
    grouped = defaultdict(list)
    for row, reason in blocked:
        grouped[reason].append(row)
    for reason in sorted(grouped):
        rows = grouped[reason]
        cents = sum(row["amount_cents"] for row in rows)
        print(f"  {reason:<32} {len(rows):>3}   {common.money(cents):>10}")
        for row in rows:
            print(f"      {row['disbursement_id']}  {row['method']:<8} {row['status']:<10} {common.money(row['amount_cents'])}")
    print()
    if execute:
        print(f"Plan rows inserted: {inserted}. Already queued: {already}.")
        print("disbursements row count unchanged. No second live payment was created.")
    else:
        print("Dry run. reprocess_queue was not written. No disbursement was inserted.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan safe disbursement reprocessing. Dry-run by default.")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Insert safe rows into reprocess_queue. Does not create a disbursement.",
    )
    parser.add_argument(
        "--self-check",
        action="store_true",
        help="Accepted for symmetry. The scan always checks the planted safe and blocked sets.",
    )
    args = parser.parse_args()
    if not common.DB_PATH.exists() or not common.EVENTS_PATH.exists():
        print("Missing seeded files. From the portfolio folder run: python3 choice-ops/python/seed.py")
        return 1
    _schema, queries = common.load_sql()
    events = common.load_events()
    conn = common.connect()
    try:
        settings = common.settings_row(conn)
        cutoff = common.hours_before(settings["as_of"], settings["pending_window_hours"])
        queue_before = conn.execute("SELECT COUNT(*) AS n FROM reprocess_queue").fetchone()["n"]
        live_before = conn.execute("SELECT COUNT(*) AS n FROM disbursements").fetchone()["n"]
        evaluated = evaluate_all(conn, queries, events, cutoff)
        inserted = 0
        already = 0
        if args.execute:
            safe_rows = [(row, reason) for row, reason in evaluated if reason == "safe"]
            inserted, already = write_plans(conn, safe_rows, settings["as_of"])
        queue_after = conn.execute("SELECT COUNT(*) AS n FROM reprocess_queue").fetchone()["n"]
        live_after = conn.execute("SELECT COUNT(*) AS n FROM disbursements").fetchone()["n"]
        print_report(
            evaluated,
            execute=args.execute,
            inserted=inserted,
            already=already,
            as_of=settings["as_of"],
            window=settings["pending_window_hours"],
        )
        problems = self_check(evaluated)
        if live_after != live_before:
            problems.append("disbursements changed size during reprocess")
        if not args.execute and queue_after != queue_before:
            problems.append("dry run wrote reprocess_queue")
        if args.execute:
            queued = {
                row["disbursement_id"]
                for row in conn.execute("SELECT disbursement_id FROM reprocess_queue")
            }
            expected_safe = {key for key, reason in cases.REPROCESS_EXPECT.items() if reason == "safe"}
            if queued != expected_safe:
                problems.append(
                    f"queue has {sorted(queued)}; safe set is {sorted(expected_safe)}"
                )
        if problems:
            print("SELF-CHECK FAILED")
            for problem in problems:
                print(f"  {problem}")
            return 1
        print("SELF-CHECK OK. Safe and blocked sets match the planted cases.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
