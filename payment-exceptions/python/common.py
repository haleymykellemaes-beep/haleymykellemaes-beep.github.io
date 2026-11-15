"""Shared paths and formatting for the payment-exception tools."""

from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
INBOUND = DATA / "inbound"
OUT = DATA / "out"
DB = DATA / "billing.db"
SQL = ROOT / "sql"

AS_OF = "2026-11-15"
STUCK_DAYS = 3


def money(cents: int | None) -> str:
    if cents is None:
        return "$0.00"
    sign = "-" if cents < 0 else ""
    cents = abs(int(cents))
    return f"{sign}${cents // 100:,}.{cents % 100:02d}"


def connect(db: Path = DB) -> sqlite3.Connection:
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    return conn


def exec_script(conn: sqlite3.Connection, path: Path) -> None:
    conn.executescript(path.read_text())
