# 20-智能导购 Agent 实施报告

日期：2026-11-02。项目根目录：`E:\Simlect-AI-Mall-main\Simlect-AI-Mall-main`。

分支：`feat/agent-safe-advice-product-search`；HEAD 仍为 `14726bf267daf7a3ffb622f5f3dff92e427a2541`。未提交 Git，保留此前售后、案件、商品、RAG 代码和报告修改。

## 一、实际交付

已实现独立的 Python 导购 LangGraph、购物条件理解、只读 MCP 召回和批量详情、同一 SKU 约束筛选、可解释排序、结构化比较及多轮购物上下文。现有聊天界面新增明确的“售后客服 / 智能导购”选择，继续复用消息、推送和商品卡片组件。

本轮为源码及自动化测试交付，**未主动加载后台服务的新代码，未做真实模型/Embedding/商品中间件端到端运行验收**。没有启动或停止服务、修改真实 `.env`、执行数据库迁移、真实下单/支付/退款或提交 Git。

## 二、独立工作流

```text
用户明确选择 shopping 模式
  → 复用原 sendMessage：登录、限流、消息落库与后台任务
  → 独立 shopping.runner：验证身份、获取购物上下文锁
  → START
  → understand：解析本轮购物条件并合并上一轮要求
  → 条件不足？是 → compose：澄清问题
  → search：SEARCH_PRODUCTS，或比较模式复用上一轮商品 ID
  → details：GET_PRODUCT_DETAIL(productIds)，批量查询最新详情及 SKU 库存
  → select：SKU 筛选、真实属性比较、确定性评分排序
  → compose：结构化结果
  → END
  → 带锁校验保存购物上下文与报告
  → 复用原消息保存、商品卡片及 push_done
```

默认 support 模式仍进入原客服/售后图，未修改其节点或案件流转。不根据聊天内容偷偷切换 Agent，没有开发 Supervisor。

导购独立图位于 `app/shopping/graph.py`，可以直接对编译后的图传入已验证用户及购物输入获取结构化结果。图不复用售后记忆或订单状态，也不绑定退款、下单和支付工具。

## 三、需求解析

### 确定性解析

`requirements.understand` 解析并保留：

- 品类及明确 categoryId，或通用搜索关键词。
- 预算上下限、元/千/k/万单位；支持修改预算、取消预算、严格“低于”边界，负预算、非人民币预算及反向区间要求澄清。
- 品牌偏好、多个已识别品牌和品牌排除；支持显式自定义品牌字段。
- 办公、游戏、学习、通勤等使用场景。
- 颜色、颜色排除、内存规格、最低标称续航，以及轻便/防水等偏好。
- 相对要求：“更便宜”使用上轮已知最低 SKU 价格作为严格上界；“续航更长”使用上轮最大可解析标称小时数作为严格下界。

只给商品品类或关键词即可搜索，不要求填写完整条件；只有预算时会询问品类。未知价格/续航不能充当相对比较基准。`重新开始/清空条件/重新选` 支持重新建立购物要求。

### 可选模型语义层

`extraction.extract` 复用现有 `create_chat_llm`，通过 Pydantic 结构化输出只允许 keyword/category/brand/excludeBrand/scene/attribute 需求槽位。每项需要当前用户原文引文；不存在的引文、额外 stock/score/userId 等字段会拒绝，回退确定性解析。

预算和相对价格阈值仍由程序处理，模型不能提供商品、业务价格、库存、工具名或身份。模型只看到用户文本和此前需求，不接收登录 Token、订单信息或商品业务事实。已有规则条件不会被模型随意放宽，显式品牌排除不能被模型撤销。

`SHOPPING_REQUIREMENT_LLM_ENABLED` 默认 false。未修改真实配置，所有模型适配器测试均为 Mock；未经用户另行授权，不启用真实模型消耗。推荐展示使用确定性模板，避免自由生成性能、优惠或库存承诺。

## 四、MCP 与 Java 数据链路

