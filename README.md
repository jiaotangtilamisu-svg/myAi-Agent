# Simlect-AI-Mall：智能导购、售后与多智能体商城

> 项目上下文快照：2026-11-07。本文件面向开发者及无法直接访问仓库的 AI，独立说明当前本地项目的功能、实现边界与运行方法。它描述的是经过多轮增量开发的本地版本，不等同于原始仓库或线上站点，也不代表系统已达到生产上线标准。

原始仓库：<https://github.com/Audreator/Simlect-AI-Mall>。参考体验站：<https://www.simlect.com/>。线上站点的数据、配置与本地运行状态不能相互替代。

## 1. 项目是什么

这是一个 B2C 单商家商城，包含 Vue 商城、Vue 管理后台、Java 领域微服务，以及 Python 智能客服。智能客服由 Supervisor 统一助手、独立智能导购工作流、售后查询及诊断工作流组成，通过 MCP 调用 Java 业务接口，结合商品库存事实、本人订单和政策 RAG 证据回答问题。

核心原则：**模型理解需求和组织语言，Java 业务系统提供商品、订单、权限和状态事实；提案、申请、审核、履约、退款结果分别记录，不能混为一次自动执行。**

本地目录：`E:\Simlect-AI-Mall-main\Simlect-AI-Mall-main`。这不是可直接迁移至其他电脑的通用路径，现有 Windows 脚本包含本机 E 盘工具路径。

### 必须先知道的边界

- 商品目录存在公开商品资料、参考站资料、本地演示及测试数据。可查询的数据库记录不自动等于真实商业在售商品。
- 部分 SKU、人民币售价及库存由本地生成或配置，不能称为来源商家的真实售价或实时仓储库存。来源与授权应单独保留，即使消费者界面不直接展示内部字段。
- 支持真实业务接口和数据库持久化，但本机模拟退款不产生真实资金，不改写原支付渠道状态。
- Agent 真实退款执行受到服务端隔离；管理员审核通过也不等于已退款。真实渠道接入与资金操作需要另外配置、授权和验收。
- 政策法规不是商城额外承诺。没有政策、事实或适用条件时必须表达不确定，不能编造期限与退款资格。
- 不应把源码存在、Mock 测试通过、隔离浏览器通过、真实模型通过、生产可用混为一谈。

## 项目功能亮点

以下是当前源码中已有的能力和设计，不代表每项均已完成生产压测或真实第三方验收。业务规则及剩余限制见后文。

| 亮点 | 实际实现与价值 | 主要源码位置 |
|---|---|---|
| 独立智能导购 | 自然语言预算/品类解析、硬条件与软偏好、2～3款比较、多轮条件调整；业务工具回源校验，避免凭空报价 | Agent `app/shopping/`、`services/product_service.py` |
| 售后诊断与案件闭环 | 本人订单/物流/政策核实、诊断建议、方案版本、用户确认、人工审批、履约记录和进度查询 | Agent `app/graph/`；Order `AftersalesCaseService` |
| Supervisor多Agent调度 | 区分单任务和复合任务，按需调用独立工作流，校验结果并保留部分成功及证据 | Agent `app/supervisor/` |
| 混合检索与可信商品事实 | Elasticsearch关键词/向量召回与RRF融合，再用Java核实同SKU价格库存；未知、零值、服务失败分开表达 | Agent `app/rag/`；Product、Stock、Search |
| 有审核边界的政策RAG | 文档解析/切分、来源版本、有效期、发布审核、可逆启停及审计，法规与商城承诺分开 | Search知识管理；Admin `PolicyCenter.vue` |
| 异步对话与完整证据 | 消息受理与后台执行分离，WS推送、消息ID恢复、结构化JSON持久化、简洁回答与完整证据展开 | Agent `api/`、`services/`；商城 `components/agent/` |
| 秒杀券多层并发保护 | Redis Lua原子库存预占与用户防重、数据库行锁和条件扣减兜底、已有待支付订单复用、失败补偿及限流 | Common `RedisComponent`；Order `prepareCouponRush`；Coupon库存服务 |
| 优惠券使用防重 | 同时按用户、券ID和未使用状态条件更新，避免同一用户券并发锁给多个订单 | Coupon `CouponInternalService.validateAndLock` |
| SKU库存与订单状态保护 | 库存条件更新/操作号幂等、订单状态流转、超时关单及库存回补相关业务 | Stock服务；Order服务及MQ监听器 |
| 支付与退款边界 | 支付回调、交易记录及原渠道退款相关代码保留；Agent退款隔离、人工审核和仅隔离环境模拟验收 | Pay服务；Order；Agent `action_execute_service.py` |
| 签到与会员营销 | 月度签到位图、补签、连续/累计天数、成长等级、升级礼券和连续签到奖励 | User `SignServiceImpl`；会员服务；Coupon签到奖励 |
| 事务消息与补偿治理 | 本地Outbox、异步投递、死信处理、重试/补偿及日志查询，减少业务已提交但事件丢失的问题 | Common Outbox；各域RabbitMQ组件；Admin补偿日志 |
| 运营与内容治理 | 评价/追评、商家回复、举报处理、图片审核/人工复核、临时禁用管理及敏感词 | Order、User、Admin对应Controller与页面 |
| 多终端操作入口 | 商城PC/移动适配，Admin移动工作台、商品订单用户及运营页面，已有PWA构建能力 | 两个前端的router、layouts、mobile及Vite配置 |
| 数据来源与ETL | 小样本导入、dry-run、来源映射、批次幂等、历史交易隔离，避免公开资料冒充当前真实业务 | `tools/data_governance/`；来源映射表及Admin公开资料页面 |
| 可重复质量工程 | 单元/契约/故障注入/属性及受控变异测试、独立SQL规则、专用Chromium页面闭环与视频证据 | `tools/quality_engineering/`、`e2e/` |

### 阅读导航

- 第2节：技术架构与系统边界。
- 第3节：业务功能；其中3.5专述优惠券与并发，3.6～3.9补充会员、交易、运营和基础设施。
- 第4～8节：聊天协议、案件状态机、RAG、数据与安全。
- 第9～12节：源码定位、运行方式、测试口径及已知限制。
- 附录A：按当前Java Controller声明生成的完整接口定位清单，补充正文未逐一展开的操作。

## 2. 技术架构与职责

```text
商城 Vue/TS :6001                 Admin Vue/JS :6002/admin/
              \                 /
              Vite API代理 / Gateway :8080
                 │
                 ├─ /api/agent/** → Python FastAPI :7050
                 │    ├─ 鉴权、消息保存、后台任务、WebSocket、恢复查询
                 │    ├─ Supervisor：识别→调度→校验→汇总
                 │    ├─ Shopping：需求→搜索→详情→筛选→推荐/比较
                 │    └─ Aftersales：订单/物流→政策→诊断/建议
                 │              │
                 │              └─ MCP :7060/mcp → Java内部业务API
                 └─ Java微服务：User/Product/Stock/Order/Pay/Cart/Coupon/Search/Admin
                        ├─ MySQL：业务、消息、案件、版本和审计
                        ├─ Redis：会话/缓存/限流/确认提案/幂等相关状态
                        ├─ Elasticsearch：商品关键词、向量与知识检索
                        └─ RabbitMQ：业务异步事件、索引/向量处理等

DeepSeek：模型调用；DashScope text-embedding-v4：Embedding
Nacos：Java服务注册发现；Sentinel：流量治理；Seata：已有事务组件，本机可关闭
```

注意：当前 Gateway 将 `/api/agent/**` 直接路由至 Python。项目仍有 Java 消息相关代码，不应据此推断所有聊天请求必须先由 Java Agent Controller 同步调用 Python。RabbitMQ 承担已有业务异步职责，也不能据其存在认定每条聊天任务都走 MQ。

| 技术 | 当前项目配置/用途 |
|---|---|
| Java | JDK17，Spring Boot 3.5.4、Spring Cloud 2025.0.0、Spring Cloud Alibaba 2025.0.0.0；MyBatis、OpenFeign |
| Python | 本机使用 Python3.12；FastAPI、Uvicorn、LangGraph/LangChain、FastMCP、httpx、异步数据库客户端 |
| 前端 | Vue3、Vite、Pinia、Vue Router、Element Plus；商城 TypeScript，管理端主要 JavaScript |
| 数据与中间件 | 项目本地方案为 MySQL8.3、Redis7、RabbitMQ3.13、Elasticsearch9.2.1/IK、Nacos2.4.3 |
| AI服务 | 已有 DeepSeek、DashScope 配置；模型名、超时及密钥以环境和调用工厂为准，不在 README 放密钥 |
| 测试 | pytest、Java JUnit/Mockito/H2、Node测试、vue-tsc、生产构建、Playwright专用Chromium、独立SQL断言 |

依赖准确版本以各模块 `pom.xml`、Python依赖清单及前端 `package-lock.json` 为准。

## 3. 完整功能地图

### 3.1 商城与管理后台

| 领域 | 用户端能力 | 管理及业务能力 |
|---|---|---|
| 账户 | 图形验证码、登录、注册相关流程、个人资料、地址 | 管理员认证、用户管理、敏感操作二次确认；邮件能力需实际邮件配置 |
| 商品 | 首页轮播与分类、关键词搜索、价格筛选、详情、规格选择、图片、评价 | 分类、属性、商品新增编辑、上下架、SKU、公开商品资料导入/适配 |
| 库存 | SKU可售情况、零库存和未知库存区分 | 库存查询、预占/释放及扣减回补相关业务；批量SKU查询避免逐SKU远程请求 |
| 购物车 | 登录用户购物车、数量与规格、持久化 | 服务端用户隔离；购买条件仍由业务端再次校验 |
| 订单 | 本人列表、明细、物流、收货、评价、售后入口及进度 | 订单状态管理、物流记录、售后案件；用户不能查询他人订单/明细 |
| 支付 | 订单支付入口及本地联调能力 | 既有支付宝渠道、回调及幂等逻辑；真实配置及资金验收不由本地模拟替代 |
| 营销 | 优惠券、领券、签到、会员成长等已有入口 | 券与营销管理、签到汇总、通知等原有能力保留 |
| 个人中心 | 收藏、足迹、通知、订单、账户等 | 用户和运营管理页面 |
| 智能客服 | 售后/导购/统一助手三模式、消息记录、商品卡、完整证据、案件操作 | 消息查询、政策管理、案件审核与履约追踪 |

