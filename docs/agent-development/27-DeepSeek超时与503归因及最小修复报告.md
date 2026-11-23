# 第27阶段：DeepSeek超时与503归因及最小修复报告

日期：2026-11-03（Asia/Shanghai）。项目目录：E:/Simlect-AI-Mall-main/Simlect-AI-Mall-main。

## 结论与当前边界

已确认的是一次**客户端流式内容块等待超时**和随后另一次**模型摘要HTTP503**，不能把两者混成同一次请求，也不能根据503推断首次静默的唯一原因。未发现本消息被重复提交或两个逻辑调用同时执行的证据。SDK默认重试、超时层级和无必要的政策摘要增加了额外等待/调用风险。

本轮已完成最小代码修复和Mock测试，**真实LLM/Embedding API调用均0，没有重启服务、没有修改.env，也没有提交Git**。修复尚未加载到运行中的Agent；不能宣称已通过修复后真实运行验收。等待用户单独授权一次受控真实调用后再加载并验收，不自动补测。

## 原始日志与时间线

原始文件（未清理或改写）：

- `logs/independent-services/agent/20261103-165128-e84f210f/stdout.log`
- 同目录`stderr.log`，包含`langchain_openai.stream_chunk_timeout fired`。
- 关联的消息30持久化结果在 `.cache/stage27/results/chat-real-results.json`；原阶段API用量在`real-api-ledger.json`。

本次脱敏抽取、原日志SHA-256和精确行号保存在 `.cache/stage27-timeout-review/results/original-log-evidence.json`，未输出或保存账号密码、Cookie、Token、Authorization。

| 时间（北京时间2026-11-03） | 原日志事件 | 判断 |
| --- | --- | --- |
| 16:55:42.557 | agent_task_started，message_id=30 | 本轮仅一次任务启动 |
| 16:55:44.023 | embedding_usage，15 Token | RAG问题向量化成功，不是LLM成功 |
| 16:55:45.949 | aftersales_policy_retrieved，SUCCESS/1引用 | ES与已发布政策目录已通过 |
| 16:57:49.008 | llm_usage_error，StreamChunkTimeoutError | 客户端内容块等待超时，未返回可用模型答案 |
| 16:57:49.123 | agent_task_completed | 已保存安全降级原文，完成不是模型成功 |
| 16:57:51.033 | llm_usage_error，OpenAIAPIError；assistant_condense_failed | 另一个摘要调用返回HTTP503，错误正文报告“Service is too busy” |
| 16:57:51.038 | assistant_condense_done，765→500字符 | 此处是本地截断降级完成，不是摘要模型成功 |

从任务启动到主任务结束约126.566秒；从RAG成功到超时约123.059秒。后一个间隔还包括调用构建等开销，**不是已精确记录的HTTP请求耗时**。503日志在主任务完成后约1.911秒出现，没有原始摘要HTTP开始时间，不能把1.911秒当其精确请求耗时。

## HTTP状态、次数与并发

- 消息30包含2个应用级模型调用：法规证据选择，以及随后为了记忆压缩调用的摘要。源码分别是`app/rag/advice.py::policy_advice`和`app/memory/assistant_condense.py::condense_assistant_for_history`。后者由`post_turn.py::PostTurnService.run`调度。
- 首次流式模型调用的HTTP状态码、首字节时间、已收到块数没有写入现有原日志；**未知，不能把商城sendMessage的HTTP200当供应商HTTP200**。
- 摘要错误字符串明确携带503。基于当前配置，两者使用同一`api.deepseek.com`地址和deepseek-flash模型；未发现401、403或400的证据。日志无法证明503源于上游模型主机、边缘代理还是其他内部组件。
- 原日志没有逐HTTP尝试记录。应用调用2次不等于HTTP请求2次；实际重试次数及失败请求计费Token**无法还原**。安装的OpenAI SDK默认max_retries=2，符合条件的错误最多初次+2次重试；不能据此断言实际发生了3次。
- 当前消息仅有一次agent_task_started，前一消息29已在16:52:59左右完成，消息30于16:55:42开始。未见同一消息重复提交或两个上述调用重叠的证据。摘要是另一个用途的顺序调用，不是主模型重试。其他用户/进程或服务商整体负载未有全面追踪，不下结论。
- `_pending_condense`只提供本进程同一user/message的在途去重；不等于跨进程幂等。没有证据表明本次存在跨进程重复摘要，故不新增分布式锁或任务平台。

