"""并发与后台异步冲刷保障。"""
from __future__ import annotations
import os
import sys
import tempfile
import threading

from conftest import redeem, set_policy  # noqa: F401

DAY = "2030-03-08"


def _fresh_app(tmp_path: str, auto_flush: str, interval: str = "0.2"):
    os.environ["DATA_DIR"] = tmp_path
    os.environ["BUFFER_AUTO_FLUSH"] = auto_flush
    os.environ["BUFFER_FLUSH_INTERVAL_SEC"] = interval
    for name in list(sys.modules):
        if name == "app" or name.startswith("app."):
            del sys.modules[name]
    from app.main import app  # noqa: F401
    from app.services import buffer_service
    from app.repositories import facts, buffer as buffer_repo
    from app.db import connect
    return buffer_service, facts, buffer_repo, connect


def test_concurrent_seal_and_flush_single_batch_no_duplicate_facts(client):
    """多线程同时钉扎/冲刷同一业务日：只能产出一个 sealed 批，事实不重复。"""
    set_policy(client, "flush_before_seal")
    for i in range(20):
        redeem(client, f"C-C{i:02d}", day=DAY, amount=1)

    from app.services import redeem_service, buffer_service

    errors: list[Exception] = []
    barrier = threading.Barrier(4)

    def worker_seal():
        barrier.wait()
        try:
            redeem_service.seal({"business_day": DAY})
        except Exception as exc:  # 409 是预期：只允许一个 sealed 批
            errors.append(exc)

    def worker_flush():
        barrier.wait()
        try:
            buffer_service.flush(DAY)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker_seal) for _ in range(3)]
    threads.append(threading.Thread(target=worker_flush))
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # 唯一 sealed 批
    batches = client.get("/api/batches").json()
    sealed = [b for b in batches if b["business_day"] == DAY and b["status"] == "sealed"]
    assert len(sealed) == 1
    # 全部 20 笔恰好各一条事实，没有重复纳入
    facts = client.get(f"/api/facts?business_day={DAY}").json()
    assert len(facts) == 20
    assert len({f["coupon_code"] for f in facts}) == 20
    assert all(f["status"] == "sealed" and f["batch_id"] == sealed[0]["id"] for f in facts)
    assert client.get(f"/api/redeem/buffer?business_day={DAY}").json()["remaining"] == 0
    # 其余 seal 线程拿到 409，而不是悄悄建第二个批
    from fastapi import HTTPException
    assert errors and all(isinstance(e, HTTPException) and e.status_code == 409 for e in errors)


def test_auto_flush_worker_drains_buffer_async():
    tmp = tempfile.TemporaryDirectory()
    try:
        buffer_service, facts, buffer_repo, connect = _fresh_app(tmp.name, "1", "0.1")
        from fastapi.testclient import TestClient
        from app.main import app

        with TestClient(app) as c:
            assert buffer_service.worker._thread is not None
            for i in range(5):
                redeem(c, f"C-W{i:02d}", day=DAY, amount=2)
            # 不手动 flush，等后台线程异步落库
            deadline_passed = False
            for _ in range(100):
                remaining = c.get(f"/api/redeem/buffer?business_day={DAY}").json()["remaining"]
                if remaining == 0:
                    break
                threading.Event().wait(0.05)
            else:
                deadline_passed = True
            assert not deadline_passed
            rows = facts.list_facts(connect(), DAY)
            assert len(rows) == 5 and all(f["status"] == "open" for f in rows)
    finally:
        buffer_service.worker.stop()
        tmp.cleanup()
