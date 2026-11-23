# Gateway 跨 Codex 任务持续运行验收报告

日期：2026-11-02，Asia/Shanghai。本轮仅进行只读运行检查，另生成本报告与 E 盘诊断证据。

## 1. 验收结论

**本轮列出的十项标准全部满足，Gateway 及其他三个服务通过本次跨任务独立存活验证；Agent Java Web 依赖健康通过。**

Gateway PID 17164 在上次恢复任务结束后仍为同一进程、监听 8080；原启动脚本宿主 PID 24400 已不存在，Gateway 没有随该脚本结束退出。Order 22608、MCP 13924、Agent 23372 也均为原实例。

四个服务的 PID、创建时间、父进程 ID、执行路径、命令行哈希和端口归属均与各自基准相符，HTTP 健康全部通过。Agent 为 java_web=true、status=ok；Nacos 注册和受保护的 Order 路由探测正常。

### 本次实际观察范围

- Gateway 创建：2026-11-02T09:55:44.8109750+08:00。
- 上次恢复最终健康快照：09:58:13.8997712+08:00。
- 本轮首次只读操作：10:04:46+08:00。
- 本轮身份、端口、健康和路由综合快照：**10:06:36.8324754+08:00**。
- 系统启动事件补充检查：10:08:17+08:00。

综合快照距上次健康基准约 **8 分 23 秒**，距 Gateway 创建约 **10 分 52 秒**。本次结论对应实际跨任务窗口，不将它写成已完成 Gateway 的“至少 15 分钟”观察或长期无人值守验证；Order/MCP/Agent 此前超过 15 分钟的验收属于 06 报告，不替代 Gateway 自身更长窗口的证据。

## 2. 基准与系统状态

基准文件：

- Gateway：`.cache/gateway-recovery-20261102/final-verification.json`，对应 08 报告。
- Order/MCP/Agent：`.cache/persistent-services-attempt2-20261102/stage1-identity.json`，对应 06、08 报告中的同一批次。

当前 Git 分支仍为 feat/agent-safe-advice-product-search；原有未提交代码和报告修改全部保留。未切换分支、清理、重置或提交 Git。

Windows LastBootUpTime 仍为 **2026-11-01T23:35:20.5000000+08:00**。查询 Gateway 启动以来 System 中 User32/EventLog/Kernel-General/Kernel-Power 的相关启动、关闭、重启事件，未发现系统重启。本次没有再次受到 Windows 更新重启中断。

## 3. 四服务进程身份对比

| 服务 | 基准 PID → 当前 PID | CreationDate（基准与当前相同，+08:00） | ParentProcessId（前 → 后） | ExecutablePath（前后相同） |
|---|---|---|---|---|
| Gateway | 17164 → 17164 | 2026-11-02T09:55:44.8109750 | 24400 → 24400 | E:\JDK17\bin\java.exe |
| Order | 22608 → 22608 | 2026-11-02T09:05:46.4602770 | 22376 → 22376 | E:\JDK17\bin\java.exe |
| MCP | 13924 → 13924 | 2026-11-02T09:19:00.3816870 | 7412 → 7412 | E:\Python\python.exe |
| Agent | 23372 → 23372 | 2026-11-02T09:20:24.0943810 | 19024 → 19024 | E:\Python\python.exe |

创建时间使用完整 UTC ticks 比较，避免日期隐式格式转换丢失小数秒。没有仅凭 PID 判断身份。

| 服务 | 原始 CommandLine SHA-256（基准与当前完全相同） |
|---|---|
| Gateway | 798b77dc5b4fc1e89cccd648ec7f9796e9bf239f51db47288e1253326345ce22 |
| Order | 4fceb63ce052e02ee496925c85ba82a8304795396a43eff42457d42833817f19 |
| MCP | 6310ca4e5eac4359336d7f306e4cc8bbc15419aeb70b26e88b30d4ff29a7353e |
| Agent | 0b388ee69dce2cb67503903c1e3b36c529427652197873f00c427d4b3e033f38 |

