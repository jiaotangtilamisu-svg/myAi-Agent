# 第27阶段：RAG与售后Agent端到端验收报告

更新日期：2026-11-03（Asia/Shanghai）。本报告取代审核前的待审批版本；旧报告保存在 `.cache/stage27/reports-before-final/`。用户已明确批准本法规审核发布及限定真实 API 验收。

## 实际调用链

Admin原文上传 → KnowledgeDocumentParser → 版本与Chunk → 用户确认后审核发布 → RabbitMQ既有向量化消费者 → 分批text-embedding-v4 → 原ES索引。

商城已登录用户发送 → 原异步消息接口保存messageId → LangGraph专业Agent / Supervisor调度 → RAG问题Embedding → ES向量召回 → 经Gateway访问Java已发布政策目录 → 版本/有效期/哈希复核 → 原文证据 + 受约束DeepSeek辅助 → 保存回复 → WebSocket/消息轮询 → 聊天页展示。

购物分支保持MCP → Gateway → Product → Stock真实业务查询。RAG直接检索不虚构MCP工具调用。Supervisor模型负责的部分复用专业Agent；路由/汇总保留原确定性逻辑，没有声称Supervisor每个节点都调用模型。

## 四题真实RAG验收

| 序号 | 问题 | 状态/命中数 | 最高相关度 | 首命中位置 |
| --- | --- | --- | ---: | --- |
| 1 | 消费者权益保护法实施条例主要适用于哪些消费场景？ | SUCCESS / 5 | 0.867792 | 第一条 |
| 2 | 经营者在提供商品或服务时有哪些基本义务？ | SUCCESS / 5 | 0.839111 | 第二章 |
| 3 | 消费者权益受到侵害时有哪些相关规定？ | SUCCESS / 5 | 0.865566 | 第三章 |
| 4 | 经营者能否通过格式条款不合理限制消费者权利？ | SUCCESS / 5 | 0.891825 | 第十七条 |

4/4均经真实Embedding和ES命中本法规，返回版本1、官方URL、章节/条款、来源、score。每个Chunk都与Java已发布有效目录/版本/正文哈希一致；目录不可用时拒绝使用结果。停用后NO_MATCH/0条，重新启用后SUCCESS/5条，2/2通过。

这里的“4/4通过”指真实召回和来源/有效状态契约，不代表法律问答准确率100%。宽泛问题首命中可能为章节标题；第4题首命中第17条。未构建人工标注全集、未对召回完整性和每条语义精度做统计，不用这些score代替法律结论。当前仅接入本实施条例，不能用模型记忆补齐被引用法律。

## 真实售后与Supervisor场景（保留全部尝试）

| 消息ID | 模式/场景 | 真实结果与验收判断 |
| --- | --- | --- |
| 23 | 售后：超过七天能否退货 | RAG SUCCESS、第18条；真实DeepSeek返回usage，回复已保存。发现最终回复层丢失补充事实提示，原次完整性仅部分通过，已修复 |
| 24 | 售后：终身保修、免费退换承诺 | LOW_RELEVANCE，明确不能确认；没有编造商城承诺，没有为无依据场景强行调用模型；拒绝编造通过 |
| 25 | Supervisor普通售后 | 仅售后Agent；SUCCESS/COMPLETE，保留第18、19条和来源、明确国家法规不是商城承诺及所需事实；通过 |
| 26 | Supervisor商品推荐 | 仅导购Agent，真实MCP两工具成功，返回最多3款业务库演示商品及SKU/价格/库存；通过 |
| 27 | Supervisor复合首次 | 两Agent完成查询，但导购NO_MATCHING_SKU，错误关键词过滤；未满足商品推荐预期，不算通过 |
| 28 | 同复合任务第一次复验 | 关键词已修复，但旧购物上下文残留错误“库存状态”SKU属性导致无推荐；仍不算通过 |
| 29 | 同复合任务最终复验 | 两Agent SUCCESS，政策MODEL_GROUNDED，导购真实商品3款，COMPLETE；页面与持久化均核验，通过 |
| 30 | 售后模式修复后复验 | RAG SUCCESS；DeepSeek流式超时，摘要503；回复终结、保存并展示“模型辅助分析暂不可用”和原文。失败降级通过，正常模型路径本次未通过 |

