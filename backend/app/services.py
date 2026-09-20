"""业务服务层：组卷发布、attempt 生命周期、交卷判分、名单、邀请码、统计导出。

规格依据：架构 7、8、9.1–9.10 / 测试方案 6.5、6.7、6.8、6.9、6.13、6.14

关键实现说明：
    * 发布 = 校验标签题量 → 随机抽题 → 写 exam_questions 快照 → 冻结。
    * 交卷 = 单事务内判分并写 answers（含未作答题目的 0 分记录）。
    * 幂等 = 进程内按 attempt 加锁 + 数据库条件更新双保险；
      已产生判分结果的 attempt 再次提交直接返回既有结果，answers 不被覆盖。
    * 统计口径「有 attempt」= 已产生判分结果的 attempt（正常提交 / 超时提交）；
      未交卷的 attempt 不计入分母，在导出中视为缺考。
"""

from __future__ import annotations

import csv
import io
import random
import re
import threading
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Sequence

from sqlalchemy import func
from sqlalchemy import update as sa_update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.config import (
    ATTEMPT_IN_PROGRESS,
    ATTEMPT_SUBMITTED,
    ATTEMPT_TIMEOUT_SUBMITTED,
    EXPORT_COLUMNS,
    EXPORT_STATUS_ABSENT,
    EXPORT_STATUS_NORMAL,
    EXPORT_STATUS_TIMEOUT,
)
from app.domain import ExamStateError
from app.models import (
    Answer,
    Attempt,
    Exam,
    ExamCandidate,
    ExamQuestion,
    Question,
    User,
    dumps_json,
    loads_json,
)
from app.scoring import ScoringConfigError, judge
from app.shuffling import candidate_seed, shuffled_options
from app.stats import compute_pass_line, compute_wrong_rates

# --------------------------------------------------------------------------
# 提交并发保护
# --------------------------------------------------------------------------

#: 中国大陆手机号：11 位、以 1 开头（spec 4.6 建议的格式校验）
_PHONE_RE = re.compile(r"1\d{10}")

#: 单进程内按 attempt 串行化交卷；SQLite 单机部署下的确定性保障。
_submit_locks_guard = threading.Lock()
_submit_locks: dict[int, threading.Lock] = {}


def _lock_for_attempt(attempt_id: int) -> threading.Lock:
    with _submit_locks_guard:
        lock = _submit_locks.get(attempt_id)
        if lock is None:
            lock = threading.Lock()
            _submit_locks[attempt_id] = lock
        return lock


# --------------------------------------------------------------------------
# 组卷发布
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PublishResult:
    exam_id: int
    question_count: int
    total_score: float


def parse_rules(exam: Exam) -> list[dict]:
    """读取组卷规则 [{tag, count}]。"""
    settings = loads_json(exam.settings_json, {})
    rules = settings.get("rules") or []
    return [r for r in rules if isinstance(r, dict)]


def _question_tags(question: Question) -> set[str]:
    return {str(t) for t in loads_json(question.tags_json, [])}


