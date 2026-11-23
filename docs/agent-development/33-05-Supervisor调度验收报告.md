# 第33阶段Supervisor调度

本轮执行记录以2026年11月5日本机日志时间为准，2026年11月6日完成交付整理。未调用真实LLM或Embedding（均为0），未下单、支付或真实退款；未发布政策，未重新处理61个已发布法规向量。当前目录的价格和库存属于本地配置，不冒充供应商实时商业数据。Mock、真实隔离MySQL/ES、本机公开接口、真实浏览器分别列明，不能互相替代。

修复[Simlect-backend/Simlect-agent/app/services/mode_routing.py](<E:/Simlect-AI-Mall-main/Simlect-AI-Mall-main/Simlect-backend/Simlect-agent/app/services/mode_routing.py>)，send_message接收与agent_engine执行共同使用effective_mode。纯购物进入shopping，纯售后进入support，混合进入supervisor；主动选择supervisor仍保留统一调度。未知意图保留所选模式并澄清。未把所有请求无条件交给两个Agent。

ACK保留requestedMode及实际agentMode；商城AgentSendPanel读取有效模式同步选框。身份不从模型或该模式字段取得，原server-side context/内部认证/业务归属分别验证。Supervisor调用两个原独立图，保留任务状态/失败/超时及证据，不在汇总层修改价格、库存和政策原文。

本机“查询售后政策，另外推荐3000元以内的手机”实际运行两个专业图，状态为{"aftersales": "SUCCESS", "shopping": "SUCCESS"}，并取得3个政策Chunk。产品与政策查询走本机远程MCP和Java；只有policy_model_advice、status_transport被Mock。具体ChunkID见[.cache/stage33/local-business-reads.json](<E:/Simlect-AI-Mall-main/Simlect-AI-Mall-main/.cache/stage33/local-business-reads.json>)，不是只生成路由文字。

单Agent异常、超时、部分成功、重复任务、用户隔离、上下文恢复、串域隔离等重跑test_supervisor.py/test_stage32_flow_and_recovery.py/test_stage33_contracts.py；结果属于1304项Python全量，未重复计数。模式误拒绝原测试按新业务目标改为断言真实runner只调用一次，未放宽SKU、身份或退款限制。

真实浏览器三种模式选项、快捷问题随模式变化及已落库多Agent结果能显示；本轮没有通过正式账号发送新复合任务。真实模型汇总及付费向量分支仍未验收。
