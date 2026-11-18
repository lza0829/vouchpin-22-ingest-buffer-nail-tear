"""端到端核对：核销先进缓冲，再钉扎，校验两种互斥的钉前冲刷策略。

共同不变量（两种策略都必须成立）：
- 钉扎明细只来自已落库的 open 事实；
- 仍在 redeem_buffer、未落库的核销绝不出现在 sealed 批次明细里；
- 同一业务日只允许一个 sealed 批。
"""
from conftest import redeem, set_policy  # noqa: F401

# 与 seed 的“今天/昨天”错开，保证该日只有本测试写入的数据。
DAY = "2030-03-07"


# ---------------------------------------------------------------- flush_before_seal

def test_policy_a_flush_before_seal_drains_buffer_then_seals(client):
    set_policy(client, "flush_before_seal")
    redeem(client, "T-A1", day=DAY, amount=10)
    redeem(client, "T-A2", day=DAY, amount=20)

    # 钉前：两行都还在缓冲，事件/事实表里没有这两个核销
    buf = client.get(f"/api/redeem/buffer?business_day={DAY}").json()
    assert buf["remaining"] == 2 and buf["buffer_amount"] == 30.0
    preview = client.get(f"/api/redeem/preview?business_day={DAY}").json()
    assert preview["open_count"] == 0
    assert preview["buffer"]["remaining"] == 2

    r = client.post("/api/redeem/seal", json={"business_day": DAY})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["fact_count"] == 2 and out["total_amount"] == 30.0
    assert out["flush_policy"] == "flush_before_seal"
    assert out["flushed"]["flushed"] == 2 and out["flushed"]["remaining"] == 0
    # 强制冲刷后缓冲残留必须为 0
    assert out["buffer_remaining"] == 0 and out["buffer_amount"] == 0

    buf_after = client.get(f"/api/redeem/buffer?business_day={DAY}").json()
    assert buf_after["remaining"] == 0
    facts = client.get(f"/api/facts?business_day={DAY}").json()
    assert {f["coupon_code"] for f in facts} == {"T-A1", "T-A2"}
    assert all(f["status"] == "sealed" for f in facts)
    events = client.get(f"/api/events?business_day={DAY}").json()
    assert {e["coupon_code"] for e in events if e["event_type"] == "redeem"} == {"T-A1", "T-A2"}

    detail = client.get(f"/api/batches/{out['batch_id']}").json()
    assert {f["coupon_code"] for f in detail["facts"]} == {"T-A1", "T-A2"}
    assert detail["buffer_remaining"] == 0


def test_policy_a_flush_failure_rejects_seal_and_keeps_buffer(client):
    set_policy(client, "flush_before_seal")
    redeem(client, "T-DUP", day=DAY, amount=10)
    # 先手动冲刷让 T-DUP 落库
    fr = client.post("/api/redeem/flush", json={"business_day": DAY})
    assert fr.status_code == 200 and fr.json()["remaining"] == 0
    # 同券码再入缓冲；flush 时会因 coupon_code UNIQUE 失败
    redeem(client, "T-DUP", day=DAY, amount=10)

    r = client.post("/api/redeem/seal", json={"business_day": DAY})
    assert r.status_code == 409
    assert "冲刷" in r.json()["detail"]

    # 拒钉后缓冲原样保留，未产生第二个批次，已落库事实仍为 open（钉扎整体回滚）
    buf = client.get(f"/api/redeem/buffer?business_day={DAY}").json()
    assert buf["remaining"] == 1
    row = buf["items"][0]
    assert row["flush_status"] == "failed" and row["flush_error"]
    batches = client.get("/api/batches").json()
    assert all(b["business_day"] != DAY or b["status"] != "sealed" for b in batches)
    facts = client.get(f"/api/facts?business_day={DAY}").json()
    assert all(f["status"] == "open" for f in facts)

    # 修复后（缓冲失败行无法再落库 → 移除脏行场景由人工处理；这里验证再次 flush 仍可被重试）
    # 改为另一张新券码：直接验证成功路径需要先清掉失败行，故只确认 failed 持续可见
    preview = client.get(f"/api/redeem/preview?business_day={DAY}").json()
    assert preview["buffer"]["remaining"] == 1
    assert preview["facts"] and all(f["coupon_code"] != "T-DUP" or f["status"] == "open"
                                    for f in preview["facts"])


def test_policy_a_no_open_facts_after_clean_flush_is_400(client):
    set_policy(client, "flush_before_seal")
    r = client.post("/api/redeem/seal", json={"business_day": "2026-11-19"})
    assert r.status_code == 400


# ------------------------------------------------------- seal_with_dirty_buffer