1. `SEARCH_PRODUCTS` 保持原关键词/向量 RRF、Java 回源和既有召回机制。导购从中最多选取 8 个候选 ID，不信任召回时点的报价作为最终推荐依据。
2. 原 `GET_PRODUCT_DETAIL` 增加可选 `productIds`，单商品 `productId` 调用保持兼容；不能同时指定两种格式，批量上限 12。
3. 新 `ProductService.get_product_details` 只调用一次现有 Java `query_product_batch`，校验 ID 集合、数量及业务结果，保留 SKU、属性、价格、商品状态和库存状态；失败不回退旧搜索价格。
4. Java `ProductAgentQueryService.queryBatch` 继续复用原批量 SKU 查询和每 200 项一批的库存 RPC，不引入逐 SKU 网络查询。
5. 商品没有独立品牌字段，品牌判断使用真实 `propertyValues` 中品牌属性，不根据标题猜品牌。分类名通过 `SysCategoryMapper.selectAgentNames` 一次有界查询读取当前产品及父分类，新增只读字段 categoryName/parentCategoryName，不修改数据库结构。
6. MCP 原 schemaVersion=2 的 productQuery 保留上述字段，导购拒绝纯文本“成功”、无结构化结果、错误商品 ID、缺少详情及工具失败。

Java 搜索和普通商城购物链路没有重写。导购先召回、再做一次最新批量详情，库存可能因此读取两次，但不是每个 SKU 一次请求。

## 五、筛选、比较与评分

### SKU 一致性

`selection.select` 将预算、颜色/内存、库存放在**同一个 SKU**上判断。不会使用黑色款的最低价和白色款的库存拼成推荐。完整原 SKU 列表与 eligibleSkus 分开保留。

- 下架、删除、不存在及状态未知的商品不推荐。
- 预算不符合的 SKU 排除；有预算时价格未知的 SKU 不能声称符合预算。
- 已确认库存为 0 的 SKU 排除；查询失败、缺记录、null、无效响应均保持未知，允许作为明确标注“库存待确认”的条件候选，不作现货承诺。
- 只要存在满足条件且确认有货的 SKU，准确表述为“存在已核实有货规格”，不保证全部规格有货。
- 类目必须匹配真实分类字段；品牌、规格硬条件缺失时不视为满足。规格缺少 SKU 值且产品层有多个不一致值时，不自行挑选一个。
- 详情中的 SKU 价格与本次商品价格区间矛盾时拒绝推荐；搜索价格变化则以重新查询的详情为准。
- 续航只比较可解析的单一“小时/h”标称值；不把电池容量、范围或未知值转换成续航，也不保证不同产品测试条件一致。

未知价格仍为 null，页面显示未知；不转成 0 元。真实业务 0 元价格和未知是不同情况。

### 可解释评分

硬筛选后使用事实完整度/匹配分：

| 构成 | 分值 |
|---|---:|
| 存在满足要求且已核实有货的 SKU | 2 |
| 至少有一个满足要求的已知 SKU 价格 | 1 |
| 已匹配的必需规格数量 | 每项 1 |
| 明确业务属性支持的请求场景数量 | 每项 1 |

分数是透明约定，不是质量、销量、测评或用户评价评分。相同条件下按分数、价格、商品 ID 稳定排序；用户明确要求便宜时优先按实际符合条件的最低 SKU 价格排序。最终最多推荐 3 个商品，不为了凑数量造商品。

优势只描述可验证事实，例如存在有货规格；不足列出未知价格、库存待确认、场景依据不足和属性缺失，不虚构缺陷或性能。场景适用性只基于真实显式属性，没有数据时明确标注未知/待确认。matchStatus 区分 VERIFIED 和 CONDITIONAL。

比较结果保留最新全商品价格区间、状态、原 SKU、属性、观察时间；与推荐所选规格报价分开标识。比较“刚才商品”时重新批量读取详情，不复用 Redis 中过时库存。

## 六、多轮上下文、结果与存储

独立 Redis 前缀：`mall:agent:shopping:<当前用户>`。上下文保存条件、上次推荐 ID、上次已知价格及标称续航基线，TTL 为 1 小时，不保存登录 Token，不写入售后会话记忆。

同一用户购物请求通过 NX 锁串行化；保存使用 Lua 同时检查锁所有者并写入上下文/本次结果，锁失效的旧请求不能覆盖新上下文。只按锁所有者释放该导购锁，不清空其他 Redis 数据。取消和业务查询失败不会生成虚假商品结论。

结构化报告包含：

```text
schemaVersion / agentType=shopping / status / requirementSource
requirements / clarification / toolsCalled / queryTime / executionAllowed=false
recommendations[]:
  productId / productName / cover / productStatus / categoryName
  price: min / max / complete
  attributes / skus / eligibleSkus / availability / matchStatus
  reasons / advantages / limitations / sceneMatches
  score: total / components / meaning
  queryTime / batteryHours / source
comparison[] / excluded[]
```

状态包括 SUCCESS、NEEDS_CLARIFICATION、NO_RESULTS、NO_MATCHING_SKU、TOOL_ERROR、CANCELLED；购物上下文不可用或占用时单独返回 CONTEXT_UNAVAILABLE/SHOPPING_BUSY，不把故障伪装成无商品。

