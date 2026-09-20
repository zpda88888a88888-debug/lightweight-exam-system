"""题库导出 CSV（CH-011）。

规格依据：规格说明 4.11、5.2「题库管理」、7.4「题库导出 CSV 列」
"""

from __future__ import annotations

import csv
import io
from datetime import timedelta

from tests.support import (
    admin_headers,
    build_running_scenario,
    create_question,
    submit,
)


def export_rows(client, headers) -> list[list[str]]:
    resp = client.get("/api/admin/questions/export", headers=headers)
    assert resp.status_code == 200, resp.text
    assert "text/csv" in resp.headers["content-type"]
    return list(csv.reader(io.StringIO(resp.content.decode("utf-8"))))


def header_of(rows: list[list[str]]) -> list[str]:
    return rows[0]


def row_for(rows: list[list[str]], stem: str) -> list[str]:
    for row in rows[1:]:
        if row[2] == stem:
            return row
    raise AssertionError(f"导出中没有题目：{stem}")


def test_header_matches_spec(client, clock):
    """列顺序与含义符合规格 7.4。"""
    headers = admin_headers(client)
    create_question(client, headers, stem="题一", answer=["A"], tags=["t"])
    create_question(client, headers, stem="题二", answer=["A"], tags=["t"])

    rows = export_rows(client, headers)
    header = header_of(rows)

    assert header[:3] == ["ID", "题型", "题干"]
    # 最少 4 个选项列
    assert header[3:7] == ["选项A", "选项B", "选项C", "选项D"]
    assert header[-7:] == [
        "正确答案", "分值", "标签", "解析", "上次抽中考试", "上次抽中时间", "累计正确率",
    ]


def test_empty_bank_exports_header_only(client, clock):
    """题库为空时仍导出表头，便于当作模板。"""
    headers = admin_headers(client)
    rows = export_rows(client, headers)
    assert len(rows) == 1
    assert header_of(rows)[0] == "ID"


def test_question_content_exported(client, clock):
    """题型、题干、选项、答案、分值、标签、解析都正确导出。"""
    headers = admin_headers(client)
    create_question(
        client,
        headers,
        stem="我国安全生产方针是？",
        question_type="multi",
        options=[
            {"key": "A", "text": "安全第一"},
            {"key": "B", "text": "预防为主"},
            {"key": "C", "text": "综合治理"},
            {"key": "D", "text": "生产优先"},
        ],
        answer=["A", "B", "C"],
        score=15,
        tags=["安全生产", "方针"],
    )

    rows = export_rows(client, headers)
    row = row_for(rows, "我国安全生产方针是？")

    assert row[1] == "多选题"
    assert row[3:7] == ["安全第一", "预防为主", "综合治理", "生产优先"]
    # 正确答案以原始选项标识给出，多个用逗号分隔
    assert row[7] == "A,B,C"
    assert row[8] == "15.0" or row[8] == "15"
    assert row[9] == "安全生产,方针"


def test_judge_question_exported(client, clock):
    """判断题：题型中文正确，答案为 对/错。"""
    headers = admin_headers(client)
    create_question(
        client, headers, stem="判断题一", question_type="judge", options=[],
        answer=["对"], score=5, tags=["t"],
    )

    rows = export_rows(client, headers)
    row = row_for(rows, "判断题一")
    assert row[1] == "判断题"
    assert row[7] == "对"
    assert row[3] == "正确"  # 判断题的默认选项
    assert row[4] == "错误"


def test_option_columns_expand_to_max(client, clock):
    """选项列按本次导出的最大选项数展开（超过 4 个时不会截断）。"""
    headers = admin_headers(client)
    create_question(
        client, headers, stem="六选项题",
        options=[{"key": k, "text": f"选项{k}"} for k in "ABCDEF"],
        answer=["A"], tags=["t"],
    )

    rows = export_rows(client, headers)
    header = header_of(rows)
    assert "选项E" in header
    assert "选项F" in header
    assert "选项G" not in header

    row = row_for(rows, "六选项题")
    assert row[header.index("选项F")] == "选项F"


