"""Small, versioned projections of existing authenticated Java reads. No writes."""

from datetime import datetime

from app.auth.agent_context import require_agent_user
from app.services.java_internal_client import java_internal_client
from app.services.tool_invoke_result import ToolInvokeResult


def envelope(
    kind: str, order_id: str | None, status: str, data=None
) -> ToolInvokeResult:
    return ToolInvokeResult(
        content=f"售后{kind}事实查询：{status}",
        business_facts={
            "schemaVersion": 1,
            "kind": kind,
            "orderId": order_id,
            "queryStatus": status,
            "data": data,
            "queriedAt": datetime.now().astimezone().isoformat(),
            "source": f"java.order.agent.{kind}",
        },
    )


def scalar(value):
    return (
        value if type(value) in (str, int, float, bool) or value is None else str(value)
    )


async def read_order_facts(user_id: str, order_id: str | None) -> ToolInvokeResult:
    try:
        user = require_agent_user(user_id)
    except ValueError:
        return envelope("order", order_id, "UNAUTHORIZED")
    if not order_id:
        return envelope("order", order_id, "MISSING_ORDER_ID")
    try:
        row = await java_internal_client.get_order(user.user_id, order_id)
        if not row:
            # Deliberately indistinguishable from an order belonging to someone else.
            return envelope("order", order_id, "NOT_FOUND_OR_FORBIDDEN")
        if (
            str(row.get("user_id")) != user.user_id
            or str(row.get("order_id")) != order_id
        ):
            return envelope("order", order_id, "NOT_FOUND_OR_FORBIDDEN")
        items = row.get("items") or []
        if not isinstance(items, list):
            return envelope("order", order_id, "SERVICE_ERROR")
        data = {
            "orderId": order_id,
            "ownerVerified": True,
            "orderStatus": scalar(row.get("order_status")),
            "orderTime": scalar(row.get("order_time")),
            "hasPaymentReference": bool(row.get("pay_order_id")),
            "items": [
                {
                    "orderItemId": scalar(i.get("order_item_id")),
                    "orderItemStatus": scalar(i.get("order_item_status")),
                }
                for i in items
                if isinstance(i, dict)
            ],
        }
        return envelope("order", order_id, "SUCCESS", data)
    except Exception:  # noqa: BLE001 -- Boundary fails closed without exposing provider errors.
        return envelope("order", order_id, "SERVICE_ERROR")


async def read_logistics_facts(user_id: str, order_id: str) -> ToolInvokeResult:
    try:
        user = require_agent_user(user_id)
    except ValueError:
        return envelope("logistics", order_id, "UNAUTHORIZED")
    try:
        # Java rechecks both the logged-in token and order ownership for this read.
        row = await java_internal_client.get_logistics(user.user_id, order_id)
        if not row:
            return envelope("logistics", order_id, "NO_RECORD")
        if str(row.get("order_id")) != order_id:
            return envelope("logistics", order_id, "SERVICE_ERROR")
        records = row.get("record_list") or []
        if not isinstance(records, list):
            return envelope("logistics", order_id, "SERVICE_ERROR")
        # No receiver name, phone, address or tracking number enters a diagnosis.
        data = {
            "orderId": order_id,
            "logisticsStatus": scalar(row.get("logistics_status")),
            "dataClass": "DEMO" if any("LOCAL DEMO" in str(value).upper() or "NO PHYSICAL DELIVERY" in str(value).upper()
                for value in [row.get("receiver_address"), row.get("sender_address"),
                              *(r.get("record_address") for r in records if isinstance(r, dict))]) else "UNKNOWN",
            "records": [
                {"recordTime": scalar(r.get("record_time"))}
                for r in records
                if isinstance(r, dict)
            ],
        }
        return envelope("logistics", order_id, "SUCCESS", data)
    except Exception:  # noqa: BLE001 -- Boundary fails closed without exposing provider errors.
        return envelope("logistics", order_id, "SERVICE_ERROR")
