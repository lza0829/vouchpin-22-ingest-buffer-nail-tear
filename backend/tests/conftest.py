from __future__ import annotations
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    """每个测试一个全新临时库，且关闭后台自动冲刷，保证时序确定。"""
    tmp = tempfile.TemporaryDirectory()
    monkeypatch.setenv("DATA_DIR", tmp.name)
    monkeypatch.setenv("BUFFER_AUTO_FLUSH", "0")

    # 确保拿到干净的模块状态（config 在 import 时读环境变量）。
    for name in list(sys.modules):
        if name == "app" or name.startswith("app."):
            del sys.modules[name]

    from app import config  # noqa: F401  触发新 env 下的配置
    from app.main import app
    from app.services.buffer_service import worker

    assert worker._thread is None  # 自动冲刷确实关闭

    with TestClient(app) as c:
        yield c

    worker.stop()
    tmp.cleanup()


def redeem(client, code: str, camp: str = "NEW10", amount: float | None = None,
           day: str | None = None) -> dict:
    body = {"event_type": "redeem", "coupon_code": code, "campaign_code": camp}
    if amount is not None:
        body["amount"] = amount
    if day is not None:
        body["business_day"] = day
    r = client.post("/api/events", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["buffered"] is True
    assert data["event_id"] is None and data["fact_id"] is None
    return data


def set_policy(client, policy: str):
    r = client.put("/api/settings/seal-policy", json={"policy": policy})
    assert r.status_code == 200, r.text
    return r.json()