页面可见不代表所有外部依赖已接通。邮件、承运商实况、真实支付退款、ERP/WMS等要单独验收。

### 3.2 智能导购

独立入口：`app/shopping/runner.py`；LangGraph：`app/shopping/graph.py`。

```text
understand → search → details → select → compose → END
     └─ 条件不足/无法比较 → 澄清或明确缺数据
```

- 解析品类、预算上下限/区间、品牌、属性、用途、推荐数量；区分硬条件与软偏好。
- 商品召回复用关键词、向量与 RRF 排序融合；实际是否执行向量分支取决于配置、向量覆盖与服务状态。
- 使用 `SEARCH_PRODUCTS`、`GET_PRODUCT_DETAIL` 获取候选，再回源 Java 校验商品状态、SKU、价格和批量库存。
- 预算必须基于同一个符合要求的 SKU，不能借用其他规格低价；未知价格不能作为符合预算的商品。
- 区分真实库存0、未查询到记录、库存服务不可用；未知不得自动补成0。
- 类别匹配避免把“手机互联行车记录仪”当手机、把“耳机图案手机壳”当耳机。
- 支持2～3款比较、按上一轮序号指定比较对象、多轮预算品牌条件调整；不足请求数量时说明实际数量，不编造凑数。
- 推荐保留价格、属性、SKU、库存状态、来源与查询时间；缺失属性明确未知。
- 数据模式包括 `REAL`、`DEMO`、`LOCAL_STORE`。REAL严格模式不能把未核实或演示数据当真实商品；LOCAL_STORE用于本机已配置目录，不自动赋予商业真实性。
- 不自动下单、支付或修改库存。

主要实现：`shopping/requirements.py`、`shopping/selection.py`、`services/product_service.py`、`services/product_facts.py`、`rag/rrf.py`，Java `ProductAgentInternalController` 与库存接口。

### 3.3 智能售后

主要工作流：`app/graph/runner.py`、`builder.py`、`nodes.py`，复用 `domain/aftersales_intent.py`、订单/物流工具及RAG。

- 本人订单列表、订单详情、物流查询、退款/案件处理进度。
- 识别退货、退款、换货、物流异常、未发货、支付异常、退款异常、质量问题和政策咨询。
- 查询政策与实际订单事实，生成异常类型、理由、证据不足项和下一步；不把“未发现异常”等同于“没有售后权利”。
- 无订单号时可追问或列出本人订单，不擅自挑选；明确指代可恢复上下文，但仍要重新校验归属。
- 售后诊断与方案可以携带 `caseType`、`orderId`、`diagnosis`、`orderFacts`、`logisticsFacts`、`policyEvidence`、`evidenceSources`、`confidence`、`recommendedActions`、`approvalRequired`、`executionAllowed` 等结构化字段。
- 纯进度查询直接读取实际案件履约状态；“一直没到账、失败、异常”等保留异常诊断语义。
- 支持方案草稿、填写和修改真实原因及材料、用户确认、提交人工审核、查询案件、物流登记与历史追踪。
- 资格判断是基于事实和规则的核实/人工审核要求，尚不能把自由文本法规片段自动转成法律裁决或无条件退款许可。

### 3.4 Supervisor统一助手

入口：`app/supervisor/runner.py`；图：`identify → execute → validate → summarize`。

- 售后任务调用售后工作流，购买/推荐/比较调用导购工作流；模糊任务澄清。
- 复合任务分别调用两个专业Agent，保留各自证据及状态；不是无条件同时调用两个Agent。
- 当前图中任务按列表**顺序执行**，并有单任务超时、取消和结果契约校验；不要描述成已实现任意并行多Agent系统。
- 一个Agent失败时保留另一个的成功事实，不把部分成功包装为全部成功。
- 传递可信用户身份、只读委派和经过校验的专业结果；不生成或覆盖用户ID，不绕过审批。
- 汇总保留商品事实、SKU及政策来源，面向用户的简洁回答与可展开的完整证据分离。
- 当前记忆主要按用户组织。同用户多独立 `conversationId` 的完整隔离仍属已记录缺口，不能宣称已经全面支持。

### 3.5 优惠券、秒杀与并发控制

**业务功能：** 优惠券列表/广场和详情、满减券/折扣券/无门槛券、有效期及使用门槛、我的优惠券、秒杀券抢购预占、待支付券订单和支付入口、券使用/过期状态、临期提醒；后台券新增编辑、上下架等管理与缓存更新。会员升级礼券及连续签到发券复用券域。

主要入口为Coupon `DiscountCouponController`、`DiscountCouponServiceImpl`；抢券订单由Order `OrderInfoServiceImpl.prepareCouponRush`、`postCouponRushOrder` 编排。

```text
用户抢券 → 登录/活动条件及限流
         → Redis Lua：库存判断 + 原子扣减 + 用户预占
         → Coupon数据库行锁/条件扣减
         → Order创建待支付订单 + 超时关单消息
         → 支付处理 / 超时关闭和预占释放
```

| 并发问题 | 已有实现 | 边界 |
|---|---|---|
| 多人同时抢同一批券 | `RedisComponent.rushingCoupon` 的Lua原子执行库存判断、扣减、用户集合和预占Hash写入 | Lua原子性限于Redis执行范围，不是Redis与MySQL跨服务事务 |
| 用户重复点击/请求重发 | 有效用户预占防重复；找到已建待支付订单时返回同一订单 | 不应把请求被拒绝或复用订单描述为新领取成功 |
| 数据库库存超卖 | `selectByCouponIdForUpdate` 行锁；扣减SQL附带剩余库存条件 | 库存修改和同步入口也需遵守一致性约束 |
| 一张用户券同时用于多单 | `validateAndLock` 按userId、userCouponId、NOUSE状态更新，必须影响1行才能锁定成功 | 后续使用/释放仍需合法状态转换，不能直接无条件改状态 |
| 签到重复发奖 | 奖励事务入口、幂等记录、数据库唯一约束 | 签到事件重投不能重复创建奖励 |
| 建单失败、超时未支付 | Redis预占释放、库存回补、消息关单与同步逻辑 | 网络超时/进程崩溃后的跨服务补偿仍需故障验证与对账 |
| 瞬时请求和缓存击穿 | 抢券限流；券列表/详情缓存与互斥重建锁，释放锁校验持有者 | 限流不是业务幂等，缓存也不是最终库存权威 |

关键源码：Common `component/RedisComponent.java`、`CouponRushRateLimitService.java`；Coupon `component/CouponRushStockService.java`、`DiscountCouponCacheComponent.java`、`biz/CouponInternalService.java`；Order `biz/impl/OrderInfoServiceImpl.java`。

相关测试包括 `CouponRushStockServiceTest`、`CouponInternalServiceTest`、`DiscountCouponServiceImplTest`、`CouponRushRateLimitServiceTest`。它们的存在不代表已经进行生产规模压测。仍需专项验证Redis故障、Feign超时、重复补偿、预占过期，以及管理员编辑券库存/重新预热与用户抢券同时发生的情况。**已有并发保护，不宣称所有一致性风险已清零。**

### 3.6 用户、签到、会员与互动功能

- 账户：自动登录校验、图形验证码、登录/退出、注册、邮箱验证码、忘记密码、个人信息/密码修改；另有滑动验证码接口。邮件和其他外部校验需配置实际服务。
- 地址：用户收货地址维护与管理端地址查询；位置相关接口由LocationController提供。
- 签到：按月查询日历、当日签到、补签、累计及连续天数；MySQL月位图与汇总为持久化依据，Redis用于缓存，不把缓存当唯一事实。
- 会员：会员档案/中心、成长等级与徽章、等级奖励领取；Admin可配置升级礼券与连续签到奖励。
- 收藏与足迹：商品收藏、浏览记录及历史查询，浏览相关异步处理；不因新增Agent功能删除传统入口。
- 通知：站内通知列表、未读数量、已读等操作；优惠券、订单/物流及相关业务事件可触发通知，死信重投和补偿机制属于后台可靠性能力。
- 评价：商品评价、评价统计、本人评价、追评及删除等既有接口；管理员评价管理/商家回复、评价举报及审核。
- 文件与图片：用户/管理端上传和资源访问；图片审核、记录查询、人工复核、临时封禁信息与解除管理。审核服务是否可用取决于配置，不等于所有上传都已完成真实第三方审核验收。

### 3.7 商品、购物车、库存与交易功能补充

- 商品域：多级分类、分类属性/属性值、商品新增与编辑、SKU组合与规格价格、封面及详情、上下架、首页推荐；空图占位、未知价格与库存保留空值；公开资料批次预览、导入与本地目录适配。
- 搜索域：普通商城关键词检索、筛选排序、热词/热搜管理、商品关键词索引和向量相关同步；搜索结果回源核实，召回相关性与真实库存是不同阶段。
- 购物车：本人购物车读取、增加、调整、删除等现有操作，订单创建仍需重新校验商品/SKU与库存，购物车展示不是预占库存的证明。
- 库存：内部单SKU/批量查询及库存扣减回补相关接口；使用库存操作记录支持幂等。Stock对外健康Controller不是全部库存业务入口。
- 订单：创建/提交订单、本人列表与详情、支付关联、取消/关闭、确认收货、订单删除等业务；物流主记录与轨迹管理、评价及售后入口。具体可操作状态以业务端校验为准。
- 定时/延迟业务：已有支付订单任务、RabbitMQ超时/死信处理及自动收货相关逻辑。不能把定时任务存在等同于业务事件已在每个部署中启用。
- 支付：支付信息创建、支付宝回调、交易记录查询、本地模拟支付联调入口和退款相关基础能力；本地模拟和真实资金渠道必须分开配置、授权及验收。

