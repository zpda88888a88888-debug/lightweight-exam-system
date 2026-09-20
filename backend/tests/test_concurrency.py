"""阶段 7：200 并发交卷压测（测试方案 6.14 / 准出标准 E6）。

规格依据：spec 8 —— 50–200 人同时在线，交卷峰值 200 人同时提交不丢失数据。

说明：本测试使用 TestClient + 线程池模拟 200 个不同 attempt 同时提交。
测试环境与生产一致地开启 WAL + busy_timeout=5000，否则并发结论无效
（测试方案 风险 R2）。
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from sqlmodel import Session, select

from app.models import Answer, Attempt
from tests.support import (
    admin_headers,
    create_attempt_ok,
    create_exam,
    create_question,
    generate_invites,
    import_roster,
    join_ok,
    publish,
    submit,
)

CANDIDATE_COUNT = 200

pytestmark = pytest.mark.slow


def build_load_scenario(client, clock):
    """预置 200 名考生与 attempt。"""
    headers = admin_headers(client)
    question = create_question(
        client, headers, stem="并发题", question_type="multi",
        options=[
            {"key": "A", "text": "a"},
            {"key": "B", "text": "b"},
            {"key": "C", "text": "c"},
        ],
        answer=["A", "B", "C"], score=10, tags=["并发"],
    )
    exam = create_exam(
        client,
        headers,
        title="并发压测考试",
        recruitment_no="ZP-LOAD",
        start_at=clock.now() - timedelta(hours=1),
        end_at=clock.now() + timedelta(hours=1),
        rules=[{"tag": "并发", "count": 1}],
    )
    roster = [
        (f"138{i:08d}", f"考生{i}", f"1101011990{i:08d}")
        for i in range(CANDIDATE_COUNT)
    ]
    resp = import_roster(client, headers, exam["id"], roster)
    assert resp.status_code == 200, resp.text
    assert generate_invites(client, headers, exam["id"]).status_code == 200
    assert publish(client, headers, exam["id"]).status_code == 200

    from tests.support import invite_code_for

    attempts: list[tuple[str, int, int]] = []
    for phone, name, _id_card in roster:
        code = invite_code_for(client, headers, exam["id"], name)
        token = join_ok(client, phone, code)
        attempt_id = create_attempt_ok(client, token, exam["id"])
        attempts.append((token, attempt_id, int(name.replace("考生", ""))))

    return headers, exam, question, attempts


def test_200_concurrent_submissions_no_data_loss(client, clock):
    """200 个不同 attempt 并发提交 → 全部成功落库，answers 无丢失。"""
    headers, exam, question, attempts = build_load_scenario(client, clock)

    barrier = threading.Barrier(CANDIDATE_COUNT)
    results: list[tuple[int, dict]] = []
    errors: list[str] = []
    lock = threading.Lock()

    def worker(index: int, token: str, attempt_id: int):
        # 一半考生全对（满分），一半考生漏选（按比例得分），确保判分一致可校验
        selected = ["A", "B", "C"] if index % 2 == 0 else ["A", "B"]
        try:
            barrier.wait(timeout=60)
            resp = submit(
                client, token, attempt_id, [{"question_id": question["id"], "answer": selected}]
            )
            with lock:
                results.append((attempt_id, {"status": resp.status_code, "body": resp.json()}))
        except Exception as exc:  # noqa: BLE001
            with lock:
                errors.append(f"attempt {attempt_id}: {exc!r}")

    with ThreadPoolExecutor(max_workers=CANDIDATE_COUNT) as pool:
        futures = [pool.submit(worker, i, token, aid) for i, (token, aid, _) in enumerate(attempts)]
        for future in futures:
            future.result(timeout=180)

    assert errors == [], f"并发提交出现异常：{errors[:5]}"
    assert len(results) == CANDIDATE_COUNT

    # 全部 200 个请求成功，且无 database is locked
    for attempt_id, result in results:
        assert result["status"] == 200, f"attempt {attempt_id} 返回 {result}"
        assert "locked" not in str(result["body"]).lower()

    # 判分结果与串行期望一致：偶数满分、奇数 6.7
    scores = {aid: body["body"]["score"] for aid, body in results}
    assert set(scores.values()) == {10.0, 6.7}
    assert sum(1 for s in scores.values() if s == 10.0) == CANDIDATE_COUNT // 2

    # 数据库最终状态：200 个 attempt 全部为已提交，answers 恰好 200 行（无丢失、无重复）
    with Session(client.app.state.engine) as session:
        stored = list(
            session.exec(select(Attempt).where(Attempt.exam_id == exam["id"])).all()
        )
        assert len(stored) == CANDIDATE_COUNT
        assert all(a.status == "submitted" for a in stored)

        answer_rows = list(
            session.exec(
                select(Answer).where(Answer.attempt_id.in_([a.id for a in stored]))
            ).all()
        )
        assert len(answer_rows) == CANDIDATE_COUNT, "answers 行数不等于 attempt 数，存在丢失"

        # 每题每 attempt 恰好一行
        seen = {(a.attempt_id, a.question_id) for a in answer_rows}
        assert len(seen) == CANDIDATE_COUNT

        total_score = sum(float(a.score) for a in stored)
    expected_total = 100 * 10.0 + 100 * 6.7
    assert abs(total_score - expected_total) < 0.01, f"总分不符：{total_score} != {expected_total}"


def test_concurrent_submissions_are_idempotent_under_load(client, clock):
    """并发重复提交同一 attempt（重试场景）→ 只判分一次，结果一致。"""
    headers = admin_headers(client)
    question = create_question(
        client, headers, stem="重试题", answer=["A"], score=10, tags=["重试"]
    )
    exam = create_exam(
        client,
        headers,
        title="重试并发考试",
        recruitment_no="ZP-RETRY",
        start_at=clock.now() - timedelta(hours=1),
        end_at=clock.now() + timedelta(hours=1),
        rules=[{"tag": "重试", "count": 1}],
    )
    roster = [("13800000001", "张三", "110101199001010011")]
    import_roster(client, headers, exam["id"], roster)
    generate_invites(client, headers, exam["id"])
    assert publish(client, headers, exam["id"]).status_code == 200

    from tests.support import invite_code_for

    token = join_ok(client, "13800000001", invite_code_for(client, headers, exam["id"], "张三"))
    attempt_id = create_attempt_ok(client, token, exam["id"])

    payload = [{"question_id": question["id"], "answer": ["A"]}]
    barrier = threading.Barrier(8)
    results: list[dict] = []
    lock = threading.Lock()

    def worker():
        barrier.wait(timeout=30)
        resp = submit(client, token, attempt_id, payload)
        with lock:
            results.append({"status": resp.status_code, "body": resp.json()})

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: worker(), range(8)))

    assert all(r["status"] == 200 for r in results)
    scores = {r["body"]["score"] for r in results}
    timestamps = {r["body"]["submitted_at"] for r in results}
    assert scores == {10.0}
    assert len(timestamps) == 1, "并发重复提交产生了不同的判分时间"

    with Session(client.app.state.engine) as session:
        rows = list(session.exec(select(Answer).where(Answer.attempt_id == attempt_id)).all())
    assert len(rows) == 1, "并发重复提交导致 answers 重复写入"


def test_wal_mode_enabled_in_test_environment(client):
    """测试环境必须与生产一致开启 WAL，否则并发结论无效（风险 R2）。"""
    from sqlalchemy import text

    with Session(client.app.state.engine) as session:
        journal_mode = session.execute(text("PRAGMA journal_mode")).scalar()
        busy_timeout = session.execute(text("PRAGMA busy_timeout")).scalar()
    assert str(journal_mode).lower() == "wal"
    assert int(busy_timeout) == 5000
