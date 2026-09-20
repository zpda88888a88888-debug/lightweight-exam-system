"""阶段 6：统计聚合与成绩 CSV 导出（测试方案 6.13、6.2、6.3）。

规格依据：spec 4.7、7.3 / 架构 9.10

口径定义（本实现明确定义，见 README）：
    「有 attempt 的人」= 已产生判分结果的 attempt（正常提交 / 超时提交）。
    未交卷的 attempt 不计入分母，在导出中视为缺考。
"""

from __future__ import annotations

import csv
import io
from datetime import timedelta

from tests.support import (
    admin_headers,
    build_draft_scenario,
    build_running_scenario,
    create_exam,
    create_question,
    create_attempt_ok,
    generate_invites,
    get_paper,
    import_roster,
    join_ok,
    publish,
    submit,
)

#: 测试方案 6.3 的数据集：1 满分、1 部分得分、1 选错、1 未作答、1 未登录
DATASET_ROSTER = [
    ("13800000001", "满分考生", "110101199001010011"),
    ("13800000002", "部分考生", "110101199001010022"),
    ("13800000003", "错选考生", "110101199001010033"),
    ("13800000004", "未答考生", "110101199001010044"),
    ("13800000005", "缺考考生", "110101199001010055"),
]


def build_wrong_rate_dataset(client, clock):
    """构造测试方案 6.3 的数据集，返回 (headers, exam, question, roster)。"""
    headers = admin_headers(client)
    question = create_question(
        client,
        headers,
        stem="多选题：正确为 A、B、C",
        question_type="multi",
        options=[
            {"key": "A", "text": "选项A"},
            {"key": "B", "text": "选项B"},
            {"key": "C", "text": "选项C"},
            {"key": "D", "text": "选项D"},
        ],
        answer=["A", "B", "C"],
        score=10,
        tags=["多选"],
    )
    exam = create_exam(
        client,
        headers,
        title="标错率数据集",
        recruitment_no="ZP-WR",
        start_at=clock.now() - timedelta(hours=1),
        end_at=clock.now() + timedelta(hours=1),
        pass_ratio=50,
        rules=[{"tag": "多选", "count": 1}],
    )
    import_roster(client, headers, exam["id"], DATASET_ROSTER)
    generate_invites(client, headers, exam["id"])
    assert publish(client, headers, exam["id"]).status_code == 200

    qid = question["id"]

    def answer(name: str, selected: list[str]):
        phone = next(p for p, n, _ in DATASET_ROSTER if n == name)
        from tests.support import invite_code_for

        token = join_ok(client, phone, invite_code_for(client, headers, exam["id"], name))
        attempt_id = create_attempt_ok(client, token, exam["id"])
        body = [{"question_id": qid, "answer": selected}] if selected is not None else []
        resp = submit(client, token, attempt_id, body)
        assert resp.status_code == 200, resp.text
        return resp.json()

    answer("满分考生", ["A", "B", "C"])   # 满分
    answer("部分考生", ["A", "B"])        # 6.7 分 → 算错
    answer("错选考生", ["A", "B", "C", "D"])  # 0 分 → 算错
    answer("未答考生", None)              # 未作答 → 算错
    # 缺考考生：不登录

    return headers, exam, question, DATASET_ROSTER


# --------------------------------------------------------------------------
# 统计口径
# --------------------------------------------------------------------------


def test_wrong_rate_dataset_matches_spec(client, clock):
    """测试方案 6.3 数据集 → 标错率 3/4 = 75%，未登录者不计入分母。"""
    headers, exam, question, _ = build_wrong_rate_dataset(client, clock)

    resp = client.get(f"/api/admin/exams/{exam['id']}/stats", headers=headers)
    assert resp.status_code == 200, resp.text
    stats = resp.json()

    assert stats["total_candidates"] == 5
    assert stats["attempt_count"] == 4
    assert stats["absent_count"] == 1

    by_id = {q["question_id"]: q for q in stats["questions"]}
    assert by_id[question["id"]]["wrong_rate"] == 0.75
    assert by_id[question["id"]]["full_score"] == 10.0


