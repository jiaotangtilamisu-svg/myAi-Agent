# 13-Product服务启动验收报告

检查日期：2026-11-02（北京时间）。本轮仅批准 Product 单次启动，不批准 Stock、Search 或其他服务恢复。

## 1. 结论

**Product 单服务启动与健康检查通过；本轮整体验收未通过。**

Product 实际 Java PID 为 **15276**，监听 127.0.0.1:8099，HTTP 200 / UP，Nacos 实例 healthy/enabled=true，MySQL、Redis 连接成功，布隆预热完成。

但启动后核对发现 Order 22608、MCP 13924、Agent 23372 均已不存在，相关端口连接被拒绝。Gateway 17164 保持运行且 HTTP 200 / UP。未执行任何其他服务的停止、启动或恢复命令；现有证据不足以确认三个服务退出的触发来源，不将时间上的相邻关系写成 Product 导致退出。

## 2. 启动前检查

11:19:24 进程/环境快照，11:20:16 数据连接与 Redis 快照：

| 检查项 | 实际结果 |
| --- | --- |
| Git 分支 | feat/agent-safe-advice-product-search |
| HEAD | 14726bf267daf7a3ffb622f5f3dff92e427a2541 |
| 工作区 | 原有第一轮代码、测试及报告修改保留，未提交、未清理 |
| Product 原实例与端口 | 未发现 Product Java 实例；8099 未占用 |
| JDK | E:\JDK17\bin\java.exe，17.0.3.1 |
| 可执行包 | Simlect-backend/Simlect-product/app/target/simlect-product-1.0.0.jar 存在 |
| JAR SHA-256 | 228491703ae752224d1ffb0decd1f26e631ce0913873df686abfcbd1c931faf7 |
| MySQL | 127.0.0.1:13306 / simlect_product，现有应用凭据 SELECT 1 成功，product_info 8 行 |
| Redis | PING 成功；既有布隆主键与配置键均存在 |
| Nacos | readiness HTTP 200 / OK |
| 可用物理内存 | 2.098 GiB；资源偏紧已在启动前说明 |
| Windows 更新 | RebootRequired=false |

启动前四个核心 PID 均存在且创建时间与既有验收记录一致，见第 6 节。未输出任何密码、Token 或密钥。

## 3. 实际启动方式及进程

