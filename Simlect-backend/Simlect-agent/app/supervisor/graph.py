"""Supervisor LangGraph: route → sequential specialist calls → validate → organize facts."""

import asyncio
from functools import lru_cache
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.auth.agent_context import require_agent_user
from app.auth.delegation import read_only_delegation
from app.config.settings import get_settings
from app.services.agent_runtime import is_cancelled
from app.services.stream_service import stream_service
from app.supervisor import adapters
from app.supervisor.aggregation import aggregate
from app.supervisor.contracts import AgentResult, checked_result
from app.supervisor.routing import plan


class SupervisorState(TypedDict, total=False):
    user_id: str
    message_id: int
    text: str
    context: dict
    plan: dict
    results: dict
    report: dict
    cancelled: bool


async def identify_node(state):
    require_agent_user(state["user_id"])
    route = plan(state["text"], (state.get("context") or {}).get("lastRoute"))
    return {"plan": route, "results": {}}


async def execute_node(state):
    user = require_agent_user(state["user_id"]).user_id
    results = {}
    for task in state["plan"]["tasks"]:
        if await is_cancelled(user, state["message_id"]):
            return {"cancelled": True, "results": results}
        await stream_service.push_agent_status(
            user, state["message_id"], task["agent"], "RUNNING"
        )
        try:
            timeout = min(
                max(float(get_settings().supervisor_agent_timeout_seconds), 0.01), 120
            )

            async def delegated_call(task=task):
                with read_only_delegation():
                    return await adapters.invoke(task, user, state["message_id"])

            value = await asyncio.wait_for(delegated_call(), timeout)
            try:
                value = checked_result(value, task["agent"])
            except (ValueError, TypeError, KeyError):
                value = AgentResult(
                    agent=task["agent"],
                    status="INVALID_RESULT",
                    errorCode="CONTRACT_REJECTED",
                )
        except TimeoutError:
            value = AgentResult(
                agent=task["agent"], status="TIMEOUT", errorCode="SPECIALIST_TIMEOUT"
            )
        except Exception:  # noqa: BLE001 -- Provider details can contain private facts; never expose them.
            value = AgentResult(
                agent=task["agent"], status="ERROR", errorCode="SPECIALIST_FAILED"
            )
        results[task["agent"]] = value.model_dump()
        await stream_service.push_agent_status(
            user, state["message_id"], task["agent"], value.status
        )
        if value.status == "CANCELLED":
            return {"cancelled": True, "results": results}
    return {"results": results}


async def validate_node(state):
    require_agent_user(state["user_id"])
    clean = {}
    for task in state["plan"]["tasks"]:
        name = task["agent"]
        try:
            clean[name] = checked_result(state["results"][name], name).model_dump()
        except (ValueError, TypeError, KeyError):
            clean[name] = AgentResult(
                agent=name, status="INVALID_RESULT", errorCode="CONTRACT_REJECTED"
            ).model_dump()
    return {"results": clean}


async def summarize_node(state):
    return {"report": aggregate(state["plan"], state.get("results") or {})}


@lru_cache(maxsize=1)
def build_supervisor_graph():
    graph = StateGraph(SupervisorState)
    for name, node in (
        ("identify", identify_node),
        ("execute", execute_node),
        ("validate", validate_node),
        ("summarize", summarize_node),
    ):
        graph.add_node(name, node)
    graph.add_edge(START, "identify")
    graph.add_conditional_edges(
        "identify",
        lambda s: "execute" if s["plan"]["tasks"] else "summarize",
        {"execute": "execute", "summarize": "summarize"},
    )
    graph.add_conditional_edges(
        "execute",
        lambda s: END if s.get("cancelled") else "validate",
        {END: END, "validate": "validate"},
    )
    graph.add_edge("validate", "summarize")
    graph.add_edge("summarize", END)
    return graph.compile()
