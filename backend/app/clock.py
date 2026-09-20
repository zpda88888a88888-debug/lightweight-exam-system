"""可注入时钟。

规格依据：测试方案 5「时间相关测试使用可注入的时钟，不依赖系统真实时间」
         与风险 R5「禁止 datetime.now() 直接出现在被测逻辑中」。

被测逻辑一律通过 Clock 取时间，测试可替换为 FrozenClock 精确控制边界时刻。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

#: 基准时区：所有时间以 naive UTC 存储与比较，避免 SQLite 时区歧义
UTC = timezone.utc


def utcnow_naive() -> datetime:
    """当前 UTC 时间（naive，微秒截断到秒以下保留，便于相等比较）。"""
    return datetime.now(UTC).replace(tzinfo=None)


class Clock(Protocol):
    """时钟协议。"""

    def now(self) -> datetime:  # pragma: no cover - 协议声明
        ...


class SystemClock:
    """生产用时钟。"""

    def now(self) -> datetime:
        return utcnow_naive()


class FrozenClock:
    """测试用固定时钟。"""

    def __init__(self, moment: datetime) -> None:
        self._moment = moment

    def now(self) -> datetime:
        return self._moment

    def set(self, moment: datetime) -> None:
        self._moment = moment