原定两售后与三Supervisor不同场景均已执行；共8条真实消息，额外3条为上述缺陷复验，没有新增其他收费场景。最终8条均终结status=2且有持久化回复；status=2/HTTP200不代表每次模型成功或符合验收，必须按上表解释。原失败历史未删除。

消息29最终返回本地验收茶杯白色SKU12.30元/库存7、演示帆布包69元/库存100、演示保温杯89元/库存100。未知价格商品没有被当作预算内推荐，库存缺失没有转为0；同茶杯黑色SKU库存0未作为有货推荐。使用场景缺少属性时仍提示待确认。价格和库存为当时查询值，不是价格保证或真实商业销售证明。

## 工具、上下文与证据

商城UI逐个提交问题，未从Redis/浏览器读取用户会话Token。完成后只读查询本轮消息和Supervisor结果；保存的structured结果包含独立plan、results.aftersales、results.shopping、指纹和executionAllowed=false。消息25只有售后、26只有购物、29两个专业Agent，证明不是无条件双调用或只返回路由判断。

消息26、27、28、29各有SEARCH_PRODUCTS、GET_PRODUCT_DETAIL两条真实shopping_tool_result日志，共8条，query_status=SUCCESS，批量返回8个商品；业务查询成功与筛选得到推荐严格区分。购物工具路由仅接受MCP返回的schemaVersion2结构，失败不重新查询来冒充MCP成功。MCP独立7060进程健康；这8条是Agent侧实际工具结果记录，不冒充独立网络抓包或新增协议级全量审计。

RAG政策证据和产品事实保存在各专业结果中，再统一展示，不合并为同一业务字段。购物旧上下文错误库存属性已在服务端校验；颜色等合法要求保留。上下文跨用户隔离/越权/退款隔离有本轮全量Mock回归，本轮未用第二个真实用户追加收费测试，也未再次修改或查询真实订单。既有演示订单保持4条，不创建虚假订单。

## 已修复的真实运行问题

- ES字段与精确元数据路径不匹配：修复Python兼容现有索引，保留全部原数据。
- Gateway旧JAR缺政策目录路由：加载源码已有配置，首次404按失败计，不绕过目录认证。
- 模型分析经过工作流但最终层仅返回引用：传递受约束分析结果至最终回复和Supervisor汇总；模型不得输出任意法律承诺。
- “推荐300元以内……且有库存”被当字面商品名及模型库存属性污染旧会话：最小解析和状态校验修复；实际复验由无推荐变为3款，不用假数据填补。

## 尚未完成、风险和后续

1. **独立售后模式修复后的正常DeepSeek路径仍需服务恢复后再验一次。**消息30外部超时/503已经记录，当前没有继续重试；不能以Mock通过或Supervisor成功替代这项独立运行验收。失败请求usage未知，账单不能精确归零。
2. 只有1份国家法规，商城自有规则仍无经审核内容；依法可退、商品范围、期限等必须结合真实事实及补充法律，不能承诺必退。没有把国家法规改写成商城规则。
3. 宽泛问题可能优先召回章标题，未做标注集精度评估；后续可在授权范围内做召回质量优化，本轮不追加模型、语料或索引重建。
4. 本次真实联调是同一已有演示用户；多用户、并发、长时间模型稳定性只有已有自动化覆盖或尚未验证，不声称生产可用。
5. 未运行真实支付、退款、下单、邮件，也没有真实企业ERP/OMS/WMS数据验收；既有安全边界仍在。

## 本阶段修改文件与作用

以下均相对项目根目录；本轮没有覆盖其他阶段的既有修改。

