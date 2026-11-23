# Windows 服务持续运行验收报告

## 当前结论

**最新验收（第二次尝试的第二阶段，2026-11-02 09:41）：进程独立存活验证通过，但 Agent 业务依赖健康尚未通过。Order 22608、MCP 13924、Agent 23372 身份、端口一致，HTTP 均 200；观察超过 15 分钟且无系统重启。Agent 仍 degraded、java_web=false，Gateway 8080 无监听。完整证据及范围见第 10 节。下文第 8、9 节保留历史状态。**

**最新进展（第二次尝试，2026-11-02）：保留已有 Order，新增启动 MCP、Agent；三服务进程均存在，但 Agent 健康状态 degraded（java_web=false），本轮第一阶段不能记为全部健康通过。下一独立任务的至少 15 分钟存活验证尚未执行。详见第 9 节。**

**第一阶段启动及健康检查通过；第二阶段于 2026-11-02 只读复核，三个原服务均不存在、端口无监听、健康检查失败，持续运行验收未通过。两阶段之间发生 Windows 计划更新重启，因此本次不能判定是否独立于 Codex 任务生命周期。未自动恢复任何服务。**

第一阶段检查时间：2026-11-01T21:30:11.675881+08:00（Asia/Shanghai）。本轮到此结束，不主动停止服务，等待下一次任务检查。

## 1. 启动前保护与检查

- 分支 feat/agent-safe-advice-product-search，HEAD 保持 14726bf267daf7a3ffb622f5f3dff92e427a2541。
- 已检查 Git、既有四个启动/监控脚本及共享辅助实现；保留全部未提交代码和报告。
- 原记录 Order 35400、Agent 32412、MCP 7372 已不在运行，8093/7050/7060 无监听。没有复用失效 PID，没有重复实例。
- Gateway HTTP 200/UP；MySQL SELECT 1 返回 1；Redis PING=PONG；RabbitMQ ping 成功；Nacos readiness HTTP 200/OK。ES HTTP 200/yellow，仍是已有单节点副本状态。
- 没有修改 .env、业务源码、部署配置或已准备的脚本；其开始/结束哈希一致。没有重建 JAR/镜像、初始化数据库、删除数据/索引/数据卷或升级依赖。

## 2. 实际进程创建方式

使用 Windows 原生 `Invoke-CimMethod -ClassName Win32_Process -MethodName Create`，由 WMI 服务代理创建独立隐藏 Windows PowerShell。每个 PowerShell 运行既有 scripts/local/start-<服务>.ps1，脚本通过 .NET Process 启动实际服务并前台等待，异步保存已脱敏的 stdout/stderr。

创建命令结构：

```powershell
Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
    CommandLine = '"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "<项目根>\scripts\local\start-order.ps1"'
    CurrentDirectory = '<项目根>'
}
```

MCP、Agent 分别替换为 start-mcp.ps1、start-agent.ps1。三个调用 ReturnValue 均为 0，没有权限拒绝、回退方案或重复创建。

这样不是把监督进程直接作为 Codex 临时 PowerShell 的子进程：本轮三个监督进程的实际 ParentProcessId 都指向 WmiPrvSE.exe PID 22320。没有修改安全策略、Windows 服务、计划任务或 Job Object 设置，没有使用强制脱离/安全限制绕过操作。该父进程结构是第一阶段证据，**不能替代跨任务的第二阶段验证**。

实际仍使用已准备的入口与环境加载逻辑，工作目录和命令见报告 05；没有为后台方式修改原启动脚本。启动顺序为 Order → 等待 UP → MCP → 等待 ok → Agent → 等待 ok。只执行了一次各服务启动，未遇到启动失败或进行失败重启。

## 3. 第一阶段 PID 与健康结果

| 服务 | 监督 PowerShell PID | 监督进程 Parent PID/名称 | 启动器 PID | 实际监听 PID | 健康 |
|---|---:|---|---:|---|---|
| order | 26860 | 22320 / WmiPrvSE.exe | 31692 | 31692 | HTTP 200 / UP |
| mcp | 19400 | 22320 / WmiPrvSE.exe | 20908 | 24284 | HTTP 200 / ok |
| agent | 4448 | 22320 / WmiPrvSE.exe | 36776 | 15216 | HTTP 200 / ok |

Python venv 启动器与实际监听解释器 PID 不同是正常父子关系。第二阶段必须检查实际监听 PID，同时核对启动器 StartTicks，避免 PID 复用误判。

