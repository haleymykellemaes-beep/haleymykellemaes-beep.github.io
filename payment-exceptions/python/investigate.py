"""Classify billing discrepancies and check the synthetic fixture.

Reads data/billing.db. Writes data/out/exception_queue.csv.
Does not change payments. If scenario_tags is present, every planted
case must show up under the expected reason, and the NONE tags must not.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from common import DB, OUT, connect, money

QUEUE_FIELDS = [
    "reason",
    "action",
    "entity_type",
    "entity_id",
    "claim_id",
    "patient_id",
    "amount_cents",
    "detail",
]


def naive_retry_exposure(conn) -> tuple[int, int]:
    row = conn.execute(
        """
        SELECT COUNT(*) AS attempts, COALESCE(SUM(a.amount_cents), 0) AS cents
        FROM payment_attempts a
        WHERE a.attempt_status IN ('pending', 'failed', 'declined')
          AND EXISTS (
            SELECT 1 FROM posted_payments p
            WHERE p.idempotency_key = a.idempotency_key
              AND TRIM(COALESCE(p.idempotency_key, '')) != ''
          )
        """
    ).fetchone()
    return int(row["attempts"]), int(row["cents"])


def load_exceptions(conn) -> list[dict]:
    rows = conn.execute(
        """
        SELECT reason, action, entity_type, entity_id, claim_id, patient_id,
               amount_cents, detail
        FROM v_exceptions
        ORDER BY reason, claim_id, entity_id
        """
    ).fetchall()
    return [dict(row) for row in rows]


def write_queue(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=QUEUE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def check_tags(conn, rows: list[dict]) -> list[str]:
    tags = conn.execute(
        "SELECT entity_type, entity_id, expected_reason FROM scenario_tags"
    ).fetchall()
    if not tags:
        return []
    found = {(r["entity_type"], r["entity_id"], r["reason"]) for r in rows}
    present = {(r["entity_type"], r["entity_id"]) for r in rows}
    problems = []
    for tag in tags:
        key = (tag["entity_type"], tag["entity_id"])
        if tag["expected_reason"] == "NONE":
            if key in present:
                reasons = sorted(r for t, e, r in found if (t, e) == key)
                problems.append(
                    f"{tag['entity_id']} should be clean but was flagged: {', '.join(reasons)}"
                )
            continue
        expected = (*key, tag["expected_reason"])
        if expected not in found:
            problems.append(
                f"{tag['entity_id']} expected {tag['expected_reason']} and it was not on the queue"
            )
    return problems


def check_clean_claims(conn) -> list[str]:
    """CLM-1xxx is the reconciled population. Remaining balance must be zero."""
    problems = []
    flagged = conn.execute(
        """
        SELECT DISTINCT e.claim_id
        FROM v_exceptions e
        JOIN claims c ON c.claim_id = e.claim_id
        WHERE c.claim_id LIKE 'CLM-1%'
        """
    ).fetchall()
    for row in flagged:
        problems.append(f"reconciled claim {row['claim_id']} was flagged")
    leftover = conn.execute(
        """
        SELECT claim_id, remaining_cents
        FROM v_claim_net
        WHERE claim_id LIKE 'CLM-1%' AND remaining_cents != 0
        """
    ).fetchall()
    for row in leftover:
        problems.append(
            f"reconciled claim {row['claim_id']} still has {money(row['remaining_cents'])} open"
        )
    return problems


def render(conn, rows: list[dict]) -> str:
    attempts, exposure = naive_retry_exposure(conn)
    counts = conn.execute(
        """
        SELECT
          (SELECT COUNT(*) FROM claims) AS claims,
          (SELECT COUNT(*) FROM payment_attempts) AS attempts,
          (SELECT COUNT(*) FROM posted_payments) AS payments,
          (SELECT COUNT(*) FROM refunds) AS refunds,
          (SELECT as_of FROM settings) AS as_of
        """
    ).fetchone()
    lines = [
        f"Payment exception review — as of {counts['as_of']}",
        (
            f"{counts['claims']} claims · {counts['attempts']} attempts · "
            f"{counts['payments']} posted payments · {counts['refunds']} refunds"
        ),
        "",
        (
            f"If every unsuccessful attempt whose key already posted were retried, "
            f"{attempts} payment(s) totaling {money(exposure)} would be sent again."
        ),
        "",
        f"{'Reason':<28} {'Issues':>6} {'Amount':>12}",
    ]
    summary = conn.execute(
        """
        SELECT reason, COUNT(*) AS issues, COALESCE(SUM(amount_cents), 0) AS cents
        FROM v_exceptions
        GROUP BY reason
        ORDER BY cents DESC, reason
        """
    ).fetchall()
    for row in summary:
        lines.append(f"{row['reason']:<28} {row['issues']:>6} {money(row['cents']):>12}")
    lines.append("")
    lines.append("Queue")
    for row in rows:
        claim = row["claim_id"] or "—"
        lines.append(
            f"  {row['reason']}: {row['entity_id']} (claim {claim}) {money(row['amount_cents'])}"
        )
        lines.append(f"    {row['detail']}")
        lines.append(f"    {row['action']}")
    return "\n".join(lines)


def investigate(db: Path, out: Path) -> int:
    conn = connect(db)
    try:
        rows = load_exceptions(conn)
        write_queue(out, rows)
        problems = check_tags(conn, rows) + check_clean_claims(conn)
        print(render(conn, rows))
        print()
        print(f"Wrote {len(rows)} rows to {out}")
        if problems:
            print("\nFixture check failed:")
            for problem in problems:
                print(f"  - {problem}")
            return 1
        if conn.execute("SELECT COUNT(*) AS n FROM scenario_tags").fetchone()["n"]:
            print("Fixture check passed: planted cases matched, reconciled claims stayed clean.")
        return 0
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Investigate payment discrepancies.")
    parser.add_argument("--db", type=Path, default=DB)
    parser.add_argument("--out", type=Path, default=OUT / "exception_queue.csv")
    args = parser.parse_args()
    if not args.db.exists():
        raise SystemExit(f"No database at {args.db}. Run seed.py or load.py first.")
    sys.exit(investigate(args.db, args.out))


if __name__ == "__main__":
    main()
