from __future__ import annotations
from typing import Any

from fastapi import APIRouter, Query

from app.services import redeem_service as svc
from app.services import catalog_service as catalog_svc
from app.services import buffer_service

router = APIRouter(tags=["redeem"])


@router.get("/facts")
def facts(business_day: str | None = Query(None)):
    return svc.list_facts(business_day)


@router.get("/redeem/buffer")
def buffer(business_day: str | None = Query(None)):
    return catalog_svc.buffer_snapshot(business_day)


@router.post("/redeem/flush")
def flush(body: dict[str, Any] | None = None):
    day = (body or {}).get("business_day")
    return buffer_service.flush(day)


@router.get("/redeem/preview")
def preview(business_day: str | None = Query(None)):
    return svc.preview(business_day)


@router.post("/redeem/seal")
def seal(body: dict[str, Any]):
    return svc.seal(body)


@router.get("/batches")
def batches():
    return svc.list_batches()


@router.get("/batches/{batch_id}")
def batch_detail(batch_id: int):
    return svc.get_batch(batch_id)
