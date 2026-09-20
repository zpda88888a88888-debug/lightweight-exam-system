"""题库统计（CH-008）。

规格依据：规格说明 4.10、5.2「题库管理」

每道题展示：
    - 上次被随机抽中的考试名称与抽题时间（依据发布时的试卷快照）；
    - 累计答题正确率 = 正确次数 ÷ 所有已判分提交次数（未作答算错）。
"""

from __future__ import annotations

from datetime import timedelta

from tests.support import (
    admin_headers,
    build_running_scenario,
    create_exam,
    create_question,
    generate_invites,
    import_roster,
    make_bank,
    publish,
    submit,
)


def stats_of(client, headers, question_id: int) -> dict:
    rows = client.get("/api/admin/questions", headers=headers).json()
    for row in rows:
        if row["id"] == question_id:
            assert row["stats"] is not None, "题库列表必须返回 stats"
            return row["stats"]
    raise AssertionError(f"题库列表中没有题目 {question_id}")


def test_never_drawn_and_never_answered(client, clock):
    """从未被抽中、也从未被作答 → 全部为 None/0，界面据此显示「暂无」。"""
    headers = admin_headers(client)
    question = create_question(client, headers, stem="新题", answer=["A"], tags=["t"])

    stats = stats_of(client, headers, question["id"])
    assert stats["last_drawn_exam_id"] is None
    assert stats["last_drawn_exam_title"] is None
    assert stats["last_drawn_at"] is None
    assert stats["answer_count"] == 0
    assert stats["correct_rate"] is None, "从未被作答不能返回 0（会被误读为没人做对）"


def test_last_drawn_after_publish(client, clock):
    """发布后：记录抽中的考试名称与抽题时间。"""
    scenario = build_running_scenario(client, clock, question_count=2)
    headers = scenario.headers

    # scenario.exam 是创建时（发布前）的快照，published_at 为空；
    # 这里重新取一次以拿到实际发布时刻。
    published = next(
        e for e in client.get("/api/admin/exams", headers=headers).json()
        if e["id"] == scenario.exam_id
    )
    drawn_at = published["published_at"]
    assert drawn_at is not None

    for question in scenario.bank:
        stats = stats_of(client, headers, question["id"])
        assert stats["last_drawn_exam_id"] == scenario.exam_id
        assert stats["last_drawn_exam_title"] == scenario.exam["title"]
        assert stats["last_drawn_at"] == drawn_at


def test_last_drawn_is_most_recent_exam(client, clock):
    """同一题被多场考试抽中 → 显示最近一次抽中的考试。"""
    headers = admin_headers(client)
    # 该标签只有 1 道题，两场考试都必然抽到它
    bank = make_bank(client, headers, count=1, tag="唯一标签")
    question_id = bank[0]["id"]

    first = create_exam(
        client, headers, title="第一场", recruitment_no="STAT-1",
        start_at=clock.now() - timedelta(hours=1), end_at=clock.now() + timedelta(hours=1),
        rules=[{"tag": "唯一标签", "count": 1}],
    )
    import_roster(client, headers, first["id"], [("13800000001", "张三", "110101199001010011")])
    generate_invites(client, headers, first["id"])
    assert publish(client, headers, first["id"]).status_code == 200

    # 推进时间后再发布第二场，保证 published_at 更晚
    clock.set(clock.now() + timedelta(hours=2))

    second = create_exam(
        client, headers, title="第二场", recruitment_no="STAT-2",
        start_at=clock.now() - timedelta(hours=1), end_at=clock.now() + timedelta(hours=1),
        rules=[{"tag": "唯一标签", "count": 1}],
    )
    import_roster(client, headers, second["id"], [("13800000001", "张三", "110101199001010011")])
    generate_invites(client, headers, second["id"])
    assert publish(client, headers, second["id"]).status_code == 200

    stats = stats_of(client, headers, question_id)
    assert stats["last_drawn_exam_title"] == "第二场"
    assert stats["last_drawn_exam_id"] == second["id"]


