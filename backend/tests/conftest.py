"""测试夹具：独立临时 SQLite、可注入 FrozenClock、TestClient。

规格依据：测试方案 5
    - 禁止测试间共享数据库状态（每个用例独立 tmp_path 数据库）
    - 时间相关测试使用可注入时钟，不依赖系统真实时间
    - 测试环境必须开启 WAL（与生产一致），否则并发结论无效
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.clock import FrozenClock
from app.config import Settings
from app.main import create_app

#: 所有测试的时间基准（naive UTC）
BASE_TIME = datetime(2026, 9, 19, 10, 0, 0)

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "test-password"
TOKEN_SECRET = "test-secret"


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock(BASE_TIME)


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        admin_username=ADMIN_USERNAME,
        admin_password=ADMIN_PASSWORD,
        token_secret=TOKEN_SECRET,
        db_path=tmp_path / "exam.db",
    )


@pytest.fixture
def app(settings, clock):
    return create_app(settings, clock)


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def running_exam():
    """便捷时间窗口：(BASE-1h, BASE+1h)。"""
    return BASE_TIME - timedelta(hours=1), BASE_TIME + timedelta(hours=1)
