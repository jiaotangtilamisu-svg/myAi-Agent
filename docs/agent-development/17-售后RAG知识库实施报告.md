# 17-售后 RAG 知识库实施报告

实施日期：2026-11-02。项目根目录：`E:\Simlect-AI-Mall-main\Simlect-AI-Mall-main`。

当前分支：`feat/agent-safe-advice-product-search`；HEAD：`14726bf267daf7a3ffb622f5f3dff92e427a2541`。本轮未提交 Git，保留此前商品搜索、退款隔离、订单归属及报告的未提交修改。

## 一、实际完成情况与边界

已完成文档导入和管理接口、解析与切分、审批发布、MQ 向量化、现有 ES 向量索引存储、带来源和版本核验的检索、LangGraph 集成及 Mock 回归测试。

本轮属于代码开发与隔离测试交付，**尚未部署到运行服务，也未完成真实数据库/MQ/ES 的售后文档联调**。没有执行新增 SQL，没有导入或发布任何正式售后政策，没有向现有索引写入测试样例，没有删除现有 FAQ。本报告中的“通过”均限定为下述自动化 Mock/单元测试范围。

没有修改真实 `.env`，没有启动、停止或重启服务，没有执行退款、支付、邮件操作，没有调用真实 LLM 或 Embedding API。

## 二、修改文件清单

以下路径均相对于上述项目根目录；“修改”是在现有内容上增量修改。

| 文件 | 类型及本轮内容 |
|---|---|
| `Simlect-backend/Simlect-search/pom.xml` | 修改；增加 PDFBox 3.0.7 解析 PDF，未升级其他生产依赖 |
| `Simlect-backend/Simlect-common/src/main/java/com/simlect/entity/enums/RagDataTypeEnum.java` | 修改；增加独立 `aftersales_policy` 类型，保留 FAQ/product |
| `Simlect-backend/Simlect-search/src/main/java/com/simlect/biz/KnowledgeDocumentParser.java` | 新增；PDF/DOCX/TXT 有界解析、章节识别、重叠切分、确定性分块 ID 和 SHA-256 |
| `Simlect-backend/Simlect-search/src/main/java/com/simlect/entity/po/KnowledgeDocument.java` | 新增；文档版本、审核、索引状态模型 |
| `Simlect-backend/Simlect-search/src/main/java/com/simlect/mappers/KnowledgeDocumentMapper.java` | 新增；参数化 SQL，文档行锁、修订历史、分页和当前版本读取 |
| `Simlect-backend/Simlect-search/src/main/java/com/simlect/biz/KnowledgeDocumentService.java` | 新增；草稿导入、更新、确认发布、软删除、重新向量化、当前发布目录和 MQ 同步 |
| `Simlect-backend/Simlect-search/src/main/java/com/simlect/controller/admin/KnowledgeDocumentController.java` | 新增；复用管理员会话鉴权，提供文档管理接口 |
| `Simlect-backend/Simlect-search/src/main/java/com/simlect/controller/internal/KnowledgeCatalogController.java` | 新增；内部当前有效文档目录，供 Python 核验 |
| `Simlect-backend/Simlect-search/src/main/java/com/simlect/component/RabbitMQRagListenerComponent.java` | 修改；复用现有 RAG 队列、消费幂等、重试/DLQ，增加政策类型分支 |
| `Simlect-backend/Simlect-gateway/src/main/resources/application.yml` | 修改；只增加 `/internal/knowledge/catalog` 到 `simlect-search` 的路由；现有管理路由覆盖 `/admin/rag/**` |
| `sql/08_aftersales_knowledge.sql` | 新增；两张独立文档/版本表迁移脚本，无样例 INSERT，未执行 |
| `Simlect-backend/Simlect-agent/app/config/settings.py` | 修改；政策独立默认 Top-K=5、分数阈值=0.75 |
| `Simlect-backend/Simlect-agent/app/rag/retriever.py` | 修改；保留 FAQ/商品方法，增加 `search_policy` 和当前目录/版本/正文哈希验证 |
| `Simlect-backend/Simlect-agent/app/rag/policy.py` | 新增；售后问题识别、结构化状态、证据引用式回答 |
| `Simlect-backend/Simlect-agent/app/graph/state.py` | 修改；增加本轮 `policy_result` 状态 |
| `Simlect-backend/Simlect-agent/app/graph/nodes.py` | 修改；政策问题检索入口、退款意图证据注入、确定性回答及安全记忆写入 |
| `Simlect-backend/Simlect-agent/app/services/agent_runtime.py` | 修改；政策上下文流式缓冲，最终移除未经证实的规则，保留原动作卡片安全链路 |
| `Simlect-backend/Simlect-search/src/test/java/com/simlect/biz/KnowledgeDocumentParserTest.java` | 新增；8 项解析/切分用例 |
| `Simlect-backend/Simlect-search/src/test/java/com/simlect/biz/KnowledgeDocumentServiceTest.java` | 新增；12 项版本/发布/向量写入/删除/失败用例 |
| `Simlect-backend/Simlect-search/src/test/java/com/simlect/component/PolicyRagConsumerTest.java` | 新增；2 项现有 MQ 接入/失败分支用例 |
| `Simlect-backend/Simlect-search/src/test/java/com/simlect/controller/admin/KnowledgeDocumentControllerTest.java` | 新增；3 项管理鉴权/文件大小用例 |
| `Simlect-backend/Simlect-agent/tests/test_aftersales_policy_rag.py` | 新增；38 项政策检索、来源验证、异常、意图、无模型编造和流式保护用例 |
| `docs/agent-development/17-售后RAG知识库实施报告.md` | 新增；本报告 |

