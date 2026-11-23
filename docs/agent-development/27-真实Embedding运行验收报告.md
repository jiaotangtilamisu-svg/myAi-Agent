# 第27阶段：真实Embedding运行验收报告

更新日期：2026-11-03（Asia/Shanghai）。本报告取代审核前的待审批版本；旧报告保存在 `.cache/stage27/reports-before-final/`。用户已明确批准本法规审核发布及限定真实 API 验收。

## 真实调用与向量写入

使用既有配置text-embedding-v4、1024维，不硬编码或输出Key。Search复用原MQ消费者、EmbeddingModel和Elasticsearch VectorStore，只有该已审核版本获准向量化。

维度探测1次（1个输入、3 Token）；文档61块分为10、10、10、10、10、10、1，共7批。文档7批usage分别为387、898、826、415、405、759、18，总计3708 Token。含探测合计3711 Token、8个成功usage观测。61个正式向量与探测向量区分，探测不作为政策Chunk入库。

停用和启用前后，文档向量化仍是这7批，ES仍为61个唯一Chunk，哈希不变；没有点击重新向量化。READY同版本幂等性另有Mock测试，没有为测试主动追加一次收费向量化。

## 查询侧真实消耗

| 类别 | 观测成功响应数 | 已返回的Token |
| --- | ---: | ---: |
| 维度探测 + 文档7批 | 8 | 3711 |
| 四题/停用启用及首次Gateway404查询 | 7 | 80 |
| Agent/MCP检索（含失败场景、复验） | 8 | 96 |
| Embedding已观测合计 | 23 | 3887 |

文档向量化3708 Token与问题检索Token分别计算，不能说整阶段只花3708。首次检索虽然最终因Gateway404失败，已成功生成问题向量，13 Token也计入，不隐瞒失败消耗。

DeepSeek成功usage观测10次，已返回usage合计8811 Token，包含受约束政策分析、购物需求解析及原有异步会话摘要。流式回调的model字段部分未返回，但工厂沿用已配置deepseek-flash，未另换服务。没有把摘要调用算成额外的独立验收场景。

最终售后复验出现StreamChunkTimeoutError；随后摘要调用OpenAIAPIError，运行日志显示HTTP503/服务繁忙。两次错误无有效usage，不填0冒充免费；因此8811仅是已知成功响应Token，不是供应商最终账单或全部实耗。SDK内部重试次数未通过独立逐请求记录完全证实，不声称为零；没有再手动重试这个外部故障。

## 运行发现的问题与修复

1. 原Python检索使用content_vector，而真实Spring AI索引字段是embedding；元数据映射是text+keyword，精确过滤必须使用metadata.dataType.keyword、metadata.category.keyword、metadata.documentId.keyword。已对齐源码并测试，没重建索引、没重复向量化。
2. 第一条真实RAG请求在Gateway目录校验处404，返回CATALOG_UNAVAILABLE；旧JAR不含源码中已有路由。保留失败记录，加载既有路由后重跑四题。
3. 供应商暂时超时/503导致最后独立售后模型辅助不可用，证据引用仍正常。不能将这项写成真实模型成功。

## 调用范围、幂等与证据

仅一份法规。真实检索4题，生命周期各1次；首次404后复验四题；商城原定2个售后、3个Supervisor场景，因发现真实缺陷又复验2次复合和1次售后。所有尝试保留在消息23～30及用量表，没有删除失败历史，不追加其他法规或模型场景。

`real-api-ledger.json`记录供应商usage、模型错误类型及真实工具结果；`published-snapshot.json`保存Search批次；`rag-*.json`保存每个直接问题的响应；模型错误日志在独立服务日志中。日志汇总不包含Key、Authorization Header、密码或会话Token。字符数、Chunk数和推算值从未当计费Token。

## 自动化测试（与真实 API 验收分开）

| 范围 | 通过 | 失败/错误 | 跳过 | 性质 |
| --- | ---: | ---: | ---: | --- |
| Python Agent + 数据治理 | 539 | 0 | 0 | Mock/隔离网络回归；保留1项既有MCP客户端弃用警告 |
| Java Common | 229 | 0 | 0 | 单元/Mock |
| Java Search | 120 | 0 | 0 | 单元/Mock |
| Admin Node | 11 | 0 | 0 | 本阶段审核前执行；前端修改后生产构建通过 |

Python最终证据：`python-acceptance-restored.xml/log`；Java：`java-approved-tests.log`、`java-final-summary.json`；Admin：`admin-tests.log`、`admin-build.log`。Java合计349，未声称本轮重跑全项目全部Java测试。Python测试期间禁止真实外部API；这些数量不能当真实模型调用数。

## 数据与安全边界

没有新增数据库结构迁移。导入前10库备份：`.cache/stage27/database-backup/before-governance.sql`，136958字节，SHA-256 `806b3aa0950d4d84554ea09c25baab125ad9ae525fd1979545bc1cd2172fe5ce`。审核发布前另备份 `.cache/stage27/approved-database-backup/before-governance.sql`，247119字节，SHA-256 `c9af01576816a70de45239d54b19a8b19f6b195ef78e4d7bf434305dfa5022ab`。

导入、提交审核、通过、发布、停用及启用均走现有Admin权限和业务接口，没有直接SQL伪造审批。用户自行登录，本轮没有读取/导出会话凭据；商城问题通过该已登录页面发送，完成后只读核验本轮消息及结果。

最终商品12、SKU13、库存12、订单4，与前值一致；这些是演示/验收记录，不是企业真实商业数据。数量不变本身不证明每一字段未变，本轮也没有调用它们的写接口。只新增本法规及其版本/Chunk/审计、正常聊天记录/记忆和向量；未删除FAQ、未清空索引、未执行支付/退款/下单/邮件，退款隔离和人工审批继续保留。未提交Git。



## 后续超时复核与测试范围澄清

2026-11-03：已分析消息30原始日志，并完成最小源码修复及Mock回归：Python552项通过；随后政策专项20项通过（包含于552，不重复相加）。本轮真实API调用0、未重载服务，修复后真实运行等待一次受控授权。原阶段成功/失败运行记录及计费数据不变。

Java349仅Common229+Search120专项，第26阶段1034为选定8模块；其余6模块688项本次未重跑，Search新增3项。本轮未新增执行Java测试，不能把专项或历史结果写成当前全量回归。详见[超时归因与最小修复报告](./27-DeepSeek超时与503归因及最小修复报告.md)。


## 单次受控真实运行最终补充（2026-11-03）

仅重载Agent，新PID13976，其他服务保持原PID。本次仅新增独立售后消息31；问题Embedding1次成功、36 Token；DeepSeek1次HTTP200响应头后整体辅助20.797秒TimeoutError、usage未知，无自动重试或额外模型摘要，61个文档向量未重新处理。

同时发现biz_data VARCHAR(2000)写入5段结构化证据失败（MySQL1406）。2307字降级原文已保存、status=2，但biz_data为null，当前页面显示服务暂时不可用。因此本次真实端到端验收**未通过**，不能用HTTP200/status=2、Mock通过或Agent健康替代成功。已停止，不追加真实调用，也未修复新发现的持久化问题。

本次仅22项Python政策专项Mock预检通过；未新增执行Java/前端测试。此前Java349仅Common+Search专项；第26阶段1034为选定8模块，不是全仓集成测试。本次结果和费用单独记录，不改写原阶段历史成功/失败及Token记录。

详情见[27-单次受控真实API验收结果.md](./27-单次受控真实API验收结果.md)。
