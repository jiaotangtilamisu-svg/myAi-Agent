# AI核心功能完整性审计与补齐报告

验收日期：2026-11-05（Asia/Shanghai）。项目根目录：E:\Simlect-AI-Mall-main\Simlect-AI-Mall-main。分支：feat/agent-safe-advice-product-search。未提交Git。

## 结论与验收口径

本轮完成源码审计、实质增量开发、自动化回归及必要服务加载。截图所要求的导购、案件确认、审批、退货物流、验收及模拟退款均有现有或新增业务调用链，不以页面按钮或HTTP200代替业务实现。现有Supervisor、两专业Agent、MCP、RAG、持久化、降级和退款安全隔离均保留。

**不能宣称所有生产场景和所有真实页面已最终验收。** 浏览器安全工具不能可靠识别当前URL，已停止UI操作，不绕过限制；无真实大模型、Embedding、承运商或真实资金验收。退货物流进度支持经人工核实后登记和查询，不伪装承运商实时数据；附件文件上传不在新案件模块实现，当前支持文本材料说明和既有诊断/政策证据。真实渠道退款继续关闭，模拟结果严格标注MOCK。

标记“已完整实现”指该功能存在业务实现并有本轮自动化证据，不等于未经执行的浏览器或真实第三方验收通过。下表另列运行范围。外部条件不足的项目标为部分实现或尚无法验证。

## 审计范围与修改前发现

先生成《AI核心功能修改前差距矩阵.md》，再修改代码。全文扫描79份阶段报告，并建立7659个Java/Python/Vue/TS/XML/SQL文件的路径、行数和SHA-256盘点；排除node_modules、target、虚拟环境等目录。Agent现有app目录131个源码/配套文件。盘点、报告标题及未完成事项摘要保存在.cache/core-audit-20261105/source-report-inventory.json。自动扫描不冒称逐行人工验证了所有文件。

沿实际链路重点复核：Agent入口、两专业图、Supervisor、MCP注册/路由、Product/Stock/Search、Order内部归属接口、案件Service/Mapper/DDL、支付渠道、前端聊天和管理端案件页，以及相关测试。

修改前主要缺口：

- 品牌/颜色的“优先”被当硬性条件；材质、尺寸、强制现货缺显式解析和校验。
- 用户无法登记退货物流；只有管理员登记接口。
- 退货物流缺可查询的进度/异常及核实来源。
- 用户确认只保存一段note，原因和材料不便查询；确认时应重新核验当前订单归属。
- 模拟退款结果藏在审计JSON；管理端缺失败模拟入口和明确原因。
- 管理界面允许对处理失败案件点归档，但服务端拒绝，前后端状态机不一致。
- 结构化确认记录直接渲染为原始JSON，消费者难以理解。

## 三张截图逐项核查矩阵

### 智能导购

Python路径基于Simlect-backend/Simlect-agent/；Java路径基于Simlect-backend/。

| 功能 | 最终判定 | 源码/调用链 | 本轮证据 |
|---|---|---|---|
| 商品类别与预算/价格区间 | 已完整实现 | app/shopping/requirements.py -> graph.py | test_core_shopping_constraints、test_shopping_agent；20以内/预算20元以内等价，杯子口语解析 |
| 品牌、颜色、材质、尺寸、使用场景 | 已实现但有边界 | requirements.py、selection.py | 新增品牌软偏好、材质/尺寸、日常场景和取消条件测试；受控字典/规则，不宣称穷尽所有自然语言 |
| 硬约束和软偏好 | 已完整实现 | requireInStock/attributes与preferredBrands/preferredAttributes分开 | 有货硬要求排除库存未知；优先品牌不排除其他品牌；同SKU属性核验 |
| 关键词、向量、混合召回 | 已完整实现（真实向量尚无法验证） | app/services/product_service.py -> app/rag/retriever.py | 全Python回归；本机关键词业务查询；未调用付费Embedding |
| RRF融合 | 已完整实现 | app/rag/rrf.py -> product_service.py | 现有RRF测试随本轮完整执行 |
| 品类与SKU精筛 | 已完整实现 | app/shopping/selection.py -> ProductAgentInternalController -> StockInternalController/queryBatch | 真实本机手机查询、全Java商品/搜索测试 |
| 售价、库存、在售状态、同SKU一致性 | 已完整实现 | ProductAgentQueryService与Python product_facts/selection | 未知价格不补0，库存0与未知分开，预算只依据已知同SKU售价 |
| 数据来源与查询时间 | 已完整实现 | product facts/dataProvenance/queryTime -> MCP -> shopping result | 实际业务工具返回；本地目录/设定库存不冒称供应商实时来源 |
| 2—3款对比 | 已完整实现 | shopping/graph.py、runner.render_comparison | 本机第一/第二、第一/第三返回指定真实ID；三款及无效引用由自动化覆盖 |
| 推荐理由、优势、不足 | 已完整实现 | selection.py事实完整度/条件匹配评分 | 推荐理由来自实际属性；缺续航等不编造性能；新增偏好评分中文标签 |
| 多轮预算/品类/偏好修改 | 已完整实现 | requirements.py、shopping/store.py、runner.py | 取消材质/现货/颜色、保留品类、便宜比较及用户隔离回归 |
| 无匹配/无库存 | 已完整实现 | graph状态与消费者展示 | 20元茶杯本机NO_RESULTS；不以其他杯具或演示商品补数 |

