# 第23阶段：ETL导入实施报告

## 实际修改文件

- tools/data_governance/olist.py：9文件规范、流式CSV/磁盘SQLite暂存、金额/日期/坐标、重复、外键、文件SHA与质量报告。
- storage.py：仅simlect_data_governance的事务写入、批次、内容哈希、不可变版本、幂等与失败审计。
- cli.py：默认dry-run、显式apply、校验版本与备份清单；不提供写现有Order/Pay/User业务表的路径。
- backup.py：Docker容器内既有数据库认证，十库一致性备份；不把密码放在主机命令或日志中。
- migrate.py、sql/21_data_governance.sql：显式范围校验后仅CREATE新治理库和3表；无ALTER/DROP/TRUNCATE。
- catalogue.py：15个明确合成候选、字段级来源与多SKU数据。
- adapters.py：复用现有Java商品批量读、已验证用户订单读、Stock变更/补偿契约；提供ProductSaveDTO纯映射和非执行订单场景计划。
- tests/test_etl.py：CSV、幂等、回滚、版本、来源、模拟绑定安全等测试。
- Simlect-agent/app/services/data_provenance.py、product_facts.py：区分业务出处与技术查询出处，未知来源不冒称实时商业数据。
- app/shopping/selection.py、runner.py、app/utils/biz_payload.py：保留来源并防历史商品作为当前在售推荐。
- Simlect-web/src/utils/dataProvenance.ts、components/agent/AgentProductList.vue：来源标签；新增来源测试。
- Search/RabbitMQRagListenerComponent.java：同一PRODUCT事件刷新关键词索引后再向量化；失败仍走原重试/DLQ。新增ProductIndexEventTest两项。

既有文件修改前副本在.cache/data-governance-20261103/before/。只格式化本轮新增的ETL/来源代码，没有格式化全项目。

## 真实数据库实施

备份：.cache/data-governance-20261103/backup/before-governance.sql，132123字节；SHA-256 7515306c9264fd104faff495b2027bafd82c960c5feae673fe68519bb17cbcd0。备份内容私有，不加入Git或报告正文。

范围审查后建立simlect_data_governance三表；为Search应用既有第17阶段CREATE IF NOT EXISTS知识目录2表。没有改原业务表结构或FAQ。

合成候选真实MySQL导入：首次COMMITTED 15行；同一批再次ALREADY_IMPORTED 0行。故障注入使用另两条明确SYNTHETIC的隔离测试记录：第一行写入后第二行哈希失败，事务回滚后记录数0、批次FAILED；修复该测试输入后重试COMMITTED 2行。失败审计保留TRANSACTION_ROLLED_BACK，不把这些测试记录标为PUBLIC_DATASET。

## 幂等与回滚边界

batchId由来源/版本/文件内容摘要确定；同批重复跳过。record_key由来源/实体/原ID/版本确定，同版本内容变化拒绝，不覆盖旧记录；新版本追加。批次行锁与唯一键保护并发；事务失败回滚历史行与来源行，再单独记录失败状态。

这只保证隔离MySQL导入事务，不承诺跨Product/Stock/Order HTTP发布原子性。Stock适配要求持久化、不可变操作意图和已登记SYNTHETIC SKU/独立SYNTH_用户绑定；operationId重复可重试，释放携带requiredOperationId，禁止改变同一操作的数量。该适配器未对真实库存执行。

## 未下载数据时的真实dry-run

运行：
```powershell
.\Simlect-backend\Simlect-agent\.venv\Scripts\python.exe -B -m tools.data_governance.cli --input data/olist/raw --version olist-local-v1 --dry-run --output .cache/data-governance-20261103/results/olist-dry-run.json
```

结果INVALID，退出码2，列出全部9个缺失CSV，未连接业务库或导入Olist数据。这不是导入成功，也不是代码测试失败。

请将原始CSV放入E:/Simlect-AI-Mall-main/Simlect-AI-Mall-main/data/olist/raw/。原始数据、临时spool、备份和质量输出位于忽略目录；禁止把包含真实凭据的本地配置纳入提交。

## 明确未完成

Olist全量导入/真实数据质量统计、候选向Product/Stock发布、独立模拟用户/地址/订单/物流/案件场景、跨服务发布恢复登记及完整真实商业数据验收均未完成。原因分别为CSV缺失、用户明确要求发布前确认，以及尚未准备经验证的模拟业务绑定。当前没有企业实时数据源，不宣称商业数据接入成功。
