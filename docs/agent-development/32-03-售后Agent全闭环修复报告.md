# 第32阶段售后Agent全闭环修复

## 意图与订单

domain/aftersales_intent.py是动作/对象/查询/否定组合契约，供Supervisor、售后图和诊断共同使用；RETURN/REFUND/EXCHANGE/CANCEL_ORDER/ORDER_QUERY/ORDER_DETAIL/LOGISTICS_QUERY/POLICY_QUERY/AFTERSALES_PROGRESS分别路由。订单号可在句首/句中/句尾或下一轮补充；替换合法订单引用再解析语义，解决“退订单号的货”。否定操作先于取消/退款，不允许“暂不取消订单”进入取消意图。

services/aftersales_context.prepare_turn仅在可信当前user上下文中保存待补充目的；补充单号或“继续”恢复原意图，每次仍调用业务接口验证归属；缓存订单号不构成权限。多个单号不自动选单。退款进度仍查询退款事实，不错误改查案件列表。

缺单号退货直接显示本人候选并要求选择，不再反问用户想做什么。订单未核实时禁止创建申请。取消订单提供既有订单详情操作指引，本轮未增加Agent直接取消订单执行器；属于受限能力，不描述为已经取消。换货新增人工处理申请类型exchange，Java申请记录、审核、处理结果可持久化；不代表已经实际补发。资金退款类型仍严格只有refund/return_refund，换货不能改名绕入退款。

## 案件和恢复

沿用现有AftersalesCaseService/Mapper/Controller状态机：AWAITING_USER→本人CONFIRM→ADMIN_REVIEW→管理员APPROVE/REJECT→MANUAL_PENDING→CLAIM→IN_PROGRESS；退货登记/物流核实/验收后，隔离环境分步模拟退款。失败可留因跟进；超时UNKNOWN需人工核对，不自动重新划款；原退款编号保持不变。所有前置条件、处理人、版本、幂等、事务和审计由Java验证。

Supervisor及导购完整报告存入既有agent_message.biz_data MEDIUMTEXT。saved_agent_result.load_saved_result校验登录身份、消息归属、完成状态、messageId与Agent结构；结果API在Redis过期/不可用时从数据库恢复。create_from_message优先使用已落库fullReport，兼容历史缓存。旧消息没有fullReport且旧缓存也失效时无法凭空补造证据，需重新查询。

前端AgentCasePanel自动读取当前案件；并发历史卡片仅对同一用户合并在途读取，不缓存结果、不跨用户共享；每次详情重新请求Java。用户确认前只创建待确认草稿；提交后显示真实caseId/状态/处理记录。退款依然由服务端隔离，任何确认按钮不能执行真实资金操作。

## 隔离MySQL实际证据

run_mysql_cases.py先备份正式案件四表；生成白名单随机库，原Controller/事务/MyBatis套件在MySQL运行，最后只删除该测试库。78项通过，涵盖并发确认/审批/创建、回滚、他人订单拒绝、物流/验收/失败/稳定退款ID及人工换货阻断退款。消息23项检查通过，真实MySQL保存>2000字符并逐字段重读JSON；通知断开后仍可恢复；实际表不可用异常不报成功。身份查询与订单事实为Fixture/Mock，不是正式用户真实退款闭环或浏览器闭环。
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

补充订单资格上下文用例：上轮已知订单→“这个订单还能退吗”恢复该引用并二次归属核实；无上下文时列本人候选，不任意选单。一般“怎么申请售后”是政策咨询，不创建案件。最终Python全量1279通过。
