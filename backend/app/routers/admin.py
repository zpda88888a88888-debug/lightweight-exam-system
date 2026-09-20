"""管理端路由。

规格依据：架构 7.2、9.2、9.3、9.6、9.8、9.10

状态门禁（发布即冻结，架构 9.3）：除查询外，所有写操作都先要求草稿状态
（归档与发布本身除外）。
"""

from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import delete as sa_delete
from sqlalchemy import func
from sqlmodel import Session, select

from app.config import PARTICIPATION_NOT_STARTED, QUESTION_TYPES, STATUS_ARCHIVED
from app.config import (
    EXTERNAL_ARCHIVED,
    EXTERNAL_DRAFT,
    EXTERNAL_ENDED,
    EXTERNAL_RUNNING,
    EXTERNAL_UPCOMING,
)
from app.domain import (
    ensure_deletable,
    ensure_draft,
    ensure_published,
    external_status,
)
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
from app.schemas import (
    AdminLoginRequest,
    AdminLoginResponse,
    AdminPaperOut,
    AdminPaperQuestionOut,
    CandidateRowOut,
    ExamIn,
    ExamOut,
    GenerateInvitesRequest,
    GenerateInvitesResponse,
    PublishResponse,
    QuestionImportRequest,
    QuestionImportResult,
    QuestionIn,
    QuestionOut,
    QuestionStatsOut,
    RosterImportResponse,
    ResultRowOut,
    ResultsResponse,
    StatsQuestionRow,
    StatsResponse,
    TagCountOut,
)
from app.security import InviteCodeGenerator, issue_admin_token, verify_admin_credentials
from app.services import (
    build_result_rows,
    compute_question_stats,
    compute_stats,
    export_invite_codes_csv,
    export_questions_csv,
    export_results_csv,
    generate_invite_codes,
    import_roster,
    load_paper_questions,
    parse_roster_csv,
    publish_exam,
)
from app.stats import VALID_PASS_RATIOS

JUDGE_DEFAULT_OPTIONS = [{"key": "对", "text": "正确"}, {"key": "错", "text": "错误"}]

#: 允许按对外状态查询的取值集合
VALID_EXTERNAL_STATUSES = frozenset(
    {EXTERNAL_DRAFT, EXTERNAL_UPCOMING, EXTERNAL_RUNNING, EXTERNAL_ENDED, EXTERNAL_ARCHIVED}
)


def _validate_question(payload: QuestionIn) -> tuple[str, str, str]:
    """校验题目并返回 (options_json, answer_json, tags_json)。"""
    if payload.type not in QUESTION_TYPES:
        raise HTTPException(status_code=422, detail=f"未知题型：{payload.type}")

    options = [o.model_dump() for o in payload.options]
    if payload.type == "judge" and not options:
        options = JUDGE_DEFAULT_OPTIONS

    if not options:
        raise HTTPException(status_code=422, detail="选项不能为空")

    keys = [o["key"] for o in options]
    if len(set(keys)) != len(keys):
        raise HTTPException(status_code=422, detail="选项标识重复")

    answer = list(payload.answer)
    if not answer:
        raise HTTPException(status_code=422, detail="正确答案不能为空")
    if payload.type == "single" and len(set(answer)) != 1:
        raise HTTPException(status_code=422, detail="单选题必须且只能有 1 个正确答案")
    if payload.type == "judge" and len(set(answer)) != 1:
        raise HTTPException(status_code=422, detail="判断题必须且只能有 1 个正确答案")
    unknown = [a for a in answer if a not in keys]
    if unknown:
        raise HTTPException(status_code=422, detail=f"正确答案含不存在的选项标识：{unknown}")

    return dumps_json(options), dumps_json(answer), dumps_json(list(payload.tags))


def _question_out(question: Question, stats: QuestionStatsOut | None = None) -> QuestionOut:
    return QuestionOut(
        id=question.id,
        type=question.type,
        stem=question.stem,
        options=loads_json(question.options_json, []),
        answer=loads_json(question.answer_json, []),
        score=question.score,
        tags=loads_json(question.tags_json, []),
        analysis=question.analysis,
        updated_at=question.updated_at,
        stats=stats,
    )


