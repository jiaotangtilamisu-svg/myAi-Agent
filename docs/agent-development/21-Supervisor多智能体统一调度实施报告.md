# 第21阶段：Supervisor 多智能体统一调度实施报告

实施日期：2026-11-02。当前分支：`feat/agent-safe-advice-product-search`。HEAD：`14726bf267daf7a3ffb622f5f3dff92e427a2541`。

本轮完成代码开发、隔离自动化测试和商城前端构建；未部署新代码、未启停服务、未提交 Git。工作区中第1至20阶段的未提交代码和报告均保留。以下文件路径均相对项目根目录 `E:/Simlect-AI-Mall-main/Simlect-AI-Mall-main`。

## 1. Supervisor 架构与实际工作流

新增独立的 LangGraph Supervisor，复用两个专业 Agent，不替换原售后或导购图：

```text
START → identify（意图及任务划分）
           ├─ 无明确任务 → summarize（澄清）→ END
           └─ execute（按计划调用专业 Agent）
                  → validate（结构、事实、安全约束校验）
                  → summarize（组织结构化证据）→ END
```

关键入口：`app/supervisor/graph.py:build_supervisor_graph`、`execute_node`，以及 `app/supervisor/runner.py:run_supervisor`（Python 路径均位于 `Simlect-backend/Simlect-agent/`）。

- `routing.py:plan` 使用可测试的确定性规则识别订单、物流、售后、购买、推荐、比较及复合意图。单一意图只调用一个 Agent；模糊意图不调用工具而请求澄清。
- 复合任务最多调用两个专业 Agent，目前按售后、导购顺序执行。一个失败或超时仍可保留另一个的有效结果，最终返回部分成功，不无条件同时调用。
- “退款到账后按同价位购买”等存在未验证跨域依赖的问题先澄清，不擅自推导退款金额或可用预算。
- 每个专业 Agent 默认超时60秒，服务端上限120秒；支持取消，不自动重试。当前未实现并行调度及持久化任务恢复。

## 2. 专业 Agent 复用与兼容改造

`app/supervisor/adapters.py:invoke` 只传递经过验证的用户身份、当前消息 ID 和受校验的任务文本。

**售后：**复用 `build_agent_graph(persist_checkpoint=False)` 的原有节点与边，使用 `collect_only` 返回诊断报告或政策检索结果。委派模式限定为既有只读诊断及政策分支，不进入旧通用执行动作循环。保留订单/物流事实、政策依据、冲突和不确定性。无订单号时澄清；仅在明确指代“这笔订单”等情况下复用该用户先前已验证订单号。

**导购：**调用原 `run_shopping_agent(..., collect_only=True)`，保留原需求理解、商品工具查询、筛选、评分及多轮购物上下文，直接收集完整结构化结果。

收集模式不发送子 Agent 的中间回答、不完成原消息、不进行售后会话绑定/解绑、不执行售后图的后置记忆模型总结，也不自动创建案件。普通售后、导购独立模式默认行为保留。Supervisor 统一保存一次最终消息并发送一次 DONE。

## 3. 状态传递、上下文隔离与并发控制

- `Task` 和 `AgentResult` 是禁止额外字段的 Pydantic 合约；任务不接受模型指定的 `userId`、工具名或执行参数。
- 每次调用仍通过 `require_agent_user` 验证可信登录上下文；原 Java 订单归属校验继续生效。
- Redis 主控键前缀为 `mall:agent:supervisor:<用户>`；只保留 `lastRoute`，不把商品事实混入售后记忆。复合任务不设单一后续路由，模糊“继续”会要求澄清。
- 售后主控提示单独存储于 `mall:agent:aftersales:supervisor:<用户>`，只保存订单号或政策查询引用；导购沿用已有独立购物上下文。
- 单用户主控租约300秒，写回和释放均用 Lua 校验持有者令牌，失效请求不能覆盖新请求状态或删除别人的锁。
- 完整结果按用户和消息 ID 缓存1小时，最大512 KiB；单个专业结果限制384 KiB。新增 `GET /api/agent/supervisor/result`，仅从当前认证用户的命名空间取结果，过期返回404。
- 未新增跨用户共享记忆或数据库结构。本轮的售后多轮保持是订单/政策引用，不等同于完整语义对话记忆。

## 4. 结果校验与汇总

`app/supervisor/contracts.py:checked_result` 对身份字段、执行标记、来源、订单归属标记、价格及库存结构进行校验。导购推荐必须有商品详情查询依据；可推荐 SKU 必须存在于原始 SKU 列表，价格、库存和库存查询状态必须一致。未知值保留 `null`，不能变为0。价格区间须与有效 SKU 已知价格一致；库存已知为零的 SKU 不能作为现货推荐。

售后结果保留政策文档名称、版本、章节、来源、相关度及证据原文；有冲突、证据不足或高风险时保留人工审核要求。所有执行标志均为 `false`。