def test_average_score_denominator_excludes_absent(client, clock):
    """平均分分母 = 有 attempt 的人：(10 + 6.7 + 0 + 0) / 4 = 4.2。"""
    headers, exam, _, _ = build_wrong_rate_dataset(client, clock)
    stats = client.get(f"/api/admin/exams/{exam['id']}/stats", headers=headers).json()

    expected = (10.0 + 6.7 + 0.0 + 0.0) / 4
    assert abs(stats["average_score"] - round(expected, 1)) < 1e-6
    assert stats["average_score"] == 4.2


def test_pass_line_and_rate_from_scores(client, clock):
    """及格率：得分 [10, 6.7, 0, 0]，50% → 取前 2 名（10、6.7）及格。"""
    headers, exam, _, _ = build_wrong_rate_dataset(client, clock)
    stats = client.get(f"/api/admin/exams/{exam['id']}/stats", headers=headers).json()

    assert stats["pass_ratio"] == 50
    assert stats["pass_line"] == 6.7
    assert stats["pass_count"] == 2
    assert abs(stats["pass_rate"] - 0.5) < 1e-9


def test_stats_on_exam_without_attempts(client, clock):
    """无人交卷 → 平均分 0、及格 0、缺考 = 全部名单。"""
    scenario = build_running_scenario(client, clock, question_count=2)
    stats = client.get(
        f"/api/admin/exams/{scenario.exam_id}/stats", headers=scenario.headers
    ).json()

    assert stats["total_candidates"] == 2
    assert stats["attempt_count"] == 0
    assert stats["absent_count"] == 2
    assert stats["average_score"] == 0.0
    assert stats["pass_line"] is None
    assert stats["pass_count"] == 0
    assert stats["pass_rate"] == 0.0


def test_pass_line_ties_all_pass_end_to_end(client, clock):
    """及格线并列放宽：100/75/75/50/25 @40% → 前 2 名含并列 → 3 人及格。"""
    headers = admin_headers(client)
    bank = [
        create_question(client, headers, stem=f"题{i}", answer=["A"], score=25, tags=["t"])
        for i in range(4)
    ]
    roster = [
        ("13800000001", "甲", "110101199001010011"),
        ("13800000002", "乙", "110101199001010022"),
        ("13800000003", "丙", "110101199001010033"),
        ("13800000004", "丁", "110101199001010044"),
        ("13800000005", "戊", "110101199001010055"),
    ]
    exam = create_exam(
        client,
        headers,
        title="并列及格考试",
        recruitment_no="ZP-TIE",
        start_at=clock.now() - timedelta(hours=1),
        end_at=clock.now() + timedelta(hours=1),
        pass_ratio=40,
        rules=[{"tag": "t", "count": 4}],
    )
    import_roster(client, headers, exam["id"], roster)
    generate_invites(client, headers, exam["id"])
    assert publish(client, headers, exam["id"]).status_code == 200

    from tests.support import invite_code_for

    # 正确答题数量：4、3、3、2、1 → 得分 100、75、75、50、25
    for (phone, name, _), correct_count in zip(roster, [4, 3, 3, 2, 1]):
        token = join_ok(client, phone, invite_code_for(client, headers, exam["id"], name))
        attempt_id = create_attempt_ok(client, token, exam["id"])
        answers = [{"question_id": q["id"], "answer": ["A"]} for q in bank[:correct_count]]
        assert submit(client, token, attempt_id, answers).status_code == 200

    stats = client.get(f"/api/admin/exams/{exam['id']}/stats", headers=headers).json()
    assert stats["pass_line"] == 75.0
    assert stats["pass_count"] == 3
    assert abs(stats["pass_rate"] - 0.6) < 1e-9