def _exam_out(exam: Exam, now: datetime) -> ExamOut:
    settings = loads_json(exam.settings_json, {})
    return ExamOut(
        id=exam.id,
        title=exam.title,
        recruitment_no=exam.recruitment_no,
        status=exam.status,
        external_status=external_status(exam, now),
        start_at=exam.start_at,
        end_at=exam.end_at,
        pass_ratio=exam.pass_ratio,
        settings={"rules": settings.get("rules") or []},
        created_at=exam.created_at,
        published_at=exam.published_at,
    )


def _load_exam(session: Session, exam_id: int) -> Exam:
    exam = session.get(Exam, exam_id)
    if exam is None:
        raise HTTPException(status_code=404, detail="考试不存在")
    return exam


def _ensure_question_mutable(session: Session, question_id: int) -> None:
    """已发布/已归档考试的快照题目不可修改或删除（架构 9.6）。

    快照按 question_id 引用题库，因此必须在题库侧冻结，
    才能保证「之后修改题库不影响已发布考试」。
    """
    links = list(
        session.exec(
            select(ExamQuestion).where(ExamQuestion.question_id == question_id)
        ).all()
    )
    if not links:
        return
    exam_ids = {link.exam_id for link in links}
    frozen = list(
        session.exec(
            select(Exam).where(Exam.id.in_(exam_ids), Exam.status != "draft")
        ).all()
    )
    if frozen:
        titles = "、".join(e.title for e in frozen)
        raise HTTPException(
            status_code=409,
            detail=f"该题目已被已发布考试引用（{titles}），不可修改或删除",
        )


async def _read_csv_body(request: Request) -> str:
    """读取 CSV 文本：支持 text/csv 原样上传或 JSON {"csv": "..."}。"""
    raw = await request.body()
    content_type = (request.headers.get("content-type") or "").lower()
    if "application/json" in content_type:
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=422, detail="JSON 解析失败") from exc
        if isinstance(data, dict) and "csv" in data:
            return str(data["csv"])
        raise HTTPException(status_code=422, detail='JSON 需要 {"csv": "..."} 结构')
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="CSV 编码必须为 UTF-8") from exc


