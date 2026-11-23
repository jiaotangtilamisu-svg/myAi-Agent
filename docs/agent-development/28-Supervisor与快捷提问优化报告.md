# 第28阶段Supervisor与快捷提问优化报告

## 服务端模式边界

AgentEngine沿用原support/shopping/supervisor分派。售后模式收到购物或复合任务、导购模式收到售后请求时，由服务端持久化模式不匹配提示，不调用另一专业Agent。用户身份仍来自原可信Context，未增加模型userId入口。Supervisor继续使用两个独立工作流及只读委派，不绕过退款隔离或人工审批。

路由不再把我购买的商品这样的过去事实当作新购物需求；能退/可退/能换也识别为售后。复合请求拆分后分别执行，不无条件同时运行两个Agent。单一购物/售后、模糊需求澄清、切换与隔离沿用既有状态约束。

## 快捷入口

前端agentCapabilities统一列出已核实能力。售后3个：本人订单列表、换货政策、七天后退货政策。导购3个：20元茶杯、3000元手机、上轮商品比较。统一助手5个：本人订单、两类政策、茶杯、政策+茶杯复合任务。会员/签到/收藏/热销等未验证提示已从随机池移除。首次比较没有上轮候选时应返回明确补充提示，不伪造三个商品。

点击通过原sendMessage发送完整文本和当前agentMode；等待中禁点。没有新增重复聊天接口。浏览器对全部11个可见模式入口逐一点击，测试HTTP记录为support=3、shopping=3、supervisor=5，完整文本与模式相符；这是隔离Mock接收端，不是Java生产sendMessage真实模型验收。

后端另有11个同一能力表参数化整图用例，复用真实专业LangGraph与Supervisor，仅替换MCP、RAG、模型、存储、通知等外部边界；没有Mock掉专业工作流。复合用例确实得到两个专业Agent的数据，不只检查路由字符串。

## 本人订单与异常状态

诊断缺订单号时复用QUERY_ORDERS，列本人候选让用户选择，绝不默选最近一单。列表为空、列表服务失败和缺订单号分别记录；失败进入SERVICE_ERROR，且实际尝试的工具保留在tools_called。LOCAL DEMO物流被标为演示，没有真实配送，不能用作真实异常证据。

导购/统一模式的完成通知也复用先落库后通知。终止/已取消消息返回False时不发DONE；DB异常单独走DB_PERSISTENCE_FAILED，而非模型故障。

## 仍有限制

完整导购/统一报告沿用原Redis 1小时缓存，过期后完整报告接口仍需重新查询；已有持久化文本、卡片与售后政策证据恢复接口保留。本轮没有新增长期案件/购物证据存储或迁移。实际用户订单归属用隔离Mock和Java专项验证，未冒用管理员/用户Token执行真实订单查询。

## 验证范围与数据保护

本轮Python完整运行既有Agent tests与tools/data_governance/tests，共634通过、0失败、0跳过；其中新增63例（质量49、整图14）。Java仅5个指定测试类43例通过，不是全仓回归，也不应与第26阶段1034例直接比较。前端Node测试31例通过，类型检查和生产构建通过。浏览器另有11次快捷按钮点击，属于隔离HTTP记录验证，不能当作真实模型回答。

真实LLM调用0，真实Embedding调用0；无迁移、无商品/订单/库存写入、无政策发布/审批、无Git提交。正式聊天本轮前后为51条且逐行哈希相同，商品12/SKU13/库存12/订单4保持不变；法规仍PUBLISHED、revision=1、READY、61个向量。第27阶段曾记录31条，本轮开始快照已为51条，不能把不同阶段的数量当成本轮新增。

原始证据：[.cache/stage28/results/python.xml](E:/Simlect-AI-Mall-main/Simlect-AI-Mall-main/.cache/stage28/results/python.xml)、[.cache/stage28/results/java-summary.json](E:/Simlect-AI-Mall-main/Simlect-AI-Mall-main/.cache/stage28/results/java-summary.json)、[.cache/stage28/results/frontend-tests.log](E:/Simlect-AI-Mall-main/Simlect-AI-Mall-main/.cache/stage28/results/frontend-tests.log)、[.cache/stage28/results/frontend-build.log](E:/Simlect-AI-Mall-main/Simlect-AI-Mall-main/.cache/stage28/results/frontend-build.log)、[.cache/stage28/results/audit.json](E:/Simlect-AI-Mall-main/Simlect-AI-Mall-main/.cache/stage28/results/audit.json)、[.cache/stage28/results/source-manifest.json](E:/Simlect-AI-Mall-main/Simlect-AI-Mall-main/.cache/stage28/results/source-manifest.json)。
