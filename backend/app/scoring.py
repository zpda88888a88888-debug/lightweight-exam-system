"""判分引擎（纯函数，无 IO、无框架依赖）。

规格依据：spec 6.1 / 架构 8

判分规则：
    单选 / 判断：完全匹配得满分，否则 0 分。
    多选：不选 0 分；选了任何错误选项 0 分；
          只选正确选项但漏选 → 满分 × (选对数量 / 正确选项总数)。
    所有得分保留 1 位小数，四舍五入（ROUND_HALF_UP）。

本模块刻意保持纯净：判分只在服务端进行，且规则集中于此，便于配置化调整。
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable, Sequence

SINGLE = "single"
MULTI = "multi"
JUDGE = "judge"

VALID_TYPES = frozenset({SINGLE, MULTI, JUDGE})

_ONE_DECIMAL = Decimal("0.1")


class ScoringConfigError(ValueError):
    """题目配置错误（如满分为 0、正确答案为空）。"""


def round_half_up_1(value: float) -> float:
    """保留 1 位小数，四舍五入（避开 Python 内建 round 的银行家舍入）。"""
    return float(Decimal(str(value)).quantize(_ONE_DECIMAL, rounding=ROUND_HALF_UP))


def _normalize(keys: Iterable[str]) -> set[str]:
    """选项标识按集合语义归一：去重、转字符串、忽略空白。"""
    result: set[str] = set()
    for key in keys:
        if key is None:
            continue
        text = str(key).strip()
        if text:
            result.add(text)
    return result


def judge(
    question_type: str,
    correct_keys: Sequence[str],
    selected_keys: Sequence[str],
    full_score: float,
) -> float:
    """计算单题得分。

    Args:
        question_type: single / multi / judge
        correct_keys: 正确答案的原始选项标识，如 ["A", "B", "C"]
        selected_keys: 考生提交的原始选项标识
        full_score: 本题满分，必须 > 0

    Returns:
        得分，保留 1 位小数，范围 [0, full_score]。

    Raises:
        ValueError: 未知题型。
        ScoringConfigError: 满分非法或正确答案为空。
    """
    if question_type not in VALID_TYPES:
        raise ValueError(f"未知题型: {question_type!r}")

    if full_score is None or full_score <= 0:
        raise ScoringConfigError(f"满分必须大于 0，收到 {full_score!r}")

    correct = _normalize(correct_keys)
    if not correct:
        raise ScoringConfigError("正确答案为空，题目配置错误")

    selected = _normalize(selected_keys)

    if question_type == MULTI:
        if not selected:
            return 0.0
        # 选了任何错误选项 → 0 分
        if not selected <= correct:
            return 0.0
        # 只选正确选项但漏选 → 按正确选项总数比例得分
        ratio = len(selected) / len(correct)
        return round_half_up_1(full_score * ratio)

    # 单选 / 判断：完全匹配得满分，否则 0 分
    if selected == correct:
        return round_half_up_1(full_score)
    return 0.0
