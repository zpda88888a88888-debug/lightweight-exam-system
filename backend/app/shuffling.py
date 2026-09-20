"""选项乱序。

规格依据：spec 6.6 / 架构 9.7

规则：
    - 题目顺序全局固定（发布时随机确定，存 exam_questions.seq）。
    - 选项顺序每个考生独立乱序，种子 = 手机号 + 邀请码。
    - 刷新后选项顺序不变（同一考生同一题 → 同一排列）。
    - 提交原始选项标识（A/B/C/D），非显示位置。
    - 判断题不打乱。
"""

from __future__ import annotations

import hashlib
import random
from typing import Sequence

from app.scoring import JUDGE


def _seed_for(seed_text: str, question_id: int) -> int:
    """由考生种子与题目 id 派生稳定整数种子。"""
    raw = f"{seed_text}#{question_id}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(raw).digest()[:8], "big")


def candidate_seed(phone: str, invite_code: str) -> str:
    """考生乱序种子 = 手机号 + 邀请码。"""
    return f"{phone}:{invite_code}"


def shuffled_options(
    *,
    question_type: str,
    question_id: int,
    options: Sequence[dict],
    seed_text: str,
) -> list[dict]:
    """返回该考生看到的选项顺序。

    判断题与单选项题目不打乱；乱序使用确定性随机，刷新后不变。
    """
    opts = list(options)
    if len(opts) <= 1:
        return opts
    # 判断题不打乱
    if question_type == JUDGE:
        return opts

    rng = random.Random(_seed_for(seed_text, question_id))
    shuffled = opts[:]
    rng.shuffle(shuffled)
    return shuffled