### 3.8 Admin运营后台功能补充

除商品、订单、售后案件和政策中心外，当前管理端还保留：

- 首页工作台与数据统计、统计明细、运营工具。
- 用户列表、用户信息、收货地址管理、会员及签到奖励配置。
- 分类、商品属性、SKU与商品管理、公开资料批次及参考目录适配入口。
- 订单、发货信息、物流记录、评价、举报及售后案件人工处理。
- 优惠券管理、热搜词管理。
- FAQ/RAG资料、问题维护、政策版本审核与启停、向量同步失败记录及处理入口。
- AI提示词管理、客服消息记录查询、敏感词管理及同步。
- 图片审核与人工处理、封禁相关管理。
- MQ补偿日志与相关处理入口；运营工具内有统计、商品数据/RAG处理、延迟队列等维护操作，这些可能写数据或触发API，不能在只读验收中随意点击。
- 移动工作台以及移动商品、订单、用户、评价、举报、优惠券、热搜、统计、图片审核、客服记录、MQ日志、政策等页面；并非每个PC页面都有完全相同的移动交互。

菜单存在、API存在、业务实现和运行验收是不同层次；下方附录提供源码定位，不把未检查的每个分支统一标为“已验收”。

### 3.9 工程基础设施与故障治理

- Gateway提供Java服务路由和Agent HTTP/WS入口、登录边界及流量控制；Nacos注册发现、OpenFeign内部调用，内部令牌与业务用户授权分别校验。
- MySQL领域数据、Redis缓存与限流/确认状态、Elasticsearch商品/知识索引、RabbitMQ业务事件各司其职。
- 已有本地消息Outbox、派发任务、事务消息发送器、死信监听、补偿记录与自动重放任务；业务提交和事件投递仍需通过幂等消费及补偿实现一致性，不能宣称跨服务绝对原子。
- 券缓存互斥重建、商品布隆过滤器预热等缓存保护已有实现；缓存不能覆盖数据库权威事实。
- FastAPI健康/指标入口、Java Actuator、工具调用关联日志、消息持久化错误分类、模型/工具超时与降级策略。
- Windows独立进程启动、日志/退出信息、选择性加载新代码及进程身份检查；项目专用浏览器、隔离夹具和可追踪验收记录。
- 多轮记忆、消息恢复、数据契约、权限、价格/SKU/库存、政策证据及售后状态机已有专项与回归测试；属性测试、故障注入和受控源码变异属于已有质量工具，不意味着全项目覆盖率100%。

### 3.10 MCP工具及商品咨询上下文

现有FastMCP注册包含以下业务工具，源码入口为 `app/mcp_server/server.py`，实际参数、鉴权与返回契约由工具层校验：

| 工具 | 能力与限制 |
|---|---|
| `SEARCH_PRODUCTS` | 搜索商品，传递候选商品、SKU价格/库存及状态，不将普通文本等同于业务查询成功 |
| `GET_PRODUCT_DETAIL` | 商品详情与结构化规格事实；缺失字段保留未知 |
| `QUERY_ORDERS` | 本人订单相关查询，不能信任模型提供的任意用户ID |
| `QUERY_LOGISTICS` | 本人订单物流查询；人工轨迹与承运商实况须区分 |
| `QUERY_COMMENT` | 查询订单评价相关信息，遵守订单归属 |
| `QUERY_USER_COUPONS` | 查询当前用户优惠券及相关状态 |
| `PROPOSE_CONFIRM_RECEIPT` | 生成确认收货提案，不等于已经收货或执行成功 |
| `PROPOSE_REFUND` | 生成退款建议/提案；不能绕过Agent服务端退款执行隔离 |
| `PROPOSE_PRODUCT_REVIEW` | 生成商品评价提案，后续确认与业务校验独立处理 |
| `PROPOSE_RECOMMENT` | 生成追评提案，保留归属与确认边界 |

客服还支持从商品页进入咨询，传递 `consultProductId`，读取、暂停或清理当前商品咨询上下文；这些入口与购物需求多轮记忆协作，不是把所有历史消息一律当成当前商品。传统提案机制、售后案件确认与管理员履约是不同流程，不能认为所有PROPOSE工具均已获准直接执行。

## 4. 聊天异步链路与协议

1. 前端提交 `POST /api/agent/sendMessage` 表单，字段包括 `message`、`agentMode`，以及可选商品咨询信息。
2. Python `require_login` 取得经过验证的身份，限流并保存用户消息，调度后台执行。
3. HTTP立即返回 `messageId` 等受理信息；**受理成功不等于AI任务成功**。
4. `services/agent_engine.py` 分派 `support`、`shopping`、`supervisor`；各工作流执行必要查询、模型或确定性处理。
5. WebSocket推送执行状态与回答；结果通过消息服务保存文本及完整业务证据。
6. 前端按 `messageId` 关联展示，通过历史和单条恢复接口在刷新、断连后恢复，而不是依赖未完成的内存流。

| 对外路径（Gateway后） | 用途 |
|---|---|
| `POST /api/agent/sendMessage` | 提交消息，表单；agentMode为support/shopping/supervisor |
| `POST /api/agent/loadHistoryMessage` | 当前用户历史消息 |
| `POST /api/agent/getMessage` | 单消息结果恢复，校验归属 |
| `POST /api/agent/cancelMessage` | 取消任务 |
| `POST /api/agent/shopping/result`、`/supervisor/result` | 专业/统一结果查询 |
| `POST /api/agent/aftersales/cases` | 从已核实的诊断消息生成案件草稿，不是退款执行 |
| `POST /api/agent/confirmAction`、`/cancelAction` | 现有待确认提案机制，退款仍受服务端隔离 |
| `POST /api/order/aftersalesCase/list`、`/detail` | 本人案件列表及详情；当前兼容表单和JSON，列表可按orderId过滤 |

WebSocket后端在 `app/main.py`、`api/websocket.py`；准确外部升级路径、Origin与代理以Gateway和前端配置为准。接口业务错误可能使用HTTP200加业务码，必须同时检查业务状态和最终结果。

### 数据契约与错误表达

- 商品查询使用结构化结果（当前导购校验 `schemaVersion=2`），包含查询状态、商品与SKU事实；不要假定MCP文本传输成功就代表业务成功。
- 文本、结构化证据与消息ID必须一致保存；模型失败和数据库保存失败是不同错误，不能统一显示“服务不可用”或虚报成功。
- `agent_message.biz_data` 保存完整JSON证据。初始DDL仍能看到 `VARCHAR(2000)`，升级SQL已将其拓宽为 **MEDIUMTEXT**；部署不能只执行旧初始DDL。
- 模型超时、503、断流、非法响应必须保留错误类型和可验证的降级结果；RAG成功而模型失败时可展示有来源的证据，不能编造模型答案。
- 商品价格库存等关键事实必须先查询后展示；普通闲聊的流式机制保留。

## 5. 售后案件、履约与退款状态机

Java权威实现：`Simlect-order/app/src/main/java/com/simlect/biz/AftersalesCaseService.java`；查询Mapper：`AftersalesCaseMapper.java`。用户Controller位于 `controller/aftersales/`。

```text
诊断消息 → 方案草稿 AWAITING_USER
  → 本人确认 → 高风险 ADMIN_REVIEW → 管理员批准 → MANUAL_PENDING
              低风险按后端规则进入人工任务 ───────────┘
  → 人工领取 IN_PROGRESS → 处理成功 RESOLVED → ARCHIVED
                       └→ PROCESSING_FAILED → 重试任务
审核驳回 REJECTED → 补充/修订方案 → 再次本人确认及审核
允许的阶段可取消 CANCELLED；非法流转由服务端拒绝
```

高风险方案不能被模型的低风险标记绕过。通过版本号/条件更新与requestId幂等保护并发和重复操作，方案版本与操作时间线持久化。

退款履约与案件状态独立：

```text
退货退款：登记运单 → 实际收到与验收通过 → 准备模拟单
仅退款：人工核实相应条件 ─────────────────→ 准备模拟单
NOT_EXECUTED → PENDING → PROCESSING → SUCCEEDED / FAILED / UNKNOWN
```

- 退款履约类型仅支持 `refund`、`return_refund`；人工换货是另外的处理语义，不能塞进退款执行类型。
- `PENDING`只是待执行；登记物流不等于验收，批准案件也不等于资金退款。
- `UNKNOWN`必须人工核实，不允许盲目重复执行；失败重试保留原模拟退款单号及审计。
- `SIMLECT_AFTERSALES_MOCK_REFUND_ENABLED` 默认关闭；页面按后端capabilities显示允许的操作，不确定时禁用。
- Agent退款执行保护与模拟开关不是同一开关。不能因为管理员模拟验收通过，就解除 `action_execute_service.py` 的真实退款隔离。
- 真实支付渠道退款需另外完成渠道配置、授权和人工审核，当前本文不将其视为已真实联调通过。
- 本地模拟成功不代表银行到账，也不会把原订单的支付状态改成真实退款；订单详情独立展示售后进度。

用户入口：客服 `AgentCasePanel.vue`、订单列表“售后进度”、订单详情。管理入口：`/admin/order/aftersalesCases`；支持审核、接单、退货物流人工核实、验收、模拟结果及审计。

## 6. 售后政策管理与RAG

政策管理页：`/admin/setting/policies`。复用现有FAQ、Search、MQ向量化与ES，不另建知识库微服务。

处理链：原文上传 → PDF/Word/TXT解析 → 条款/文本切分及元数据 → 草稿/审核 → 正式发布 → 现有Embedding服务 → ES向量存储 → 有效政策检索 → 来源引用。

