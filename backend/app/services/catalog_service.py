from __future__ import annotations
from typing import Any

from app.db import connect
from app.repositories import settings as settings_repo
from app.repositories import facts as fact_repo
from app.repositories import batches as batch_repo
from app.repositories import events as event_repo
from app.repositories import buffer as buffer_repo
from app.services import buffer_service
from app.services import seal_policy


def dashboard() -> dict[str, Any]:
    conn = connect()
    try:
        day = settings_repo.get(conn, "business_day")
        facts = fact_repo.list_facts(conn, day)
        open_n = sum(1 for f in facts if f["status"] == "open")
        sealed_n = sum(1 for f in facts if f["status"] == "sealed")
        total = round(sum(float(f["amount"]) for f in facts), 2)
        events = event_repo.list_events(conn, day)
        batches = batch_repo.list_batches(conn)
        sealed_today = fact_repo.day_is_sealed(conn, day)

        # 未冲刷缓冲必须在总览显式可见，避免把缓冲里的核销误当成已入湖事实。
        buffered = buffer_repo.list_buffer(conn, business_day=day)
        buffered_total = round(sum(float(r["amount"]) for r in buffered), 2)
        buffered_failed = sum(1 for r in buffered if r["flush_status"] == "failed")
        from app.services import ingest_shadow
        receipt_remaining = ingest_shadow.receipt_remaining(conn)
        if receipt_remaining >= 0:
            buffered = []
            buffered_total = 0.0
            buffered_failed = 0
        policy = settings_repo.get(conn, seal_policy.SETTING_KEY, seal_policy.DEFAULT_POLICY)
        try:
            policy = seal_policy.normalize(policy)
        except ValueError:
            policy = seal_policy.DEFAULT_POLICY

        return {
            "business_day": day,
            "event_count": len(events),
            "fact_count": len(facts),
            "open_fact_count": open_n,
            "sealed_fact_count": sealed_n,
            "redeem_total_today": total,
            "batch_count": len(batches),
            "day_sealed": sealed_today,
            "buffer_count": len(buffered),
            "buffer_pending_count": len(buffered) - buffered_failed,
            "buffer_failed_count": buffered_failed,
            "buffer_amount": buffered_total,
            "seal_flush_policy": policy,
        }
    finally:
        conn.close()


def buffer_snapshot(business_day: str | None = None) -> dict[str, Any]:
    conn = connect()
    try:
        day = business_day or settings_repo.get(conn, "business_day")
        rows = buffer_repo.list_buffer(conn, business_day=day)
        return {
            "business_day": day,
            "remaining": len(rows),
            "buffer_amount": round(sum(float(r["amount"]) for r in rows), 2),
            "fingerprint": buffer_service.buffer_fingerprint(rows),
            "items": rows,
        }
    finally:
        conn.close()
