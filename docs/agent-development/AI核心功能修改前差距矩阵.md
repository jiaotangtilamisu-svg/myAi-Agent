# AI核心功能审计：修改前差距矩阵

本矩阵在本轮业务修改前生成。源码盘点及所有阶段报告的全文扫描摘要保存在.cache/core-audit-20261105/source-report-inventory.json；全文扫描不等于逐文件人工证明正确。本轮以真实调用链和新增测试复核，不沿用历史通过数量。

| 功能 | 修改前判定 | 源码/链路依据与缺口 |
|---|---|---|
| 导购品类预算、多轮比较 | 已实现但存在问题 | Agent app/shopping/requirements.py、graph.py、selection.py、runner.py；材质/尺寸缺显式解析、软品牌偏好可能硬排除 |
| 混合召回、RRF、Java回源 | 已完整实现（源码路径） | product_service.py、mcp_tool_router.py -> Gateway -> ProductAgentInternalController；真实付费向量运行尚无法验证 |
| 本人订单、详情、物流 | 已完整实现（已有接口与权限测试） | MCP QUERY_ORDERS/QUERY_LOGISTICS -> OrderAgentInternalController；本轮需重跑订单安全回归 |
| 有效政策/版本来源/去重 | 已完整实现（代码与Mock） | rag/retriever.py、policy.py -> Search政策状态与索引；不得新增真实API调用 |
| 售后资格判断 | 部分实现 | aftersales_diagnosis.py确定性事实/冲突与不确定性；并非覆盖所有商品与商城规则的自动法律裁决 |
| 方案、确认、提交、进度 | 已实现但存在问题 | Java create为AWAITING_USER草稿，CONFIRM才提交；用户原因只在审计，列表详情展示不直观 |
| 人工审批、角色、并发/幂等 | 已完整实现（需本轮测试） | AftersalesCaseService、CaseAuthentication、AftersalesCaseMapper |
| 用户填写退货物流 | 未实现 | RETURN_LOGISTICS仅管理员入口；用户无端点无表单 |
| 物流进度/异常 | 部分实现 | 仅运单及验收审计，无退货物流状态查询投影或人工异常跟进 |
| 退货验收 | 已完整实现（源码） | RETURN_ACCEPT须管理员处理人、已有运单、记录验收意见 |
| 模拟退款成功/失败/重试 | 已实现但存在问题 | 默认关闭，稳定单号和成功防重复；管理UI无模拟失败选择，详情无汇总结果 |
| 真实退款 | 安全关闭/未运行验收 | 原商城Pay渠道保留；Agent与案件无真实执行依赖，不扩大资金授权 |
| Supervisor/MCP/RAG/历史/降级/持久化/证据 | 已保留，需本轮回归 | 现有独立图与服务不重写；浏览器交互不能以健康检查替代 |

计划最小范围：复用案件审计增加用户归属校验的运单登记、管理员退货进度/异常记录与详情投影；补足管理及用户界面；修复购物条件解析。无新增数据库表或迁移，不调用真实金融/模型API。最终状态以实际测试和页面验收为准。