未改写 LangGraph 拓扑、MCP Server、现有商品查询、退款执行保护或 Java 订单归属实现。售后检索沿用原 FAQ 的图节点直接调用 retriever 方式，没有另建微服务或重复新增 MCP 检索层。

## 三、核心实现

### 1. 文档处理与元数据

`KnowledgeDocumentParser.parse/split`：

- PDF：PDFBox 3.x，逐页提取，保留页码；拒绝加密/禁止提取文档。扫描件无文本时明确提示需要 OCR，不假装解析成功。
- Word：支持 DOCX，使用 JDK ZIP/XML 解析段落、表格单元格文本和标题样式；禁用外部实体/DTD，不执行宏、不拉取链接。旧版 `.doc` 明确拒绝，需先转换为 DOCX。
- TXT：支持 UTF-8、带 BOM 的 UTF-16LE/BE，以及 GB18030 回退。
- 按标题/章节和页边界分组，正文每块最多 800 个 Java UTF-16 字符单元，相邻块重叠约 120；优先使用换行/句号边界，避免割裂 Unicode 代理对。
- 保留 `chunkId/chunkIndex/section/page/start/end/text/sha256`。偏移是章节内字符偏移，DOCX/TXT 页码为 0，表示没有可靠分页。
- 上限：上传 10 MiB、PDF 200 页、提取文本 400000 字符、每文档 500 块；DOCX 限制 ZIP 条目、单条目和累计解压量。

原始二进制文件不落上传目录；数据库保存正文分块及修订历史，供重新向量化使用。

### 2. 管理与发布接口

管理前缀为 `/admin/rag/knowledge`，均为 POST，使用项目原有管理员 Token/Cookie 与 Redis 登录会话校验。

| 路径 | 主要参数 | 作用 |
|---|---|---|
| `/import` | multipart `file/title/source`；更新时另传 `documentId/expectedRevision` | 导入或更新为 DRAFT，不触发 Embedding |
| `/list` | `page/size` | 分页，单页最多 50 |
| `/detail` | `documentId` | 查看当前元数据与分块 |
| `/publish` | `documentId/revision/confirmedPolicy=true` | 管理员明确核实来源和正文后发布 |
| `/reindex` | `documentId/revision` | 对已经确认的当前版本重新向量化 |
| `/delete` | `documentId/revision` | 软删除并排队清理该文档的向量 |

本轮提供后端管理 API，没有新增后台上传页面。实际政策内容需由用户确认后再导入和发布；测试文件只存在于测试夹具中，均明确标注 TEST ONLY。

### 3. 版本、MQ 与 ES

状态流程：`DRAFT → 显式确认 → INDEXING → READY`。更新增加版本并重新变为 DRAFT；删除变为 DELETED。

`KnowledgeDocumentService.enqueue` 在数据库事务提交后，通过现有 `ReliableMessageSender`、RAG exchange/queue 发送 `aftersales_policy` 消息。`RabbitMQRagListenerComponent.handleRagData` 新分支调用 `synchronize`，复用已有失败记录、重试和 DLQ。

