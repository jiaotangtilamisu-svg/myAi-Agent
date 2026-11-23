from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request

from app.auth.agent_context import agent_user_context

from app.auth.token_service import TokenUserInfo, require_login

__all__ = ["TokenUserInfo", "require_login", "get_request_token"]

async def require_agent_login(request: Request, user: Annotated[TokenUserInfo, Depends(require_login)]) -> AsyncIterator[TokenUserInfo]:
    # Child asyncio tasks inherit this context; credentials never enter graph state or prompts.
    with agent_user_context(user.user_id, (get_request_token(request) or user.token or "").strip()):
        yield user


def get_request_token(request: Request) -> str | None:

    return request.headers.get("token") or request.cookies.get("token")