复用第 12 号报告确认的命令，仅执行一次：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\deploy\run-configured.ps1 -Stage Java -Service product
```

工作目录为 `E:\Simlect-AI-Mall-main\Simlect-AI-Mall-main`。通过 Windows Win32_Process.Create 启动独立 PowerShell，增加 `-WindowStyle Hidden`，返回值为 0；未使用 Codex 临时会话持续托管 Java。没有重建 JAR 或修改启动脚本。

| 项目 | 实测值 |
| --- | --- |
| 请求时间 | 2026-11-02T11:21:27.7494269+08:00 |
| Launcher PID | 26180（启动脚本完成后已退出） |
| 实际 Java PID | 15276 |
| Java ParentProcessId | 26180 |
| Java CreationDate | 2026-11-02T11:21:36.9525840+08:00 |
| ExecutablePath | E:\JDK17\bin\java.exe |
| Java 工作目录 | E:\Simlect-AI-Mall-main\Simlect-AI-Mall-main\Simlect-backend\Simlect-product\app |
| 监听 | 127.0.0.1:8099 → PID 15276（netstat 实测） |

实际 Java 命令参数为：

```text
"E:\JDK17\bin\java.exe" -Xms64m -Xmx320m -Dfile.encoding=UTF-8 -jar "E:\Simlect-AI-Mall-main\Simlect-AI-Mall-main\Simlect-backend\Simlect-product\app\target\simlect-product-1.0.0.jar" --server.address=127.0.0.1 --spring.cloud.nacos.discovery.ip=127.0.0.1 --spring.datasource.url=jdbc:mysql://127.0.0.1:13306/simlect_product?useUnicode=true&characterEncoding=utf-8&serverTimezone=Asia/Shanghai&allowPublicKeyRetrieval=true&allowMultiQueries=true&useSSL=false
```

沿用现有脚本环境加载，未覆盖 .env；运行时 JAVA_TOOL_OPTIONS 指向 E:\SimlectRuntime\tmp。

## 4. 日志保护与启动日志

旧 product.out.log、product.err.log、product.process.json 先复制备份到：

`E:\Simlect-AI-Mall-main\Simlect-AI-Mall-main\logs\product-start-backup\20261102-112127\`

原文件同时保留为 `logs/local-run/<原文件名>.pre-start-20261102-112127`，腾出原固定输出路径，未删除或覆盖历史内容。三个备份和三个保留原文件的 SHA-256 均与启动前一致。

本次新日志：

- stdout：`E:\Simlect-AI-Mall-main\Simlect-AI-Mall-main\logs\local-run\product.out.log`
- stderr：`E:\Simlect-AI-Mall-main\Simlect-AI-Mall-main\logs\local-run\product.err.log`
- PID 记录：`E:\Simlect-AI-Mall-main\Simlect-AI-Mall-main\logs\local-run\product.process.json`

关键日志时间：11:21:51 Tomcat 启动；11:21:52.526 Nacos 注册完成；11:21:52.738 Spring 启动完成；11:21:53.102 MySQL Hikari 启动完成；11:21:53.247 “商品布隆过滤器已预热全量商品 8 个”。

截至日志检查，预热成功记录 **1 次**，ERROR 行 **0**，关闭/启动失败标记 **0**；stderr 仅见 JAVA_TOOL_OPTIONS 提示。既有 commons-logging、开发模式和默认负载均衡缓存提示仍存在，不算启动失败。

**E 盘要求的现有限制：**本次证据、备份及 stdout/stderr 均保存在 E 盘，但既有 Sentinel 组件日志明确提示其默认目录仍是 `C:\Users\Administrator\logs\csp\`。本轮禁止修改配置，因此没有改动该目录设置；不能宣称所有第三方组件日志均已迁移到 E 盘。

## 5. Redis 布隆过滤器对比

使用只读 SCAN/TYPE/PTTL/MEMORY USAGE/DUMP 哈希/STRLEN/BITCOUNT/HGETALL 核对，不保存完整 Redis 内容，不执行删除、清空或配置修改。

| Key | 类型 | 启动前 / 后结果 |
| --- | --- | --- |
| mall:product:bloom | string | 长度均 897046 字节；BITCOUNT 均 80；MEMORY USAGE 均 917568；PTTL 均 -1 |
| {mall:product:bloom}:config | hash | MEMORY USAGE 均 168；PTTL 均 -1；配置完全相同 |

配置：size=7188793、hashIterations=10、expectedInsertions=500000、falseProbability=0.001。

主键 DUMP SHA-256 前后均为 `60d473ba9a8a0cfe6494656bbe370c128391942080867bcec519bd4553561e88`；配置键均为 `01b4dc76cec9b4fbe42b979cccce1c5b666eefbf710cfe6ae2f765543645aee9`。没有新增匹配的布隆 Key。

结合既有 ProductBloomFilterComponent 的 tryInit/add 流程，启动确实进行了授权的预热写入尝试，日志显示完成 8 个商品；已有过滤器结果保持不变，未观察到重置、扩容或第二次预热。代码没有记录 tryInit 返回值，未逐条抓取 Redis 命令，因此不能声称“没有发出写命令”或对瞬时操作做超出快照范围的保证。

## 6. 启动后健康与原有服务

11:26:06 快照：

| 服务 | 启动前 PID / 创建时间（+08:00） | 启动后 | 健康 |
| --- | --- | --- | --- |
| Product | 无 | 15276 / 11:21:36.9525840，8099 | HTTP 200 / UP |
| Gateway | 17164 / 09:55:44.8109750 | 同 PID、同创建时间，8080 | HTTP 200 / UP |
| Order | 22608 / 09:05:46.4602770 | 原 PID 不存在，8093 无监听 | 连接拒绝 |
| MCP | 13924 / 09:19:00.3816870 | 原 PID 不存在，7060 无监听 | 连接拒绝 |
| Agent | 23372 / 09:20:24.0943810 | 原 PID 不存在，7050 无监听 | 连接拒绝 |

Product Nacos 实例：public（空 namespace ID）、DEFAULT_GROUP、simlect-product、127.0.0.1:8099、DEFAULT cluster、healthy=true、enabled=true、ephemeral=true。

11:25:06 应用凭据再次执行 MySQL SELECT 1 成功，product_info 仍为 8 行；Redis PING 成功。行数一致仅是只读快照，不等于全库写入审计。

Stock 8102、Search 8108 均未监听，本轮未启动它们，未调用 MCP 商品搜索、Embedding 或商品业务写接口。

## 7. 内存与意外退出记录

可用物理内存从启动前 **2.098 GiB** 变为 11:26:06 的 **4.661 GiB**（增加 2.563 GiB）。期间三个原有服务退出，因此不能把系统内存差值当作 Product 的内存消耗或优化成果，也未据此认定 OOM。

只读追加检查找到已有监控自动生成的 exit.json：

| 记录对象 | 时间（+08:00） | ExitCode |
| --- | --- | --- |
| MCP 启动父进程 7412 | 11:25:34.4918926 | -1073741510 |
| Agent 启动父进程 19024 | 11:25:34.5116352 | -1073741510 |
| Order Java 22608 | 11:25:34.5987956 | -1073741510 |

该值对应 0xC000013A，符合控制台中断类退出。MCP/Agent 记录的是虚拟环境启动父进程，不能替代实际服务子进程 13924/23372 的精确退出码或退出时间。process.json 仍保留旧 Running 状态，必须结合 exit.json 和实时进程判断。

Windows LastBootUpTime 仍为 2026-11-01T23:35:20.5000000+08:00，排除本次观察期间系统重启。所读日志末尾未见本时段新的 Python Traceback 或 Java 致命异常；Order 10:20 的登录超时为此前记录，不能作为本次退出原因。**共同中断来源、是否有人关闭控制台、宿主事件及精确子进程退出机制尚未确认。**未自动恢复，也未执行停止命令。

## 8. 文件保护、证据与后续事项

既有受保护文件快照复核无哈希不一致；本轮额外复核部署脚本、Agent .env、Product application.yml 与 JAR 均未改变。没有修改业务源码、配置、数据库结构，没有 Git 提交、Docker 重启、支付、退款或模型调用。

证据在 `E:\Simlect-AI-Mall-main\Simlect-AI-Mall-main\.cache\product-start-20261102\`：preflight.json、redis-before.json、redis-after.json、start-request.json、log-backups.json、acceptance.json、core-exit-observation.json。退出记录保留在各 `logs/independent-services/<service>/<run>/exit.json`；未清理日志。

已通过：Product 单次启动、端口/PID 对应、健康、Nacos 注册、MySQL/Redis 连接、布隆预热与前后快照核对、历史日志保护。

未通过：原有四服务均保持运行的要求（仅 Gateway 保持）。尚未验证：Product 跨 Codex 任务独立存活、15 分钟持续运行、Product→Stock 查询与商品搜索业务效果。Stock 未获启动授权，Search 未恢复。

建议下一步先审核本报告，对三个服务的共同控制台中断做只读诊断，再决定恢复方案；本轮到此暂停，不启动 Stock 或开始商品搜索开发。