def publish_exam(
    session: Session,
    exam: Exam,
    now: datetime,
    *,
    rng: random.Random | None = None,
) -> PublishResult:
    """发布考试：随机抽题生成快照，并冻结。

    Raises:
        ExamStateError: 非草稿状态，或某标签题量不足（错误信息含标签名）。
    """
    from app.domain import ensure_draft

    ensure_draft(exam)

    rules = parse_rules(exam)
    if not rules:
        raise ExamStateError("组卷规则为空，无法发布", status_code=400)

    rng = rng or random.Random()

    all_questions = list(session.exec(select(Question)).all())

    selected: list[Question] = []
    selected_ids: set[int] = set()
    insufficiency: list[tuple[str, int, int]] = []

    for rule in rules:
        tag = str(rule.get("tag", "")).strip()
        try:
            need = int(rule.get("count", 0))
        except (TypeError, ValueError):
            need = 0
        if not tag or need <= 0:
            raise ExamStateError(f"组卷规则非法：{rule!r}", status_code=400)

        pool = [
            q
            for q in all_questions
            if tag in _question_tags(q) and q.id not in selected_ids
        ]
        if len(pool) < need:
            insufficiency.append((tag, need, len(pool)))
            continue

        picked = rng.sample(pool, need)
        for q in picked:
            selected_ids.add(q.id)
            selected.append(q)

    if insufficiency:
        detail = "；".join(
            f"标签「{tag}」需要 {need} 题，题库仅有 {have} 题"
            for tag, need, have in insufficiency
        )
        raise ExamStateError(f"题库题量不足，发布失败：{detail}", status_code=409)

    # 写入快照（幂等：先清空再写，保证可重复执行不产生重复行）
    for existing in session.exec(
        select(ExamQuestion).where(ExamQuestion.exam_id == exam.id)
    ).all():
        session.delete(existing)
    session.flush()

    # 题目顺序全局随机固定
    rng.shuffle(selected)
    total_score = 0.0
    for seq, question in enumerate(selected):
        assert question.id is not None
        session.add(
            ExamQuestion(
                exam_id=exam.id,
                question_id=question.id,
                seq=seq,
                score=question.score,
            )
        )
        total_score += float(question.score)

    exam.status = "published"
    exam.published_at = now
    session.add(exam)
    session.commit()

    return PublishResult(
        exam_id=exam.id, question_count=len(selected), total_score=round(total_score, 1)
    )


# --------------------------------------------------------------------------
# 试卷与 attempt
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PaperQuestion:
    question: Question
    seq: int
    score: float


def load_paper_questions(session: Session, exam_id: int) -> list[PaperQuestion]:
    """按快照顺序加载试卷题目。"""
    rows = list(
        session.exec(
            select(ExamQuestion).where(ExamQuestion.exam_id == exam_id).order_by(ExamQuestion.seq)
        ).all()
    )
    if not rows:
        return []
    question_ids = [r.question_id for r in rows]
    questions = {
        q.id: q
        for q in session.exec(select(Question).where(Question.id.in_(question_ids))).all()
    }
    result: list[PaperQuestion] = []
    for row in rows:
        question = questions.get(row.question_id)
        if question is not None:
            result.append(PaperQuestion(question=question, seq=row.seq, score=row.score))
    return result


def build_paper_payload(session: Session, exam: Exam, user: User) -> dict:
    """构造试卷响应（绝不含 answer / analysis）。

    选项顺序按考生种子乱序；题目顺序为快照全局固定顺序。
    """
    roster = session.exec(
        select(ExamCandidate).where(
            ExamCandidate.exam_id == exam.id, ExamCandidate.user_id == user.id
        )
    ).first()
    seed = candidate_seed(user.phone, roster.invite_code if roster and roster.invite_code else "")

    items = load_paper_questions(session, exam.id)
    questions = []
    for item in items:
        options = loads_json(item.question.options_json, [])
        options = shuffled_options(
            question_type=item.question.type,
            question_id=item.question.id,
            options=options,
            seed_text=seed,
        )
        questions.append(
            {
                "id": item.question.id,
                "type": item.question.type,
                "stem": item.question.stem,
                "options": options,
            }
        )
    return {
        "exam": {
            "id": exam.id,
            "title": exam.title,
            "start_at": exam.start_at,
            "end_at": exam.end_at,
        },
        "questions": questions,
    }


def get_or_create_attempt(session: Session, exam: Exam, user: User, now: datetime) -> Attempt:
    """创建 attempt；已存在则返回既有记录（一人一场仅一个）。

    并发下由 UNIQUE(exam_id, user_id) 兜底：插入冲突时回查既有记录。
    """
    attempt = session.exec(
        select(Attempt).where(Attempt.exam_id == exam.id, Attempt.user_id == user.id)
    ).first()
    if attempt is not None:
        return attempt

    attempt = Attempt(
        exam_id=exam.id,
        user_id=user.id,
        started_at=now,
        status=ATTEMPT_IN_PROGRESS,
        switch_count=0,
        switch_log_json="[]",
    )
    session.add(attempt)
    try:
        session.commit()
    except IntegrityError:
        # 并发下另一请求已创建：回滚并返回既有记录
        session.rollback()
        existing = session.exec(
            select(Attempt).where(Attempt.exam_id == exam.id, Attempt.user_id == user.id)
        ).first()
        if existing is None:
            raise
        return existing
    session.refresh(attempt)
    return attempt


