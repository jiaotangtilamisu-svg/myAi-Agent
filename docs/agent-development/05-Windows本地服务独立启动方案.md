# Windows 本地服务独立启动方案

准备日期：2026-11-01。本轮仅创建脚本、文档并做静态/校验模式检查，**没有启动或停止任何服务**。故障归因中的不确定性仍保留，没有修改业务代码或真实 .env，没有提交 Git。

## 1. 使用原则

由用户通过 Windows 开始菜单/Win+R 手动打开三个独立 Windows PowerShell 窗口，在每个窗口前台托管一个服务。不要让 Codex 工具、后台任务或一次性隐藏执行窗口代为持有它们。

脚本没有使用 Start-Job、后台 Start-Process、隐藏窗口、自动重启、创建 Job Object 或退出时自动杀子进程。它在当前窗口通过 .NET Process 启动子进程，持续等待退出并异步收集两个输出流；窗口必须保持打开。

这减少对临时任务宿主的依赖，**不保证任意外部进程管理器无法终止进程，也尚未通过真实启动验证 CTRL+C、父子进程和窗口生命周期行为**。这些属于用户批准后的恢复验收范围。

## 2. 命令来源与真实启动命令

已对照 deploy/run-configured.ps1、deploy/start-local.ps1 及 MCP Server 端口读取实现。沿用其实际解释器、JVM 参数、工作目录和配置加载规则，没有猜测新服务入口。

项目根目录：`E:\Simlect-AI-Mall-main\Simlect-AI-Mall-main`。

### Order

工作目录：`E:\Simlect-AI-Mall-main\Simlect-AI-Mall-main\Simlect-backend\Simlect-order\app`。

```powershell
& 'E:\JDK17\bin\java.exe' -Xms64m -Xmx320m -Dfile.encoding=UTF-8 -jar 'E:\Simlect-AI-Mall-main\Simlect-AI-Mall-main\Simlect-backend\Simlect-order\app\target\simlect-order-1.0.0.jar' --server.address=127.0.0.1 --spring.cloud.nacos.discovery.ip=127.0.0.1 '--spring.datasource.url=jdbc:mysql://127.0.0.1:13306/simlect_order?useUnicode=true&characterEncoding=utf-8&serverTimezone=Asia/Shanghai&allowPublicKeyRetrieval=true&allowMultiQueries=true&useSSL=false'
```

脚本实际从 target 选择唯一可执行 JAR，排除 sources/javadoc/original；文件缺失或不唯一立即失败，不触发构建。沿用已安装 JDK 17，不调整堆大小，不覆盖 JAR。

### MCP Server

工作目录：`E:\Simlect-AI-Mall-main\Simlect-AI-Mall-main\Simlect-backend\Simlect-agent`。

```powershell
& '.\.venv\Scripts\python.exe' -m app.mcp_server
```

FASTMCP_HOST=127.0.0.1、FASTMCP_PORT=7060；从现有源码确认其使用这两个变量。

### Python Agent

工作目录与 MCP 相同。

```powershell
& '.\.venv\Scripts\python.exe' -m uvicorn app.main:app --host 127.0.0.1 --port 7050
```

使用已有生产运行 .venv，不使用 .venv-tests，不安装依赖。Python venv 启动器可能再生成一个实际监听解释器子进程，监控脚本会显示监听进程及父 PID。

上述命令只是说明；推荐使用下文脚本，以获得双流日志及退出记录。

## 3. 环境变量加载

三个脚本共用 scripts/local/service-common.ps1。它只读取现有 `Simlect-backend/Simlect-agent/.env`，按旧启动器的规则解析 `ALL_CAPS_NAME=value`，不使用 Invoke-Expression、不把内容当成 PowerShell、不创建或写回 .env。现有文件需保持与旧脚本兼容，不在本阶段变更 dotenv 语法。

应用所需的数据库、Redis、内部令牌、Java/MCP 地址和模型配置沿用该文件；不在脚本或本报告写入真实凭据。校验令牌为空或是既有弱占位符时拒绝启动。仅加载配置不等于调用模型；启动脚本不发送聊天、支付、退款或邮件请求。

复用的本地进程配置：

