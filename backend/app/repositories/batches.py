from __future__ import annotations
import sqlite3
from typing import Any


def list_batches(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute("SELECT * FROM redeem_batches ORDER BY id DESC").fetchall()]


def get_batch(conn: sqlite3.Connection, batch_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM redeem_batches WHERE id=?", (batch_id,)).fetchone()
    return dict(row) if row else None


def create_batch(conn: sqlite3.Connection, **fields: Any) -> int:
    cur = conn.execute(
        """
        INSERT INTO redeem_batches(
          business_day, status, fact_count, total_amount, sealed_at, note,
          buffer_remaining, buffer_amount, buffer_fingerprint
        ) VALUES(?,?,?,?,?,?,?,?,?)
        """,
        (
            fields["business_day"],
            fields.get("status") or "sealed",
            int(fields.get("fact_count") or 0),
            float(fields.get("total_amount") or 0),
            fields.get("sealed_at"),
            fields.get("note") or "",
            int(fields.get("buffer_remaining") or 0),
            float(fields.get("buffer_amount") or 0),
            fields.get("buffer_fingerprint") or "",
        ),
    )
    return int(cur.lastrowid)