def build_router(get_session, get_clock, get_settings, get_current_admin) -> APIRouter:
    router = APIRouter(prefix="/api/admin", tags=["admin"])

    # ------------------------------------------------------------------
    # 登录
    # ------------------------------------------------------------------

    @router.post("/login", response_model=AdminLoginResponse)
    def admin_login(
        payload: AdminLoginRequest, settings=Depends(get_settings), clock=Depends(get_clock)
    ) -> AdminLoginResponse:
        if not verify_admin_credentials(
            settings.admin_username, settings.admin_password, payload.username, payload.password
        ):
            raise HTTPException(status_code=401, detail="账号或密码错误")
        token = issue_admin_token(
            settings.token_secret, clock.now(), settings.admin_token_ttl_seconds, payload.username
        )
        return AdminLoginResponse(token=token)

    # ------------------------------------------------------------------
    # 题库管理
    # ------------------------------------------------------------------

    @router.get("/questions", response_model=list[QuestionOut], dependencies=[Depends(get_current_admin)])
    def list_questions(
        type: str | None = None,
        tag: str | None = None,
        keyword: str | None = None,
        session: Session = Depends(get_session),
    ) -> list[QuestionOut]:
        rows = list(session.exec(select(Question).order_by(Question.id)).all())
        if type:
            rows = [q for q in rows if q.type == type]
        if keyword:
            rows = [q for q in rows if keyword in q.stem]
        if tag:
            rows = [q for q in rows if tag in loads_json(q.tags_json, [])]
        # 统计一次性算好，避免逐题查库（CH-008）。
        # 没有任何抽题/作答记录的题目也要返回默认 stats（全 None），
        # 这样前端统一按"暂无"渲染，不必为 null 再写分支。
        stats = compute_question_stats(session)
        return [_question_out(q, stats.get(q.id) or QuestionStatsOut()) for q in rows]

    @router.post(
        "/questions",
        response_model=QuestionOut,
        status_code=201,
        dependencies=[Depends(get_current_admin)],
    )
    def create_question(
        payload: QuestionIn, session: Session = Depends(get_session), clock=Depends(get_clock)
    ) -> QuestionOut:
        options_json, answer_json, tags_json = _validate_question(payload)
        question = Question(
            type=payload.type,
            stem=payload.stem,
            options_json=options_json,
            answer_json=answer_json,
            score=payload.score,
            tags_json=tags_json,
            analysis=payload.analysis,
            updated_at=clock.now(),
        )
        session.add(question)
        session.commit()
        session.refresh(question)
        return _question_out(question)

    @router.put(
        "/questions/{question_id}",
        response_model=QuestionOut,
        dependencies=[Depends(get_current_admin)],
    )
    def update_question(
        question_id: int,
        payload: QuestionIn,
        session: Session = Depends(get_session),
        clock=Depends(get_clock),
    ) -> QuestionOut:
        question = session.get(Question, question_id)
        if question is None:
            raise HTTPException(status_code=404, detail="题目不存在")
        _ensure_question_mutable(session, question_id)

        options_json, answer_json, tags_json = _validate_question(payload)
        question.type = payload.type
        question.stem = payload.stem
        question.options_json = options_json
        question.answer_json = answer_json
        question.score = payload.score
        question.tags_json = tags_json
        question.analysis = payload.analysis
        question.updated_at = clock.now()
        session.add(question)
        session.commit()
        session.refresh(question)
        return _question_out(question)

    @router.delete("/questions/{question_id}", dependencies=[Depends(get_current_admin)])
    def delete_question(question_id: int, session: Session = Depends(get_session)) -> dict:
        question = session.get(Question, question_id)
        if question is None:
            raise HTTPException(status_code=404, detail="题目不存在")
        _ensure_question_mutable(session, question_id)
        session.delete(question)
        session.commit()
        return {"ok": True}

    @router.post(
        "/questions/import",
        response_model=QuestionImportResult,
        dependencies=[Depends(get_current_admin)],
    )
    def import_questions(
        payload: QuestionImportRequest,
        session: Session = Depends(get_session),
        clock=Depends(get_clock),
    ) -> QuestionImportResult:
        """JSON 批量导入，按 id upsert。"""
        created = updated = 0
        for item in payload.questions:
            options_json, answer_json, tags_json = _validate_question(item)
            existing = session.get(Question, item.id) if item.id else None
            if existing is None:
                session.add(
                    Question(
                        id=item.id,
                        type=item.type,
                        stem=item.stem,
                        options_json=options_json,
                        answer_json=answer_json,
                        score=item.score,
                        tags_json=tags_json,
                        analysis=item.analysis,
                        updated_at=clock.now(),
                    )
                )
                created += 1
            else:
                existing.type = item.type
                existing.stem = item.stem
                existing.options_json = options_json
                existing.answer_json = answer_json
                existing.score = item.score
                existing.tags_json = tags_json
                existing.analysis = item.analysis
                existing.updated_at = clock.now()
                session.add(existing)
                updated += 1
        session.commit()
        return QuestionImportResult(
            created=created, updated=updated, total=len(payload.questions)
        )

    @router.get("/questions/export", dependencies=[Depends(get_current_admin)])
    def export_questions(session: Session = Depends(get_session)) -> PlainTextResponse:
        """导出题库为 CSV（CH-011）。列含义见规格说明 7.4。"""
        csv_text = export_questions_csv(session)
        return PlainTextResponse(
            content=csv_text,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="question-bank.csv"'},
        )

    # ------------------------------------------------------------------
    # 题库标签（组卷规则的封闭选项）
    # ------------------------------------------------------------------

    @router.get("/tags", response_model=list[TagCountOut], dependencies=[Depends(get_current_admin)])
    def list_tags(session: Session = Depends(get_session)) -> list[TagCountOut]:
        """返回题库中所有标签及各自的可用题数。

        计数口径与发布抽题一致：一道题打了 N 个标签，就在这 N 个标签下各计 1 次。
        前端据此把组卷规则的标签做成封闭选项，并显示"可用 N 题"。
        """
        counts: dict[str, int] = {}
        for question in session.exec(select(Question)).all():
            # 同一题重复打同一标签只算一次
            for tag in {str(t) for t in loads_json(question.tags_json, [])}:
                if tag:
                    counts[tag] = counts.get(tag, 0) + 1
        return [
            TagCountOut(tag=tag, question_count=count)
            for tag, count in sorted(counts.items())
        ]

    # ------------------------------------------------------------------
    # 试卷管理（只读快照）
    # ------------------------------------------------------------------

    @router.get(
        "/exams/{exam_id}/paper",
        response_model=AdminPaperOut,
        dependencies=[Depends(get_current_admin)],
    )
    def admin_paper(
        exam_id: int, session: Session = Depends(get_session), clock=Depends(get_clock)
    ) -> AdminPaperOut:
        """查看某场考试与试卷的对应关系（含正确答案，仅管理端）。

        试卷是发布时冻结的快照，本接口**只读**，不提供任何改题入口。
        """
        exam = _load_exam(session, exam_id)
        if exam.status == "draft":
            raise HTTPException(status_code=409, detail="该考试尚未发布，暂无试卷")

        items = load_paper_questions(session, exam_id)
        questions = [
            AdminPaperQuestionOut(
                seq=item.seq,
                question_id=item.question.id,
                type=item.question.type,
                stem=item.question.stem,
                options=loads_json(item.question.options_json, []),
                answer=loads_json(item.question.answer_json, []),
                score=float(item.score),
                analysis=item.question.analysis or "",
            )
            for item in items
        ]
        total = round(sum(item.score for item in items), 1)
        return AdminPaperOut(
            exam=_exam_out(exam, clock.now()),
            questions=questions,
            total_score=total,
            question_count=len(questions),
        )

    # ------------------------------------------------------------------
    # 考试
    # ------------------------------------------------------------------

    @router.get("/exams", response_model=list[ExamOut], dependencies=[Depends(get_current_admin)])
    def list_exams(
        status: str | None = None,
        recruitment_no: str | None = None,
        title: str | None = None,
        start_from: datetime | None = None,
        start_to: datetime | None = None,
        session: Session = Depends(get_session),
        clock=Depends(get_clock),
    ) -> list[ExamOut]:
        """考试列表，支持按状态 / 选聘编号 / 名称 / 开考时间范围查询（CH-006）。

        - `status` 用**对外状态**（draft/upcoming/running/ended/archived），与界面一致；
        - `recruitment_no` 与 `title` 为包含匹配；
        - `start_from` / `start_to` 为开考时间的闭区间（naive UTC）。

        空字符串条件视为"不过滤"，避免前端把未填写的表单项一并提交时把列表清空。
        """
        status = (status or "").strip() or None
        recruitment_no = (recruitment_no or "").strip() or None
        title = (title or "").strip() or None

        if status is not None and status not in VALID_EXTERNAL_STATUSES:
            raise HTTPException(
                status_code=422,
                detail=f"未知状态：{status}，可选值：{'、'.join(sorted(VALID_EXTERNAL_STATUSES))}",
            )

        now = clock.now()
        rows = list(session.exec(select(Exam).order_by(Exam.id)).all())

        if recruitment_no:
            needle = recruitment_no.lower()
            rows = [e for e in rows if needle in e.recruitment_no.lower()]
        if title:
            needle = title
            rows = [e for e in rows if needle in e.title]
        if start_from is not None:
            rows = [e for e in rows if e.start_at >= start_from]
        if start_to is not None:
            rows = [e for e in rows if e.start_at <= start_to]
        if status is not None:
            rows = [e for e in rows if external_status(e, now) == status]

        return [_exam_out(e, now) for e in rows]

    @router.post(
        "/exams", response_model=ExamOut, status_code=201, dependencies=[Depends(get_current_admin)]
    )
    def create_exam(
        payload: ExamIn, session: Session = Depends(get_session), clock=Depends(get_clock)
    ) -> ExamOut:
        if payload.pass_ratio not in VALID_PASS_RATIOS:
            raise HTTPException(
                status_code=422,
                detail=f"pass_ratio 必须是 {VALID_PASS_RATIOS[0]}–{VALID_PASS_RATIOS[-1]} 且为 10 的倍数",
            )
        if payload.end_at <= payload.start_at:
            raise HTTPException(status_code=422, detail="截止时间必须晚于开考时间")

        duplicate = session.exec(
            select(Exam).where(Exam.recruitment_no == payload.recruitment_no)
        ).first()
        if duplicate is not None:
            raise HTTPException(status_code=409, detail="选聘编号已存在")

        exam = Exam(
            title=payload.title,
            recruitment_no=payload.recruitment_no,
            status="draft",
            start_at=payload.start_at,
            end_at=payload.end_at,
            pass_ratio=payload.pass_ratio,
            settings_json=dumps_json({"rules": [r.model_dump() for r in payload.settings.rules]}),
            created_at=clock.now(),
        )
        session.add(exam)
        session.commit()
        session.refresh(exam)
        return _exam_out(exam, clock.now())

    @router.put("/exams/{exam_id}", response_model=ExamOut, dependencies=[Depends(get_current_admin)])
    def update_exam(
        exam_id: int,
        payload: ExamIn,
        session: Session = Depends(get_session),
        clock=Depends(get_clock),
    ) -> ExamOut:
        exam = _load_exam(session, exam_id)
        ensure_draft(exam)  # 发布即冻结

        if payload.pass_ratio not in VALID_PASS_RATIOS:
            raise HTTPException(status_code=422, detail="pass_ratio 非法")
        if payload.end_at <= payload.start_at:
            raise HTTPException(status_code=422, detail="截止时间必须晚于开考时间")

        duplicate = session.exec(
            select(Exam).where(
                Exam.recruitment_no == payload.recruitment_no, Exam.id != exam_id
            )
        ).first()
        if duplicate is not None:
            raise HTTPException(status_code=409, detail="选聘编号已存在")

        exam.title = payload.title
        exam.recruitment_no = payload.recruitment_no
        exam.start_at = payload.start_at
        exam.end_at = payload.end_at
        exam.pass_ratio = payload.pass_ratio
        exam.settings_json = dumps_json({"rules": [r.model_dump() for r in payload.settings.rules]})
        session.add(exam)
        session.commit()
        session.refresh(exam)
        return _exam_out(exam, clock.now())

    @router.delete("/exams/{exam_id}", dependencies=[Depends(get_current_admin)])
    def delete_exam(exam_id: int, session: Session = Depends(get_session)) -> dict:
        exam = _load_exam(session, exam_id)
        ensure_deletable(exam)

        # 显式按依赖顺序删除并从数据库落盘，避免无 ORM relationship 时
        # SQLAlchemy 无法推导删除顺序而触发外键约束错误。
        session.execute(sa_delete(ExamQuestion).where(ExamQuestion.exam_id == exam_id))
        session.execute(sa_delete(ExamCandidate).where(ExamCandidate.exam_id == exam_id))
        session.flush()

        session.delete(exam)
        session.commit()
        return {"ok": True}

    @router.post(
        "/exams/{exam_id}/publish",
        response_model=PublishResponse,
        dependencies=[Depends(get_current_admin)],
    )
    def publish(
        exam_id: int, session: Session = Depends(get_session), clock=Depends(get_clock)
    ) -> PublishResponse:
        exam = _load_exam(session, exam_id)
        result = publish_exam(session, exam, clock.now())
        return PublishResponse(
            exam_id=result.exam_id,
            question_count=result.question_count,
            total_score=result.total_score,
        )

    @router.post(
        "/exams/{exam_id}/archive", response_model=ExamOut, dependencies=[Depends(get_current_admin)]
    )
    def archive(
        exam_id: int, session: Session = Depends(get_session), clock=Depends(get_clock)
    ) -> ExamOut:
        exam = _load_exam(session, exam_id)
        ensure_published(exam)
        exam.status = STATUS_ARCHIVED
        session.add(exam)
        session.commit()
        session.refresh(exam)
        return _exam_out(exam, clock.now())

    # ------------------------------------------------------------------
    # 名单与邀请码
    # ------------------------------------------------------------------

    @router.get(
        "/exams/{exam_id}/candidates",
        response_model=list[CandidateRowOut],
        dependencies=[Depends(get_current_admin)],
    )
    def list_candidates(
        exam_id: int, session: Session = Depends(get_session)
    ) -> list[CandidateRowOut]:
        _load_exam(session, exam_id)
        links = list(
            session.exec(select(ExamCandidate).where(ExamCandidate.exam_id == exam_id)).all()
        )
        # 一次性取出本场全部 attempt，避免逐人查库（CH-010）
        attempts = {
            attempt.user_id: attempt
            for attempt in session.exec(
                select(Attempt).where(Attempt.exam_id == exam_id)
            ).all()
        }

        out: list[CandidateRowOut] = []
        for link in links:
            user = session.get(User, link.user_id)
            if user is None:
                continue
            attempt = attempts.get(link.user_id)
            # 没有 attempt = 从未用邀请码登录过
            out.append(
                CandidateRowOut(
                    user_id=user.id,
                    phone=user.phone,
                    name=user.name,
                    id_card=user.id_card,
                    invite_code=link.invite_code,
                    status=attempt.status if attempt else PARTICIPATION_NOT_STARTED,
                    started_at=attempt.started_at if attempt else None,
                    submitted_at=attempt.submitted_at if attempt else None,
                    score=attempt.score if attempt else None,
                )
            )
        out.sort(key=lambda r: r.name)
        return out

    @router.post(
        "/exams/{exam_id}/candidates/import",
        response_model=RosterImportResponse,
        dependencies=[Depends(get_current_admin)],
    )
    async def import_candidates(
        exam_id: int,
        request: Request,
        session: Session = Depends(get_session),
        clock=Depends(get_clock),
    ) -> RosterImportResponse:
        exam = _load_exam(session, exam_id)
        ensure_draft(exam)

        text = await _read_csv_body(request)
        try:
            rows = parse_roster_csv(text)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        try:
            result = import_roster(session, exam, rows, clock.now())
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        return RosterImportResponse(
            users_created=result.users_created,
            users_updated=result.users_updated,
            linked=result.linked,
            total_rows=result.total_rows,
        )

    @router.post(
        "/exams/{exam_id}/candidates/generate",
        response_model=GenerateInvitesResponse,
        dependencies=[Depends(get_current_admin)],
    )
    def generate_codes(
        exam_id: int,
        payload: GenerateInvitesRequest | None = None,
        session: Session = Depends(get_session),
        clock=Depends(get_clock),
        settings=Depends(get_settings),
    ) -> GenerateInvitesResponse:
        """生成邀请码：全部覆盖，需二次确认。"""
        exam = _load_exam(session, exam_id)
        ensure_draft(exam)

        existing = session.exec(
            select(func.count())
            .select_from(ExamCandidate)
            .where(ExamCandidate.exam_id == exam_id, ExamCandidate.invite_code.is_not(None))
        ).one()
        confirm = bool(payload.confirm) if payload else False
        if existing and not confirm:
            raise HTTPException(
                status_code=409,
                detail="重新生成将覆盖全部邀请码并使旧码立即失效，请确认后重试",
            )

        generator = InviteCodeGenerator(digits=settings.invite_code_digits)
        count = generate_invite_codes(session, exam, generator, clock.now())
        return GenerateInvitesResponse(generated=count)

    @router.get("/exams/{exam_id}/candidates/export", dependencies=[Depends(get_current_admin)])
    def export_codes(exam_id: int, session: Session = Depends(get_session)) -> PlainTextResponse:
        exam = _load_exam(session, exam_id)
        csv_text = export_invite_codes_csv(session, exam)
        return PlainTextResponse(
            content=csv_text,
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="invite_codes_{exam.recruitment_no}.csv"'
            },
        )

    # ------------------------------------------------------------------
    # 统计与导出
    # ------------------------------------------------------------------

    @router.get(
        "/exams/{exam_id}/results", response_model=ResultsResponse, dependencies=[Depends(get_current_admin)]
    )
    def results(exam_id: int, session: Session = Depends(get_session)) -> ResultsResponse:
        exam = _load_exam(session, exam_id)
        rows = build_result_rows(session, exam)
        return ResultsResponse(
            exam_id=exam_id,
            rows=[
                ResultRowOut(
                    user_id=r.user_id,
                    phone=r.phone,
                    name=r.name,
                    id_card=r.id_card,
                    invite_code=r.invite_code,
                    started_at=r.started_at,
                    submitted_at=r.submitted_at,
                    score=r.score,
                    is_pass=bool(r.is_pass),
                    switch_count=r.switch_count,
                    switch_log=r.switch_log,
                    status=r.status,
                )
                for r in rows
            ],
        )

    @router.get("/exams/{exam_id}/results/export", dependencies=[Depends(get_current_admin)])
    def export_results(exam_id: int, session: Session = Depends(get_session)) -> PlainTextResponse:
        exam = _load_exam(session, exam_id)
        csv_text = export_results_csv(session, exam)
        return PlainTextResponse(
            content=csv_text,
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="results_{exam.recruitment_no}.csv"'
            },
        )

    @router.get("/exams/{exam_id}/stats", response_model=StatsResponse, dependencies=[Depends(get_current_admin)])
    def stats(exam_id: int, session: Session = Depends(get_session)) -> StatsResponse:
        exam = _load_exam(session, exam_id)
        result = compute_stats(session, exam)
        return StatsResponse(
            exam_id=exam_id,
            total_candidates=result.total_candidates,
            attempt_count=result.attempt_count,
            absent_count=result.absent_count,
            average_score=result.average_score,
            pass_ratio=result.pass_ratio,
            pass_line=result.pass_line,
            pass_count=result.pass_count,
            pass_rate=result.pass_rate,
            questions=[StatsQuestionRow(**q) for q in result.questions],
        )

    return router