# --------------------------------------------------------------------------
# 交卷判分
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SubmitResult:
    attempt_id: int
    score: float
    status: str
    submitted_at: datetime


def _finalize_attempt(
    session: Session,
    attempt: Attempt,
    exam: Exam,
    answers_payload: Sequence[dict],
    switch_count: int,
    switch_log: Sequence[str],
    now: datetime,
) -> SubmitResult:
    """在事务内判分并落库，返回最终结果。

    调用方须已持有该 attempt 的锁。
    """
    # 服务端以 end_at 为准判定是否超时；超时仍正常判分
    timed_out = now > exam.end_at
    final_status = ATTEMPT_TIMEOUT_SUBMITTED if timed_out else ATTEMPT_SUBMITTED

    submitted: dict[int, list[str]] = {}
    for entry in answers_payload:
        qid = entry.get("question_id")
        answer = entry.get("answer") or []
        if qid is None:
            continue
        if isinstance(answer, str):
            answer = [answer]
        submitted[int(qid)] = [str(a) for a in answer]

    total = 0.0
    paper_items = load_paper_questions(session, exam.id)

    for item in paper_items:
        assert item.question.id is not None
        selected = submitted.get(item.question.id, [])
        correct = loads_json(item.question.answer_json, [])
        try:
            earned = judge(item.question.type, correct, selected, item.score)
        except ScoringConfigError:
            # 题目配置错误不应让考生无法交卷：该题记 0 分
            earned = 0.0
        is_correct = 1 if earned >= float(item.score) else 0
        total += earned
        session.add(
            Answer(
                attempt_id=attempt.id,
                question_id=item.question.id,
                answer_json=dumps_json(selected),
                is_correct=is_correct,
                score=earned,
            )
        )

    total = round(total, 1)

    switch_count_value = int(switch_count or 0)
    switch_log_value = dumps_json([str(x) for x in (switch_log or [])])

    # 条件更新：仅当 attempt 仍为 in_progress 时本次判分才生效。
    # 这是跨线程/跨进程的正确性闸门：并发下只有一个事务能把状态推进到终态，
    # 失败者 rowcount == 0，回滚掉刚写入的 answers 并返回既有结果。
    stmt = (
        sa_update(Attempt)
        .where(Attempt.id == attempt.id, Attempt.status == ATTEMPT_IN_PROGRESS)
        .values(
            score=total,
            status=final_status,
            submitted_at=now,
            switch_count=switch_count_value,
            switch_log_json=switch_log_value,
        )
    )
    result = session.execute(stmt)

    if result.rowcount != 1:
        session.rollback()
        current = session.get(Attempt, attempt.id)
        if current is None:  # pragma: no cover - 极端竞态
            raise ExamStateError("attempt 不存在", status_code=404)
        return _existing_result(session, current)

    session.commit()
    session.expire_all()
    final = session.get(Attempt, attempt.id)

    return SubmitResult(
        attempt_id=final.id,
        score=float(final.score),
        status=final.status,
        submitted_at=final.submitted_at,
    )


def _existing_result(session: Session, attempt: Attempt) -> SubmitResult:
    """已判分 attempt 的既有结果（幂等返回）。"""
    session.refresh(attempt)
    return SubmitResult(
        attempt_id=attempt.id,
        score=float(attempt.score),
        status=attempt.status,
        submitted_at=attempt.submitted_at,
    )


