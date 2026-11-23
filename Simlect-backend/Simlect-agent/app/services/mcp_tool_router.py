"""
================================================================================
文件：services/mcp_tool_router.py
角色：工具调用门面（白名单 + 参数校验 + 调 MCP + 本地卡片回填）
================================================================================

【这个文件干什么】
nodes.tools_node 不直接碰 HTTP，统一走 McpToolRouter.invoke：
1) ToolGuardrail：工具是否允许、userId 是否被篡改
2) mcp_streamable_client.call_tool：请求 :7060
3) 对 SEARCH_PRODUCTS / QUERY_ORDERS 可用本地 mcp_tools_service 回填卡片，
   防止 MCP 进程版本旧导致前端卡片丢字段

【流程】
invoke(tool_name, args, user_id)
  → is_allowed 白名单检查
  → 注入 userId + validate_tool_args 参数校验
  → _to_mcp_args 键名规范化（snake → camel）
  → mcp_streamable_client.call_tool 远程调用
  → parse_tool_wire 解析结果
  → _backfill_structured 本地回填卡片（可选）

【如何使用】
await mcp_tool_router.invoke(tool_name, args, user_id) → ToolInvokeResult

【关联】
tool_guard、mcp_streamable_client、mcp_tools_service、nodes.tools_node
【类比】带鉴权的 Feign 网关过滤器 + 防腐层。
================================================================================
"""

from __future__ import annotations  # import：延迟解析类型注解，允许在类定义前引用尚未定义的类型（类似 Java 泛型前向引用）

import structlog  # import：结构化日志库，输出 JSON 风格 key-value 日志，类比 SLF4J + MDC

from app.harness.guardrails.tool_guard import ToolGuardrail  # import：工具调用护栏 — 白名单校验 + 参数合法性检查
from app.harness.metrics.runtime_sensors import TOOL_CALL_TOTAL  # import：Prometheus Counter 指标 — 按 tool/status 维度计数
from app.auth.agent_context import require_agent_user
from app.services.mcp_streamable_client import mcp_streamable_client  # import：MCP Streamable HTTP 客户端单例，负责调 :7060
from app.services.tool_invoke_result import ToolInvokeResult, parse_tool_wire  # import：工具结果 DTO + Wire 字符串解析器

logger = structlog.get_logger()  # 获取本模块 logger 实例，后续 logger.info/warning/exception 都用它
tool_guard = ToolGuardrail()  # 模块级护栏单例 — 全局共享一份，类似 Java @Component 无状态 Bean