## 三类原因分开判断

| 类别 | 已证实 | 不能据此证明 |
| --- | --- | --- |
| 服务商/上游 | 摘要收到503，响应报告繁忙；当时供应链返回不可用 | 首个流式静默也必然由该故障造成；具体上游组件、限流或容量根因 |
| 网络/超时 | LangChain内容块墙钟计时器触发 | TCP连接超时、DNS错误、TLS错误或断网；原日志没有这些异常 |
| 请求配置 | 主聊天streaming=True；请求timeout=60秒，内容块timeout=120秒；未显式传SDK重试；简单JSON选择沿用长流式/思考路径 | API Key错误、URL错误、模型不存在或流式usage不兼容；此前同配置成功且本次没有对应4xx证据 |

当前已安装版本：langchain-openai 1.7.3、OpenAI Python SDK 3.42.0、httpx 0.28.1。以上默认值直接核对本机安装源码：`langchain_openai/chat_models/base.py`的`request_timeout/max_retries/stream_chunk_timeout`，以及`openai/_constants.py::DEFAULT_MAX_RETRIES`、`openai/_base_client.py::_should_retry`。

httpx的read timeout针对字节读取，SSE心跳可使其持续刷新；LangChain的120秒计时针对解析后的内容块，心跳不重置它。因此“timeout=60仍等约123秒”不构成没有超时设置的证据。是否实际收到过心跳未被原日志记录，只能将机制作为解释，不当事实。

项目`llm_max_retries=3`原来未传入ChatOpenAI，实际SDK使用默认2；Agent总任务超时300秒，Supervisor单专业Agent60秒，而旧流式内容块等待120秒，层级不协调。修复只约束法规辅助选择，不全局重配普通聊天或延长等待来掩盖上游故障。

## 最小修复（已修改，未重载）

| 文件/关键方法 | 修改 |
| --- | --- |
| `Simlect-backend/Simlect-agent/app/config/settings.py` | 新增policy_llm_timeout_seconds，默认20秒，校验0～45秒范围（不含0），不写真实.env |
| `app/services/llm_factory.py::create_policy_llm` | 政策JSON选择使用独立配置：非流式、SDK自动重试0、timeout20秒、最多512输出Token、temperature0；官方DeepSeek端点显式关闭thinking。原聊天/导购/记忆工厂和普通聊天流式保持原样 |
| `app/rag/advice.py::policy_advice` | asyncio.timeout约束整次辅助等待；临时AsyncClient用完关闭；HTTP hooks记录不含URL/正文/凭据的call_id、attempt、HTTP状态、响应头到达耗时；另记录整体结果/耗时/异常类型。200但伪造来源仍拒绝；失败仍只用已核实引文 |
| `app/memory/post_turn.py::PostTurnService.run` | 政策轮次已有结构化证据和完整持久化文本，保存本地截断的上下文摘要，跳过额外异步LLM摘要和长上下文压缩。既防无意义重写法规，也防主模型故障后立即再调用同服务；不删除完整回复 |
| `tests/test_policy_advice.py` | 原模型Mock接点改为专用政策工厂，保留原7项护栏测试 |
| `tests/test_policy_model_resilience.py` | 新增13项Mock验证，包含真实SDK+MockTransport，实际外部请求0 |

HTTP hook的elapsed_ms是到响应头，不是整个生成时延；policy_model_finished另记完整辅助调用耗时。没有响应时status_code为null，不虚构状态码。随机call_id用于关联一次逻辑调用，不暴露userId、消息正文或订单事实。

不添加自动切换服务商、无限重试、队列重投或新框架，不绕过RAG状态/版本校验，不改变退款隔离、订单归属和Supervisor只读委派。没有修改任何Java、Vue业务文件或数据库。

## Mock测试与真实运行分开

