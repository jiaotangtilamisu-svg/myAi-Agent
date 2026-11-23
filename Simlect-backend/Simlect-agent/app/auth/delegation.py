"""Server-only delegation boundary. Never populated from HTTP/model parameters."""

from contextlib import contextmanager
from contextvars import ContextVar

_delegated = ContextVar("supervisor_read_only_delegation", default=False)


def is_delegated():
    return _delegated.get()


@contextmanager
def read_only_delegation():
    marker = _delegated.set(True)
    try:
        yield
    finally:
        _delegated.reset(marker)


def deny_delegated_write():
    if is_delegated():
        raise ValueError(
            "统一调度只允许查询和建议；确认、审批和业务执行须通过原授权入口"
        )
