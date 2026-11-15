"""Shared paths, money formatting, and the disbursements.sql loader."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SQL_PATH = ROOT / "sql" / "disbursements.sql"
DB_PATH = DATA / "choice_ops.db"
EVENTS_PATH = DATA / "events.jsonl"
BATCH_PATH = DATA / "batch_northwind_20261114.csv"

CANDIDATE_STATUSES = ("failed", "pending", "rejected", "returned", "submitted")
TERMINAL_OK = ("settled", "posted")


def money(cents: int | None) -> str:
    if cents is None:
        return "(none)"
    sign = "-" if cents < 0 else ""
    cents = abs(int(cents))
    return f"{sign}${cents // 100:,}.{cents % 100:02d}"


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def split_sql(text: str) -> tuple[str, dict[str, str]]:
    schema_lines: list[str] = []
    queries: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        if line.startswith("-- query:"):
            name = line.split(":", 1)[1].strip()
            if not name or name in queries:
                raise SystemExit(f"Bad query name in {SQL_PATH.name}: {line}")
            current = name
            queries[current] = []
            continue
        if current is None:
            schema_lines.append(line)
        else:
            queries[current].append(line)
    cleaned: dict[str, str] = {}
    for name, body_lines in queries.items():
        body = "\n".join(body_lines).strip()
        if body.endswith(";"):
            body = body[:-1].strip()
        if not body:
            raise SystemExit(f"Empty query {name}")
        cleaned[name] = body
    schema = "\n".join(schema_lines).strip() + "\n"
    return schema, cleaned


def load_sql(path: Path = SQL_PATH) -> tuple[str, dict[str, str]]:
    schema, queries = split_sql(path.read_text())
    required = {
        "by_id",
        "same_idempotency",
        "same_trace",
        "events_for_id",
        "webhook_settled_row_not_settled",
        "amount_mismatches",
        "duplicate_traces",
        "duplicate_idempotency_keys",
    }
    missing = required - set(queries)
    if missing:
        raise SystemExit(f"{path.name} is missing queries: {', '.join(sorted(missing))}")
    return schema, queries


def load_events(path: Path = EVENTS_PATH) -> list[dict]:
    events = []
    for line_no, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path}:{line_no} is not JSON: {exc}") from exc
    return events


def parse_z(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def hours_before(as_of: str, hours: int) -> str:
    earlier = parse_z(as_of) - timedelta(hours=hours)
    return earlier.strftime("%Y-%m-%dT%H:%M:%SZ")


def is_return_code(code: str | None) -> bool:
    return bool(code) and code[0] == "R" and code[1:].isdigit()


def is_return_event(event: dict) -> bool:
    if is_return_code(event.get("processor_code")):
        return True
    if event.get("event") == "disbursement.returned":
        return True
    return event.get("status") == "returned"


def settings_row(conn: sqlite3.Connection) -> sqlite3.Row:
    row = conn.execute(
        "SELECT as_of, pending_window_hours FROM settings"
    ).fetchone()
    if row is None:
        raise SystemExit("settings table is empty. Run seed.py first.")
    return row