`synchronize` 使用已有 Spring AI `VectorStore`，因此仍由现有 EmbeddingModel 生成向量，写入现有 `simlect_vectorstore` 配置索引，不另建向量服务。ES 元数据包括文档 ID、版本、名称、文件名、章节、页码、来源、分块 ID、哈希、类型及确认标记。

新版本全部 `add` 成功后才删除本文件旧版本向量；删除只使用数据库记录中的该文件分块 ID，不执行清空索引或按类型批量删除，也不接触 FAQ 向量。确定性分块 ID 支持同版本重试覆盖。

向量化/ES 写入失败时不能进入 READY，仍停留 INDEXING；需要查看既有 MQ 失败管理并重试/重新向量化。没有实现独立 FAILED 状态。数据库和 ES 不是分布式事务：失败可能留下部分无效向量，但目录核验会拒绝把它们用于回答。

### 4. 检索与来源核验

`RagRetriever.search_policy` 复用 `embed_text`、现有 ES 连接与熔断器，限定 `metadata.dataType=aftersales_policy`，不混入普通 FAQ。

- Top-K 默认 5，允许 1～20；过召回候选最多 80，按 ES 分数排序、去重，过滤低于默认 0.75 的结果。该分数不是“可信概率”，阈值需后续用真实政策评测校准。
- 检查向量维度、有限数值及非零向量。
- 经 Gateway 使用原内部 Token 调用 `/internal/knowledge/catalog`，每批最多 50 个文档。
- Java 只返回已确认、READY 且 `indexedRevision==revision` 的当前目录。
- Python 再核对当前版本、分块 ID、正文 SHA-256；文档名、来源、章节与页码来自权威目录，不信任 ES 中同名展示字段。
- 旧版本、已删除、未确认、索引未完成及正文被篡改的结果均不成为证据。损坏的目录/元数据也不会被当作有效政策。

返回结构示意（仅结构，不表示正式政策）：

```json
{
  "status": "SUCCESS",
  "hits": [{
    "documentId": "<UUID>", "revision": 1, "chunkId": "<UUID>",
    "documentName": "<已确认文档名称>", "filename": "<文件名>",
    "section": "<章节>", "page": 1, "source": "<可追溯来源>",
    "text": "<经哈希核对的原文片段>", "score": 0.9
  }]
}
```

异常状态分别为 `NO_MATCH`、`LOW_RELEVANCE`、`EMBEDDING_FAILED`、`ES_UNAVAILABLE`、`CATALOG_UNAVAILABLE`，均有明确用户提示；不把查询失败当成无匹配。

### 5. LangGraph 与可信回答

`build_context_node` 对明确的纯政策问题直接检索，绕开 LLM 意图分类和无关商品/订单查询；REFUND 业务意图也会获取政策证据。“我的订单退款状态”等订单查询保留原业务链路。

`agent_loop_node` 对纯政策问题不调用 LLM，直接引用确认后的片段，并附文档名、章节、页码、来源、版本和分数。引用每一行都标记为引文，正文不是可执行指令。

退款上下文的模型文本先缓冲，`finalize_agent_response` 丢弃未经证实的规则，只保留安全建议、可验证政策引文和原有动作卡片解析。无命中/低相关度/依赖失败时不输出模型补全的售后规则。记忆模块也只写入该安全回答。

普通闲聊、商品事实保护、退款执行阻断、已验证用户身份和订单归属链路继续保留。此处只检索依据和提出建议，不代表判定具体订单一定具备退款资格。

## 四、测试环境与真实结果

使用已有独立 Python 3.12.0 测试环境、JDK17/Maven。Python 在独立测试工作目录运行，使用虚拟密钥与 `.invalid` 模型地址，隔离真实 `.env`。HTTP/Embedding/ES/业务访问使用 Mock，并使用既有禁止外部网络的测试钩子；Java 测试使用既有 NoNetworkSecurityManager。所有测试文件、临时目录、依赖及日志保存在 E 盘。

