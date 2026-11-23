# 第27阶段：单次受控真实API验收结果

日期：2026-11-03（Asia/Shanghai）。项目：E:/Simlect-AI-Mall-main/Simlect-AI-Mall-main。

## 结论：本次真实端到端验收未通过，已停止

严格只提交一次独立售后请求，messageId=31。真实RAG检索成功；DeepSeek收到HTTP200响应头但在20秒配置期限内没有完成响应，返回UNAVAILABLE/TimeoutError，未取得模型usage。另发现结构化证据写入biz_data超过VARCHAR(2000)，触发MySQL1406。

数据库保留了2307字降级引文文本、status=2，但biz_data为null；当前聊天页显示“服务暂时不可用，请稍后重试”。**不能把HTTP200、status=2、Agent健康或文本有保存描述为AI回答成功/完整持久化成功。**发生超时后没有再提交问题、重试模型、追加摘要、运行Supervisor或修复数据库/持久化源码。

## 授权范围与环境加载

仅用已发布《中华人民共和国消费者权益保护法实施条例》（国务院令第778号），documentId=f85d1c36-053a-430b-a05f-e9ce88810e99，revision=1，LAW/PUBLISHED/READY，未新增政策。

仅重载Agent：旧PID13368 → 新PID13976，原监督脚本 `scripts/local/start-agent.ps1`，等价实际服务命令：

```powershell
E:\Simlect-AI-Mall-main\Simlect-AI-Mall-main\Simlect-backend\Simlect-agent\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 7050
```

工作目录为Simlect-backend/Simlect-agent，仍由现有脚本读取本地环境；没有编辑.env。核实监听PID与CIM命令行，创建时间晚于修复源码；加载前备份原日志，记录4个关键源码SHA-256，加载后哈希未变。本次实际日志出现新policy_model_http/policy_model_finished/policy_history_local事件，证明新路径确实执行，不仅根据端口或时间判断。

Agent前后HTTP200/status=ok，java_web、Redis、MySQL、Elasticsearch均true。其他既有进程保持Gateway12272、Order5620、Product31092、Stock32800、Search15036、MCP9448；未重启其他服务或Docker。

独立启动监督PID22524不是实际Agent服务PID。CIM父进程、创建时间和可执行路径见agent-process.json，前后进程对照见process-comparison.json；不将本次时点检查当15分钟存活测试。

## 调用前发现并完成的最小兼容修正