| 文件 | 增量内容 |
| --- | --- |
| `Simlect-backend/Simlect-search/src/main/java/com/simlect/biz/KnowledgeDocumentService.java` | 现有VectorStore按最多10条分批；同版本READY重复消息跳过，仍复用原MQ、Embedding和固定Chunk ID |
| `Simlect-backend/Simlect-search/src/test/java/com/simlect/biz/KnowledgeDocumentServiceTest.java` | 61块/7批及READY去重Mock回归 |
| `Simlect-backend/Simlect-search/src/main/java/com/simlect/component/EmbeddingUsageObserver.java` | 仅记录模型、条数、维度、usage、结果，不记录请求正文/向量/凭据 |
| `Simlect-backend/Simlect-search/src/test/java/com/simlect/component/EmbeddingUsageObserverTest.java` | usage缺失时仍安全观测 |
| `Simlect-front/Simlect-admin/src/views/setting/PolicyCenter.vue` | Word无固定页码时不展示虚假的“第0页” |
| `Simlect-backend/Simlect-agent/app/rag/retriever.py` | 对齐真实ES映射：向量字段embedding，元数据精确字段使用.keyword；保留发布目录/版本/哈希/有效期验证 |
| `Simlect-backend/Simlect-agent/tests/test_aftersales_policy_rag.py` | 真实映射对应的检索请求断言 |
| `Simlect-backend/Simlect-agent/app/rag/embedding.py` | 记录供应商返回的真实usage，不泄露内容和Key |
| `Simlect-backend/Simlect-agent/app/services/model_usage.py` | LangChain回调观测成功usage及错误类型 |
| `Simlect-backend/Simlect-agent/app/services/llm_factory.py` | 复用现有模型配置，挂载usage回调并请求流式usage |
| `Simlect-backend/Simlect-agent/tests/test_model_usage.py` | 供应商usage结构及缺失值测试 |
| `Simlect-backend/Simlect-agent/app/rag/advice.py` | 真实LLM仅选择已验证Chunk ID与限定的补充事实字段；拒绝多余字段、伪造来源及执行指令；结论由固定安全文案和原文引用组成 |
| `Simlect-backend/Simlect-agent/app/graph/nodes.py`、`app/graph/state.py` | 在原政策分支中执行受约束模型辅助分析，保留引用与状态；不重写LangGraph |
| `Simlect-backend/Simlect-agent/app/services/agent_runtime.py` | 最终WS/持久化回复保留经过校验的补充事实提示，不再仅保留引用 |
| `Simlect-backend/Simlect-agent/app/supervisor/adapters.py`、`app/supervisor/aggregation.py` | 将政策辅助状态传递并在汇总中展示，不丢失政策和商品事实 |
| `Simlect-backend/Simlect-agent/tests/test_policy_advice.py` | 6项模型证据/伪造字段/失败降级测试，1项最终WS与持久化文本一致测试 |
| `Simlect-backend/Simlect-agent/app/shopping/requirements.py`、`app/shopping/extraction.py` | 修正“且有库存”被误当商品名；阻止库存/价格等业务字段成为模型生成的SKU属性，并校验旧会话中的错误属性；保留颜色等规格 |
| `Simlect-backend/Simlect-agent/tests/test_policy_shopping_acceptance.py` | 2项真实验收发现问题的回归，包含旧上下文校验与显式关键词保留 |

辅助采集、临时启动核验和结果文件在 `.cache/stage27/`，不包含账号、密码、Cookie或Token。源码修改前副本在 `.cache/stage27/before/`。没有修改真实.env，没有重写RAG、MCP、Supervisor或专业Agent。

## 自动化测试（与真实 API 验收分开）

| 范围 | 通过 | 失败/错误 | 跳过 | 性质 |
| --- | ---: | ---: | ---: | --- |
| Python Agent + 数据治理 | 539 | 0 | 0 | Mock/隔离网络回归；保留1项既有MCP客户端弃用警告 |
| Java Common | 229 | 0 | 0 | 单元/Mock |
| Java Search | 120 | 0 | 0 | 单元/Mock |
| Admin Node | 11 | 0 | 0 | 本阶段审核前执行；前端修改后生产构建通过 |

Python最终证据：`python-acceptance-restored.xml/log`；Java：`java-approved-tests.log`、`java-final-summary.json`；Admin：`admin-tests.log`、`admin-build.log`。Java合计349，未声称本轮重跑全项目全部Java测试。Python测试期间禁止真实外部API；这些数量不能当真实模型调用数。

## 最终服务状态

| 服务 | 端口 | 实际PID | HTTP / status |
| --- | ---: | ---: | --- |
| gateway | 8080 | 12272 | 200 / UP |
| order | 8093 | 5620 | 200 / UP |
| product | 8099 | 31092 | 200 / UP |
| stock | 8102 | 32800 | 200 / UP |
| user | 8105 | 24012 | 200 / UP |
| admin | 8111 | 152 | 200 / UP |
| search | 8108 | 15036 | 200 / UP |
| mcp | 7060 | 9448 | 200 / ok |
| agent | 7050 | 13368 | 200 / ok |