| 范围 | 通过 | 失败/错误 | 跳过 |
|---|---:|---:|---:|
| Python 全量现有 tests（含本轮新增 38 项） | 262 | 0 | 0 |
| Java Common | 229 | 0 | 0 |
| Java Gateway | 41 | 0 | 0 |
| Java Search（含本轮新增 25 项） | 94 | 0 | 0 |
| Java Product app | 116 | 0 | 0 |
| Java Stock app | 39 | 0 | 0 |
| Java Order app | 344 | 0 | 0 |
| Java Pay app | 65 | 0 | 0 |
| **Java 本轮所选模块合计** | **928** | **0** | **0** |

Java 命令选择 `Simlect-search,Simlect-gateway,Simlect-product/app,Simlect-stock/app,Simlect-order/app,Simlect-pay/app -am test`，离线执行，结果 BUILD SUCCESS。未将未在本次 reactor 中执行的旧 Admin/User 报告计入统计。

Ruff：新增 `policy.py` 与新测试文件全规则通过；修改的 retriever/nodes/state/runtime 按 E9、F63、F7、F82 检查通过，未自动修复原项目全局遗留告警。Python 有既有 MCP 客户端弃用提示及 pytest-asyncio loop-scope 提示，非测试失败。本轮无前端文件修改，没有重复运行前端构建，不将此前构建结果冒充本轮测试结果。

新增测试覆盖：正常 TXT/PDF/DOCX 导入、编码、章节/切分/重叠、XXE 拒绝、扫描件提示、超限；发布必须显式确认、修改后撤销确认、乐观版本冲突、MQ 分发/失败；VectorStore Mock 写入元数据及顺序、Embedding/ES 写失败不先删除旧向量；文档更新、软删除及受限清理；多文档 Top-K、来源保留、低相关度、无匹配、无效向量、ES 404/503/熔断、目录失败/损坏、过期/删除/正文篡改拒绝；售后意图触发、绕开分类器、工具完成前不提前输出规则、拒绝模型编造“999天”规则。

首轮执行曾出现测试夹具问题：Python 新测试缺少 Redis Mock；Java 新测试在 Mockito stubbing 内调用 Spy 构造样例。已仅修正本轮测试夹具后重跑，以上为最终结果，不隐藏首轮失败。测试没有调用真实退款接口；原退款安全、订单归属和商品搜索测试随全量回归通过。

测试证据目录：`.cache/aftersales-rag-20261102/results/`：

- `python-final.log`、`python-final.xml`：最终 262 项结果。
- `java-final.log`：本轮 Maven 执行日志；`java-summary.json`：所选模块统计。
- 对应 Java XML：各模块 `target/surefire-reports/TEST-*.xml`。

本轮修改已有文件前的备份位于 `.cache/aftersales-rag-20261102/before/`；其他此前未提交修改未覆盖、未清理、未重置。

## 五、尚未完成与后续验收

1. **真实部署未验证**：新增表迁移未执行；需审核 `sql/08_aftersales_knowledge.sql` 后仅创建独立文档表，再构建并受控加载 Search/Gateway/Agent 新代码。当前运行服务不因此自动获得本轮功能。
2. **正式政策未确认**：需用户提供并确认真实文档、来源和适用范围。无真实政策时应返回无依据提示，不发布测试夹具。
3. **真实 Embedding/MQ/ES 联调未执行**：需另行明确授权真实 Embedding 消耗，再验收导入草稿不请求模型、确认发布才向量化、异步 READY、检索来源、更新/删除后旧版本即时失效和重试行为。不要清空索引或删除既有 FAQ。
4. **管理界面未新增**：本轮以管理 API 实现导入/更新/删除/重建；后续可在原后台增加页面，复用现有鉴权。
5. **格式范围**：不提供 OCR、旧版 DOC 或复杂版面还原。PDF 跨页章节继承、DOCX 非正文附件和精确页码不保证；扫描件/旧 DOC 有明确拒绝提示。
6. **意图与召回需要真实语料评测**：当前关键词规则覆盖常见政策问法，不能宣称覆盖全部自然语言表达；阈值、块长和候选数需根据确认后的政策评测。过召回后大量旧版本候选可能降低召回率，但不会放宽版本/哈希检查使用旧政策。
7. **可用性取舍**：更新即撤销旧版本可检索资格；索引或目录不可用时宁可明确无法核实，不回退到可能过期的规则。批量长文档向量化会在事务内持有文档行锁，后续应按实际延迟评估处理批次和超时。

本轮停止在代码和 Mock 测试交付点，等待审核；不自动执行 SQL、不部署服务、不导入正式政策、不提交 Git。
