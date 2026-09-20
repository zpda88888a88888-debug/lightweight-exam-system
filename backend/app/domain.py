"""领域规则：惰性考试状态、时间窗口校验。

规格依据：架构 9.1、9.2、9.3

对外状态不落库，由 `status` + 当前时间惰性计算，因此不需要定时任务。
"""

from __future__ import annotations

from datetime import datetime

from app.config import (
    EXTERNAL_ARCHIVED,
    EXTERNAL_DRAFT,
    EXTERNAL_ENDED,
    EXTERNAL_RUNNING,
    EXTERNAL_UPCOMING,
    STATUS_ARCHIVED,
    STATUS_DRAFT,
    STATUS_PUBLISHED,
)
from app.models import Exam


class ExamStateError(Exception):
    """考试状态不允许当前操作。携带对外提示文案与建议 HTTP 状态码。"""

    def __init__(self, message: str, status_code: int = 409) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def external_status(exam: Exam, now: datetime) -> str:
    """计算对外状态（架构 9.2）。"""
    if exam.status == STATUS_DRAFT:
        return EXTERNAL_DRAFT
    if exam.status == STATUS_ARCHIVED:
        return EXTERNAL_ARCHIVED
    if exam.status != STATUS_PUBLISHED:
        # 未知人工状态按草稿处理，避免出现“可答题”的漏洞
        return EXTERNAL_DRAFT

    if now < exam.start_at:
        return EXTERNAL_UPCOMING
    if now <= exam.end_at:
        return EXTERNAL_RUNNING
    return EXTERNAL_ENDED


def is_running(exam: Exam, now: datetime) -> bool:
    """考试是否进行中（含 start_at 与 end_at 两个边界时刻）。"""
    return external_status(exam, now) == EXTERNAL_RUNNING


def ensure_published(exam: Exam) -> None:
    """要求考试已发布（未发布不可作为考试对象操作）。"""
    if exam.status == STATUS_DRAFT:
        raise ExamStateError("考试尚未发布", status_code=409)
    if exam.status == STATUS_ARCHIVED:
        raise ExamStateError("考试已归档", status_code=409)


def ensure_draft(exam: Exam) -> None:
    """发布即冻结：仅草稿状态可修改（架构 9.3）。"""
    if exam.status == STATUS_DRAFT:
        return
    if exam.status == STATUS_ARCHIVED:
        raise ExamStateError("考试已归档，不可修改", status_code=409)
    raise ExamStateError("考试已发布，内容已冻结，不可修改", status_code=409)


def ensure_deletable(exam: Exam) -> None:
    """仅草稿可删除（spec 4.5）。"""
    if exam.status != STATUS_DRAFT:
        raise ExamStateError("仅草稿状态的考试可删除", status_code=409)


def ensure_running(exam: Exam, now: datetime) -> None:
    """要求考试进行中，否则给出明确的拒绝文案（spec 4.1）。"""
    status = external_status(exam, now)
    if status == EXTERNAL_RUNNING:
        return
    if status == EXTERNAL_DRAFT:
        raise ExamStateError("考试尚未发布", status_code=409)
    if status == EXTERNAL_UPCOMING:
        raise ExamStateError("考试未开始", status_code=409)
    if status == EXTERNAL_ENDED:
        raise ExamStateError("考试已结束", status_code=409)
    raise ExamStateError("考试已归档", status_code=409)


def ensure_joinable_window(exam: Exam, now: datetime) -> None:
    """登录时间窗口校验：未开始与已结束均拒绝（边界含等号）。"""
    status = external_status(exam, now)
    if status == EXTERNAL_RUNNING:
        return
    if status == EXTERNAL_DRAFT:
        raise ExamStateError("考试尚未发布", status_code=409)
    if status == EXTERNAL_UPCOMING:
        raise ExamStateError("考试未开始", status_code=409)
    if status == EXTERNAL_ENDED:
        raise ExamStateError("考试已结束", status_code=409)
    raise ExamStateError("考试已归档", status_code=409)
