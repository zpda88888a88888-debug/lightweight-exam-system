"""阶段 1：题目标错率计算。

规格依据：spec 4.7 / 6.3 / 架构 9.10 / 测试方案 6.3

断言独立性声明：期望值 0.75 / 0.0 / 1.0 为字面量，来自测试方案 6.3 的数据集描述。
"""

import pytest

from app.stats import compute_wrong_rates


def test_wrong_rate_counts_unanswered_as_wrong():
    """测试方案 6.3 数据集：5 名考生，1 人未登录（无 attempt）。

    1 人满分、1 人部分得分、1 人 0 分（选错项）、1 人未作答 → 4 人有 attempt。
    未作答算错，故错 3 人；未登录者不计入分母 → 3/4 = 75%。
    """
    # (earned, full_score)；无 attempt 者根本不进入这个列表
    records = [
        (10.0, 10.0),   # 满分
        (6.7, 10.0),    # 部分得分 → 算错
        (0.0, 10.0),    # 选了错项 → 算错
        (0.0, 10.0),    # 未作答 → 算错
    ]
    rates = compute_wrong_rates({101: records})
    assert rates[101] == pytest.approx(0.75)


def test_wrong_rate_zero_when_all_full_marks():
    """全部满分 → 标错率 0。"""
    rates = compute_wrong_rates({7: [(5.0, 5.0), (2.0, 2.0)]})
    assert rates[7] == pytest.approx(0.0)


def test_wrong_rate_one_when_all_wrong():
    """全部错（含未作答）→ 标错率 1。"""
    rates = compute_wrong_rates({7: [(0.0, 5.0), (0.0, 5.0)]})
    assert rates[7] == pytest.approx(1.0)


def test_denominator_is_attempt_holders_only():
    """分母 = 所有有 attempt 的人：3 人有 attempt，1 人满分 → 2/3。"""
    rates = compute_wrong_rates({9: [(10.0, 10.0), (0.0, 10.0), (5.0, 10.0)]})
    assert rates[9] == pytest.approx(2 / 3)


def test_partial_score_above_zero_still_counts_wrong():
    """得分 < 满分即算错（含部分得分），9.9/10 也算错。"""
    rates = compute_wrong_rates({3: [(9.9, 10.0), (10.0, 10.0)]})
    assert rates[3] == pytest.approx(0.5)


def test_question_with_no_attempt_holders_is_skipped():
    """无人有 attempt 的题目不出现在结果中（避免除零）。"""
    rates = compute_wrong_rates({5: []})
    assert 5 not in rates
    assert compute_wrong_rates({}) == {}


def test_multiple_questions_independent():
    """多题独立计算，互不影响。"""
    rates = compute_wrong_rates(
        {
            1: [(10.0, 10.0), (10.0, 10.0)],           # 0%
            2: [(10.0, 10.0), (0.0, 10.0)],            # 50%
            3: [(0.0, 10.0), (0.0, 10.0)],             # 100%
        }
    )
    assert rates[1] == pytest.approx(0.0)
    assert rates[2] == pytest.approx(0.5)
    assert rates[3] == pytest.approx(1.0)