- 政策状态包括 `DRAFT`、`PENDING_REVIEW`、`PUBLISHED`、`DISABLED`、`RETIRED`，保留历史版本、来源、有效期和操作审计。
- 未审核不能作为正式规则发布；停用可逆且不能删除原始文档，重新启用须校验版本、审核及有效期。
- 法规、行业对标和平台自有演示规则分开分类；京东等第三方政策不能自动成为Simlect承诺。
- 引用保留文档ID、名称、版本、Chunk ID、条款/章节、原文、来源链接及相关度等信息。
- 过滤不生效、过期、停用及不适用版本；结合关键词与向量结果、问题意图和条款相关性去重，不靠降低阈值制造命中。
- 无命中、低相关度、Embedding失败、ES不可用分别处理。七日无理由退货与质量问题退换修不能混淆；缺商品类别、收货时间等信息时明确追问。
- 已接入国务院令第778号《中华人民共和国消费者权益保护法实施条例》，已有61个Chunk的处理记录；其他法规草稿不能据此推断为已发布。该数量是历史接入记录，不是当前数据库实时计数。
- 真实Embedding通常使用 `text-embedding-v4`、1024维，必须与现有索引映射匹配；不应为测试擅自重复处理已成功向量化文档。

代码：Python `app/rag/retriever.py`、`embedding.py`、`rrf.py`；Java `Simlect-search` 的 `EsSearchComponent`、`RabbitMQRagListenerComponent` 及知识管理相关代码。

## 7. 数据库与数据治理

| 库/归属 | 核心数据和关系 |
|---|---|
| `simlect_user` | 用户、地址、成长/签到等账户数据；登录用户是订单归属的身份来源 |
| `simlect_product` | `product_info`商品、`product_sku`规格价格、分类属性；SKU关联productId |
| `simlect_stock` | `sku_stock`及库存操作记录；按SKU关联商品，不从其他SKU借库存 |
| `simlect_cart` | 用户购物车，用户间隔离 |
| `simlect_order` | `order_info`订单、`order_item`明细；明细通过所属订单校验用户 |
| 同上 | `aftersales_case`、`aftersales_plan`、`aftersales_manual_task`、`aftersales_audit`：案件/方案版本/人工任务/审计 |
| `simlect_pay` | 支付及退款渠道业务，不等于售后模拟审计 |
| `simlect_coupon` | 优惠券及营销数据 |
| `simlect_search` | FAQ、`knowledge_document`、revision、原文source、policy_audit；ES是检索存储，不是订单权威库 |
| `simlect_agent` | `agent_message`消息文本/业务JSON，`agent_session_memory`用户记忆 |
| `simlect_admin` | 管理账户、权限与运营配置 |
| `simlect_data_governance` | `etl_batch`、`source_record`、`historical_record`：导入批次、来源、隔离历史记录 |

领域数据库通过Java接口/OpenFeign及MQ协作，不应为新功能随意跨库调用Mapper。Python保留已有消息持久化能力，不应由模型直接写商品或订单表。

数据治理工具在 `tools/data_governance/`：原始检查、清洗转换、字段映射、主外键/重复验证、dry-run、批次、幂等及质量报告。公开历史订单/支付应留在隔离历史层，不写入当前用户的交易记录。

来源体系要区分两种含义：`PUBLIC_DATASET/SYNTHETIC/MANUAL/LIVE_API`描述来源渠道，`REAL/DEMO/TEST/UNKNOWN`描述商品可信级别，二者不能互相等同。ABO公开资料授权与来源说明仍应保留；本地生成价格和库存不能因为基础图片真实就改称真实商家数据。

DDL入口 `sql/`，主要增量：`08_aftersales_knowledge.sql`、`09_aftersales_cases.sql`、`21_data_governance.sql`、`22_policy_governance.sql`、`23_agent_message_evidence.sql`。具体表归属见 `sql/TABLE_OWNERSHIP.md`。**现有数据库不能盲目重放全部SQL**；部分ALTER非幂等，必须备份并检查当前结构后执行所需增量。

## 8. 安全与可靠性

- Gateway认证与内部服务令牌只是不同信任层；内部令牌正确不等于可读任意用户订单。
- Python可信上下文和Java归属校验双重约束；用户ID不能由LLM、表单或任意HTTP参数自由覆盖。
- 订单明细必须经过所属订单归属校验；案件查询也按用户及指定订单过滤后分页。
- MCP服务端校验内部令牌并验证业务用户身份；对外不开放任意用户代理。
- 管理员权限在后端验证，敏感管理接口可能要求一次性二次确认票据；不得通过隐藏按钮冒充授权控制。
- Redis限流、待确认提案原子状态保护、业务幂等号、数据库事务和乐观并发约束分别保护不同阶段。
- 超时、503、工具失败、持久化失败、断流和断连按类型降级；不能吞错后仍报告成功。
- 日志不能输出API Key、Authorization、Cookie、密码或用户完整敏感订单资料。
- 模型超时重试不能一概而论：通用LLM配置与政策专用调用策略不同。现有政策调用曾限定20秒、零重试、512输出Token；不应据此声称整个系统所有模型调用都使用该限制。以实际调用工厂和场景代码为准。

## 9. 仓库定位指南

```text
Simlect-backend/
  Simlect-common/         公共实体/枚举/工具等
  Simlect-gateway/        HTTP/WS路由、鉴权及流量入口
  Simlect-user/           账户与用户域
  Simlect-product/        商品/分类/属性/SKU及内部查询
  Simlect-stock/          库存域
  Simlect-order/          订单、物流、售后案件及人工履约
  Simlect-pay/            支付及原渠道退款相关代码
  Simlect-cart/           购物车
  Simlect-coupon/         优惠券及营销
  Simlect-search/         搜索、FAQ/知识、向量处理
  Simlect-admin/          管理服务
  Simlect-agent/
    app/api/             FastAPI接口、WebSocket、鉴权依赖
    app/services/        编排、消息、工具、Java客户端、模型、可靠性
    app/auth/            可信身份、委派权限
    app/domain/          业务意图等确定性契约
    app/graph/           售后/客服LangGraph
    app/shopping/        独立导购图、需求与筛选
    app/supervisor/      路由、专业适配、状态与结果聚合
    app/mcp_server/      FastMCP工具服务
    app/rag/             Embedding、召回、融合与政策证据
    app/memory/          会话记忆
    app/db/              数据库连接
    app/resilience/      韧性组件
    tests/               Python自动化
Simlect-front/
  Simlect-web/           Vue/TS商城；src/components/agent为客服主要UI
  Simlect-admin/         管理端；views/order、setting、product等
sql/                    初始DDL及增量迁移
deploy/                 Compose、本机配置及启动脚本
scripts/local/          Order/Agent/MCP独立启动与检查
tools/data_governance/  ETL和迁移等工具
tools/quality_engineering/ 场景库、独立规则断言、故障与回归工具
e2e/                    Playwright专用浏览器及真实页面操作
data/                   公开商品资料、政策等本地数据
docs/agent-development/ 分阶段实现/验收/失败及风险报告
.cache/、logs/           本机证据、测试环境、运行日志；不能当可公开源码打包
```

Java部分模块采用 `api/app` 结构，Admin/Search/Gateway等布局不同，不能统一假设入口都在 `/app`。

## 10. 本机运行方式

### 地址与端口

| 服务 | 本机默认端口 |
|---|---:|
| 商城 / Admin前端 | 6001 / 6002（Admin入口 `/admin/`） |
| Gateway | 8080 |
| User / Product / Stock | 8105 / 8099 / 8102 |
| Order / Pay / Cart / Coupon | 8093 / 8096 / 8084 / 8087 |
| Search / Admin后端 | 8108 / 8111 |
| Agent / MCP | 7050 / 7060 |

这是配置约定，不是实时探活结果。Java通常通过Nacos发现，不能只看Gateway健康就认定所有功能可用。MySQL本机Compose可映射为13306等非默认主机端口，以本地Compose为准。

### 启动前提

需要JDK17、Maven、符合前端engines的Node/npm、Python3.12、Docker Desktop/WSL2以及已正确初始化和迁移的数据库。项目现有脚本使用 `E:\JDK17`、`E:\Nodejs`、`E:\Python`、`E:\SimlectRuntime` 等路径，新电脑必须先适配，不能直接复制执行。

在项目根目录使用已有整套本机入口：

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\run-configured.ps1
```

默认All会启动中间件并调用Java/Python/前端启动逻辑。已有健康服务时应先检查占用并仅操作必要模块，不能用它反复重启整套系统。

已有独立启动入口（前台监督运行，若后台启动应采用已有独立Windows进程方式并保留日志）：

```powershell
.\scripts\local\start-order.ps1 -ValidateOnly
.\scripts\local\start-agent.ps1 -ValidateOnly
.\scripts\local\start-mcp.ps1 -ValidateOnly
.\scripts\local\check-agent-services.ps1
```

去掉 `-ValidateOnly` 才是启动。Python底层入口为在 `Simlect-backend/Simlect-agent` 工作目录执行现有虚拟环境的 `python -m uvicorn app.main:app --host 127.0.0.1 --port 7050`；MCP为 `python -m app.mcp_server`。使用本机脚本可复用现有环境加载，避免裸启动遗漏变量。

前端各自目录执行 `npm run dev`；商品服务与库存服务等Java启动命令应按对应构建产物及本地环境确认，不用Order脚本替代其他模块。

### 配置与健康检查

Python配置入口 `app/config/settings.py`，本机脚本读取 `Simlect-backend/Simlect-agent/.env`。重要配置包括LLM/Embedding地址模型、内部令牌、Java/MCP地址、MySQL/Redis/ES、Origin白名单及导购数据模式。此文件不得公开，也不要把环境值粘贴给其他AI；只分享脱敏键名、错误类型和状态。

健康入口：Java `/actuator/health`，Agent和MCP `/health`。Agent需同时检查 `status` 和 `java_web`，不能只看HTTP200。搜索503检查Search注册与监听，购物车503检查Cart；验证码不出检查User及 `/account/checkCode` 对应路由，不应一律归咎于前端。

## 11. 自动化与验收口径

统一代码回归入口：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\quality_engineering\run-regression.ps1
```

