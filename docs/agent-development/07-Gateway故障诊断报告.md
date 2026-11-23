# Gateway 故障只读诊断报告

检查日期：2026-11-02（Asia/Shanghai）。运行态证据时间：09:47:16+08:00。

## 1. 结论

**当前直接阻塞是 Gateway 没有运行：无对应 Java 进程，8080 无监听，Agent 指向该地址的 Java Web 检查失败。** Order 自身健康、Nacos 中 Order 注册正常，尚未发现本地路由配置与该实例地址不一致。

- 已确认：历史 Gateway 成功启动过；当前旧 PID 16884 不存在，Nacos Gateway 实例列表为空，8080 请求连接被拒绝。
- 高概率情况：昨晚 Windows 计划更新重启后，Gateway 未恢复启动。旧日志在重启请求同一时刻记录 Redis 连接重置；本轮未找到今天新的 Gateway 启动记录。
- 尚不能确认：Gateway 精确退出时刻、退出码、接收的退出信号；不能将 Redis Connection reset 直接认定为进程崩溃根因，也不能认定代码启动失败。

本轮没有启动 Gateway，没有更改 JAVA_WEB_URL、源码、配置或路由，没有重启任何服务或 Docker，没有执行退款/支付，没有提交 Git。所有诊断证据保存于 E 盘。

## 2. 模块、目录与现有启动入口

项目根目录：`E:\Simlect-AI-Mall-main\Simlect-AI-Mall-main`，下文路径均相对此目录。

| 项目 | 实际检查结果 |
|---|---|
| Maven 模块 | `Simlect-backend/Simlect-gateway`，父 POM 已列入该模块 |
| Java 主类 | `com.simlect.cloud.gateway.GatewayApplication`，含 `@EnableDiscoveryClient` |
| 工作目录 | `E:\Simlect-AI-Mall-main\Simlect-AI-Mall-main\Simlect-backend\Simlect-gateway` |
| 可执行包 | `Simlect-backend/Simlect-gateway/target/simlect-gateway-1.0.0.jar`，68,587,050 字节，最后修改 2026-11-01 13:51:36 |
| 专用独立监督脚本 | 当前没有 `scripts/local/start-gateway.ps1`；三服务的 service-common.ps1 仅支持 Order/MCP/Agent，不能直接传入 gateway |
| 可复用现有入口 | `deploy/run-configured.ps1 -Stage Java -Service gateway`，委托 `deploy/start-local.ps1` 的 Java 分支，仅选择 gateway |
| 全量入口 | run-configured 默认 All 会处理中间件及其他服务；本次恢复不应使用默认 All |

## 3. 当前运行状态与进程记录

Win32_Process 查询未发现命令行对应 Gateway 的 java.exe/javaw.exe；旧记录 PID 16884 也不存在。

`logs/local-run/gateway.process.json` 内容仅含历史元数据：

```text
Id = 16884
Port = 8080
StartTicks = 639291143057935734
```

该文件于 2026-11-01 15:18:25 写入，不包含完整启动命令、父进程、退出码或退出时间。它不是当前活进程证明。当前没有 Gateway 的 CreationDate、ParentProcessId、ExecutablePath、CommandLine 可读取，不能用历史配置冒充当前进程信息。

| 检查 | 本轮实际结果 |
|---|---|
| 8080 TCP LISTEN | 无 |
| GET http://127.0.0.1:8080/actuator/health | 无 HTTP 响应，SocketException：目标计算机积极拒绝连接 |
| Order PID | 22608，创建时间仍为 2026-11-02T09:05:46.4602770+08:00 |
| Order /actuator/health | HTTP 200 / UP |
| Agent /health | HTTP 200 / degraded，java_web=false，Redis/MySQL/ES=true |
| Windows 最近启动时间 | 2026-11-01T23:35:20.5000000+08:00 |

没有为了本轮诊断停止、重启或替换已经通过跨任务验收的三个服务。

## 4. 最近一次启动日志与异常

项目日志目录内找到的 Gateway 文件只有：

- `logs/local-run/gateway.out.log`：12,770 字节，最后写入 2026-11-01 23:29:11。
- `logs/local-run/gateway.err.log`：79 字节，最后写入 2026-11-01 15:18:25。
- `logs/local-run/gateway.process.json`：旧启动记录。

关键时间线：