### 售后Agent

| 功能 | 最终判定 | 源码/接口 | 本轮证据 |
|---|---|---|---|
| 本人订单列表、指定订单详情 | 已完整实现 | app/supervisor/adapters.py、services/order_service.py -> OrderAgentInternalController | test_agent_order_security、OrderAgentOwnershipTest等本轮回归 |
| 订单商品/SKU/状态/多订单选择 | 已完整实现 | /internal/order/agent/getOrder、getOrderItem、listOrderItems | Java内部接口校验业务用户及父订单归属；多订单不擅自选一笔 |
| 物流查询 | 已完整实现（承运商实时准确性尚无法验证） | QUERY_LOGISTICS -> /internal/order/agent/getLogistics | 现有接口/权限Mock回归；不伪造轨迹 |
| 有效政策、分类、版本、期限、原文来源 | 已完整实现 | app/rag/retriever.py、policy.py、evidence_quality.py -> /internal/knowledge/catalog | Mock涵盖启停/期限/来源哈希；本机已发布法规词项浏览SUCCESS |
| 去重及法规/商城承诺区分 | 已完整实现 | rag/aftersales_topics.py、policy.py、evidence_quality.py | 七日、质量、运费、无依据等回归；未发布草稿不作为正式政策 |
| 售后资格 | 部分实现 | services/aftersales_diagnosis.py | 事实、冲突、时间/政策条件与不确定性；缺商品状态或正式商城规则时要求补充，未实现所有商品类别的自动最终资格裁定 |
| 提案/确认卡/主动提交 | 已完整实现 | api/routes/agent.py /aftersales/cases -> Java create -> AWAITING_USER；CONFIRM才提交 | draft与正式提交分离；本人已保存诊断；取消、幂等、拒绝越权覆盖 |
| 确认时后端重新核验 | 已完整实现 | AftersalesCaseService.command CONFIRM | 新增当前订单归属再查，失效回滚；原因/材料校验 |
| 编号/原因/文本材料/提交时订单状态 | 已完整实现（文本材料） | applicationNote、detail投影、AgentCasePanel | 实际H2序列化/反序列化及历史兼容测试；文件附件上传未新增 |
| 申请进度与驳回重提 | 已完整实现 | /order/aftersalesCase/list/detail/resubmit | 服务端状态/版本/权限及前端工具测试；本轮无真实案件状态变更 |

### 售后管理后台