class McpToolRouter:  # MCP 工具路由器 — 门面类，类比 Java @Service，对外只暴露 invoke 入口
    """Dispatches tools via Streamable HTTP MCP server (not in-process)."""
    # ↑ 类 docstring（英文）：通过 HTTP 远程调 MCP 进程，不在 Agent 进程内直接执行业务

    async def invoke(self, tool_name, args, user_id):
        import time,re
        from app.services.tool_audit import business_status,message_id,transport_path,transport_status
        started=time.monotonic();status='ERROR';path_token=transport_path.set('GUARD');transport_token=transport_status.set('NOT_CALLED')
        try:
            result=await self._invoke(tool_name,args,user_id)
            status=business_status(result)
            if transport_path.get()=='GUARD':status='DENIED'
            return result
        finally:
            try:
                logger.info('agent_tool_result',tool=tool_name if re.fullmatch(r'[A-Z_]{1,64}',str(tool_name)) else 'INVALID_TOOL',
                            message_id=message_id.get(),path=transport_path.get(),transport_status=transport_status.get(),business_status=status,duration_ms=round((time.monotonic()-started)*1000,2))
            finally:
                transport_path.reset(path_token);transport_status.reset(transport_token)

    async def _invoke(
        self,
        tool_name: str,  # 工具名，如 "SEARCH_PRODUCTS"，须与白名单 / MCP server 注册名一致
        args: dict,  # LLM 传入的参数字典，键可能是 snake_case 或 camelCase
        user_id: str,  # 当前登录用户 ID — 由上层注入，不信任 LLM 传的 userId
    ) -> ToolInvokeResult:  # 返回统一结果 DTO，含 content 文本 + 可选 assistant_cards 卡片

        if not tool_guard.is_allowed(tool_name):  # 白名单检查：工具名不在允许列表则直接拒绝
            TOOL_CALL_TOTAL.labels(tool=tool_name, status="denied").inc()  # Prometheus：记录一次「拒绝」计数
            return ToolInvokeResult(content=f"未知工具: {tool_name}")  # 返回友好错误文案，不抛异常打断对话流
        from app.auth.delegation import is_delegated
        from app.harness.guardrails.tool_guard import READ_TOOLS
        if is_delegated() and tool_name not in READ_TOOLS:
            return ToolInvokeResult(content="统一调度不允许执行或创建待执行业务操作")

        if tool_name in {"QUERY_ORDERS", "QUERY_LOGISTICS", "QUERY_COMMENT", "PROPOSE_REFUND", "PROPOSE_CONFIRM_RECEIPT", "PROPOSE_PRODUCT_REVIEW", "PROPOSE_RECOMMENT"}:
            try:
                user_id = require_agent_user(user_id).user_id
            except ValueError:
                return ToolInvokeResult(content="【操作失败】当前登录用户身份校验未通过")

        raw = dict(args or {})  # 浅拷贝参数 Map — dict(args) 新建对象，避免修改调用方原始 dict
        raw["userId"] = user_id  # 强制覆盖 userId — 防止 LLM 伪造他人 ID 做越权操作

        if not tool_guard.validate_tool_args(tool_name, raw, user_id):  # 校验必填字段、类型、用户身份一致性
            TOOL_CALL_TOTAL.labels(tool=tool_name, status="invalid_args").inc()  # 指标：参数校验未通过
            return ToolInvokeResult(content="【操作失败】用户身份校验未通过")  # 返回校验失败提示给前端

        try:  # try-except 包裹远程调用 — 网络/MCP 异常在此捕获，不向上抛给 LangGraph
            mcp_args = self._to_mcp_args(tool_name, raw)  # 把 Python 侧 snake_case 键转为 MCP schema 期望的 camelCase
            from app.services.tool_audit import transport_path,transport_status
            transport_path.set('REMOTE_MCP')
            transport_status.set('FAILED')
            text = await mcp_streamable_client.call_tool(tool_name, mcp_args)  # 异步 HTTP 调 MCP 进程 :7060，返回 Wire 字符串
            transport_status.set('COMPLETED')
            result = parse_tool_wire(text)  # 解析 Wire 字符串 → ToolInvokeResult（可能含卡片 JSON）
            if mcp_args.get("includeFacts") is True:
                # Do not reinterpret text as business success or backfill an old MCP protocol.
                TOOL_CALL_TOTAL.labels(tool=tool_name, status="success" if (result.business_facts or {}).get("queryStatus") == "SUCCESS" else "error").inc()
                return result
            from app.services.tool_audit import business_status
            if business_status(result)=='ERROR':
                TOOL_CALL_TOTAL.labels(tool=tool_name,status='error').inc()
                return self._product_failure(tool_name,'【操作失败】业务工具未完成请求')
            result = await self._backfill_structured(tool_name, mcp_args, result)
            state = business_status(result).lower()
            TOOL_CALL_TOTAL.labels(tool=tool_name, status=state).inc()
            return result  # 必要时用本地逻辑回填/覆盖卡片
        except TypeError as e:  # 参数类型不匹配 — 如 MCP handler 缺必填参数导致 TypeError
            logger.warning("mcp_tool_bad_args", tool=tool_name, error_type=type(e).__name__)  # 结构化 warning 日志，便于排查
            TOOL_CALL_TOTAL.labels(tool=tool_name, status="bad_args").inc()  # 指标：参数类型/结构错误
            return self._product_failure(tool_name, "【操作失败】参数不完整")  # 用户可读的错误文案
        except Exception as e:  # 兜底：网络超时、MCP 500、JSON 解析失败等未预期异常
            logger.warning("mcp_tool_failed", tool=tool_name, error_type=type(e).__name__)  # exception 级别会附带完整堆栈
            TOOL_CALL_TOTAL.labels(tool=tool_name, status="error").inc()  # 指标：系统级错误
            return self._product_failure(tool_name, "【操作失败】系统处理异常，请稍后重试")  # 通用失败文案，不暴露内部细节

    @staticmethod
    def _product_failure(tool_name: str, text: str) -> ToolInvokeResult:
        if tool_name in {"SEARCH_PRODUCTS", "GET_PRODUCT_DETAIL"}:
            from app.services.product_facts import failure_result, render_facts
            data = failure_result()
            return ToolInvokeResult(content=render_facts(data), product_query=data)
        return ToolInvokeResult(content=text)

    async def _backfill_structured(
        self,
        tool_name: str,  # 当前调用的工具名 — 决定走哪条回填分支
        mcp_args: dict,  # 已规范化为 camelCase 的参数 — 传给本地 mcp_tools_service
        result: ToolInvokeResult,  # MCP 远程返回的解析结果 — 可能被本地结果覆盖
    ) -> ToolInvokeResult:  # 返回最终 ToolInvokeResult — 优先保证前端卡片字段完整
        """Prefer in-process tool logic so MCP process drift cannot serve stale search/order cards."""
        # ↑ 英文 docstring：优先用 Agent 进程内逻辑，防止 MCP 进程版本旧导致搜索/订单卡片缺字段

        if tool_name in {"SEARCH_PRODUCTS", "GET_PRODUCT_DETAIL"}:
            # Never rerun retrieval/embedding to conceal an MCP failure or stale protocol.
            from app.services.product_facts import failure_result, render_facts
            data = result.product_query
            if not isinstance(data, dict) or data.get("schemaVersion") != 2 or data.get("queryStatus") not in {"SUCCESS", "NOT_FOUND", "SERVICE_ERROR"} or not isinstance(data.get("products"), list):
                data = failure_result()
                return ToolInvokeResult(content=render_facts(data), product_query=data)
            result.content = render_facts(data)
            return result

        if result.assistant_cards or result.biz_type:  # MCP 结果已含结构化卡片或 biz_type 标识
            return result  # 无需回填，直接返回 MCP 结果

        if tool_name != "QUERY_ORDERS":  # 除 QUERY_ORDERS 外，其他工具到此直接返回
            return result  # 非订单查询工具 — 不做本地回填

        return result  # Missing order protocol is UNKNOWN, never replay a query to hide it.

    def _to_mcp_args(self, tool_name: str, args: dict) -> dict:  # 私有方法：参数键名 snake_case → camelCase 映射
        """Normalize to camelCase keys expected by MCP tool schemas."""
        # ↑ 英文 docstring：规范化为 MCP 工具 schema 期望的 camelCase 键名

        # lambda 辅助函数 g：按 keys 顺序取 args 中第一个存在且非 None 的值 — 兼容 snake/camel 两种键名
        g = lambda *keys: next((args[k] for k in keys if k in args and args[k] is not None), None)
        uid = g("userId", "user_id")  # 用户 ID — 优先 camelCase，回退 snake_case

        if tool_name == "SEARCH_PRODUCTS":  # 商品搜索工具参数映射
            out = {"userId": uid, "keyword": g("keyword") or ""}  # 构造 camelCase 请求体 — keyword 默认空串
            ex = g("excludeProductId", "exclude_product_id")  # 排除商品 ID — 兼容两种键名
            if ex is not None:  # 有值才加入 — 避免向 MCP 传 null 导致 schema 校验失败
                out["excludeProductId"] = ex
            return out  # 返回 SEARCH_PRODUCTS 专用参数 Map

        if tool_name == "QUERY_ORDERS":  # 订单查询工具参数映射
            out = {"userId": uid}  # 至少传 userId — 必填
            if args.get("includeFacts") is True:
                out["includeFacts"] = True
            oid = g("orderId", "order_id")  # 订单 ID — 可选
            if oid is not None:  # 有 orderId 则查单笔，无则查最近列表
                out["orderId"] = oid
            return out

        if tool_name == "GET_PRODUCT_DETAIL":  # 商品详情工具 — 固定 userId + productId 两字段
            if "productIds" in args:
                return {"userId": uid, "productIds": args["productIds"]}
            return {"userId": uid, "productId": g("productId", "product_id")}

        if tool_name in ("QUERY_LOGISTICS", "QUERY_COMMENT", "PROPOSE_CONFIRM_RECEIPT"):  # 共用 userId+orderId 的工具组
            if tool_name == "QUERY_LOGISTICS" and args.get("includeFacts") is True:
                return {"userId": uid, "orderId": g("orderId", "order_id"), "includeFacts": True}
            return {"userId": uid, "orderId": g("orderId", "order_id")}

        if tool_name == "QUERY_USER_COUPONS":  # 优惠券查询 — userId 必填，status 可选筛选
            out = {"userId": uid}
            st = g("status")  # 优惠券状态：0 未使用 / 1 已使用 / 2 已过期
            if st is not None:
                out["status"] = st
            return out

        if tool_name == "PROPOSE_REFUND":  # 退款提案 — 需要 orderItemId（订单项 ID）
            return {"userId": uid, "orderItemId": g("orderItemId", "order_item_id")}

        if tool_name == "PROPOSE_PRODUCT_REVIEW":  # 评价提案 — 四个字段
            return {
                "userId": uid,
                "orderId": g("orderId", "order_id"),  # 订单 ID
                "commentContent": g("commentContent", "comment_content"),  # 评价正文
                "star": g("star"),  # 星级 1-5
            }

        if tool_name == "PROPOSE_RECOMMENT":  # 追评提案 — 三个字段
            return {
                "userId": uid,
                "orderId": g("orderId", "order_id"),  # 订单 ID
                "reCommentContent": g("reCommentContent", "re_comment_content"),  # 追评正文
            }

        return {"userId": uid}  # 未知工具 — 兜底只传 userId，由 MCP 侧决定是否够用


mcp_tool_router = McpToolRouter()  # 模块级单例 — graph/nodes 直接 `from ... import mcp_tool_router` 使用
