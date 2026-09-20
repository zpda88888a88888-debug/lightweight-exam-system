"""阶段 4：选项乱序（测试方案 6.10）。

规格依据：spec 6.6 / 架构 9.7
对应变异 M9：种子改为随机 → 稳定性测试必须失败。

稳定性断言用纯函数（确定性种子），差异断言用固定题库样本 + 足够题量
（规避风险 R8 的概率性偶发失败）。
"""

from __future__ import annotations

from tests.support import build_running_scenario

OPTIONS = [
    {"key": "A", "text": "选项A"},
    {"key": "B", "text": "选项B"},
    {"key": "C", "text": "选项C"},
    {"key": "D", "text": "选项D"},
]

JUDGE_OPTIONS = [{"key": "对", "text": "正确"}, {"key": "错", "text": "错误"}]


# --------------------------------------------------------------------------
# 单元：确定性乱序（纯函数）
# --------------------------------------------------------------------------


def test_option_order_stable_for_same_candidate():
    """同一考生同一题：两次乱序结果完全一致（幂等于刷新后不变）。"""
    from app.shuffling import shuffled_options

    seed = "13800000001:123456"
    first = shuffled_options(
        question_type="single", question_id=1, options=OPTIONS, seed_text=seed
    )
    second = shuffled_options(
        question_type="single", question_id=1, options=OPTIONS, seed_text=seed
    )
    assert first == second


def test_option_order_uses_original_option_objects():
    """乱序只改顺序，不增删选项、不改内容。"""
    from app.shuffling import shuffled_options

    shuffled = shuffled_options(
        question_type="multi", question_id=7, options=OPTIONS, seed_text="seed"
    )
    assert len(shuffled) == len(OPTIONS)
    assert {o["key"] for o in shuffled} == {o["key"] for o in OPTIONS}
    assert sorted(o["key"] for o in shuffled) == sorted(o["key"] for o in OPTIONS)


def test_different_seeds_produce_different_orders():
    """不同考生种子在足够多的题目上必然出现顺序差异（确定性扫描）。"""
    from app.shuffling import shuffled_options

    seed_a = "13800000001:111111"
    seed_b = "13800000002:222222"

    differing = 0
    for question_id in range(1, 101):
        order_a = [o["key"] for o in shuffled_options(
            question_type="single", question_id=question_id, options=OPTIONS, seed_text=seed_a
        )]
        order_b = [o["key"] for o in shuffled_options(
            question_type="single", question_id=question_id, options=OPTIONS, seed_text=seed_b
        )]
        if order_a != order_b:
            differing += 1

    assert differing > 0, "两个种子在 100 道题上产生了完全相同的顺序，乱序失效"


def test_judge_questions_not_shuffled_in_unit():
    """判断题不打乱（单元层）。"""
    from app.shuffling import shuffled_options

    for question_id in range(1, 20):
        result = shuffled_options(
            question_type="judge",
            question_id=question_id,
            options=JUDGE_OPTIONS,
            seed_text="13800000001:123456",
        )
        assert [o["key"] for o in result] == ["对", "错"]


# --------------------------------------------------------------------------
# 集成：试卷接口的乱序行为
# --------------------------------------------------------------------------


def test_same_candidate_sees_stable_option_order(client, clock):
    """集成：同一考生两次拉卷，选项顺序完全一致（刷新不变）。"""
    scenario = build_running_scenario(client, clock, question_count=5)
    token = scenario.login("张三")

    from tests.support import get_paper

    first = get_paper(client, token, scenario.exam_id).json()
    second = get_paper(client, token, scenario.exam_id).json()

    for q1, q2 in zip(first["questions"], second["questions"]):
        assert [o["key"] for o in q1["options"]] == [o["key"] for o in q2["options"]]


def test_option_sets_equal_original(client, clock):
    """集成：乱序后每个考生的选项集合与原题选项集合相等（无增删）。"""
    scenario = build_running_scenario(client, clock, question_count=5)
    by_id = {q["id"]: q for q in scenario.bank}

    for name in ("张三", "李四"):
        body = scenario.paper(name).json()
        for question in body["questions"]:
            original_keys = {o["key"] for o in by_id[question["id"]]["options"]}
            paper_keys = {o["key"] for o in question["options"]}
            assert paper_keys == original_keys


def test_different_candidates_differ_on_at_least_one_question(client, clock):
    """集成：两名考生在足够大的题目样本上至少有一题选项顺序不同。"""
    scenario = build_running_scenario(client, clock, question_count=20)
    zhang = scenario.paper("张三").json()
    li = scenario.paper("李四").json()

    differences = 0
    for qz, ql in zip(zhang["questions"], li["questions"]):
        assert qz["id"] == ql["id"]
        order_z = [o["key"] for o in qz["options"]]
        order_l = [o["key"] for o in ql["options"]]
        if order_z != order_l:
            differences += 1

    assert differences > 0, "两名考生 20 道题全部顺序相同，乱序未生效"


def test_judge_question_shuffle_stable_via_second_exam(client, clock):
    """判断题：两名考生的选项顺序都保持 对/错（集成层，独立考试）。

    注意：必须在发布前建好判断题——发布后题库中被引用的题目会被冻结
    （架构 9.6），无法再改为判断题。
    """
    from datetime import timedelta

    from tests.support import (
        admin_headers,
        create_exam,
        create_question,
        generate_invites,
        import_roster,
        publish,
    )

    headers = admin_headers(client)
    for i in range(2):
        create_question(
            client,
            headers,
            stem=f"判断题{i + 1}",
            question_type="judge",
            options=[],
            answer=["对"],
            score=5,
            tags=["判断题标签"],
        )
    exam = create_exam(
        client,
        headers,
        title="判断题考试",
        recruitment_no="ZP-JUDGE",
        start_at=clock.now() - timedelta(hours=1),
        end_at=clock.now() + timedelta(hours=1),
        rules=[{"tag": "判断题标签", "count": 2}],
    )
    roster = [
        ("13800000001", "张三", "110101199001010011"),
        ("13800000002", "李四", "110101199001010022"),
    ]
    import_roster(client, headers, exam["id"], roster)
    generate_invites(client, headers, exam["id"])
    assert publish(client, headers, exam["id"]).status_code == 200

    from tests.support import invite_code_for, join_ok

    for _phone, name, _id in roster:
        code = invite_code_for(client, headers, exam["id"], name)
        token = join_ok(client, _phone, code)
        body = client.get(
            f"/api/exams/{exam['id']}/paper",
            headers={"Authorization": f"Bearer {token}"},
        ).json()
        assert len(body["questions"]) == 2
        for question in body["questions"]:
            assert question["type"] == "judge"
            assert [o["key"] for o in question["options"]] == ["对", "错"]


def test_scoring_uses_original_keys_not_display_position(client, clock):
    """提交原始选项标识：即使选项被乱序，提交 "A" 仍按原始 A 判分。"""
    scenario = build_running_scenario(client, clock, question_count=4, score=10)
    token = scenario.login("张三")
    attempt_id = scenario.start("张三")

    from tests.support import submit

    body = submit(client, token, attempt_id, scenario.answer_all_correct()).json()
    # 题库正确答案均为 A；选项已乱序，但提交的是原始标识，故仍是满分
    assert body["score"] == 40.0