| 功能 | 最终判定 | 源码/链路 | 本轮证据 |
|---|---|---|---|
| 列表/详情/订单/原因/材料/政策 | 已完整实现 | Simlect-front/Simlect-admin/src/views/order/AftersalesCases.vue -> /admin-api/aftersalesCase/list/detail | 全Java、Admin构建和工具测试；新原因/材料投影 |
| 审核通过/拒绝/意见/审计 | 已完整实现 | AftersalesCaseService APPROVE/REJECT、CaseAuthentication | 审核意见必填、管理员后端校验、事务回滚/并发幂等 |
| 用户登记退货物流公司/运单 | 已完整实现 | 新 /order/aftersalesCase/returnLogistics -> USER_RETURN_LOGISTICS | 审核后本人可提交；重复票据回放；他人/未审核拒绝；用户不能提交验收标志 |
| 退货物流状态、查询、异常跟进 | 部分实现（人工记录完整） | RETURN_PROGRESS及detail.fulfillment | 运输中/送达/异常，处理人记录核实说明；来源MANUAL_VERIFIED；无承运商实时接口验收 |
| 人工退货验收通过/不通过/意见 | 已完整实现 | RETURN_ACCEPT -> 审计及fulfillment.acceptance | 须先有用户或管理员运单；验收失败不得模拟退款；保留状态流转 |
| 模拟退款执行/成功/失败原因 | 已完整实现（隔离模拟） | MOCK_REFUND -> fulfillment.refundMode/refundStatus/failureReason | 默认关闭；隔离测试反射开启Mock；管理UI新增失败模拟选择；不产生资金调用 |
| 原单号重试/防重复/幂等 | 已完整实现（Mock及原业务接口） | 固定case+plan生成模拟单号；requestId+hash+actor、行锁与CAS；原商城锚点保留 | 失败重试同单号、成功禁止重做、过期版本拒绝、权限测试 |
| 类型限制 | 已完整实现 | 仅refund、return_refund | 其他类型服务端拒绝；用户填运单仅return_refund |
| 真实退款 | 安全关闭；尚无法验证 | 既有OrderInfoServiceImpl -> PayFeignSupport -> PayChannel4AliPay保留 | 全Java使用SDK Mock；Agent执行隔离保持；无真实资金验收 |

## 本次新增调用链与数据契约

购物：前端sendMessage -> app/api/routes/agent.py -> agent_service异步任务 -> agent_engine -> shopping.runner -> LangGraph -> mcp_tool_router -> MCP SEARCH_PRODUCTS/GET_PRODUCT_DETAIL -> Gateway -> Java Product回源 -> Stock批量 -> 同SKU筛选/偏好评分 -> 持久化与WebSocket推送。Supervisor通过独立专业图及结果契约调度，未把各图合并重写。

售后：用户消息 -> 专业图查本人订单、按需物流、RAG -> 保存诊断 -> 用户生成方案草稿 -> 填真实原因/可选文本材料 -> 主动CONFIRM -> Java再次核验当前订单归属 -> 按风险审核 -> 管理员接单 -> 用户登记退货物流 -> 处理人记录进度/异常 -> 验收 -> 隔离模拟退款或人工处理 -> 结果/失败/重试 -> 归档。

新字段来自现有审计，不重复建业务表：

- detail.applicationReason：最终确认的真实原因；applicationMaterials：最多两项350字文本；submittedOrderStatus：确认时重查的订单状态，不以旧诊断冒充当前状态。
- detail.fulfillment：type、carrier、trackingNo、logisticsStatus、logisticsSource、logisticsNote、acceptance、acceptanceNote、refundMode、refundStatus、refundId、failureReason、executionAllowed=false。
- 原历史普通文本CONFIRM note继续兼容；新内容以JSON保留在aftersales_audit.note，编码后超2000字符明确拒绝，不截断。
- 用户运单只保留type/carrier/trackingNo白名单；不能顺带提交accepted、退款结果或执行开关。进度来源明确为人工核实，不能当自动承运商查询。

## API清单与实际路由

