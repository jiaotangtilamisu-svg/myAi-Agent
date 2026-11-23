# 真实LLM与Embedding验收状态

本报告只使用本轮实际执行证据，更新时间：2026-11-06T16:27:01+08:00。

隔离批次 `8b75daf15e`；Git 分支 `feat/agent-safe-advice-product-search`，基线 `14726bf267daf7a3ffb622f5f3dff92e427a2541`。未提交、未重置 Git，保留原有修改。正式业务与测试数据分别统计。

最终统一运行：[完整门禁与 Playwright HTML/JSON 结果目录](<E:/Simlect-AI-Mall-main/Simlect-AI-Mall-main/.cache/stage34/8b75daf15e/runs/20261106-160904776>)；汇总：[acceptance-summary.json](<E:/Simlect-AI-Mall-main/Simlect-AI-Mall-main/.cache/stage34/8b75daf15e/acceptance-summary.json>)。

浏览器执行口径：7项业务结果来自 [本轮完整套件原始记录](<E:/Simlect-AI-Mall-main/Simlect-AI-Mall-main/.cache/stage34/8b75daf15e/runs/20261106-154006770>)，该次恢复项失败；修复Windows日志管道等待后，恢复专项1项在最终运行通过。合计8个不同用例最近结果通过，**不是一次8/8全绿**，失败轮次未隐藏。Python/Java/前端门禁与浏览器门禁分别保留。

**未执行，不能标记通过。** 真实 DeepSeek 外发 0 次、真实 Embedding 外发 0 次，新增真实 API Token 消耗为 0。未重新 Embedding 61 个正式法规 Chunk。

本地出口拒绝请求统计：LLM 5 次、Embedding 13 次。这些是本地 503/降级验证，forwarded=false，不是服务商请求，也不产生模型费用。没有启用真实请求开关。脱敏原始记录：[egress.jsonl](<E:/Simlect-AI-Mall-main/Simlect-AI-Mall-main/.cache/stage34/8b75daf15e/egress.jsonl>)。

自动审批此前拒绝了“新增商品向量化”的真实调用准备，理由是超出已限定的法规验收范围。因此没有运行该真实探针，也没有通过其他路径规避。现有配置仅由本地出口服务在内存读取；报告不包含密钥或认证头。

已有技术限额：最多 4 LLM/6 Embedding，512 输出 Token、20 秒总期限、零自动重试；首个超时、429或5xx会锁止。限额不是授权本身。未来恢复建议进一步缩小为一次法规查询 Embedding 加一次政策说明 DeepSeek，不处理商品向量、不新增法规、不重做61块，先确认具体范围后执行。

自然语言规则识别、多轮状态和本机业务流程已测试；真实模型的意图理解、政策解释和 Supervisor 推理质量仍未验收。不得用 Mock 成功补写这些结果。