def test_policy_b_seal_with_dirty_buffer_snapshots_and_excludes_buffer(client):
    set_policy(client, "seal_with_dirty_buffer")
    # 先落库两条（手动 flush），再留两条在缓冲
    redeem(client, "T-P1", day=DAY, amount=10)
    redeem(client, "T-P2", day=DAY, amount=20)
    fr = client.post("/api/redeem/flush", json={"business_day": DAY})
    assert fr.json()["remaining"] == 0
    redeem(client, "T-B1", day=DAY, amount=5)
    redeem(client, "T-B2", day=DAY, amount=7)

    preview = client.get(f"/api/redeem/preview?business_day={DAY}").json()
    assert preview["open_count"] == 2
    assert preview["buffer"]["remaining"] == 2
    expected_fp = preview["buffer"]["fingerprint"]
    assert expected_fp and len(expected_fp) == 64

    r = client.post("/api/redeem/seal", json={"business_day": DAY})
    assert r.status_code == 200, r.text
    out = r.json()
    # 本批只钉已落库 open 事实
    assert out["fact_count"] == 2 and out["total_amount"] == 30.0
    # 批次快照了 buffer_remaining 与指纹
    assert out["buffer_remaining"] == 2 and out["buffer_amount"] == 12.0
    assert out["buffer_fingerprint"] == expected_fp

    # 缓冲原样保留、未被 flush
    buf = client.get(f"/api/redeem/buffer?business_day={DAY}").json()
    assert {i["coupon_code"] for i in buf["items"]} == {"T-B1", "T-B2"}

    # 关键不变量：sealed 明细里绝不能出现仍在缓冲的券码
    detail = client.get(f"/api/batches/{out['batch_id']}").json()
    sealed_codes = {f["coupon_code"] for f in detail["facts"]}
    assert sealed_codes == {"T-P1", "T-P2"}
    assert sealed_codes.isdisjoint({"T-B1", "T-B2"})
    assert detail["buffer_fingerprint"] == expected_fp

    # 总览必须显示未冲刷缓冲
    dash = client.get("/api/dashboard").json()
    # dashboard 默认看 settings 里的 business_day，切到 DAY 再查
    client.put("/api/settings/day", json={"business_day": DAY})
    dash = client.get("/api/dashboard").json()
    assert dash["buffer_count"] == 2
    assert dash["buffer_amount"] == 12.0
    assert dash["day_sealed"] is True
    assert dash["seal_flush_policy"] == "seal_with_dirty_buffer"


def test_policy_b_dirty_buffer_with_no_open_facts_is_400(client):
    set_policy(client, "seal_with_dirty_buffer")
    redeem(client, "T-ONLY-BUF", day=DAY, amount=9)
    r = client.post("/api/redeem/seal", json={"business_day": DAY})
    assert r.status_code == 400
    # 缓冲没有被偷偷落库
    buf = client.get(f"/api/redeem/buffer?business_day={DAY}").json()
    assert buf["remaining"] == 1
    facts = client.get(f"/api/facts?business_day={DAY}").json()
    assert facts == []


def test_policy_b_buffer_flushed_after_seal_stays_open_not_resealed(client):
    set_policy(client, "seal_with_dirty_buffer")
    redeem(client, "T-K1", day=DAY, amount=10)
    client.post("/api/redeem/flush", json={"business_day": DAY})
    redeem(client, "T-K2", day=DAY, amount=8)
    sealed = client.post("/api/redeem/seal", json={"business_day": DAY}).json()
    assert sealed["buffer_remaining"] == 1

    # 钉扎后把残留缓冲冲刷入湖：成为新的 open 事实，不会混进旧 sealed 批
    fr = client.post("/api/redeem/flush", json={"business_day": DAY}).json()
    assert fr["remaining"] == 0 and fr["flushed"] == 1
    detail = client.get(f"/api/batches/{sealed['batch_id']}").json()
    assert {f["coupon_code"] for f in detail["facts"]} == {"T-K1"}
    facts = client.get(f"/api/facts?business_day={DAY}").json()
    late = next(f for f in facts if f["coupon_code"] == "T-K2")
    assert late["status"] == "open" and late["batch_id"] is None
    # 同日不允许再开第二个 sealed 批
    again = client.post("/api/redeem/seal", json={"business_day": DAY})
    assert again.status_code == 409


# --------------------------------------------------------------- 策略互斥与守卫

def test_policy_is_global_mutex_unknown_value_rejected(client):
    r = client.put("/api/settings/seal-policy", json={"policy": "both"})
    assert r.status_code == 400
    cur = client.get("/api/settings/seal-policy").json()
    assert cur["policy"] == "flush_before_seal"  # 默认策略
    assert len(cur["options"]) == 2


def test_sealed_day_rejects_new_redeem_enqueue(client):
    set_policy(client, "flush_before_seal")
    redeem(client, "T-S1", day=DAY, amount=10)
    client.post("/api/redeem/seal", json={"business_day": DAY})
    r = client.post("/api/events", json={
        "event_type": "redeem", "coupon_code": "T-S2", "campaign_code": "NEW10",
        "business_day": DAY,
    })
    assert r.status_code == 409
