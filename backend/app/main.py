"""FastAPI 应用工厂。

规格依据：架构 2、3、4、7、10

本机运行（无 Docker）：
    uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlmodel import Session

from app.clock import Clock, SystemClock
from app.config import Settings
from app.db import create_db_engine, init_db
from app.domain import ExamStateError
from app.security import ROLE_ADMIN, ROLE_CANDIDATE, TokenError, decode_token


def create_app(settings: Settings | None = None, clock: Clock | None = None) -> FastAPI:
    """构造应用。测试可注入独立 Settings 与 FrozenClock。"""
    settings = settings or Settings.from_env()
    clock = clock or SystemClock()

    app = FastAPI(title="极轻量级客观题考试系统", version="0.1.0")

    engine = create_db_engine(settings.db_path)
    app.state.settings = settings
    app.state.clock = clock
    app.state.engine = engine

    init_db(engine)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ---------------- 依赖 ----------------

    def get_session(request: Request) -> Iterator[Session]:
        with Session(request.app.state.engine) as session:
            yield session

    def get_clock(request: Request) -> Clock:
        return request.app.state.clock

    def get_settings(request: Request) -> Settings:
        return request.app.state.settings

    def _bearer(authorization: str | None) -> str:
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="缺少认证信息")
        return authorization[7:].strip()

    def get_current_admin(
        request: Request,
        authorization: str | None = Header(default=None),
        settings: Settings = Depends(get_settings),
        clock: Clock = Depends(get_clock),
    ) -> dict:
        token = _bearer(authorization)
        try:
            payload = decode_token(token, settings.token_secret, now=clock.now())
        except TokenError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        if payload.get("role") != ROLE_ADMIN:
            raise HTTPException(status_code=403, detail="需要管理员权限")
        return payload

    def get_current_candidate(
        request: Request,
        authorization: str | None = Header(default=None),
        settings: Settings = Depends(get_settings),
        clock: Clock = Depends(get_clock),
    ) -> dict:
        token = _bearer(authorization)
        try:
            payload = decode_token(token, settings.token_secret, now=clock.now())
        except TokenError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        if payload.get("role") != ROLE_CANDIDATE:
            raise HTTPException(status_code=403, detail="需要考生权限")
        return payload

    app.state.get_session = get_session
    app.state.get_clock = get_clock
    app.state.get_settings = get_settings
    app.state.get_current_admin = get_current_admin
    app.state.get_current_candidate = get_current_candidate

    # ---------------- 异常映射 ----------------

    @app.exception_handler(ExamStateError)
    async def _exam_state_handler(_request: Request, exc: ExamStateError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

    # ---------------- 路由 ----------------

    from app.routers import admin as admin_router
    from app.routers import candidate as candidate_router

    app.include_router(candidate_router.build_router(get_session, get_clock, get_settings, get_current_candidate))
    app.include_router(
        admin_router.build_router(get_session, get_clock, get_settings, get_current_admin)
    )

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True}

    return app


app = create_app()