def test_stats_question_order_follows_snapshot(client, clock):
    """统计中的题目顺序与试卷快照一致。"""
    scenario = build_running_scenario(client, clock, question_count=4)
    stats = client.get(
        f"/api/admin/exams/{scenario.exam_id}/stats", headers=scenario.headers
    ).json()
    paper = scenario.paper("张三").json()
    assert [q["question_id"] for q in stats["questions"]] == [q["id"] for q in paper["questions"]]
    assert [q["seq"] for q in stats["questions"]] == [0, 1, 2, 3]


# --------------------------------------------------------------------------
# 成绩导出
# --------------------------------------------------------------------------

EXPECTED_HEADER = [
    "选聘编号",
    "考试名称",
    "手机号",
    "姓名",
    "身份证号",
    "邀请码",
    "开始时间",
    "交卷时间",
    "得分",
    "是否及格",
    "切屏次数",
    "切屏时间点",
    "状态",
]


def parse_csv(text: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(text)))


def test_export_header_matches_spec_exactly(client, clock):
    """列头与 spec 7.3 完全一致（顺序与命名）。"""
    headers, exam, _, _ = build_wrong_rate_dataset(client, clock)
    resp = client.get(f"/api/admin/exams/{exam['id']}/results/export", headers=headers)
    assert resp.status_code == 200
    rows = parse_csv(resp.content.decode("utf-8"))
    assert rows[0] == EXPECTED_HEADER


def test_export_includes_absent_with_empty_score(client, clock):
    """缺考考生出现在导出中，得分为空，状态为「缺考」。"""
    headers, exam, _, roster = build_wrong_rate_dataset(client, clock)
    resp = client.get(f"/api/admin/exams/{exam['id']}/results/export", headers=headers)
    rows = parse_csv(resp.content.decode("utf-8"))
    body = rows[1:]

    assert len(body) == len(roster)  # 5 人全部出现

    absent = [r for r in body if r[12] == "缺考"]
    assert len(absent) == 1
    absent_row = absent[0]
    assert absent_row[3] == "缺考考生"
    assert absent_row[8] == ""      # 得分空
    assert absent_row[6] == ""      # 开始时间空
    assert absent_row[7] == ""      # 交卷时间空

    # 其余 4 人状态为正常提交
    normal = [r for r in body if r[12] == "正常提交"]
    assert len(normal) == 4


def test_export_scores_and_pass_flags(client, clock):
    """得分列按 1 位小数输出，是否及格与及格线一致。"""
    headers, exam, _, _ = build_wrong_rate_dataset(client, clock)
    rows = parse_csv(
        client.get(f"/api/admin/exams/{exam['id']}/results/export", headers=headers)
        .content.decode("utf-8")
    )[1:]

    by_name = {r[3]: r for r in rows}
    assert by_name["满分考生"][8] == "10.0"
    assert by_name["部分考生"][8] == "6.7"
    assert by_name["错选考生"][8] == "0.0"
    assert by_name["未答考生"][8] == "0.0"

    # 及格线 6.7：满分考生与部分考生及格
    assert by_name["满分考生"][9] == "是"
    assert by_name["部分考生"][9] == "是"
    assert by_name["错选考生"][9] == "否"
    assert by_name["未答考生"][9] == "否"


def test_export_timeout_status(client, clock):
    """超时提交 → 状态「超时提交」。"""
    scenario = build_running_scenario(client, clock, question_count=2)
    token = scenario.login("张三")
    attempt_id = scenario.start("张三")
    clock.set(scenario.end_at + timedelta(minutes=3))
    assert submit(client, token, attempt_id, scenario.answer_all_correct()).status_code == 200

    rows = parse_csv(
        client.get(
            f"/api/admin/exams/{scenario.exam_id}/results/export", headers=scenario.headers
        ).content.decode("utf-8")
    )[1:]
    by_name = {r[3]: r for r in rows}
    assert by_name["张三"][12] == "超时提交"
    assert by_name["李四"][12] == "缺考"


