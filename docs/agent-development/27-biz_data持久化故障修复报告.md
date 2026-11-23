# 第27阶段：biz_data持久化故障修复报告

日期：2026-11-03（Asia/Shanghai）。数据库迁移及本地测试已完成，真实模型调用0。

## 实际结构、历史与容量选择

实际库/表为simlect_agent.agent_message，biz_data原为VARCHAR(2000)，utf8mb4对应最大8000字节；字段为NULL可空。历史共31行，14个NULL，非空17行均为有效JSON，已保存记录最大1032字符/2098字节。这里的历史最大值不包括之前因MySQL1406而根本没有写入的较大证据。

当前政策Top-K=5、每块上限约800字符，正文已可能4000字符，再加section、文档名称、Chunk ID、版本、官方URL、发布机构与分数，2000字符明显不够。已有专业Agent结果契约允许384KiB级结构；TEXT的65535字节不足以长期承载这些完整对象，因此采用MEDIUMTEXT，最大16777215字节。并未把它解释为允许无限量召回或大模型输出；Top-K/原服务契约继续生效。

不新增重复证据表：当前一条消息的文本与结构化证据本就共属一个原子更新，单字段扩容最小且兼容现有String/JSON。未修改数据成JSON列，避免破坏历史字符串和兼容接口。没有截断biz_data、缩减hits或丢弃来源。原有assistant_message的16000字符显示保护仍在，正常5块政策低于该限制；完整证据始终在biz_data中，前端能展开完整原文。

## 全调用入口与映射核查

- Python：save_user_message仅插入用户消息；complete_message是biz_data主要写入口。售后诊断、独立政策、商品/订单卡片、购物和Supervisor最终完成均复用该服务。interrupt/cancel不重写biz_data。管理员加载/删除由同一Python消息服务承接。
- 原始DDL见sql/09_agent.sql；本轮不重写该历史脚本，通过新增sql/23增量升级。
- Java Admin实体AgentMessage.bizData和AgentMessageQuery.bizData为String，无2000字符注解。当前AgentMessageServiceImpl实际用RestClient代理Python；没有该业务的MyBatis Mapper/数据库直接写入链，因此不存在需要同步改宽的MyBatis列定义。查询DTO继续保留String兼容。
- 修复Java对象响应Map.toString可能产生非JSON的问题，字符串响应原样保留；Jackson/ResponseVO正常承载完整字段。新测试验证大于2000字符、文档ID/Chunk/版本/来源往返。
- 前端历史DTO和WS均保留bizData；对象输入使用JSON.stringify，不能String(object)变成[object Object]。

## 备份、迁移及影响范围

10库一致性备份：`.cache/stage27-persistence/database-backup/before-governance.sql`，289100字节，SHA-256 e4623e3ee9c1e1b3d3ecf72db3c150c8344a2bdc5e091b2f958ebb508217380b。

相关表单独备份：同目录agent_message.sql，74179字节，SHA-256 a5fc54fa9d00de9648d3997c23c84c3e28d4d876d8e7ddc694cf5a17c4863850。仅展示哈希/路径，不输出备份中的业务内容或密码。

实际执行唯一DDL：

```sql
ALTER TABLE simlect_agent.agent_message
  MODIFY COLUMN biz_data MEDIUMTEXT NULL COMMENT '业务数据及完整证据JSON';
```

通过工具先Dry-run，再验证备份哈希与库范围、短锁等待限制后执行。DDL不是可通过普通事务ROLLBACK撤销的操作，故先备份；未执行删除、清表、迁移其他字段或更改数据。前后31条消息所有原字段的逐行SHA-256一致，最后核验仍一致。再次运行迁移工具changed=false，验证幂等跳过；未缩回VARCHAR。将来回退前必须检查新数据长度，不能盲目缩窄。

实际测试使用名为stage27_message_evidence_test的连接级TEMPORARY表，按迁移后的基表结构创建；测试适配器仅将应用SQL表名替换为该临时表，参数和完整JSON不变。连接关闭自动移除，不向正式表插入测试消息。三种模型状态各成功保存约240KB JSON并逐字符相同；另验证错误状态4不会被完成覆盖。正式31行前后哈希不变。

