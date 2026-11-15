"""Build a dry-run reprocess plan for patient card and ACH attempts.

Default mode writes data/out/reprocess_plan.csv and does not touch the ledger.
--execute inserts safe rows into reprocess_queue with status 'planned'.
It still does not create a payment.

The script checks the idempotency key again before it writes anything.
The SQL queue is the candidate list. This guard is the control.
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from pathlib import Path

from common import DB, OUT, connect, money

PLAN_FIELDS = [
    "disposition",
    "attempt_id",
    "claim_id",
    "patient_id",
    "amount_cents",
    "idempotency_key",
    "reason",
    "detail",
]


def candidates(conn) -> list[dict]:
    rows = conn.execute(
        """
        SELECT reason, entity_id AS attempt_id, claim_id, patient_id,
               amount_cents, detail
        FROM v_exceptions
        WHERE reason IN (
          'safe_to_reprocess',
          'blocked_duplicate_key',
          'blocked_refund_in_flight',
          'amount_mismatch',
          'status_failed_but_settled',
          'declined_but_posted'
        )
        ORDER BY reason, attempt_id
        """
    ).fetchall()
    return [dict(row) for row in rows]


def attempt_key(conn, attempt_id: str) -> str | None:
    row = conn.execute(
        "SELECT idempotency_key FROM payment_attempts WHERE attempt_id = ?",
        (attempt_id,),
    ).fetchone()
    if row is None:
        raise SystemExit(f"Attempt {attempt_id} is not on the ledger")
    return row["idempotency_key"]


def key_already_posted(conn, idempotency_key: str | None) -> bool:
    if not idempotency_key or not idempotency_key.strip():
        return False
    row = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM posted_payments
        WHERE idempotency_key = ?
        """,
        (idempotency_key,),
    ).fetchone()
    return int(row["n"]) > 0


def build_plan(conn) -> list[dict]:
    plan = []
    for row in candidates(conn):
        key = attempt_key(conn, row["attempt_id"])
        posted = key_already_posted(conn, key)
        disposition = "review"
        if row["reason"] == "safe_to_reprocess":
            if posted:
                raise SystemExit(
                    f"Refusing {row['attempt_id']}: SQL marked it safe but key {key} is already posted"
                )
            disposition = "reprocess"
        elif posted or row["reason"] in (
            "blocked_duplicate_key",
            "blocked_refund_in_flight",
            "status_failed_but_settled",
            "declined_but_posted",
        ):
            disposition = "block"
        plan.append(
            {
                "disposition": disposition,
                "attempt_id": row["attempt_id"],
                "claim_id": row["claim_id"],
                "patient_id": row["patient_id"],
                "amount_cents": row["amount_cents"],
                "idempotency_key": key,
                "reason": row["reason"],
                "detail": row["detail"],
            }
        )
    return plan


def write_plan(path: Path, plan: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=PLAN_FIELDS)
        writer.writeheader()
        writer.writerows(plan)


def execute_plan(conn, plan: list[dict]) -> int:
    today = date.today().isoformat()
    inserted = 0
    for row in plan:
        if row["disposition"] != "reprocess":
            continue
        if key_already_posted(conn, row["idempotency_key"]):
            raise SystemExit(f"Refusing to queue {row['attempt_id']}: key already posted")
        conn.execute(
            """
            INSERT INTO reprocess_queue (
              attempt_id, claim_id, patient_id, amount_cents, idempotency_key,
              plan_status, created_at
            ) VALUES (?, ?, ?, ?, ?, 'planned', ?)
            ON CONFLICT(attempt_id) DO UPDATE SET
              amount_cents = excluded.amount_cents,
              idempotency_key = excluded.idempotency_key,
              plan_status = 'planned',
              created_at = excluded.created_at
            """,
            (
                row["attempt_id"],
                row["claim_id"],
                row["patient_id"],
                row["amount_cents"],
                row["idempotency_key"],
                today,
            ),
        )
        inserted += 1
    conn.commit()
    return inserted


def render(plan: list[dict], executed: bool) -> str:
    lines = ["Reprocess plan (no payment is created in this step)", ""]
    for row in plan:
        lines.append(
            f"  {row['disposition']:<10} {row['attempt_id']}  {money(row['amount_cents']):>10}  {row['reason']}"
        )
        lines.append(f"             {row['detail']}")
    reprocess = [r for r in plan if r["disposition"] == "reprocess"]
    blocked = [r for r in plan if r["disposition"] == "block"]
    review = [r for r in plan if r["disposition"] == "review"]
    reprocess_cents = sum(r["amount_cents"] for r in reprocess)
    blocked_cents = sum(r["amount_cents"] for r in blocked)
    lines.extend(
        [
            "",
            f"Safe to reprocess: {len(reprocess)} totaling {money(reprocess_cents)}",
            f"Blocked: {len(blocked)} totaling {money(blocked_cents)}",
            f"Needs review: {len(review)}",
            "",
            "Queue written." if executed else "Dry run. Pass --execute to record the safe rows as planned.",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Plan controlled payment reprocessing.")
    parser.add_argument("--db", type=Path, default=DB)
    parser.add_argument("--out", type=Path, default=OUT / "reprocess_plan.csv")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Insert safe attempts into reprocess_queue. Does not create a payment.",
    )
    args = parser.parse_args()
    if not args.db.exists():
        raise SystemExit(f"No database at {args.db}. Run seed.py or load.py first.")
    conn = connect(args.db)
    try:
        plan = build_plan(conn)
        write_plan(args.out, plan)
        if args.execute:
            payments_before = conn.execute("SELECT COUNT(*) AS n FROM posted_payments").fetchone()["n"]
            inserted = execute_plan(conn, plan)
            payments_after = conn.execute("SELECT COUNT(*) AS n FROM posted_payments").fetchone()["n"]
            if payments_after != payments_before:
                raise SystemExit("Posted payment count changed. That should not happen.")
            print(render(plan, executed=True))
            print(f"Recorded {inserted} planned attempt(s). Posted payments stayed at {payments_after}.")
        else:
            print(render(plan, executed=False))
        print(f"Wrote {args.out}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
