# 18-智能售后异常诊断 Agent 实施报告

日期：2026-11-02。

项目根目录：`E:\Simlect-AI-Mall-main\Simlect-AI-Mall-main`。

分支：`feat/agent-safe-advice-product-search`；原基线 HEAD：`14726bf267daf7a3ffb622f5f3dff92e427a2541`。本轮未提交 Git，保留此前未提交源码与第 00～17 阶段报告。

## 一、交付范围

已实现现有 LangGraph 内的售后异常诊断分支，实际查询现有 MCP 订单/物流只读工具，检索第 17 阶段 RAG，融合查询状态、订单状态、物流节点时间、冲突和政策来源，返回结构化报告及建议。

采用确定性证据分诊，不依赖模型生成业务事实、政策期限或退款资格。无证据时明确输出不确定。没有新增微服务、Supervisor、生产依赖或数据库结构。

**本轮完成源码与 Mock/隔离测试，未部署到运行服务，未进行真实订单、物流和正式政策的线上联调。** 没有启动/停止服务、修改真实 `.env`、执行迁移、操作现有 FAQ/ES 数据、调用真实模型/Embedding 或执行退款、支付、邮件。

## 二、工作流结构

```text
原有 entry / 登录上下文
  → build_context：售后诊断意图识别、提取明确订单号
  → diagnosis_order：QUERY_ORDERS(includeFacts=true)
  → diagnosis_logistics：按需 QUERY_LOGISTICS(includeFacts=true)
  → diagnosis_policy：第 17 阶段 search_policy
  → diagnosis_analyze：证据校验、异常分型、冲突分析、建议和审核要求
  → 原 finalize：保存 JSON 业务数据并推送报告正文
  → 原 post_turn / cleanup
```

其他对话继续走原 `agent_loop ⇄ tools`；纯政策问题继续走第 17 阶段证据引用路径。“我要退款”等原退款提案请求保留原链路和执行隔离，不被普通诊断分支替代。

诊断意图包括 `LOGISTICS_STAGNATION`、`UNSHIPPED_ORDER`、`PAYMENT_ANOMALY`、`REFUND_PROGRESS`、`PRODUCT_QUALITY`、`AFTERSALES_CONSULT`。识别使用可测试的规则，明确标识订单号与真实 Java ID 格式，复用原订单/订单项 ID 解析器；多个不同订单或缺少订单号时请求澄清，不默认挑选最近订单。

物流只在物流停滞、以及需要核对的未发货场景查询。订单不可访问、登录校验失败或缺少订单号时，不继续物流和政策 Embedding 查询。每个新节点检查原 Redis 取消标志，取消后转入 cleanup，不继续后续查询。

## 三、修改文件及关键方法

下列文件均位于 `Simlect-backend/Simlect-agent/`，路径相对于项目根目录。

| 文件 | 本轮修改与关键方法 |
|---|---|
| `app/services/aftersales_facts.py`（新增） | `read_order_facts/read_logistics_facts`：复用原 Java 内部客户端，投影为有版本、来源、查询时间和状态的事实；去除收件人、地址、电话、支付单号等无关敏感字段 |
| `app/services/aftersales_diagnosis.py`（新增） | `identify_case/extract_order_id/fetch_facts/diagnose/render_diagnosis`：意图、明确订单号、MCP 结果验证、时区处理、确定性证据分析和报告 |
| `app/graph/aftersales_nodes.py`（新增） | `diagnosis_order_node/diagnosis_logistics_node/diagnosis_policy_node/diagnosis_analyze_node`：四个可取消的诊断节点 |
| `app/graph/builder.py` | 保留原主图，增加上述分支与取消条件边，继续复用原 checkpoint/finalize/post_turn/cleanup |
| `app/graph/state.py` | 增加诊断类型、订单号、订单事实、物流事实、政策结果和最终报告状态 |
| `app/graph/nodes.py` | `build_context_node` 增加诊断入口；`post_turn_node` 保存同一份证据报告正文 |
| `app/mcp_server/server.py` | 原 `QUERY_ORDERS/QUERY_LOGISTICS` 增加默认 false 的 `includeFacts`，继续使用原 `_verified_order_user` 登录校验 |
| `app/services/mcp_tool_router.py` | 透传明确布尔 `includeFacts`；保留 verified user 注入；诊断不对纯文本旧结果做本地回填，避免把失败掩盖成成功 |
| `app/services/tool_invoke_result.py` | 增加可选 `business_facts` / wire `businessFacts`；未使用新字段的工具返回方式兼容 |
| `app/services/agent_runtime.py` | `finalize_agent_response` 为诊断结果增加独立落库/推送分支，不让模型文本或动作 Token 覆盖报告，不进入动作确认解析 |
| `app/rag/policy.py` | 增加 `RETRIEVAL_ERROR` 用户提示，和无匹配、低分、Embedding/ES/目录故障分开 |
| `tests/test_aftersales_diagnosis.py`（新增） | 62 项分诊、MCP 认证、来源、异常、取消、LangGraph 集成和执行隔离测试 |
| `docs/agent-development/18-智能售后异常诊断Agent实施报告.md`（新增） | 本报告 |

