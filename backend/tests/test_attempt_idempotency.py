"""阶段 3：attempt 创建、交卷幂等、超时标记（测试方案 6.5、6.14）。

规格依据：架构 7.1、9.5 / spec 7.4、8
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from sqlmodel import Session, select

from app.models import Answer, Attempt
from app.models import loads_json
from tests.support import (
    build_running_scenario,
    create_attempt,
    submit,
)


def db_answers(app, attempt_id: int) -> list[Answer]:
    with Session(app.state.engine) as session:
        return list(
            session.exec(select(Answer).where(Answer.attempt_id == attempt_id)).all()
        )


def db_attempt(app, attempt_id: int) -> Attempt | None:
    with Session(app.state.engine) as session:
        return session.get(Attempt, attempt_id)


# --------------------------------------------------------------------------
# attempt 创建与复用
# --------------------------------------------------------------------------


def test_create_attempt_twice_returns_same_id(client, clock):
    """同一 (exam_id, user_id) 重复创建 → 返回已有 attempt_id，不新建。"""
    scenario = build_running_scenario(client, clock)
    token = scenario.login("张三")

    first = create_attempt(client, token, scenario.exam_id)
    second = create_attempt(client, token, scenario.exam_id)
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["attempt_id"] == second.json()["attempt_id"]


def test_attempt_response_contains_end_at(client, clock):
    """创建 attempt 返回 end_at，供前端计算倒计时。"""
    scenario = build_running_scenario(client, clock)
    token = scenario.login("张三")
    body = create_attempt(client, token, scenario.exam_id).json()
    assert set(body.keys()) == {"attempt_id", "end_at"}
    assert body["end_at"] == scenario.exam["end_at"]


def test_two_candidates_get_separate_attempts(client, clock):
    """不同考生各自独立 attempt。"""
    scenario = build_running_scenario(client, clock)
    id_zhang = scenario.start("张三")
    id_li = scenario.start("李四")
    assert id_zhang != id_li


def test_create_attempt_requires_running(client, clock):
    """仅进行中可创建 attempt。"""
    scenario = build_running_scenario(client, clock)
    token = scenario.login("张三")
    clock.set(scenario.end_at + timedelta(seconds=1))
    resp = create_attempt(client, token, scenario.exam_id)
    assert resp.status_code == 409
    assert resp.json()["detail"] == "考试已结束"


# --------------------------------------------------------------------------
# 交卷判分与幂等
# --------------------------------------------------------------------------


def test_first_submit_judges_and_scores(client, clock):
    """首次交卷：判分、写 answers、置 submitted_at 与 status。"""
    scenario = build_running_scenario(client, clock, question_count=3, score=10)
    token = scenario.login("张三")
    attempt_id = scenario.start("张三")

    resp = submit(client, token, attempt_id, scenario.answer_all_correct())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["score"] == 30.0
    assert body["status"] == "submitted"
    assert body["submitted_at"] is not None

    attempt = db_attempt(client.app, attempt_id)
    assert attempt.status == "submitted"
    assert attempt.score == 30.0
    assert len(db_answers(client.app, attempt_id)) == 3


def test_submit_is_idempotent(client, clock):
    """重复提交（相同答案）→ 返回结果与首次完全一致。"""
    scenario = build_running_scenario(client, clock, question_count=3)
    token = scenario.login("张三")
    attempt_id = scenario.start("张三")
    answers = scenario.answer_all_correct()

    first = submit(client, token, attempt_id, answers).json()
    second = submit(client, token, attempt_id, answers).json()

    assert first["score"] == second["score"]
    assert first["status"] == second["status"]
    assert first["submitted_at"] == second["submitted_at"]
    assert first["attempt_id"] == second["attempt_id"]


def test_resubmit_with_different_answers_keeps_first_result(client, clock):
    """重复提交（不同答案）→ 仍返回首次结果，answers 表不被覆盖。"""
    scenario = build_running_scenario(client, clock, question_count=3)
    token = scenario.login("张三")
    attempt_id = scenario.start("张三")

    first = submit(client, token, attempt_id, scenario.answer_all_correct()).json()
    before = {a.question_id: a.answer_json for a in db_answers(client.app, attempt_id)}

    # 全部改错
    wrong = [{"question_id": q["id"], "answer": ["D"]} for q in scenario.bank]
    second = submit(client, token, attempt_id, wrong).json()

    assert second["score"] == first["score"] == 30.0
    assert second["submitted_at"] == first["submitted_at"]

    after = {a.question_id: a.answer_json for a in db_answers(client.app, attempt_id)}
    assert after == before
    # 仍然是 3 行，没有因为二次提交而重复写入
    assert len(db_answers(client.app, attempt_id)) == 3


def test_unanswered_questions_recorded_as_zero(client, clock):
    """未作答题目的 Answer 行为 0 分且计为错误（标错率分母需要）。"""
    scenario = build_running_scenario(client, clock, question_count=3)
    token = scenario.login("张三")
    attempt_id = scenario.start("张三")

    only_first = [{"question_id": scenario.bank[0]["id"], "answer": ["A"]}]
    body = submit(client, token, attempt_id, only_first).json()
    assert body["score"] == 10.0

    rows = db_answers(client.app, attempt_id)
    assert len(rows) == 3
    scored = {r.question_id: r.score for r in rows}
    assert scored[scenario.bank[0]["id"]] == 10.0
    assert scored[scenario.bank[1]["id"]] == 0.0
    assert scored[scenario.bank[2]["id"]] == 0.0
    assert all(r.is_correct == 0 for r in rows if r.score == 0.0)


def test_answer_for_unknown_question_ignored(client, clock):
    """提交不属于本场试卷的题目 id → 忽略，不产生额外 answers 行。"""
    scenario = build_running_scenario(client, clock, question_count=2)
    token = scenario.login("张三")
    attempt_id = scenario.start("张三")

    payload = scenario.answer_all_correct() + [{"question_id": 999999, "answer": ["A"]}]
    body = submit(client, token, attempt_id, payload).json()
    assert body["score"] == 20.0
    assert len(db_answers(client.app, attempt_id)) == 2


def test_empty_submission_scores_zero(client, clock):
    """空答案交卷 → 0 分，且仍写出全部 0 分记录。"""
    scenario = build_running_scenario(client, clock, question_count=3)
    token = scenario.login("张三")
    attempt_id = scenario.start("张三")

    body = submit(client, token, attempt_id, []).json()
    assert body["score"] == 0.0
    rows = db_answers(client.app, attempt_id)
    assert len(rows) == 3
    assert all(r.score == 0.0 for r in rows)


def test_switch_record_persisted(client, clock):
    """切屏次数与时间点正确落库。"""
    scenario = build_running_scenario(client, clock, question_count=1)
    token = scenario.login("张三")
    attempt_id = scenario.start("张三")

    log = ["2026-09-19T10:01:23", "2026-09-19T10:05:00"]
    assert (
        submit(
            client,
            token,
            attempt_id,
            scenario.answer_all_correct(),
            switch_count=2,
            switch_log=log,
        ).status_code
        == 200
    )

    attempt = db_attempt(client.app, attempt_id)
    assert attempt.switch_count == 2
    assert loads_json(attempt.switch_log_json, []) == log


def test_switch_record_not_overwritten_on_resubmit(client, clock):
    """幂等重交不得覆盖首次落库的切屏记录。"""
    scenario = build_running_scenario(client, clock, question_count=1)
    token = scenario.login("张三")
    attempt_id = scenario.start("张三")

    submit(client, token, attempt_id, scenario.answer_all_correct(), switch_count=2,
           switch_log=["2026-09-19T10:01:23"])
    submit(client, token, attempt_id, scenario.answer_all_correct(), switch_count=99,
           switch_log=["2099-01-01T00:00:00"])

    attempt = db_attempt(client.app, attempt_id)
    assert attempt.switch_count == 2


# --------------------------------------------------------------------------
# 超时提交
# --------------------------------------------------------------------------


def test_timeout_submission_marked_and_still_scored(client, clock):
    """超时提交：标记 timeout_submitted，但正常判分。"""
    scenario = build_running_scenario(client, clock, question_count=3, score=10)
    token = scenario.login("张三")
    attempt_id = scenario.start("张三")

    clock.set(scenario.end_at + timedelta(minutes=5))
    body = submit(client, token, attempt_id, scenario.answer_all_correct()).json()
    assert body["status"] == "timeout_submitted"
    assert body["score"] == 30.0


def test_timeout_status_stays_after_resubmit(client, clock):
    """超时提交后再次提交 → status 保持 timeout_submitted。"""
    scenario = build_running_scenario(client, clock, question_count=2)
    token = scenario.login("张三")
    attempt_id = scenario.start("张三")

    clock.set(scenario.end_at + timedelta(minutes=1))
    first = submit(client, token, attempt_id, scenario.answer_all_correct()).json()
    assert first["status"] == "timeout_submitted"

    second = submit(client, token, attempt_id, []).json()
    assert second["status"] == "timeout_submitted"
    assert second["score"] == first["score"]


def test_submit_at_exact_end_at_is_not_timeout(client, clock):
    """边界：now == end_at 时交卷不算超时（含边界）。"""
    scenario = build_running_scenario(
        client, clock, question_count=1, start_offset=timedelta(hours=-1), end_offset=timedelta(0)
    )
    token = scenario.login("张三")
    attempt_id = scenario.start("张三")
    body = submit(client, token, attempt_id, scenario.answer_all_correct()).json()
    assert body["status"] == "submitted"


# --------------------------------------------------------------------------
# 并发（测试方案 6.14 的同一 attempt 部分）
# --------------------------------------------------------------------------


def test_concurrent_same_attempt_submit_judges_once(client, clock):
    """同一 attempt 并发提交 → 仅一次判分生效，两者返回一致。"""
    scenario = build_running_scenario(client, clock, question_count=3)
    token = scenario.login("张三")
    attempt_id = scenario.start("张三")
    answers = scenario.answer_all_correct()

    barrier = threading.Barrier(2)
    results: list[dict] = []
    errors: list[Exception] = []
    lock = threading.Lock()

    def worker():
        try:
            barrier.wait(timeout=10)
            resp = submit(client, token, attempt_id, answers)
            with lock:
                results.append({"status": resp.status_code, "body": resp.json()})
        except Exception as exc:  # noqa: BLE001
            with lock:
                errors.append(exc)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(worker) for _ in range(2)]
        for future in futures:
            future.result(timeout=30)

    assert not errors, errors
    assert len(results) == 2
    assert all(r["status"] == 200 for r in results)
    assert results[0]["body"]["score"] == results[1]["body"]["score"] == 30.0
    assert results[0]["body"]["submitted_at"] == results[1]["body"]["submitted_at"]

    # 只有一次判分生效：answers 恰好 3 行（无重复）
    rows = db_answers(client.app, attempt_id)
    assert len(rows) == 3


def test_concurrent_attempt_creation_returns_single_attempt(client, clock):
    """并发创建 attempt → 结果指向同一 attempt，库里只有一条。"""
    scenario = build_running_scenario(client, clock, question_count=1)
    token = scenario.login("张三")

    barrier = threading.Barrier(4)
    ids: list[int] = []
    lock = threading.Lock()

    def worker():
        barrier.wait(timeout=10)
        resp = create_attempt(client, token, scenario.exam_id)
        with lock:
            ids.append(resp.json()["attempt_id"])

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: worker(), range(4)))

    assert len(set(ids)) == 1

    with Session(client.app.state.engine) as session:
        rows = list(
            session.exec(
                select(Attempt).where(Attempt.exam_id == scenario.exam_id)
            ).all()
        )
    assert len(rows) == 1