| 配置 | 用途 |
|---|---|
| JAVA_HOME=E:\JDK17；原本地工具目录加入 PATH | 原有 Java/Node/Python/Maven 路径 |
| TEMP/TMP=E:\SimlectRuntime\tmp | 现有 Windows 短临时目录；不存在时拒绝启动，不自动改环境 |
| JAVA_TOOL_OPTIONS 追加 jdk.net.unixdomain.tmpdir | 沿用原有 JDK NIO 临时目录兼容配置 |
| PYTHONUTF8=1、PYTHONUNBUFFERED=1 | UTF-8 输出、降低日志缓冲 |
| SIMLECT_PAY_LOCAL_MOCK_ENABLED=true | 保留原有本地模拟支付配置，不启用真实支付 |
| SEATA_ENABLED=false | 保留既有本地未启用 Seata 的配置 |
| FASTMCP_HOST/FASTMCP_PORT | 固定本机 MCP 7060，与本项目既有 Agent 配置对应 |

实际加载的全部变量名称可用 -ValidateOnly 查看；不输出值。配置仅设置在当前监督脚本执行期间及其子进程内，脚本结束后复原原 PowerShell 进程环境，不写系统/用户环境变量。

新脚本不操作 Docker、不初始化数据库、不加载 deploy 脚本的 All/Middleware/Build 分支。Agent 自身原有 lifespan 仍会检查已存在的 agent_session_memory 表；这属于原应用行为，不是新增初始化流程。

## 4. 用户批准后的启动方法（本轮未执行）

先确认已有 MySQL、Redis、RabbitMQ、Nacos、ES、Gateway 可用，并核对当前端口和记录。不要为了启动三个应用重启这些依赖。

可先做无启动校验：

```powershell
Set-Location 'E:\Simlect-AI-Mall-main\Simlect-AI-Mall-main'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\local\start-order.ps1 -ValidateOnly
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\local\start-mcp.ps1 -ValidateOnly
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\local\start-agent.ps1 -ValidateOnly
```

ValidateOnly 不启动进程、不修改环境、不创建运行日志、不访问健康端点。它只核对已有文件和生成脱敏计划。

确认后由用户分别从 Win+R 执行，打开三个独立窗口，按 Order → MCP → Agent 顺序，每步健康后再进入下一步：

```text
powershell.exe -NoProfile -NoExit -ExecutionPolicy Bypass -File "E:\Simlect-AI-Mall-main\Simlect-AI-Mall-main\scripts\local\start-order.ps1"

powershell.exe -NoProfile -NoExit -ExecutionPolicy Bypass -File "E:\Simlect-AI-Mall-main\Simlect-AI-Mall-main\scripts\local\start-mcp.ps1"

powershell.exe -NoProfile -NoExit -ExecutionPolicy Bypass -File "E:\Simlect-AI-Mall-main\Simlect-AI-Mall-main\scripts\local\start-agent.ps1"
```

不要从 Codex 的临时终端代开以上窗口来做“独立宿主”试验。也不必运行旧的 run-configured.ps1，否则会与独立窗口争用端口。新脚本发现端口已占用或已记录实例仍存活时拒绝重复启动，不停止任何已有进程。

脚本启动后窗口会显示 Launcher PID 和本次日志目录，保持前台等待。业务输出分别写 stdout.log/stderr.log，不会实时铺满窗口；如需查看，可在第四个 PowerShell 窗口对本次日志执行 Get-Content -Tail 50 -Wait。

## 5. 只读监控与健康检查

在第四个 PowerShell 窗口执行：

```powershell
Set-Location 'E:\Simlect-AI-Mall-main\Simlect-AI-Mall-main'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\local\check-agent-services.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\local\check-agent-services.ps1 -AsJson
```

