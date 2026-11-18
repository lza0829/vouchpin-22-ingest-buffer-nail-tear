"""核销缓冲队列服务。

写入侧（event_service）把核销先 enqueue 到 redeem_buffer；本服务负责把缓冲行
flush 进 coupon_events + redeem_facts。冲刷与钉扎共用一把进程级互斥锁，保证
同一业务日「缓冲 → 事件/事实 → 钉批」不会并发交叉；SQLite BEGIN IMMEDIATE
再提供跨进程的写互斥。
"""
from __future__ import annotations
import hashlib
import logging
import threading
from typing import Any

from app import config
from app.db import connect
from app.repositories import buffer as buffer_repo
from app.repositories import events as event_repo
from app.repositories import facts as fact_repo

logger = logging.getLogger("vouchpin.buffer")

# 全局互斥：flush（手动/后台）与 seal（钉扎）串行，只贯彻一种钉前冲刷策略。
ingest_lock = threading.RLock()

_FINGERPRINT_FIELDS = (
    "id",
    "coupon_code",
    "campaign_code",
    "amount",
    "business_day",
    "occurred_at",
    "flush_status",
)


def buffer_fingerprint(rows: list[dict[str, Any]]) -> str:
    """对缓冲残留做稳定指纹；空缓冲为 sha256 空串摘要。"""
    digest = hashlib.sha256()
    for row in rows:
        line = "|".join(str(row[key]) for key in _FINGERPRINT_FIELDS)
        digest.update(line.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def buffer_state(conn, business_day: str) -> dict[str, Any]:
    rows = buffer_repo.pending_rows(conn, business_day)
    total = round(sum(float(r["amount"]) for r in rows), 2)
    return {
        "remaining": len(rows),
        "buffer_amount": total,
        "fingerprint": buffer_fingerprint(rows),
        "items": rows,
    }


def enqueue_redeem(conn, *, coupon_code: str, campaign_code: str, amount: float,
                   business_day: str, occurred_at: str, note: str = "") -> int:
    return buffer_repo.enqueue(
        conn,
        coupon_code=coupon_code,
        campaign_code=campaign_code,
        amount=amount,
        business_day=business_day,
        occurred_at=occurred_at,
        note=note,
    )


def flush_day(conn, business_day: str) -> dict[str, Any]:
    """把一个业务日的缓冲逐行落库，回执与事实同源。

    每行一个 SAVEPOINT：成功则写事件+事实并删缓冲行；失败（如券码重复核销，
    redeem_facts.coupon_code UNIQUE 拒绝二次落入）则回滚该行、标记 failed 并
    保留在缓冲里等待人工处理，绝不静默丢弃，也绝不把未落库的行当成事实。
    回执的 flushed/remaining 只来自真实落库与真实残留，调用方必须已持有
    ingest_lock 并打开写事务。
    """
    rows = buffer_repo.pending_rows(conn, business_day)
    flushed_ids: list[int] = []
    failed: list[dict[str, Any]] = []

    for row in rows:
        buffer_repo.reset_retry(conn, row["id"])
        savepoint = f"sp_buffer_{row['id']}"
        conn.execute(f"SAVEPOINT {savepoint}")
        try:
            event_id = event_repo.insert_event(
                conn,
                event_type="redeem",
                coupon_code=row["coupon_code"],
                campaign_code=row["campaign_code"],
                amount=float(row["amount"]),
                business_day=row["business_day"],
                occurred_at=row["occurred_at"],
                note=row["note"],
            )
            fact_repo.insert_fact(
                conn,
                coupon_code=row["coupon_code"],
                campaign_code=row["campaign_code"],
                amount=float(row["amount"]),
                business_day=row["business_day"],
                event_id=event_id,
                status="open",
            )
        except Exception as exc:  # 单行失败不拖垮整批
            conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
            conn.execute(f"RELEASE SAVEPOINT {savepoint}")
            buffer_repo.mark_failed(conn, row["id"], str(exc))
            failed.append({"buffer_id": row["id"], "error": str(exc)})
        else:
            conn.execute(f"RELEASE SAVEPOINT {savepoint}")
            buffer_repo.delete(conn, row["id"])
            flushed_ids.append(row["id"])

    remaining = buffer_repo.remaining_count(conn, business_day)
    return {
        "business_day": business_day,
        "flushed": len(flushed_ids),
        "flushed_ids": flushed_ids,
        "failed": failed,
        "remaining": remaining,
    }


def flush(business_day: str | None = None) -> dict[str, Any]:
    """手动/后台冲刷入口：全程持全局互斥锁，与钉扎严格串行。"""
    with ingest_lock:
        conn = connect(immediate=True)
        try:
            if business_day is not None:
                summaries = [flush_day(conn, business_day)]
            else:
                summaries = [flush_day(conn, day) for day in buffer_repo.distinct_days(conn)]
            conn.commit()
            return {
                "days": summaries,
                "flushed": sum(s["flushed"] for s in summaries),
                "failed": sum(len(s["failed"]) for s in summaries),
                "remaining": sum(s["remaining"] for s in summaries),
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def flush_all() -> dict[str, Any]:
    """后台工作线程入口：冲刷所有有残留的业务日。"""
    return flush(None)


class FlushWorker:
    """守护线程：按固定间隔把缓冲异步落事件/事实。"""

    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not config.BUFFER_AUTO_FLUSH:
            logger.info("缓冲自动冲刷已关闭 (BUFFER_AUTO_FLUSH=0)")
            return
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="redeem-buffer-flush", daemon=True)
        self._thread.start()
        logger.info(
            "缓冲自动冲刷已启动，间隔 %s 秒", config.BUFFER_FLUSH_INTERVAL_SEC
        )

    def _run(self) -> None:
        while not self._stop.wait(config.BUFFER_FLUSH_INTERVAL_SEC):
            try:
                flush_all()
            except Exception:
                logger.exception("缓冲自动冲刷失败，残留留待下轮重试")

    def stop(self) -> None:
        self._stop.set()


worker = FlushWorker()
