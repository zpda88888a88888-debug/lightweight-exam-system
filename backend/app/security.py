"""认证与凭证工具：HMAC 签名 token、邀请码生成、密码校验。

规格依据：spec 8 安全 / 架构 7、9.8、10

设计取舍：
    不引入 JWT 库，使用标准库 hmac + sha256 实现无状态签名 token，
    减少依赖面；token 内含角色、考试与考生标识及过期时间。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlmodel import Session, select

from app.models import ExamCandidate

ROLE_ADMIN = "admin"
ROLE_CANDIDATE = "candidate"


class TokenError(Exception):
    """token 无效、被篡改或已过期。"""


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def _sign(payload_bytes: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).digest()
    return _b64url_encode(digest)


def sign_token(payload: dict[str, Any], secret: str) -> str:
    """生成签名 token：base64url(payload).base64url(signature)。"""
    payload_bytes = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"{_b64url_encode(payload_bytes)}.{_sign(payload_bytes, secret)}"


def decode_token(token: str, secret: str, *, now: datetime) -> dict[str, Any]:
    """校验并解析 token。

    Raises:
        TokenError: 格式错误、签名不匹配或已过期。
    """
    if not token or token.count(".") != 1:
        raise TokenError("token 格式错误")
    payload_part, signature_part = token.split(".", 1)
    try:
        payload_bytes = _b64url_decode(payload_part)
    except Exception as exc:  # noqa: BLE001
        raise TokenError("token 载荷无法解码") from exc

    expected = _sign(payload_bytes, secret)
    if not hmac.compare_digest(expected, signature_part):
        raise TokenError("token 签名不匹配")

    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise TokenError("token 载荷非法") from exc

    exp = payload.get("exp")
    if exp is None or now.timestamp() > float(exp):
        raise TokenError("token 已过期")
    return payload


def issue_admin_token(secret: str, now: datetime, ttl_seconds: int, username: str) -> str:
    """签发管理员 token。"""
    return sign_token(
        {
            "role": ROLE_ADMIN,
            "sub": username,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=ttl_seconds)).timestamp()),
        },
        secret,
    )


def issue_candidate_token(
    secret: str,
    now: datetime,
    ttl_seconds: int,
    *,
    exam_id: int,
    user_id: int,
    phone: str,
) -> str:
    """签发考生 token。"""
    return sign_token(
        {
            "role": ROLE_CANDIDATE,
            "exam_id": exam_id,
            "user_id": user_id,
            "phone": phone,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=ttl_seconds)).timestamp()),
        },
        secret,
    )


def verify_admin_credentials(settings_username: str, settings_password: str, username: str, password: str) -> bool:
    """恒定时间比对的账号密码校验。"""
    user_ok = hmac.compare_digest(username or "", settings_username)
    pass_ok = hmac.compare_digest(password or "", settings_password)
    return user_ok and pass_ok


@dataclass(frozen=True)
class InviteCodeGenerator:
    """6 位数字邀请码生成器（全局唯一由调用方结合 DB 校验保证）。"""

    digits: int = 6

    def random_code(self) -> str:
        """生成一个密码学随机的数字邀请码（含前导零）。"""
        upper = 10 ** self.digits
        return f"{secrets.randbelow(upper):0{self.digits}d}"

    def generate_unique(self, session: Session, *, max_attempts: int = 200) -> str:
        """生成全局唯一邀请码。

        以数据库查询 + 唯一约束双重兜底；重试次数用尽则抛错。
        """
        for _ in range(max_attempts):
            code = self.random_code()
            exists = session.exec(
                select(ExamCandidate.id).where(ExamCandidate.invite_code == code)
            ).first()
            if exists is None:
                return code
        raise RuntimeError("邀请码生成重试次数用尽，无法得到全局唯一邀请码")
