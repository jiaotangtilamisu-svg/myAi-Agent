# 第32阶段Supervisor与多轮上下文治理

保留Supervisor LangGraph的路由→专业Agent→校验→汇总；不无条件并发两个Agent。routing.py接入统一售后契约和品牌归一，复合连接词只在动作边界切分，不拆“三星和华为”。数量/优先/现货追问保留购物上下文，业务切换仍由可信用户会话路由。

adapters.py复用原售后图和导购图，分别校验AgentResult。本人订单列表直接使用QUERY_ORDERS真实结构；售后申请进度使用现有Java案件接口，退款进度保留退款业务语义。结果不合法、超时、错误分别保留，单Agent失败不覆盖另一个成功结果。delegation只读约束不变。

store.py按用户隔离pending businessIntent/orderId与购物requirements，不用模型userId。prepare_turn恢复的是业务目的和引用，订单归属仍二次查询。50组购物对话逐轮验证预算、品牌、规格偏好、现货及数量，另有售后下一轮补订单、多订单拒选、跨用户上下文隔离测试。

Supervisor runner将完整专业结果原样持久化fullReport，聚合只组织消费者文本，不改价格库存，不丢政策来源。前端默认用持久化证据，缓存不是唯一事实源。日志保留messageId与工具耗时；GUARD/REMOTE_MCP、传输COMPLETED/FAILED与业务SUCCESS/EMPTY/ERROR/UNKNOWN分开记录，普通文本不算成功，MCP缺协议不重复查询Java掩盖错误。
|层次|本轮通过|失败|跳过|实际范围|
|---|---:|---:|---:|---|
|Python全量|1279|0|0|Agent/tests及data_governance/tests；外部网络/模型隔离|
|Java全模块|1585|0|2|根POM离线test；默认H2和Mock，不冒充MySQL|
|商城Node测试|65|0|0|工具函数/协议断言，不是浏览器DOM验收|
|Admin Node测试|24|0|0|工具函数/协议断言，不是浏览器DOM验收|
|隔离MySQL案件|78|0|0|同一Java Controller/事务/MyBatis用例，订单事实与身份查询Mock|
|隔离MySQL消息检查|23|0|0|真实SQL与消息Service，模型情形/通知Mock|
|本机公开业务图检查|13|0|0|实际MCP/Gateway/Java/ES；用户身份夹具、模型建议与通知Mock|
|本机安全/源码契约检查|7|0|0|未登录拒绝、Vite模块、61个已发布Chunk只读|
|健康检查|14|0|0|14个现有本机服务|

## 证据边界

真实LLM、Embedding调用均为0，真实退款、支付、下单均为0。没有发布/修改正式政策、重新向量化61个Chunk、修改正式商品/价格/库存/订单。公共目录及本地价格库存不冒充来源商家的实时商业数据。Mock、隔离MySQL、本机公开接口、浏览器及付费模型验收分别统计。

浏览器工具本轮返回：“could not determine the current browser URL on Windows with enough confidence to enforce policy”，已停止UI自动化；没有改用CDP、读取Cookie或伪造登录绕过。浏览器完整交互为BLOCKED，不能写作通过。当前LOCAL_STORE真实运行走关键词和Java核验；真实Embedding向量分支/RRF双路实际参与仍需另行付费授权。真实物流承运商、真实资金渠道未验收。