def test_export_switch_count_and_log(client, clock):
    """切屏次数与时间点进入导出。"""
    scenario = build_running_scenario(client, clock, question_count=1)
    token = scenario.login("张三")
    attempt_id = scenario.start("张三")
    log = ["2026-09-19T10:01:23", "2026-09-19T10:05:00"]
    submit(
        client, token, attempt_id, scenario.answer_all_correct(), switch_count=2, switch_log=log
    )

    rows = parse_csv(
        client.get(
            f"/api/admin/exams/{scenario.exam_id}/results/export", headers=scenario.headers
        ).content.decode("utf-8")
    )[1:]
    by_name = {r[3]: r for r in rows}
    assert by_name["张三"][10] == "2"
    assert "2026-09-19T10:01:23" in by_name["张三"][11]

    # 缺考者切屏次数为 0
    assert by_name["李四"][10] == "0"


def test_export_special_characters_escaped(client, clock):
    """姓名含逗号、引号时正确转义（CSV 解析后字段还原）。"""
    scenario = build_draft_scenario(
        client,
        clock,
        roster=[
            ("13800000001", '张,三', "110101199001010011"),
            ("13800000002", '李"四', "110101199001010022"),
        ],
        import_roster_rows=True,
        recruitment_no="ZP-ESC",
    )
    scenario.generate(confirm=True)
    assert scenario.publish().status_code == 200

    rows = parse_csv(
        client.get(
            f"/api/admin/exams/{scenario.exam_id}/results/export", headers=scenario.headers
        ).content.decode("utf-8")
    )[1:]
    names = {r[3] for r in rows}
    assert names == {'张,三', '李"四'}


def test_export_rows_cover_all_roster_members(client, clock):
    """导出覆盖全部名单，且考号/考试信息正确。"""
    scenario = build_running_scenario(client, clock, question_count=2)
    rows = parse_csv(
        client.get(
            f"/api/admin/exams/{scenario.exam_id}/results/export", headers=scenario.headers
        ).content.decode("utf-8")
    )[1:]
    assert len(rows) == 2
    for row in rows:
        assert row[0] == scenario.exam["recruitment_no"]
        assert row[1] == scenario.exam["title"]
        assert len(row[4]) == 18  # 身份证号
        assert len(row[5]) == 6   # 邀请码


def test_results_json_endpoint(client, clock):
    """成绩列表接口：结构完整、缺考者得分为 null。"""
    headers, exam, _, _ = build_wrong_rate_dataset(client, clock)
    resp = client.get(f"/api/admin/exams/{exam['id']}/results", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["exam_id"] == exam["id"]
    assert len(body["rows"]) == 5

    absent = [r for r in body["rows"] if r["status"] == "缺考"]
    assert len(absent) == 1
    assert absent[0]["score"] is None
    assert absent[0]["started_at"] is None

    scored = [r for r in body["rows"] if r["score"] is not None]
    assert len(scored) == 4
    assert scored[0]["score"] >= scored[-1]["score"], "成绩应按得分降序"


def test_export_and_stats_require_admin(client, clock):
    """导出与统计需要管理员权限。"""
    scenario = build_running_scenario(client, clock)
    token = scenario.login("张三")
    auth = {"Authorization": f"Bearer {token}"}
    assert client.get(f"/api/admin/exams/{scenario.exam_id}/results/export", headers=auth).status_code == 403
    assert client.get(f"/api/admin/exams/{scenario.exam_id}/stats", headers=auth).status_code == 403


def test_export_not_leaking_correct_answers(client, clock):
    """导出中不得出现正确答案内容（仅成绩数据）。"""
    headers, exam, question, _ = build_wrong_rate_dataset(client, clock)
    text = client.get(
        f"/api/admin/exams/{exam['id']}/results/export", headers=headers
    ).content.decode("utf-8")
    # 正确答案 A、B、C 不应以列表形式出现
    assert "answer_json" not in text
    assert "解析" not in text
