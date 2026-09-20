"""数据库引擎与会话。

规格依据：架构 4、10、12 —— SQLite 开启 WAL，busy_timeout=5000。

并发要求（spec 8：200 人同时交卷不丢数据）依赖：
    - journal_mode = WAL
    - busy_timeout = 5000
    - 每个请求独立 Session（不跨线程共享）
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool
from sqlmodel import Session, SQLModel, create_engine


def create_db_engine(db_path: Path | str, *, echo: bool = False) -> Engine:
    """创建带 WAL / busy_timeout 配置的 SQLite 引擎。

    连接池使用 NullPool（每个请求一条独立连接）：
        SQLAlchemy 默认 QueuePool 只有 5 + 10 条连接，200 人同时交卷会在
        取连接阶段直接超时失败（压力测试实测），而 SQLite 本身把写入串行化，
        连接池限流并不能提升吞吐，只会造成排队失败。
        NullPool 让 200 并发请求各自持有一条短连接，由 SQLite 的
        写锁 + busy_timeout 负责排队，实测 200 并发全部成功。
    """
    if str(db_path) != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(
        f"sqlite:///{db_path}",
        echo=echo,
        # SQLite 默认禁止跨线程使用连接；FastAPI 同步端点跑在线程池中
        connect_args={"check_same_thread": False, "timeout": 5.0},
        poolclass=NullPool,
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def init_db(engine: Engine) -> None:
    """建表（幂等）。"""
    import app.models  # noqa: F401  确保模型已注册到 metadata

    SQLModel.metadata.create_all(engine)


def session_scope(engine: Engine) -> Iterator[Session]:
    """with 用法的事务性会话。"""
    with Session(engine) as session:
        yield session