进程明细（命令行经过现有敏感值过滤）：

| 服务 | PID | ParentProcessId | CreationDate | CommandLine |
|---|---:|---:|---|---|
| order | 31692 | 26860 | 2026-11-01T21:26:03.408441+08:00 | `"E:\JDK17\bin\java.exe" "-Xms64m" "-Xmx320m" "-Dfile.encoding=UTF-8" "-jar" "E:\Simlect-AI-Mall-main\Simlect-AI-Mall-main\Simlect-backend\Simlect-order\app\target\[REDACTED]-order-1.0.0.jar" "--server.address=127.0.0.1" "--spring.cloud.nacos.discovery.ip=127.0.0.1" "--spring.datasource.url=jdbc:mysql://127.0.0.1:13306/[REDACTED]_order?useUnicode=true&characterEncoding=utf-8&serverTimezone=Asia/Shanghai&allowPublicKeyRetrieval=true&allowMultiQueries=true&useSSL=false"` |
| mcp | 28408 | 20908 | 2026-11-01T10:29:32.126448+08:00 | `"E:\wps内容\WPS Office\12.1.0.29161\office6\wps.exe" /wps /from_prome /prome-pipe-token=[REDACTED] /prome-prestart-type=1` |
| mcp | 20908 | 19400 | 2026-11-01T21:27:22.508975+08:00 | `"E:\Simlect-AI-Mall-main\Simlect-AI-Mall-main\Simlect-backend\Simlect-agent\.venv\Scripts\python.exe" "-m" "app.mcp_server"` |
| mcp | 24284 | 20908 | 2026-11-01T21:27:22.525482+08:00 | `"E:\Python\python.exe" "-m" "app.mcp_server"` |
| agent | 36776 | 4448 | 2026-11-01T21:27:30.008829+08:00 | `"E:\Simlect-AI-Mall-main\Simlect-AI-Mall-main\Simlect-backend\Simlect-agent\.venv\Scripts\python.exe" "-m" "uvicorn" "app.main:app" "--host" "127.0.0.1" "--port" "7050"` |
| agent | 15216 | 36776 | 2026-11-01T21:27:30.021159+08:00 | `"E:\Python\python.exe" "-m" "uvicorn" "app.main:app" "--host" "127.0.0.1" "--port" "7050"` |

完整监督进程命令、CreationDate、监听与启动器信息记录于 `.cache/persistent-services-20261101/stage1-identity.json`；原始只读监控输出位于 stage1-monitor.json。脱敏可能同时隐藏与配置密码同字的普通项目名片段，这是过滤行为，不代表启动命令缺失或替换了实际 JAR。

## 4. 日志与退出记录

- order：`E:\Simlect-AI-Mall-main\Simlect-AI-Mall-main\logs\independent-services\order\20261101-212603-0605911b`，监督进程启动时间 `2026-11-01T21:26:00.5658270+08:00`。
- mcp：`E:\Simlect-AI-Mall-main\Simlect-AI-Mall-main\logs\independent-services\mcp\20261101-212722-92d8f333`，监督进程启动时间 `2026-11-01T21:27:19.8631330+08:00`。
- agent：`E:\Simlect-AI-Mall-main\Simlect-AI-Mall-main\logs\independent-services\agent\20261101-212729-915eaa6e`，监督进程启动时间 `2026-11-01T21:27:27.2372690+08:00`。

每个目录分别包含 startup.log、stdout.log、stderr.log、process.json；实际退出后才产生 exit.json。目前三个服务 State=Running，尚未生成 exit.json；ExitCode=null 表示仍在运行，不能写成退出码 0。

日志检查未发现 Python Traceback、OutOfMemoryError/MemoryError 或 ERROR 级启动错误。Agent 有原有 aiomysql 提示：agent_session_memory 表已存在，属于已存在表的 IF NOT EXISTS 检查，不是初始化失败；应用 health=ok。Order 的 JAVA_TOOL_OPTIONS 提示属于正常启动参数回显，经过敏感值过滤。

已有旧 logs/local-run 日志与 PID 记录没有覆盖。新方案使用 logs/independent-services/<服务>/latest.json 选择新批次。

## 5. 第一阶段检查方式与安全边界