输出各服务记录 PID、PID/StartTicks 是否一致、当前相关进程 PID/ParentProcessId/CreationDate/ExecutablePath/脱敏 CommandLine、监听 PID、健康 HTTP 状态及应用 status。优先读取新方案 latest.json，无新记录时回退读取旧 logs/local-run/*.process.json，以便查看当前现场。

用户会话令牌和其他敏感参数在命令行输出中经过过滤。读取元数据失败、进程已退出、端口被其他进程占用或健康失败时只报告，不自动恢复。健康为 200 但记录身份不匹配时，不能据此认定是正确实例。无权限读取进程细节时应由用户核对账户权限，不绕过安全策略。

| 服务 | 只读健康 URL |
|---|---|
| Order | http://127.0.0.1:8093/actuator/health |
| MCP | http://127.0.0.1:7060/health |
| Agent | http://127.0.0.1:7050/health |

监控健康请求显式绕过系统代理，只访问本机，避免之前的代理误判。只检查上述服务，不执行真实业务接口。

## 6. 日志、PID 与退出码

每个启动批次创建唯一目录，旧目录不覆盖、不轮转删除：

```text
logs/independent-services/<order|mcp|agent>/<yyyyMMdd-HHmmss>-<随机后缀>/
    startup.log       启动/失败/正常返回信息
    stdout.log        时间戳、脱敏后的标准输出
    stderr.log        时间戳、脱敏后的标准错误
    process.json      服务、启动时间、监督 PowerShell PID、Launcher PID、StartTicks、工作目录、命令、状态、退出码
    exit.json         子进程退出事件的 PID、ExitCode、ExitedAt（实际退出后才生成）
logs/independent-services/<服务>/latest.json  指向该服务最新批次记录
```

没有把原有 logs/local-run 改作新日志，也不覆盖旧进程记录。Python 实际监听 PID 与启动器 PID 可以不同，监控同时查看其关系，不能把一个正常的子进程误判为孤立服务。

ServiceLog.cs 使用 .NET 的两个异步输出事件写入独立文件，原应用 stderr 中的 INFO/WARNING 不被 PowerShell 误当成启动异常。记录保留完整脱敏后的输出行及异常信息，不截断堆栈。配置中敏感变量的非空值与继承的敏感环境值在写入日志前替换，额外过滤 token/password/api key/Bearer 模式；日志只存脱敏内容，不额外保留未脱敏副本。

退出码通过 Process.ExitCode 与 .NET Exited 事件记录；Windows PowerShell 中断导致普通等待未返回时，事件记录作为补充。若整个监督窗口被强制终止、机器关机或磁盘不可写，仍可能丢失退出事件：这时应认定未知，不能根据缺少记录推导 ExitCode=0。此方案不是持久 Windows 服务，也没有静默自动重启。

## 7. 停止方法

在对应服务所属的独立窗口按一次 Ctrl+C，等待其优雅关闭，再在第四窗口确认监听端口释放、实际子进程退出，并检查 process.json/exit.json。停止顺序建议 Agent → MCP → Order。

不要直接关闭三个窗口来替代可观察的停止。若 Ctrl+C 未完成，不使用批量 kill；先记录 PID/CreationDate/端口及日志，人工确认目标和原因后再决定是否结束该单个进程。本轮没有新建自动停止脚本。

不要运行旧 stop-configured.ps1 来停止独立窗口实例：它管理旧记录，并且会停止其他商城服务和中间件，不适合这个试验。

## 8. 异常排查与恢复边界

1. 启动前失败：检查 startup.log、已有 JAR/venv/短临时目录和端口占用；脚本不会补装、构建、清理或删除数据。
2. 进程已启动后退出：检查 exit.json 的真实退出码和时间，再看 stderr/stdout 的最后时间戳。SupervisorInterrupted 或没有退出码不是成功退出。
3. 监听属于其他 PID：核对实际命令和父子关系，不能仅凭同名 java/python 结束进程。
4. 同时退出：对比三个 exit.json、Windows 事件和 PowerShell 窗口状态，调查是否有共同控制台/Job Object/外部清理；不把父进程退出本身当成证据。
5. 健康失败：先读日志和依赖状态，不自动重启任何服务，不初始化数据库，不删除 ES 索引或 Docker 数据卷。
6. 日志脱敏是防泄露过滤，不建议启用会打印请求体/凭据的调试输出。编码或拆分后的任意敏感内容无法由简单字符串过滤作绝对保证；本方案不主动记录环境值或请求凭据。

## 9. 本轮验证结果与交付文件

新增文件：三个 start 脚本、只读 check 脚本、共享 service-common.ps1、.NET ServiceLog.cs，以及本报告。

已完成：5 个 PowerShell 文件语法解析均无错误；Windows PowerShell 5.1.26100.9444 编译 C# helper 成功；三个 -ValidateOnly 成功；校验模式不改变进程内内部令牌环境；PowerShell 与实际 C# 写入路径的合成敏感值过滤检查通过。C# 日志检查仅实例化未启动的 Process，**没有调用 Process.Start**。

未执行：实际服务启动/停止、真实 Ctrl+C 退出和退出事件落盘、真实 stdout/stderr 持续采集、持续存活验证。监控脚本只做解析检查，尚未执行其进程/健康检查路径。上述功能需用户确认后在独立窗口验收，不能在本报告中写成运行测试通过。

临时准备证据位于 `.cache/independent-launch-preparation`，没有 API Key/Token 明文清单。现有未提交修改全部保留，业务代码和 .env 未改动，Git 未提交。等待用户确认后再进入实际恢复阶段。
