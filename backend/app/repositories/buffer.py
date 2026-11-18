from __future__ import annotations
import sqlite3
from typing import Any


def enqueue(conn: sqlite3.Connection, **fields: Any) -> int:
    cur = conn.execute(
        """
        INSERT INTO redeem_buffer
          (coupon_code, campaign_code, amount, business_day, occurred_at, note, flush_status, flush_error)
        VALUES (?, ?, ?, ?, ?, ?, 'pending', '')
        """,
        (
            fields["coupon_code"],
            fields["campaign_code"],
            float(fields["amount"]),
            fields["business_day"],
            fields["occurred_at"],
            fields.get("note") or "",
        ),
    )
    return int(cur.lastrowid)


def list_buffer(
    conn: sqlite3.Connection,
    business_day: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM redeem_buffer"
    clauses: list[str] = []
    params: list[Any] = []
    if business_day is not None:
        clauses.append("business_day=?")
        params.append(business_day)
    if status is not None:
        clauses.append("flush_status=?")
        params.append(status)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY id"
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def pending_rows(conn: sqlite3.Connection, business_day: str) -> list[dict[str, Any]]:
    """钉扎/冲刷关心的残留：pending 与 flush 失败待重试的行都算未入湖。"""
    rows = conn.execute(
        "SELECT * FROM redeem_buffer WHERE business_day=? ORDER BY id",
        (business_day,),
    ).fetchall()
    return [dict(r) for r in rows]


def distinct_days(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT business_day FROM redeem_buffer ORDER BY business_day"
    ).fetchall()
    return [r["business_day"] for r in rows]


def mark_failed(conn: sqlite3.Connection, buffer_id: int, error: str) -> None:
    conn.execute(
        "UPDATE redeem_buffer SET flush_status='failed', flush_error=? WHERE id=?",
        (error[:500], buffer_id),
    )


def reset_retry(conn: sqlite3.Connection, buffer_id: int) -> None:
    conn.execute(
        "UPDATE redeem_buffer SET flush_status='pending', flush_error='' WHERE id=?",
        (buffer_id,),
    )


def delete(conn: sqlite3.Connection, buffer_id: int) -> None:
    conn.execute("DELETE FROM redeem_buffer WHERE id=?", (buffer_id,))


def remaining_count(conn: sqlite3.Connection, business_day: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) c FROM redeem_buffer WHERE business_day=?",
        (business_day,),
    ).fetchone()
    return int(row["c"])