使用实际准备好的只读监控命令：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\local\check-agent-services.ps1 -AsJson
```

检查确认三个启动器 PID/StartTicks 与记录一致、相关监听存在、三个健康接口 HTTP 200、状态 UP/ok。健康请求直连本机，不使用系统代理。

本轮没有执行退款、支付、邮件、真实聊天推理或其他业务写入；没有新建验收用户/订单、清理数据或重启中间件。原服务自身启动生命周期及原有后台任务仍按原代码运行，本报告不将其等同于本轮发起业务操作。

## 6. 第一阶段记录的第二阶段计划（历史记录）

**本轮没有执行第二阶段，不能提前填写通过。** 下一次任务应先只读运行监控脚本，并与 stage1-identity.json 比较：

1. Order 实际监听 PID 31692 仍存在且启动时间未变。
2. MCP 实际监听 PID 24284、启动器 PID 20908 仍存在且启动时间/StartTicks 未变。
3. Agent 实际监听 PID 15216、启动器 PID 36776 仍存在且启动时间/StartTicks 未变。
4. 三个监督进程 PID 26860、19400、4448 的存活情况和父进程关系记录下来。
5. 8093/7060/7050 由对应 PID 监听，HTTP 200 且应用状态仍 UP/ok。
6. 检查本次 stdout/stderr、process.json/exit.json，记录是否发生退出；不自动重启缺失服务，不用新 PID 替换后宣称旧实例存活。

只有下一任务的相同实例和健康均通过，才能认定“跨本次 Codex 任务生命周期持续存活”成立。一次跨任务通过也只证明所观察的窗口，不等于长期无人值守稳定性保证。

| 阶段 | 状态 |
|---|---|
| 第一阶段：本轮顺序启动与健康、PID核验 | 通过 |
| 第二阶段：下一任务相同 PID 独立存活 | 待执行 |
| 整体持续运行验收 | 未完成，等待第二阶段 |

## 7. 证据与本轮结束状态

证据目录 `.cache/persistent-services-20261101` 被 Git 忽略：

- dependencies.json：启动前 HTTP 依赖健康；MySQL/Redis/RabbitMQ 的只读检查结果在本轮工具输出中。
- order-create.json、mcp-create.json、agent-create.json：原生创建返回码和监督 PID。
- stage1-monitor.json、stage1-identity.json：用于下一任务逐项比对的基准。
- stage1-log-scan.json：启动日志错误/警告标志及退出记录检查。
- protected.json：既有业务源码、配置、报告和脚本保护哈希，不含真实凭据明文。

本轮仅新增本报告和忽略目录中的运行记录。未提交 Git、未推送、未开始商品搜索开发。正常三个服务保持运行，本次任务结束时不主动停止它们；等待下一轮独立存活检查。

## 8. 第二阶段实际验收：2026-11-02

### 8.1 检查范围及结果

进程与日志快照时间为 **2026-11-02T08:26:32.4854975+08:00**（Asia/Shanghai）；本节覆盖第 6 节历史待执行状态。只读执行既有 check-agent-services.ps1，并额外按指定 PID 查询 Win32_Process、核对系统启动时间及 System 事件日志。没有启动、停止、重启服务，没有修改源码、.env 或启动脚本，没有提交 Git。

| 服务 | 第一阶段监听 PID | 第二阶段对应 PID | 第一阶段 CreationDate（+08:00） | 第一阶段 ParentProcessId | 第二阶段身份对比 | 端口监听 | HTTP 健康 |
|---|---:|---|---|---:|---|---|---|
| Order | 31692 | 不存在 | 2026-11-01T21:26:03.408441 | 26860 | 无当前进程，不能匹配创建时间、命令行、父进程或执行路径 | 8093 无监听 | 无 HTTP 响应，失败 |
| MCP | 24284 | 不存在 | 2026-11-01T21:27:22.525482 | 20908 | 无当前进程，不能匹配创建时间、命令行、父进程或执行路径 | 7060 无监听 | 无 HTTP 响应，失败 |
| Agent | 15216 | 不存在 | 2026-11-01T21:27:30.021159 | 36776 | 无当前进程，不能匹配创建时间、命令行、父进程或执行路径 | 7050 无监听 | 无 HTTP 响应，失败 |

第一阶段完整脱敏命令行见第 3 节及 stage1-identity.json；可执行文件为 Order 的 `E:\JDK17\bin\java.exe`、MCP/Agent 的 `E:\Python\python.exe`。第二阶段三个指定 PID 均不存在，命令行、ExecutablePath、CreationDate、ParentProcessId 均无当前值；不得以磁盘上的旧 process.json 替代活进程信息，也不能将“无法比对”写成“一致”。健康检查目标分别为第 5 节脚本中的 `/actuator/health`、`/health`、`/health`，均未获得成功响应。

原启动器 31692、20908、36776 均不存在。原监督 PID 26860、19400 不存在；PID **4448 已被复用**为 `FMService64.exe`，创建时间 `2026-11-01T23:35:33.0849840+08:00`、ParentProcessId=1164，与第一阶段 PowerShell 创建时间 `2026-11-01T21:27:27.2372690+08:00`、ParentProcessId=22320 不同。当前该进程 ExecutablePath 不可得，不作推断。它不是原 Agent 监督进程。

第一阶段 MCP Processes 数组还收录了 WPS PID 28408，其创建时间早于 MCP 启动，且不是监听 PID；这属于仅按 ParentProcessId 收集相关进程可能误纳入的历史记录，不能作为 MCP 身份或存活证据。本次以明确的监听 PID 24284 为核验对象，不改动原始证据。

### 8.2 日志与退出记录

保留第 4 节全部原日志目录，不删除、不覆盖日志。最近记录如下：

| 服务 | 最新有效记录 | 退出记录 | 结论 |
|---|---|---|---|
| Order | stdout.log 最后写入 2026-11-01T23:29:11.0160255+08:00；23:29:10 出现 Redis SocketException: Connection reset，随后连接 127.0.0.1:16379 被拒绝 | 无 exit.json；旧 process.json 仍为 Running、ExitCode=null | 元数据已过时；精确退出时间、退出码未知，不能把最后日志时间当作退出时间 |
| MCP | stderr.log 最后写入 2026-11-01T21:27:24.3713582+08:00，内容为 StreamableHTTP session manager started；stdout.log 为空 | 无 exit.json；旧 process.json 仍为 Running、ExitCode=null | 精确退出时间、退出码未知；未发现退出堆栈，不代表未退出 |
| Agent | startup.log 新增 Exited with code 1073807364；stderr.log 无新增 Traceback，最后仍是应用启动完成记录 | exit.json：启动器 PID 36776、ExitCode=1073807364、ExitedAt=2026-11-01T23:29:10.3821375+08:00；process.json 为 Exited，监督脚本记录时间为 23:29:10.4843103 | 已确认启动器退出，不能将启动器退出码直接当作监听子进程 15216 的独立退出码 |

没有观察到三服务日志中的 OOM 记录。Order 存在上述新的依赖连接异常堆栈；不能据此认定是业务代码崩溃。Agent 原有 aiomysql 表已存在警告保持不变。

### 8.3 系统重启证据与判断边界

只读系统事件确认：

1. 2026-11-01T23:29:10.0831390+08:00，User32 1074：`MoUsoCoreWorker.exe` 代表 SYSTEM 发起计划内操作系统 Service Pack 重启，原因代码 0x80020010。
2. 23:33:48，Kernel-General 13 记录系统关闭；23:34:00，Kernel-General 12 记录系统启动。
3. 23:35:02，User32 1074：`TrustedInstaller.exe` 代表 SYSTEM 发起计划内操作系统升级重启，原因代码 0x80020003；23:35:08 再次关闭，23:35:20 再次启动。
4. Win32_OperatingSystem.LastBootUpTime 为 **2026-11-01T23:35:20.5000000+08:00**，与事件一致，晚于三个原进程的创建时间。

**已确认：** 两阶段之间 Windows 发生计划更新重启；原服务均不在当前系统会话中，原监听端口为空；Agent 新增退出记录。本次不满足用户规定的相同实例存活与全部健康标准。

**高概率关联：** Agent 退出时间与首次系统重启请求仅相差约 0.3 秒，Order 同时出现 Redis 连接中断，与系统关机过程高度吻合。系统重启足以中断普通后台进程，原方案没有安装开机自启机制。

**尚无法确认：** Order/MCP 的精确终止时刻与退出码、各进程收到何种关闭信号、是否曾在 Windows 重启前受到其他停止事件影响。本轮不能证明 Codex 回收了进程，也不能证明进程已成功脱离 Codex 生命周期；跨任务观察被系统重启混杂，需在无系统重启的观察窗口另行验收，且恢复服务须等待后续授权。

### 8.4 最终验收与证据

| 检查项 | 第二阶段结果 |
|---|---|
| 原监听进程存在且 PID 不变 | 0/3，通过条件未满足 |
| 创建时间、命令行、父进程、执行路径一致 | 0/3 可确认一致；原进程不存在 |
| 正确端口由原进程监听 | 0/3 |
| HTTP 健康 | 0/3 |
| 无新退出记录 | 不满足，Agent 有新退出记录 |
| 持续运行验收 | **未通过** |
| Codex 生命周期独立性的因果判断 | **尚无法确认：期间发生系统重启** |

证据保存在 Git 忽略目录 `.cache/persistent-services-20261101/`：stage2-monitor.json（既有监控输出）、stage2-identity-logs.json（指定 PID、日志与系统启动时间）、stage2-system-evidence.json（系统事件、PID 复用与 Order 异常摘要）。命令和日志内容沿用现有脱敏方式，不包含凭据原文。

本轮保留所有既有未提交修改，只更新本报告及忽略目录中的检查证据。没有自动恢复服务，没有执行退款、支付或其他真实业务操作，没有开始商品搜索开发。验收结束，等待审核。

## 9. 第二次尝试：第一阶段运行记录（2026-11-02）

### 9.1 保护与更新检查

分支仍为 feat/agent-safe-advice-product-search，HEAD 仍为 14726bf267daf7a3ffb622f5f3dff92e427a2541。保留原有未提交代码和报告；对此前 protected.json 中的文件进行 SHA-256 核对，无变化。没有修改业务源码、.env、启动脚本或 C# 日志实现，没有提交 Git。

2026-11-02T09:16:15.9604543+08:00 的只读更新检查：

- LastBootUpTime：2026-11-01T23:35:20.5000000+08:00，与上次第二阶段一致。
- Microsoft.Update.SystemInfo.RebootRequired=false；Windows Update RebootRequired、CBS RebootPending、CBS PackagesPending 均不存在。
- 更新 UX 的 RebootRequired/RebootScheduled/RebootDeadline/IsRebootRequired 值未提供，不能写成显式 false。
- 所查更新/重启名称任务中未发现已排定的近期系统重启。WindowsUpdate Scheduled Start 的动作仅为启动 wuauserv，不等于重启系统；RUXIM PLUGScheduler 下次运行是当日 17:54:20，不能将其等同于已排定系统重启。Device Install Reboot Required 任务 Ready、无下次运行时间，仅凭任务存在不能认定当前需要重启。
- **风险保留：** PendingFileRenameOperations 非空，包含打印驱动文件替换及 ToDesk/ZulerCoreTools 操作。它不能单独证明 Windows Update 正等待重启，也不能承诺系统未来不会重启。没有清除标记、关闭更新、暂停更新或修改计划任务。下一阶段必须再次验证系统启动时间与重启事件。
- 一次只读检查因自动权限审批超时未执行；重试成功。最初任务信息存在空日期字段，后续兼容处理；完整的任务字段另存 scheduled-restarts-summary.json，避免将早期序列化截断内容作为判断依据。

### 9.2 启动顺序与已有实例

启动前发现 Order 已由现有脚本运行，PID 22608，创建于 09:05:46，8093 监听且 HTTP 200/UP；本任务没有启动或重启 Order，没有将其冒称为本任务创建。

保留该实例，确认 Order 健康后，以 Windows 原生 Win32_Process.Create 创建隐藏 PowerShell，执行既有 start-mcp.ps1；MCP `/health` 返回 HTTP 200/ok 后，以同一方式执行 start-agent.ps1。两次原生创建返回值均为 0；没有重复创建或失败重试，也没有重启任何 Docker 中间件。

| 服务 | 实际监听 PID | CreationDate（+08:00） | ParentProcessId | ExecutablePath | 端口 | 健康 |
|---|---:|---|---:|---|---:|---|
| Order（复用） | 22608 | 2026-11-02T09:05:46.4602770 | 22376 | E:\JDK17\bin\java.exe | 8093 | HTTP 200 / UP |
| MCP（新增） | 13924 | 2026-11-02T09:19:00.3816870 | 7412 | E:\Python\python.exe | 7060 | HTTP 200 / ok |
| Agent（新增） | 23372 | 2026-11-02T09:20:24.0943810 | 19024 | E:\Python\python.exe | 7050 | HTTP 200 / degraded |

| 服务 | 启动器 PID | 启动器 StartTicks | 监督 PowerShell PID | 监督进程父 PID |
|---|---:|---|---:|---:|
| Order | 22608 | 639291783464602774 | 22376 | 6520（Explorer） |
| MCP | 7412 | 639291791402824710 | 23152 | 6084 |
| Agent | 19024 | 639291792240446189 | 3264 | 6084 |

Order 监督 PowerShell 创建时间为 08:30:10.1919430，来自现有桌面会话；MCP/Agent 监督创建时间分别为 09:18:56.4001010、09:20:20.1439560。父进程结构只能作为当前身份记录，不能代替下一任务存活验证。

完整的脱敏 CommandLine、ExecutablePath、CreationDate、ParentProcessId 和原始命令行 SHA-256 保存在 `.cache/persistent-services-attempt2-20261102/stage1-identity.json`。下一阶段同时比对文本与哈希，避免脱敏掩盖命令行差异；不得输出凭据原文。

### 9.3 健康与日志的实际限制

身份快照时间：2026-11-02T09:21:16.6744572+08:00。三个启动器均通过 PID/StartTicks 身份核验，三个监听均对应上表实际进程，本批次均无 exit.json。

Agent 健康复查正文：`{"redis":true,"mysql":true,"elasticsearch":true,"java_web":false,"status":"degraded"}`。日志出现 `health_java_web_failed`，错误详情为空；不能仅根据此事件确认是 Gateway 退出、认证失败、网络异常或其他具体原因。本轮未额外启动 Gateway、修改配置或重启 Agent。Agent 应用已完成启动，但**整体健康不通过**，HTTP 200 本身不足以满足验收。

最近 100 行日志检查：Order/MCP 未命中 ERROR、Traceback、OOM；Agent stdout 有一次健康探测错误，stderr 仅有已有 aiomysql 表已存在警告。未发现本批次启动失败或异常退出记录；这不等同于证明长期无异常。

本批次日志目录（均在 E 盘，旧日志完整保留）：

- Order：`logs/independent-services/order/20261102-090546-b2f00e9a`。
- MCP：`logs/independent-services/mcp/20261102-091859-695bd2e0`。
- Agent：`logs/independent-services/agent/20261102-092023-a967f07c`。

既有脚本分别记录 startup.log、stdout.log、stderr.log、process.json，进程实际退出时尝试记录 exit.json；监督进程被外部强制关闭仍可能来不及写退出记录，故后续必须查活进程与端口，不能信任旧 State=Running。

### 9.4 下一独立任务的验收要求

本任务结束时不主动停止上述服务。**第二阶段尚未执行，不提前宣称脱离 Codex 生命周期。**

至少在本任务最终回复结束 **15 分钟后**，由下一次独立 Codex 任务进行只读复核；同时不得早于身份快照的 NotBefore：2026-11-02T09:36:16.6744572+08:00。两项取更晚时间，不能仅因为进程从启动至今已超过 15 分钟，就省略跨任务观察窗口。

1. LastBootUpTime 必须仍为 2026-11-01T23:35:20.5000000+08:00，结合期间系统事件确认无重启；若再重启，判为观察中断，不能用于推断 Codex 回收。
2. 核对监听 PID 22608、13924、23372 的 CreationDate、ParentProcessId、ExecutablePath、CommandLine 与 SHA-256；同步核对两个 venv 启动器、监督进程和启动器 StartTicks。
3. 端口 8093/7060/7050 必须仍归对应实例，HTTP 和应用状态分别记录。Agent 当前 degraded，若下一阶段仍 degraded，不能将整体健康写为通过；即便相同实例持续存在，也应区分“进程独立存活”和“业务依赖健康”。
4. 检查本批次最新 stdout/stderr、process.json/exit.json，不将上一批次 Agent 的退出记录误算为新实例退出。
5. 下一任务不自动启动、停止、重启或修复任何进程；PID 不同或缺失则如实记录。

证据目录均在 E 盘 `.cache/persistent-services-attempt2-20261102/`：update-markers.json、scheduled-restarts-summary.json、prestart-services.json、mcp-create.json、agent-create.json、stage1-monitor.json、stage1-identity.json、agent-health-detail.json。原始含待文件替换路径的证据留在忽略目录，不纳入提交。

| 项目 | 本次状态 |
|---|---|
| Windows Update 明确待重启标记 | 未发现；存在其他待文件替换记录，保留风险 |
| 三服务存在且端口匹配 | 通过（Order 复用，MCP/Agent 本轮新增） |
| 三服务全部应用健康 | **未通过：Agent degraded / java_web=false** |
| 至少 15 分钟跨任务相同实例存活 | **尚未验证，等待下一独立任务** |
| 整体持续运行验收 | **未完成** |

本轮未调用外部模型、执行退款或支付，未改业务代码、环境配置、脚本、更新策略、数据库或中间件。报告保留上次 Windows 重启中断记录，与本轮当前状态分别记录。到此暂停，等待下一阶段只读检查。

## 10. 第二次尝试：第二阶段只读验收结果

### 10.1 观察窗口与重启排除

本阶段由用户在上一任务最终回复后再次发起。首次只读操作时间为 **2026-11-02T09:25:33.8244464+08:00**；初次快照 09:27:11，中途检查 09:35:30，最终快照 **2026-11-02T09:41:47.6448377+08:00**。

用户发起检查时距离第一阶段结束不足 15 分钟，因此没有提前判为通过，而是在本轮继续等待并复核。最终距本轮首次操作约 **16 分 14 秒**，距第一阶段身份快照 09:21:16 约 **20 分 31 秒**，且晚于原定 NotBefore 09:36:16；由于上一任务最终回复早于本轮首次操作，跨任务观察窗口也已超过 15 分钟。

系统 LastBootUpTime 仍为 **2026-11-01T23:35:20.5000000+08:00**，与第一阶段一致。查询 09:21:16 以来 System 日志中 User32/EventLog/Kernel-General/Kernel-Power 的相关启动、关闭和重启事件，未发现重启事件。与第 8 节上一次被 Windows 计划更新重启打断的观察不同，**本次观察窗口未被系统重启打断**。

### 10.2 逐项进程身份与端口比较

| 服务 | 第一阶段 PID → 第二阶段 PID | 第一阶段 CreationDate（+08:00） | 第二阶段 CreationDate（+08:00） | ParentProcessId（前 → 后） | ExecutablePath（前后相同） | 监听端口与所属 PID（前后相同） |
|---|---|---|---|---|---|---|
| Order | 22608 → 22608 | 2026-11-02T09:05:46.4602770 | 2026-11-02T09:05:46.4602770 | 22376 → 22376 | E:\JDK17\bin\java.exe | 8093 → 22608 |
| MCP | 13924 → 13924 | 2026-11-02T09:19:00.3816870 | 2026-11-02T09:19:00.3816870 | 7412 → 7412 | E:\Python\python.exe | 7060 → 13924 |
| Agent | 23372 → 23372 | 2026-11-02T09:20:24.0943810 | 2026-11-02T09:20:24.0943810 | 19024 → 19024 | E:\Python\python.exe | 7050 → 23372 |

命令行核对使用原始 CommandLine 的 SHA-256，同时保留脱敏全文。下列哈希在第一、第二阶段完全一致，未仅凭 PID 判定：

| 服务 | CommandLine SHA-256（前后相同） | 命令结构 |
|---|---|---|
| Order | 4fceb63ce052e02ee496925c85ba82a8304795396a43eff42457d42833817f19 | java.exe -Xms64m -Xmx320m -Dfile.encoding=UTF-8 -jar 现有 Order JAR，含原 server.address/Nacos IP/MySQL URL 参数 |
| MCP | 6310ca4e5eac4359336d7f306e4cc8bbc15419aeb70b26e88b30d4ff29a7353e | E:\Python\python.exe -m app.mcp_server |
| Agent | 0b388ee69dce2cb67503903c1e3b36c529427652197873f00c427d4b3e033f38 | E:\Python\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 7050 |

完整脱敏命令行、可执行路径与各项比较见 stage2-final-verification.json。三个监督进程 22376/23152/3264、两个 Python venv 启动器 7412/19024 也仍为同一实例；其 PID、创建时间、父进程、执行路径、命令行哈希全部一致，三个启动器 StartTicks 通过既有监控脚本验证。

**核验工具更正说明：** 早期 stage2-early-snapshot.json 的 CreationMatches 字段因 PowerShell 将已解析的日期对象隐式转成不含小数秒的字符串而错误显示 false。保留该原始证据；随后改用显式 DateTimeOffset.UtcTicks 比较，8 个记录均一致，更正证据为 stage2-early-creation-comparison-corrected.json；最终快照也使用完整 ticks 比较，全部 true。这是本轮临时核验表达式的精度问题，未修改业务源码或既有监控脚本，也不是服务创建时间变化。

### 10.3 HTTP 与业务依赖健康

| 服务 | 第一阶段 HTTP/status | 第二阶段 HTTP/status | 结果 |
|---|---|---|---|
| Order | 200 / UP | 200 / UP | 健康接口正常响应 |
| MCP | 200 / ok | 200 / ok | 健康接口正常响应 |
| Agent | 200 / degraded | 200 / degraded | 进程可响应，业务依赖尚未全部健康 |
| Gateway | 第一阶段未单独断定具体故障 | 8080 无监听，健康请求连接被拒绝 | 当前不可用，未启动或修复 |

Agent 最终 `/health` 原文（不含凭据）：

```json
{"redis":true,"mysql":true,"elasticsearch":true,"java_web":false,"status":"degraded"}
```

Gateway `/actuator/health` 和 `/api/` 的直接本机 GET 均未得到 HTTP 响应，最内层异常为 `System.Net.Sockets.SocketException`，信息为“由于目标计算机积极拒绝，无法连接”，目标 127.0.0.1:8080；监听查询也为空。

只读源码核对：`Simlect-backend/Simlect-agent/app/services/health_service.py` 的 `HealthService.check_all()` 会以 httpx 三秒超时请求 `settings.java_web_url + /api/`。Agent 日志新增 `health_java_web_failed`，但原日志 `error` 字段为空、无异常类型或堆栈。因此可以确认 Java Web 依赖检查失败和本机 Gateway 端口不可用，两者一致；不能凭空补写 Agent 内部捕获的具体异常类型，也未进一步修改日志或业务实现进行诊断。

### 10.4 从本批次启动至今的日志检查

完整读取第 9.3 节三个原批次的 startup.log/stdout.log/stderr.log，检查 process.json/exit.json 和 latest.json；未清理或覆盖原日志。

- 三个 latest.json 均仍指向第一阶段的同一批次目录；三个服务都没有 exit.json，没有退出/停止记录，没有重复启动标记。
- Order 日志仅记录一次启动，MCP 记录一次 session manager started，Agent 记录一次 agent_service_started 和 Started server process [23372]；未观察到进程重启。多次快照的端口和原 PID 一致，未观察到端口变化。此结论基于快照与日志，不宣称已经连续抓取每一次套接字事件。
- Order、MCP 全批次日志中未发现新的 ERROR、异常堆栈或依赖连接失败。三服务未发现 Traceback 或 OOM 记录。
- Agent 共记录 6 次 `health_java_web_failed`：09:21:16、09:22:09、09:27:04、09:27:09、09:35:30、09:41:38；包含第一阶段已有记录与本次健康请求产生的记录，不应将这些探测错误误判成 Agent 退出。没有新异常堆栈。
- Agent stderr 原有 aiomysql “agent_session_memory 表已存在”警告仍在，无新增启动异常。没有真实聊天、外部模型、支付或退款调用。

### 10.5 两个维度的验收结论

| 维度 | 结果 | 依据 |
|---|---|---|
| A：进程独立存活 | **通过（本次观察窗口）** | 三个相同实例在上一任务结束后继续存在，完整身份及监听端口匹配，HTTP 均正常响应；已超过 15 分钟，系统没有重启，无异常退出记录 |
| B：Agent 业务依赖健康 | **未通过** | java_web=false、status=degraded；Gateway 8080 无监听，请求被拒绝 |

**进程独立存活验证通过，但 Agent 业务依赖健康尚未通过。**

这次通过证明所观察的跨任务窗口内相同实例持续存活，不等于长期无人值守稳定性、开机自启或重启后自动恢复保证；也不能据此承诺完整商城业务已可用。Gateway 不可用的进一步原因、本次之外的更长运行窗口尚未验证，等待审核后的另行指令，不自动恢复。

### 10.6 证据与保护结果

E 盘忽略目录 `.cache/persistent-services-attempt2-20261102/` 新增：

- stage2-early-snapshot.json：早期身份与 HTTP 快照。
- stage2-early-creation-comparison-corrected.json：日期精度核对更正。
- stage2-log-audit.json：完整批次日志与系统事件早期核对。
- stage2-mid-monitor.json：09:35 中途只读监控。
- stage2-final-verification.json：最终逐项身份、命令行哈希、健康详情、Gateway、日志与重启事件证据。
- stage2-file-protection.json：业务源码、配置与脚本保护核对，既有受保护文件未变化。

本轮仅更新本报告及 E 盘忽略目录中的验收记录；没有启动、停止、重启任何服务，没有重启 Docker，没有修改源码、.env、配置、启动脚本或更新策略，没有删除日志或数据，没有提交/推送 Git，没有开始商品搜索开发。完成后暂停，等待审核。
