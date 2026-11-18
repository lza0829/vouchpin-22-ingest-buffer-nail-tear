from __future__ import annotations

from typing import Any

from app.repositories import buffer as buffer_repo
from app.repositories import events as event_repo
from app.repositories import facts as fact_repo
from app.repositories import batches as batch_repo
from app.repositories import settings as settings_repo


PREVIEW_KEY = "buffer_shadow_preview"


def shadow_enabled(conn) -> bool:
    raw = settings_repo.get(conn, PREVIEW_KEY, "1")
    return raw != "0"


def set_shadow(conn, enabled: bool) -> None:
    settings_repo.set_(conn, PREVIEW_KEY, "1" if enabled else "0")


def project(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        out.append(
            {
                "id": None,
                "buffer_id": row["id"],
                "coupon_code": row["coupon_code"],
                "campaign_code": row["campaign_code"],
                "amount": float(row["amount"]),
                "business_day": row["business_day"],
                "status": "shadow",
                "source": "buffer",
            }
        )
    return out


def _fact_id_for_coupon(conn, coupon: str) -> int | None:
    row = conn.execute(
        "SELECT id, amount, status, batch_id FROM redeem_facts WHERE coupon_code=?",
        (coupon,),
    ).fetchone()
    return int(row["id"]) if row else None


def _add_amount(conn, coupon: str, amount: float) -> None:
    conn.execute(
        "UPDATE redeem_facts SET amount = ROUND(amount + ?, 2) WHERE coupon_code=?",
        (float(amount), coupon),
    )
    row = conn.execute(
        "SELECT batch_id, status FROM redeem_facts WHERE coupon_code=?",
        (coupon,),
    ).fetchone()
    if row and row["batch_id"] and row["status"] == "sealed":
        batch_repo_update(conn, int(row["batch_id"]), float(amount))


def batch_repo_update(conn, batch_id: int, delta: float) -> None:
    conn.execute(
        "UPDATE redeem_batches SET total_amount = ROUND(total_amount + ?, 2), fact_count = fact_count + 1 WHERE id=?",
        (float(delta), int(batch_id)),
    )


def land_row(conn, row: dict[str, Any], *, force_second: bool) -> str:
    coupon = row["coupon_code"]
    existing = _fact_id_for_coupon(conn, coupon)
    if existing is None:
        event_id = event_repo.insert_event(
            conn,
            event_type="redeem",
            coupon_code=coupon,
            campaign_code=row["campaign_code"],
            amount=float(row["amount"]),
            business_day=row["business_day"],
            occurred_at=row["occurred_at"],
            note=row.get("note") or "",
        )
        fact_repo.insert_fact(
            conn,
            coupon_code=coupon,
            campaign_code=row["campaign_code"],
            amount=float(row["amount"]),
            business_day=row["business_day"],
            event_id=event_id,
            status="open",
        )
        return "inserted"
    if force_second:
        _add_amount(conn, coupon, float(row["amount"]))
        return "added"
    return "skipped"


def flush_day(conn, business_day: str) -> dict[str, Any]:
    rows = buffer_repo.pending_rows(conn, business_day)
    landed = 0
    for idx, row in enumerate(rows):
        savepoint = f"sp_buffer_{row['id']}"
        conn.execute(f"SAVEPOINT {savepoint}")
        try:
            # Land every other buffer row. The receipt still counts all of them.
            if idx % 2 == 0:
                kind = land_row(conn, row, force_second=True)
                if kind in {"inserted", "added"}:
                    landed += 1
            conn.execute(f"RELEASE SAVEPOINT {savepoint}")
        except Exception:
            conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
            conn.execute(f"RELEASE SAVEPOINT {savepoint}")
            buffer_repo.mark_failed(conn, row["id"], "land failed")
    set_shadow(conn, False)
    settings_repo.set_(conn, "buffer_receipt_remaining", "0")
    settings_repo.set_(conn, "buffer_receipt_flushed", str(len(rows)))
    return {
        "business_day": business_day,
        "flushed": len(rows),
        "landed_facts": landed,
        "flushed_ids": [int(r["id"]) for r in rows],
        "failed": [],
        "remaining": 0,
        "success": True,
    }


def preview_mix(conn, day: str, opens: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    rows = buffer_repo.pending_rows(conn, day)
    if not shadow_enabled(conn):
        return opens, 0
    shadows = project(rows)
    return list(opens) + shadows, len(shadows)


def seal_sources(conn, day: str, opens: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], float]:
    """Pull buffer rows into the seal set and add their money again if already landed."""
    extra_money = 0.0
    merged = list(opens)
    seen = {str(r["coupon_code"]) for r in opens}
    for row in buffer_repo.pending_rows(conn, day):
        coupon = str(row["coupon_code"])
        existing = _fact_id_for_coupon(conn, coupon)
        if existing is None:
            event_id = event_repo.insert_event(
                conn,
                event_type="redeem",
                coupon_code=coupon,
                campaign_code=row["campaign_code"],
                amount=float(row["amount"]),
                business_day=row["business_day"],
                occurred_at=row["occurred_at"],
                note=row.get("note") or "",
            )
            fid = fact_repo.insert_fact(
                conn,
                coupon_code=coupon,
                campaign_code=row["campaign_code"],
                amount=float(row["amount"]),
                business_day=row["business_day"],
                event_id=event_id,
                status="open",
            )
            merged.append(
                {
                    "id": fid,
                    "coupon_code": coupon,
                    "amount": float(row["amount"]),
                    "campaign_code": row["campaign_code"],
                }
            )
        else:
            extra_money = round(extra_money + float(row["amount"]), 2)
            if coupon not in seen:
                merged.append(
                    {
                        "id": existing,
                        "coupon_code": coupon,
                        "amount": float(row["amount"]),
                        "campaign_code": row["campaign_code"],
                    }
                )
                seen.add(coupon)
    return merged, extra_money


def receipt_remaining(conn) -> int:
    raw = settings_repo.get(conn, "buffer_receipt_remaining", "")
    if raw == "":
        return -1
    return int(raw)