## 修复后的保存顺序与数据契约

原顺序：push_done → 数据库写入 → 异常时push_chat_error → 丢弃biz_data并补写status2。现在为：严格序列化 → 同一SQL原子保存text+biz_data+status2 → 推DONE（携带bizData）。失败则抛MessagePersistenceError，经独立分支写入status4/agent_persistence_error并推DB_PERSISTENCE_FAILED；不走原无证据成功补写，不运行后处理摘要。

政策biz_data保留原有status/hits字段全部内容，增加kind=policy_answer、messageId、responseStatus、modelStatus、modelFailureCode、executionAllowed=false。模型正常返回为SUCCESS；模型超时/503为DEGRADED，政策原文照常保存；RAG无依据为EVIDENCE_UNAVAILABLE。HTTP200但模型JSON非法不能被当作成功。

如果WS发布失败但数据库已经成功，不反向改成失败或丢弃证据，前端通过同一messageId的所有者范围查询恢复。取消/终态保护返回False，不发新的DONE；失败状态4不被重复完成覆盖。数据库完全不可用时只能通知明确失败，不能保证写下失败标记，不会伪称成功。

## 修改文件

| 文件（相对项目根目录） | 作用 |
| --- | --- |
| sql/23_agent_message_evidence.sql | 仅将biz_data扩展为MEDIUMTEXT |
| tools/data_governance/message_migration.py | 默认Dry-run、备份哈希校验、单字段范围白名单、幂等跳过及逐行哈希保护 |
| tools/data_governance/tests/test_message_migration.py | 允许扩容、拒绝删除/缩窄/无关表SQL的4项测试 |
| Simlect-backend/Simlect-agent/app/services/message_service.py | 完成写入返回状态、数据库异常包装、失败状态4、失败DTO错误码；biz_data原字符串无截断 |
| Simlect-backend/Simlect-agent/app/services/agent_runtime.py | 证据严格JSON序列化、先保存后DONE；发送失败可读库恢复；数据库异常使用独立失败路径；政策payload保留完整hits与模型降级状态 |
| Simlect-backend/Simlect-agent/app/graph/nodes.py、app/graph/state.py | 持久化失败不走原“空证据成功”补写，不再执行后处理/模型摘要 |
| Simlect-backend/Simlect-agent/app/models/message_send.py、app/services/stream_service.py | WS DONE携带完整bizData，错误携带errorCode |
| Simlect-backend/Simlect-agent/app/rag/advice.py | 整体deadline包含客户端准备/清理、异常阶段及失败码；保留真实证据护栏 |
| Simlect-backend/Simlect-agent/app/services/llm_factory.py | 明确连接/写入/池超时5秒、读取20秒，整体仍20秒；零重试、非流式、512 Token、关闭thinking不变 |
| Simlect-backend/Simlect-agent/tests/test_policy_evidence_delivery.py | 13项新增持久化/降级/通知/响应体测试 |
| Simlect-backend/Simlect-agent/tests/test_policy_model_resilience.py | 适配显式timeout对象和失败分类字段，继续真实SDK+MockTransport |
| Simlect-backend/Simlect-admin/src/main/java/com/simlect/biz/impl/AgentMessageServiceImpl.java | 保留长String，对结构化对象用既有JsonUtils.toJson而不是Map.toString |
| Simlect-backend/Simlect-admin/src/test/java/com/simlect/biz/impl/AgentMessageServiceImplTest.java | 2项新增长JSON/完整来源映射 |
| Simlect-front/Simlect-web/src/utils/agentPolicy.ts | 严格解析同一消息完整证据、降级分类及安全来源链接 |
| Simlect-front/Simlect-web/src/utils/agentHistory.ts、agentReply.ts | JSON对象无损转换、失败4终态、WS/轮询按消息ID恢复 |
| Simlect-front/Simlect-web/src/components/agent/AgentChatItem.vue | 正常/降级原文展示，完整来源/版本/Chunk/原文折叠区；数据库错误保留明确文案 |
| Simlect-front/Simlect-web/src/views/agent/AgentChatList.vue、src/stores/agentMessage.ts | 接收bizData/errorCode，持久化失败不强制变成status=2 |
| Simlect-front/Simlect-web/tests/agentPolicy.test.ts | 5项前端合同/完整证据/错误分类测试 |

