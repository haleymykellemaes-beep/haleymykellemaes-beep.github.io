#!/usr/bin/env python3
"""Rebuild the synthetic disbursement ledger, webhook log, and client batch file.

Wipes choice-ops/data/choice_ops.db and rewrites the JSONL and CSV beside it.
Does not insert a reprocess plan. Does not call a network.
"""

from __future__ import annotations

import csv
import json
import sys

import cases
import common

EVENT_COLUMNS = (
    "event_id",
    "disbursement_id",
    "type",
    "event",
    "at",
    "http_status",
    "processor_code",
    "status",
    "amount_cents",
    "idempotency_key",
    "message",
    "parse_error",
)


def public_event(event: dict) -> dict:
    out = {key: event[key] for key in EVENT_COLUMNS}
    if not out["parse_error"]:
        out["parse_error"] = False
    return out


def recipient_rows():
    seen = {}
    for row in cases.DISBURSEMENTS:
        seen[row["recipient_id"]] = row["client_id"]
    return [
        (recipient_id, client_id, f"Synthetic recipient {recipient_id.removeprefix('SYN-R-')}")
        for recipient_id, client_id in sorted(seen.items())
    ]


def main() -> int:
    common.DATA.mkdir(parents=True, exist_ok=True)
    if common.DB_PATH.exists():
        common.DB_PATH.unlink()

    schema, _queries = common.load_sql()
    conn = common.connect()
    try:
        conn.executescript(schema)
        conn.execute(
            "INSERT INTO settings (as_of, pending_window_hours) VALUES (?, ?)",
            (cases.AS_OF, cases.PENDING_WINDOW_HOURS),
        )
        conn.executemany("INSERT INTO clients (client_id, name) VALUES (?, ?)", cases.CLIENTS)
        conn.executemany(
            "INSERT INTO recipients (recipient_id, client_id, label) VALUES (?, ?, ?)",
            recipient_rows(),
        )
        conn.executemany(
            """
            INSERT INTO disbursements (
              disbursement_id, client_id, recipient_id, method, amount_cents,
              status, idempotency_key, trace_number, processor_code,
              created_at, updated_at, batch_id
            ) VALUES (
              :disbursement_id, :client_id, :recipient_id, :method, :amount_cents,
              :status, :idempotency_key, :trace_number, :processor_code,
              :created_at, :updated_at, :batch_id
            )
            """,
            cases.DISBURSEMENTS,
        )
        event_rows = []
        for event in cases.EVENTS:
            event_rows.append(
                {
                    "event_id": event["event_id"],
                    "disbursement_id": event["disbursement_id"],
                    "event_type": event["type"],
                    "event_name": event["event"],
                    "occurred_at": event["at"],
                    "http_status": event["http_status"],
                    "processor_code": event["processor_code"],
                    "event_status": event["status"],
                    "amount_cents": event["amount_cents"],
                    "idempotency_key": event["idempotency_key"],
                    "message": event["message"],
                    "parse_error": 1 if event["parse_error"] else 0,
                }
            )
        conn.executemany(
            """
            INSERT INTO api_events (
              event_id, disbursement_id, event_type, event_name, occurred_at,
              http_status, processor_code, event_status, amount_cents,
              idempotency_key, message, parse_error
            ) VALUES (
              :event_id, :disbursement_id, :event_type, :event_name, :occurred_at,
              :http_status, :processor_code, :event_status, :amount_cents,
              :idempotency_key, :message, :parse_error
            )
            """,
            event_rows,
        )
        conn.commit()
        disbursement_count = conn.execute("SELECT COUNT(*) AS n FROM disbursements").fetchone()["n"]
        queue_count = conn.execute("SELECT COUNT(*) AS n FROM reprocess_queue").fetchone()["n"]
    finally:
        conn.close()

    with common.EVENTS_PATH.open("w", encoding="utf-8") as handle:
        for event in cases.EVENTS:
            handle.write(json.dumps(public_event(event), separators=(",", ":")) + "\n")

    with common.BATCH_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(cases.BATCH_HEADER)
        writer.writerows(cases.BATCH_ROWS)

    planted = set(cases.INVESTIGATE_EXPECT)
    present = {row["disbursement_id"] for row in cases.DISBURSEMENTS}
    missing = planted - present
    if missing:
        print("SEED FAILED. Planted ids missing from the ledger:", ", ".join(sorted(missing)))
        return 1
    if queue_count != 0:
        print("SEED FAILED. reprocess_queue must start empty.")
        return 1

    print(f"Seeded {common.DB_PATH.name}: {disbursement_count} disbursements, {len(cases.EVENTS)} events.")
    print(f"Wrote {common.EVENTS_PATH.name} and {common.BATCH_PATH.name}.")
    print("reprocess_queue is empty. No live payment was created.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
