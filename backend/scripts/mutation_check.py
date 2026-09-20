"""变异测试执行器（测试方案 4.3 / 准出标准 E3）。

做法：对被测实现逐个注入预设错误，运行「应捕获该错误的测试」，
若测试失败则说明测试有效（已捕获）；若测试仍通过，说明测试无效。

用法：
    python scripts/mutation_check.py            # 执行全部变异并打印报告
    python scripts/mutation_check.py --json     # 额外输出 JSON
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Mutation:
    id: str
    inject_point: str
    description: str
    target_file: str
    old: str
    new: str
    test: str


MUTATIONS: list[Mutation] = [
    Mutation(
        id="M1",
        inject_point="多选判分",
        description="「选错得 0 分」改为「选错扣分」",
        target_file="app/scoring.py",
        old="""        if not selected <= correct:
            return 0.0""",
        new="""        if not selected <= correct:
            wrong = len(selected - correct)
            return round_half_up_1(max(0.0, full_score - wrong))""",
        test="tests/test_scoring.py::test_multi_choice_wrong_selection_scores_zero",
    ),
    Mutation(
        id="M2",
        inject_point="多选判分",
        description="漏选比例分母改为「已选数量」",
        target_file="app/scoring.py",
        old="        ratio = len(selected) / len(correct)",
        new="        ratio = len(selected) / len(selected)",
        test="tests/test_scoring.py::test_multi_choice_partial_selection_scores_proportionally",
    ),
    Mutation(
        id="M3",
        inject_point="多选判分",
        description="保留 2 位小数",
        target_file="app/scoring.py",
        old='_ONE_DECIMAL = Decimal("0.1")',
        new='_ONE_DECIMAL = Decimal("0.01")',
        test="tests/test_scoring.py::test_score_rounded_to_one_decimal",
    ),
    Mutation(
        id="M4",
        inject_point="及格线",
        description="「并列全部通过」改为「只取前 N 名」",
        target_file="app/stats.py",
        old="    pass_count = sum(1 for s in scores if s >= threshold)",
        new="    pass_count = k",
        test="tests/test_pass_line.py::test_pass_line_includes_all_ties",
    ),
    Mutation(
        id="M5",
        inject_point="及格率/平均分口径",
        description="分母改为「全部考生（含缺考）」",
        target_file="app/services.py",
        old="    average = sum(scores) / len(scores) if scores else 0.0",
        new="    average = sum(scores) / max(1, int(total_candidates)) if scores else 0.0",
        test="tests/test_stats_export.py::test_average_score_denominator_excludes_absent",
    ),
    Mutation(
        id="M6",
        inject_point="标错率",
        description="未作答不计入分母",
        target_file="app/stats.py",
        old="""        wrong = sum(1 for earned, full_score in records if earned < full_score)
        rates[question_id] = wrong / len(records)""",
        new="""        answered = [r for r in records if r[0] > 0]
        wrong = sum(1 for earned, full_score in records if earned < full_score)
        rates[question_id] = wrong / len(answered) if answered else 0.0""",
        test="tests/test_wrong_rate.py::test_wrong_rate_counts_unanswered_as_wrong",
    ),
    Mutation(
        id="M7",
        inject_point="幂等",
        description="重复提交重新判分",
        target_file="app/services.py",
        old="""        if fresh.status != ATTEMPT_IN_PROGRESS:
            return _existing_result(session, fresh)""",
        new="""        if False:
            return _existing_result(session, fresh)""",
        test="tests/test_attempt_idempotency.py::test_submit_is_idempotent",
    ),
    Mutation(
        id="M8",
        inject_point="试卷接口",
        description="响应中带上 answer_json",
        target_file="app/services.py",
        old="""                "options": options,
            }
        )""",
        new="""                "options": options,
                "answer": loads_json(item.question.answer_json, []),
            }
        )""",
        test="tests/test_paper_contract.py::test_paper_response_has_no_answer_field",
    ),
    Mutation(
        id="M9",
        inject_point="选项乱序",
        description="种子改为随机",
        target_file="app/shuffling.py",
        old='    return int.from_bytes(hashlib.sha256(raw).digest()[:8], "big")',
        new="    import random as _random\n\n    return _random.randint(0, 2**63)",
        test="tests/test_shuffling.py::test_option_order_stable_for_same_candidate",
    ),
    Mutation(
        id="M10",
        inject_point="发布冻结",
        description="发布后允许改组卷",
        target_file="app/domain.py",
        old="""    if exam.status == STATUS_DRAFT:
        return
    if exam.status == STATUS_ARCHIVED:
        raise ExamStateError("考试已归档，不可修改", status_code=409)""",
        new="""    if True:
        return
    if exam.status == STATUS_ARCHIVED:
        raise ExamStateError("考试已归档，不可修改", status_code=409)""",
        test="tests/test_publish_freeze.py::test_published_exam_rejects_rule_change",
    ),
]


def run_test(test: str) -> tuple[bool, str]:
    """运行单个测试，返回 (是否通过, 尾部输出)。"""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", test, "-p", "no:cacheprovider", "-q", "--no-header"],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    return proc.returncode == 0, (proc.stdout or "")[-1500:]


def apply_and_check(mutation: Mutation) -> dict:
    path = BACKEND_ROOT / mutation.target_file
    original = path.read_text(encoding="utf-8")

    if mutation.old not in original:
        return {
            "id": mutation.id,
            "inject_point": mutation.inject_point,
            "description": mutation.description,
            "test": mutation.test,
            "result": "INVALID",
            "detail": "注入点未在源码中找到（实现可能已改动），请更新变异脚本",
        }

    try:
        path.write_text(original.replace(mutation.old, mutation.new, 1), encoding="utf-8")
        passed, output = run_test(mutation.test)
    finally:
        path.write_text(original, encoding="utf-8")

    caught = not passed
    return {
        "id": mutation.id,
        "inject_point": mutation.inject_point,
        "description": mutation.description,
        "test": mutation.test,
        "result": "CAUGHT" if caught else "MISSED",
        "detail": "" if caught else output,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="变异测试执行器")
    parser.add_argument("--json", action="store_true", help="输出 JSON 汇总")
    args = parser.parse_args(argv)

    results = []
    print("=" * 78)
    print("变异测试（M1–M10）：注入错误 → 期望对应测试失败")
    print("=" * 78)

    for mutation in MUTATIONS:
        outcome = apply_and_check(mutation)
        results.append(outcome)
        mark = {"CAUGHT": "✓ 已捕获", "MISSED": "✗ 未捕获", "INVALID": "! 注入点失效"}[
            outcome["result"]
        ]
        print(f"[{outcome['id']:>3}] {mark}  {outcome['inject_point']} — {outcome['description']}")
        print(f"        测试：{outcome['test']}")
        if outcome["result"] != "CAUGHT":
            print(f"        详情：{outcome['detail'][:400]}")

    caught = sum(1 for r in results if r["result"] == "CAUGHT")
    total = len(results)
    print("-" * 78)
    print(f"结果：{caught}/{total} 个变异被测试捕获")

    report = BACKEND_ROOT / "mutation-report.md"
    lines = [
        "# 变异测试报告（测试方案 4.3 / 准出标准 E3）",
        "",
        f"- 执行时间：自动生成",
        f"- 结果：**{caught}/{total}** 个变异被捕获",
        "",
        "| 编号 | 注入点 | 变异内容 | 预期捕获测试 | 结果 |",
        "|---|---|---|---|---|",
    ]
    for r in results:
        mark = {"CAUGHT": "✅ 已捕获", "MISSED": "❌ 未捕获", "INVALID": "⚠️ 注入点失效"}[
            r["result"]
        ]
        lines.append(
            f"| {r['id']} | {r['inject_point']} | {r['description']} | `{r['test']}` | {mark} |"
        )
    lines.append("")
    report.write_text("\n".join(lines), encoding="utf-8")
    print(f"报告已写入：{report}")

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))

    return 0 if caught == total else 1


if __name__ == "__main__":
    sys.exit(main())