- Python Agent全部现有测试 + 数据治理：**552通过、0失败、0跳过**。证据`python-final.xml/log`；保留1条已有MCP弃用警告。
- 增加调用关联日志字段后，政策专项20项（13新增+7既有）再次通过，证据`targeted-final.xml/log`。20项是552中的子集，不能加总成572。
- MockTransport覆盖503、401、400、ReadTimeout、ConnectError，每例真实SDK只发起1个模拟请求，失败均UNAVAILABLE/executionAllowed=false；200但伪造Chunk也失败；正常200仅接受真实证据ID。
- 墙钟限时测试确认取消等待且不重试；专用政策工厂关闭thinking不影响普通聊天；SUCCESS、NO_MATCH、ES_UNAVAILABLE政策回合均没有额外模型摘要调度。
- 首次专项曾出现4项测试夹具失败（过短测试时限导致首轮懒初始化超时、未注入Redis Mock），已完善夹具并通过；初次日志保留，不伪称始终一次通过。
- 测试使用假配置、隔离工作目录、出站网络阻断和MockTransport；网络阻断安全用例日志保留。没有重新执行真实LLM、Embedding、金融或邮件操作。

## Java 349与第26阶段1034的范围核对

| Maven模块 | 第26阶段保存的结果 | 第27阶段专项结果 |
| --- | ---: | ---: |
| Simlect-common | 229 | 229 |
| Simlect-gateway | 41 | 未重跑 |
| Simlect-product/app | 122 | 未重跑 |
| Simlect-stock/app | 39 | 未重跑 |
| Simlect-search | 117 | 120 |
| Simlect-order/app | 390 | 未重跑 |
| Simlect-pay/app | 65 | 未重跑 |
| Simlect-cart/app | 31 | 未重跑 |
| 合计 | 1034，选定8模块 | 349，仅Common+Search |

证据为 `.cache/stage26/results/java-summary.json`（及当时java-release/search-release日志）与`.cache/stage27/results/java-final-summary.json`、`java-approved-tests.log`。第26阶段其余6模块688项本次未覆盖，Search相对新增3项，所以第27阶段229+120=349，不是删掉或跳过685项测试，也不是测试用例异常减少。

**第27阶段Java是专项回归；第26阶段1034也是选定模块回归，不能扩大为全仓所有微服务/真实数据库集成测试。本轮未修改Java，没有新增执行Java测试，更不能把历史349或1034当本次新结果。** Maven打包-DskipTests不计入测试通过。

## 待授权的一次受控真实验收

当前只完成源码与Mock；现有服务没有重启，故运行进程仍是修复前代码。建议用户确认后：备份Agent当前日志、仅重新加载Agent；使用同一已验证的法规证据，**最多一次DeepSeek政策辅助JSON选择、零自动重试、20秒墙钟、512输出Token**。为严格只产生这一次模型调用，可用受控入口复用已有真实RAG证据，不重复Embedding、不重跑Supervisor或摘要。不得把旁路单次API成功当完整UI验收；如还要求全链路，应另明确授权一次问题Embedding。

记录call_id、实际HTTP次数、状态、完整耗时、供应商usage；失败立即停止，不补试、不切换供应商。预期结果必须是受验证Chunk ID/补充事实字段或明确UNAVAILABLE，不得承诺退货退款。当前**尚未获得这次真实调用授权，未执行**。


## 单次受控真实运行最终补充（2026-11-03）

仅重载Agent，新PID13976，其他服务保持原PID。本次仅新增独立售后消息31；问题Embedding1次成功、36 Token；DeepSeek1次HTTP200响应头后整体辅助20.797秒TimeoutError、usage未知，无自动重试或额外模型摘要，61个文档向量未重新处理。

同时发现biz_data VARCHAR(2000)写入5段结构化证据失败（MySQL1406）。2307字降级原文已保存、status=2，但biz_data为null，当前页面显示服务暂时不可用。因此本次真实端到端验收**未通过**，不能用HTTP200/status=2、Mock通过或Agent健康替代成功。已停止，不追加真实调用，也未修复新发现的持久化问题。

本次仅22项Python政策专项Mock预检通过；未新增执行Java/前端测试。此前Java349仅Common+Search专项；第26阶段1034为选定8模块，不是全仓集成测试。本次结果和费用单独记录，不改写原阶段历史成功/失败及Token记录。

详情见[27-单次受控真实API验收结果.md](./27-单次受控真实API验收结果.md)。
