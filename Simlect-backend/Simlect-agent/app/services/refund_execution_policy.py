"""Phase one is advice-only. No request, confirmation or environment flag enables refunds."""

import structlog

REFUND_ADVICE_ONLY_MESSAGE = (
    "当前智能客服仅提供退款建议，不执行退款。请前往商城订单页按正常售后流程申请。"
)
logger = structlog.get_logger()


def deny_agent_refund_execution() -> None:
    # Do not include tokens, action IDs, order details or the request body in this audit event.
    logger.warning(
        "agent_refund_execution_blocked", channel="agent", reason="advice_only"
    )
    raise ValueError(REFUND_ADVICE_ONLY_MESSAGE)
