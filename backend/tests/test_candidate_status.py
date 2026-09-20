"""考生管理：参与状态查询（CH-010）。

规格依据：规格说明 4.6、5.2「考生管理」

状态用于回答"谁在考试、谁没来"：
    not_started       未登录（从未用邀请码登录，没有 attempt）
    in_progress       答题中
    submitted         已交卷
    timeout_submitted 超时交卷
"""

from __future__ import annotations

from datetime import timedelta

from tests.support import build_running_scenario, submit, create_attempt, join_ok


def rows_by_name(client, headers, exam_id: int) -> dict[str, dict]:
    rows = client.get(f"/api/admin/exams/{exam_id}/candidates", headers=headers).json()
    return {row["name"]: row for row in rows}


def test_all_not_started_before_any_login(client, clock):
    """没人登录过 → 全部「未登录」。"""
    scenario = build_running_scenario(client, clock, question_count=1)
    rows = rows_by_name(client, scenario.headers, scenario.exam_id)

    assert len(rows) == 2
    for row in rows.values():
        assert row["status"] == "not_started"
        assert row["started_at"] is None
        assert row["submitted_at"] is None
        assert row["score"] is None


def test_in_progress_after_starting(client, clock):
    """登录并开始答题但未交卷 → 答题中（这才是"谁在考试"）。"""
    scenario = build_running_scenario(client, clock, question_count=1)
    token = scenario.login("张三")
    assert create_attempt(client, token, scenario.exam_id).status_code == 200

    rows = rows_by_name(client, scenario.headers, scenario.exam_id)
    assert rows["张三"]["status"] == "in_progress"
    assert rows["张三"]["started_at"] is not None
    assert rows["张三"]["submitted_at"] is None
    assert rows["张三"]["score"] is None
    # 李四没登录
    assert rows["李四"]["status"] == "not_started"


def test_submitted_status_and_score(client, clock):
    """交卷后 → 已交卷，带交卷时间与得分。"""
    scenario = build_running_scenario(client, clock, question_count=2, score=10)
    token = scenario.login("张三")
    attempt_id = scenario.start("张三")
    assert submit(client, token, attempt_id, scenario.answer_all_correct()).status_code == 200

    rows = rows_by_name(client, scenario.headers, scenario.exam_id)
    assert rows["张三"]["status"] == "submitted"
    assert rows["张三"]["score"] == 20.0
    assert rows["张三"]["submitted_at"] is not None
    assert rows["李四"]["status"] == "not_started"


def test_timeout_submitted_status(client, clock):
    """截止后才交卷 → 超时交卷。"""
    scenario = build_running_scenario(client, clock, question_count=1)
    token = scenario.login("张三")
    attempt_id = scenario.start("张三")

    clock.set(scenario.end_at + timedelta(minutes=3))
    assert submit(client, token, attempt_id, scenario.answer_all_correct()).status_code == 200

    rows = rows_by_name(client, scenario.headers, scenario.exam_id)
    assert rows["张三"]["status"] == "timeout_submitted"


def test_four_states_together(client, clock):
    """四种状态可以同时出现（前端据此做人数汇总）。"""
    scenario = build_running_scenario(
        client,
        clock,
        question_count=1,
        roster=[
            ("13800000001", "未登录者", "110101199001010011"),
            ("13800000002", "答题中者", "110101199001010022"),
            ("13800000003", "已交卷者", "110101199001010033"),
            ("13800000004", "超时者", "110101199001010044"),
        ],
    )

    # 答题中
    token_b = scenario.login("答题中者")
    assert create_attempt(client, token_b, scenario.exam_id).status_code == 200

    # 已交卷
    token_c = scenario.login("已交卷者")
    attempt_c = create_attempt(client, token_c, scenario.exam_id).json()["attempt_id"]
    assert submit(client, token_c, attempt_c, scenario.answer_all_correct()).status_code == 200

    # 超时交卷
    token_d = scenario.login("超时者")
    attempt_d = create_attempt(client, token_d, scenario.exam_id).json()["attempt_id"]
    clock.set(scenario.end_at + timedelta(minutes=1))
    assert submit(client, token_d, attempt_d, scenario.answer_all_correct()).status_code == 200

    rows = rows_by_name(client, scenario.headers, scenario.exam_id)
    assert rows["未登录者"]["status"] == "not_started"
    assert rows["答题中者"]["status"] == "in_progress"
    assert rows["已交卷者"]["status"] == "submitted"
    assert rows["超时者"]["status"] == "timeout_submitted"

    summary = {}
    for row in rows.values():
        summary[row["status"]] = summary.get(row["status"], 0) + 1
    assert summary == {
        "not_started": 1,
        "in_progress": 1,
        "submitted": 1,
        "timeout_submitted": 1,
    }


def test_status_still_present_when_codes_not_generated(client, clock):
    """未生成邀请码时同样能看到状态（此时必然是未登录）。"""
    from tests.support import build_draft_scenario

    scenario = build_draft_scenario(client, clock, roster=[("13800000001", "张三", "110101199001010011")])
    assert scenario.import_rows([("13800000001", "张三", "110101199001010011")]).status_code == 200

    rows = rows_by_name(client, scenario.headers, scenario.exam_id)
    assert rows["张三"]["status"] == "not_started"
    assert rows["张三"]["invite_code"] is None


def test_other_exam_attempt_does_not_leak(client, clock):
    """别的考试的 attempt 不应影响本场状态。"""
    first = build_running_scenario(client, clock, recruitment_no="ZP-S1", title="考试一",
                                  roster=[("13800000001", "张三", "110101199001010011")])
    token = first.login("张三")
    attempt_id = first.start("张三")
    assert submit(client, token, attempt_id, first.answer_all_correct()).status_code == 200

    second = build_running_scenario(client, clock, recruitment_no="ZP-S2", title="考试二",
                                    roster=[("13800000001", "张三", "110101199001010011")])
    rows = rows_by_name(client, second.headers, second.exam_id)
    assert rows["张三"]["status"] == "not_started", "不应把别的考试的作答算到本场"


def test_candidate_status_requires_admin(client, clock):
    scenario = build_running_scenario(client, clock, question_count=1)
    assert client.get(f"/api/admin/exams/{scenario.exam_id}/candidates").status_code == 401
