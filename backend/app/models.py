"""数据模型（SQLModel）。

规格依据：架构 6 数据模型。

与架构文档的一处有意偏差（已记录）：
    `exam_candidates.invite_code` 在架构文档中标注 NOT NULL，
    但测试方案 6.8 要求「名单导入后未生成邀请码时，考生无法登录」，
    即邀请码生成前必须允许为空。故此处改为 nullable + UNIQUE
    （SQLite 的 UNIQUE 允许多个 NULL）。

其余关键约束完全落地：
    - users.id_card 全局唯一
    - exams.recruitment_no 全局唯一
    - exam_candidates.invite_code 全局唯一
    - attempts(exam_id, user_id) 唯一
    - answers(attempt_id, question_id) 唯一
    - attempts.switch_log_json 只进不出（不随试卷接口下发）
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from sqlmodel import Field, SQLModel, UniqueConstraint

from app.config import ATTEMPT_IN_PROGRESS, STATUS_DRAFT


class User(SQLModel, table=True):
    """考生主数据。身份证号全局唯一，跨考试复用同一 user 记录。"""

    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(description="姓名")
    phone: str = Field(index=True, description="手机号")
    id_card: str = Field(unique=True, index=True, description="身份证号（全局唯一）")
    created_at: datetime


class Exam(SQLModel, table=True):
    """考试。status 只存人工状态：draft / published / archived。"""

    __tablename__ = "exams"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    recruitment_no: str = Field(unique=True, index=True, description="选聘编号（全局唯一）")
    status: str = Field(default=STATUS_DRAFT, index=True)
    start_at: datetime
    end_at: datetime
    pass_ratio: int
    settings_json: str = Field(default="{}", description="组卷规则等")
    created_at: datetime
    published_at: Optional[datetime] = None


class ExamCandidate(SQLModel, table=True):
    """考试名单：某考生参加某场考试，持有该场的邀请码。"""

    __tablename__ = "exam_candidates"
    __table_args__ = (UniqueConstraint("exam_id", "user_id", name="uq_exam_candidate"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    exam_id: int = Field(foreign_key="exams.id", index=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    invite_code: Optional[str] = Field(default=None, unique=True, index=True)
    created_at: datetime


class Question(SQLModel, table=True):
    """题库题目。纯文本内容。"""

    __tablename__ = "questions"

    id: Optional[int] = Field(default=None, primary_key=True)
    type: str = Field(index=True, description="single / multi / judge")
    stem: str = Field(description="题干")
    options_json: str = Field(default="[]", description='[{"key":"A","text":"..."}]')
    answer_json: str = Field(default="[]", description='["A","B"] 正确答案，绝不下发')
    score: float = Field(description="默认分值")
    tags_json: str = Field(default="[]", description='["标签"]')
    analysis: str = Field(default="", description="解析，绝不下发")
    updated_at: datetime


class ExamQuestion(SQLModel, table=True):
    """试卷快照：发布时随机抽题并固定顺序。"""

    __tablename__ = "exam_questions"

    exam_id: int = Field(foreign_key="exams.id", primary_key=True)
    question_id: int = Field(foreign_key="questions.id", primary_key=True)
    seq: int = Field(description="题目顺序，发布时随机固定")
    score: float = Field(description="本题在本场考试中的分值")


class Attempt(SQLModel, table=True):
    """一个考生在一场考试中的一次答题记录。"""

    __tablename__ = "attempts"
    __table_args__ = (UniqueConstraint("exam_id", "user_id", name="uq_attempt"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    exam_id: int = Field(foreign_key="exams.id", index=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    started_at: datetime
    submitted_at: Optional[datetime] = None
    score: Optional[float] = None
    status: str = Field(default=ATTEMPT_IN_PROGRESS, index=True)
    switch_count: int = Field(default=0)
    switch_log_json: str = Field(default="[]")


class Answer(SQLModel, table=True):
    """判分结果明细。"""

    __tablename__ = "answers"
    __table_args__ = (UniqueConstraint("attempt_id", "question_id", name="uq_answer"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    attempt_id: int = Field(foreign_key="attempts.id", index=True)
    question_id: int = Field(foreign_key="questions.id", index=True)
    answer_json: str = Field(default="[]", description="考生提交的原始选项标识")
    is_correct: int = Field(default=0)
    score: float = Field(default=0.0)


# --------------------------------------------------------------------------
# JSON 字段读写辅助
# --------------------------------------------------------------------------


def loads_json(raw: str | None, default: Any) -> Any:
    """宽容解析 JSON 文本字段。"""
    if not raw:
        return default
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return default
    return value if value is not None else default


def dumps_json(value: Any) -> str:
    """序列化为紧凑 JSON 文本（中文不转义，便于导出可读）。"""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