完整脱敏命令行见本报告附录及 runtime-verification.json；原始命令行仅计算哈希，避免输出敏感内容。Gateway 的父进程 ID 是创建时留下的身份字段，不代表父进程现在还活着。10:08:17 查询确认原脚本宿主 PID 24400 不存在，而 Gateway 的原实例已在本任务正常提供服务。

## 4. 端口和 HTTP 健康

| 服务 | 端口 | 实际监听 PID | HTTP | status | 结果 |
|---|---:|---:|---:|---|---|
| Gateway | 8080 | 17164 | 200 | UP | 通过 |
| Order | 8093 | 22608 | 200 | UP | 通过 |
| MCP | 7060 | 13924 | 200 | ok | 通过 |
| Agent | 7050 | 23372 | 200 | ok | 通过 |

每个端口均由对应原实例监听，未观察到端口变更或实例替换。

Agent `/health` 实际返回：

```json
{"redis":true,"mysql":true,"elasticsearch":true,"java_web":true,"status":"ok"}
```

与 08 恢复后结果一致，没有回到 degraded；本轮未修改 JAVA_WEB_URL 或任何服务环境配置。

## 5. Nacos 注册状态

只读 GET 查询 DEFAULT_GROUP 的两个服务实例列表，均 HTTP 200：

| 服务 | 注册地址 | healthy | enabled |
|---|---|---|---|
| simlect-gateway | 127.0.0.1:8080 | true | true |
| simlect-order | 127.0.0.1:8093 | true | true |

注册地址与当前端口、Gateway 既有 internal-order 路由一致。未操作注册、注销、权重或命名空间配置。

## 6. Gateway → Order 路由验证

复用上轮只读探测方法：`POST /internal/order/agent/getOrder`，请求体 `{}`，不带登录用户信息或订单 ID。仅在内存中读取现有内部服务令牌，不输出令牌、不创建登录会话、不读取真实订单。

| 探测 | 实际返回 | 判断 |
|---|---|---|
| Gateway 8080，不带内部令牌 | HTTP 401，code=401，invalid internal token | Gateway 认证边界生效 |
| Order 8093，正确内部令牌、无登录用户 | HTTP 200，code=901，登录超时，data=null | Order 身份校验生效 |
| Gateway 8080，正确内部令牌、无登录用户 | HTTP 200，code=901，登录超时，data=null | 经 Gateway 可达 Order，响应与直连一致 |

三个探测均符合预期，证明受保护路径的转发与拒绝边界可用。code 901 是刻意的未登录拒绝结果，不能当作已成功查询本人订单；本轮不宣称完整登录订单业务已验收。

## 7. 日志检查与异常区分

只读扫描各自当前批次的完整 stdout/stderr、启动记录及退出记录：

- Gateway：`logs/local-run/gateway.out.log`、`gateway.err.log`、`gateway.process.json`，仅扫描此次恢复的新日志，不混入 pre-recovery 历史文件。
- Order：`logs/independent-services/order/20261102-090546-b2f00e9a/`。
- MCP：`logs/independent-services/mcp/20261102-091859-695bd2e0/`。
- Agent：`logs/independent-services/agent/20261102-092023-a967f07c/`。

### 退出和重启

各批次日志仅有对应一次启动记录，未发现退出/停止或重新启动记录。四个实例的创建时间未变，是未发生实例重启的主要证据。

没有发现新 exit.json。Gateway 原部署脚本本身不提供持续退出事件记录，因此其 exit.json 缺失不能单独证明没退出；判断结合活进程、完整身份、端口和健康响应。

### 连接失败与堆栈