def submit_attempt(
    session: Session,
    attempt: Attempt,
    exam: Exam,
    answers_payload: Sequence[dict],
    switch_count: int,
    switch_log: Sequence[str],
    now: datetime,
) -> SubmitResult:
    """交卷（幂等）。

    已产生判分结果的 attempt 再次提交，无论答案是否不同，
    一律返回首次结果且不改写 answers 表。
    """
    lock = _lock_for_attempt(attempt.id)
    with lock:
        # 关键：丢弃调用方可能已陈旧的读快照。
        # WAL 下长事务会固定在旧快照上，若不在锁内重新开启事务，
        # 会读不到「前一个并发请求刚提交的终态」，导致重复判分。
        attempt_id = attempt.id
        session.rollback()
        fresh = session.get(Attempt, attempt_id)
        if fresh is None:
            raise ExamStateError("attempt 不存在", status_code=404)

        if fresh.status != ATTEMPT_IN_PROGRESS:
            return _existing_result(session, fresh)

        return _finalize_attempt(
            session, fresh, exam, answers_payload, switch_count, switch_log, now
        )


# --------------------------------------------------------------------------
# 名单与邀请码
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class RosterImportResult:
    users_created: int
    users_updated: int
    linked: int
    total_rows: int


def import_roster(
    session: Session,
    exam: Exam,
    rows: Sequence[dict],
    now: datetime,
) -> RosterImportResult:
    """导入名单。

    口径（业务方确认 R1）：身份证号已存在则关联已有考生并更新姓名、手机号（upsert），
    不报错。身份证号仍是全局唯一键。
    """
    created = updated = linked = 0
    seen_id_cards: set[str] = set()

    for row in rows:
        phone = (row.get("手机号") or row.get("phone") or "").strip()
        name = (row.get("姓名") or row.get("name") or "").strip()
        id_card = (row.get("身份证号") or row.get("id_card") or "").strip()
        if not phone and not name and not id_card:
            continue  # 空行
        if not id_card:
            raise ValueError("身份证号不能为空")
        # 手机号格式校验（spec 4.6 建议项）：11 位、以 1 开头
        if phone and not _PHONE_RE.fullmatch(phone):
            raise ValueError(f"手机号格式非法：{phone}")

        # 同一批次内重复身份证号：合并为一条
        if id_card in seen_id_cards:
            continue
        seen_id_cards.add(id_card)

        user = session.exec(select(User).where(User.id_card == id_card)).first()
        if user is None:
            user = User(name=name, phone=phone, id_card=id_card, created_at=now)
            session.add(user)
            session.flush()
            created += 1
        else:
            # upsert：更新姓名与手机号
            changed = False
            if name and user.name != name:
                user.name = name
                changed = True
            if phone and user.phone != phone:
                user.phone = phone
                changed = True
            if changed:
                session.add(user)
                updated += 1

        link = session.exec(
            select(ExamCandidate).where(
                ExamCandidate.exam_id == exam.id, ExamCandidate.user_id == user.id
            )
        ).first()
        if link is None:
            session.add(
                ExamCandidate(
                    exam_id=exam.id, user_id=user.id, invite_code=None, created_at=now
                )
            )
            linked += 1

    session.commit()
    return RosterImportResult(
        users_created=created, users_updated=updated, linked=linked, total_rows=len(rows)
    )


def generate_invite_codes(
    session: Session,
    exam: Exam,
    generator,
    now: datetime,
) -> int:
    """为名单中所有考生生成全局唯一 6 位数字邀请码（全部覆盖）。

    仅草稿状态可操作；重新生成会作废旧码。
    """
    from app.domain import ensure_draft

    ensure_draft(exam)

    roster = list(
        session.exec(select(ExamCandidate).where(ExamCandidate.exam_id == exam.id)).all()
    )
    # 先清空本场旧码，避免与新生成本场冲突
    for link in roster:
        link.invite_code = None
    session.flush()

    for link in roster:
        link.invite_code = generator.generate_unique(session)
        session.add(link)

    session.commit()
    return len(roster)