| 时间（2026-11-01，+08:00） | 日志事实 |
|---|---|
| 15:18:27.982 | Starting GatewayApplication v1.0.0，Java 17.0.3.1，PID 16884；日志注明实际 JAR 与 Gateway 工作目录 |
| 15:18:27.986 | No active profile set，使用 default profile |
| 15:18:34.122 | Netty started on port 8080 |
| 15:18:36.121 | Nacos DEFAULT_GROUP，simlect-gateway，127.0.0.1:8080 register finished |
| 15:18:36.517 | Started GatewayApplication，启动耗时 9.797 秒 |
| 23:29:10.764 | Lettuce Redis 连接发生 java.net.SocketException: Connection reset，有 Netty 读取堆栈 |

stderr 只有 JAVA_TOOL_OPTIONS 提示。未发现 APPLICATION FAILED TO START、启动期 ERROR 或 OOM；已有 simlect.production-ready=false 开发模式警告不是启动失败。

第 06 报告记录 Windows 在 23:29:10 发起计划更新重启，之后重新启动。时间关系支持“系统重启后未恢复”的判断，但本地旧启动器没有持久退出事件机制，无法还原精确退出码和精确终止时刻。不能把 stdout 最后写入时间当作退出时间。

## 5. 配置和包内容核对

主要配置：`Simlect-backend/Simlect-gateway/src/main/resources/application.yml`。

| 配置项 | 源码/JAR/环境检查 |
|---|---|
| server.port | 8080 |
| server.shutdown | graceful，关闭阶段超时 30 秒 |
| Spring application name | simlect-gateway |
| Profile | 历史运行使用 default；现有 .env 和检查 Shell 未指定 SPRING_PROFILES_ACTIVE；JAR 未发现 application-*.yml/.properties。当前不存在可供验证的活 Gateway 环境 |
| Nacos 地址 | `${NACOS_ADDR:127.0.0.1:8848}`；现有 .env 为 127.0.0.1:8848 |
| Nacos namespace/group | 默认空 namespace（public）、DEFAULT_GROUP；现有 .env 未另行设置 |
| 注册 IP | 现有启动脚本传 `--spring.cloud.nacos.discovery.ip=127.0.0.1` |
| Redis | YAML 默认 127.0.0.1:6379；实际本地启动应加载 .env 的 REDIS_HOST=127.0.0.1、REDIS_PORT=16379 |
| Sentinel | 默认 127.0.0.1:8858，用于限流与健康检查相关功能 |
| 内部服务认证 | SIMLECT_INTERNAL_TOKEN 已配置，仅记录存在，不输出内容；Gateway 内部令牌校验保持启用 |
| config import | optional:classpath:simlect-common.yml；实际 Gateway JAR 未包含该配置文件，optional 导入并非当前启动错误证据 |

只读打开 JAR 检查结果：

- Build-Jdk-Spec=17，Spring-Boot-Version=3.5.4，Start-Class=GatewayApplication。
- JAR 的 BOOT-INF/classes/application.yml 与源码配置在统一换行后完全一致。
- Gateway POM 和 JAR 没有发现 MySQL JDBC/Hikari 数据源库；不是直接连接商城业务 MySQL 的模块。它依赖 Redis（认证等）、Nacos（发现）、Sentinel，并通过路由访问各 Java 服务。
- 现有配置没有发现把 Gateway 改到其他端口，或将内部 Order 路由固定到错误端口的情况。运行态路由尚不可查询，因为 Gateway 未运行。

## 6. 路由、认证和 Order 关系

真实调用路径：

```text
Agent/MCP 的 HTTP 内部读客户端
  → JAVA_WEB_URL=http://127.0.0.1:8080
  → /internal/order/agent/...
  → Gateway InternalTokenGlobalFilter 校验 X-Internal-Token
  → 路由 internal-order：Path=/internal/order/**，uri=lb://simlect-order
  → Nacos 发现 Order 实例
  → 127.0.0.1:8093/internal/order/agent/...
  → OrderAgentInternalController 再校验登录用户及订单归属
```

该内部路由不配置 StripPrefix/RewritePath，路径原样保留，与 Controller 的 `@RequestMapping("/internal/order/agent")` 一致。不是所有 `/internal/**` 任意路径都会被代理：当前显式配置 order/product/coupon/user 四类内部路由。

普通商城 `/api/order/**`、订单评价、物流路由也指向 lb://simlect-order，但配置 RewritePath 去除 `/api/`；不要把普通业务路径重写规则套到内部接口。

