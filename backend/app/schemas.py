"""API 请求/响应模型。

规格依据：架构 7 API 草案 / 测试方案 6.6（用 Pydantic 模型固定字段集合）

安全要点：
    `PaperQuestionOut` 刻意只声明 4 个字段（id/type/stem/options），
    从类型层面保证 `answer_json` 与 `analysis` 不可能下发。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

QuestionType = Literal["single", "multi", "judge"]


class StrictModel(BaseModel):
    """禁止未声明字段。"""

    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------
# 考生端
# --------------------------------------------------------------------------


class JoinRequest(StrictModel):
    phone: str = Field(min_length=1)
    invite_code: str = Field(min_length=1)


class ExamBrief(StrictModel):
    id: int
    title: str
    start_at: datetime
    end_at: datetime


class JoinResponse(StrictModel):
    token: str
    exam: ExamBrief


class OptionOut(StrictModel):
    key: str
    text: str


class PaperQuestionOut(StrictModel):
    """试卷题目：绝不含 answer_json、绝不含 analysis。"""

    id: int
    type: QuestionType
    stem: str
    options: list[OptionOut]


class PaperResponse(StrictModel):
    exam: ExamBrief
    questions: list[PaperQuestionOut]


class AttemptCreateResponse(StrictModel):
    attempt_id: int
    end_at: datetime


class SubmitAnswerIn(StrictModel):
    question_id: int
    answer: list[str] = Field(default_factory=list)


class SubmitRequest(StrictModel):
    answers: list[SubmitAnswerIn] = Field(default_factory=list)
    switch_count: int = Field(default=0, ge=0)
    switch_log: list[str] = Field(default_factory=list)


class SubmitResponse(StrictModel):
    ok: bool
    attempt_id: int
    score: float
    status: str
    submitted_at: datetime


# --------------------------------------------------------------------------
# 管理端
# --------------------------------------------------------------------------


class AdminLoginRequest(StrictModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class AdminLoginResponse(StrictModel):
    token: str


class QuestionIn(StrictModel):
    id: Optional[int] = None
    type: QuestionType
    stem: str = Field(min_length=1)
    options: list[OptionOut] = Field(default_factory=list)
    answer: list[str] = Field(min_length=1)
    score: float = Field(gt=0)
    tags: list[str] = Field(default_factory=list)
    analysis: str = ""


class QuestionStatsOut(StrictModel):
    """题目统计（CH-008）。

    口径：
        last_drawn_*  —— 上次被随机抽中的考试（依据发布时生成的试卷快照）；
        correct_rate  —— 累计答题正确率 = 正确次数 ÷ 所有已判分提交次数；
                         未作答算错，因此与"标错率"互补；
                         从未被作答时为 None（界面显示"暂无"，不是 0%）。
    """

    last_drawn_exam_id: int | None = None
    last_drawn_exam_title: str | None = None
    last_drawn_at: datetime | None = None
    answer_count: int = 0
    correct_count: int = 0
    correct_rate: float | None = None


class QuestionOut(StrictModel):
    id: int
    type: QuestionType
    stem: str
    options: list[OptionOut]
    answer: list[str]
    score: float
    tags: list[str]
    analysis: str
    updated_at: datetime
    #: 仅在题库列表接口填充；单题增改返回时为 None
    stats: QuestionStatsOut | None = None


class QuestionImportRequest(StrictModel):
    questions: list[QuestionIn]


class QuestionImportResult(StrictModel):
    created: int
    updated: int
    total: int


class RosterRule(StrictModel):
    tag: str = Field(min_length=1)
    count: int = Field(gt=0)


class ExamSettings(StrictModel):
    rules: list[RosterRule] = Field(default_factory=list)


class ExamIn(StrictModel):
    title: str = Field(min_length=1)
    recruitment_no: str = Field(min_length=1)
    start_at: datetime
    end_at: datetime
    pass_ratio: int
    settings: ExamSettings = Field(default_factory=ExamSettings)


class ExamOut(StrictModel):
    id: int
    title: str
    recruitment_no: str
    status: str
    external_status: str
    start_at: datetime
    end_at: datetime
    pass_ratio: int
    settings: ExamSettings
    created_at: datetime
    published_at: Optional[datetime] = None


class GenerateInvitesRequest(StrictModel):
    confirm: bool = False


class GenerateInvitesResponse(StrictModel):
    generated: int


class TagCountOut(StrictModel):
    """题库标签及可用题数（用于组卷规则的封闭选项）。"""

    tag: str
    question_count: int


class AdminPaperQuestionOut(StrictModel):
    """管理端试卷快照中的题目（**含正确答案与解析**，仅管理端可见）。"""

    seq: int
    question_id: int
    type: QuestionType
    stem: str
    options: list[OptionOut]
    answer: list[str]
    score: float
    analysis: str


class AdminPaperOut(StrictModel):
    """管理端试卷只读视图：考试与试卷的对应关系。"""

    exam: ExamOut
    questions: list[AdminPaperQuestionOut]
    total_score: float
    question_count: int


class RosterImportResponse(StrictModel):
    users_created: int
    users_updated: int
    linked: int
    total_rows: int


class PublishResponse(StrictModel):
    exam_id: int
    question_count: int
    total_score: float


class CandidateRowOut(StrictModel):
    """名单中的一名考生及其**参与状态**（CH-010）。

    状态取值：
        not_started       未登录（从未用邀请码登录过，没有 attempt）
        in_progress       答题中（已登录并开始答题，尚未交卷）
        submitted         已交卷（截止前正常提交）
        timeout_submitted 超时交卷（截止时刻之后才提交）
    """

    user_id: int
    phone: str
    name: str
    id_card: str
    invite_code: Optional[str]
    status: str
    started_at: Optional[datetime] = None
    submitted_at: Optional[datetime] = None
    score: Optional[float] = None


class StatsQuestionRow(StrictModel):
    question_id: int
    seq: int
    wrong_rate: float
    full_score: float


class StatsResponse(StrictModel):
    exam_id: int
    total_candidates: int
    attempt_count: int
    absent_count: int
    average_score: float
    pass_ratio: int
    pass_line: Optional[float]
    pass_count: int
    pass_rate: float
    questions: list[StatsQuestionRow]


class ResultRowOut(StrictModel):
    user_id: int
    phone: str
    name: str
    id_card: str
    invite_code: Optional[str]
    started_at: Optional[datetime]
    submitted_at: Optional[datetime]
    score: Optional[float]
    is_pass: bool
    switch_count: int
    switch_log: list[str]
    status: str


class ResultsResponse(StrictModel):
    exam_id: int
    rows: list[ResultRowOut]
