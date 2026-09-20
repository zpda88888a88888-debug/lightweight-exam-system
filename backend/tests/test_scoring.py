"""阶段 1：判分引擎不变量与黄金样本。

规格依据：spec 6.1 / 架构 8 / 测试方案 6.1

断言独立性声明：
    以下所有 expected 值均为字面量，由测试方案 6.1 的黄金样本表人工锁定，
    未调用 app.scoring 中的任何辅助函数来计算期望值。
"""

import pytest

from app.scoring import ScoringConfigError, judge

# --------------------------------------------------------------------------
# 黄金样本（测试方案 6.1，人工确认，不由 AI 推导）
# --------------------------------------------------------------------------

GOLDEN_MULTI = [
    # (正确答案, 满分, 考生答案, 期望得分)
    (["A", "B", "C"], 10, ["A", "B"], 6.7),
    (["A", "B", "C"], 10, ["A"], 3.3),
    (["A", "B", "C"], 10, ["A", "B", "C", "D"], 0),
    (["A", "B", "C"], 10, ["A", "D"], 0),
    (["A", "B", "C"], 10, [], 0),
    (["A", "B", "C"], 10, ["A", "B", "C"], 10.0),
]

GOLDEN_SINGLE = [
    (["B"], 5, ["B"], 5.0),
    (["B"], 5, ["A"], 0),
]

GOLDEN_JUDGE = [
    (["对"], 2, ["对"], 2.0),
    (["对"], 2, ["错"], 0),
]


@pytest.mark.parametrize("correct,full,selected,expected", GOLDEN_MULTI)
def test_multi_choice_golden_samples(correct, full, selected, expected):
    """INV-6 / INV-3 / INV-4 / INV-5：多选黄金样本逐条锁定口径。"""
    assert judge("multi", correct, selected, full) == expected


@pytest.mark.parametrize("correct,full,selected,expected", GOLDEN_SINGLE)
def test_single_choice_golden_samples(correct, full, selected, expected):
    """INV-7：单选完全匹配得满分，否则 0 分。"""
    assert judge("single", correct, selected, full) == expected


@pytest.mark.parametrize("correct,full,selected,expected", GOLDEN_JUDGE)
def test_judge_type_golden_samples(correct, full, selected, expected):
    """INV-7：判断题完全匹配得满分，否则 0 分。"""
    assert judge("judge", correct, selected, full) == expected


# --------------------------------------------------------------------------
# 不变量
# --------------------------------------------------------------------------


def test_multi_choice_wrong_selection_scores_zero():
    """INV-4：选了任意错误选项 → 0 分（对应变异 M1）。"""
    # 正确答案 ABC，考生选了 D（错误项）但同时选对了全部正确项
    assert judge("multi", ["A", "B", "C"], ["A", "B", "C", "D"], 10) == 0
    # 选了一个正确项 + 一个错误项
    assert judge("multi", ["A", "B", "C"], ["A", "D"], 10) == 0


def test_multi_choice_empty_selection_scores_zero():
    """INV-3：多选不选任何选项 → 0 分。"""
    assert judge("multi", ["A", "B"], [], 10) == 0


def test_multi_choice_full_correct_selection_scores_full():
    """INV-5：只选正确选项且全选 → 满分。"""
    assert judge("multi", ["A", "B", "C"], ["A", "B", "C"], 10) == 10.0
    # 提交顺序不影响（集合语义）
    assert judge("multi", ["A", "B", "C"], ["C", "A", "B"], 10) == 10.0


def test_multi_choice_partial_selection_scores_proportionally():
    """INV-6：漏选按比例得分（对应变异 M2，分母必须是正确选项总数而非已选数量）。"""
    assert judge("multi", ["A", "B", "C"], ["A", "B"], 10) == 6.7
    # 正确答案 4 项，选 1 项：5 * 1/4 = 1.25 → 1.3（四舍五入）
    assert judge("multi", ["A", "B", "C", "D"], ["A"], 5) == 1.3
    # 正确答案 4 项，选 3 项：5 * 3/4 = 3.75 → 3.8
    assert judge("multi", ["A", "B", "C", "D"], ["A", "B", "C"], 5) == 3.8