`aggregation.py:aggregate` 基于校验后的结构化数据组织摘要、行动建议、证据来源和不确定性，不简单拼接两个 Agent 的自由文本，也不让另一个模型重新生成价格、库存或政策。原始专业数据深复制保留并计算 SHA-256 指纹，用于校验汇总前后数据一致性；该指纹不是上游真实性签名。

最终展示使用 `SUPERVISOR_RESULT`，包含统一说明、商品卡片及专业 Agent 状态。完整证据通过独立接口读取；过长展示采用简短提示而不截断 JSON 或政策条款。状态“查询完成”不表示退款、审批或支付完成。

## 5. 安全边界与审批兼容

新增 `app/auth/delegation.py:read_only_delegation`，使用仅服务端控制的 ContextVar。主控调用层和专业适配器均设置只读委派作用域，异常、取消后恢复；HTTP 参数和模型不能修改它。

委派期间：

1. MCP 路由及底层 MCP HTTP 客户端仅允许既有读工具。
2. `action_execute_service` 的执行入口及 `JavaBridge._post_form` 拒绝写入，不能通过直接构造动作绕过。
3. 子 Agent 的流式发布和消息完成/中断写回受抑制，创建用户消息及取消写入入口被阻断。
4. 即使配置允许自动建立售后案件，收集模式仍强制按需处理，不自动创建、确认、审批或执行。
5. 原有退款服务端隔离继续保留；未开放下单、支付、真实退款。

显式用户后续操作仍走原授权入口。`aftersales_case_service.create_from_message` 新增从本人已完成主控消息读取缓存诊断的兼容分支：核验消息归属、结果合约及诊断内容后，才复用原案件创建与 Java 订单归属校验。过期、他人、无诊断或不合法结果拒绝。审批仍由原服务端权限和状态机控制，主控结果不构成审批授权。

## 6. 修改文件清单

### Python 新增

| 路径（位于 Simlect-backend/Simlect-agent/） | 内容 |
| --- | --- |
| app/auth/delegation.py | 服务端只读委派作用域 |
| app/supervisor/__init__.py | 独立主控包 |
| app/supervisor/contracts.py | 任务/结果合约、事实与安全校验、数据指纹 |
| app/supervisor/routing.py | 单一/复合/模糊意图与后续路由 |
| app/supervisor/store.py | 用户级路由、售后引用、结果缓存、租约 |
| app/supervisor/adapters.py | 原售后与导购工作流适配 |
| app/supervisor/graph.py | LangGraph 调度、超时、取消、结果校验 |
| app/supervisor/aggregation.py | 证据组织及统一展示投影 |
| app/supervisor/runner.py | 主控入口、单次消息完成与状态发布 |
| tests/test_supervisor.py | 52项新增测试（含参数化用例） |

### Python 增量修改

| 路径（同上） | 本轮变化 |
| --- | --- |
| app/config/settings.py | 主控单 Agent 超时设置，默认60秒 |
| app/api/routes/agent.py | 三种模式及本人主控结果读取接口 |
| app/services/agent_service.py | 模式校验及支持上下文隔离 |
| app/services/agent_engine.py | 主控入口分派 |
| app/graph/state.py | 服务端 collect_only 状态 |
| app/graph/builder.py | 可选关闭委派图 checkpoint，原默认保留 |
| app/graph/nodes.py | 收集模式避免子消息、绑定及后置模型写入 |
| app/graph/case_nodes.py | 收集模式禁止自动建案 |
| app/shopping/runner.py | 可收集原导购结果，不重复完成消息 |
| app/services/mcp_tool_router.py | 委派读工具白名单 |
| app/services/mcp_streamable_client.py | 直连 MCP 客户端同层保护 |
| app/services/action_execute_service.py | 委派执行器及 Java 写入桥阻断 |
| app/services/message_service.py | 委派期间消息写入/取消保护 |
| app/services/stream_service.py | 抑制子流；发布校验后的执行状态元数据 |
| app/models/message_send.py | 可选 agentStatus，兼容原消息格式 |
| app/services/aftersales_case_service.py | 本人主控诊断结果显式建案兼容及类型校验 |
| tests/test_shopping_agent.py | 原非法模式测试改用 unknown_agent；supervisor 现已合法，原测试目的保留 |

### 前端（位于 Simlect-front/Simlect-web/）

| 路径 | 内容 |
| --- | --- |
| src/api/modules.ts | 增加 supervisor 模式和完整结果接口 |
| src/views/agent/AgentSendPanel.vue | 增加统一助手选项；保留售后、导购及原默认模式 |
| src/views/agent/AgentChatList.vue | 接收 Agent 状态事件，避免当回答文字处理 |
| src/components/agent/AgentChatItem.vue | 状态展示、统一结果、商品卡片、完整证据、政策及不确定性展示 |
| src/stores/agentMessage.ts | 可选状态类型 |
| src/utils/agentHistory.ts | 历史项可选状态兼容 |
| src/utils/agentExecution.ts（新增） | 允许状态、状态合并、中文标签及统一结果解析 |
| tests/agentExecution.test.ts（新增） | Node 内置测试，无新测试框架 |