该脚本依赖本机已准备好的测试环境、安全网络harness和工具路径，不是新克隆仓库上无需准备的通用命令。包含Python、受控变异、Java、前端测试/构建及只读健康检查。

项目专用浏览器验收（先准备已验证的隔离环境和正常测试登录）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\e2e\run-e2e.ps1 -Suite return -CloseBrowser -CleanTestData
```

Playwright自行启动Chromium，商城与Admin独立上下文，不接管个人Chrome，不导出Cookie/Token，不绕过验证码。隔离页面使用 `127.0.0.2:16001` 和 `127.0.0.2:16002/admin/`，不是正式6001/6002；实际页面写入隔离案件后由SQL独立核实，截图/视频和失败日志落E盘。清理仅针对已识别的隔离临时行，不清空正式数据库或向量库。

**最近一次退款修复专项记录（2026-11-06，历史结果而非本次重新执行）：**

| 层次 | 记录结果 | 不代表什么 |
|---|---|---|
| Python全量单元/Mock | 1349通过，0失败，0跳过 | 不等于真实DeepSeek验收 |
| Java全模块离线回归 | 1601通过，0失败，2邮件测试跳过 | 不等于真实渠道支付/退款/邮件验收 |
| 商城 / Admin前端测试 | 72 / 27通过，生产构建通过 | 不等于所有页面业务分支均验收 |
| 隔离浏览器退款主链 | 1用例通过，含自然语言进度，18项独立SQL断言通过 | 不等于全项目浏览器一次全绿，也不等于真实资金成功 |

证据见 `docs/agent-development/退款待执行与管理端确认无反馈修复记录-20261106.md`。其Java专项667项与全量重叠，不能再次相加。更早第34阶段另有不同执行范围，不应混用数字。

## 12. 已知限制与后续工作

1. 本地目录与来源数据不等于企业ERP/OMS/WMS；缺少真实商品或仓储数据时应说明，不能伪造商业事实。
2. 真实LLM和Embedding历史连通/个别调用结果不等于最新全部工作流已通过真实模型验收；存在超时、503历史，需要有限额度单独验收。
3. 同用户多独立会话隔离、多明细逐件/部分金额退货、所有异常分支页面覆盖、长期稳定性仍有记录中的缺口。
4. 物流人工登记不是承运商实时轨迹，仓库验收必须由实际人员确认；不应自动勾选收到/验收。
5. 真实退款默认受限；模拟成功不改变原支付事实，渠道接入和到账对账尚需独立建设及授权。
6. 政策检索提供依据，不取代法律适用核实；官方法规与商城额外服务承诺不能混淆。
7. 源码变更后需构建/重载实际运行服务；不能拿新源码测试通过证明旧进程已加载修复。重载前备份日志，仅重载必要服务。
8. 本次README工作只检查源码和报告，**没有探活服务、运行回归、重启服务或重新验收任何业务**。

## 13. 将本文件提供给另一个AI时

可以直接附上README，并说明“这是本地增量版本的上下文，不是生产完成声明”。让AI优先根据业务边界分析；若要定位具体缺陷，再提供相关源码、脱敏响应、错误堆栈和对应验收范围。

不要要求AI仅凭README断言实时服务状态、真实库存、用户订单或政策当前发布数量。不要发送 `.env`、测试私密账号文件、浏览器资料目录、Token、原始数据库备份。不要让AI通过伪造登录、改业务状态、降低相关度阈值或将模拟数据标成真实来“修复”验收。

优先阅读索引：

- `docs/agent-development/三大模块功能实现矩阵.md`：导购、售后和后台功能到源码/测试的对应。
- `docs/agent-development/34-10-第34阶段最终验收矩阵.md`：隔离环境最终结果及未完成项。
- `docs/agent-development/退款待执行与管理端确认无反馈修复记录-20261106.md`：较新的进度查询、验收提示及必要服务加载记录。
- `e2e/README.md`：项目专用浏览器、登录及证据机制。
- `tools/quality_engineering/README.md`：场景、独立规则和回归工具。
- `sql/TABLE_OWNERSHIP.md`：数据库归属。

## 14. 许可

项目源码许可见 [LICENSE.md](LICENSE.md)（MIT，保留原作者声明）。商品图片、公开数据集、参考站内容和政策文件来源有各自的使用条件；源码MIT许可不能替代第三方资料授权。商业使用前需分别核实相关资料的许可及转载范围。


## 附录A：Java接口声明与源码定位清单

本清单由2026-11-07当前工作区Java Controller注解提取，列出用户端、管理端、内部工具和维护操作，避免仅写AI功能而遗漏原商城业务。**这是源码声明索引，不是实时开放API清单，也不是逐接口运行验收。**

- 路径为Controller声明路径，调用时还需结合Gateway前缀、StripPrefix/重写及权限规则；不要直接为全部路径拼同一个前缀。
- `REQUEST`表示使用@RequestMapping声明；具体HTTP方法和参数仍需看源码。相同路径的表单/JSON实现可能合并显示。
- 内部接口需要内部认证和相应业务权限，管理接口需要管理员授权；维护、删除、退款、索引和同步入口不能随意测试执行。
- 基类、异常处理器及没有映射声明的Controller文件不当作业务接口计数；此静态扫描不是OpenAPI校验，不覆盖继承/动态注册的所有可能路径。

当前扫描包含 **75个有映射声明的Controller文件、402个文件内去重的HTTP方法/路径声明**。该数字不等于独立业务功能数或测试通过数。

| 模块 | Controller源码 | 声明操作 |
|---|---|---|
| Simlect-admin | [admin/AgentMessageController.java](Simlect-backend/Simlect-admin/src/main/java/com/simlect/controller/admin/AgentMessageController.java) | `POST /admin/agentMessage/loadDataList`<br>`POST /admin/agentMessage/deleteAgentMessageByMessageId` |
| Simlect-admin | [admin/HomeController.java](Simlect-backend/Simlect-admin/src/main/java/com/simlect/controller/admin/HomeController.java) | `POST /admin/home/loadLessStockProduct`<br>`POST /admin/home/getTodayData`<br>`POST /admin/home/loadWeeklyStatisticsData` |
| Simlect-admin | [admin/MqCompensationLogController.java](Simlect-backend/Simlect-admin/src/main/java/com/simlect/controller/admin/MqCompensationLogController.java) | `POST /admin/mqCompensationLog/loadDataList`<br>`POST /admin/mqCompensationLog/getByLogId`<br>`POST /admin/mqCompensationLog/updateStatus`<br>`POST /admin/mqCompensationLog/replay` |
| Simlect-admin | [admin/SensitiveWordController.java](Simlect-backend/Simlect-admin/src/main/java/com/simlect/controller/admin/SensitiveWordController.java) | `POST /admin/sensitiveWord/list`<br>`POST /admin/sensitiveWord/save`<br>`POST /admin/sensitiveWord/delete`<br>`POST /admin/sensitiveWord/refresh` |
| Simlect-admin | [admin/SettingController.java](Simlect-backend/Simlect-admin/src/main/java/com/simlect/controller/admin/SettingController.java) | `POST /admin/setting/saveLogistics`<br>`POST /admin/setting/getLogistics`<br>`POST /admin/setting/loadPromptList`<br>`POST /admin/setting/getPromptDetail`<br>`POST /admin/setting/savePrompt`<br>`POST /admin/setting/cleanPromptCache` |
| Simlect-admin | [admin/StatisticsInfoController.java](Simlect-backend/Simlect-admin/src/main/java/com/simlect/controller/admin/StatisticsInfoController.java) | `POST /admin/statisticsInfo/loadDataList` |
| Simlect-admin | [admin/ToolController.java](Simlect-backend/Simlect-admin/src/main/java/com/simlect/controller/admin/ToolController.java) | `POST /admin/tool/statistics`<br>`POST /admin/tool/productData`<br>`POST /admin/tool/ragData`<br>`POST /admin/tool/addAllOrderToDelayQueue` |
| Simlect-admin | [internal/AdminAuditInternalController.java](Simlect-backend/Simlect-admin/src/main/java/com/simlect/controller/internal/AdminAuditInternalController.java) | `POST /internal/admin/audit/log` |
| Simlect-cart | [admin/ProductCartController.java](Simlect-backend/Simlect-cart/app/src/main/java/com/simlect/controller/admin/ProductCartController.java) | `POST /admin/productCart/loadDataList`<br>`POST /admin/productCart/add`<br>`POST /admin/productCart/addBatch`<br>`POST /admin/productCart/addOrUpdateBatch`<br>`POST /admin/productCart/getProductCartByCartId`<br>`POST /admin/productCart/updateProductCartByCartId`<br>`POST /admin/productCart/deleteProductCartByCartId`<br>`POST /admin/productCart/getProductCartByProductIdAndPropertyValueIdHashAndUserId`<br>`POST /admin/productCart/updateProductCartByProductIdAndPropertyValueIdHashAndUserId`<br>`POST /admin/productCart/deleteProductCartByProductIdAndPropertyValueIdHashAndUserId` |
| Simlect-cart | [internal/CartInternalController.java](Simlect-backend/Simlect-cart/app/src/main/java/com/simlect/controller/internal/CartInternalController.java) | `POST /internal/cart/deleteBatch` |
| Simlect-cart | [ProductCartController.java](Simlect-backend/Simlect-cart/app/src/main/java/com/simlect/controller/ProductCartController.java) | `POST /productCart/add2Cart`<br>`POST /productCart/loadProductCart`<br>`POST /productCart/deleteCart` |
| Simlect-coupon | [admin/DiscountCouponController.java](Simlect-backend/Simlect-coupon/app/src/main/java/com/simlect/controller/admin/DiscountCouponController.java) | `POST /admin/discountCoupon/saveDiscountCoupon`<br>`POST /admin/discountCoupon/loadDiscountCoupon`<br>`POST /admin/discountCoupon/getDiscountCouponInfo`<br>`POST /admin/discountCoupon/updateDiscountCouponStatus`<br>`POST /admin/discountCoupon/warmupRushStock`<br>`POST /admin/discountCoupon/reconcileRushStock` |
| Simlect-coupon | [DiscountCouponController.java](Simlect-backend/Simlect-coupon/app/src/main/java/com/simlect/controller/DiscountCouponController.java) | `POST /discountCoupon/getDiscountCouponDetail`<br>`POST /discountCoupon/loadDiscountCoupon`<br>`POST /discountCoupon/rushCoupon`<br>`POST /discountCoupon/buyDiscountCoupon`<br>`POST /discountCoupon/loadUserCoupon` |
| Simlect-coupon | [internal/CouponAgentInternalController.java](Simlect-backend/Simlect-coupon/app/src/main/java/com/simlect/controller/internal/CouponAgentInternalController.java) | `POST /internal/coupon/agent/listUserCoupons` |
| Simlect-coupon | [internal/CouponInternalController.java](Simlect-backend/Simlect-coupon/app/src/main/java/com/simlect/controller/internal/CouponInternalController.java) | `POST /internal/coupon/validateAndLock`<br>`POST /internal/coupon/getCoupon`<br>`POST /internal/coupon/getCouponBrief`<br>`POST /internal/coupon/getUserCoupon`<br>`POST /internal/coupon/changeUserCouponStatus`<br>`POST /internal/coupon/createUserCoupon`<br>`POST /internal/coupon/deductStock`<br>`POST /internal/coupon/rush/assertNotBlocked`<br>`POST /internal/coupon/rush/hasAvailableStock`<br>`POST /internal/coupon/rush/syncFromDbIfRedisZero`<br>`POST /internal/coupon/rush/releaseRedisReserve`<br>`POST /internal/coupon/rush/releaseCouponReserve`<br>`POST /internal/coupon/rush/invalidateCache` |
| Simlect-order | [admin/CommentReportController.java](Simlect-backend/Simlect-order/app/src/main/java/com/simlect/controller/admin/CommentReportController.java) | `POST /admin/commentReport/loadDataList`<br>`POST /admin/commentReport/getCommentReportByReportId`<br>`POST /admin/commentReport/handleReport`<br>`POST /admin/commentReport/deleteCommentReportByReportId` |
| Simlect-order | [admin/OrderCommentController.java](Simlect-backend/Simlect-order/app/src/main/java/com/simlect/controller/admin/OrderCommentController.java) | `POST /admin/orderComment/loadDataList`<br>`POST /admin/orderComment/add`<br>`POST /admin/orderComment/addBatch`<br>`POST /admin/orderComment/addOrUpdateBatch`<br>`POST /admin/orderComment/getOrderCommentByOrderId`<br>`POST /admin/orderComment/updateOrderCommentByOrderId`<br>`POST /admin/orderComment/deleteOrderCommentByOrderId` |
| Simlect-order | [admin/OrderController.java](Simlect-backend/Simlect-order/app/src/main/java/com/simlect/controller/admin/OrderController.java) | `POST /admin/order/loadOrder`<br>`POST /admin/order/loadOrderStatus`<br>`POST /admin/order/loadComment`<br>`POST /admin/order/getComment`<br>`POST /admin/order/bizComment`<br>`POST /admin/order/delComment`<br>`POST /admin/order/getLogistics`<br>`POST /admin/order/delivery` |
| Simlect-order | [admin/OrderInfoController.java](Simlect-backend/Simlect-order/app/src/main/java/com/simlect/controller/admin/OrderInfoController.java) | `POST /admin/orderInfo/loadDataList`<br>`POST /admin/orderInfo/add`<br>`POST /admin/orderInfo/addBatch`<br>`POST /admin/orderInfo/addOrUpdateBatch`<br>`POST /admin/orderInfo/getOrderInfoByOrderId`<br>`POST /admin/orderInfo/updateOrderInfoByOrderId`<br>`POST /admin/orderInfo/deleteOrderInfoByOrderId` |
| Simlect-order | [admin/OrderItemController.java](Simlect-backend/Simlect-order/app/src/main/java/com/simlect/controller/admin/OrderItemController.java) | `POST /admin/orderItem/loadDataList`<br>`POST /admin/orderItem/add`<br>`POST /admin/orderItem/addBatch`<br>`POST /admin/orderItem/addOrUpdateBatch`<br>`POST /admin/orderItem/getOrderItemByOrderItemId`<br>`POST /admin/orderItem/updateOrderItemByOrderItemId`<br>`POST /admin/orderItem/deleteOrderItemByOrderItemId` |
| Simlect-order | [admin/OrderLogisticsInfoController.java](Simlect-backend/Simlect-order/app/src/main/java/com/simlect/controller/admin/OrderLogisticsInfoController.java) | `POST /admin/orderLogisticsInfo/loadDataList`<br>`POST /admin/orderLogisticsInfo/add`<br>`POST /admin/orderLogisticsInfo/addBatch`<br>`POST /admin/orderLogisticsInfo/addOrUpdateBatch`<br>`POST /admin/orderLogisticsInfo/getOrderLogisticsInfoByOrderId`<br>`POST /admin/orderLogisticsInfo/updateOrderLogisticsInfoByOrderId`<br>`POST /admin/orderLogisticsInfo/deleteOrderLogisticsInfoByOrderId` |
| Simlect-order | [admin/OrderLogisticsInfoRecordController.java](Simlect-backend/Simlect-order/app/src/main/java/com/simlect/controller/admin/OrderLogisticsInfoRecordController.java) | `POST /admin/orderLogisticsInfoRecord/loadDataList`<br>`POST /admin/orderLogisticsInfoRecord/add`<br>`POST /admin/orderLogisticsInfoRecord/addBatch`<br>`POST /admin/orderLogisticsInfoRecord/addOrUpdateBatch`<br>`POST /admin/orderLogisticsInfoRecord/getOrderLogisticsInfoRecordByRecordId`<br>`POST /admin/orderLogisticsInfoRecord/updateOrderLogisticsInfoRecordByRecordId`<br>`POST /admin/orderLogisticsInfoRecord/deleteOrderLogisticsInfoRecordByRecordId` |
| Simlect-order | [aftersales/AftersalesAdminController.java](Simlect-backend/Simlect-order/app/src/main/java/com/simlect/controller/aftersales/AftersalesAdminController.java) | `POST /admin/aftersalesCase/returnLogistics`<br>`POST /admin/aftersalesCase/returnProgress`<br>`POST /admin/aftersalesCase/acceptReturn`<br>`POST /admin/aftersalesCase/simulateRefund`<br>`POST /admin/aftersalesCase/detail`<br>`POST /admin/aftersalesCase/list`<br>`POST /admin/aftersalesCase/approve`<br>`POST /admin/aftersalesCase/reject`<br>`POST /admin/aftersalesCase/claim`<br>`POST /admin/aftersalesCase/succeed`<br>`POST /admin/aftersalesCase/fail`<br>`POST /admin/aftersalesCase/retry`<br>`POST /admin/aftersalesCase/archive`<br>`POST /admin/aftersalesCase/prepareRefund`<br>`POST /admin/aftersalesCase/startMockRefund`<br>`POST /admin/aftersalesCase/completeMockRefund`<br>`POST /admin/aftersalesCase/timeoutMockRefund` |
| Simlect-order | [aftersales/AftersalesUserController.java](Simlect-backend/Simlect-order/app/src/main/java/com/simlect/controller/aftersales/AftersalesUserController.java) | `POST /order/aftersalesCase/detail`<br>`POST /order/aftersalesCase/list`<br>`POST /order/aftersalesCase/returnLogistics`<br>`POST /order/aftersalesCase/confirm`<br>`POST /order/aftersalesCase/resubmit`<br>`POST /order/aftersalesCase/archive`<br>`POST /order/aftersalesCase/amend`<br>`POST /order/aftersalesCase/cancel` |
| Simlect-order | [CommentReportController.java](Simlect-backend/Simlect-order/app/src/main/java/com/simlect/controller/CommentReportController.java) | `POST /commentReport/submitReport` |
| Simlect-order | [internal/AftersalesInternalController.java](Simlect-backend/Simlect-order/app/src/main/java/com/simlect/controller/internal/AftersalesInternalController.java) | `POST /internal/order/aftersales/create` |
| Simlect-order | [internal/OrderAgentInternalController.java](Simlect-backend/Simlect-order/app/src/main/java/com/simlect/controller/internal/OrderAgentInternalController.java) | `POST /internal/order/agent/listOrders`<br>`POST /internal/order/agent/getOrder`<br>`POST /internal/order/agent/getOrderItem`<br>`POST /internal/order/agent/listOrderItems`<br>`POST /internal/order/agent/getLogistics`<br>`POST /internal/order/agent/getComment` |
| Simlect-order | [internal/OrderInternalController.java](Simlect-backend/Simlect-order/app/src/main/java/com/simlect/controller/internal/OrderInternalController.java) | `POST /internal/order/get`<br>`POST /internal/order/cancelUnpaidForPayTimeout`<br>`POST /internal/order/confirmReceipt`<br>`POST /internal/order/onConfirmed`<br>`POST /internal/order/paySuccess`<br>`POST /internal/order/prepareCouponRush`<br>`POST /internal/order/postCouponRushOrder`<br>`POST /internal/order/syncPaidCouponRushUserCoupons`<br>`POST /internal/order/cancelOrder`<br>`POST /internal/order/stats/range`<br>`POST /internal/order/stats/daily`<br>`POST /internal/order/tool/addAllWaitPayToDelayQueue` |
| Simlect-order | [LocalPaymentController.java](Simlect-backend/Simlect-order/app/src/main/java/com/simlect/controller/LocalPaymentController.java) | `GET /order/paymentMode`<br>`POST /order/localPay` |
| Simlect-order | [OrderCommentController.java](Simlect-backend/Simlect-order/app/src/main/java/com/simlect/controller/OrderCommentController.java) | `POST /order/comment/postComment`<br>`POST /order/comment/loadComment`<br>`POST /order/comment/getComment`<br>`POST /order/comment/postReComment`<br>`POST /order/comment/loadMyComment`<br>`POST /order/comment/delMyComment`<br>`POST /order/comment/getProductCommentStats` |
| Simlect-order | [OrderController.java](Simlect-backend/Simlect-order/app/src/main/java/com/simlect/controller/OrderController.java) | `POST /order/postOrder`<br>`POST /order/getPayInfo`<br>`POST /order/getOrderInfo`<br>`POST /order/loadMyOrder`<br>`POST /order/cancelOrder`<br>`POST /order/deleteOrder`<br>`POST /order/confirmOrder`<br>`POST /order/refundOrder`<br>`POST /order/getMyOrderDetail`<br>`POST /order/getLogistics`<br>`GET /order/getOrderCountInfo` |
| Simlect-pay | [internal/PayInternalController.java](Simlect-backend/Simlect-pay/app/src/main/java/com/simlect/controller/internal/PayInternalController.java) | `POST /internal/pay/trade/createPending`<br>`POST /internal/pay/trade/markSuccess`<br>`POST /internal/pay/trade/markClosed`<br>`POST /internal/pay/trade/markRefunded`<br>`POST /internal/pay/channel/getPayUrl`<br>`POST /internal/pay/channel/refund`<br>`POST /internal/pay/channel/closeOrder`<br>`POST /internal/pay/channel/queryOrder` |
| Simlect-pay | [PayNotifyController.java](Simlect-backend/Simlect-pay/app/src/main/java/com/simlect/controller/PayNotifyController.java) | `POST /notify/alipayNotify` |
| Simlect-pay | [PayTradeRecordController.java](Simlect-backend/Simlect-pay/app/src/main/java/com/simlect/controller/PayTradeRecordController.java) | `POST /payTrade/loadMyTrades` |
| Simlect-product | [admin/ProductInfoController.java](Simlect-backend/Simlect-product/app/src/main/java/com/simlect/controller/admin/ProductInfoController.java) | `POST /admin/productInfo/previewReferenceCatalogue`<br>`POST /admin/productInfo/publishReferenceCatalogue`<br>`POST /admin/productInfo/referenceCatalogueStatus`<br>`POST /admin/productInfo/previewCatalogueReadiness`<br>`POST /admin/productInfo/prepareCatalogue`<br>`POST /admin/productInfo/previewPublicCatalogue`<br>`POST /admin/productInfo/publishPublicCatalogue`<br>`POST /admin/productInfo/loadDataList`<br>`POST /admin/productInfo/addProduct`<br>`POST /admin/productInfo/updateProduct`<br>`POST /admin/productInfo/addBatch`<br>`POST /admin/productInfo/addOrUpdateBatch`<br>`POST /admin/productInfo/getProductInfoByProductId`<br>`POST /admin/productInfo/updateProductInfoByProductId`<br>`POST /admin/productInfo/deleteProductInfoByProductId`<br>`POST /admin/productInfo/loadProduct`<br>`POST /admin/productInfo/getProductInfo`<br>`POST /admin/productInfo/updateSkuStock`<br>`POST /admin/productInfo/updateProductStatus`<br>`POST /admin/productInfo/deleteProduct`<br>`POST /admin/productInfo/commendProduct` |
| Simlect-product | [admin/ProductPropertyValueController.java](Simlect-backend/Simlect-product/app/src/main/java/com/simlect/controller/admin/ProductPropertyValueController.java) | `POST /admin/productPropertyValue/loadDataList`<br>`POST /admin/productPropertyValue/add`<br>`POST /admin/productPropertyValue/addBatch`<br>`POST /admin/productPropertyValue/addOrUpdateBatch`<br>`POST /admin/productPropertyValue/getProductPropertyValueByProductIdAndPropertyValueId`<br>`POST /admin/productPropertyValue/updateProductPropertyValueByProductIdAndPropertyValueId`<br>`POST /admin/productPropertyValue/deleteProductPropertyValueByProductIdAndPropertyValueId` |
| Simlect-product | [admin/ProductSkuController.java](Simlect-backend/Simlect-product/app/src/main/java/com/simlect/controller/admin/ProductSkuController.java) | `POST /admin/productSku/loadDataList`<br>`POST /admin/productSku/add`<br>`POST /admin/productSku/addBatch`<br>`POST /admin/productSku/addOrUpdateBatch`<br>`POST /admin/productSku/getProductSkuByProductIdAndPropertyValueIdHash`<br>`POST /admin/productSku/updateProductSkuByProductIdAndPropertyValueIdHash`<br>`POST /admin/productSku/deleteProductSkuByProductIdAndPropertyValueIdHash` |
| Simlect-product | [admin/SysCategoryController.java](Simlect-backend/Simlect-product/app/src/main/java/com/simlect/controller/admin/SysCategoryController.java) | `POST /admin/sysCategory/loadCategory`<br>`POST /admin/sysCategory/saveCategory`<br>`POST /admin/sysCategory/addBatch`<br>`POST /admin/sysCategory/addOrUpdateBatch`<br>`POST /admin/sysCategory/getSysCategoryByCategoryId`<br>`POST /admin/sysCategory/updateSysCategoryByCategoryId`<br>`POST /admin/sysCategory/delCategory`<br>`POST /admin/sysCategory/changeCategorySort`<br>`POST /admin/sysCategory/saveProductProperty`<br>`POST /admin/sysCategory/delProductProperty` |
| Simlect-product | [admin/SysProductPropertyController.java](Simlect-backend/Simlect-product/app/src/main/java/com/simlect/controller/admin/SysProductPropertyController.java) | `POST /admin/sysProductProperty/loadDataList`<br>`POST /admin/sysProductProperty/add`<br>`POST /admin/sysProductProperty/addBatch`<br>`POST /admin/sysProductProperty/addOrUpdateBatch`<br>`POST /admin/sysProductProperty/getSysProductPropertyByPropertyId`<br>`POST /admin/sysProductProperty/updateSysProductPropertyByPropertyId`<br>`POST /admin/sysProductProperty/deleteSysProductPropertyByPropertyId` |
| Simlect-product | [internal/ProductAgentInternalController.java](Simlect-backend/Simlect-product/app/src/main/java/com/simlect/controller/internal/ProductAgentInternalController.java) | `POST /internal/product/agent/queryBatch`<br>`POST /internal/product/agent/searchOnSale`<br>`POST /internal/product/agent/getDetail` |
| Simlect-product | [internal/ProductInternalController.java](Simlect-backend/Simlect-product/app/src/main/java/com/simlect/controller/internal/ProductInternalController.java) | `POST /internal/product/snapshotBatch`<br>`POST /internal/product/defaultSku`<br>`POST /internal/product/increaseSales`<br>`POST /internal/product/searchIndex`<br>`POST /internal/product/ragIndex`<br>`POST /internal/product/lessStockSkuPage`<br>`POST /internal/product/listOnSaleProductIds` |
| Simlect-product | [ProductController.java](Simlect-backend/Simlect-product/app/src/main/java/com/simlect/controller/ProductController.java) | `GET /product/loadCategory`<br>`GET /product/loadCommendProduct`<br>`POST /product/loadProduct`<br>`POST /product/getProduct`<br>`POST /product/search` |
| Simlect-product | [PublicCatalogueController.java](Simlect-backend/Simlect-product/app/src/main/java/com/simlect/controller/PublicCatalogueController.java) | `GET /product/publicCatalogue`<br>`POST /admin/productInfo/publicBatches` |
| Simlect-search | [admin/KnowledgeDocumentController.java](Simlect-backend/Simlect-search/src/main/java/com/simlect/controller/admin/KnowledgeDocumentController.java) | `POST /admin/rag/knowledge/import`<br>`POST /admin/rag/knowledge/list`<br>`POST /admin/rag/knowledge/detail`<br>`POST /admin/rag/knowledge/publish`<br>`POST /admin/rag/knowledge/reindex`<br>`POST /admin/rag/knowledge/delete`<br>`POST /admin/rag/knowledge/transition`<br>`POST /admin/rag/knowledge/metadata`<br>`POST /admin/rag/knowledge/version`<br>`GET /admin/rag/knowledge/original` |
| Simlect-search | [admin/RagController.java](Simlect-backend/Simlect-search/src/main/java/com/simlect/controller/admin/RagController.java) | `POST /admin/rag/loadRagQuestion`<br>`POST /admin/rag/saveRagQuestion`<br>`POST /admin/rag/delRagQuestion` |
| Simlect-search | [admin/RagQuestionController.java](Simlect-backend/Simlect-search/src/main/java/com/simlect/controller/admin/RagQuestionController.java) | `POST /admin/ragQuestion/loadDataList`<br>`POST /admin/ragQuestion/add`<br>`POST /admin/ragQuestion/addBatch`<br>`POST /admin/ragQuestion/addOrUpdateBatch`<br>`POST /admin/ragQuestion/getRagQuestionByQuestionId`<br>`POST /admin/ragQuestion/updateRagQuestionByQuestionId`<br>`POST /admin/ragQuestion/deleteRagQuestionByQuestionId` |
| Simlect-search | [admin/RagSyncFailureController.java](Simlect-backend/Simlect-search/src/main/java/com/simlect/controller/admin/RagSyncFailureController.java) | `POST /admin/ragSyncFailure/loadDataList`<br>`POST /admin/ragSyncFailure/replay`<br>`POST /admin/ragSyncFailure/updateStatus`<br>`POST /admin/ragSyncFailure/dismissRedisSnapshot` |
| Simlect-search | [admin/SearchHotKeywordController.java](Simlect-backend/Simlect-search/src/main/java/com/simlect/controller/admin/SearchHotKeywordController.java) | `POST /admin/searchHotKeyword/loadList`<br>`POST /admin/searchHotKeyword/save`<br>`POST /admin/searchHotKeyword/del` |
| Simlect-search | [CatalogueIndexController.java](Simlect-backend/Simlect-search/src/main/java/com/simlect/controller/CatalogueIndexController.java) | `POST /internal/search/syncCatalogue` |
| Simlect-search | [internal/KnowledgeCatalogController.java](Simlect-backend/Simlect-search/src/main/java/com/simlect/controller/internal/KnowledgeCatalogController.java) | `POST /internal/knowledge/catalog` |
| Simlect-search | [internal/SearchToolInternalController.java](Simlect-backend/Simlect-search/src/main/java/com/simlect/controller/internal/SearchToolInternalController.java) | `POST /internal/search/tool/refreshKeywordIndex`<br>`POST /internal/search/tool/productData`<br>`POST /internal/search/tool/ragData` |
| Simlect-search | [SearchController.java](Simlect-backend/Simlect-search/src/main/java/com/simlect/controller/SearchController.java) | `POST /search/products`<br>`GET /search/loadHotKeywords`<br>`GET /search/loadRecentKeywords`<br>`POST /search/saveKeyword`<br>`POST /search/clearRecentKeywords`<br>`POST /search/removeRecentKeyword`<br>`GET /search/loadGuessKeywords`<br>`GET /search/loadRecommendProducts` |
| Simlect-stock | [internal/StockInternalController.java](Simlect-backend/Simlect-stock/app/src/main/java/com/simlect/controller/internal/StockInternalController.java) | `POST /internal/stock/initializeCatalogue`<br>`POST /internal/stock/queryBatch`<br>`POST /internal/stock/get`<br>`POST /internal/stock/change`<br>`POST /internal/stock/changeBatch`<br>`POST /internal/stock/lockAndVerify`<br>`POST /internal/stock/set`<br>`POST /internal/stock/totalByProduct`<br>`POST /internal/stock/listLessThan` |
| Simlect-stock | [StockController.java](Simlect-backend/Simlect-stock/app/src/main/java/com/simlect/controller/StockController.java) | `POST /stock/health` |
| Simlect-user | [AccountController.java](Simlect-backend/Simlect-user/app/src/main/java/com/simlect/controller/AccountController.java) | `GET /account/autoLogin`<br>`GET /account/checkCode`<br>`POST /account/register`<br>`POST /account/login`<br>`POST /account/logout`<br>`GET /account/getUserInfo`<br>`POST /account/updateUserInfo`<br>`POST /account/updatePassword`<br>`POST /account/getEmailCode`<br>`POST /account/forgetPassword` |
| Simlect-user | [admin/AccountController.java](Simlect-backend/Simlect-user/app/src/main/java/com/simlect/controller/admin/AccountController.java) | `POST /admin/account/checkCode`<br>`POST /admin/account/login`<br>`POST /admin/account/logout`<br>`GET /admin/account/checkLogin`<br>`POST /admin/account/confirmPassword` |
| Simlect-user | [admin/FileController.java](Simlect-backend/Simlect-user/app/src/main/java/com/simlect/controller/admin/FileController.java) | `POST /admin/file/uploadImage`<br>`GET /admin/file/getResource` |
| Simlect-user | [admin/ImageModerationController.java](Simlect-backend/Simlect-user/app/src/main/java/com/simlect/controller/admin/ImageModerationController.java) | `POST /admin/imageModeration/loadDataList`<br>`POST /admin/imageModeration/getByRecordId`<br>`POST /admin/imageModeration/handleReview`<br>`POST /admin/imageModeration/getTempBanInfo`<br>`POST /admin/imageModeration/unbanUser`<br>`POST /admin/imageModeration/censorImage` |
| Simlect-user | [admin/MemberLevelRewardConfigController.java](Simlect-backend/Simlect-user/app/src/main/java/com/simlect/controller/admin/MemberLevelRewardConfigController.java) | `POST /admin/memberLevelRewardConfig/getConfig`<br>`POST /admin/memberLevelRewardConfig/saveConfig` |
| Simlect-user | [admin/SignRewardConfigController.java](Simlect-backend/Simlect-user/app/src/main/java/com/simlect/controller/admin/SignRewardConfigController.java) | `POST /admin/signRewardConfig/getConfig`<br>`POST /admin/signRewardConfig/saveConfig` |
| Simlect-user | [admin/UserAddressController.java](Simlect-backend/Simlect-user/app/src/main/java/com/simlect/controller/admin/UserAddressController.java) | `POST /admin/userAddress/loadDataList`<br>`POST /admin/userAddress/add`<br>`POST /admin/userAddress/addBatch`<br>`POST /admin/userAddress/addOrUpdateBatch`<br>`POST /admin/userAddress/getUserAddressByAddressId`<br>`POST /admin/userAddress/updateUserAddressByAddressId`<br>`POST /admin/userAddress/deleteUserAddressByAddressId` |
| Simlect-user | [admin/UserController.java](Simlect-backend/Simlect-user/app/src/main/java/com/simlect/controller/admin/UserController.java) | `POST /admin/user/loadUser`<br>`POST /admin/user/changeStatus` |
| Simlect-user | [admin/UserInfoController.java](Simlect-backend/Simlect-user/app/src/main/java/com/simlect/controller/admin/UserInfoController.java) | `POST /admin/userInfo/loadDataList`<br>`POST /admin/userInfo/add`<br>`POST /admin/userInfo/addBatch`<br>`POST /admin/userInfo/addOrUpdateBatch`<br>`POST /admin/userInfo/getUserInfoByUserId`<br>`POST /admin/userInfo/updateUserInfoByUserId`<br>`POST /admin/userInfo/deleteUserInfoByUserId`<br>`POST /admin/userInfo/getUserInfoByEmail`<br>`POST /admin/userInfo/updateUserInfoByEmail`<br>`POST /admin/userInfo/deleteUserInfoByEmail`<br>`POST /admin/userInfo/getUserInfoByNickName`<br>`POST /admin/userInfo/updateUserInfoByNickName`<br>`POST /admin/userInfo/deleteUserInfoByNickName` |
| Simlect-user | [FileController.java](Simlect-backend/Simlect-user/app/src/main/java/com/simlect/controller/FileController.java) | `POST /file/uploadImage`<br>`GET /file/getResource` |
| Simlect-user | [internal/UserAgentInternalController.java](Simlect-backend/Simlect-user/app/src/main/java/com/simlect/controller/internal/UserAgentInternalController.java) | `POST /internal/user/agent/latestBrowseProductId` |
| Simlect-user | [internal/UserInternalController.java](Simlect-backend/Simlect-user/app/src/main/java/com/simlect/controller/internal/UserInternalController.java) | `POST /internal/user/address/get`<br>`POST /internal/user/member/addGrowthOnPay`<br>`POST /internal/user/notify/sendAsync`<br>`POST /internal/user/listAllUserIds`<br>`POST /internal/user/listUserIdsByPage`<br>`POST /internal/user/listBriefByUserIds`<br>`POST /internal/user/countByJoinDate` |
| Simlect-user | [LocationController.java](Simlect-backend/Simlect-user/app/src/main/java/com/simlect/controller/LocationController.java) | `GET /location/resolve`<br>`GET /location/sync` |
| Simlect-user | [SignController.java](Simlect-backend/Simlect-user/app/src/main/java/com/simlect/controller/SignController.java) | `POST /sign/getSignCalendar`<br>`POST /sign/sign`<br>`POST /sign/msign` |
| Simlect-user | [SlideCaptchaController.java](Simlect-backend/Simlect-user/app/src/main/java/com/simlect/controller/SlideCaptchaController.java) | `POST /captcha/get`<br>`POST /captcha/check`<br>`POST /captcha/cancel` |
| Simlect-user | [UserAddressController.java](Simlect-backend/Simlect-user/app/src/main/java/com/simlect/controller/UserAddressController.java) | `GET /userAddress/loadDataList`<br>`POST /userAddress/addAddress`<br>`POST /userAddress/updateAddress`<br>`POST /userAddress/updateDefault`<br>`POST /userAddress/delAddress` |
| Simlect-user | [UserBrowseController.java](Simlect-backend/Simlect-user/app/src/main/java/com/simlect/controller/UserBrowseController.java) | `POST /userBrowse/loadBrowse`<br>`POST /userBrowse/clearBrowse`<br>`POST /userBrowse/removeBrowse` |
| Simlect-user | [UserBrowseHistoryController.java](Simlect-backend/Simlect-user/app/src/main/java/com/simlect/controller/UserBrowseHistoryController.java) | `POST /browseHistory/loadBrowse`<br>`POST /browseHistory/clearBrowse`<br>`POST /browseHistory/removeBrowse` |
| Simlect-user | [UserFavoriteController.java](Simlect-backend/Simlect-user/app/src/main/java/com/simlect/controller/UserFavoriteController.java) | `POST /userFavorite/loadFavorite`<br>`POST /userFavorite/toggleFavorite`<br>`POST /userFavorite/isFavorite`<br>`POST /userFavorite/removeFavorite` |
| Simlect-user | [UserMemberController.java](Simlect-backend/Simlect-user/app/src/main/java/com/simlect/controller/UserMemberController.java) | `GET /userMember/getProfile`<br>`GET /userMember/getMemberCenter`<br>`POST /userMember/getMemberCenter`<br>`GET /userMember/loadMemberCenter`<br>`POST /userMember/loadMemberCenter`<br>`POST /userMember/claimLevelReward`<br>`GET /userMember/getLevelBadge` |
| Simlect-user | [UserNotificationController.java](Simlect-backend/Simlect-user/app/src/main/java/com/simlect/controller/UserNotificationController.java) | `POST /userNotification/loadNotification`<br>`GET /userNotification/countUnread`<br>`POST /userNotification/markRead`<br>`POST /userNotification/markAllRead`<br>`POST /userNotification/deleteNotification`<br>`POST /userNotification/clearAll`<br>`GET /userNotification/getPopupNotification`<br>`POST /userNotification/clearPopupNotification` |
