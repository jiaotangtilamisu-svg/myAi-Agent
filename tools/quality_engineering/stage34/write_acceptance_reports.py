"""Render acceptance reports from recorded public evidence; never changes data."""
import json
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RUN = Path(json.loads((ROOT / '.cache/stage34/active.json').read_text())['directory'])
OUT = ROOT / 'docs/agent-development'


def read(file):
    data = Path(file).read_bytes()
    return data.decode('utf-16' if data.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig')


def load(file):
    return json.loads(read(file))


def link(file, title=None):
    p = Path(file)
    if not p.is_absolute():
        p = ROOT / p
    return f'[{title or p.name}](<{p.as_posix()}>)'


def main():
    candidates = sorted((RUN / 'runs').glob('*/gates.json'))
    current = candidates[-1].parent
    gates = load(current / 'gates.json')
    if not any(g['gate'] == 'disposable-test-data-cleanup' for g in gates):
        raise RuntimeError('FINAL_BROWSER_AND_CLEANUP_GATES_REQUIRED')
    if any(g['exitCode'] for g in gates):
        raise RuntimeError('FAILED_GATES_MUST_BE_REVIEWED_BEFORE_FINAL_REPORT')
    regression = current / 'regression'
    regression.mkdir(exist_ok=True)
    source = ROOT / '.cache/quality-engineering-20261105'
    for name in ['summary.json', 'gates.json', 'python-all.xml', 'python-all.log',
                 'java-all.log', 'web-tests.log', 'web-build.log', 'admin-tests.log',
                 'admin-build.log', 'mutation.json', 'mutation.log', 'runtime-health.json']:
        if (source / name).exists():
            shutil.copy2(source / name, regression / name)
    summary = load(regression / 'summary.json')
    e2e = load(current / 'playwright-results.json')
    raw_stats = e2e['stats']
    stats = dict(raw_stats)
    business_evidence = current
    def project_tests(report, project):
        rows=[]
        def collect(suite):
            for spec in suite.get('specs', []):
                rows.extend(t for t in spec.get('tests', []) if t.get('projectName') == project)
            for child in suite.get('suites', []):collect(child)
        for suite in report.get('suites', []):collect(suite)
        return rows
    split_run = len(project_tests(e2e, 'business')) == 0
    if split_run:
        # Keep the failed full run intact. Count the seven business cases only
        # from that run, plus the successfully rerun recovery case exactly once.
        prior = sorted(p for p in (RUN/'runs').glob('*/playwright-results.json') if p.parent < current)
        business=[]
        for candidate in reversed(prior):
            rows=project_tests(load(candidate), 'business')
            if len(rows)==7 and all(t['status']=='expected' for t in rows):
                business=rows;business_evidence=candidate.parent;break
        if len(business) != 7:
            raise RuntimeError('PREVIOUS_SEVEN_BUSINESS_CASES_NOT_PASSED')
        if raw_stats['expected'] != 1 or raw_stats['unexpected'] or raw_stats['skipped']:
            raise RuntimeError('RECOVERY_RERUN_NOT_PASSED')
        stats['expected'] += len(business)
        stats.pop('duration',None);stats.pop('startTime',None)
        stats['scope']='latest result of eight unique cases across separate invocations; no combined duration'
    sql = load(RUN / 'browser-sql-oracle.json')
    primary = load(RUN / 'browser-primary-return.json')
    cleanup = load(RUN / 'browser-cleanup.json')
    final_data = load(RUN / 'browser-database-before-cleanup.json')
    compare = load(RUN / 'formal-data-comparison.json')
    es = load(RUN / 'es-readonly-proof.json')
    repair = load(RUN / 'policy-vector-copy-repair.json')
    mutation = load(regression / 'mutation.json')
    isolated_health=load(RUN/'isolated-health-final.json')
    formal_health=load(RUN/'formal-health-final.json')
    ports=load(RUN/'plan.json')['ports']
    if any(h['http']!=200 or not h['identityMatches'] or not h['listenerMatches'] for h in isolated_health):
        raise RuntimeError('FINAL_SERVICE_HEALTH_NOT_VERIFIED')
    agent_health=next(h for h in isolated_health if h['service']=='agent')
    if agent_health['status']!='ok' or agent_health['javaWeb'] is not True:
        raise RuntimeError('FINAL_AGENT_DEPENDENCY_HEALTH_NOT_OK')
    health_table='| 隔离服务 | 实际PID | 端口 | HTTP/业务状态 | 身份及监听核对 |\n|---|---:|---:|---|---|\n'+''.join(
        f"| {h['service']} | {h['pid']} | {ports[h['service']]} | {h['http']}/{h['status'] or '页面'} | 一致 |\n" for h in isolated_health)
    page_errors = [json.loads(s) for s in read(RUN / 'browser-artifacts/page-errors.jsonl').splitlines() if s.strip()]
    api = [json.loads(s) for s in read(RUN / 'egress.jsonl').splitlines() if s.strip()]
    paid = {kind: sum(r.get('kind') == kind and r.get('forwarded') is True for r in api)
            for kind in ['llm', 'embedding']}
    blocked = {kind: sum(r.get('kind') == kind and r.get('forwarded') is False for r in api)
               for kind in ['llm', 'embedding']}
    if any(paid.values()):
        raise RuntimeError('REAL_API_RESULTS_REQUIRE_SEPARATE_REVIEW')
    evidence = {
        'runId': RUN.name, 'finalRun': str(current), 'browser': stats,
        'browserFinalInvocation':raw_stats, 'businessEvidenceRun':str(business_evidence),
        'browserExecutionMode':'7 business + 1 repaired recovery, separate invocations' if split_run else 'full single invocation',
        'python': summary['python'], 'java': {k: v for k, v in summary['java'].items() if k != 'classes'},
        'web': summary['web'], 'admin': summary['admin'], 'sql': {k: v for k, v in sql.items() if k != 'rules'},
        'mutation': {k: v for k, v in mutation.items() if k != 'mutants'},
        'paidForwarded': paid, 'paidBlockedLocally': blocked,
        'cleanupVerified': cleanup['verified'], 'formalTablesChanged': compare['changedTables'],
        'casesBeforeCleanup': len(final_data['cases']), 'auditBeforeCleanup': len(final_data['audit']),
        'messagesBeforeCleanup': len(final_data['messages']), 'primaryCase': primary,
        'realModelAccepted': False, 'independentConversationIdAccepted': False,
        'isolatedServicesVerified':len(isolated_health),'formalHealthy':formal_health['Passed'],
    }
    (RUN / 'acceptance-summary.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf8')
    py, java = summary['python'], summary['java']
    common = f'''本报告只使用本轮实际执行证据，更新时间：{datetime.now().astimezone().isoformat(timespec='seconds')}。

隔离批次 `{RUN.name}`；Git 分支 `feat/agent-safe-advice-product-search`，基线 `14726bf267daf7a3ffb622f5f3dff92e427a2541`。未提交、未重置 Git，保留原有修改。正式业务与测试数据分别统计。

最终统一运行：{link(current, '完整门禁与 Playwright HTML/JSON 结果目录')}；汇总：{link(RUN / 'acceptance-summary.json')}。

浏览器执行口径：7项业务结果来自 {link(business_evidence, '本轮完整套件原始记录')}，该次恢复项失败；修复Windows日志管道等待后，恢复专项1项在最终运行通过。合计8个不同用例最近结果通过，**不是一次8/8全绿**，失败轮次未隐藏。Python/Java/前端门禁与浏览器门禁分别保留。
'''
    results = f'''| 层次 | 通过 | 失败 | 跳过 | 说明 |
|---|---:|---:|---:|---|
| Python 单元/Mock 全量 | {py['passed']} | {py['failures'] + py['errors']} | {py['skipped']} | 外部网络被测试 harness 阻断 |
| Java Maven reactor 测试 | {java['passed']} | {java['failed']} | {java['skipped']} | 发现 {java['discovered']} 项；非真实支付/邮件集成 |
| 商城前端 Node 测试 | {summary['web']['passed']} | {summary['web']['failed']} | {summary['web']['skipped']} | 类型检查及生产构建另行通过 |
| Admin 前端 Node 测试 | {summary['admin']['passed']} | {summary['admin']['failed']} | {summary['admin']['skipped']} | 生产构建另行通过 |
| Playwright 真实隔离页面 | {stats['expected']}个不同用例 | {stats['unexpected']}（最近结果） | {stats['skipped']} |7项业务+1项修复后恢复，分次执行；完整尝试曾有失败，原始记录保留 |
| 独立只读 SQL 断言 | {sql['passed']} | {sql['failed']} | 0 | {sql['assertions']} 条规则，不能与浏览器测试相加 |
| 手工选择的源码变异 | {mutation['killed']} killed | {mutation['survived']} survived | 0 | 不是全项目变异覆盖率 |
| 真实 DeepSeek / Embedding | 0 | 0 | 不适用 | 外发 {paid['llm']} / {paid['embedding']}；未验收 |

Java 跳过：`com.simlect.biz.impl.AliEmailServiceImplTest.placeholder`、`serviceImplementsEmailService`。类级 `@Disabled`：内部直接 new 阿里云客户端并依赖真实 DirectMail 网络，不能纯单测。不是退款、订单归属或支付回调测试跳过。没有把跳过算作通过。

{link(regression / 'summary.json', '本轮自动化计数原始结果')}。各层不得相加为一个虚假的端到端测试总数。

执行范围：Python/Java/Admin为本轮14:58启动的完整回归；订单页面最后修复后，商城前端重新执行70项测试和类型检查/生产构建。浏览器完整套件执行后，恢复用例单独修复并复测；没有将这次专项描述成8项一次全绿，也没有拿历史阶段数字充当本轮结果。
'''
    images = RUN / 'browser-artifacts'
    main_audit = [r for r in final_data['audit'] if r['caseId'] == primary['caseId']]
    (RUN / 'primary-return-audit.json').write_text(json.dumps(main_audit, ensure_ascii=False, indent=2), encoding='utf8')
    states = ' → '.join(primary['actions'])
    docs = {}
    docs['34-01-独立测试环境与数据隔离报告.md'] = f'''# 独立测试环境与数据隔离

{common}
已执行隔离，不只修改库名：9 个 `q34_{RUN.name}_*` schema、每个 Java 服务单独受限账号、连接属性 `quality34_service`、Python aiomysql 独立 Agent 库、Nacos Group `QUALITY34_{RUN.name}`、独立 RabbitMQ vhost 和用户、Redis 26379 专用容器及独立数据卷。正式配置 `.env` 未覆盖。

ES 经 19200 网关限制为两个明确的隔离索引，拒绝正式索引写入、别名和 reindex 等逃逸操作。曾实际验证拒绝正式索引写入。证据：{link(RUN / 'isolation-verified.json')}、{link(RUN / 'mysql-sessions.json')}、{link(RUN / 'database-grants.json')}。

测试夹具：2 个普通用户、1 个测试管理员、6 件商品、10 个 SKU、9 条库存、6 个订单。价格、库存、物流和账号全部合成。缺失库存故意留 null，茶杯库存为 0。公开法规只读复制，不复制正式用户和订单。

商城 `http://127.0.0.2:16001/`；Admin `http://127.0.0.2:16002/admin/`。正式 6001/6002 已核实，但可写验收明确拒绝使用正式端口。

本轮没有执行正式数据库迁移；创建隔离结构前保存 schema-only 备份。只读比较 {compare['checkedTables']} 张正式表，变化 {len(compare['changedTables'])} 张：{link(RUN / 'formal-data-comparison.json')}。这证明所列数据快照一致，不代表扫描所有可能的外部系统。

清理前案件 {len(final_data['cases'])}、审计 {len(final_data['audit'])}、消息 {len(final_data['messages'])}；清理后浏览器生成案件与消息为 0。保留小样本夹具、账号及法规副本以便复用，不 drop 库、不删容器或卷、不 FLUSH Redis。{link(RUN / 'browser-cleanup.json')}。

最终隔离服务核对：{link(RUN / 'isolated-health-final.json')}；正式14服务中健康 {formal_health['Passed']}、失败 {formal_health['Failed']}，时间 {formal_health['CheckedAt']}，只读检查未重启正式服务。

{health_table}
隔离Agent的java_web=true、status=ok。进程比对包含PID、CreationDate、ExecutablePath、完整命令行及监听归属，未只看PID。源码版本哈希：{link(RUN / 'source-versions.json')}。
'''
    docs['34-02-AI退货完整浏览器验收报告.md'] = f'''# AI退货完整浏览器验收

{common}
**隔离页面及真实业务持久化闭环通过；真实模型参与部分未执行。** 不将规则识别成功描述为 DeepSeek 验收。

本次最终主案件 `{primary['caseId']}`，订单 `{primary['orderId']}`，状态 `{primary['state']}`。所有业务写入来自专用 Chromium 页面点击；SQL 仅 SELECT 验证。没有 HTTP 脚本代替用户确认或管理员审批。

真实操作：普通用户正常登录 → 本人订单 → 详情及 SKU → 客服“我要退货” → 多订单澄清 → 指定本人订单 → 有效法规证据 → 草稿 → 修改原因/材料并升版 → 确认 → 刷新 → 管理员审核/领取 → 用户登记测试物流 → 管理员验收 → 准备退款 → MOCK 处理中 → MOCK 成功 → 记录结果 → 归档 → 用户查询。

MCP真实调用审计只保留工具名称、传输/业务状态、messageId和耗时，见 {link(RUN / 'mcp-tools-audit-summary.json')}。全批次（包含重跑）观察到101条REMOTE_MCP完成且业务SUCCESS：QUERY_ORDERS 35、SEARCH_PRODUCTS 30、GET_PRODUCT_DETAIL 36。这不是101个独立场景，不与测试通过数相加。RAG还复用Search目录和检索接口，未伪装成额外MCP工具。

草稿 `AWAITING_USER` 产生 CREATE，不等于正式申请；本人确认后为 `ADMIN_REVIEW`。案件、方案和审计均真实持久化，法规证据带文档、Chunk、版本和来源。

完整 {len(main_audit)} 项审计：`{states}`。

证据：{link(RUN / 'primary-return-audit.json')}、{link(RUN / 'browser-primary-return.json')}、{link(images / '11-user-final-result.png', '用户归档与模拟结果截图')}、{link(images / '10-admin-mock-refund-succeeded.png', '管理员模拟结果截图')}、{link(images / 'shop-full-return.webm', '商城完整业务视频')}、{link(images / 'admin-full-return.webm', 'Admin完整业务视频')}。最后恢复专项的短视频另存为 shop-business.webm/admin-business.webm，不能用短视频冒充完整退货流程。

额外真实页面分支：A 查看 B 订单被拒；管理员驳回后用户修改并重新确认；双击确认没有增加重复 CONFIRM；模拟 FAILED 原退款号重试；UNKNOWN 未人工核实拒绝且审计不变；人工核实后同号成功；无商城终身退款政策不承诺。

未覆盖全部页面变体：重复登记物流与所有不允许订单状态主要由 Java 测试验证，本轮未各自完成独立浏览器分支。主链使用单明细测试订单，现有案件以订单关联并在诊断证据中保留商品/SKU，不能据此宣称已经验收多明细订单的逐件选择或部分金额退款。没有真实承运商、仓库或资金渠道。不能宣称所有售后条件已实现全自动判定。

{results}
'''
    docs['34-03-AI导购真实业务验收报告.md'] = f'''# AI导购本机业务验收

{common}
浏览器使用真实 Java Product/Stock/Search、MCP、MySQL 和隔离小样本。商品为合成测试数据，不是供应商真实售价或库存。本轮真实 Embedding 和 LLM 均未调用。

| 实际输入 | 数据断言 |
|---|---|
| 重新选，推荐5000元以上三星手机，256GB，有现货 | 仅 DEMO34S1；同 SKU 价格至少 5000、库存为对应记录 |
| 改成5000元以内苹果手机，256GB，有现货 | 仅 DEMO34A2；前一轮三星与下限条件不串扰 |
| 重新选，推荐两款手机 | 正好两款候选，不补造商品 |
| 比较第一款和第二款 | isComparison=true，两款不同 productId，保留上下文 |
| 重新选，推荐有现货的茶杯 | 库存 0，不作现货推荐 |

测试在页面发送自然语言后，以数据库消息的结构化结果逐 SKU 验证 productId/skuId、价格、库存查询状态和 queryTime。不只断言 HTTP 200。缺失库存保留 null，独立数据规则也覆盖该契约。

代码：{link('e2e/tests/shopping-supervisor.spec.mjs')}。截图：{link(images / '16-shopping-two-products-compared.png')}、{link(images / '17-zero-stock-no-fabricated-recommendation.png')}。

本轮浏览器验证关键词召回和 Java 回源；真实查询向量生成未验收。ES 原有向量自相似查询与 RRF 为另一层只读检查，不能算作真实自然语言混合检索通过。Apple/iPhone、Samsung/Galaxy 同义表达的更大语料由自动化测试覆盖，本轮页面只执行表内代表场景。
'''
    docs['34-04-Supervisor多Agent验收报告.md'] = f'''# Supervisor实际双Agent验收

{common}
真实页面输入“查询现有售后政策，另外推荐5000元以内的手机”。最终持久化计划含 aftersales 和 shopping 两项；results 同时含两个专业 Agent，均为 SUCCESS。商品结果逐 SKU 对照 MySQL；政策结果验证文档 ID、Chunk、revision=1、司法部来源说明和 originalUrl 官方主机名。

返回的是两个现有独立工作流实际业务结果，非路由文字。页面刷新后同 messageId 的 bizData 原样恢复。截图：{link(images / '18-supervisor-two-agent-results.png')}、{link(images / '19-supervisor-refresh-persisted.png')}。

此前 Search 不可用时曾出现售后 ERROR/导购 SUCCESS，系统保留部分成功，不伪造成全成功。对应失败尝试保留在 {link(RUN / 'browser-attempts')} 和 runs 各次结果中；最终双 Agent 成功以最终统一运行结果为准。

仅验证本机业务调度；付费模型出口关闭。各专业 Agent 仍自行校验身份，Supervisor 不赋予订单访问或退款执行权限。没有以两个 Agent 的单元测试代替这次真实调度。
'''
    docs['34-05-真实LLM与Embedding验收报告.md'] = f'''# 真实LLM与Embedding验收状态

{common}
**未执行，不能标记通过。** 真实 DeepSeek 外发 {paid['llm']} 次、真实 Embedding 外发 {paid['embedding']} 次，新增真实 API Token 消耗为 0。未重新 Embedding 61 个正式法规 Chunk。

本地出口拒绝请求统计：LLM {blocked['llm']} 次、Embedding {blocked['embedding']} 次。这些是本地 503/降级验证，forwarded=false，不是服务商请求，也不产生模型费用。没有启用真实请求开关。脱敏原始记录：{link(RUN / 'egress.jsonl')}。

自动审批此前拒绝了“新增商品向量化”的真实调用准备，理由是超出已限定的法规验收范围。因此没有运行该真实探针，也没有通过其他路径规避。现有配置仅由本地出口服务在内存读取；报告不包含密钥或认证头。

已有技术限额：最多 4 LLM/6 Embedding，512 输出 Token、20 秒总期限、零自动重试；首个超时、429或5xx会锁止。限额不是授权本身。未来恢复建议进一步缩小为一次法规查询 Embedding 加一次政策说明 DeepSeek，不处理商品向量、不新增法规、不重做61块，先确认具体范围后执行。

自然语言规则识别、多轮状态和本机业务流程已测试；真实模型的意图理解、政策解释和 Supervisor 推理质量仍未验收。不得用 Mock 成功补写这些结果。
'''
    docs['34-06-RAG政策检索质量报告.md'] = f'''# RAG政策检索质量

{common}
本轮保留国务院令第778号《中华人民共和国消费者权益保护法实施条例》已发布版本1，只读复制到隔离检索库，不审核、发布或修改正式法规。

发现并修复测试夹具缺陷：Elasticsearch 9 默认 `_source` 不返回 dense_vector。第一次复制实际仅含文本与元数据，不能据旧记录宣称61条向量已复制。现显式使用 `_source.exclude_vectors=false`，校验61条、每条1024维、有限非零数值，再只补齐隔离副本的原有向量字段，未生成新向量、未换文档ID。

正式源向量前后和隔离副本 SHA-256 一致：`{repair['isolatedSHA256']}`。文本元数据 SHA 保持 `{repair['textMetadataSHA256']}`。证据：{link(RUN / 'policy-vector-copy-repair.json')}。

独立真实 ES 查询：关键词命中 {es['keywordHits']}、已有向量自相似 Top-K 命中 {es['vectorHits']}、最高分 {es['selfSimilarityScore']}，共享 RRF 去重后 {es['rrfUniqueResults']} 条。{link(RUN / 'es-readonly-proof.json')}。

退货和 Supervisor 页面实际召回该文档，验证政策名称、版本、Chunk、官方链接；无商城自有终身退款规则时保留证据不足。国家法规没有变成商城承诺，资格不充分时转人工核实。

**边界：**已有向量自相似成功，不等于新的语义 query Embedding 成功。自然语言双路召回完整真实 API 验收未执行。过期、停用、版本冲突、去重及低相关度等更广场景由本轮 Python/Java 自动化测试覆盖，未对正式政策做状态变更。

实现与专项测试：{link('tools/quality_engineering/stage34/copy_policy.py')}、{link('tools/quality_engineering/stage34/vector_contract.py')}、{link('Simlect-backend/Simlect-agent/tests/test_stage34_vector_copy.py')}。
'''
    docs['34-07-多轮会话与消息恢复报告.md'] = f'''# 多轮会话与消息恢复

{common}
已执行：购物条件品牌/预算修改、序号比较；售后追问订单→补充原因→确认；三种模式切换；刷新恢复消息、结构化政策和案件；仅重启隔离 Agent 后恢复历史消息及已归档案件。重启测试前后逐条比较已有消息完整 JSON 和案件审计，没有以手工传 previous 状态代替页面恢复。

修复真实缺陷：案件进度请求缺少 Gateway `/api` 前缀；Supervisor 与售后共用 `load_case_progress`。LangGraph build_context 已完成进度响应后，原条件边仍继续 agent_loop，可能额外触发 LLM。新增 finalize 分支保留已有取消/诊断路径，成功和失败均不再误入模型。

关键源码：{link('Simlect-backend/Simlect-agent/app/services/aftersales_context.py')}、{link('Simlect-backend/Simlect-agent/app/supervisor/adapters.py')}、{link('Simlect-backend/Simlect-agent/app/graph/builder.py')}。新增9项专项测试：{link('Simlect-backend/Simlect-agent/tests/test_stage34_progress_route.py')}。

真实重启对比：{link(RUN / 'browser-restart-comparison.json')}；历史恢复截图：{link(images / '20-agent-restart-case-and-history-restored.png')}。故障注入按PID/CreationDate/命令行及端口核实后强制终止隔离Agent，再启动；不是对正式服务的优雅维护。测试断言恢复/进度查询未增加任何 LLM 请求，包括被本地拒绝的请求。

**未完成：同一用户的多个独立 conversationId。** 当前历史/记忆仍以用户和模式组织，不能宣称具有两个独立会话的完整隔离。不同用户订单权限与本轮A/B拒绝通过，不等于同用户双会话隔离。此项仍为架构能力缺口，未在浏览器整改中重写会话模型；M只能部分通过。
'''
    docs['34-08-系统稳定性与故障注入报告.md'] = f'''# 系统稳定性与故障注入

{common}
{results}
关键本轮修复：

| 根因 | 最小修复 | 实际回归 |
|---|---|---|
| 客服 z-index=10000 压住 Element Plus 确认框 | 客服改为1900，高于header、低于确认层 | 真实确认/审核可点击，无 force 点击 |
| 同一订单多案件列表缺少唯一可见标识 | 显示 caseId、可访问分组和 data-case-id | 精确定位新案件，不误操作旧案件 |
| 双击时确认框点击遮罩被关闭 | 复用 confirmAction，禁止点击遮罩关闭 | 双击只产生一次新的 CONFIRM |
| 案件进度 URL与图路由不一致 | `/api` 前缀、共用服务、finalize边 |9项专项及真实重启恢复 |
| ES9 复制遗漏真实向量 | 显式请求向量并校验 |12项专项、真实ES只读验证 |
| Windows启动/恢复记录JSON含BOM | 共用BOM兼容读取，保留非法JSON拒绝 |1项Node专项、Search启动及Agent恢复 |
| 订单/物流读取失败抛出未处理Object | 返回明确失败状态并清空旧数据 |4项前端专项、页面越权拒绝无新增pageerror |
| 隔离Search仅160MiB堆，实际发生Java heap space | 仅隔离Search改384MiB；启动前可用内存1797MiB | 保留exit99和OOM日志，恢复后完整重跑 |
| 恢复测试同步等待被子进程继承的Windows管道EOF | 启动/停止输出直接到独立日志文件 | 实际Agent已健康但旧测试ETIMEDOUT；修复后恢复专项通过，耗时见原始报告 |
| persistent context关闭后再调用video.saveAs导致协议已关闭 | 关闭前取得本地video.path，关闭后复制已完成文件，核对会话归属 | 原始业务录像保留并按画面核验恢复；新会话收尾独立验证 |
| 长历史超过22k诊断摘录导致测试看不到资金提示 | 改为定位最后一条消息中的当前案件区域，直接断言真实可见的归档/模拟成功/资金提示 | 保留全部业务断言，恢复专项重新通过 |

测试脚本也保留失败：一次把 source 描述当 URL 的断言失败，修正为严格验证 source + originalUrl + revision；没有删掉来源断言。PowerShell 单元素参数数组、沙箱内异步网络阻塞和BOM启动失败分别保留原始日志，不归为业务通过。

隔离Search早先退出事件原因未明；本次PID24088在15:28:13退出，native记录exit99，stdout/stderr均出现Java heap space，涉及Nacos、RabbitMQ消费者和ES客户端。**这次已确认Java堆耗尽**，不能再写成只有控制台猜测。单纯detached进程组并未解决内存不足。正式服务不变，仅隔离Search由160改384MiB后恢复，并重跑完整浏览器套件。此前其他退出是否同因仍未证实。{link(RUN / 'history/search-confirmed-oom-20261106-152813')}、{link(RUN / 'logs/search-20261106-145629994', '原始OOM日志')}、{link(RUN / 'browser-search-survival.json', 'Agent重启前后Search身份与健康')}。一次短期通过不证明没有内存泄漏或长期稳定性风险。

真实页面故障分支：模拟退款失败/UNKNOWN/人工核实、订单越权、无商城政策、双击确认；真实隔离Agent重启产生WebSocket断连并验证持久化恢复。数据库断连、Redis/ES失败、MCP/LLM超时/503/坏JSON等由网络封锁的单元/Mock故障注入覆盖，没有停止正式中间件伪造故障。

浏览器pageerror历史共 {len(page_errors)} 条保留，不删除失败现场。已定位订单拒绝响应在 onMounted 内未捕获的Object，物流读取有同类缺口，均已修复。{link(RUN / 'browser-order-error-handled.json', '修复后页面越权拒绝未增加pageerror')}。不声称所有历史控制台告警都不存在。
'''
    docs['34-09-数据库安全与退款隔离报告.md'] = f'''# 数据库安全与退款隔离

{common}
独立 SQL 验证 {sql['assertions']} 条，{sql['passed']} 通过、{sql['failed']} 失败：案件owner=源消息owner=订单owner、可信ownerVerified、executionAllowed=false、连续case_version、不可覆盖plan_version、USER确认/ADMIN审批、MOCK类型限制、同方案退款号稳定、UNKNOWN必须人工核实、商品订单库存摘要不变、完整bizData JSON。

{link(RUN / 'browser-sql-oracle.json')}；主案件审计 {link(RUN / 'primary-return-audit.json')}。SQL是独立预期，不调用Agent自己判断答案正确，也不代替页面写操作。

保留 `deny_agent_refund_execution`。隔离Order只开放MOCK，真实资金开关关闭；没有启动隔离Pay服务、真实渠道凭据不提供给隔离应用。退款类型限定 refund / return_refund，换货不转成资金动作。准备退款、人工审核、接收验货和本地MOCK结果分别审计，MOCK成功不写成资金到账。

正式 {compare['checkedTables']} 张业务表前后摘要相等；正式61条法规全文元数据及向量哈希相等。未操作真实用户订单、商品库存、政策发布状态。没有正式数据迁移。

清理必须显式 `-CleanTestData`，所有门禁成功才执行；按本轮记录的caseId/messageId与合成owner精确删除隔离测试行，事务执行。先保存 {link(RUN / 'browser-database-before-cleanup.json')}，再验证 {link(RUN / 'browser-database-after-cleanup.json')}。清理结果：{link(RUN / 'browser-cleanup.json')}。

保留2个测试用户、1个管理员、6商品、10SKU、9库存、6订单、法规副本；不是删除整个测试环境。不删除正式记录、索引、卷、日志，不重置自增ID。账号和密钥仅留本机private配置，不进入本报告。
'''
    matrix = '''| 项 | 结论 | 本轮证据与限制 |
|---|---|---|
| A 退货意图 | 部分通过 | 页面自然语言规则路由和追问成功；真实LLM未执行 |
| B 本人订单核实 | 通过 | A列表/详情、B订单拒绝、SQL归属与SKU |
| C 政策资格判断 | 部分通过 | 有效法规来源真实，缺条件不承诺；非自动法律裁决，真实语义向量查询未验收 |
| D 方案生成 | 通过 | 真实草稿、原因材料、方案升版、政策证据 |
| E 本人确认提交 | 通过 | 页面确认、ADMIN_REVIEW、唯一案件、重复点击保护 |
| F 管理员审核 | 通过 | 页面通过/驳回、用户修改重提、审计 |
| G 退货物流 | 通过 | 页面登记合成单号及数据库记录；非承运商实时服务 |
| H 退货验收 | 通过 | 管理端页面收到/验收/证据记录 |
| I 模拟退款 | 通过 | 成功/失败/同号重试/UNKNOWN拒绝/人工核实/归档；无真实资金 |
| J 真实LLM | 未执行 | 外发0；不得以Mock/规则替代 |
| K RAG与真实Embedding | 部分通过 | 法规引用、真实ES原有向量和RRF通过；新Embedding未执行 |
| L Supervisor | 通过 | 双专业工作流实际运行、各自证据、刷新持久化；非真实模型验收 |
| M 多轮与恢复 | 部分通过 | 品牌预算调整、刷新、Agent重启恢复通过；同用户独立conversationId缺口 |
| N 生产风险 | 未通过 | 仍有真实API验收、独立会话、长期稳定性及外部履约系统风险 |
'''
    docs['34-10-第34阶段最终验收矩阵.md'] = f'''# 第34阶段最终验收矩阵

{common}
**结论：项目专用浏览器整改及隔离AI退货业务闭环已通过；第34阶段整体仍为部分通过。** 用户页面、管理员页面、真实接口、隔离MySQL、RAG文本证据和模拟退款确已串通，但不能补写真实LLM/Embedding验收或独立会话能力。

{matrix}
{results}
数据库额外规则通过、ES自相似检查通过，均不是浏览器或真实模型测试的替代。8项浏览器用例包含很多子步骤；不得把每次重跑或每条SQL断言叠加为端到端通过数量。

报告索引：34-01隔离、34-02退货、34-03导购、34-04Supervisor、34-05真实API、34-06RAG、34-07恢复、34-08缺陷/故障、34-09数据/退款安全。详细执行环境见额外浏览器整改报告。

尚未完成：真实付费API有限验收；同用户多独立会话；多明细订单逐件退货/部分金额链路；全部异常分支的页面覆盖；真实仓储/承运商/资金联调（本阶段禁止）；长期稳定性。正式Python服务未重载本轮修复，已加载的是隔离Agent。后续正式部署应单独授权维护窗口。
'''
    docs['34-浏览器自动化整改与验收报告.md'] = f'''# 第34阶段项目专用浏览器整改与验收

{common}
不再依赖个人Chrome标签页识别。已落地 `e2e/`，固定 Playwright 1.65.0，配套 Chromium158.0.8127.18。二进制、npm缓存、运行记录、视频全部在E盘。浏览器独立启动，商城/Admin独立BrowserContext，真实验证码由用户手工完成一次，后续复用项目会话。

无个人Chrome接管、无远程调试端口、无Cookie/Token/storageState导出、无验证码绕过；删除Playwright默认的no-sandbox参数以保留浏览器沙箱。请求仅放行隔离商城/Admin两个origin，不伪造route.fulfill响应。不录制登录凭据视频，不保存HAR/原生trace认证头。业务视频和脱敏HTTP元数据可用。

一键复用命令：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\\e2e\\run-e2e.ps1 -Suite all -WithRegression -CloseBrowser -CleanTestData
```

该命令核对已创建的隔离账号与夹具，不会重新初始化/覆盖数据库；首次隔离建库由独立prepare/configure流程完成并有保护。若现有隔离服务不健康则停止，不反复重启。人工验证码不可消除，首次新浏览器仍需一次正常登录。费用开关默认关闭。

本轮7项业务用例与修复后的恢复专项1项分别通过，完成SQL验证、视频收尾和隔离业务行清理。完整业务视频：{link(images / 'shop-full-return.webm')}（31分55秒）、{link(images / 'admin-full-return.webm')}（22分14秒）；这些是收尾RPC失败后保留下来的原始业务录像，已按15秒画面核对角色，使用本地stream-copy重封装补齐容器索引，**没有生成、剪切或重编码画面**，原始/输出哈希见 {link(RUN / 'full-video-recovery.json')}。不是补录操作。最终恢复专项正常保存视频：{link(images / 'shop-business.webm')}、{link(images / 'admin-business.webm')}。HTML结果：{link(current / 'playwright-report/index.html')}；完整7项结果另见前轮记录。截图位于 {link(images)}。

主要新增文件：`e2e/package.json/package-lock.json`、`playwright.config.mjs`、`start-browser.ps1`、`run-e2e.ps1`、`lib/`、`scripts/browser-session.mjs`、`scripts/close-session.mjs`、`tests/*.spec.mjs`及harness契约测试。独立数据库oracle、精确清理和向量复制校验在 `tools/quality_engineering/stage34/`。

业务最小修复文件：`Simlect-front/Simlect-web/src/styles/variables.scss`、`src/components/agent/AgentCasePanel.vue`、`src/views/OrderDetailView.vue`、`src/views/OrderLogisticsView.vue`、`src/utils/protectedOrder.ts`；`Simlect-backend/Simlect-agent/app/services/aftersales_context.py`、`app/supervisor/adapters.py`、`app/graph/builder.py`。新增确认层、订单失败状态、路由、向量契约专项测试。原始文件备份位于 `.cache/stage34/source-before/`。

测试基础设施修复：BOM兼容、严格参数数组、日志stderr不误当退出失败、ES9显式取向量、Agent健康探针8秒（没有扩大LLM20秒限制）、仅隔离Search原生进程启动组。无业务数据库正式迁移；无依赖大版本升级；无Git提交。

{results}
受限事项：自动审批拒绝新增商品向量化准备，未执行额外付费API；本轮真实模型验收0。完整第34阶段结论见34-10，不宣称所有生产化要求已通过。
'''
    OUT.mkdir(exist_ok=True)
    for name, body in docs.items():
        dest = OUT / name
        if dest.exists() and '隔离批次 `' + RUN.name + '`' not in dest.read_text(encoding='utf8'):
            raise RuntimeError('REFUSE_OVERWRITING_UNRELATED_REPORT: ' + name)
        dest.write_text(body, encoding='utf8')
    print(json.dumps({'reports': len(docs), 'directory': str(OUT), 'evidence': str(RUN / 'acceptance-summary.json')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