本轮未修改 Java 业务代码、Maven/npm/Python 生产依赖、真实 .env、数据库或 Gateway 配置。已有文件修改前副本位于 `.cache/supervisor-20261102/before/`，均保存于 E 盘。

## 7. 测试环境、命令与真实结果

使用既有 Python 3.12 独立测试环境 `.venv-tests`，生产依赖通过既有测试 harness 导入；测试在独立工作目录运行。模型和 Embedding 使用假凭据、`.invalid` 地址及既有网络阻断 harness，未调用真实外部 API。Java 使用 JDK17、Maven 离线模式及既有禁止外部网络的测试安全管理器。未连接真实业务写接口。

| 检查范围 | 通过 | 失败/错误 | 跳过 |
| --- | ---: | ---: | ---: |
| Python 全量 pytest | 448 | 0 | 0 |
| 其中本轮 Supervisor 新增 | 52 | 0 | 0 |
| Java 选定现有回归模块 | 975 | 0 | 0 |
| 前端 Node 单元测试 | 6 | 0 | 0 |
| vue-tsc 类型检查 | 通过 | 0 | 不适用 |
| 商城 Vite/PWA 生产构建 | 通过 | 0 | 不适用 |
| 新主控包、delegation.py、test_supervisor.py 的 Ruff | 通过 | 0 | 不适用 |

Python 实际命令核心：`.venv-tests/Scripts/python.exe -m pytest -p pytest_asyncio.plugin tests -q --tb=short -o faulthandler_timeout=45 --junitxml=<结果路径>`，并关闭自动插件、使用既有网络拦截 harness。最终用时5.53秒；1条已有 MCP streamable 客户端弃用警告，不是失败。新增52项相对原396项。

Java 现有测试：`mvn -o ... -pl Simlect-common,Simlect-gateway,Simlect-search,Simlect-product/app,Simlect-stock/app,Simlect-order/app,Simlect-pay/app -am test`，沿用本地测试 settings 和网络隔离参数。common229、gateway41、search94、product117、stock39、order390、pay65，合计975。未声称执行没有包含的其他模块或运行态测试。

前端执行 `node --experimental-strip-types --test tests/agentExecution.test.ts`，以及实际 package.json 的 `npm run build`（包含 `vue-tsc -b` 和 Vite/PWA）。未安装或升级依赖。未新增全项目 ESLint 检查结论。

测试覆盖：售后、物流、购买、比较及复合路由；模糊/依赖意图澄清；Agent 切换；单 Agent 失败、超时与取消；跨用户及分域上下文；原售后图和导购适配；主控租约；真实结构的商品价格/SKU/库存零与未知；原始 SKU 一致性；政策来源、无匹配及不确定性；合约拒绝身份覆盖、执行标记和无依据数据；只读路由、MCP 客户端、执行器和消息写入边界；审批/退款隔离；显式本人案件桥接；HTTP 模式与结果归属；前端三模式及旧消息格式兼容。

测试开发中有一次新增测试错误引用不存在的模型工厂名称，修正为现有 `bind_agent_llm` 后重跑全量448项通过；没有删除失败用例或伪造模型调用通过结果。前端6项是解析和状态逻辑测试，并非浏览器点击端到端测试。

原始日志及机器可读结果位于：

- `.cache/supervisor-20261102/results/python-final.log`、`python-final.xml`
- `.cache/supervisor-20261102/results/java-final.log`、`java-summary.json`
- `.cache/supervisor-20261102/results/frontend-tests-final.log`
- `.cache/supervisor-20261102/results/frontend-final.log`

## 8. 尚未完成与后续运行验收

1. 本轮完成离线/Mock 开发验收，尚未将主控代码加载到运行服务，也未进行真实 MCP/Gateway 贯通或浏览器交互验收；不能据此认定线上运行通过。
2. 意图识别目前采用保守规则，未做真实模型语义路由。未覆盖的表达应澄清；跨领域金额等依赖不自动推断。
3. 复合任务为顺序调用，未实现并行、任务恢复或自动重试；主控只有用户级短期路由记忆，没有新建会话数据库。
4. 实时执行状态在连接期间展示，历史完整结果依赖1小时缓存。缓存过期不影响原最终摘要，但无法继续展开或用该缓存诊断创建案件，需重新查询。
5. 完整证据保留实际业务返回值和来源，准确性仍依赖原商品、库存、订单和已确认政策数据；不把指纹或 Mock 测试当成真实数据认证。
6. 后续授权运行验收应分别检查三模式切换、单 Agent 工具调用、复合任务部分失败、多用户结果访问、来源展示及显式案件创建，再检查原专业 Agent 独立模式。若使用真实模型/Embedding，必须另获授权。

本轮没有执行真实下单、支付、退款、邮件、数据库迁移、服务重启或 Git 提交。完成后暂停，等待审核。