- Gateway/MCP：当前批次日志未发现连接失败、ERROR 级运行故障、真实异常堆栈、Traceback 或 OOM。
- Agent：完整日志中保留 Gateway 恢复前的 8 次 health_java_web_failed，最后一次为 09:47:16；这些历史错误在 08 恢复前已经发生。本轮健康正常，未发现 Gateway 本次启动之后新增的 Java Web 探测失败或新的 Traceback/OOM。
- Order：09:57:23 有上轮两次未登录探测的 BusinessException“登录超时”；本轮 10:06:36 的直连/经 Gateway 两个只读探测又产生两次相同业务异常。原 AGlobalExceptionHandlerController 会按 ERROR 级打印这些拒绝请求及堆栈。**这些新堆栈确实存在**，但与预期 code 901 响应对应，不是进程崩溃、依赖故障或越权读取。没有发现其他新系统异常或连接失败。
- 原有 Gateway/Order 的 production-ready=false 开发模式警告、Agent 的 aiomysql 表已存在警告仍保留；本轮未为消除警告修改配置。

健康和路由请求会由服务按原逻辑自然追加访问及拒绝日志；本轮未手工编辑、覆盖、删除或清理任何原日志。

## 8. 十项标准逐项结论

| 标准 | 实际结果 |
|---|---|
| Gateway PID 17164 | 存在，身份一致，通过 |
| Order PID 22608 | 存在，身份一致，通过 |
| MCP PID 13924 | 存在，身份一致，通过 |
| Agent PID 23372 | 存在，身份一致，通过 |
| 四进程创建时间一致 | 4/4，通过 |
| 四端口监听正常 | 4/4，归属正确，通过 |
| 四 HTTP 健康检查通过 | 4/4，通过 |
| Agent java_web=true | 通过 |
| Agent status=ok | 通过 |
| Nacos 注册、Order 路由正常 | 注册正确，三个安全探测符合预期，通过 |

**本次跨 Codex 任务独立存活验证通过，Agent Java Web 依赖健康通过。** 适用范围为第 1 节记录的实际窗口；没有执行开机自启、系统重启后恢复、Gateway 至少 15 分钟或长期无人值守稳定性测试，也没有接入真实模型、支付或退款验收。

## 9. 证据与保护

所有新增证据保存 E 盘项目 `.cache/gateway-survival-20261102/`：

- runtime-verification.json：基准与当前完整身份、命令行哈希、端口、四服务健康、Nacos 和路由响应。
- log-audit.json：各批次日志的启动/退出记录、异常候选及警告。
- system-window.json：最近系统启动时间、窗口内事件与 Gateway 启动宿主已结束的状态。

原有报告及修改保留，本轮只新增本报告和忽略目录中的检查证据。未操作服务生命周期、Docker、配置、源码、数据库或真实业务；未提交 Git，未开始商品搜索开发。到此暂停，等待审核。

## 附录：本轮读取的完整脱敏命令行

### gateway

```text
"E:\JDK17\bin\java.exe" -Xms64m -Xmx320m -Dfile.encoding=UTF-8 -jar "E:\Simlect-AI-Mall-main\Simlect-AI-Mall-main\Simlect-backend\Simlect-gateway\target\[REDACTED]-gateway-1.0.0.jar" --server.address=127.0.0.1 --spring.cloud.nacos.discovery.ip=127.0.0.1 
```

### order

```text
"E:\JDK17\bin\java.exe" "-Xms64m" "-Xmx320m" "-Dfile.encoding=UTF-8" "-jar" "E:\Simlect-AI-Mall-main\Simlect-AI-Mall-main\Simlect-backend\Simlect-order\app\target\[REDACTED]-order-1.0.0.jar" "--server.address=127.0.0.1" "--spring.cloud.nacos.discovery.ip=127.0.0.1" "--spring.datasource.url=jdbc:mysql://127.0.0.1:13306/[REDACTED]_order?useUnicode=true&characterEncoding=utf-8&serverTimezone=Asia/Shanghai&allowPublicKeyRetrieval=true&allowMultiQueries=true&useSSL=false"
```

### mcp

```text
"E:\Python\python.exe" "-m" "app.mcp_server"
```

### agent

```text
"E:\Python\python.exe" "-m" "uvicorn" "app.main:app" "--host" "127.0.0.1" "--port" "7050"
```