原 `sql/09_agent.sql` 的 biz_data 是 varchar(2000)，本轮不擅自迁移该表：

- 消息正文/商品卡片保存可读推荐，bizData 只存小型导购摘要、messageId、商品 ID 和禁止执行标记。
- 完整属性/SKU 报告保存为本用户 Redis 结果，单报告最多 256 KiB，TTL 1 小时。
- 新增登录接口 `POST /api/agent/shopping/result`，表单 messageId，只按当前用户键查询；过期或不存在返回业务 404，不从其他用户取结果。
- 聊天正文展示必要 SKU 摘要，更多规格可查看商品详情；完整结构化数据可通过上述接口查询。

## 七、前端入口与兼容性

原 `/api/agent/sendMessage` 增加可选 agentMode=shopping/support，默认 support；后端拒绝未知模式，当前用户仍来自登录依赖，不采信表单 userId。

`AgentSendPanel.vue` 使用同一个聊天界面增加模式选择，回答期间禁止切换，导购模式展示购物示例。`AgentEngine` 仅按该显式模式进入独立导购 runner，原售后图保持原入口。

继续复用原消息列表、商品搜索消息格式及商品卡片，无新聊天微服务。导购不激活或清理售后商品咨询上下文，自己的偏好和售后记忆相互隔离。

## 八、修改文件清单

以下路径均相对于项目根目录。

| 文件 | 内容 |
|---|---|
| `Simlect-backend/Simlect-agent/app/shopping/__init__.py` | 新增独立模块 |
| 同目录 `requirements.py` | 预算、品类、品牌、规格、场景及多轮条件合并 |
| 同目录 `extraction.py` | 可选模型结构化提取、原文依据和回退 |
| 同目录 `selection.py` | 同 SKU 硬筛选、未知值保持、比较和透明评分 |
| 同目录 `graph.py` | 独立 LangGraph、必要工具强制调用、失败与取消 |
| 同目录 `store.py` | 用户隔离上下文/结果、过期锁写保护 |
| 同目录 `runner.py` | 原聊天适配、结果保存、确定性说明和商品卡片 |
| `Simlect-backend/Simlect-agent/tests/test_shopping_agent.py` | 新增 52 项测试 |
| `Simlect-backend/Simlect-agent/app/config/settings.py` | 默认关闭真实购物需求模型的开关 |
| `Simlect-backend/Simlect-agent/app/services/agent_engine.py` | 显式选择独立导购/原售后图 |
| `Simlect-backend/Simlect-agent/app/services/agent_service.py` | 模式校验、保留原限流/登录消息流程、隔离咨询态 |
| `Simlect-backend/Simlect-agent/app/api/routes/agent.py` | 模式参数及本人结果接口 |
| `Simlect-backend/Simlect-agent/app/services/product_service.py` | 有界批量详情和响应验证 |
| `Simlect-backend/Simlect-agent/app/services/mcp_tools_service.py` | 批量详情工具适配 |
| `Simlect-backend/Simlect-agent/app/services/mcp_tool_router.py` | GET_PRODUCT_DETAIL 批量参数透传 |
| `Simlect-backend/Simlect-agent/app/mcp_server/server.py` | 原工具兼容的 productIds 可选参数 |
| `Simlect-backend/Simlect-product/app/src/main/java/com/simlect/mappers/SysCategoryMapper.java` | 有界批量分类名称查询 |
| `Simlect-backend/Simlect-product/app/src/main/java/com/simlect/biz/ProductAgentQueryService.java` | 在原批量结果中补充真实分类名称 |
| `Simlect-backend/Simlect-product/app/src/test/java/com/simlect/biz/ProductAgentQueryServiceTest.java` | 新增一次分类查询/一次库存批量调用断言 |
| `Simlect-front/Simlect-web/src/api/modules.ts` | 模式参数与导购结果接口 |
| `Simlect-front/Simlect-web/src/views/agent/AgentSendPanel.vue` | 同一聊天界面模式切换和购物提示 |
| `docs/agent-development/20-智能导购Agent实施报告.md` | 本报告 |

修改前的相关已有文件保存在 `.cache/shopping-agent-20261102/before/`。未重置、清理或提交 Git，没有修改数据库结构、真实配置和原退款执行/订单归属/案件状态机/RAG 实现。

## 九、自动化测试