def test_score_rounded_to_one_decimal():
    """INV-2：得分保留 1 位小数，且为四舍五入（对应变异 M3）。"""
    # 30 * 1/3 = 10.0
    assert judge("multi", ["A", "B", "C"], ["A"], 30) == 10.0
    # 10 * 1/7 = 1.4285... → 1.4
    assert judge("multi", list("ABCDEFG"), ["A"], 10) == 1.4
    # 10 * 2/7 = 2.857... → 2.9
    assert judge("multi", list("ABCDEFG"), ["A", "B"], 10) == 2.9
    # 10 * 5/7 = 7.142... → 7.1
    assert judge("multi", list("ABCDEFG"), ["A", "B", "C", "D", "E"], 10) == 7.1


def test_multi_choice_degenerate_single_correct_option():
    """边界：多选正确答案仅 1 项（退化情形）等同于单选。"""
    assert judge("multi", ["A"], ["A"], 10) == 10.0
    assert judge("multi", ["A"], ["B"], 10) == 0
    assert judge("multi", ["A"], [], 10) == 0


def test_multi_choice_all_options_correct():
    """边界：多选正确答案全选（选项总数 = 正确数）。"""
    assert judge("multi", ["A", "B"], ["A"], 10) == 5.0
    assert judge("multi", ["A", "B"], ["A", "B"], 10) == 10.0


def test_answer_with_unknown_option_key_scores_zero():
    """边界：答案含不存在的选项标识（正确答案 ABC，考生选 E）→ 视为选错 → 0 分。"""
    assert judge("multi", ["A", "B", "C"], ["E"], 10) == 0
    assert judge("single", ["B"], ["E"], 5) == 0


def test_duplicate_option_keys_are_deduplicated():
    """边界：重复选项标识 ["A","A","B"] 按集合语义去重后计分。"""
    assert judge("multi", ["A", "B", "C"], ["A", "A", "B"], 10) == 6.7
    # 重复的正确项不应造成“超过满分”
    assert judge("multi", ["A", "B"], ["A", "A", "A"], 10) == 5.0


def test_blank_option_keys_are_ignored():
    """边界：空字符串与纯空白选项标识不参与判分（归一后忽略）。"""
    # 正确答案里的空白项不影响正确选项总数
    assert judge("multi", ["A", "", "   "], ["A"], 10) == 10.0
    # 考生答案里的空白项不构成“选错”
    assert judge("multi", ["A", "B"], ["A", "B", "  "], 10) == 10.0
    assert judge("multi", ["A", "B"], ["A", ""], 10) == 5.0


def test_none_option_keys_are_ignored():
    """边界：None 选项标识被忽略，不抛异常。"""
    assert judge("single", ["A"], [None], 5) == 0
    assert judge("judge", ["对"], ["对", None], 2) == 2.0


def test_score_within_range_for_any_answer():
    """INV-1：任意答案的得分 ∈ [0, 满分]。"""
    correct = ["A", "B", "C"]
    full = 10
    candidates = [
        [], ["A"], ["B"], ["C"], ["A", "B"], ["A", "C"], ["B", "C"],
        ["A", "B", "C"], ["D"], ["A", "D"], ["A", "B", "C", "D"],
        ["Z"], ["A", "A", "B", "B", "C"],
    ]
    for selected in candidates:
        got = judge("multi", correct, selected, full)
        assert 0 <= got <= full, f"越界: selected={selected} got={got}"


def test_unknown_question_type_rejected():
    """防御性：未知题型不得静默返回 0 分。"""
    with pytest.raises(ValueError):
        judge("essay", ["A"], ["A"], 10)


@pytest.mark.parametrize("full", [0, -1, -10])
def test_non_positive_full_score_is_config_error(full):
    """边界/防御性：满分值为 0 或负数 → 配置错误。"""
    with pytest.raises(ScoringConfigError):
        judge("multi", ["A"], ["A"], full)


@pytest.mark.parametrize("qtype", ["single", "multi", "judge"])
def test_empty_correct_answer_is_config_error(qtype):
    """边界/防御性：正确答案为空 → 配置错误。"""
    with pytest.raises(ScoringConfigError):
        judge(qtype, [], ["A"], 10)
