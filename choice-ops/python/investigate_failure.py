#!/usr/bin/env python3
"""Root-cause timeline for one outbound disbursement.

Reads the JSONL API/webhook log and the SQLite ledger. Prints the mismatch.
With no id, checks every planted failure and exits non-zero if one is missed
or mislabeled. Does not retry a payment.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict

import cases
import common

CAUSE_TEXT = cases.CAUSE_TEXT


def events_for(events: list[dict], disbursement_id: str) -> list[dict]:
    rows = [event for event in events if event["disbursement_id"] == disbursement_id]
    return sorted(rows, key=lambda event: (event["at"], event["event_id"]))


def diagnose(row, events, key_rows, trace_rows) -> str:
    others_trace = [item for item in trace_rows if item["disbursement_id"] != row["disbursement_id"]]
    if row["trace_number"] and others_trace:
        return "duplicate_trace"
    if len(key_rows) > 1 and any(item["status"] in common.TERMINAL_OK for item in key_rows):
        return "idempotency_already_settled"
    amounts = [event["amount_cents"] for event in events if event.get("amount_cents") is not None]
    if any(amount != row["amount_cents"] for amount in amounts):
        return "amount_mismatch"
    returns = [event for event in events if common.is_return_event(event)]
    if returns and row["status"] != "returned":
        return "return_in_flight"
    code = row["processor_code"]
    if code is None and returns:
        code = returns[-1].get("processor_code")
    if code == "R01":
        return "ach_r01"
    if code == "R03":
        return "ach_r03"
    if row["status"] == "rejected" or any(
        event.get("type") == "batch.reject" or event.get("processor_code") == "BATCH_REJECT"
        for event in events
    ):
        return "batch_rejected"
    webhook_settled = any(
        event.get("type") == "webhook" and event.get("status") in common.TERMINAL_OK
        for event in events
    )
    if webhook_settled and row["status"] not in common.TERMINAL_OK:
        return "status_mismatch"
    if row["status"] == "failed" and (
        row["processor_code"] in ("91", "96")
        or any(event.get("processor_code") in ("91", "96") for event in events)
    ):
        return "retryable_failure"
    if row["status"] == "pending":
        return "pending"
    if row["status"] in common.TERMINAL_OK:
        return "settled_ok"
    if row["status"] == "submitted":
        return "submitted_ok"
    return "unclassified"


def load_bundle(conn, queries, events, disbursement_id):
    row = conn.execute(queries["by_id"], {"disbursement_id": disbursement_id}).fetchone()
    if row is None:
        return None
    key_rows = conn.execute(
        queries["same_idempotency"], {"idempotency_key": row["idempotency_key"]}
    ).fetchall()
    if row["trace_number"]:
        trace_rows = conn.execute(
            queries["same_trace"], {"trace_number": row["trace_number"]}
        ).fetchall()
    else:
        trace_rows = []
    return row, events_for(events, disbursement_id), key_rows, trace_rows


def print_case(row, log_events, key_rows, trace_rows, cause: str) -> None:
    code = row["processor_code"] or "(none)"
    print(f"{row['disbursement_id']}  {row['client_name']}")
    print(f"  Recipient    {row['recipient_id']} ({row['recipient_label']})")
    print(f"  Method       {row['method']}    {common.money(row['amount_cents'])}    ledger status {row['status']}")
    print(f"  Idempotency  {row['idempotency_key']}")
    print(f"  Trace        {row['trace_number'] or '(none)'}    processor code {code}")
    print("  Log          choice-ops/data/events.jsonl")
    if not log_events:
        print("    (no API or webhook lines for this id)")
    for event in log_events:
        http = event["http_status"] if event["http_status"] is not None else "-"
        processor = event["processor_code"] or "(none)"
        status = event["status"] or "(none)"
        amount = common.money(event["amount_cents"]) if event.get("amount_cents") is not None else "(none)"
        kind = event["type"]
        name = event["event"] or ""
        print(f"    {event['at']}  {kind} {name}  HTTP {http}  code {processor}  status {status}  {amount}")
        if event.get("message"):
            print(f"        {event['message']}")
    print(f"  Ledger       status {row['status']}  updated {row['updated_at']}  code {code}")
    if len(key_rows) > 1:
        others = ", ".join(
            f"{item['disbursement_id']} {item['status']} {common.money(item['amount_cents'])}"
            for item in key_rows
        )
        print(f"  Same key     {others}")
    if len(trace_rows) > 1:
        others = ", ".join(
            f"{item['disbursement_id']} {item['status']} {common.money(item['amount_cents'])}"
            for item in trace_rows
        )
        print(f"  Same trace   {others}")
    print(f"  Root cause   {cause}")
    print(f"  {CAUSE_TEXT.get(cause, 'No planted explanation for this cause.')}")
    print()


def sql_id_set(conn, sql: str, column: str) -> set[str]:
    return {row[column] for row in conn.execute(sql)}


def check_sql(conn, queries) -> list[str]:
    problems = []
    checks = [
        ("webhook_settled_row_not_settled", "disbursement_id"),
        ("amount_mismatches", "disbursement_id"),
        ("duplicate_traces", "trace_number"),
        ("duplicate_idempotency_keys", "idempotency_key"),
    ]
    for name, column in checks:
        found = sql_id_set(conn, queries[name], column)
        expected = cases.SQL_EXPECT[name]
        if found != expected:
            problems.append(
                f"SQL {name} found {sorted(found) or '(none)'}; expected {sorted(expected)}"
            )
    return problems


def check_log_table(conn, queries, events) -> list[str]:
    problems = []
    db_ids = {row["event_id"] for row in conn.execute("SELECT event_id FROM api_events")}
    file_ids = {event["event_id"] for event in events}
    if db_ids != file_ids:
        problems.append("JSONL event ids and api_events differ. Run seed.py again.")
    for disbursement_id in cases.INVESTIGATE_EXPECT:
        file_order = [event["event_id"] for event in events_for(events, disbursement_id)]
        db_order = [
            row["event_id"]
            for row in conn.execute(queries["events_for_id"], {"disbursement_id": disbursement_id})
        ]
        if file_order != db_order:
            problems.append(f"Log and api_events order differ for {disbursement_id}")
    return problems


def run_planted(conn, queries, events) -> int:
    grouped: dict[str, list] = defaultdict(list)
    problems = []
    printed = []
    for disbursement_id, expected in cases.INVESTIGATE_EXPECT.items():
        bundle = load_bundle(conn, queries, events, disbursement_id)
        if bundle is None:
            problems.append(f"{disbursement_id} is missing from the ledger")
            continue
        row, log_events, key_rows, trace_rows = bundle
        cause = diagnose(row, log_events, key_rows, trace_rows)
        grouped[cause].append(row)
        printed.append((row, log_events, key_rows, trace_rows, cause))
        if cause != expected:
            problems.append(f"{disbursement_id} diagnosed {cause}; planted cause is {expected}")

    print(f"As of {cases.AS_OF}. Planted failure check.")
    print(f"{'failure type':<32} {'rows':>5}  {'dollars':>12}")
    involved_rows = 0
    involved_cents = 0
    seen = set(grouped)
    for cause in cases.CAUSE_ORDER:
        rows = grouped.get(cause, [])
        cents = sum(row["amount_cents"] for row in rows)
        involved_rows += len(rows)
        involved_cents += cents
        print(f"{cause:<32} {len(rows):>5}  {common.money(cents):>12}")
        seen.discard(cause)
    for cause in sorted(seen):
        rows = grouped[cause]
        cents = sum(row["amount_cents"] for row in rows)
        print(f"{cause:<32} {len(rows):>5}  {common.money(cents):>12}  (not a planted type)")
    print(f"{'involved':<32} {involved_rows:>5}  {common.money(involved_cents):>12}")
    print()
    for row, log_events, key_rows, trace_rows, cause in printed:
        print_case(row, log_events, key_rows, trace_rows, cause)

    problems.extend(check_sql(conn, queries))
    problems.extend(check_log_table(conn, queries, events))
    missing_types = [cause for cause in cases.CAUSE_ORDER if cause not in grouped]
    if missing_types:
        problems.append("Missed planted types: " + ", ".join(missing_types))
    if problems:
        print("SELF-CHECK FAILED")
        for problem in problems:
            print(f"  {problem}")
        return 1
    print(f"SELF-CHECK OK. {len(cases.CAUSE_ORDER)} planted causes found on {len(cases.INVESTIGATE_EXPECT)} rows.")
    return 0


def run_one(conn, queries, events, disbursement_id: str) -> int:
    bundle = load_bundle(conn, queries, events, disbursement_id)
    if bundle is None:
        print(f"No disbursement {disbursement_id}. Run seed.py, then use an id such as DSP-7001.")
        return 1
    row, log_events, key_rows, trace_rows = bundle
    cause = diagnose(row, log_events, key_rows, trace_rows)
    print_case(row, log_events, key_rows, trace_rows, cause)
    expected = cases.INVESTIGATE_EXPECT.get(disbursement_id)
    if expected is None:
        print("This id is not one of the planted failures.")
        return 0
    if cause != expected:
        print(f"SELF-CHECK FAILED. Diagnosed {cause}; planted cause is {expected}.")
        return 1
    print(f"Planted case confirmed: {cause}.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Print a disbursement root-cause timeline.")
    parser.add_argument("disbursement_id", nargs="?", help="Example: DSP-7001")
    parser.add_argument(
        "--self-check",
        action="store_true",
        help="Check every planted failure. This is also the default when no id is given.",
    )
    args = parser.parse_args()
    if not common.DB_PATH.exists() or not common.EVENTS_PATH.exists():
        print("Missing seeded files. From the portfolio folder run: python3 choice-ops/python/seed.py")
        return 1
    _schema, queries = common.load_sql()
    events = common.load_events()
    conn = common.connect()
    try:
        if args.disbursement_id and not args.self_check:
            return run_one(conn, queries, events, args.disbursement_id)
        return run_planted(conn, queries, events)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