| 范围 | 通过 | 失败/错误 | 跳过 |
|---|---:|---:|---:|
| Python 新增导购测试 | 52 | 0 | 0 |
| Python 既有回归 | 344 | 0 | 0 |
| **Python 合计** | **396** | **0** | **0** |
| Java Common | 229 | 0 | 0 |
| Java Gateway | 41 | 0 | 0 |
| Java Search | 94 | 0 | 0 |
| Java Product app | 117 | 0 | 0 |
| Java Stock app | 39 | 0 | 0 |
| Java Order app | 390 | 0 | 0 |
| Java Pay app | 65 | 0 | 0 |
| **Java 所选模块合计** | **975** | **0** | **0** |

前端 `npm run build` 最终通过，包含 `vue-tsc -b`、Vite 和 PWA 生产构建，没有安装/升级 npm 依赖。package.json 没有单元测试或 ESLint 脚本，未虚构此类结果。

测试覆盖用户要求的 20 类场景：正常推荐、预算、实际品类、场景、品牌、空召回、比较、多 SKU、未知价格、零库存、库存失败、下架、属性缺失、多轮修改/追加、搜索与详情不一致、MCP 失败、缺少必要工具拒绝、理由与真实属性一致、不下单支付；另覆盖同一 SKU 价格/颜色交叉误用、null 库存、严格预算边界、续航比较、真实 MCP wire 字段传递、用户隔离、锁失效、取消、HTTP 模式与身份及受约束模型 Mock。

Python 使用独立 3.12 测试环境、虚拟密钥、隔离工作目录和外网阻断钩子；LLM/Embedding、商品、库存与 Redis 均 Mock。Java 离线执行，测试 JVM 使用原 NoNetworkSecurityManager；原第 19 阶段案件测试仍仅使用内存 H2。没有连接开发数据库写业务数据。

中间补测曾出现 2 个失败：通用裸关键词回退覆盖了“想买咖啡”提取词，以及新 HTTP 测试漏导入夹具类型；均修正后全量重跑。前端中间构建遇到临时目录权限及新增样式位于 Sass @use 之前的问题，已分别使用项目内 E 盘临时目录及调整本轮样式顺序解决，没有关闭 PWA 或绕过类型检查。

Ruff：新增购物模块及新测试全规则通过；修改旧 Python 文件按 E9/F63/F7/F82 检查通过，没有修复全项目遗留问题。既有 MCP 客户端弃用和 pytest-asyncio fixture 提示保留，不宣称零警告。

证据位于 `.cache/shopping-agent-20261102/results/`：`python-final.log/xml`、`java-final.log`、`java-summary.json`、`frontend-final.log`；Java 用例明细为各模块 target/surefire-reports。统计只包含本轮实际 reactor 模块，没有合入旧 Admin/User 报告。

## 十、安全边界与未完成事项

1. 导购强制使用当前登录上下文，只允许固定 SEARCH_PRODUCTS/GET_PRODUCT_DETAIL 读取；模型输出不能改变 userId、工具白名单、Agent 模式或执行开关。
2. 所有价格、属性、SKU 和库存来自业务工具；失败不复用旧报价，不提前流式输出未经验证的业务事实。
3. executionAllowed 始终 false，不生成下单/支付/退款 pending action，不调用原 confirmAction 执行链。
4. 本轮未做真实服务加载、浏览器交互和跨服务端到端验收。后续需受控加载 Product、MCP、Agent 及前端；不需要数据库迁移。真实模型/Embedding 请求须另行授权。
5. 默认规则解析覆盖明确条件与常见词典，不能宣称理解全部自然语言、隐含条件和未知品类关系；可选模型语义层真实质量尚未验证。复杂条件应继续扩展评测与澄清能力，不能用虚构属性补足。
6. 价格筛选在有界召回后执行，未声称穷尽整个商品库或找到全网最低价。可用属性受原商品库实际维护质量限制。
7. 当前每用户一个购物上下文，TTL 1 小时；没有多窗口会话隔离或长期完整报告归档。锁存活期 120 秒，超时旧请求安全拒绝写入，不保证自动恢复长任务。
8. 完整结构化报告过期后不能仅从小型 bizData 还原全部 SKU；历史聊天仍保留已展示摘要。长期留存如有需要，需单独审核存储设计，不能擅自改表。
9. 续航是标称属性比较，不是统一测试条件的实测结论；没有数据时明确未知。没有引入评测分、销量推断、优惠价格或性能预测。
10. 暂无 Supervisor、多智能体自动路由、自动购买或财务操作，本轮到独立导购交付为止。

完成后暂停，等待审核；不提交 Git、不自动部署或开始下一阶段。
