"""阶段 1：及格线计算不变量与黄金样本。

规格依据：spec 4.7 / 6.2 / 架构 9.10 / 测试方案 6.2

断言独立性声明：
    期望及格人数为字面量，直接取自测试方案 6.2 的黄金样本表，
    未调用 app.stats 计算期望值。
"""

import math

import pytest

from app.stats import compute_pass_line

# --------------------------------------------------------------------------
# 黄金样本（测试方案 6.2）
# --------------------------------------------------------------------------

GOLDEN = [
    # (得分序列, pass_ratio, 期望及格人数)
    # [80,75,75,60,50]@40% → 前 2 名为 80 与 75，75 并列 2 人全部通过 = 3
    ([80, 75, 75, 60, 50], 40, 3),
    # 无并列
    ([100, 90, 80, 70, 60], 40, 2),
    # 全部并列，全部通过
    ([50, 50, 50, 50], 50, 4),
    # 单人
    ([10], 90, 1),
    # 无 attempt
    ([], 50, 0),
]


@pytest.mark.parametrize("scores,ratio,expected", GOLDEN)
def test_pass_line_golden_samples(scores, ratio, expected):
    """黄金样本：及格人数逐条锁定口径。"""
    result = compute_pass_line(scores, ratio)
    assert result.pass_count == expected
    assert result.total == len(scores)


def test_pass_line_includes_all_ties():
    """INV：并列全部通过（对应变异 M4：只取前 N 名）。"""
    # 40% of 5 = 2 名；第 2 名得分 75 有并列，故 3 人及格
    result = compute_pass_line([80, 75, 75, 60, 50], 40)
    assert result.pass_count == 3
    assert result.threshold == 75.0


def test_pass_ratio_denominator_excludes_absent():
    """INV-10：分母 = 所有有 attempt 的人，缺考不进分母（对应变异 M5）。"""
    # 传入的序列本身就是“有 attempt 的人”，无 attempt 者不在其中
    result = compute_pass_line([90, 80], 50)
    assert result.total == 2
    assert result.pass_count == 1


def test_pass_count_at_least_ceil_of_ratio():
    """INV-8：及格人数 ≥ ⌈pass_ratio% × 有 attempt 人数⌉（并列只放宽不放严）。"""
    datasets = [
        [80, 75, 75, 60, 50],
        [100, 90, 80, 70, 60],
        [50, 50, 50, 50],
        [10],
        [66.7, 66.7, 33.3, 0.0, 100.0, 50.0],
        [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
    ]
    for scores in datasets:
        for ratio in range(10, 100, 10):
            expected_floor = math.ceil(len(scores) * ratio / 100)
            result = compute_pass_line(scores, ratio)
            assert result.pass_count >= expected_floor, (
                f"scores={scores} ratio={ratio} "
                f"pass_count={result.pass_count} < {expected_floor}"
            )
            assert result.pass_count <= len(scores)


def test_strictly_above_threshold_always_passes():
    """INV-9：所有得分严格高于及格线者必然及格。"""
    scores = [100, 90, 80, 70, 60, 60, 30]
    for ratio in range(10, 100, 10):
        result = compute_pass_line(scores, ratio)
        assert result.threshold is not None
        for s in scores:
            if s > result.threshold:
                assert s >= result.threshold


def test_threshold_matches_kth_highest_score():
    """及格线 = 降序第 k 名得分，k = ⌈ratio% × N⌉。"""
    scores = [100, 90, 80, 70, 60]
    result = compute_pass_line(scores, 40)
    # ⌈0.4 × 5⌉ = 2 → 第 2 名 = 90
    assert result.threshold == 90.0
    assert result.pass_count == 2


def test_all_same_score_all_pass():
    """边界：所有考生同分 → 全部及格。"""
    result = compute_pass_line([72.5] * 8, 10)
    assert result.pass_count == 8
    assert result.threshold == 72.5


def test_single_candidate_ratio_bounds():
    """边界：单人时 pass_ratio 恰好 10% 与 90% 均及格 1 人。"""
    assert compute_pass_line([55], 10).pass_count == 1
    assert compute_pass_line([55], 90).pass_count == 1


@pytest.mark.parametrize("ratio", [10, 20, 30, 40, 50, 60, 70, 80, 90])
def test_all_nine_ratio_steps_supported(ratio):
    """INV-11：pass_ratio 覆盖 10%–90% 共 9 档。"""
    result = compute_pass_line([100, 80, 60, 40, 20, 0, 10, 30, 50, 70], ratio)
    assert result.pass_count >= math.ceil(10 * ratio / 100)
    assert result.total == 10


@pytest.mark.parametrize("ratio", [0, 5, 95, 100, -10, 150])
def test_ratio_outside_range_rejected(ratio):
    """防御性：pass_ratio 必须在 10–90 且为 10 的倍数。"""
    with pytest.raises(ValueError):
        compute_pass_line([100, 90], ratio)


def test_empty_scores_yields_zero_pass():
    """无 attempt：及格人数 0，及格线为 None。"""
    result = compute_pass_line([], 50)
    assert result.pass_count == 0
    assert result.total == 0
    assert result.threshold is None
