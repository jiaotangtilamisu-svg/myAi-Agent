"""Request-local identity, verified from the login session, never from model arguments."""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field


@dataclass(frozen=True)
class AgentUser:
    user_id: str
    token: str = field(repr=False)


_current_user: ContextVar[AgentUser | None] = ContextVar(
    "agent_verified_user", default=None
)


@contextmanager
def agent_user_context(user_id: str, token: str) -> Iterator[AgentUser]:
    if not user_id or not token:
        raise ValueError("登录身份无效，请重新登录")
    user = AgentUser(user_id, token)
    marker = _current_user.set(user)
    try:
        yield user
    finally:
        _current_user.reset(marker)


def current_agent_user() -> AgentUser | None:
    return _current_user.get()


def require_agent_user(user_id: str) -> AgentUser:
    user = current_agent_user()
    if user is None or not user_id or user.user_id != user_id:
        raise ValueError("当前登录用户身份校验未通过")
    return user
