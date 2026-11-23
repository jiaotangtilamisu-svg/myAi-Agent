# 第33阶段导购Agent验收

本轮执行记录以2026年11月5日本机日志时间为准，2026年11月6日完成交付整理。未调用真实LLM或Embedding（均为0），未下单、支付或真实退款；未发布政策，未重新处理61个已发布法规向量。当前目录的价格和库存属于本地配置，不冒充供应商实时商业数据。Mock、真实隔离MySQL/ES、本机公开接口、真实浏览器分别列明，不能互相替代。

原独立Shopping LangGraph保持不变，修复条件进入召回前后的契约。需求解析区分硬brands/attributes与preferredBrands/preferredAttributes；上下限、严格上下限、模糊偏好不混用。三星/Samsung/Galaxy、小米/Xiaomi/Redmi、苹果/Apple/iPhone等品牌别名统一。增加材质、容量、功率、处理器、耳机类型/连接方式等类型化提取，CPU型号i7-13650不再误作7～13650元价格。

Java品牌属性是第一依据；无品牌属性时只允许明确厂牌名称前缀作为PRODUCT_NAME_PREFIX证据，不接受LLM猜测。兼容/适用苹果的配件不能当Apple品牌，苹果味果汁不能当苹果手机。三星Galaxy紧邻中文前缀能正确识别。属性冲突继续拒绝，未把来源自动升级REAL。

推荐逐个SKU同时检查价格、属性和库存，不用商品最低价配另一个SKU库存。未知价格不进硬预算，未知库存保持null，真实零库存排除；库存异常状态单独保留。字段不完整、重复SKU/商品事实不随意选一个。评分仍是证据完备度与偏好匹配，不是虚构用户评分。

|实际输入|结果|推荐数|
|---|---|---:|
|推荐5000以上的三星手机|SUCCESS|2|
|帮我推荐20以内的茶杯|NO_RESULTS|0|
|帮我推荐预算20元以内的茶杯|NO_RESULTS|0|
|推荐200元以内的耳机|SUCCESS|3|
|推荐8000以上的手机|SUCCESS|3|
|最好是苹果|SUCCESS|3|
|最好有512GB存储|SUCCESS|3|
|价格提高到10000元以上|SUCCESS|3|
|不要苹果，换成华为|NO_MATCHING_SKU|0|
|只推荐有现货的商品|NO_MATCHING_SKU|0|

5000元以上三星真实链路返回2款，都有Java品牌依据且每个合格SKU不少于5000元。两种20元以内茶杯表达均无匹配，未拿其它品类凑数。当前目录为本地设价和库存，不是商业实时供应链验收。

三款3000元以内手机召回后，按第一、第二款对比，实际GET_PRODUCT_DETAIL返回ID与前轮前两项一致。轻薄续航偏好笔记本执行了SEARCH_PRODUCTS/GET_PRODUCT_DETAIL，但未将缺失续航属性冒充已知。MCP日志包含REMOTE_MCP、传输完成及业务SUCCESS，见[.cache/stage33/local-reads.log](<E:/Simlect-AI-Mall-main/Simlect-AI-Mall-main/.cache/stage33/local-reads.log>)；图→工具为真，模型建议和状态推送有明确Mock，不冒充HTTP聊天全闭环。

|层次|通过|失败|跳过|边界|
|---|---:|---:|---:|---|
|Python全量|1304|0|0|Agent/tests及data_governance/tests；外部网络隔离|
|Java根POM全模块test|1592|0|2|默认H2/Mock及单元；不等于真实MySQL或生产验收|
|最后品牌前缀修正后的Java专项补跑|513|0|0|common 229、product 149、search 135；与上一行重叠，不能相加冒充全量|
|商城Node测试|65|0|0|协议与工具函数；另有真实浏览器只读检查|
|Admin Node测试|24|0|0|协议与工具函数|
|隔离真实Java HTTP/MySQL及ES|21|0|0|9个实际HTTP查询+12个ES DSL检查；六条合成Fixture，实际存储和查询|
|隔离MySQL售后案件|79|0|0|实际Controller/Service/事务/MyBatis/订单归属SQL；身份会话Fixture|
|隔离MySQL消息持久化|23|0|0|真实SQL，模型异常和WS注入|
|本机真实公开业务图|13|0|0|LangGraph→远程MCP→Gateway→Java/Stock/Search；政策模型建议和通知Mock|
|本机硬品牌多轮图|4|0|0|三星→苹果→预算修改→256GB；直接传递图上下文，未写正式消息|
|本机搜索表达|10|0|0|实际Gateway/Search/ES商品ID与顺序断言|
|只读运行契约|7|0|0|4项未登录拒绝、2个Vite模块、61条法规向量摘要|
|服务健康|14|0|0|仅健康/端口，不代替业务验收|
|显式关键突变|11个杀死|0个存活|0|价格、库存、意图、模式等小范围探针，不是全项目突变覆盖率|

两项Java跳过为既有AliEmail测试`placeholder`、`serviceImplementsEmailService`，类级禁用；未发送邮件。前后端生产构建及商城vue-tsc均通过。Ruff仅执行F821/F823关键错误检查并通过，未自动修复全项目格式遗留问题。未将循环内部160/150/80次组合和随机输入计作同等数量的独立pytest用例。

独立断言位于[tools/quality_engineering/oracles.py](<E:/Simlect-AI-Mall-main/Simlect-AI-Mall-main/tools/quality_engineering/oracles.py>)，从原始Java标准化商品与SKU计算预算、可售状态、价格/库存一致性，不使用LLM自评。新增专项[Simlect-backend/Simlect-agent/tests/test_stage33_contracts.py](<E:/Simlect-AI-Mall-main/Simlect-AI-Mall-main/Simlect-backend/Simlect-agent/tests/test_stage33_contracts.py>)25项。

尚未验证的边界：真实DeepSeek及付费Embedding双路召回/RRF参与未获授权；本轮没有发送或保存正式账户新聊天消息，因此没有把直接调用图、身份Fixture或历史消息页面冒充全新已登录HTTP/WS闭环。当前生产服务指向正式开发库，整套身份、消息、案件与浏览器写操作仍需独立隔离环境。管理员审批、物流验收和退款操作没有在正式案件上执行；真实物流承运商及真实资金渠道未验收。

当前单用户历史会话模式不等同于多独立conversationId聊天系统。未登录、越权、串用户、损坏上下文已有自动化断言，但多独立会话标签页的完整真实浏览器并行隔离尚未证明。缺少可信属性或来源时继续拒绝或标为未知，不自动修补正式商品资料。未开展容量压测、长时故障恢复或任意输入永不出错的证明。