| 消费端/内部路径 | 方法 | 含义 |
|---|---|---|
| /api/agent/sendMessage | POST | 异步发消息，不要求同步返回答案 |
| /api/agent/loadHistoryMessage、getMessage | POST | 历史/指定消息恢复 |
| /api/agent/supervisor/result、shopping/result | POST | 当前本人完整证据 |
| /api/agent/aftersales/cases | POST | 根据本人已保存消息生成草稿 |
| /api/order/aftersalesCase/list、detail | POST | 本人申请与履约投影 |
| /api/order/aftersalesCase/confirm、resubmit、archive | POST | 用户确认、补充、归档 |
| /api/order/aftersalesCase/returnLogistics | POST | 新增本人退货运单登记，JSON Command |
| /admin-api/aftersalesCase/list、detail | POST | 管理员案件查询 |
| /admin-api/aftersalesCase/approve、reject、claim、succeed、fail、retry、archive | POST | 现有人工审批/任务接口 |
| /admin-api/aftersalesCase/returnLogistics、acceptReturn、simulateRefund | POST | 管理员物流、验收及隔离模拟 |
| /admin-api/aftersalesCase/returnProgress | POST | 新增管理员物流状态/异常跟进 |
| /internal/product/agent/searchOnSale、queryBatch、getDetail | POST | 商品业务回源 |
| /internal/stock/queryBatch | POST | 同SKU批量库存 |
| /internal/order/agent/listOrders、getOrder、getOrderItem、listOrderItems、getLogistics | POST | 原订单工具入口，需内部身份+可信业务用户 |
| /internal/knowledge/catalog | POST | 发布状态、版本、有效期校验 |

