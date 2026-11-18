# Vouchpin（券钉簿）

骨架：券事件入湖 → 核销先入**缓冲队列** → 冲刷落事件/核销事实 → 钉扎批次（带缓冲快照）→ 过期/退回窗（后挖）→ 批次互证。

## 核销缓冲与钉前冲刷

核销（redeem）写入不再直落事实，而是先进 `redeem_buffer` 缓冲表，由三条路径冲刷进
`coupon_events` + `redeem_facts`：

- 后台守护线程按 `BUFFER_FLUSH_INTERVAL_SEC` 间隔自动冲刷（`BUFFER_AUTO_FLUSH=0` 可关）；
- 手动 `POST /api/redeem/flush`；
- 钉扎时按策略冲刷（见下）。

每行冲刷在独立 SAVEPOINT 内进行：成功则删缓冲行；失败（如券码重复核销）则把该行标记
`failed` 并保留在缓冲、记录 `flush_error`，绝不静默丢弃，也绝不把未落库内容当成事实。

### 钉前冲刷策略（全局互斥，二选一，存于 settings.seal_flush_policy）

设置页或 `PUT /api/settings/seal-policy` 切换，非法值返回 400；钉扎代码只按这一个开关分叉：

| 策略 | 钉扎行为 |
| --- | --- |
| `flush_before_seal`（默认，钉前强制冲刷） | 钉扎开始先 flush 该业务日缓冲至事件与事实；冲刷后缓冲残留必须为 0，否则拒钉（409）；批次明细只来自冲刷后的 open 事实 |
| `seal_with_dirty_buffer`（允许带脏缓冲钉扎） | 不强制 flush；本批只钉已落库 open 事实；批次快照 `buffer_remaining` / `buffer_amount` / `buffer_fingerprint`；总览显示未冲刷缓冲；仍在缓冲、未落库的核销禁止写入 sealed 明细 |

共同不变量：sealed 明细唯一来源是已落库的 open 事实；缓冲内容在任何策略下都不会被直接
写进 sealed 冒充已入库。flush 与 seal 共用进程级 `ingest_lock` 互斥，SQLite
`BEGIN IMMEDIATE` 再提供跨进程写互斥，避免批不全或重复纳入。

## 主要接口

- `POST /api/events`：redeem 返回 `buffered:true + buffer_id`；issue/void 直写事件
- `GET /api/redeem/buffer?business_day=`：缓冲残留（含指纹）
- `POST /api/redeem/flush`：手动冲刷
- `GET /api/redeem/preview`：open 事实与缓冲分块预览
- `POST /api/redeem/seal`：钉扎，返回批次及缓冲快照
- `GET /api/batches` / `GET /api/batches/{id}`：批次列表（含快照列）/ 批次 sealed 明细
- `GET|PUT /api/settings/seal-policy`：读取/切换全局互斥策略

## 本地运行

- API: `cd backend && python -m uvicorn app.main:app --port 10800`
- Web: `cd frontend && npm install && npm run dev`（5800）
- 测试: `cd backend && pip install -r requirements-dev.txt && pytest`（测试自动关闭自动冲刷）
- 环境变量：`DATA_DIR`、`BUFFER_AUTO_FLUSH`（默认 1）、`BUFFER_FLUSH_INTERVAL_SEC`（默认 5）