Agent的java_web=true、status=ok。进程创建时间、父PID、可执行路径和命令行保存在 `final-processes.json`；最终HTTP证据为 `final-health.json`。仅为本轮时点健康，不冒称新的15分钟持续运行验收。

为加载已批准的兼容修复，先备份后重载了Search、MCP和Agent；实际发现Gateway旧JAR缺少已有的政策目录路由后，仅重载这一必要依赖。Gateway现PID12272，旧PID17164已替换。Order、Product、Stock、User、Admin未被本轮重启。没有重启Docker或中间件。

Gateway首轮离线打包因Windows锁定运行JAR而失败；备份日志/JAR、核对身份并停止该服务后，打包成功，再使用原 `deploy/run-configured.ps1 -Stage Java -Service gateway` 启动。未修改路由源码；不能将这次失败隐去。

## 数据与安全边界

没有新增数据库结构迁移。导入前10库备份：`.cache/stage27/database-backup/before-governance.sql`，136958字节，SHA-256 `806b3aa0950d4d84554ea09c25baab125ad9ae525fd1979545bc1cd2172fe5ce`。审核发布前另备份 `.cache/stage27/approved-database-backup/before-governance.sql`，247119字节，SHA-256 `c9af01576816a70de45239d54b19a8b19f6b195ef78e4d7bf434305dfa5022ab`。

导入、提交审核、通过、发布、停用及启用均走现有Admin权限和业务接口，没有直接SQL伪造审批。用户自行登录，本轮没有读取/导出会话凭据；商城问题通过该已登录页面发送，完成后只读核验本轮消息及结果。

最终商品12、SKU13、库存12、订单4，与前值一致；这些是演示/验收记录，不是企业真实商业数据。数量不变本身不证明每一字段未变，本轮也没有调用它们的写接口。只新增本法规及其版本/Chunk/审计、正常聊天记录/记忆和向量；未删除FAQ、未清空索引、未执行支付/退款/下单/邮件，退款隔离和人工审批继续保留。未提交Git。

结论：法规发布、61块真实向量、4题RAG、停用/启用以及3种Supervisor路由/复合场景已验证。独立售后模式最终正常模型复验受外部故障阻塞，安全降级已验证。完成本轮并暂停，不自动进入下一阶段。


## 后续超时复核与测试范围澄清

2026-11-03：已分析消息30原始日志，并完成最小源码修复及Mock回归：Python552项通过；随后政策专项20项通过（包含于552，不重复相加）。本轮真实API调用0、未重载服务，修复后真实运行等待一次受控授权。原阶段成功/失败运行记录及计费数据不变。

Java349仅Common229+Search120专项，第26阶段1034为选定8模块；其余6模块688项本次未重跑，Search新增3项。本轮未新增执行Java测试，不能把专项或历史结果写成当前全量回归。详见[超时归因与最小修复报告](./27-DeepSeek超时与503归因及最小修复报告.md)。


## 单次受控真实运行最终补充（2026-11-03）

仅重载Agent，新PID13976，其他服务保持原PID。本次仅新增独立售后消息31；问题Embedding1次成功、36 Token；DeepSeek1次HTTP200响应头后整体辅助20.797秒TimeoutError、usage未知，无自动重试或额外模型摘要，61个文档向量未重新处理。

同时发现biz_data VARCHAR(2000)写入5段结构化证据失败（MySQL1406）。2307字降级原文已保存、status=2，但biz_data为null，当前页面显示服务暂时不可用。因此本次真实端到端验收**未通过**，不能用HTTP200/status=2、Mock通过或Agent健康替代成功。已停止，不追加真实调用，也未修复新发现的持久化问题。

本次仅22项Python政策专项Mock预检通过；未新增执行Java/前端测试。此前Java349仅Common+Search专项；第26阶段1034为选定8模块，不是全仓集成测试。本次结果和费用单独记录，不改写原阶段历史成功/失败及Token记录。

详情见[27-单次受控真实API验收结果.md](./27-单次受控真实API验收结果.md)。
