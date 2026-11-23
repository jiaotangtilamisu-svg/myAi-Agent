"""Independent shopping LangGraph; only SEARCH_PRODUCTS and GET_PRODUCT_DETAIL reads."""

import re
from datetime import UTC, datetime
from functools import lru_cache
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
import structlog

from app.auth.agent_context import require_agent_user
from app.config.settings import get_settings
from app.services.agent_runtime import is_cancelled
from app.services.mcp_tool_router import mcp_tool_router
from app.shopping.extraction import extract
from app.shopping.selection import select

logger = structlog.get_logger()


class ShoppingState(TypedDict, total=False):
    user_id: str
    message_id: int
    text: str
    previous: dict
    understanding: dict
    requirements: dict
    status: str
    ids: list
    products: list
    selected: dict
    result: dict
    tools: list
    recall: dict


async def cancelled(state):
    require_agent_user(state["user_id"])
    return await is_cancelled(state["user_id"], state["message_id"])


async def understand_node(state):
    if await cancelled(state):
        return {"status": "CANCELLED"}
    prior = state.get("previous") or {}
    parsed = await extract(
        state["text"], prior.get("requirements"), prior.get("baseline")
    )
    if parsed["compare"] and not prior.get("ids"):
        parsed["clarification"] = "当前没有上轮商品可比较，请先搜索商品。"
    if parsed['compare']:
        positions=parsed.get('comparisonPositions') or list(range(1,len(prior.get('ids',[]))+1))
        if any(i<1 or i>len(prior.get('ids',[])) for i in positions) or not 2<=len(positions)<=3:
            parsed['clarification']='请指定上一轮中2～3款存在的商品进行比较；不会自动补选其他商品。'
        elif str(parsed.get('clarification') or '').startswith('想选什么商品'):
            parsed['clarification']=None
        if '第' in state['text'] and not parsed.get('comparisonPositions'):
            parsed['clarification']='请用有效的整数序号指定要比较的商品，例如第一款和第二款。'
        parsed['requirements']['requestedCount']=max(2,len(positions))
    return {
        "understanding": parsed,
        "requirements": parsed["requirements"],
        "status": "NEEDS_CLARIFICATION" if parsed["clarification"] else "READY",
    }


def wire(result):
    data = result.product_query
    if (
        not isinstance(data, dict)
        or data.get("schemaVersion") != 2
        or data.get("queryStatus") not in {"SUCCESS", "NOT_FOUND"}
        or not isinstance(data.get("products"), list)
    ):
        raise ValueError("No verified product response")
    for p in data["products"]:
        if not isinstance(p, dict) or not re.fullmatch(
            r"[A-Za-z0-9_-]{1,64}", str(p.get("product_id") or "")
        ):
            raise ValueError("Invalid product reference")
    return data


async def search_node(state):
    if await cancelled(state):
        return {"status": "CANCELLED"}
    if state["understanding"]["compare"]:
        prior=state['previous']['ids']
        positions=state['understanding'].get('comparisonPositions') or list(range(1,len(prior)+1))
        return {"ids": [prior[i-1] for i in positions][:12], "tools": [],"status":"READY"}
    req = state["requirements"]
    query = "category:" + req["categoryId"] if req.get("categoryId") else req["keyword"]
    if not req.get('categoryId') and req.get('brands'):
        query='criteria:'+' '.join([query,*req['brands'],*req.get('attributes',{}).values()])
    try:
        data = wire(
            await mcp_tool_router.invoke(
                "SEARCH_PRODUCTS", {"keyword": query}, state["user_id"]
            )
        )
        # Search facts already come from Java; preselect before the batch limit so
        # accessories/expensive hits do not consume the whole recall window.
        candidates=select(data['products'],{**req,'requestedCount':12},data_mode=get_settings().shopping_data_mode)
        preferred=[p['productId'] for p in candidates['recommendations']]
        ids = (preferred or list(dict.fromkeys(p["product_id"] for p in data["products"])))[:12]
        logger.info("shopping_tool_result", message_id=state["message_id"], tool="SEARCH_PRODUCTS", query_status=data["queryStatus"], count=len(ids))
        return {
            "ids": ids,
            "status": "READY" if ids else "NO_RESULTS",
            "tools": ["SEARCH_PRODUCTS"],
            "recall": data,
        }
    except Exception:  # noqa: BLE001 -- Fail closed rather than treating tool failure as no matches.
        return {"status": "TOOL_ERROR", "ids": [], "tools": ["SEARCH_PRODUCTS"]}


