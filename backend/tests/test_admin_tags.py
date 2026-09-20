"""管理端题库标签接口（CH-005）。

规格依据：规格说明 4.5、5.2「组卷规则的标签必须从题库已有标签中选择」

该接口为前端提供封闭选项的数据源，因此必须：
    - 列出题库中真实存在的标签（否则组卷规则会配置出必然失败的考试）；
    - 给出每个标签的可用题数（前端据此做即时校验，避免发布才发现题量不足）。
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
    publish,
)


def test_tags_empty_bank(client, clock):
    """题库为空 → 返回空列表（不是 404）。"""
    headers = admin_headers(client)
    resp = client.get("/api/admin/tags", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_tags_with_counts(client, clock):
    """返回标签及各自的可用题数。"""
    headers = admin_headers(client)
    create_question(client, headers, stem="安全1", answer=["A"], tags=["安全生产"])
    create_question(client, headers, stem="安全2", answer=["A"], tags=["安全生产"])
    create_question(client, headers, stem="法规1", answer=["A"], tags=["法律法规"])

    tags = {t["tag"]: t["question_count"] for t in client.get("/api/admin/tags", headers=headers).json()}
    assert tags == {"安全生产": 2, "法律法规": 1}


def test_question_with_multiple_tags_counted_in_each(client, clock):
    """一道题打多个标签 → 在每个标签下各计一次（与发布抽题口径一致）。"""
    headers = admin_headers(client)
    create_question(client, headers, stem="双标签", answer=["A"], tags=["标签A", "标签B"])
    create_question(client, headers, stem="单标签", answer=["A"], tags=["标签A"])

    tags = {t["tag"]: t["question_count"] for t in client.get("/api/admin/tags", headers=headers).json()}
    assert tags["标签A"] == 2
    assert tags["标签B"] == 1


def test_duplicate_tag_on_same_question_counted_once(client, clock):
    """同一题重复打同一标签只算一次。"""
    headers = admin_headers(client)
    create_question(client, headers, stem="重复标签", answer=["A"], tags=["标签A", "标签A"])

    tags = {t["tag"]: t["question_count"] for t in client.get("/api/admin/tags", headers=headers).json()}
    assert tags["标签A"] == 1


def test_blank_tags_ignored(client, clock):
    """空标签不应出现在选项里（否则会配置出一个永远抽不到题的规则）。"""
    headers = admin_headers(client)
    create_question(client, headers, stem="无标签", answer=["A"], tags=[])
    create_question(client, headers, stem="有空标签", answer=["A"], tags=["", "有效标签"])

    tags = [t["tag"] for t in client.get("/api/admin/tags", headers=headers).json()]
    assert tags == ["有效标签"]


def test_tag_count_matches_publish_availability(client, clock):
    """标签题数口径必须与发布抽题一致。

    若某标签报告可用 2 题，则按该标签抽 2 题必须能发布成功；
    抽 3 题必须失败。这条防止"前端显示可用但实际抽不到"。
    """
    headers = admin_headers(client)
    for i in range(2):
        create_question(client, headers, stem=f"标签X题{i}", answer=["A"], score=5, tags=["标签X"])

    reported = {t["tag"]: t["question_count"] for t in client.get("/api/admin/tags", headers=headers).json()}
    assert reported["标签X"] == 2

    def make_exam(need: int, no_suffix: str):
        exam = create_exam(
            client,
            headers,
            title=f"抽{need}题",
            recruitment_no=f"ZP-TAG-{no_suffix}",
            start_at=clock.now() - timedelta(hours=1),
            end_at=clock.now() + timedelta(hours=1),
            rules=[{"tag": "标签X", "count": need}],
        )
        import_roster(client, headers, exam["id"], [("13800000001", "张三", "110101199001010011")])
        generate_invites(client, headers, exam["id"])
        return exam

    # 抽 2 题：与报告的可用数一致 → 必须成功
    ok_exam = make_exam(2, "OK")
    assert publish(client, headers, ok_exam["id"]).status_code == 200

    # 抽 3 题：超过可用数 → 必须失败并指名标签
    bad_exam = make_exam(3, "BAD")
    resp = publish(client, headers, bad_exam["id"])
    assert resp.status_code == 409
    assert "标签X" in resp.json()["detail"]


def test_tags_update_after_question_edit(client, clock):
    """题目标签被编辑后，标签列表随之变化（保持与题库一致）。"""
    headers = admin_headers(client)
    question = create_question(client, headers, stem="改标签", answer=["A"], tags=["旧标签"])

    assert [t["tag"] for t in client.get("/api/admin/tags", headers=headers).json()] == ["旧标签"]

    resp = client.put(
        f"/api/admin/questions/{question['id']}",
        headers=headers,
        json={
            "type": "single",
            "stem": "改标签",
            "options": question["options"],
            "answer": ["A"],
            "score": 5,
            "tags": ["新标签"],
            "analysis": "",
        },
    )
    assert resp.status_code == 200

    tags = [t["tag"] for t in client.get("/api/admin/tags", headers=headers).json()]
    assert tags == ["新标签"]


def test_tags_deleted_question_disappears(client, clock):
    """题目删除后，其独占标签不再出现在列表中。"""
    headers = admin_headers(client)
    question = create_question(client, headers, stem="待删除", answer=["A"], tags=["临时标签"])

    assert client.delete(f"/api/admin/questions/{question['id']}", headers=headers).status_code == 200
    assert client.get("/api/admin/tags", headers=headers).json() == []


def test_tags_requires_admin(client, clock):
    """标签接口需要管理员权限。"""
    scenario = build_running_scenario(client, clock, question_count=1)
    assert client.get("/api/admin/tags").status_code == 401

    token = scenario.login("张三")
    assert (
        client.get("/api/admin/tags", headers={"Authorization": f"Bearer {token}"}).status_code
        == 403
    )
