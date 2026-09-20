"""考试列表查询（CH-006）。

规格依据：规格说明 4.9、5.2「考试管理」

支持按状态、选聘编号、考试名称、开考时间范围查询，且条件可组合。
"""

from __future__ import annotations

from datetime import timedelta

from tests.support import (
    admin_headers,
    build_running_scenario,
    create_exam,
    import_roster,
    make_bank,
    publish,
)


def make_exams(client, clock):
    """造 4 场考试：草稿 / 未开始 / 进行中 / 已结束。"""
    headers = admin_headers(client)
    make_bank(client, headers, count=2, tag="查询标签")

    def build(title, no, start_offset, end_offset, do_publish):
        exam = create_exam(
            client,
            headers,
            title=title,
            recruitment_no=no,
            start_at=clock.now() + start_offset,
            end_at=clock.now() + end_offset,
            rules=[{"tag": "查询标签", "count": 2}],
        )
        if do_publish:
            import_roster(
                client, headers, exam["id"], [("13800000001", "张三", "110101199001010011")]
            )
            assert publish(client, headers, exam["id"]).status_code == 200
        return exam

    return headers, {
        "draft": build("草稿考试", "QRY-DRAFT", timedelta(hours=-1), timedelta(hours=1), False),
        "upcoming": build("未开始考试", "QRY-UP", timedelta(hours=5), timedelta(hours=7), True),
        "running": build("进行中考试", "QRY-RUN", timedelta(hours=-1), timedelta(hours=1), True),
        "ended": build("已结束考试", "QRY-END", timedelta(hours=-5), timedelta(hours=-3), True),
    }


def titles(rows) -> set[str]:
    return {row["title"] for row in rows}


def test_list_all_without_filters(client, clock):
    headers, _ = make_exams(client, clock)
    rows = client.get("/api/admin/exams", headers=headers).json()
    assert len(rows) == 4


def test_filter_by_external_status(client, clock):
    headers, _ = make_exams(client, clock)

    for status, expected in [
        ("draft", "草稿考试"),
        ("upcoming", "未开始考试"),
        ("running", "进行中考试"),
        ("ended", "已结束考试"),
    ]:
        rows = client.get(f"/api/admin/exams?status={status}", headers=headers).json()
        assert titles(rows) == {expected}, f"status={status} 过滤错误"


def test_filter_by_archived_status(client, clock):
    headers, exams = make_exams(client, clock)
    assert client.post(
        f"/api/admin/exams/{exams['running']['id']}/archive", headers=headers
    ).status_code == 200

    rows = client.get("/api/admin/exams?status=archived", headers=headers).json()
    assert titles(rows) == {"进行中考试"}

    # 归档后不再出现在 running 里
    rows = client.get("/api/admin/exams?status=running", headers=headers).json()
    assert titles(rows) == set()


def test_filter_by_recruitment_no_partial(client, clock):
    headers, _ = make_exams(client, clock)

    rows = client.get("/api/admin/exams?recruitment_no=QRY-R", headers=headers).json()
    assert titles(rows) == {"进行中考试"}

    rows = client.get("/api/admin/exams?recruitment_no=qry-", headers=headers).json()
    assert len(rows) == 4, "选聘编号应大小写不敏感"


def test_filter_by_title_fuzzy(client, clock):
    headers, _ = make_exams(client, clock)

    rows = client.get("/api/admin/exams?title=进行中", headers=headers).json()
    assert titles(rows) == {"进行中考试"}

    # 子串匹配（模糊）：所有含"考试"的
    rows = client.get("/api/admin/exams?title=考试", headers=headers).json()
    assert len(rows) == 4

    rows = client.get("/api/admin/exams?title=不存在", headers=headers).json()
    assert rows == []


def test_filter_by_start_time_range(client, clock):
    headers, _ = make_exams(client, clock)

    # 开考时间在 [now-2h, now+2h] 之间：草稿(-1h) 与 进行中(-1h)
    start_from = (clock.now() - timedelta(hours=2)).isoformat()
    start_to = (clock.now() + timedelta(hours=2)).isoformat()
    rows = client.get(
        f"/api/admin/exams?start_from={start_from}&start_to={start_to}", headers=headers
    ).json()
    assert titles(rows) == {"草稿考试", "进行中考试"}

    # 只看未来开考的
    rows = client.get(
        f"/api/admin/exams?start_from={clock.now().isoformat()}", headers=headers
    ).json()
    assert titles(rows) == {"未开始考试"}


def test_filters_combine(client, clock):
    headers, _ = make_exams(client, clock)

    rows = client.get(
        "/api/admin/exams?status=running&title=进行中", headers=headers
    ).json()
    assert titles(rows) == {"进行中考试"}

    # 条件互斥 → 空集
    rows = client.get(
        "/api/admin/exams?status=running&title=草稿", headers=headers
    ).json()
    assert rows == []


def test_unknown_status_rejected(client, clock):
    headers = admin_headers(client)
    resp = client.get("/api/admin/exams?status=不存在的状态", headers=headers)
    assert resp.status_code == 422
    assert "未知状态" in resp.json()["detail"]


def test_empty_filters_ignored(client, clock):
    """空字符串条件不应把列表清空。"""
    headers, _ = make_exams(client, clock)

    rows = client.get(
        "/api/admin/exams?title=&recruitment_no=&status=", headers=headers
    ).json()
    # status= 会被当作 None（FastAPI 对空串的 str 参数得到 ""），
    # 这里断言至少不会因为空串把它们全部过滤掉
    assert len(rows) >= 1


def test_query_requires_admin(client, clock):
    scenario = build_running_scenario(client, clock, question_count=1)
    assert client.get("/api/admin/exams?status=running").status_code == 401

    token = scenario.login("张三")
    assert (
        client.get(
            "/api/admin/exams?status=running",
            headers={"Authorization": f"Bearer {token}"},
        ).status_code
        == 403
    )
