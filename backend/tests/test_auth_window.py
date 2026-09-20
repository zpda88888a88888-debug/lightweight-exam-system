"""阶段 2：考生登录与时间窗口（测试方案 6.4）。

规格依据：spec 4.1 / 架构 9.1
"""

from __future__ import annotations

from datetime import timedelta

from tests.support import build_running_scenario, create_attempt, get_paper, join, submit


def test_join_success_during_running_window(client, clock):
    """进行中：手机号 + 邀请码正确 → 返回 token 与考试信息。"""
    scenario = build_running_scenario(client, clock)
    resp = join(client, "13800000001", scenario.code("张三"))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["token"]
    # 字段集合精确匹配（架构 7.1 的 exam 结构）
    assert set(body["exam"].keys()) == {"id", "title", "start_at", "end_at"}
    assert body["exam"]["id"] == scenario.exam_id
    assert body["exam"]["title"] == "测试考试"


def test_join_before_start_rejected(client, clock):
    """未开始：now < start_at → 拒绝「考试未开始」。"""
    scenario = build_running_scenario(
        client,
        clock,
        start_offset=timedelta(hours=1),
        end_offset=timedelta(hours=2),
    )
    resp = join(client, "13800000001", scenario.code("张三"))
    assert resp.status_code == 409
    assert resp.json()["detail"] == "考试未开始"


def test_join_after_end_rejected(client, clock):
    """已结束：now > end_at → 拒绝「考试已结束」。"""
    scenario = build_running_scenario(
        client,
        clock,
        start_offset=timedelta(hours=-2),
        end_offset=timedelta(hours=-1),
    )
    resp = join(client, "13800000001", scenario.code("张三"))
    assert resp.status_code == 409
    assert resp.json()["detail"] == "考试已结束"


def test_wrong_invite_code_rejected(client, clock):
    """邀请码错误 → 拒绝。"""
    scenario = build_running_scenario(client, clock)
    resp = join(client, "13800000001", "000000")
    assert resp.status_code == 403


def test_phone_not_matching_invite_rejected(client, clock):
    """手机号与该邀请码不属于同一考生 → 拒绝（不能仅校验邀请码存在）。"""
    scenario = build_running_scenario(client, clock)
    zhang_code = scenario.code("张三")
    # 用张三的邀请码 + 李四的手机号
    resp = join(client, "13800000002", zhang_code)
    assert resp.status_code == 403

    # 用不在名单中的手机号
    resp2 = join(client, "13900000000", zhang_code)
    assert resp2.status_code == 403


def test_invite_code_without_phone_mismatch_ok(client, clock):
    """正确配对可通过，佐证上一条不是「全部拒绝」的假阳性。"""
    scenario = build_running_scenario(client, clock)
    assert join(client, "13800000002", scenario.code("李四")).status_code == 200


def test_already_submitted_cannot_join_again(client, clock):
    """已交卷考生再次登录 → 409「你已交卷，考试结束」（spec 4.1）。"""
    scenario = build_running_scenario(client, clock)
    token = scenario.login("张三")
    attempt_id = create_attempt(client, token, scenario.exam_id).json()["attempt_id"]
    assert submit(client, token, attempt_id, scenario.answer_all_correct()).status_code == 200

    resp = join(client, "13800000001", scenario.code("张三"))
    assert resp.status_code == 409
    assert resp.json()["detail"] == "你已交卷，考试结束"


def test_already_submitted_rejected_even_after_end(client, clock):
    """已交卷考生在考试结束之后登录 → 同样提示已交卷而非「考试已结束」。"""
    scenario = build_running_scenario(client, clock)
    token = scenario.login("张三")
    attempt_id = create_attempt(client, token, scenario.exam_id).json()["attempt_id"]
    submit(client, token, attempt_id, scenario.answer_all_correct())

    clock.set(scenario.end_at + timedelta(hours=1))
    resp = join(client, "13800000001", scenario.code("张三"))
    assert resp.status_code == 409
    assert resp.json()["detail"] == "你已交卷，考试结束"


def test_boundary_now_equals_start_at_allowed(client, clock):
    """边界：now == start_at → 允许（含边界）。"""
    scenario = build_running_scenario(
        client, clock, start_offset=timedelta(0), end_offset=timedelta(hours=1)
    )
    assert clock.now() == scenario.start_at
    assert join(client, "13800000001", scenario.code("张三")).status_code == 200


def test_boundary_now_equals_end_at_allowed(client, clock):
    """边界：now == end_at → 允许（含边界）。"""
    scenario = build_running_scenario(
        client, clock, start_offset=timedelta(hours=-1), end_offset=timedelta(0)
    )
    assert clock.now() == scenario.end_at
    token = scenario.login("张三")
    assert create_attempt(client, token, scenario.exam_id).status_code == 200
    assert get_paper(client, token, scenario.exam_id).status_code == 200


def test_paper_rejected_after_end(client, clock):
    """试卷仅在考试进行中可拉取；已结束 → 拒绝。"""
    scenario = build_running_scenario(client, clock)
    token = scenario.login("张三")
    clock.set(scenario.end_at + timedelta(seconds=1))
    resp = get_paper(client, token, scenario.exam_id)
    assert resp.status_code == 409
    assert resp.json()["detail"] == "考试已结束"


def test_paper_rejected_before_start(client, clock):
    """未开始 → 拒绝拉卷。"""
    scenario = build_running_scenario(
        client,
        clock,
        start_offset=timedelta(hours=1),
        end_offset=timedelta(hours=2),
    )
    # 未开始时也无法登录，这里直接构造 token 验证试卷接口的时间门禁
    from app.security import issue_candidate_token

    token = issue_candidate_token(
        "test-secret",
        clock.now(),
        3600,
        exam_id=scenario.exam_id,
        user_id=1,
        phone="13800000001",
    )
    resp = get_paper(client, token, scenario.exam_id)
    assert resp.status_code == 409
    assert resp.json()["detail"] == "考试未开始"


def test_missing_token_returns_401(client, clock):
    """未认证请求 → 401。"""
    scenario = build_running_scenario(client, clock)
    assert client.get(f"/api/exams/{scenario.exam_id}/paper").status_code == 401
    assert client.post(f"/api/exams/{scenario.exam_id}/attempts").status_code == 401


def test_admin_token_cannot_access_candidate_api(client, clock):
    """管理员 token 不能当作考生 token 使用。"""
    scenario = build_running_scenario(client, clock)
    admin_token = scenario.headers["Authorization"].split(" ", 1)[1]
    resp = get_paper(client, admin_token, scenario.exam_id)
    assert resp.status_code == 403


def test_other_exam_token_cannot_pull_paper(client, clock):
    """其他考试的 token 无法拉取本考试试卷。"""
    scenario_a = build_running_scenario(client, clock, recruitment_no="ZP-A", title="考试A")
    scenario_b = build_running_scenario(client, clock, recruitment_no="ZP-B", title="考试B")
    token_a = scenario_a.login("张三")
    resp = get_paper(client, token_a, scenario_b.exam_id)
    assert resp.status_code == 403


def test_invalid_token_rejected(client, clock):
    """签名不匹配 / 格式错误的 token → 401。"""
    scenario = build_running_scenario(client, clock)
    assert get_paper(client, "not-a-token", scenario.exam_id).status_code == 401

    forged = "aGVsbG8." + "x" * 10
    assert get_paper(client, forged, scenario.exam_id).status_code == 401
