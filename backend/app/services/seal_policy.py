"""钉前缓冲冲刷的全局互斥策略。

只允许两个互斥取值，钉扎（seal）按此唯一开关分叉，不允许两条路径并存：

- FLUSH_BEFORE_SEAL（钉前强制冲刷，默认）：
  钉扎开始必须先把该业务日缓冲全部 flush 到事件与事实；冲刷后缓冲残留必须为 0，
  否则拒钉；批次明细只来自冲刷后仍为 open 的落库事实。
- SEAL_WITH_DIRTY_BUFFER（允许带脏缓冲钉扎）：
  不强制 flush；本批只钉已落库的 open 事实；批次必须快照 buffer_remaining 与指纹；
  仍在缓冲、未落库的核销一律不得写进 sealed 明细。
"""
from __future__ import annotations

FLUSH_BEFORE_SEAL = "flush_before_seal"
SEAL_WITH_DIRTY_BUFFER = "seal_with_dirty_buffer"

POLICIES = (FLUSH_BEFORE_SEAL, SEAL_WITH_DIRTY_BUFFER)
DEFAULT_POLICY = FLUSH_BEFORE_SEAL

POLICY_LABELS = {
    FLUSH_BEFORE_SEAL: "钉前强制冲刷",
    SEAL_WITH_DIRTY_BUFFER: "允许带脏缓冲钉扎",
}

SETTING_KEY = "seal_flush_policy"


def normalize(value: str | None) -> str:
    """校验策略取值，非法值直接抛 ValueError（由上层转 400）。"""
    if value not in POLICIES:
        raise ValueError(f"未知钉扎冲刷策略: {value!r}，仅支持 {POLICIES}")
    return value