async def detail_node(state):
    if await cancelled(state):
        return {"status": "CANCELLED"}
    try:
        data = wire(
            await mcp_tool_router.invoke(
                "GET_PRODUCT_DETAIL", {"productIds": state["ids"]}, state["user_id"]
            )
        )
        rows = data["products"]
        rows = sorted(rows,key=lambda r:state['ids'].index(r['product_id']))
        logger.info("shopping_tool_result", message_id=state["message_id"], tool="GET_PRODUCT_DETAIL", query_status=data["queryStatus"], count=len(rows))
        if len(rows) != len(state["ids"]) or {r["product_id"] for r in rows} != set(
            state["ids"]
        ):
            raise ValueError("Incomplete or mismatched detail batch")
        return {
            "products": rows,
            "tools": [*(state.get("tools") or []), "GET_PRODUCT_DETAIL"],
        }
    except Exception:  # noqa: BLE001 -- Never reuse stale search facts after a failed detail query.
        return {
            "status": "TOOL_ERROR",
            "products": [],
            "tools": [*(state.get("tools") or []), "GET_PRODUCT_DETAIL"],
        }


async def select_node(state):
    if await cancelled(state):
        return {"status": "CANCELLED"}
    if "GET_PRODUCT_DETAIL" not in (state.get("tools") or []) or (
        not (state.get("understanding") or {}).get("compare")
        and "SEARCH_PRODUCTS" not in (state.get("tools") or [])
    ):
        return {"status": "TOOL_ERROR", "selected": {}}
    selected = select(state["products"], state["requirements"], data_mode=get_settings().shopping_data_mode)
    return {
        "selected": selected,
        "status": "SUCCESS" if selected["recommendations"] else "NO_MATCHING_SKU",
    }


async def compose_node(state):
    return {
        "result": {
            "schemaVersion": 1,
            "agentType": "shopping",
            "dataMode": "REAL" if (state.get("requirements") or {}).get("requireRealData") else get_settings().shopping_data_mode,
            "status": state["status"],
            "requirements": state.get("requirements") or {},
            "requirementSource": (state.get("understanding") or {}).get(
                "source", "rules"
            ),
            "clarification": (state.get("understanding") or {}).get("clarification"),
            "requirementEvidence":(state.get("understanding") or {}).get("fieldEvidence",{}),
            "recommendations": (state.get("selected") or {}).get("recommendations", []),
            "matchingCount": (state.get("selected") or {}).get("matchingCount", 0),
            "isComparison": bool((state.get('understanding') or {}).get('compare')),
            "comparison": (state.get("selected") or {}).get("comparison", []),
            "excluded": (state.get("selected") or {}).get("excluded", []),
            "retrieval":(state.get("recall") or {}).get("retrieval",{}),
            "toolsCalled": state.get("tools") or [],
            "queryTime": datetime.now(UTC).isoformat(),
            "executionAllowed": False,
        }
    }


@lru_cache(maxsize=1)
def build_shopping_graph():
    graph = StateGraph(ShoppingState)
    for name, node in (
        ("understand", understand_node),
        ("search", search_node),
        ("details", detail_node),
        ("select", select_node),
        ("compose", compose_node),
    ):
        graph.add_node(name, node)
    graph.add_edge(START, "understand")
    graph.add_conditional_edges(
        "understand",
        lambda s: "search" if s["status"] == "READY" else "compose",
        {"search": "search", "compose": "compose"},
    )
    graph.add_conditional_edges(
        "search",
        lambda s: "details" if s["status"] == "READY" else "compose",
        {"details": "details", "compose": "compose"},
    )
    graph.add_conditional_edges(
        "details",
        lambda s: "select" if s["status"] == "READY" else "compose",
        {"select": "select", "compose": "compose"},
    )
    graph.add_edge("select", "compose")
    graph.add_edge("compose", END)
    return graph.compile()
