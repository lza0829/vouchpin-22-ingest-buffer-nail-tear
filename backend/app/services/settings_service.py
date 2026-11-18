from __future__ import annotations
from typing import Any

from fastapi import HTTPException

from app.db import connect
from app.repositories import settings as settings_repo
from app.services import seal_policy


def get_day() -> dict[str, Any]:
    conn = connect()
    try:
        return {"business_day": settings_repo.get(conn, "business_day")}
    finally:
        conn.close()


def set_day(body: dict[str, Any]) -> dict[str, Any]:
    day = (body.get("business_day") or "").strip()
    if len(day) != 10:
        raise HTTPException(400, "business_day 格式 YYYY-MM-DD")
    conn = connect(immediate=True)
    try:
        settings_repo.set_(conn, "business_day", day)
        conn.commit()
        return {"business_day": day}
    finally:
        conn.close()


def get_seal_policy() -> dict[str, Any]:
    conn = connect()
    try:
        value = settings_repo.get(conn, seal_policy.SETTING_KEY, seal_policy.DEFAULT_POLICY)
        try:
            value = seal_policy.normalize(value)
        except ValueError as exc:
            raise HTTPException(500, str(exc)) from exc
        return {
            "key": seal_policy.SETTING_KEY,
            "policy": value,
            "label": seal_policy.POLICY_LABELS[value],
            "options": [
                {"policy": p, "label": seal_policy.POLICY_LABELS[p]} for p in seal_policy.POLICIES
            ],
        }
    finally:
        conn.close()


def set_seal_policy(body: dict[str, Any]) -> dict[str, Any]:
    raw = (body.get("policy") or "").strip()
    try:
        policy = seal_policy.normalize(raw)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    conn = connect(immediate=True)
    try:
        settings_repo.set_(conn, seal_policy.SETTING_KEY, policy)
        conn.commit()
        return {
            "key": seal_policy.SETTING_KEY,
            "policy": policy,
            "label": seal_policy.POLICY_LABELS[policy],
        }
    finally:
        conn.close()