Java 订单/物流接口、商品模块、退款执行模块、订单归属实现、前端和数据库均未修改。本轮开始时备份的现有 Python 文件位于 `.cache/aftersales-diagnosis-20261102/before/`，未用备份覆盖现有修改。

## 四、事实与诊断实现

### 1. MCP 事实协议

`businessFacts` 包含 `schemaVersion=1/kind/orderId/queryStatus/data/source/queriedAt`。

- 订单：调用现有 `/internal/order/agent/getOrder`，复用带明细的结果；再次核对返回的订单 ID 和所属用户。只保留订单状态、下单时间、是否有支付引用、订单项状态等必要字段。
- 物流：调用现有 `/internal/order/agent/getLogistics`，保留物流状态和节点时间，不把收件地址、手机号、运单号或轨迹地址带入报告。
- 登录失败返回 UNAUTHORIZED；订单不存在与不属于本人统一为 NOT_FOUND_OR_FORBIDDEN，避免泄露存在性；服务失败为 SERVICE_ERROR。物流空记录为 NO_RECORD，与服务失败分开。
- Agent 只接受版本、工具类型、订单号及数据结构匹配的结构化结果；普通文本“成功”、旧 MCP 协议、错误订单、未验证归属结果均不能成为诊断事实。

原工具默认 `includeFacts=false`，原聊天工具/订单卡片路径不变。运行验收时 MCP 与 Agent 都需要加载新代码；旧 MCP 不支持新参数时会明确失败，不静默回退猜测。

### 2. 订单与政策证据融合

RAG 使用第 17 阶段 `search_policy` 的版本、正文哈希和发布目录校验。检索查询使用诊断类别，不把用户 Token 或订单号送入 Embedding 查询。返回证据保留文档名称、版本、章节、页码、来源、分数及正文。

报告同时保留订单/物流查询来源和采集时间；建议包含当前事实查询状态、政策状态及具体政策引用。政策失败时增加“确认政策后再决定方案”的人工审核建议，不从普通 FAQ 或模型记忆补写规则。

处理结论分为：

| 诊断状态 | 含义 |
|---|---|
| CONFIRMED | 有明确业务异常证据，例如物流状态码 5；只确认异常标记，具体原因仍需核实 |
| NOT_OBSERVED | 当前限定事实不支持所述异常，不代表排除所有问题 |
| UNCERTAIN | 缺失订单、物流、政策适用条件、支付/退款流水或其他必要证据 |
| CONFLICT | 订单与物流状态冲突，或业务时间晚于检查时间，要求人工核对 |

`anomalyDetected` 为 true/false/null，null 表示无法确定。`confidence.level` 是证据充分程度，不是统计概率。

下单时间与物流节点时间只用于计算实际经过小时数；Java 无时区时间按当前项目中国本地时间 UTC+08:00 解析。不设置虚构的“48 小时不更新”“付款后几天必须发货”等政策阈值。

### 3. 各类建议的业务边界

- 物流：报告最新节点距今时长、显式异常状态；建议人工联系承运方。没有确认且可机器判定的时限时，不认定违反承诺。
- 未发货：区分待付款、已付待发货和已经发货状态；缺少承诺发货截止时间时，不能声称超时。
- 支付：有支付引用不代表实际扣款成功；不查询或执行支付，交由人工核对流水、回调和用户凭证。
- 退款：订单已退款/部分退款不等于银行卡或支付账户到账；缺少退款流水、申请/到账时间时明确无法判断超时。
- 质量：用户描述作为待核实陈述，不直接认定商品缺陷；建议保留照片和材料后人工审核。
- 冲突：明确列出冲突，降低信心并停止据此作业务裁定。

政策正文目前是自然语言检索片段，本轮不自动将其转换为可执行规则，也不对具体订单自动裁定退款资格；引用证据供人工核验适用性。报告明确区分异常状态和未经证实的根因。

## 五、结构化输出与前端传递

结构保存在原消息的 `bizData.aftersalesDiagnosis` 中，普通 `agent` 消息正文展示同源诊断说明，无需新增前端消息类型。结构字段包括：

```text
schemaVersion / caseType / orderId / checkedAt
diagnosis:
  status / anomalyDetected / reasons / conflicts / uncertainties / rootCause
orderFacts / logisticsFacts / policyEvidence / evidenceSources
confidence: level / meaning
recommendedActions[]:
  code / title / risk / basis / policyReferences / approvalRequired / executionAllowed
approvalRequired / executionAllowed
```

所有建议与报告的 `executionAllowed` 都固定为 false。`approvalRequired` 用于指示人工审核必要性，不是授权令牌，不会创建 pending action/actionId，也不存在诊断建议的确认执行入口。

## 六、测试结果

