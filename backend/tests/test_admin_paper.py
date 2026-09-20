"""管理端「试卷管理」接口（CH-002）。

规格依据：规格说明 4.8、5.2「试卷管理」

要点：
    - 试卷是发布时的快照，管理端只读查看，不提供改题入口；
    - 详情必须包含正确答案与分值（管理端专属，与考生端试卷接口相对）；
    - 草稿状态没有试卷，必须明确拒绝而不是返回空试卷。
"""

from __future__ import annotations

from datetime import timedelta

from tests.support import (
    admin_headers,
    build_draft_scenario,
    build_running_scenario,
    create_exam,
    create_question,
    generate_invites,
    import_roster,
    publish,
)


def test_admin_can_view_published_paper(client, clock):
    """已发布考试：返回试卷快照，含题目、答案与总分。"""
    scenario = build_running_scenario(client, clock, question_count=4, score=10)

    resp = client.get(
        f"/api/admin/exams/{scenario.exam_id}/paper", headers=scenario.headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["question_count"] == 4
    assert body["total_score"] == 40.0
    assert body["exam"]["id"] == scenario.exam_id
    assert len(body["questions"]) == 4


def test_paper_question_fields_complete(client, clock):
    """每道题包含序号、题型、题干、选项、正确答案、分值、解析。"""
    scenario = build_running_scenario(client, clock, question_count=2, score=10)
    body = client.get(
        f"/api/admin/exams/{scenario.exam_id}/paper", headers=scenario.headers
    ).json()

    for question in body["questions"]:
        assert set(question.keys()) == {
            "seq", "question_id", "type", "stem", "options", "answer", "score", "analysis",
        }
        assert question["type"] in {"single", "multi", "judge"}
        assert question["stem"]
        assert question["options"], "选项不能为空"
        assert question["answer"], "管理端试卷必须能看到正确答案"
        assert question["score"] > 0
        # 正确答案必须落在选项标识集合内
        option_keys = {o["key"] for o in question["options"]}
        assert set(question["answer"]) <= option_keys


def test_paper_sequence_is_contiguous_and_ordered(client, clock):
    """序号从 0 连续递增，代表试卷中的实际题序。"""
    scenario = build_running_scenario(client, clock, question_count=5)
    body = client.get(
        f"/api/admin/exams/{scenario.exam_id}/paper", headers=scenario.headers
    ).json()

    assert [q["seq"] for q in body["questions"]] == [0, 1, 2, 3, 4]


def test_paper_order_matches_candidate_paper(client, clock):
    """管理端看到的题序与考生端一致（题目顺序全局固定）。"""
    scenario = build_running_scenario(client, clock, question_count=4)

    admin_order = [
        q["question_id"]
        for q in client.get(
            f"/api/admin/exams/{scenario.exam_id}/paper", headers=scenario.headers
        ).json()["questions"]
    ]
    candidate_order = [q["id"] for q in scenario.paper("张三").json()["questions"]]

    assert admin_order == candidate_order


def test_paper_contains_only_drawn_questions(client, clock):
    """试卷只包含抽中的题目，未抽中的题目不出现（考试与试卷的对应关系）。"""
    # 题库共 5 题，但只抽 2 题
    scenario = build_running_scenario(client, clock, question_count=5)
    # 默认规则是 count=question_count，这里用另一场只抽 2 题的考试验证
    headers = admin_headers(client)
    create_question(client, headers, stem="未抽中的题", answer=["A"], score=10, tags=["另一标签"])
    exam = create_exam(
        client,
        headers,
        title="只抽两题",
        recruitment_no="ZP-PARTIAL",
        start_at=clock.now() - timedelta(hours=1),
        end_at=clock.now() + timedelta(hours=1),
        rules=[{"tag": "标签A", "count": 2}],
    )
    import_roster(client, headers, exam["id"], [("13800000001", "张三", "110101199001010011")])
    generate_invites(client, headers, exam["id"])
    assert publish(client, headers, exam["id"]).status_code == 200

    body = client.get(f"/api/admin/exams/{exam['id']}/paper", headers=headers).json()
    assert body["question_count"] == 2
    assert all(q["stem"] != "未抽中的题" for q in body["questions"])
    # 抽中的两题必须来自"标签A"
    drawn_ids = {q["question_id"] for q in body["questions"]}
    assert drawn_ids <= {q["id"] for q in scenario.bank}


def test_paper_reflects_question_score_in_exam(client, clock):
    """分值取自试卷快照（exam_questions.score），而非题库当前分值。"""
    scenario = build_running_scenario(client, clock, question_count=2, score=7)
    body = client.get(
        f"/api/admin/exams/{scenario.exam_id}/paper", headers=scenario.headers
    ).json()

    assert all(q["score"] == 7.0 for q in body["questions"])
    assert body["total_score"] == 14.0


def test_draft_exam_has_no_paper(client, clock):
    """草稿状态尚未生成快照 → 409 且给出可读原因。"""
    scenario = build_draft_scenario(client, clock, question_count=2)

    resp = client.get(
        f"/api/admin/exams/{scenario.exam_id}/paper", headers=scenario.headers
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "该考试尚未发布，暂无试卷"


def test_archived_exam_paper_still_readable(client, clock):
    """归档后试卷仍可查阅（历史归档需要）。"""
    scenario = build_running_scenario(client, clock, question_count=3)
    assert client.post(
        f"/api/admin/exams/{scenario.exam_id}/archive", headers=scenario.headers
    ).status_code == 200

    body = client.get(
        f"/api/admin/exams/{scenario.exam_id}/paper", headers=scenario.headers
    ).json()
    assert body["question_count"] == 3
    assert body["exam"]["status"] == "archived"


def test_paper_requires_admin(client, clock):
    """考生 token 与未认证请求都不能访问管理端试卷接口。"""
    scenario = build_running_scenario(client, clock, question_count=1)

    assert client.get(f"/api/admin/exams/{scenario.exam_id}/paper").status_code == 401

    candidate_token = scenario.login("张三")
    assert (
        client.get(
            f"/api/admin/exams/{scenario.exam_id}/paper",
            headers={"Authorization": f"Bearer {candidate_token}"},
        ).status_code
        == 403
    )


def test_paper_of_missing_exam_returns_404(client, clock):
    """不存在的考试 → 404。"""
    headers = admin_headers(client)
    assert client.get("/api/admin/exams/999999/paper", headers=headers).status_code == 404


def test_candidate_paper_still_hides_answers(client, clock):
    """对照：同一场考试，管理端能看到答案，考生端看不到。

    这条是防止"为了做试卷管理而把答案漏给考生端"的回归护栏。
    """
    import json

    scenario = build_running_scenario(client, clock, question_count=2)

    admin_body = client.get(
        f"/api/admin/exams/{scenario.exam_id}/paper", headers=scenario.headers
    ).json()
    assert admin_body["questions"][0]["answer"]

    candidate_body = scenario.paper("张三").json()
    serialized = json.dumps(candidate_body, ensure_ascii=False)
    assert "answer" not in serialized
    assert "analysis" not in serialized
