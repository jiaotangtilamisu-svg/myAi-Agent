# 第28阶段RAG政策检索质量优化报告

## 保留的架构与数据

继续使用现有Embedding、simlect_vectorstore及Java政策目录。法规文档f85d1c36-053a-430b-a05f-e9ce88810e99仍为PUBLISHED/approved=1/revision=1/indexedRevision=1/READY，61个已存在向量保持不变。未改法规原文、未重新切分入库、未重新Embedding、未发布其他政策。

## 检索和展示改动

原search_policy先做向量召回与阈值判断，再用Java目录验证发布状态、类别、有效期、版本及原文sha256；本轮保留这些强制校验。之后按查询词/中文连续双字与正文/章节的重合数重排，以向量分数打破并列。说明：这是已有向量候选内的确定性重排，不是新增BM25双路召回或交叉编码器。

去重使用(documentId,revision,chunkId)及同文档同版本规范化文本；排除独立标题/章标题。相同章节中完全被另一片包含的重复文本压缩；相邻精确重叠仅在展示副本中合并，并保留sourceChunkIds。不同条文不得因模板相似而删除。正式结构化hits仍保留原始正文、Chunk ID、版本、来源、章节及有效期，原文不被拼接改写入索引。最多5条检索证据，正文最多展示3条精简引用。

新增concise渲染：先给有限结论，再列出处和标明节选的原文，再列购买渠道、品类、签收时间、完好/质量等待核实信息与人工下一步。超过七天不直接承诺可退或不可退；换货只说明查询政策，没有提交申请。国家法规、行业参考、平台演示规则分开，未入库的消保法全文及商城承诺不得补造。完整原文通过原折叠证据界面查看，正文不再重复贴整篇。

## 异常与测试

保留NO_MATCH、LOW_RELEVANCE、EMBEDDING_FAILED、ES_UNAVAILABLE、CATALOG_UNAVAILABLE、RETRIEVAL_ERROR各自提示。模型失败不抹掉已核实来源；数据库保存失败单独标记，不能变成成功。

Mock测试覆盖重复ID/重复条文、相邻片段精确重叠、保留不同条件、标题过滤、各检索异常、规则型回答、无依据不承诺、完整JSON及持久化边界。浏览器确认正文简明、完整证据可展开，并保留END_OF_EVIDENCE尾标。该页面的政策正文明确为TEST ONLY，不是本轮真实检索回答。

## 未验收与边界

未运行新真实Embedding查询或真实DeepSeek问答，因此不能宣称四个法律问题的本轮真实语义召回准确率已验收；本轮只实测61向量数量及发布元数据、完成Mock回归。当前只入库实施条例，其他引用法律全文/商城正式政策仍可能缺失。低相关度阈值继续0.75，未凭Mock数据擅自降低阈值。

## 验证范围与数据保护

本轮Python完整运行既有Agent tests与tools/data_governance/tests，共634通过、0失败、0跳过；其中新增63例（质量49、整图14）。Java仅5个指定测试类43例通过，不是全仓回归，也不应与第26阶段1034例直接比较。前端Node测试31例通过，类型检查和生产构建通过。浏览器另有11次快捷按钮点击，属于隔离HTTP记录验证，不能当作真实模型回答。

真实LLM调用0，真实Embedding调用0；无迁移、无商品/订单/库存写入、无政策发布/审批、无Git提交。正式聊天本轮前后为51条且逐行哈希相同，商品12/SKU13/库存12/订单4保持不变；法规仍PUBLISHED、revision=1、READY、61个向量。第27阶段曾记录31条，本轮开始快照已为51条，不能把不同阶段的数量当成本轮新增。

原始证据：[.cache/stage28/results/python.xml](E:/Simlect-AI-Mall-main/Simlect-AI-Mall-main/.cache/stage28/results/python.xml)、[.cache/stage28/results/java-summary.json](E:/Simlect-AI-Mall-main/Simlect-AI-Mall-main/.cache/stage28/results/java-summary.json)、[.cache/stage28/results/frontend-tests.log](E:/Simlect-AI-Mall-main/Simlect-AI-Mall-main/.cache/stage28/results/frontend-tests.log)、[.cache/stage28/results/frontend-build.log](E:/Simlect-AI-Mall-main/Simlect-AI-Mall-main/.cache/stage28/results/frontend-build.log)、[.cache/stage28/results/audit.json](E:/Simlect-AI-Mall-main/Simlect-AI-Mall-main/.cache/stage28/results/audit.json)、[.cache/stage28/results/source-manifest.json](E:/Simlect-AI-Mall-main/Simlect-AI-Mall-main/.cache/stage28/results/source-manifest.json)。
