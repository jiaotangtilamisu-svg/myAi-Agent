# 第26阶段：RAG政策接入与测试报告

日期：2026-11-03，Asia/Shanghai。

本轮基于`feat/agent-safe-advice-product-search`的既有未提交成果增量修改。未reset、clean、提交或推送；真实.env、Gateway配置和数据库业务行未被本轮修改。第25阶段报告保留。
工作目录为`E:/Simlect-AI-Mall-main/Simlect-AI-Mall-main`，以下源码路径均相对此目录。备份、测试缓存及日志均在E盘。

## 原链路上的增量治理

Admin人工上传原文 → 原KnowledgeDocumentParser解析PDF/DOCX/TXT → 原切分器生成有章节/页码与SHA-256的块 → 草稿及版本、原始字节、来源元数据持久化 → 提交审核 → 管理员审核 → 人工发布 → 既有可靠MQ → 原RAG消费者/Embedding/VectorStore → 原ES索引 → 索引版本就绪 → LangGraph售后检索。

未新建ES索引、删除索引或重建RAG。向量写入仍先add成功后才清理同文档旧块，未全量清空；文档停用不删除原文或历史。保留现有失败重试/DLQ/失败记录入口及人工reindex；Mock覆盖Embedding失败后同审核版本重试成功。

## 检索安全契约

1. ES knn先按aftersales_policy与类别过滤，默认仅LAW/PLATFORM_DEMO；显式类别才允许行业参考。
2. 向量候选必须再次查询Java权威catalog；必须PUBLISHED、审批版本一致、sourceStatus=VALID、UTC有效期覆盖当前时刻、indexState=READY且indexedRevision=revision。
3. Python独立检查类别、来源状态和时区明确的有效区间；无治理元数据、旧版本或不可信分块SHA不予引用，绝不让旧向量自行授予发布资格。
4. 引用保留文档名、版本、章节、页码、source、issuer、originalUrl、发布日期及有效期；售后诊断evidenceSources同步携带这些字段。平台演示/行业参考在回答中明确标注，行业参考不自动成为商城办理依据。
5. 未命中、低相关度、Embedding失败、ES不可用及目录服务异常保留原有不同状态；无依据时确定性回答无法核实，不补造政策。

## 修改文件

- `Simlect-backend/Simlect-search/src/main/java/com/simlect/biz/PolicyRules.java`：集中治理资格规则。
- `Simlect-backend/Simlect-search/src/main/java/com/simlect/biz/KnowledgeDocumentService.java`：版本原文与审计、状态机、有效期catalog、原向量同步与恢复。
- `Simlect-backend/Simlect-search/src/main/java/com/simlect/controller/internal/KnowledgeCatalogController.java`：可选类别查询，继续内部认证机制。
- `Simlect-backend/Simlect-agent/app/rag/retriever.py`：ES分类过滤、权威目录与本地有效期校验、来源字段保留。
- `Simlect-backend/Simlect-agent/app/rag/policy.py`：资格检查、分类与出处展示。
- `Simlect-backend/Simlect-agent/app/services/aftersales_diagnosis.py`：结构化来源字段不丢失。
- 对应Java PolicyGovernanceTest/KnowledgeDocumentServiceTest/KnowledgeDocumentControllerTest与Python test_policy_governance.py/test_aftersales_policy_rag.py。

## 测试结果

| 范围 | 通过 | 失败/错误 | 跳过 | 证据 |
| --- | --- | --- | --- | --- |
| Python全量（含ETL） | 528 | 0 | 0 | results/python-release.log、XML |
| Java选定8模块 | 1034 | 0/0 | 0 | results/java-release.log、search-release.log、java-summary.json及各模块JUnit XML |
| Admin Node测试 | 11 | 0 | 0 | results/admin-tests-final.log |
| 商城Node测试 | 22 | 0 | 0 | results/shop-tests-final.log |
| 运行态断言（不是单元测试） | 20 | 0 | 0 | results/runtime.json |


| Java模块 | 测试数 | 失败 | 错误 | 跳过 |
| --- | --- | --- | --- | --- |
| Simlect-common | 229 | 0 | 0 | 0 |
| Simlect-gateway | 41 | 0 | 0 | 0 |
| Simlect-product/app | 122 | 0 | 0 | 0 |
| Simlect-stock/app | 39 | 0 | 0 | 0 |
| Simlect-search | 117 | 0 | 0 | 0 |
| Simlect-order/app | 390 | 0 | 0 | 0 |
| Simlect-pay/app | 65 | 0 | 0 | 0 |
| Simlect-cart/app | 31 | 0 | 0 | 0 |