已安装ChatOpenAI会把max_tokens转成max_completion_tokens，而[DeepSeek官方接口文档](https://api-docs.deepseek.com/api/create-chat-completion/)定义输出上限字段为max_tokens。为保证授权上限发送正确，仅在官方DeepSeek政策工厂分支通过extra_body传max_tokens=512和thinking=disabled，并避免SDK同时发送改名字段。其他服务商及普通聊天不改。

修改文件：`Simlect-backend/Simlect-agent/app/services/llm_factory.py::create_policy_llm`；相应扩展`tests/test_policy_model_resilience.py`，同时验证DeepSeek与其他兼容端点的真实SDK序列化请求体。修改前备份在.cache/stage27-controlled-once/before/。未修改真实.env、数据库或支付/退款接口。

本次Mock预检22项通过、0失败、0跳过，证明非流式、SDK零自动重试、正确512字段及原失败护栏。它是政策专项，不是本轮Python全量回归；此前552项是上一次修复的历史回归，本轮未冒称再次全量运行。

## 唯一真实请求

通过已登录商城页面提交，模式support。未读取、复制或保存账号密码、Cookie、Token。问题为：

> 我网购的商品签收已经超过七天，还能申请退货吗？请依据《中华人民共和国消费者权益保护法实施条例》说明政策依据及仍需核实的信息。

提交前本用户最大消息ID30，提交后仅新增31，日志agent_task_started一次，mode=support。没有发起Supervisor任务、订单创建或退款。前端getMessage轮询仅读取已提交消息，不是新的验收请求或模型重试。

| 时间（北京时间2026-11-03） | 事件 |
| --- | --- |
| 17:39:21.562 | 消息31任务开始 |
| 17:39:22.981 | 问题Embedding成功，1024维、36 Token |
| 17:39:24.951 | RAG SUCCESS，5个引用 |
| 17:39:26.123 | DeepSeek响应头HTTP200，attempt=1，响应头耗时250ms |
| 17:39:45.756 | policy_model_finished：UNAVAILABLE，TimeoutError，attempts=1，完整辅助流程耗时20797ms |
| 17:39:45.777 | graph_finalize_failed：MySQL1406，biz_data过长 |
| 17:39:45.831 | policy_history_local：仅本地历史摘要 |
| 17:39:45.853 | 主任务结束，降级文本保存；不等于模型回答成功 |

call_id：b803bc328af94a418865731fbb5a0380。250ms只到响应头，不能当作模型完整回答耗时；20797ms包括客户端准备/清理，配置的asyncio等待上限为20秒，不能声称整个端到端过程严格20.000秒。任务总历时约24.292秒，含RAG等处理。

## 真实请求次数、用量和重试

| 项目 | 本次实际观测 | 计费信息 |
| --- | --- | --- |
| 用户独立售后请求 | 1条，消息31 | 不以本地轮询次数替代模型请求数 |
| 问题Embedding | 1个成功响应，text-embedding-v4/1024 | 供应商返回prompt_tokens=36、total_tokens=36 |
| DeepSeek | 1个HTTP请求响应，deepseek-flash，非流式 | 响应体未完成，无usage，实际Token和费用未知，不能填0 |
| SDK自动重试 | 0，配置max_retries=0，hook最终attempts=1 | 没有第二次模型尝试 |
| 模型摘要 | 0，未出现assistant_condense或第二个llm_usage；policy_history_local=1 | 仅本地截断历史上下文 |
| 61块文档重新向量化 | 0 | Search原7批记录完全不变，无新增文档Embedding |

模型参数为20秒、非流式、thinking=disabled、max_tokens=512；请求体序列化由本次Mock预检确认，运行前有效配置及源码哈希一致。没有抓取或落盘Authorization和完整HTTP请求体。因为响应被取消，不能独立验证服务商实际生成了多少Token，也不能假设取消等于零计费；不查询余额或发起额外接口来补足账单。

HTTP200仅证明响应头成功到达，不证明有效JSON/模型业务成功。没有观察到本次503，但仍遇到限时内无完整响应，不能根据这一次推定服务商故障已经恢复，也不能仅凭本次日志区分服务端生成阻塞与中间网络/心跳机制。

## RAG条款、政策事实与未知事项

RAG命中文档来源仍为司法部国家行政法规库，官方URL https://xzfg.moj.gov.cn/front/law/detail?LawID=1708，版本1。首命中第19条（相关度显示0.795），第2为第18条（0.792）；其余包含公布正文、第20条、第21条。后二条与本问题相关性有限，不将所有召回都描述为精准答案。

降级文本中的5段原文逐段与已核验原始Word/权威版本Chunk进行完整引用匹配，匹配5/5；Chunk ID和SHA-256见controlled-result.json。第19条对应37abbe56-62ad-3c61-9f44-d0ac4f5ce084，第18条对应1a6c9fd0-1036-3c8a-8b8d-b11c356693c0。此处ID由已保存引文与权威Chunk精确匹配复核，并非声称失败的biz_data保留了完整检索对象。

没有拿到可用LLM分析文本，不存在本次成功模型回答可供法律结论准确性验收。已保存降级文本仅引用原文并提示人工核实/模型辅助不可用；未承诺一定可退、一定不可退或退款已执行。国家法规不能当商城自有承诺。前端当前只显示通用错误，因此“用户正常收到带依据的完整答复”仍未通过。

政策发布状态、有效期、版本和61个唯一向量前后不变，原文哈希保持一致；没有重建ES索引、更新法规状态或修改商品/订单。

## 持久化异常：新发现，未擅自修复

只读information_schema确认agent_message.biz_data为VARCHAR(2000)。现有最终政策分支在`app/services/agent_runtime.py::finalize_agent_response`中将完整5段证据JSON交给`app/services/message_service.py::complete_message`更新，日志出现MySQL1406 Data too long，结构化证据更新失败。

`app/graph/nodes.py::finalize_node`捕获后走`push_chat_error`。最终数据库status=2、assistant_message长度2307，biz_data=null；前端显示“服务暂时不可用，请稍后重试”。这正是不能只凭status=2判成功的情况。

本次按“发生超时立即停止”要求，只调查字段定义并保留证据，没有迁移字段、截断证据、修复业务源码、重启或再发一次请求。后续可独立审核采用精简的来源引用结构或非破坏性字段扩展，但必须评估保存/读取契约和备份；不在此处擅自选择和执行。

## 验收逐项结论

| 标准 | 实际结论 |
| --- | --- |
| 新代码加载、Agent健康 | 通过；新PID13976、健康ok、新日志路径已执行 |
| 真实RAG/正确第778号条款 | 检索与原文核验通过；召回有宽泛条目，非精度100% |
| DeepSeek完整成功响应 | 未通过；HTTP200响应头后TimeoutError |
| 有依据的模型回答 | 未通过；没有可用模型输出，不能用降级原文替代成功模型验收 |
| 不编造、金融隔离 | 未观察到无依据法律结论或金融执行；没有调用金融接口 |
| 一次请求、零重试、零额外摘要 | 通过；1条消息、1次模型HTTP尝试、本地摘要事件1次 |
| Token完整可核算 | 部分；Embedding36，模型usage未知 |
| 最终答复正常展示/完整持久化 | 未通过；仅降级文本保存，biz_data失败，页面通用错误 |
| 不重复文档向量化 | 通过；61个向量及原7批日志不变 |

## 测试范围澄清与交付证据

本次预检22项是Python政策专项Mock；本次真实验收1个独立场景、结果未通过，两者不相互替代。没有本次新的全量Python/Java/前端回归。

此前第27阶段Java349=Common229+Search120，是专项回归；第26阶段Java1034是选定8模块（Common229、Gateway41、Product122、Stock39、Search117、Order390、Pay65、Cart31）。其余6模块688项本次未重跑，Search相比增加3项；两次都不是全仓真实集成测试。本次没有执行Java测试。

证据目录 `.cache/stage27-controlled-once/`：

- before/原Agent日志、进程/政策快照及源码备份；
- results/preflight-mock.xml/log：22项Mock；effective-policy-settings.json、loaded-source-hashes.json、source-integrity-after.json；
- results/scene-stdout.log、scene-stderr.log：冻结的本次现场，不删除原日志；
- results/before-message.json、message-result.json、controlled-result.json：唯一消息、实际回复及脱敏结果；
- results/policy-after.json、process-comparison.json、agent-process.json：索引/进程和健康；
- results/controlled-call-ui.png：真实失败页面截图。

本次已停止，真实模型授权次数已用尽。保持服务现状，不自动修复、重试或开始下一阶段，等待用户审核；没有Git提交。

