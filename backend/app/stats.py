"""统计口径计算（纯函数）：及格线、题目标错率。

规格依据：spec 4.7 / 6.2 / 6.3 / 架构 9.10

口径要点：
    及格率：按得分排名取前 pass_ratio% 为及格，并列同分者全部通过；
            分母为所有有 attempt 的人（缺考不计入）。
    标错率：某题得分 < 满分即算错，未作答也算错；分母同为有 attempt 的人。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

#: 及格比例允许的 9 档
VALID_PASS_RATIOS = tuple(range(10, 100, 10))


@dataclass(frozen=True)
class PassLine:
    """及格线计算结果。"""

    total: int
    """有 attempt 的人数（分母）。"""
    threshold: float | None
    """及格线：降序第 k 名得分；无人时为 None。"""
    pass_count: int
    """及格人数（含并列放宽）。"""

    @property
    def pass_rate(self) -> float:
        """及格率（分母为 0 时返回 0.0）。"""
        return self.pass_count / self.total if self.total else 0.0

    def is_pass(self, score: float) -> bool:
        """判断某个得分是否及格。"""
        return self.threshold is not None and score >= self.threshold


def compute_pass_line(scores: Sequence[float], pass_ratio: int) -> PassLine:
    """计算及格线。

    Args:
        scores: 所有**有 attempt** 的考生得分。缺考者不得传入。
        pass_ratio: 及格比例，取值 10–90（10 的倍数）。

    Returns:
        PassLine。

    Raises:
        ValueError: pass_ratio 不在允许档位内。
    """
    if pass_ratio not in VALID_PASS_RATIOS:
        raise ValueError(
            f"pass_ratio 必须是 {VALID_PASS_RATIOS[0]}–{VALID_PASS_RATIOS[-1]} "
            f"且为 10 的倍数，收到 {pass_ratio!r}"
        )

    total = len(scores)
    if total == 0:
        return PassLine(total=0, threshold=None, pass_count=0)

    # k = ⌈pass_ratio% × 总人数⌉
    k = math.ceil(total * pass_ratio / 100)
    k = max(1, min(k, total))

    ordered = sorted(scores, reverse=True)
    threshold = ordered[k - 1]

    # 并列同分者全部通过：所有 >= 及格线者均及格
    pass_count = sum(1 for s in scores if s >= threshold)

    return PassLine(total=total, threshold=float(threshold), pass_count=pass_count)


def compute_wrong_rates(
    per_question: Mapping[int, Sequence[tuple[float, float]]],
) -> dict[int, float]:
    """计算每题的标错率。

    Args:
        per_question: {question_id: [(earned, full_score), ...]}，
            内层列表必须只包含**有 attempt** 的考生记录；
            未作答以 (0, full_score) 形式计入（未作答算错）。

    Returns:
        {question_id: wrong_rate}，无人作答的题目不出现在结果中。
    """
    rates: dict[int, float] = {}
    for question_id, records in per_question.items():
        if not records:
            continue
        wrong = sum(1 for earned, full_score in records if earned < full_score)
        rates[question_id] = wrong / len(records)
    return rates


def average_score(scores: Iterable[float]) -> float:
    """平均分（分母 = 有 attempt 的人；无人时 0.0）。"""
    values = list(scores)
    return sum(values) / len(values) if values else 0.0


def round_half_up_1(value: float) -> float:
    """保留 1 位小数（四舍五入）。"""
    from decimal import ROUND_HALF_UP, Decimal

    return float(Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
