"""核销钉扎服务。

钉扎与缓冲冲刷共用 buffer_service.ingest_lock 全局互斥。钉前如何对待缓冲只由
settings.seal_flush_policy 一个开关决定，两条路径互斥、不可同时生效：

* flush_before_seal：钉前强制 flush 该业务日缓冲；flush 后缓冲残留必须为 0，
  否则拒钉（409，已成功的冲刷合法入湖、失败行保留 failed 标记，不创建批次）；
  批次明细只取冲刷后的 open 事实。
* seal_with_dirty_buffer：不 flush；本批只钉已落库 open 事实；批次快照
  buffer_remaining / buffer_amount / buffer_fingerprint；缓冲中的核销绝不出现在
  sealed 明细里。
"""
from __future__ import annotations
from datetime import datetime
from typing import Any

from fastapi import HTTPException

from app.db import connect
from app.repositories import settings as settings_repo
from app.repositories import facts as fact_repo
from app.repositories import batches as batch_repo
from app.services import buffer_service
from app.services import seal_policy


def get_policy(conn) -> str:
    raw = settings_repo.get(conn, seal_policy.SETTING_KEY, seal_policy.DEFAULT_POLICY)
    try:
        return seal_policy.normalize(raw)
    except ValueError as exc:
        raise HTTPException(500, str(exc)) from exc


def list_facts(business_day: str | None = None) -> list[dict[str, Any]]:
    conn = connect()
    try:
        day = business_day or settings_repo.get(conn, "business_day")
        return fact_repo.list_facts(conn, day)
    finally:
        conn.close()


def preview(business_day: str | None = None) -> dict[str, Any]:
    # 只读路径：open 事实永远只来自已落库事实，缓冲单独成块展示，不混入事实。
    conn = connect()
    try:
        day = business_day or settings_repo.get(conn, "business_day")
        opens = fact_repo.open_facts_for_day(conn, day)
        state = buffer_service.buffer_state(conn, day)
        return {
            "business_day": day,
            "flush_policy": get_policy(conn),
            "open_count": len(opens),
            "open_total": round(sum(float(f["amount"]) for f in opens), 2),
            "already_sealed": fact_repo.day_is_sealed(conn, day),
            "facts": opens,
            "buffer": {
                "remaining": state["remaining"],
                "buffer_amount": state["buffer_amount"],
                "fingerprint": state["fingerprint"],
                "items": state["items"],
            },
        }
    finally:
        conn.close()


def seal(body: dict[str, Any]) -> dict[str, Any]:
    # 钉扎与冲刷共用同一把全局互斥锁：整个「钉前冲刷 → 取 open 事实 → 建批 →
    # 落状态」临界区串行执行，杜绝冲刷与钉扎交错造成半截落库、双计。
    with buffer_service.ingest_lock:
        conn = connect(immediate=True)
        transaction_open = True
        try:
            day = body.get("business_day") or settings_repo.get(conn, "business_day")
            if fact_repo.day_is_sealed(conn, day):
                raise HTTPException(409, f"业务日 {day} 已有 sealed 钉扎批")

            policy = get_policy(conn)
            flushed_summary = None

            if policy == seal_policy.FLUSH_BEFORE_SEAL:
                # 路径一：钉前强制冲刷，冲刷失败则拒钉，缓冲残留必须为 0。
                # flush_day 内部对每行用 SAVEPOINT 隔离：失败行的插入已单独撤回、
                # 缓冲行保留并标记 failed；成功行合法入湖。拒钉时提交这些冲刷结果，
                # 不创建批次、不动事实状态，错误标记也能留下供人工排查。
                flushed_summary = buffer_service.flush_day(conn, day)
                if flushed_summary["remaining"] != 0:
                    conn.commit()
                    transaction_open = False
                    raise HTTPException(
                        409,
                        "钉前缓冲冲刷未完成，已拒钉："
                        f"残留 {flushed_summary['remaining']} 行 "
                        f"(失败明细 {flushed_summary['failed']})",
                    )
                state = buffer_service.buffer_state(conn, day)
                assert state["remaining"] == 0
                snapshot = {
                    "buffer_remaining": 0,
                    "buffer_amount": 0.0,
                    "buffer_fingerprint": state["fingerprint"],
                }
            elif policy == seal_policy.SEAL_WITH_DIRTY_BUFFER:
                # 路径二：不 flush；只快照缓冲残留，明细只从已落库 open 事实取。
                state = buffer_service.buffer_state(conn, day)
                snapshot = {
                    "buffer_remaining": state["remaining"],
                    "buffer_amount": state["buffer_amount"],
                    "buffer_fingerprint": state["fingerprint"],
                }
            else:  # pragma: no cover - normalize 已兜底
                raise HTTPException(500, f"未知钉扎冲刷策略: {policy}")

            # 批次明细唯一来源：已落库且仍为 open 的事实。缓冲行在任何策略下
            # 都不会出现在这里。
            opens = fact_repo.open_facts_for_day(conn, day)
            if not opens:
                raise HTTPException(400, "无可钉扎的 open 核销事实（缓冲未落库内容不可入批）")
            total = round(sum(float(f["amount"]) for f in opens), 2)
            bid = batch_repo.create_batch(
                conn,
                business_day=day,
                status="sealed",
                fact_count=len(opens),
                total_amount=total,
                sealed_at=datetime.now().replace(microsecond=0).isoformat(),
                note=body.get("note") or "",
                **snapshot,
            )
            fact_repo.mark_batched(conn, [int(f["id"]) for f in opens], bid)
            conn.commit()
            transaction_open = False

            result = {
                "batch_id": bid,
                "business_day": day,
                "fact_count": len(opens),
                "total_amount": total,
                "status": "sealed",
                "flush_policy": policy,
                "buffer_remaining": snapshot["buffer_remaining"],
                "buffer_amount": snapshot["buffer_amount"],
                "buffer_fingerprint": snapshot["buffer_fingerprint"],
            }
            if flushed_summary is not None:
                result["flushed"] = flushed_summary
            return result
        except HTTPException:
            if transaction_open:
                conn.rollback()
            raise
        except Exception:
            if transaction_open:
                conn.rollback()
            raise
        finally:
            conn.close()


def list_batches() -> list[dict[str, Any]]:
    conn = connect()
    try:
        return batch_repo.list_batches(conn)
    finally:
        conn.close()


def get_batch(batch_id: int) -> dict[str, Any]:
    conn = connect()
    try:
        batch = batch_repo.get_batch(conn, batch_id)
        if batch is None:
            raise HTTPException(404, f"批次 {batch_id} 不存在")
        # 明细只回传真正写入 sealed 批的落库事实，缓冲内容永不出现。
        batch["facts"] = fact_repo.facts_for_batch(conn, batch_id)
        return batch
    finally:
        conn.close()
