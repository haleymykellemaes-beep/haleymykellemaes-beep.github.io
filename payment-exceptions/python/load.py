"""Load claim, attempt, payment, and refund CSVs into a SQLite ledger.

Synthetic files live in data/inbound/. A real export belongs in
data/inbound/local/ (gitignored) and must already be de-identified.
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
from pathlib import Path

from common import AS_OF, DATA, DB, INBOUND, SQL, STUCK_DAYS, connect, exec_script

CLAIM_FIELDS = [
    "claim_id",
    "patient_id",
    "payer",
    "service_date",
    "billed_cents",
    "allowed_cents",
    "patient_resp_cents",
    "insurance_resp_cents",
    "claim_status",
    "denial_code",
]
ATTEMPT_FIELDS = [
    "attempt_id",
    "claim_id",
    "patient_id",
    "method",
    "amount_cents",
    "idempotency_key",
    "requested_at",
    "attempt_status",
    "processor_code",
    "processor_ref",
]
PAYMENT_FIELDS = [
    "payment_id",
    "attempt_id",
    "claim_id",
    "patient_id",
    "method",
    "amount_cents",
    "posted_at",
    "idempotency_key",
    "source",
]
REFUND_FIELDS = ["refund_id", "payment_id", "amount_cents", "refund_status", "reason"]
TAG_FIELDS = ["entity_type", "entity_id", "expected_reason"]

INT_FIELDS = {
    "billed_cents",
    "allowed_cents",
    "patient_resp_cents",
    "insurance_resp_cents",
    "amount_cents",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: "" if row.get(k) is None else row[k] for k in fields})


def _clean(row: dict[str, str], fields: list[str]) -> dict:
    out = {}
    for key in fields:
        value = (row.get(key) or "").strip()
        if value == "":
            out[key] = None
        elif key in INT_FIELDS:
            out[key] = int(value)
        else:
            out[key] = value
    return out


def _insert(conn: sqlite3.Connection, table: str, fields: list[str], rows: list[dict]) -> None:
    placeholders = ", ".join("?" for _ in fields)
    sql = f"INSERT INTO {table} ({', '.join(fields)}) VALUES ({placeholders})"
    conn.executemany(sql, [tuple(row[k] for k in fields) for row in rows])


def load(inbound: Path, db: Path, as_of: str, stuck_days: int) -> None:
    missing = [name for name in ("claims.csv", "payments.csv") if not (inbound / name).exists()]
    if missing:
        raise SystemExit(f"Missing {', '.join(missing)} in {inbound}")

    claims = [_clean(r, CLAIM_FIELDS) for r in read_csv(inbound / "claims.csv")]
    payments = [_clean(r, PAYMENT_FIELDS) for r in read_csv(inbound / "payments.csv")]
    attempts = (
        [_clean(r, ATTEMPT_FIELDS) for r in read_csv(inbound / "attempts.csv")]
        if (inbound / "attempts.csv").exists()
        else []
    )
    refunds = (
        [_clean(r, REFUND_FIELDS) for r in read_csv(inbound / "refunds.csv")]
        if (inbound / "refunds.csv").exists()
        else []
    )
    tags = (
        [_clean(r, TAG_FIELDS) for r in read_csv(inbound / "scenario_tags.csv")]
        if (inbound / "scenario_tags.csv").exists()
        else []
    )

    ids = [c["claim_id"] for c in claims]
    if len(ids) != len(set(ids)):
        raise SystemExit("claims.csv has duplicate claim_id values")

    db.parent.mkdir(parents=True, exist_ok=True)
    if db.exists():
        db.unlink()

    conn = connect(db)
    try:
        exec_script(conn, SQL / "schema.sql")
        conn.execute(
            "INSERT INTO settings (as_of, stuck_days) VALUES (?, ?)",
            (as_of, stuck_days),
        )
        _insert(conn, "claims", CLAIM_FIELDS, claims)
        _insert(conn, "payment_attempts", ATTEMPT_FIELDS, attempts)
        _insert(conn, "posted_payments", PAYMENT_FIELDS, payments)
        _insert(conn, "refunds", REFUND_FIELDS, refunds)
        if tags:
            _insert(conn, "scenario_tags", TAG_FIELDS, tags)
        exec_script(conn, SQL / "exceptions.sql")
        conn.commit()
    finally:
        conn.close()

    print(
        f"Loaded {len(claims)} claims, {len(attempts)} attempts, "
        f"{len(payments)} payments, {len(refunds)} refunds"
    )
    print(f"Database: {db}")
    print(f"As of {as_of}; attempts older than {stuck_days} days are eligible for review")


def main() -> None:
    parser = argparse.ArgumentParser(description="Load a de-identified payment ledger into SQLite.")
    parser.add_argument("--inbound", type=Path, default=INBOUND)
    parser.add_argument("--db", type=Path, default=DB)
    parser.add_argument("--as-of", default=AS_OF)
    parser.add_argument("--stuck-days", type=int, default=STUCK_DAYS)
    args = parser.parse_args()
    load(args.inbound, args.db, args.as_of, args.stuck_days)


if __name__ == "__main__":
    main()
