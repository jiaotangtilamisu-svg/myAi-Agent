# 项目专用浏览器回归

本目录使用固定的 `@playwright/test 1.65.0` 和配套 Chromium。它自行启动浏览器，通过内部管道控制，不接管个人 Chrome，不使用个人 profile 或远程调试端口，不导出 Cookie、Token、storageState。

浏览器、npm 缓存、临时目录、视频及报告全部在 E 盘。商城和管理端为独立 BrowserContext，测试账号仅从 `.cache/stage34/<runId>/browser-fixtures-private.json` 读取，不进入测试日志。

## 当前隔离环境

- 商城：`http://127.0.0.2:16001`
- 管理端：`http://127.0.0.2:16002/admin/`
- 正式 6001/6002 地址被写入测试拒绝；不会悄悄退回正式地址。
- 复用已通过验证的 Stage34 命名空间、账号与小样本，不重置已有夹具。

## 一条命令

在项目根目录执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\e2e\run-e2e.ps1 -Suite all -WithRegression -CloseBrowser -CleanTestData
```

顺序为：隔离夹具只读核对、必要服务健康、项目浏览器登录、Python/Java/前端回归、真实浏览器退货及异常分支、SQL结果验证、截图视频、测试业务行清理。原始失败报告保存在各次运行目录，不删除失败断言。默认真实 API 关闭。

首次启动会填入专用测试账号。请只在新 Chromium 中人工完成验证码和普通登录；不自动识别验证码，不创建假会话。登录未完成会明确阻塞，而非绕过认证。进程持续持有两个上下文，后续测试不重新登录。页面按钮写业务状态，数据库查询只负责独立验证。

已有浏览器会话时，脚本复用项目自己的 Node/Chromium 会话，不重新启动浏览器。商城和管理端分别使用 E 盘本批次 `browser-profiles/shop`、`browser-profiles/admin`，由 Chromium 正常保留测试登录；不读取认证内容，不导出 storageState，也不使用个人 profile。会话失效仍需正常验证码登录。文件队列仅传递明确页面操作；不提供任意 JavaScript、网络请求或数据库写入操作。Playwright Test 负责断言和 HTML/JSON 报告。

仅回归退货主链：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\e2e\run-e2e.ps1 -Suite return
```

## 证据与保密

运行目录由 `.cache/stage34/active.json` 指定。`runs/<timestamp>/gates.json` 是分层结果，`playwright-report/index.html` 是浏览器结果。`browser-artifacts` 保存截图、两个业务视频和不含请求正文/认证头的 HTTP 元数据；登录页视频被丢弃。关闭原生 trace/HAR，避免把授权头保存进追踪文件。

单元/Mock回归与本机浏览器业务结果分别统计；费用接口经独立限额代理控制，未经本轮具体批准不启用。`-EnableRealApi` 不是授权本身；真实调用受 4 次 LLM / 6 次 Embedding、20 秒、512 输出 Token、零重试和失败锁保护。

`-CleanTestData` 只清理由本浏览器流程创建的隔离案件、方案、人工任务、审计、消息和测试 Agent 缓存；先保存完整摘要。保留两个测试用户、商品/SKU/库存、订单及61条法规只读副本。不会 TRUNCATE、重置自增、删除正式记录、清空Redis、删索引或 Docker 卷。

若必要服务失效，脚本停止并报告，不通过反复重启健康服务掩盖故障。业务回归失败保留现场及已登录浏览器，关闭/清理选项只在门禁全部成功时执行。关闭时校验视频确属本次登录会话，不用上次视频冒充。
