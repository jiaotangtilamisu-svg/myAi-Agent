# Gateway 单服务恢复验收报告

日期：2026-11-02（Asia/Shanghai）。最终健康快照：09:58:13.8997712+08:00。

## 1. 结果

**Gateway 单次启动成功，8080 监听正常，HTTP 200/UP，Nacos 注册正常。Agent 未重启，java_web 从 false 恢复为 true，status 从 degraded 恢复为 ok。**

Order 22608、MCP 13924、Agent 23372 均保留第一阶段的原进程及创建时间。Gateway → Order 的受保护只读接口转发已验证；没有读取真实订单，没有执行退款、支付或模型请求。

本轮未修改 .env、业务源码、Gateway 配置、路由或启动脚本，没有重启其他服务/Docker，没有构建 JAR，没有提交/推送 Git。

## 2. 启动前检查与历史日志保护

09:54:03 检查：

- 当前分支 feat/agent-safe-advice-product-search，保留所有已有未提交代码与报告；未清理或重置工作区。
- Gateway 进程数量为 0，8080 无监听；未发现重复实例。
- Windows Update API 与常用待重启标记未显示待重启。
- 13306、16379、5672、8848、9200 中间件端口均监听；未执行中间件启动或重启操作。
- Order/MCP/Agent 原 PID 存在，创建时间与 06 报告一致。
- 确认既有 `deploy/run-configured.ps1 -Stage Java -Service gateway` 参数、JDK17、现有 Gateway JAR 与环境加载逻辑；未使用默认 All 或 Build。

历史三文件已先复制到 E 盘目录：

```text
E:\Simlect-AI-Mall-main\Simlect-AI-Mall-main\logs\gateway-recovery-backup\20261102-095445\
  gateway.out.log
  gateway.err.log
  gateway.process.json
```

备份后分别核验 SHA-256，再把 `logs/local-run` 内原文件原地改名为：

```text
gateway.out.log.pre-recovery-20261102-095445
gateway.err.log.pre-recovery-20261102-095445
gateway.process.json.pre-recovery-20261102-095445
```

现有脚本因而在原固定路径创建本轮新文件，**没有覆盖历史文件内容**。最终复核三份备份与三份改名原件的 SHA-256 均与备份前一致。没有删除日志。

## 3. 实际启动命令和独立进程方式

使用 Windows 原生 `Win32_Process.Create`，创建独立隐藏 PowerShell，执行 07 报告确认的既有入口：

```powershell
"C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "E:\Simlect-AI-Mall-main\Simlect-AI-Mall-main\deploy\run-configured.ps1" -Stage Java -Service gateway
```

工作目录：`E:\Simlect-AI-Mall-main\Simlect-AI-Mall-main`。

原生创建请求于 09:55:35 返回 ReturnValue=0、脚本宿主 PID=24400。只提交一次启动请求，没有重复拉起或失败重试。隐藏窗口仅用于后台运行，没有修改 Windows 服务、计划任务、安全策略或进程隔离策略。

run-configured 按现有逻辑设置 JDK17 和 E 盘临时目录，再由 start-local 的 Java/gateway 分支加载已有 Agent .env、选取现有 JAR，并启动 Java。没有改写启动命令、创建新的 Gateway 启动脚本，也没有替换已有构建产物。

实际 Java CommandLine（与进程读取值相同的参数结构；路径中的项目名按实际文件填写，不含凭据）：

```text
"E:\JDK17\bin\java.exe" -Xms64m -Xmx320m -Dfile.encoding=UTF-8 -jar "E:\Simlect-AI-Mall-main\Simlect-AI-Mall-main\Simlect-backend\Simlect-gateway\target\simlect-gateway-1.0.0.jar" --server.address=127.0.0.1 --spring.cloud.nacos.discovery.ip=127.0.0.1
```

Java 工作目录为 `Simlect-backend/Simlect-gateway`；没有附加数据库 URL、真实密钥或用户凭据作为命令行参数。

## 4. Gateway 进程身份、监听和健康

| 字段 | 本轮实际值 |
|---|---|
| PID | 17164 |
| ParentProcessId | 24400（本轮脚本宿主） |
| CreationDate | 2026-11-02T09:55:44.8109750+08:00 |
| ExecutablePath | E:\JDK17\bin\java.exe |
| StartTicks | 639291813448109755 |
| CommandLine SHA-256 | 798b77dc5b4fc1e89cccd648ec7f9796e9bf239f51db47288e1253326345ce22 |
| 监听 | 127.0.0.1:8080，由 PID 17164 持有 |
| GET /actuator/health | HTTP 200，`{"status":"UP"}` |

实际命令行已保存完整脱敏版本及原始命令行哈希，可供未来辨别 PID 复用；现有脱敏器可能将同于本地敏感值的普通项目名片段也替换为 [REDACTED]，并非执行路径缺失或被修改。

## 5. Nacos 注册与发现

对本机 Nacos 进行只读实例列表查询，均返回 HTTP 200：

| 服务 | group | 实例 | healthy/enabled |
|---|---|---|---|
| simlect-gateway | DEFAULT_GROUP | 127.0.0.1:8080 | true / true |
| simlect-order | DEFAULT_GROUP | 127.0.0.1:8093 | true / true |