测试使用现有独立 Python 3.12 环境、隔离工作目录、虚拟密钥和 `.invalid` 模型地址；全部业务、模型、Embedding、RAG HTTP 访问使用 Mock，并启用现有外部网络阻断钩子。所有新日志/测试材料存放 E 盘。

| 测试范围 | 通过 | 失败 | 跳过 |
|---|---:|---:|---:|
| 新增售后诊断测试 | 62 | 0 | 0 |
| 原有 Python 回归（含商品增强、退款隔离、订单安全、第 17 阶段 RAG） | 262 | 0 | 0 |
| **本轮最终 pytest 合计** | **324** | **0** | **0** |

新增测试覆盖用户要求的 15 类场景：正常咨询、物流长时间不更新、未发货、退款进度、订单不可访问、他人订单、RAG 命中/无匹配/故障、订单/物流故障、证据冲突、不确定性、退款建议不可执行、伪造用户 ID。另覆盖质量与支付事实边界、双用户各自查询、缺失/多个订单号、旧 MCP/纯文本/损坏响应拒绝、来源版本保留、取消流程及字段隐私投影。

`test_actual_langgraph_branch_runs_tools_then_rag_then_analysis` 执行实际编译后的 LangGraph，验证调用顺序为 QUERY_ORDERS → QUERY_LOGISTICS → RAG，再进入诊断与最终消息保存；模型分类器设置为调用即失败，测试仍通过。网络及存储副作用均为 Mock，不能据此宣称真实运行链路已验收。

`test_runtime_ignores_model_text_and_action_tokens` 验证夹带编造金额与 action Token 的文本不会进入报告，动作确认解析器不会调用。原退款执行阻断和用户归属测试同时通过。

首轮为 307 通过、2 失败，均为本轮新测试样例：UTC/中国本地时间期望小时数错误、支付测试误带冲突物流；已修正样例并完整重跑。最终 324 项用例耗时约 4.23 秒。保留原始首轮日志，不伪装为首次全通过。

Ruff：新增 4 个 Python 文件全规则通过；修改的旧文件执行 E9/F63/F7/F82 检查通过，没有修复全项目遗留格式问题。现有 MCP 客户端弃用和 pytest-asyncio fixture loop-scope 提示仍存在。

本轮未改 Java/前端，因此未重复执行 Maven/前端构建；第 17 阶段 Java 928 项通过属于前轮记录，不计作本轮新执行结果。

证据：`.cache/aftersales-diagnosis-20261102/results/python-final.log`、`python-final.xml`；首轮为同目录 `python.log/python.xml`。

## 七、安全边界

1. 当前用户来自既有验证后的登录 ContextVar，`fetch_facts` 和 MCP 实现均再次验证；模型/请求传入的 userId 不能覆盖当前身份。
2. MCP 仍通过 `_verified_order_user` 按 HTTP 登录 Token 验证用户；Java 仍通过原接口再次验证用户与订单归属，内部 Token 不替代业务身份。
3. 新分支只固定调用 QUERY_ORDERS/QUERY_LOGISTICS 和已验证政策 retriever；不向模型提供自主业务执行机会，不调用写工具。
4. 原退款服务端执行保护与订单归属代码未修改；诊断报告也不携带可确认执行的 action Token。
5. 无证据、依赖失败、损坏或相互冲突的数据不会变成确定的售后规则、付款结论或退款到账结论。
6. 新代码不记录 Token、密钥、密码或完整原始订单；报告只包含当前用户可访问的必要事实。

## 八、未完成事项与后续运行验收

- **真实运行未部署**：审核后需受控加载新 MCP/Agent，并先完成第 17 阶段真实政策存储/发布的运行验收；本轮不自动重启。
- **政策与 SLA 未确认**：当前只能引用经第 17 阶段校验的文档；未来若要自动判定“超时”，需确认政策适用范围、时限及可靠业务起止时间，不能直接从检索分数推断。
- **支付/退款流水缺口**：当前复用的订单接口没有支付回调、退款申请和到账流水，报告明确不确定；后续可在授权范围内接入只读、严格归属校验的已有业务查询，不能伪造到账结论。
- **根因核查缺口**：物流显式异常不等于承运方责任已确认；质量描述不等于检验结论，需要人工或后续真实证据。
- **意图规则覆盖有限**：多意图句子目前按固定优先级选择一个主类；没有实现跨多个订单、跨轮自动选单或复杂规则解释器。
- **管理与报告 UI**：报告通过原消息正文和 bizData 返回，未新增诊断看板或人工审批执行页面。
- **真实验收建议**：使用授权隔离用户 A/B 与测试订单，核对实际 MCP 工具、Gateway/Java 查询、RAG 文档版本和消息 JSON；重复检查越权拒绝、依赖故障和退款保护。若需真实 Embedding 消耗，必须另行授权；不执行真实退款、支付或邮件。

本轮交付后暂停，等待审核；不提交 Git，不自动进入下一开发阶段。
