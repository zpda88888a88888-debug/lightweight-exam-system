"""运行配置：全部来自环境变量。

规格依据：架构 7.2、10 —— 管理员账号密码从环境变量读取，仅一个超管。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_DB_FILENAME = "exam.db"


@dataclass
class Settings:
    """应用配置。"""

    admin_username: str = "admin"
    admin_password: str = "changeme"
    token_secret: str = "dev-insecure-secret-change-me"
    db_path: Path = field(default_factory=lambda: Path("./data") / DEFAULT_DB_FILENAME)
    admin_token_ttl_seconds: int = 12 * 3600
    candidate_token_ttl_seconds: int = 12 * 3600
    invite_code_digits: int = 6
    invite_code_max_attempts: int = 200
    cors_origins: tuple[str, ...] = ("*",)

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env

        def _int(key: str, default: int) -> int:
            raw = env.get(key)
            if raw is None or raw == "":
                return default
            return int(raw)

        db_path = env.get("EXAM_DB_PATH")
        ttl = _int("TOKEN_TTL_SECONDS", 12 * 3600)

        return cls(
            admin_username=env.get("ADMIN_USERNAME", "admin"),
            admin_password=env.get("ADMIN_PASSWORD", "changeme"),
            token_secret=env.get("TOKEN_SECRET", "dev-insecure-secret-change-me"),
            db_path=Path(db_path) if db_path else Path("./data") / DEFAULT_DB_FILENAME,
            admin_token_ttl_seconds=_int("ADMIN_TOKEN_TTL_SECONDS", ttl),
            candidate_token_ttl_seconds=_int("CANDIDATE_TOKEN_TTL_SECONDS", ttl),
            invite_code_digits=_int("INVITE_CODE_DIGITS", 6),
        )

    @property
    def sqlite_url(self) -> str:
        return f"sqlite:///{self.db_path}"


#: 对外的考试状态（由后端惰性计算，不落库）
STATUS_DRAFT = "draft"
STATUS_PUBLISHED = "published"
STATUS_ARCHIVED = "archived"

EXTERNAL_DRAFT = "draft"
EXTERNAL_UPCOMING = "upcoming"
EXTERNAL_RUNNING = "running"
EXTERNAL_ENDED = "ended"
EXTERNAL_ARCHIVED = "archived"

#: attempt 状态
ATTEMPT_IN_PROGRESS = "in_progress"
ATTEMPT_SUBMITTED = "submitted"
ATTEMPT_TIMEOUT_SUBMITTED = "timeout_submitted"

#: 名单参与状态（考生管理，CH-010）：
#: 前三个复用 attempt 状态；"未登录"表示根本没有 attempt
PARTICIPATION_NOT_STARTED = "not_started"

QUESTION_TYPES = ("single", "multi", "judge")

#: 题型中文标签（导出与界面展示共用）
QUESTION_TYPE_LABELS = {"single": "单选题", "multi": "多选题", "judge": "判断题"}

#: 成绩导出状态列的中文取值
EXPORT_STATUS_NORMAL = "正常提交"
EXPORT_STATUS_TIMEOUT = "超时提交"
EXPORT_STATUS_ABSENT = "缺考"

#: 成绩 CSV 列顺序（spec 7.3，顺序与命名不可变）
EXPORT_COLUMNS = (
    "选聘编号",
    "考试名称",
    "手机号",
    "姓名",
    "身份证号",
    "邀请码",
    "开始时间",
    "交卷时间",
    "得分",
    "是否及格",
    "切屏次数",
    "切屏时间点",
    "状态",
)

#: 名单导入 CSV 表头（顺序与命名须一致）
ROSTER_COLUMNS = ("手机号", "姓名", "身份证号")
