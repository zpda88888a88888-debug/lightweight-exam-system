"""阶段 5：发布冻结与组卷快照（测试方案 6.7）。

规格依据：spec 4.5、4.6 / 架构 9.3、9.6
对应变异 M10：发布后允许改组卷 → 本文件冻结测试必须失败。
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
)

ROSTER = [("13800000001", "张三", "110101199001010011")]


def make_draft(client, clock, *, bank_count: int = 3, tag: str = "标签A", need: int | None = None,
               recruitment_no: str = "ZP-DRAFT-1"):
    headers = admin_headers(client)
    bank = make_bank(client, headers, count=bank_count, tag=tag)
    exam = create_exam(
        client,
        headers,
        title="草稿考试",
        recruitment_no=recruitment_no,
        start_at=clock.now() - timedelta(hours=1),
        end_at=clock.now() + timedelta(hours=1),
        rules=[{"tag": tag, "count": bank_count if need is None else need}],
    )
    return headers, bank, exam


def _exam_payload(clock, **overrides):
    payload = {
        "title": "改名后的考试",
        "recruitment_no": "ZP-DRAFT-1",
        "start_at": (clock.now() - timedelta(hours=2)).isoformat(),
        "end_at": (clock.now() + timedelta(hours=2)).isoformat(),
        "pass_ratio": 60,
        "settings": {"rules": [{"tag": "标签A", "count": 1}]},
    }
    payload.update(overrides)
    return payload


# --------------------------------------------------------------------------
# 草稿：可自由修改
# --------------------------------------------------------------------------


def test_draft_allows_updates_and_delete(client, clock):
    """草稿状态下组卷、时间、名单、邀请码、选聘编号均可修改，且可删除。"""
    headers, bank, exam = make_draft(client, clock)
    exam_id = exam["id"]

    resp = client.put(f"/api/admin/exams/{exam_id}", headers=headers,
                      json=_exam_payload(clock, title="新名字", recruitment_no="ZP-NEW"))
    assert resp.status_code == 200, resp.text
    assert resp.json()["title"] == "新名字"

    assert import_roster(client, headers, exam_id, ROSTER).status_code == 200
    assert generate_invites(client, headers, exam_id).status_code == 200

    assert client.delete(f"/api/admin/exams/{exam_id}", headers=headers).status_code == 200
    assert client.get("/api/admin/exams", headers=headers).json() == []


# --------------------------------------------------------------------------
# 已发布：全冻结
# --------------------------------------------------------------------------


def test_published_exam_rejects_rule_change(client, clock):
    """发布后修改组卷规则 → 拒绝（变异 M10）。"""
    scenario = build_running_scenario(client, clock)
    resp = client.put(
        f"/api/admin/exams/{scenario.exam_id}",
        headers=scenario.headers,
        json=_exam_payload(clock, recruitment_no=scenario.exam["recruitment_no"]),
    )
    assert resp.status_code == 409
    assert "冻结" in resp.json()["detail"]


def test_published_exam_rejects_time_change(client, clock):
    """发布后修改 start_at / end_at → 拒绝。"""
    scenario = build_running_scenario(client, clock)
    payload = _exam_payload(
        clock,
        recruitment_no=scenario.exam["recruitment_no"],
        start_at=(clock.now() + timedelta(hours=5)).isoformat(),
        end_at=(clock.now() + timedelta(hours=6)).isoformat(),
    )
    assert client.put(
        f"/api/admin/exams/{scenario.exam_id}", headers=scenario.headers, json=payload
    ).status_code == 409


def test_published_exam_rejects_pass_ratio_change(client, clock):
    """发布后修改 pass_ratio → 拒绝。"""
    scenario = build_running_scenario(client, clock)
    payload = _exam_payload(clock, recruitment_no=scenario.exam["recruitment_no"], pass_ratio=90)
    assert client.put(
        f"/api/admin/exams/{scenario.exam_id}", headers=scenario.headers, json=payload
    ).status_code == 409


def test_published_exam_rejects_recruitment_no_change(client, clock):
    """发布后修改选聘编号 → 拒绝。"""
    scenario = build_running_scenario(client, clock)
    payload = _exam_payload(clock, recruitment_no="ZP-CHANGED")
    assert client.put(
        f"/api/admin/exams/{scenario.exam_id}", headers=scenario.headers, json=payload
    ).status_code == 409


def test_published_exam_rejects_delete(client, clock):
    """发布后删除考试 → 拒绝。"""
    scenario = build_running_scenario(client, clock)
    resp = client.delete(f"/api/admin/exams/{scenario.exam_id}", headers=scenario.headers)
    assert resp.status_code == 409


def test_published_exam_rejects_roster_change(client, clock):
    """发布后修改名单 → 拒绝。"""
    scenario = build_running_scenario(client, clock)
    resp = import_roster(
        client, scenario.headers, scenario.exam_id, [("13800000009", "王五", "110101199001010099")]
    )
    assert resp.status_code == 409


def test_published_exam_rejects_invite_regeneration(client, clock):
    """发布后重新生成邀请码 → 拒绝。"""
    scenario = build_running_scenario(client, clock)
    resp = generate_invites(client, scenario.headers, scenario.exam_id, confirm=True)
    assert resp.status_code == 409


def test_archived_exam_rejects_modifications(client, clock):
    """归档状态同样拒绝修改。"""
    scenario = build_running_scenario(client, clock)
    archived = client.post(f"/api/admin/exams/{scenario.exam_id}/archive", headers=scenario.headers)
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    assert client.put(
        f"/api/admin/exams/{scenario.exam_id}",
        headers=scenario.headers,
        json=_exam_payload(clock, recruitment_no=scenario.exam["recruitment_no"]),
    ).status_code == 409
    assert client.delete(
        f"/api/admin/exams/{scenario.exam_id}", headers=scenario.headers
    ).status_code == 409
    assert import_roster(client, scenario.headers, scenario.exam_id, ROSTER).status_code == 409
    assert generate_invites(client, scenario.headers, scenario.exam_id).status_code == 409


def test_publish_twice_rejected(client, clock):
    """已发布考试不可再次发布。"""
    scenario = build_running_scenario(client, clock)
    resp = publish(client, scenario.headers, scenario.exam_id)
    assert resp.status_code == 409


# --------------------------------------------------------------------------
# 组卷校验与快照
# --------------------------------------------------------------------------


def test_publish_fails_when_tag_insufficient_and_names_tag(client, clock):
    """标签题数不足 → 发布失败，且错误信息必须包含该标签名（spec 4.5）。"""
    headers, bank, exam = make_draft(client, clock, bank_count=8, tag="标签A", need=5)
    # 另建一个只有 3 题的标签 B，规则要求 5 题
    make_bank(client, headers, count=3, tag="标签B")
    resp = client.put(
        f"/api/admin/exams/{exam['id']}",
        headers=headers,
        json=_exam_payload(
            clock,
            recruitment_no="ZP-DRAFT-1",
            settings={"rules": [{"tag": "标签A", "count": 5}, {"tag": "标签B", "count": 5}]},
        ),
    )
    assert resp.status_code == 200, resp.text

    resp = publish(client, headers, exam["id"])
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert "标签B" in detail
    assert "标签A" not in detail  # 标签 A 题量充足，不应被误报

    # 发布失败后仍是草稿，可重试
    exams = client.get("/api/admin/exams", headers=headers).json()
    assert exams[0]["status"] == "draft"


def test_publish_without_rules_rejected(client, clock):
    """组卷规则为空 → 发布失败。"""
    headers, bank, exam = make_draft(client, clock)
    resp = client.put(
        f"/api/admin/exams/{exam['id']}",
        headers=headers,
        json=_exam_payload(clock, recruitment_no="ZP-DRAFT-1", settings={"rules": []}),
    )
    assert resp.status_code == 200
    resp = publish(client, headers, exam["id"])
    assert resp.status_code == 400


def test_publish_creates_snapshot_with_exact_count_and_total_score(client, clock):
    """发布生成快照：题数与总分正确。"""
    scenario = build_running_scenario(client, clock, question_count=4, score=2.5)
    resp = client.get("/api/admin/exams", headers=scenario.headers).json()
    published = resp[0]
    assert published["status"] == "published"
    assert published["published_at"] is not None
    assert published["external_status"] == "running"

    body = scenario.paper("张三").json()
    assert len(body["questions"]) == 4


def test_snapshot_order_fixed_and_persisted(client, clock):
    """题目顺序发布时随机固定，之后多次拉卷不变。"""
    scenario = build_running_scenario(client, clock, question_count=6)
    first = [q["id"] for q in scenario.paper("张三").json()["questions"]]
    second = [q["id"] for q in scenario.paper("李四").json()["questions"]]
    assert first == second


def test_used_question_cannot_be_edited_after_publish(client, clock):
    """架构 9.6：已发布考试引用的题目不可修改（否则快照内容会被改动）。"""
    scenario = build_running_scenario(client, clock, question_count=2)
    question = scenario.bank[0]
    resp = client.put(
        f"/api/admin/questions/{question['id']}",
        headers=scenario.headers,
        json={
            "type": "single",
            "stem": "被改动的题干",
            "options": question["options"],
            "answer": ["A"],
            "score": 10,
            "tags": ["标签A"],
            "analysis": "",
        },
    )
    assert resp.status_code == 409
    assert "已发布考试" in resp.json()["detail"]

    # 题干在试卷中保持不变
    body = scenario.paper("张三").json()
    by_id = {q["id"]: q for q in body["questions"]}
    assert by_id[question["id"]]["stem"] == question["stem"]


def test_used_question_cannot_be_deleted_after_publish(client, clock):
    """已发布考试引用的题目不可删除，否则试卷会缺题。"""
    scenario = build_running_scenario(client, clock, question_count=2)
    question = scenario.bank[0]
    resp = client.delete(f"/api/admin/questions/{question['id']}", headers=scenario.headers)
    assert resp.status_code == 409

    body = scenario.paper("张三").json()
    assert len(body["questions"]) == 2


def test_unused_question_can_still_be_edited_and_deleted(client, clock):
    """未被已发布考试引用的题目仍可自由编辑与删除（不误伤题库管理）。"""
    scenario = build_running_scenario(client, clock, question_count=2)
    extra = create_question(
        client, scenario.headers, stem="未使用的题目", answer=["A"], score=5, tags=["其他"]
    )
    assert client.delete(
        f"/api/admin/questions/{extra['id']}", headers=scenario.headers
    ).status_code == 200

    resp = client.put(
        f"/api/admin/questions/{extra['id']}",
        headers=scenario.headers,
        json={
            "type": "single",
            "stem": "不存在",
            "options": [{"key": "A", "text": "a"}],
            "answer": ["A"],
            "score": 5,
            "tags": [],
            "analysis": "",
        },
    )
    assert resp.status_code == 404


def test_draft_exam_referenced_question_free_to_edit(client, clock):
    """草稿考试尚未生成快照，题库题目可自由编辑。"""
    headers, bank, exam = make_draft(client, clock)
    question = bank[0]
    resp = client.put(
        f"/api/admin/questions/{question['id']}",
        headers=headers,
        json={
            "type": "single",
            "stem": "草稿阶段可改",
            "options": question["options"],
            "answer": ["A"],
            "score": 10,
            "tags": ["标签A"],
            "analysis": "",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["stem"] == "草稿阶段可改"


def test_no_question_shared_between_tag_rules(client, clock):
    """同一题不应因命中多个标签规则而在试卷中重复出现。"""
    headers = admin_headers(client)
    # 一道题同时带 标签A 与 标签B
    create_question(client, headers, stem="双标签题", answer=["A"], score=10, tags=["标签A", "标签B"])
    make_bank(client, headers, count=2, tag="标签A", prefix="A题")
    make_bank(client, headers, count=2, tag="标签B", prefix="B题")
    exam = create_exam(
        client,
        headers,
        title="交叉标签考试",
        recruitment_no="ZP-CROSS",
        start_at=clock.now() - timedelta(hours=1),
        end_at=clock.now() + timedelta(hours=1),
        rules=[{"tag": "标签A", "count": 2}, {"tag": "标签B", "count": 2}],
    )
    import_roster(client, headers, exam["id"], ROSTER)
    generate_invites(client, headers, exam["id"])
    resp = publish(client, headers, exam["id"])
    assert resp.status_code == 200, resp.text
    assert resp.json()["question_count"] == 4

    from tests.support import join_ok, get_paper

    token = join_ok(client, ROSTER[0][0], _code(client, headers, exam["id"]))
    body = get_paper(client, token, exam["id"]).json()
    ids = [q["id"] for q in body["questions"]]
    assert len(ids) == len(set(ids)), "试卷中出现重复题目"


def _code(client, headers, exam_id: int) -> str:
    from tests.support import invite_code_for

    return invite_code_for(client, headers, exam_id, "张三")
