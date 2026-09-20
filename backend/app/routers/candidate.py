"""考生端路由。

规格依据：架构 7.1、9.1、9.4、9.5、9.7、9.9

授权约定：登录时校验「手机号 + 邀请码」必须属于同一场考试的同一考生，
仅凭邀请码存在不足以登录（测试方案 6.4 注意项）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.config import ATTEMPT_IN_PROGRESS
from app.domain import ExamStateError, ensure_published, ensure_joinable_window, ensure_running
from app.models import Attempt, Exam, ExamCandidate, User
from app.schemas import (
    AttemptCreateResponse,
    JoinRequest,
    JoinResponse,
    PaperResponse,
    SubmitRequest,
    SubmitResponse,
)
from app.security import issue_candidate_token
from app.services import build_paper_payload, get_or_create_attempt, submit_attempt


def _load_exam(session: Session, exam_id: int) -> Exam:
    exam = session.get(Exam, exam_id)
    if exam is None:
        raise HTTPException(status_code=404, detail="考试不存在")
    return exam


def build_router(get_session, get_clock, get_settings, get_current_candidate) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["candidate"])

    @router.post("/auth/join", response_model=JoinResponse)
    def join(
        payload: JoinRequest,
        session: Session = Depends(get_session),
        clock=Depends(get_clock),
        settings=Depends(get_settings),
    ) -> JoinResponse:
        """考生登录：手机号 + 邀请码。"""
        now = clock.now()

        link = session.exec(
            select(ExamCandidate).where(ExamCandidate.invite_code == payload.invite_code.strip())
        ).first()
        # 凭证校验：邀请码必须与手机号同属一场考试的同一考生
        if link is None:
            raise HTTPException(status_code=403, detail="手机号或邀请码错误")

        user = session.get(User, link.user_id)
        exam = session.get(Exam, link.exam_id)
        if user is None or exam is None or user.phone != payload.phone.strip():
            raise HTTPException(status_code=403, detail="手机号或邀请码错误")

        # 已交卷：任何时间再次登录均拒绝（spec 4.1）
        attempt = session.exec(
            select(Attempt).where(Attempt.exam_id == exam.id, Attempt.user_id == user.id)
        ).first()
        if attempt is not None and attempt.status != ATTEMPT_IN_PROGRESS:
            raise ExamStateError("你已交卷，考试结束", status_code=409)

        # 时间窗口（边界含等号）
        ensure_joinable_window(exam, now)

        token = issue_candidate_token(
            settings.token_secret,
            now,
            settings.candidate_token_ttl_seconds,
            exam_id=exam.id,
            user_id=user.id,
            phone=user.phone,
        )
        return JoinResponse(
            token=token,
            exam={
                "id": exam.id,
                "title": exam.title,
                "start_at": exam.start_at,
                "end_at": exam.end_at,
            },
        )

    @router.post("/exams/{exam_id}/attempts", response_model=AttemptCreateResponse)
    def create_attempt(
        exam_id: int,
        session: Session = Depends(get_session),
        clock=Depends(get_clock),
        claims: dict = Depends(get_current_candidate),
    ) -> AttemptCreateResponse:
        """创建 attempt；已存在则返回既有 attempt_id（一人一场一个）。"""
        if int(claims.get("exam_id", -1)) != exam_id:
            raise HTTPException(status_code=403, detail="无权访问该考试")

        exam = _load_exam(session, exam_id)
        now = clock.now()
        ensure_published(exam)
        ensure_running(exam, now)

        user = session.get(User, int(claims["user_id"]))
        if user is None:
            raise HTTPException(status_code=403, detail="考生不存在")

        link = session.exec(
            select(ExamCandidate).where(
                ExamCandidate.exam_id == exam.id, ExamCandidate.user_id == user.id
            )
        ).first()
        if link is None:
            raise HTTPException(status_code=403, detail="你不在本场考试名单中")

        attempt = get_or_create_attempt(session, exam, user, now)
        return AttemptCreateResponse(attempt_id=attempt.id, end_at=exam.end_at)

    @router.get("/exams/{exam_id}/paper", response_model=PaperResponse)
    def get_paper(
        exam_id: int,
        session: Session = Depends(get_session),
        clock=Depends(get_clock),
        claims: dict = Depends(get_current_candidate),
    ) -> PaperResponse:
        """拉取试卷：仅进行中可拉取，且响应绝不含答案与解析。"""
        if int(claims.get("exam_id", -1)) != exam_id:
            raise HTTPException(status_code=403, detail="无权访问该考试")

        exam = _load_exam(session, exam_id)
        now = clock.now()
        ensure_published(exam)
        ensure_running(exam, now)

        user = session.get(User, int(claims["user_id"]))
        if user is None:
            raise HTTPException(status_code=403, detail="考生不存在")

        return PaperResponse(**build_paper_payload(session, exam, user))

    @router.post("/attempts/{attempt_id}/submit", response_model=SubmitResponse)
    def submit(
        attempt_id: int,
        payload: SubmitRequest,
        session: Session = Depends(get_session),
        clock=Depends(get_clock),
        claims: dict = Depends(get_current_candidate),
    ) -> SubmitResponse:
        """交卷：一次性提交全部答案，服务端事务内判分，幂等。"""
        attempt = session.get(Attempt, attempt_id)
        if attempt is None:
            raise HTTPException(status_code=404, detail="attempt 不存在")

        if int(claims.get("exam_id", -1)) != attempt.exam_id:
            raise HTTPException(status_code=403, detail="无权访问该 attempt")
        if int(claims.get("user_id", -1)) != attempt.user_id:
            raise HTTPException(status_code=403, detail="无权访问该 attempt")

        exam = _load_exam(session, attempt.exam_id)
        # 交卷允许发生在 end_at 之后（超时提交），但不允许未发布/已归档
        ensure_published(exam)

        result = submit_attempt(
            session,
            attempt,
            exam,
            [a.model_dump() for a in payload.answers],
            payload.switch_count,
            payload.switch_log,
            clock.now(),
        )
        return SubmitResponse(
            ok=True,
            attempt_id=result.attempt_id,
            score=result.score,
            status=result.status,
            submitted_at=result.submitted_at,
        )

    return router