关键文件/方法：

- `Simlect-backend/Simlect-agent/app/services/java_internal_client.py`：JavaInternalClient._base、_headers、post_json、get_order 等。
- `Simlect-backend/Simlect-gateway/src/main/java/com/simlect/cloud/gateway/filter/InternalTokenGlobalFilter.java`：filter，校验内部服务身份。
- `Simlect-backend/Simlect-gateway/src/main/java/com/simlect/cloud/gateway/config/GatewayLoadBalancerClientConfiguration.java`：discoveryClientServiceInstanceListSupplier、reactorServiceInstanceLoadBalancer，使用发现客户端、缓存和轮询。
- `Simlect-backend/Simlect-order/app/src/main/java/com/simlect/controller/internal/OrderAgentInternalController.java`：getOrder/getOrderItem/listOrderItems 与登录用户校验。

内部 Token 正确仅代表服务身份，并不替代当前用户身份和订单归属校验。本轮没有发送订单查询或任何退款请求。

## 7. Nacos 注册的实际结果

通过本机无代理 GET 查询 Nacos，只读取健康与实例列表：

| 查询 | 结果 |
|---|---|
| /nacos/v1/console/health/readiness | HTTP 200 / OK |
| DEFAULT_GROUP，simlect-order | HTTP 200；实例 127.0.0.1:8093，healthy=true、enabled=true、ephemeral=true |
| DEFAULT_GROUP，simlect-gateway | HTTP 200；hosts=[] |

当前 Order 的 serviceName、group、注册 IP/端口与 Gateway 静态路由相符，**未发现 Order 注册发现异常**。Gateway 无实例与其进程不存在一致。由于 Gateway 未运行，无法验证它实际订阅的发现列表或端到端转发成功；不能把静态配置匹配写成路由已实际测试通过。

## 8. Agent java_web=false 的直接原因

现有 .env 的 JAVA_WEB_URL=http://127.0.0.1:8080，INTERNAL_READ_BACKEND=http；Settings 由已有 Pydantic 配置加载 .env，现有启动脚本也将其注入进程环境。

`app/services/health_service.py` 的 HealthService.check_all 使用 httpx 三秒超时请求 `${java_web_url}/api/`，而业务客户端 JavaInternalClient 将内部业务 POST 同样发往该 Gateway 地址。

当前目标端口没有任何监听、直接连接被拒绝，因而 Java Web 可达性检查不能通过；Order 的 8093 直接健康并不能替代 Gateway 8080 的可达性。**无需把 JAVA_WEB_URL 改为 Order 端口来绕过网关。**

Agent 日志事件为 health_java_web_failed，error 原字段为空；只读诊断未获取到 Agent 当时异常的具体类型，不能虚构其 Python 堆栈。Gateway 本机直接探测的实际异常为 SocketException/连接拒绝，见 runtime.json。

该健康探测仅检查 `/api/` HTTP 状态是否小于 500，本身不等于订单接口、鉴权和业务功能已完整通过；恢复后还需单独做经授权的安全只读业务验收。

## 9. 已确认启动方式与构建方式

从现有 deploy 脚本提取的 Gateway Java 命令（展示，不执行）：

```powershell
& 'E:\JDK17\bin\java.exe' `
  '-Xms64m' '-Xmx320m' '-Dfile.encoding=UTF-8' `
  '-jar' 'E:\Simlect-AI-Mall-main\Simlect-AI-Mall-main\Simlect-backend\Simlect-gateway\target\simlect-gateway-1.0.0.jar' `
  '--server.address=127.0.0.1' `
  '--spring.cloud.nacos.discovery.ip=127.0.0.1'
```

这是依据实际脚本和历史日志还原的命令，不是对已退出进程完整命令行的读取。单独复制该 Java 命令不会自动加载 .env，故恢复优先复用下节完整部署入口。