def test_stats_columns_empty_when_no_data(client, clock):
    """从未被抽中/作答：统计列留空，而不是写 0（规格 7.4）。"""
    headers = admin_headers(client)
    create_question(client, headers, stem="新题", answer=["A"], tags=["t"])

    rows = export_rows(client, headers)
    header = header_of(rows)
    row = row_for(rows, "新题")

    assert row[header.index("上次抽中考试")] == ""
    assert row[header.index("上次抽中时间")] == ""
    assert row[header.index("累计正确率")] == ""


def test_stats_columns_filled_after_publish_and_submit(client, clock):
    """发布并有人作答后：考试名称、时间与正确率都导出。"""
    scenario = build_running_scenario(client, clock, question_count=2, score=10)
    question_id = scenario.bank[0]["id"]

    # 一人答对
    token = scenario.login("张三")
    attempt_id = scenario.start("张三")
    assert submit(
        client, token, attempt_id, [{"question_id": question_id, "answer": ["A"]}]
    ).status_code == 200

    rows = export_rows(client, scenario.headers)
    header = header_of(rows)
    row = row_for(rows, scenario.bank[0]["stem"])

    assert row[header.index("上次抽中考试")] == scenario.exam["title"]
    assert row[header.index("上次抽中时间")] != ""
    # 该题只在本场出现，1 人作答 1 人答对
    assert row[header.index("累计正确率")] == "100.0%"


def test_partial_correct_rate_format(client, clock):
    """正确率保留 1 位小数并带百分号（2/3 → 66.7%）。"""
    from tests.support import create_attempt_ok, create_exam, generate_invites, import_roster, join_ok, publish

    headers = admin_headers(client)
    question = create_question(
        client, headers, stem="正确率题", question_type="single",
        options=[{"key": "A", "text": "对"}, {"key": "B", "text": "错"}],
        answer=["A"], score=10, tags=["rate"],
    )
    exam = create_exam(
        client, headers, title="正确率考试", recruitment_no="EXP-RATE",
        start_at=clock.now() - timedelta(hours=1), end_at=clock.now() + timedelta(hours=1),
        rules=[{"tag": "rate", "count": 1}],
    )
    roster = [
        ("13800000001", "甲", "110101199001010011"),
        ("13800000002", "乙", "110101199001010022"),
        ("13800000003", "丙", "110101199001010033"),
    ]
    import_roster(client, headers, exam["id"], roster)
    generate_invites(client, headers, exam["id"])
    assert publish(client, headers, exam["id"]).status_code == 200

    from tests.support import invite_code_for

    for (phone, name, _id), answer in zip(roster, [["A"], ["A"], ["B"]]):
        token = join_ok(client, phone, invite_code_for(client, headers, exam["id"], name))
        attempt_id = create_attempt_ok(client, token, exam["id"])
        assert submit(
            client, token, attempt_id, [{"question_id": question["id"], "answer": answer}]
        ).status_code == 200

    rows = export_rows(client, headers)
    row = row_for(rows, "正确率题")
    assert row[header_of(rows).index("累计正确率")] == "66.7%"


def test_special_characters_escaped(client, clock):
    """题干/解析含逗号、引号、换行时正确转义并可被 csv 正确解析回来。"""
    headers = admin_headers(client)
    messy_stem = '含,逗号"引号"和\n换行的题干'
    messy_analysis = "解析：A、B 都对"

    question = create_question(client, headers, stem=messy_stem, answer=["A"], tags=["标签,带逗号"])
    resp = client.put(
        f"/api/admin/questions/{question['id']}",
        headers=headers,
        json={
            "type": "single",
            "stem": messy_stem,
            "options": question["options"],
            "answer": ["A"],
            "score": 5,
            "tags": ["标签,带逗号"],
            "analysis": messy_analysis,
        },
    )
    assert resp.status_code == 200

    rows = export_rows(client, headers)
    row = row_for(rows, messy_stem)
    header = header_of(rows)
    assert row[header.index("标签")] == "标签,带逗号"
    assert row[header.index("解析")] == messy_analysis


def test_export_requires_admin(client, clock):
    scenario = build_running_scenario(client, clock, question_count=1)
    assert client.get("/api/admin/questions/export").status_code == 401

    token = scenario.login("张三")
    assert (
        client.get(
            "/api/admin/questions/export", headers={"Authorization": f"Bearer {token}"}
        ).status_code
        == 403
    )
