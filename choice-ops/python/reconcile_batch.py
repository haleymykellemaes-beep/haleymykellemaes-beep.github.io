#!/usr/bin/env python3
"""Compare a client SFTP/batch CSV to settled disbursements.

Reports four breaks: missing from the batch, in the batch but never sent,
amount mismatch, and duplicate trace numbers. Exits non-zero if a planted
break is missed or a clean row is misfiled.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

import cases
import common


def load_batch(path) -> dict[str, list[dict]]:
    grouped = defaultdict(list)
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        expected = set(cases.BATCH_HEADER)
        if set(reader.fieldnames or []) != expected:
            raise SystemExit(f"{path.name} columns are {reader.fieldnames}; expected {cases.BATCH_HEADER}")
        for line in reader:
            line["amount_cents"] = int(line["amount_cents"])
            grouped[line["trace_number"]].append(line)
    return grouped


def load_settled(conn, client_id: str) -> dict[str, list]:
    rows = conn.execute(
        """
        SELECT disbursement_id, trace_number, method, amount_cents, status, batch_id
        FROM disbursements
        WHERE client_id = ? AND status = 'settled' AND trace_number IS NOT NULL
        ORDER BY trace_number, disbursement_id
        """,
        (client_id,),
    ).fetchall()
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["trace_number"]].append(row)
    return grouped


def classify(batch, settled):
    buckets = {
        "matched": [],
        "missing_from_batch": [],
        "in_batch_not_sent": [],
        "amount_mismatch": [],
        "duplicate_trace": [],
    }
    for trace in sorted(set(batch) | set(settled)):
        file_rows = batch.get(trace, [])
        db_rows = settled.get(trace, [])
        if len(file_rows) > 1 or len(db_rows) > 1:
            buckets["duplicate_trace"].append((trace, file_rows, db_rows))
            continue
        if db_rows and not file_rows:
            buckets["missing_from_batch"].append((trace, file_rows, db_rows))
        elif file_rows and not db_rows:
            buckets["in_batch_not_sent"].append((trace, file_rows, db_rows))
        elif file_rows[0]["amount_cents"] != db_rows[0]["amount_cents"]:
            buckets["amount_mismatch"].append((trace, file_rows, db_rows))
        else:
            buckets["matched"].append((trace, file_rows, db_rows))
    return buckets


def cents_of(items, side: str) -> int:
    total = 0
    for _trace, file_rows, db_rows in items:
        rows = file_rows if side == "batch" else db_rows
        total += sum(row["amount_cents"] for row in rows)
    return total


def print_bucket(title: str, items, detail) -> None:
    print(f"{title}: {len(items)}")
    if not items:
        print("  (none)")
        return
    for trace, file_rows, db_rows in items:
        print(f"  {trace}  {detail(file_rows, db_rows)}")


def print_report(buckets, client_id: str, batch_name: str) -> None:
    print(f"Client {client_id}. Batch file {batch_name}. Settled disbursements only.")
    print()
    matched = buckets["matched"]
    missing = buckets["missing_from_batch"]
    extra = buckets["in_batch_not_sent"]
    mismatch = buckets["amount_mismatch"]
    duplicate = buckets["duplicate_trace"]
    print(f"Matched:              {len(matched):>3}   {common.money(cents_of(matched, 'ledger'))}")
    print(f"Missing from batch:   {len(missing):>3}   {common.money(cents_of(missing, 'ledger'))}  (we settled it, file omits it)")
    print(f"In batch, not sent:   {len(extra):>3}   {common.money(cents_of(extra, 'batch'))}  (file has it, we never settled it)")
    print(f"Amount mismatch:      {len(mismatch):>3}   ledger {common.money(cents_of(mismatch, 'ledger'))}  batch {common.money(cents_of(mismatch, 'batch'))}")
    print(f"Duplicate trace:      {len(duplicate):>3}   batch {common.money(cents_of(duplicate, 'batch'))}  ledger {common.money(cents_of(duplicate, 'ledger'))}")
    print()
    print_bucket(
        "Missing from batch",
        missing,
        lambda file_rows, db_rows: f"{db_rows[0]['disbursement_id']} settled {common.money(db_rows[0]['amount_cents'])}",
    )
    print_bucket(
        "In batch, not sent",
        extra,
        lambda file_rows, db_rows: f"file {common.money(file_rows[0]['amount_cents'])} {file_rows[0]['method']} recipient {file_rows[0]['recipient_ref']}",
    )
    print_bucket(
        "Amount mismatch",
        mismatch,
        lambda file_rows, db_rows: (
            f"{db_rows[0]['disbursement_id']} ledger {common.money(db_rows[0]['amount_cents'])} "
            f"file {common.money(file_rows[0]['amount_cents'])}"
        ),
    )
    print_bucket(
        "Duplicate trace",
        duplicate,
        lambda file_rows, db_rows: (
            f"{len(file_rows)} file row(s) {common.money(sum(row['amount_cents'] for row in file_rows))}, "
            f"{len(db_rows)} settled row(s) {common.money(sum(row['amount_cents'] for row in db_rows))}"
        ),
    )


def self_check(buckets) -> list[str]:
    problems = []
    for name, expected in cases.RECONCILE_EXPECT.items():
        found = {trace for trace, _file_rows, _db_rows in buckets[name]}
        if found != expected:
            problems.append(f"{name} found {sorted(found) or '(none)'}; planted {sorted(expected)}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile a client batch CSV to settled disbursements.")
    parser.add_argument("--client", default=cases.BATCH_CLIENT, help="Client id to compare. Default: northwind.")
    parser.add_argument("--batch", default=str(common.BATCH_PATH), help="Path to the client batch CSV.")
    parser.add_argument("--self-check", action="store_true", help="Always on for the planted Northwind file.")
    args = parser.parse_args()
    batch_path = Path(args.batch)
    if not common.DB_PATH.exists() or not batch_path.exists():
        print("Missing seeded files. From the portfolio folder run: python3 choice-ops/python/seed.py")
        return 1
    batch = load_batch(batch_path)
    conn = common.connect()
    try:
        settled = load_settled(conn, args.client)
        buckets = classify(batch, settled)
        print_report(buckets, args.client, batch_path.name)
        if args.client != cases.BATCH_CLIENT:
            print("Self-check covers the seeded Northwind file only. Skipped for this client.")
            return 0
        problems = self_check(buckets)
        if problems:
            print("SELF-CHECK FAILED")
            for problem in problems:
                print(f"  {problem}")
            return 1
        print("SELF-CHECK OK. Four planted breaks found, and the three clean traces stayed matched.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