- JDK：`E:\JDK17`，本轮 java -version 为 17.0.3.1，与历史运行日志及父 POM Java 17 要求一致。
- run-configured.ps1 设置 JAVA_HOME、E 盘工具 PATH、TEMP/TMP=`E:\SimlectRuntime\tmp`、JAVA_TOOL_OPTIONS 的 unixdomain 临时目录。
- start-local.ps1 的 Load-LocalEnvironment 按原规则读取已有 Agent .env，不覆盖该文件；检查内部令牌并设置 PYTHONUTF8、模拟支付标志与 SEATA_ENABLED=false；Java 分支对缺少的 AI Key 使用原有占位加载规则，不进行模型请求。
- Gateway 不附加 Order/MySQL 的 datasource URL 覆盖参数。
- 日志位置为 E 盘项目 `logs/local-run/gateway.out.log`、`gateway.err.log`、`gateway.process.json`。
- 现有 Build 阶段实际命令：`mvn -B -ntp -f Simlect-backend/pom.xml package`。它构建整个后端、可能运行测试，并非 Gateway 单独恢复的必要步骤。本轮没有执行 Maven 或构建；已有可用 JAR，配置一致，建议先复用，不重建无关服务。
- Maven 可执行文件 `E:\develop\apache-maven-3.9.4-bin\apache-maven-3.9.4\bin\mvn.cmd` 已确认存在。

## 10. 推荐恢复方案与待授权命令

**本节仅为后续恢复方案，所有启动与备份命令均未执行。**

建议仅恢复 Gateway，不重启 Order/MCP/Agent，不改 JAVA_WEB_URL，不重启 Docker，不调用 run-configured 的 All 或 Build。

原 start-local 的 Start-LocalProcess 使用后台 Start-Process 和固定日志名，没有三个独立脚本那样的持续监督和 exit.json；直接再启动会覆盖固定 stdout/stderr/进程记录。恢复前必须先在 E 盘按时间戳复制历史日志记录，便于回滚诊断。

在后续获准恢复时，从项目根目录执行现有精确入口；建议使用用户独立打开并保留的 PowerShell，以避免将普通后台启动绑定于临时工具任务，并在下一任务验证持续存活：

```powershell
Set-Location 'E:\Simlect-AI-Mall-main\Simlect-AI-Mall-main'

# 后续恢复前保留旧日志；本轮未执行。
$gatewayBackup = Join-Path (Get-Location).Path ('logs\gateway-recovery-backup\' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $gatewayBackup -ErrorAction Stop | Out-Null
Copy-Item -LiteralPath @(
  'logs\local-run\gateway.out.log',
  'logs\local-run\gateway.err.log',
  'logs\local-run\gateway.process.json'
) -Destination $gatewayBackup -ErrorAction Stop

powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\deploy\run-configured.ps1 -Stage Java -Service gateway
```

该命令来自现有脚本参数，不会选择其他 Java 服务或 Docker 阶段。执行前仍应重新确认 8080 无占用、无存活 Gateway 实例及更新待重启情况；发现实例或启动失败就停止，不重复拉起。

如果后续仍要求由 Codex 自动管理独立进程，可另行授权为 Gateway 准备与已验收三服务相同的监督入口，并保留原脚本；**本轮没有创建或修改任何启动脚本，也不虚构现有 start-gateway.ps1。**

恢复后的只读检查命令（本轮没有以此进行恢复）：

```powershell
Get-NetTCPConnection -LocalPort 8080 -State Listen
Invoke-RestMethod 'http://127.0.0.1:8080/actuator/health'
Invoke-RestMethod 'http://127.0.0.1:7050/health'
```

应同时记录新 Gateway 的完整进程身份、确认 Nacos Gateway 127.0.0.1:8080 注册、Agent java_web=true，并区分端口监听、HTTP 可达与真实内部路由业务校验。若 Agent 仍失败，先记录当时错误，不自动更改路由或认证。

## 11. 证据、安全与尚未验证事项

证据位于 E 盘项目 `.cache/gateway-diagnosis-20261102/`（Git 忽略目录）：

- runtime.json：当前进程/旧记录/端口、健康请求、Nacos 实例、脱敏完整旧日志、配置白名单值；内部 Token 仅记录是否已配置。
- jar-inspection.json：JAR manifest、配置一致性、Profile 与 JDBC 库核对结果。

本轮没有读取并输出真实密钥、Token 或密码。现有脱敏器可能将与本地敏感值同字的普通项目名片段也替换为 [REDACTED]，这只是输出过滤，不代表文件内容被修改。

尚未验证：新 Gateway 能否成功启动、启动后完整 Redis/发现/路由健康、真实鉴权订单只读链路、Gateway 自身新跨任务持续存活。以上等待审核后另行实施，不能作为本轮通过项。

本轮只新增本报告及 E 盘忽略目录中的诊断证据；保留原有代码、报告和日志。到此暂停，等待审核，不执行恢复操作。