def test_cumulative_correct_rate(client, clock):
    """累计正确率：3 人作答，1 人对、2 人错 → 1/3。"""
    headers = admin_headers(client)
    question = create_question(
        client, headers, stem="统计题", question_type="single",
        options=[{"key": "A", "text": "对"}, {"key": "B", "text": "错"}],
        answer=["A"], score=10, tags=["统计标签"],
    )
    exam = create_exam(
        client, headers, title="统计考试", recruitment_no="STAT-RATE",
        start_at=clock.now() - timedelta(hours=1), end_at=clock.now() + timedelta(hours=1),
        rules=[{"tag": "统计标签", "count": 1}],
    )
    roster = [
        ("13800000001", "甲", "110101199001010011"),
        ("13800000002", "乙", "110101199001010022"),
        ("13800000003", "丙", "110101199001010033"),
    ]
    import_roster(client, headers, exam["id"], roster)
    generate_invites(client, headers, exam["id"])
    assert publish(client, headers, exam["id"]).status_code == 200

    from tests.support import create_attempt_ok, invite_code_for, join_ok

    for (phone, name, _id), answer in zip(roster, [["A"], ["B"], ["B"]]):
        token = join_ok(client, phone, invite_code_for(client, headers, exam["id"], name))
        attempt_id = create_attempt_ok(client, token, exam["id"])
        assert submit(
            client, token, attempt_id, [{"question_id": question["id"], "answer": answer}]
        ).status_code == 200

    stats = stats_of(client, headers, question["id"])
    assert stats["answer_count"] == 3
    assert stats["correct_count"] == 1
    assert stats["correct_rate"] == round(1 / 3, 4)


def test_unanswered_counts_as_incorrect(client, clock):
    """未作答算错：只交卷不答题，正确率为 0 而不是 None。"""
    headers = admin_headers(client)
    scenario = build_running_scenario(client, clock, question_count=1)
    token = scenario.login("张三")
    attempt_id = scenario.start("张三")
    assert submit(client, token, attempt_id, []).status_code == 200

    stats = stats_of(client, headers, scenario.bank[0]["id"])
    assert stats["answer_count"] == 1
    assert stats["correct_count"] == 0
    assert stats["correct_rate"] == 0.0, "被作答过（哪怕没选）应返回 0，而不是 None"


def test_correct_rate_complements_wrong_rate(client, clock):
    """同一场考试同一题：正确率 + 标错率 = 1（口径互补）。"""
    headers = admin_headers(client)
    scenario = build_running_scenario(client, clock, question_count=1, score=10)
    question_id = scenario.bank[0]["id"]

    # 张三答对、李四答错
    token_a = scenario.login("张三")
    attempt_a = scenario.start("张三")
    assert submit(
        client, token_a, attempt_a, [{"question_id": question_id, "answer": ["A"]}]
    ).status_code == 200

    token_b = scenario.login("李四")
    attempt_b = scenario.start("李四")
    assert submit(
        client, token_b, attempt_b, [{"question_id": question_id, "answer": ["B"]}]
    ).status_code == 200

    correct_rate = stats_of(client, headers, question_id)["correct_rate"]
    exam_stats = client.get(
        f"/api/admin/exams/{scenario.exam_id}/stats", headers=headers
    ).json()
    wrong_rate = next(
        q["wrong_rate"] for q in exam_stats["questions"] if q["question_id"] == question_id
    )

    assert correct_rate == 0.5
    assert wrong_rate == 0.5
    assert abs((correct_rate + wrong_rate) - 1.0) < 1e-9


def test_stats_only_in_list_endpoint(client, clock):
    """单题新增/编辑的响应不带统计（stats 为 None），统计只在列表接口计算。"""
    headers = admin_headers(client)
    question = create_question(client, headers, stem="新题", answer=["A"], tags=["t"])
    assert question["stats"] is None

    updated = client.put(
        f"/api/admin/questions/{question['id']}",
        headers=headers,
        json={
            "type": "single",
            "stem": "改过",
            "options": question["options"],
            "answer": ["A"],
            "score": 5,
            "tags": ["t"],
            "analysis": "",
        },
    ).json()
    assert updated["stats"] is None


def test_stats_respects_filters(client, clock):
    """按标签筛选时，返回的题目依然带各自的统计。"""
    headers = admin_headers(client)
    scenario = build_running_scenario(client, clock, question_count=2, tag="筛选标签")

    rows = client.get("/api/admin/questions?tag=筛选标签", headers=headers).json()
    assert len(rows) == 2
    for row in rows:
        assert row["stats"]["last_drawn_exam_title"] == scenario.exam["title"]