管理端开发态6002的/api会改写为Gateway /admin-api，再转Order /admin/aftersalesCase/**。首次探针误用/api/admin路径得到404，属于验收路径错误，未修改路由去迁就；改用实际配置后，6002代理、Gateway及Order直连均返回901拒绝未登录。用户新端点经Gateway也返回901。它们证明加载和拒绝未登录，不冒称管理员实际业务操作已成功。

## 现有AI功能保留核查

| 能力 | 实现入口 | 本轮证据与限制 |
|---|---|---|
| Supervisor路由/复合任务/超时/结果校验 | app/supervisor/{routing,graph,adapters,contracts,aggregation,runner}.py | test_supervisor等完整回归；保留专业结果与失败，不无条件双调用 |
| 独立售后、独立导购 | app/graph/{builder,runner,aftersales_nodes}.py、app/shopping/* | 三模式入口agent_engine保持；跨模式提示保留 |
| MCP注册/传输/业务成功区分 | app/mcp_server/server.py、services/mcp_tool_router.py、mcp_tools_service.py | 全Python及本机实际商品工具调用 |
| RAG文档/版本/审核/向量索引 | rag/*及Search知识管理/消费者 | 全Java/Mock；本轮不改已发布法规和61向量 |
| 商品来源准入 | services/data_provenance.py、product_facts.py、shopping/selection.py | REAL/LOCAL_STORE准入保留，不将公开历史资料当实时商业商品 |
| 会话记忆/用户隔离/Checkpoint | app/memory/*、shopping/store.py、supervisor/store.py、graph/checkpointer相关代码 | test_memory_context、状态/安全回归；未提取用户登录令牌 |
| 模型超时/503/失败降级 | services/llm_factory.py、rag/advice.py、resilience/* | test_policy_model_resilience、test_policy_evidence_delivery等；真实API0 |
| 消息持久化/恢复/完整证据 | services/message_service.py、agent_runtime.py、stream_service.py、api/routes/agent.py | 大JSON、保存失败不发成功、先落库后通知、断线恢复Mock测试 |
| 取消、确认收货/评价提案 | pending_action及action_execute_service | 原功能保留，退款单独服务端阻断 |
| 管理员客服历史与政策管理 | Agent管理接口及Admin既有页面 | 未删除；Java/前端构建，真实页面交互尚未验证 |

其他模块未删减；没有重写LangGraph、MCP、商品服务或支付渠道。

## 修改文件清单

Java：

- Simlect-backend/Simlect-order/app/src/main/java/com/simlect/biz/AftersalesCaseService.java：新增USER_RETURN_LOGISTICS/RETURN_PROGRESS、申请原因材料结构化、CONFIRM重新核验归属、只读履约投影、Mock失败原因白名单。
- 同模块controller/aftersales/AftersalesUserController.java：用户物流端点。
- 同模块controller/aftersales/AftersalesAdminController.java：管理员进度端点。
- 同模块src/test/java/com/simlect/biz/AftersalesCasePersistenceTest.java：新增11项用户物流/权限/状态/材料/确认重查与履约投影测试；原幂等确认测试改为提供必填原因，不弱化重放断言。
- 同模块src/test/java/com/simlect/controller/aftersales/AftersalesCaseSecurityTest.java：新增3项新端点身份与权限测试。

Python（基于Simlect-backend/Simlect-agent）：

- app/shopping/requirements.py：软品牌/属性偏好、材质尺寸、现货硬条件、日常场景及取消条件。
- app/shopping/selection.py：同SKU硬属性/库存校验、软偏好可解释加分。
- app/shopping/runner.py：新评分项中文展示，修复首次回归暴露的KeyError。
- tests/test_core_shopping_constraints.py：新增12项需求、偏好、材质、尺寸、未知库存和同SKU校验。

前端：

- Simlect-front/Simlect-web/src/components/agent/AgentCasePanel.vue：申请原因/材料说明、编号、用户运单、履约与Mock结果，结构化时间线中文展示。
- 同项目src/utils/aftersalesCaseView.ts、tests/aftersalesCaseView.test.ts：新操作记录显示测试，避免原始JSON直接展示。
- Simlect-front/Simlect-admin/src/views/order/AftersalesCases.vue：原因材料、物流/验收/退款投影、进度异常记录、失败模拟选择及取消不误报。
- 同项目src/utils/caseManagement.mjs、tests/caseManagement.test.mjs：履约表单验证；失败案件不再显示服务端禁止的归档按钮；两项新增测试。
- 本报告及修改前差距矩阵；.cache/core-audit-20261105保存盘点、脚本及实际日志。

## 数据库和安全

只读核验现有simlect_order.aftersales_case、aftersales_plan、aftersales_manual_task、aftersales_audit四表：诊断/方案mediumtext，审计note varchar(2000)，现有行锁、版本和唯一约束可复用。**无DDL和数据迁移**，不需要新增表或执行迁移回滚。没有删除/覆盖历史数据，未执行TRUNCATE或向量重建。

只读聚合前后均为830个商品、3814个SKU、1个案件、2条案件审计（包含历史与下架记录，非全部在售）。未以真实账号创建/修改案件或订单。新增接口对正式数据只做未登录拒绝探针；写入测试均在新建隔离H2。

用户身份从现有Redis登录上下文解析，模型/请求体userId不能覆盖；内部Token与业务用户身份分开。新运单只能审核后本人填写；管理端进度/验收/模拟仅当前管理员处理人；所有更新行锁+expectedVersion/CAS+幂等requestId/actor/hash；同票据不同内容拒绝。

Agent退款隔离仍在。案件Mock退款默认false，SDK/真实支付依赖不注入案件服务；Mock不改变金融订单或资金余额。金额、退款资格和到账状态不能由LLM生成。原商城正常退款接口保留，但本轮无资金授权，不执行。

## 本轮自动化结果（最终实际执行）

| 范围 | 通过 | 失败/错误 | 跳过 | 证据 |
|---|---:|---:|---:|---|
| Python Agent全部及数据治理 | 767 | 0/0 | 0 | python.log/xml |
| Java根Maven全模块（1564发现） | 1562 | 0/0 | 2 | java-full.log、java-summary.json |
| 商城前端Node | 56 | 0/0 | 0 | web-tests.log |
| 管理端Node | 21 | 0/0 | 0 | admin-tests.log |

商城vue-tsc及生产构建通过，Admin生产构建通过。Admin是JS项目，无独立类型检查/ESLint脚本，不虚构命令或结果。Java本轮是全模块test，不是79项案件/归属专项：专项先通过，后纳入全量；不能相加重复计数。Java案件持久化55、案件权限11、订单内部接口16包含在全量内。

两个跳过均为既有AliEmailServiceImplTest.placeholder和serviceImplementsEmailService，类级Disabled因内部new真实阿里云客户端，未发送邮件。订单、退款、支付回调、案件权限未因此跳过。

首次Python回归12项失败来自新增评分标签遗漏，已修复；第二次并行构建时1项0.2秒Mock响应体超时测试在请求前耗尽预算，状态安全降级但未进入预期BODY阶段。保留原断言、生产20秒限制不变，待构建结束顺序重跑全部767通过。相关失败日志分别保留python-first-failed.log、python-concurrent-timeout.log，不隐瞒失败过程。没有以调整阈值、删测试或伪造向量使之通过。

## 本机实际业务读取验收

runtime-products.py加载当前源码、使用真实MCP/Gateway/Product/Stock，HTTP守卫阻断所有非本机请求，商品只读测试上下文不是有效用户登录，不绕过订单安全。

- 推荐3款3000元内手机取得3个真实商品ID：595164817409651、164500038733157、795322131166427。
- 比较第1/2款、第1/3款分别返回准确指定ID，只调用GET_PRODUCT_DETAIL重新读价格库存；不重新搜索错换对象。
- 20元内茶杯为NO_RESULTS，没有拿饮水杯冒充。
- 政策“查询售后政策”通过现有已审核主题浏览读取第778号法规，SUCCESS，返回第十八/十九条等真实Chunk，保留文档ID、版本及来源。该模式明确不是向量相似度；本轮没有真实Embedding。
- 新物流接口经实际代理/网关/后端验证未登录拒绝，code901，不把HTTP200作为业务成功。

本机工具测试不等于LLM测试，也不等于登录用户完整聊天持久化/浏览器操作。没有真实DeepSeek/Embedding、支付、退款、邮件或下单调用。

## 浏览器验收

按computer-use技能尝试选取现有Chrome窗口。工具返回：无法可靠确定当前浏览器URL，安全检查停止Computer Use。已停止UI路径，未使用CDP、提取Cookie或其他方式绕过。Playwright未在现有工程作为可用浏览器验收通道使用；不擅自安装新组件替代现有会话。

因此智能客服入口、三模式切换、历史、卡片/对比、完整证据、真实申请提交、管理员审批/物流/验收/模拟退款的**浏览器实际交互本轮均尚无法验证**。其源码、接口、构建和隔离测试有证据，但不能写成真实页面全部通过。待安全浏览器通道恢复或人工核验时，使用隔离账号/订单逐步点击；真实资金开关保持关闭。

## 实际服务加载

仅Order和Agent重载，日志/JAR先备份，其他核心服务未重启。

| 服务 | 当前PID | 端口 | 健康 |
|---|---:|---:|---|
| Gateway | 2532 | 8080 | UP |
| Order | 23336 | 8093 | UP，新JAR已加载 |
| Product | 5180 | 8099 | UP |
| Stock | 17448 | 8102 | UP |
| Search | 31048 | 8108 | UP |
| MCP | 10656 | 7060 | ok |
| Agent | 10668 | 7050 | ok，java_web=true |

Order JAR SHA256：88A2C073C346E820599E9F21A9E11A3ABE95C7937A6364929D5FBC45564F3910。
Order备份.cache/core-audit-20261105/order-reload-20261105-135355/；Agent备份.cache/stage31/commerce-ready/reload-20261105-135803/。前端Vite加载源码，另有生产构建通过。没有重启数据库/Docker中间件。

Order停止后曾因短暂监听记录未释放触发脚本安全退出；随即只读复核确认旧PID和端口均已消失，继续首次打包/启动，没有盲目杀进程或反复启动实例。现场错误与备份保留。健康检查仅证明进程/依赖，不冒充浏览器验收。

## 尚未完成和后续建议

1. 本轮真实浏览器全流程受安全工具限制，不能宣布最终页面验收完成。
2. 退货物流支持登记、人工核实状态、异常处理与查询；没有真实承运商数据源，不编造实时运输轨迹。需提供合法渠道后再接入。
3. 新案件支持文本材料及政策/订单证据；专门的照片附件上传、授权下载、文件安全检查尚未新增，不能称已具备完整附件系统。
4. 售后资格是证据约束的建议和人工审核，不是覆盖所有类别/政策的自动裁判；商城正式规则仍需业务确认，缺失条件明确补充。
5. 新产品目录/库存来自本机数据和参考快照，不是供应商实时商业库存；无真实来源时不能给真实销售保证。
6. 真实渠道退款的审批桥接、渠道结果未知查询/对账和持久化退款状态仍需单独实施审核；本轮允许的隔离模拟闭环已测试，但不能据此打开真实退款。
7. 所有真实LLM/Embedding及金融验收均未执行，需另行限定授权；不消耗真实Token来证明Mock通过。

本轮完成可独立实现的业务缺口，不删除任何已有AI功能；上述外部验收或业务规则问题如实保留，未虚报“全部生产验收完成”。

