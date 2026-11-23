# Supervisor实际双Agent验收

本报告只使用本轮实际执行证据，更新时间：2026-11-06T16:27:01+08:00。

隔离批次 `8b75daf15e`；Git 分支 `feat/agent-safe-advice-product-search`，基线 `14726bf267daf7a3ffb622f5f3dff92e427a2541`。未提交、未重置 Git，保留原有修改。正式业务与测试数据分别统计。

最终统一运行：[完整门禁与 Playwright HTML/JSON 结果目录](<E:/Simlect-AI-Mall-main/Simlect-AI-Mall-main/.cache/stage34/8b75daf15e/runs/20261106-160904776>)；汇总：[acceptance-summary.json](<E:/Simlect-AI-Mall-main/Simlect-AI-Mall-main/.cache/stage34/8b75daf15e/acceptance-summary.json>)。

浏览器执行口径：7项业务结果来自 [本轮完整套件原始记录](<E:/Simlect-AI-Mall-main/Simlect-AI-Mall-main/.cache/stage34/8b75daf15e/runs/20261106-154006770>)，该次恢复项失败；修复Windows日志管道等待后，恢复专项1项在最终运行通过。合计8个不同用例最近结果通过，**不是一次8/8全绿**，失败轮次未隐藏。Python/Java/前端门禁与浏览器门禁分别保留。

真实页面输入“查询现有售后政策，另外推荐5000元以内的手机”。最终持久化计划含 aftersales 和 shopping 两项；results 同时含两个专业 Agent，均为 SUCCESS。商品结果逐 SKU 对照 MySQL；政策结果验证文档 ID、Chunk、revision=1、司法部来源说明和 originalUrl 官方主机名。

返回的是两个现有独立工作流实际业务结果，非路由文字。页面刷新后同 messageId 的 bizData 原样恢复。截图：[18-supervisor-two-agent-results.png](<E:/Simlect-AI-Mall-main/Simlect-AI-Mall-main/.cache/stage34/8b75daf15e/browser-artifacts/18-supervisor-two-agent-results.png>)、[19-supervisor-refresh-persisted.png](<E:/Simlect-AI-Mall-main/Simlect-AI-Mall-main/.cache/stage34/8b75daf15e/browser-artifacts/19-supervisor-refresh-persisted.png>)。

此前 Search 不可用时曾出现售后 ERROR/导购 SUCCESS，系统保留部分成功，不伪造成全成功。对应失败尝试保留在 [browser-attempts](<E:/Simlect-AI-Mall-main/Simlect-AI-Mall-main/.cache/stage34/8b75daf15e/browser-attempts>) 和 runs 各次结果中；最终双 Agent 成功以最终统一运行结果为准。

仅验证本机业务调度；付费模型出口关闭。各专业 Agent 仍自行校验身份，Supervisor 不赋予订单访问或退款执行权限。没有以两个 Agent 的单元测试代替这次真实调度。
