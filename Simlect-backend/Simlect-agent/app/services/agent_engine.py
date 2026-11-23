"""
================================================================================
文件：services/agent_engine.py
角色：极薄的「引擎门面」，把编排层与 LangGraph runner 隔开
================================================================================

【这个文件干什么】
agent_service 异步任务只依赖 AgentEngine.assistant_answer，
内部一行转到 graph.runner.run_agent_graph。方便以后换引擎实现而不改编排。

【流程位置】
agent_service._run_agent → agent_engine.assistant_answer → run_agent_graph → nodes...

【如何使用】
业务请用模块单例：await agent_engine.assistant_answer(agent_msg)
不要在 Controller 里直接 import runner（保持分层）。

【关联】agent_service、graph.runner；导读见 docs/智能客服-Java开发者导读.md
================================================================================
"""

from app.graph.runner import run_agent_graph  # LangGraph 图执行入口（节点编排、工具调用等）


class AgentEngine:
    """
    Agent 推理引擎门面类。
    类比 Java 里的 @Service AgentEngine：编排层只依赖本类，不直接依赖 graph 包。
    """

    async def assistant_answer(self, agent_msg: dict) -> None:
        from app.services.tool_audit import audit_message
        with audit_message(agent_msg.get('messageId')):
            await self._answer(agent_msg)

    async def _answer(self, agent_msg: dict) -> None:
        """
        执行一轮完整的 Agent 对话推理。

        参数 agent_msg 需至少包含：
        - userId：用户 ID
        - messageId：本条消息 ID（用于流式推送、落库）
        - userMessage：用户输入正文（可能含商品卡片 JSON）

        无返回值；结果通过 stream_service 推送，并通过 message_service 落库。
        """

        from app.services.agent_runtime import parse_agent_message, _persist_and_notify, _evidence_json
        from app.supervisor.routing import signals
        from app.auth.agent_context import require_agent_user
        _, text = parse_agent_message(agent_msg)
        after, buying = signals(text)
        mode = agent_msg.get("agentMode") or "support"
        from app.services.mode_routing import effective_mode
        mode=effective_mode(text,mode)
        agent_msg['agentMode']=mode
        import structlog
        structlog.get_logger().info('agent_mode_resolved',message_id=agent_msg.get('messageId'),requested_mode=agent_msg.get('requestedMode',mode),effective_mode=mode)
        if mode == "supervisor":
            from app.supervisor.runner import run_supervisor
            await run_supervisor(agent_msg)
        elif mode == "shopping":
            from app.shopping.runner import run_shopping_agent
            await run_shopping_agent(agent_msg)
        else:
            await run_agent_graph(agent_msg)  # 原客服/售后图保持独立


agent_engine = AgentEngine()  # 模块级单例，供 agent_service 等 import