# --------------------------------------------------------------------------
# 统计与导出
# --------------------------------------------------------------------------


def _finalized_attempts(session: Session, exam_id: int) -> list[Attempt]:
    """已产生判分结果的 attempt（统计与导出的分母口径）。"""
    return list(
        session.exec(
            select(Attempt).where(
                Attempt.exam_id == exam_id,
                Attempt.status.in_([ATTEMPT_SUBMITTED, ATTEMPT_TIMEOUT_SUBMITTED]),
            )
        ).all()
    )


@dataclass(frozen=True)
class ExportRow:
    user_id: int
    recruitment_no: str
    exam_title: str
    phone: str
    name: str
    id_card: str
    invite_code: str
    started_at: datetime | None
    submitted_at: datetime | None
    score: float | None
    is_pass: bool | None
    switch_count: int
    switch_log: list[str]
    status: str


def build_result_rows(session: Session, exam: Exam) -> list[ExportRow]:
    """构造成绩行：名单左连 attempt，缺考也出现。

    成绩行按得分降序（缺考最后），便于阅读。
    """
    roster = list(
        session.exec(select(ExamCandidate).where(ExamCandidate.exam_id == exam.id)).all()
    )
    user_ids = [r.user_id for r in roster]
    users = {
        u.id: u
        for u in session.exec(select(User).where(User.id.in_(user_ids))).all()
    } if user_ids else {}

    attempts = {
        a.user_id: a for a in _finalized_attempts(session, exam.id)
    }

    scores = [float(a.score or 0.0) for a in attempts.values()]
    pass_line = compute_pass_line(scores, exam.pass_ratio)

    rows: list[ExportRow] = []
    for link in roster:
        user = users.get(link.user_id)
        if user is None:
            continue
        attempt = attempts.get(link.user_id)
        if attempt is None:
            rows.append(
                ExportRow(
                    user_id=user.id,
                    recruitment_no=exam.recruitment_no,
                    exam_title=exam.title,
                    phone=user.phone,
                    name=user.name,
                    id_card=user.id_card,
                    invite_code=link.invite_code or "",
                    started_at=None,
                    submitted_at=None,
                    score=None,
                    is_pass=None,
                    switch_count=0,
                    switch_log=[],
                    status=EXPORT_STATUS_ABSENT,
                )
            )
            continue

        score = float(attempt.score or 0.0)
        rows.append(
            ExportRow(
                user_id=user.id,
                recruitment_no=exam.recruitment_no,
                exam_title=exam.title,
                phone=user.phone,
                name=user.name,
                id_card=user.id_card,
                invite_code=link.invite_code or "",
                started_at=attempt.started_at,
                submitted_at=attempt.submitted_at,
                score=score,
                is_pass=pass_line.is_pass(score),
                switch_count=attempt.switch_count,
                switch_log=loads_json(attempt.switch_log_json, []),
                status=(
                    EXPORT_STATUS_TIMEOUT
                    if attempt.status == ATTEMPT_TIMEOUT_SUBMITTED
                    else EXPORT_STATUS_NORMAL
                ),
            )
        )

    rows.sort(key=lambda r: (r.score is None, -(r.score or 0.0), r.name))
    return rows