没有新增服务、中间件或独立知识库，没有修改原有商品搜索、售后业务或退款执行权限。

## 本轮测试范围与实际结果

| 测试 | 通过 | 失败/错误 | 跳过 | 性质与范围 |
| --- | ---: | ---: | ---: | --- |
| Python Agent + tools/data_governance全部现有测试 | 571 | 0 | 0 | 独立测试环境、Mock/网络阻断；1条既有MCP弃用警告 |
| Java AgentMessageServiceImplTest | 9 | 0 | 0 | 仅Admin消息映射专项，包含2个新增大JSON/对象序列化用例 |
| 商城Node测试 | 27 | 0 | 0 | 包含5个新增政策展示、消息ID、保存失败及链接安全测试 |
| 实际Vue组件SSR | 2 | 0 | 0 | AgentChatItem使用标注TEST ONLY的测试夹具；内存路由替代浏览器路由，非真实业务联调 |
| 真实MySQL临时表 | 4 | 0 | 0 | 本地SQL/约240KB JSON往返、用户隔离、失败状态保护；不是模型验收 |

前端`npm run build`通过，包含vue-tsc类型检查及Vite生产构建，没有升级依赖。SSR包含图标组件的既有渲染警告，关键政策和错误内容断言通过；不是浏览器交互或真实模型测试。首轮缺少score的测试夹具、MySQL同名临时表冲突和SSR浏览器路由依赖错误均保留初次日志；修正测试夹具/隔离方式后通过，没有用业务数据掩盖失败。

Python571为本轮Agent与数据治理测试，Java9为本轮Admin专项。**此前Java349是Common229+Search120专项，第26阶段1034是选定8模块回归，均不能当作本次Java测试结果或全仓集成测试。** Java依赖模块在`-am`过程中仅编译，未匹配该测试类的模块没有计入通过；`-Dsurefire.failIfNoSpecifiedTests=false`不等于这些模块测试通过。

证据：`.cache/stage27-persistence/results/python-complete.xml/log`、`java-admin.log`及Admin JUnit XML、`frontend-tests-release.log`、`frontend-build-release.log`、`frontend-ssr.json/log/html`、`local-mysql-tests.json`。各层测试独立列出，不合计为真实API通过数量。

## 执行边界、加载状态及遗留项

- 本轮真实DeepSeek/Embedding调用均为0；HTTP200、延迟正文、503、连接断开和非法JSON均由MockTransport/假模型模拟。测试数据库连接仅访问本地MySQL，没有向模型发送真实法规或订单。
- 没有修改已发布法规、没有重新向量化61个Chunk、没有清空索引。最终只读确认仍61个向量。
- 没有修改商品、SKU、库存、订单，没有支付/退款/下单/邮件，没有.env变更或凭据输出。
- 没有重启任何服务，未提交Git；所有历史用户修改保留，关键源码和数据库备份均位于E盘`.cache/stage27-persistence/`且被Git忽略。
- **数据库迁移已经应用；Python/Java源码修复尚未重载到运行中的Agent/Admin。**前端Vite可加载改动，生产构建和组件SSR通过，但没有发送真实聊天消息验证页面。后续运行验收须单独安排必要服务加载，并另获真实模型授权；本轮停止。
- 历史消息31等原先biz_data=null没有被回填或改写。此次只扩容并修复未来写入；不能宣称恢复了此前未落库的完整结构。
- 数据库完全不可用时，连失败标记也可能无法持久化；会推送明确DB_PERSISTENCE_FAILED并记录日志，绝不伪称保存成功，恢复后仍需核实历史状态。没有增加外部文件保存敏感业务证据的旁路。