Gateway 日志在 09:55:54.582 记录 register finished。下节路由实际响应进一步验证了 Gateway 能够通过现有 `lb://simlect-order` 路径访问 Order，不仅仅是静态配置检查。

## 6. Order 路由与认证边界验证

验证目标为已有只读查询 `POST /internal/order/agent/getOrder`；每次请求体均为 `{}`，没有登录 Token、userId 或 orderId。内部服务令牌只从现有配置在内存中读取，不打印、不写入报告。

已先检查源码：Order getOrder 的首个步骤是 authenticatedUserId；没有登录信息时返回业务码 901，不进入订单检索。没有创建测试用户、修改 Redis 登录数据或触碰真实订单状态。

| 探测 | 实际响应 | 预期与结论 |
|---|---|---|
| 8080 Gateway，不携带内部令牌 | HTTP 401，code=401，invalid internal token，data=null | 通过：Gateway 内部调用认证生效 |
| 8093 Order，携带正确内部令牌但不带用户登录信息 | HTTP 200，status=error，code=901，登录超时，data=null | 通过：Order 仍要求当前登录用户 |
| 8080 Gateway，同样携带内部令牌但不带用户登录信息 | HTTP 200，status=error，code=901，登录超时，data=null | 通过：经 Gateway 到达 Order，响应与直连一致 |

三个探测均符合预期。**HTTP 200/code 901 是本次刻意设计的未登录拒绝结果，不是订单业务成功。** 它验证了现有内部路由和两层认证边界；没有冒充已完成“登录用户成功读取本人订单”的完整验收。

## 7. 原有三个服务与 Agent 恢复

| 服务 | 恢复前 PID | 恢复后 PID | CreationDate（+08:00，保持不变） | 最终健康 |
|---|---:|---:|---|---|
| Order | 22608 | 22608 | 2026-11-02T09:05:46.4602770 | HTTP 200 / UP |
| MCP | 13924 | 13924 | 2026-11-02T09:19:00.3816870 | HTTP 200 / ok |
| Agent | 23372 | 23372 | 2026-11-02T09:20:24.0943810 | HTTP 200 / ok |

Agent `/health` 最终正文：

```json
{"redis":true,"mysql":true,"elasticsearch":true,"java_web":true,"status":"ok"}
```

java_web 从 false 恢复为 true，整体不再 degraded；没有修改 JAVA_WEB_URL，也没有重启 Agent。恢复前后差异由仅启动 Gateway 后的只读健康检查确认。

## 8. 本轮启动日志与异常判断

新标准输出和标准错误仍由既有启动脚本分别保存到 E 盘项目：

- `logs/local-run/gateway.out.log`。
- `logs/local-run/gateway.err.log`。
- `logs/local-run/gateway.process.json`。

新日志记录正常启动、Netty 8080 监听、Nacos 注册成功及 Started GatewayApplication，启动耗时 9.266 秒。stderr 仅有 E 盘 JAVA_TOOL_OPTIONS 提示。

未发现 ERROR 级启动日志、实际异常堆栈、OutOfMemoryError 或 APPLICATION FAILED。有原有 `simlect.production-ready=false` 开发模式警告，不影响本地启动；没有为消除警告修改配置。

注意：final-verification.json 的宽泛 Errors 检索候选中包含两条 **INFO**：Sentinel 的配置 JSON 含 `status:error`，以及注册 `SentinelGatewayBlockExceptionHandler` 的类名。这些是文本模式命中，不是真实错误或异常堆栈，未把它们报告为失败。

## 9. 保护检查与证据

启动前后 SHA-256 核对一致：

- deploy/run-configured.ps1、deploy/start-local.ps1。
- Simlect-backend/Simlect-agent/.env。
- Gateway application.yml。
- Gateway 现有 JAR。

Git 分支未改变，未暂存或提交本轮文件；原有未提交修改均保留。没有执行 Docker、数据库初始化、模型调用、真实退款或支付命令。

本轮证据位于 E 盘项目 `.cache/gateway-recovery-20261102/`：

- preflight.json：启动前状态及保护哈希。
- historical-log-backups.json：历史日志备份、原件保留路径与哈希。
- start-request.json：原生创建返回值、宿主 PID 与精确入口命令。
- initial-verification.json：实际 Java 身份、端口、Nacos、初次健康及脱敏启动日志。
- order-route-verification.json：三个只读路由探测和其他三个服务身份。
- final-verification.json：最终四服务健康、日志候选、Gateway 身份和备份/保护核验。

## 10. 尚未验证与后续边界

1. **新 Gateway PID 17164 的跨 Codex 任务持续存活尚未验证。** 本轮仅确认独立 Windows 原生启动及当前运行成功，不能把 Order/MCP/Agent 的先前存活结论直接套用到 Gateway。
2. 现有部署脚本没有持续监督和 exit.json，未来强制退出的精确退出码仍可能不可得。本轮没有扩展启动脚本或增加进程管理框架。
3. 本轮没有用真实用户读取订单，没有重新执行完整退款安全回归，也没有验证全部商城服务、商品、支付或真实 AI 会话；健康通过不代表上述功能全部通过。
4. 未承诺开机自启、Windows 重启后自动恢复或长期无人值守稳定性。

本轮 Gateway 单服务恢复目标完成。保持四个服务运行，不主动停止；到此暂停，等待审核，不开始商品搜索开发。
