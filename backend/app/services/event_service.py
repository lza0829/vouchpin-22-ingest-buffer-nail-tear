from __future__ import annotations
from datetime import datetime
from typing import Any

from fastapi import HTTPException

from app.db import connect
from app.repositories import settings as settings_repo
from app.repositories import events as event_repo
from app.repositories import facts as fact_repo
from app.repositories import campaigns as camp_repo
from app.services import buffer_service


def list_campaigns() -> list[dict[str, Any]]:
    conn = connect()
    try:
        return camp_repo.list_all(conn)
    finally:
        conn.close()


def list_events(business_day: str | None = None) -> list[dict[str, Any]]:
    conn = connect()
    try:
        day = business_day or settings_repo.get(conn, "business_day")
        return event_repo.list_events(conn, day)
    finally:
        conn.close()


def add_event(body: dict[str, Any]) -> dict[str, Any]:
    conn = connect(immediate=True)
    try:
        day = body.get("business_day") or settings_repo.get(conn, "business_day")
        et = body.get("event_type")
        if et not in {"issue", "redeem", "void"}:
            raise HTTPException(400, "event_type 须为 issue/redeem/void")
        code = (body.get("coupon_code") or "").strip()
        camp = (body.get("campaign_code") or "").strip()
        if not code or not camp:
            raise HTTPException(400, "coupon_code / campaign_code 必填")
        amount = float(body.get("amount") or 0)
        if et == "redeem" and amount <= 0:
            # 默认取活动面额
            camps = {c["code"]: c for c in camp_repo.list_all(conn)}
            if camp in camps:
                amount = float(camps[camp]["face_value"])
        occurred = body.get("occurred_at") or datetime.now().replace(microsecond=0).isoformat()

        if et == "redeem":
            # 核销先入湖缓冲，由 flush（手动/钉前/后台）再落事件与事实。
            if fact_repo.day_is_sealed(conn, day):
                raise HTTPException(409, f"业务日 {day} 核销已钉扎，禁止再写入核销")
            buffer_id = buffer_service.enqueue_redeem(
                conn,
                coupon_code=code,
                campaign_code=camp,
                amount=amount,
                business_day=day,
                occurred_at=occurred,
                note=body.get("note") or "",
            )
            conn.commit()
            return {
                "event_type": "redeem",
                "buffered": True,
                "buffer_id": buffer_id,
                "event_id": None,
                "fact_id": None,
                "business_day": day,
            }

        # issue / void 不属于核销入湖链路，保持直写事件。
        eid = event_repo.insert_event(
            conn,
            event_type=et,
            coupon_code=code,
            campaign_code=camp,
            amount=amount,
            business_day=day,
            occurred_at=occurred,
            note=body.get("note") or "",
        )
        conn.commit()
        return {"event_type": et, "buffered": False, "event_id": eid, "business_day": day}
    finally:
        conn.close()