所有单元测试使用Mock/测试夹具。Python从独立测试环境、独立工作目录运行，使用假凭据和网络阻断；Java离线Maven与NoNetworkSecurityManager阻断外部网络，真实退款、支付、邮件、LLM和Embedding均未调用。Java统计是全量选定模块回归与随后Search受影响模块复跑的去重最终JUnit结果，不将同一Common测试重复相加；不是全仓所有微服务的完整集成验收。
Admin生产构建通过；商城`npm run build`包含vue-tsc类型检查与生产构建，通过。Admin为JS项目，未虚构独立TypeScript脚本。日志目录均相对于`.cache/stage26/`。
开发中遇到的新测试注入错误、临时加载脚本解析错误和咨询卡片null类型错误均已修正后复跑；这些初次失败日志保留，不伪称始终一次通过。Java曾在新ProductReadContractTest中因泛型Mock注入不匹配出现3项错误，修正为类型明确的Mock后最终0失败/错误；商城曾因旧AgentConsultProduct类型不接受null构建失败，已扩展类型并通过最终构建。
新独立Python工具/测试及策略文件Ruff F/E9检查通过；扩展检查发现retriever.py已有未使用json导入F401，与修改前备份一致，本轮未清理该遗留问题。

重点覆盖：版本冲突、未审核不能发布、过期/未来/来源无效不检索、停用排除、恢复有效/过期/审批旧版、行业参考分离、官方来源字段、管理员权限、客户端伪造actor无效、保留原始文件和历史、向量写失败不删除旧数据、同版本重试恢复、ES候选返回但catalog失效时仍拒绝引用。测试样例为TEST ONLY，不写正式库。

## 真实运行验收与尚未验证

20条运行态断言全部通过，证据`results/runtime.json`。其中验证的是已部署Java/MySQL商品数据契约、页面/资源访问、匿名管理权限与数量保持，**不是20条真实政策RAG端到端验收**。
真实政策文档仍0，未发生审核发布或真实Embedding/LLM请求。RAG端到端的正式内容召回、真实Embedding耗时/失败、用户登录后的政策页面操作仍尚未验证。政策类别/有效期/停用的状态机与检索测试是Mock验证，明确不混为真实政策上线结果。

## 实际加载与运行状态

| 服务 | 端口 | 原PID | 当前PID |
| --- | --- | --- | --- |
| gateway | 8080 | 17164 | 17164 |
| order | 8093 | 5620 | 5620 |
| product | 8099 | 10012 | 31092 |
| stock | 8102 | 25048 | 32800 |
| search | 8108 | 29216 | 30104 |
| mcp | 7060 | 19908 | 33276 |
| agent | 7050 | 23960 | 9896 |
| admin | 8111 | 152 | 152 |
| user | 8105 | 24012 | 24012 |


仅重载Stock→Product→Search→MCP→Agent。Gateway、Order、User、Admin保持原PID，6001/6002 Vite无需重启而加载源码变化。Java服务历史日志和JAR在`.cache/stage26/reload/before-*`，Python原日志在`before-python-*`。使用现有`deploy/run-configured.ps1 -Stage Java -Service stock/product/search`分别启动（分别执行，不是字面含斜杠参数），Python使用原有`scripts/local/start-mcp.ps1`、`start-agent.ps1`由隐藏独立PowerShell进程启动。新日志见`logs/local-run/`与`logs/independent-services/`及`results/*launcher*.log`。
隐藏Java进程无可关闭的主窗口，核验模块路径、PID及创建时间并备份后定向Stop-Process，再单次启动，未宣称该停止方式是应用层优雅排空。未反复重启失败服务，未重启Docker或中间件。Maven打包步骤使用-DskipTests，测试结果来自前面的真实test步骤，不把打包当作测试。
当前Gateway、Order、Product、Stock、User、Admin、Search健康HTTP200/UP；MCP、Agent HTTP200/ok，Agent的java_web、redis、mysql、elasticsearch均true。RAG队列在Search加载前为0，未投递任何试验消息，未触发真实Embedding。加载新服务不等于完成新一轮15分钟跨任务存活验收；本轮没有声称长期持续运行测试通过。


## 后续人工验收

管理员在`/admin/setting/policies`提供可追溯原文；平台演示规则明确标注，官方法规及行业参考分别分类。保存草稿→核对元数据与UTC有效期→提交审核→人工核实来源并审核通过→单独确认发布。获得真实Embedding调用授权后观察MQ/索引READY和版本一致，再验证RAG引用、停用即时排除、重新启用。全过程无需真实订单、支付或退款。