def _fmt_dt(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else ""


def export_results_csv(session: Session, exam: Exam) -> str:
    """生成成绩 CSV（列顺序与命名见 spec 7.3）。"""
    rows = build_result_rows(session, exam)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(list(EXPORT_COLUMNS))
    for row in rows:
        writer.writerow(
            [
                row.recruitment_no,
                row.exam_title,
                row.phone,
                row.name,
                row.id_card,
                row.invite_code,
                _fmt_dt(row.started_at),
                _fmt_dt(row.submitted_at),
                "" if row.score is None else f"{row.score:.1f}",
                "" if row.is_pass is None else ("是" if row.is_pass else "否"),
                row.switch_count,
                dumps_json(row.switch_log),
                row.status,
            ]
        )
    return buffer.getvalue()


def export_invite_codes_csv(session: Session, exam: Exam) -> str:
    """生成邀请码分发 CSV。"""
    roster = list(
        session.exec(select(ExamCandidate).where(ExamCandidate.exam_id == exam.id)).all()
    )
    user_ids = [r.user_id for r in roster]
    users = {
        u.id: u
        for u in session.exec(select(User).where(User.id.in_(user_ids))).all()
    } if user_ids else {}

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(["手机号", "姓名", "身份证号", "邀请码"])
    for link in roster:
        user = users.get(link.user_id)
        if user is None:
            continue
        writer.writerow([user.phone, user.name, user.id_card, link.invite_code or ""])
    return buffer.getvalue()


@dataclass(frozen=True)
class StatsResult:
    total_candidates: int
    attempt_count: int
    absent_count: int
    average_score: float
    pass_ratio: int
    pass_line: float | None
    pass_count: int
    pass_rate: float
    questions: list[dict]


def compute_stats(session: Session, exam: Exam) -> StatsResult:
    """统计：平均分、及格率、题目标错率。"""
    total_candidates = session.exec(
        select(func.count()).select_from(ExamCandidate).where(ExamCandidate.exam_id == exam.id)
    ).one()

    attempts = _finalized_attempts(session, exam.id)
    scores = [float(a.score or 0.0) for a in attempts]

    pass_line = compute_pass_line(scores, exam.pass_ratio)
    average = sum(scores) / len(scores) if scores else 0.0

    # 题目标错率：每题的 (得分, 满分) 序列，仅已判分 attempt
    attempt_ids = [a.id for a in attempts]
    paper_items = load_paper_questions(session, exam.id)
    full_scores = {item.question.id: float(item.score) for item in paper_items}
    per_question: dict[int, list[tuple[float, float]]] = defaultdict(list)

    if attempt_ids:
        answers = list(
            session.exec(select(Answer).where(Answer.attempt_id.in_(attempt_ids))).all()
        )
        for answer in answers:
            full = full_scores.get(answer.question_id)
            if full is None:
                continue  # 非本场快照题目，忽略
            per_question[answer.question_id].append((float(answer.score), full))

    wrong_rates = compute_wrong_rates(per_question)

    questions = []
    for item in paper_items:
        assert item.question.id is not None
        questions.append(
            {
                "question_id": item.question.id,
                "seq": item.seq,
                "wrong_rate": wrong_rates.get(item.question.id, 0.0),
                "full_score": float(item.score),
            }
        )

    return StatsResult(
        total_candidates=int(total_candidates),
        attempt_count=len(attempts),
        absent_count=max(0, int(total_candidates) - len(attempts)),
        average_score=round(average, 1),
        pass_ratio=exam.pass_ratio,
        pass_line=pass_line.threshold,
        pass_count=pass_line.pass_count,
        pass_rate=round(pass_line.pass_rate, 4),
        questions=questions,
    )


def parse_roster_csv(text: str) -> list[dict]:
    """解析名单 CSV。

    Raises:
        ValueError: 表头不符合 `手机号,姓名,身份证号`（顺序与命名须一致）。
    """
    text = text.lstrip("\ufeff")
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration as exc:
        raise ValueError("CSV 内容为空") from exc

    header = [h.strip() for h in header]
    expected = ["手机号", "姓名", "身份证号"]
    if header != expected:
        raise ValueError(
            f"表头必须为「手机号,姓名,身份证号」，实际为「{','.join(header)}」"
        )

    rows: list[dict] = []
    for raw in reader:
        if not raw or all(not c.strip() for c in raw):
            continue  # 空行
        if len(raw) < 3:
            raise ValueError(f"名单行缺少列：{raw!r}")
        rows.append({"手机号": raw[0].strip(), "姓名": raw[1].strip(), "身份证号": raw[2].strip()})
    return rows


def compute_question_stats(session: Session) -> dict[int, dict]:
    """计算每道题的统计（CH-008）。

    - 上次被抽中：试卷快照 exam_questions 中，该题所属考试 published_at 最新的一场；
    - 累计正确率：Answers 表按题目聚合，未作答的行（得分 0）也算进分母。

    只在题库列表接口调用；数据量级为"题目数 × 抽中次数"，内存计算足够。
    """
    drawn: dict[int, tuple[datetime, Exam]] = {}
    link_stmt = select(ExamQuestion, Exam).join(Exam, ExamQuestion.exam_id == Exam.id)
    for link, exam in session.exec(link_stmt).all():
        moment = exam.published_at or exam.created_at
        current = drawn.get(link.question_id)
        if current is None or moment > current[0]:
            drawn[link.question_id] = (moment, exam)

    aggregates: dict[int, tuple[int, int]] = {}
    agg_stmt = select(
        Answer.question_id, func.count(Answer.id), func.sum(Answer.is_correct)
    ).group_by(Answer.question_id)
    for question_id, total, correct in session.exec(agg_stmt).all():
        aggregates[question_id] = (int(total or 0), int(correct or 0))

    result: dict[int, dict] = {}
    for question_id in set(drawn) | set(aggregates):
        moment, exam = drawn.get(question_id, (None, None))
        total, correct = aggregates.get(question_id, (0, 0))
        result[question_id] = dict(
            last_drawn_exam_id=exam.id if exam else None,
            last_drawn_exam_title=exam.title if exam else None,
            last_drawn_at=moment,
            answer_count=total,
            correct_count=correct,
            # 从未被作答 → None（界面显示"暂无"，避免被误读为 0%）
            correct_rate=round(correct / total, 4) if total else None,
        )
    return result


#: 题库导出 CSV 的列（选项列按本次导出的最大选项数动态展开，最少 4 列）
QUESTION_EXPORT_HEAD = ("ID", "题型", "题干")
QUESTION_EXPORT_TAIL = ("正确答案", "分值", "标签", "解析",
                        "上次抽中考试", "上次抽中时间", "累计正确率")


def _option_label(index: int) -> str:
    """0→A，25→Z，26→AA（与前端 lib/optionLabels.ts 保持一致）。"""
    label = ""
    value = index
    while True:
        label = chr(65 + value % 26) + label
        value = value // 26 - 1
        if value < 0:
            break
    return label


def export_questions_csv(session: Session) -> str:
    """导出题库为 CSV（CH-011）。

    面向人工阅读与备份：选项按题库原始顺序展开成独立列，
    正确答案用原始选项标识（非显示位置）。

    统计列在"从未被抽中/作答"时留空，而不是写 0 —— 避免被误读。
    """
    from app.config import QUESTION_TYPE_LABELS

    questions = list(session.exec(select(Question).order_by(Question.id)).all())
    stats = compute_question_stats(session)

    parsed = [(q, loads_json(q.options_json, [])) for q in questions]
    max_options = max([len(options) for _, options in parsed] + [4])

    header = list(QUESTION_EXPORT_HEAD)
    header += [f"选项{_option_label(i)}" for i in range(max_options)]
    header += list(QUESTION_EXPORT_TAIL)

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(header)

    for question, options in parsed:
        texts = [str(option.get("text", "")) for option in options]
        texts += [""] * (max_options - len(texts))

        answer = loads_json(question.answer_json, [])
        tags = loads_json(question.tags_json, [])
        stat = stats.get(question.id) or {}

        rate = stat.get("correct_rate")
        drawn_at = stat.get("last_drawn_at")

        writer.writerow(
            [
                question.id,
                QUESTION_TYPE_LABELS.get(question.type, question.type),
                question.stem,
                *texts,
                ",".join(str(a) for a in answer),
                question.score,
                ",".join(str(t) for t in tags),
                question.analysis or "",
                stat.get("last_drawn_exam_title") or "",
                _fmt_dt(drawn_at),
                f"{rate * 100:.1f}%" if rate is not None else "",
            ]
        )

    return buffer.getvalue()
