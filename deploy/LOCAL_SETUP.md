# 本机配置记录（2026-11-01）

项目根目录：`E:\Simlect-AI-Mall-main\Simlect-AI-Mall-main`。

## E 盘位置

- JDK：`E:\JDK17`（17.0.3.1）。
- Node/npm：`E:\Nodejs`（24.18.0 / 11.16.0）。
- Maven：`E:\develop\apache-maven-3.9.4-bin\apache-maven-3.9.4`；已有依赖仓库位于其 `mvn_repo`。
- Python：`E:\Python`（3.12.0）；项目新环境位于 `Simlect-backend\Simlect-agent\.venv`。原环境保留为同目录的 `.venv-backup-*`。
- pip 下载缓存：项目 `.cache\pip`。
- Docker Desktop 配置中的 WSL 数据目录：`E:\Docker\data`；容器数据使用 Docker volumes。
- 构建及启动日志：项目 `logs`。

## 本地中间件

Compose 项目名为 `simlect-local`，同时使用 `docker-compose.middleware.yml` 和 `docker-compose.local.yml`。

| 服务 | 本机端口 | 配置 |
|---|---|---|
| MySQL 8.3 | 13306 | 项目独立容器；开发账号 root/root |
| Redis 7 | 16379 | 项目独立容器 |
| RabbitMQ 3.13 | 5672 / 15672 | 开发账号 simlect/simlect |
| Nacos 2.4.3 | 8848 / 9848 | 注册发现 |
| Elasticsearch 9.2.1 + IK | 9200 | 已构建项目镜像；启动需足够内存 |
| Sentinel 1.8.8 | 8858 | 控制台 |

已在验证为空的项目 MySQL 中导入 `00`、`00b`、`14`、`15`、`16`、`01` 至 `10`、`13` SQL。不要重复初始化数据库。

本地启动采用项目已有 `SEATA_ENABLED=false` 选项，因此未安装 Seata Server。支付采用已有的本地模拟模式。

## 应用配置

- 前端 `Simlect-web/.env.development.local`：API 代理到 `127.0.0.1:8080`，Agent 到 `7050`；前端端口 `6001`。
- 管理端沿用原有配置，端口 `6002`，路径 `/admin/`。
- Python `.env` 保留原有内部令牌及连接设置，补充随机 `GRAPH_CHECKPOINT_HMAC_SECRET`；密钥不记录在本文。
- AI 的 `LLM_API_KEY` 和 `EMBEDDING_API_KEY` 目前为空，需要在 Python `.env` 中填写才能使用真实 AI 对话与向量检索。

## 启动

在项目根目录打开 PowerShell：

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\run-configured.ps1
```

也可分阶段运行 `-Stage Check`、`Java`、`Python`、`Frontend`。脚本仅为当前启动进程设置 E 盘工具路径。

启动完整 Java 服务前需至少 4 GiB 空闲物理内存；本次安装时仅剩约 1 GiB，完整后端尚未完成启动验证。

页面：`http://127.0.0.1:6001` 和 `http://127.0.0.1:6002/admin/`。

## 已验证

- Java 26 个 Maven 模块打包成功（此次跳过测试），见 `logs/setup-maven-offline.log`。
- 两个前端生产构建通过，见 `logs/setup-web-build.log`、`logs/setup-admin-build.log`。
- 两个开发页面 HTTP 200。
- MySQL、Redis、RabbitMQ、Nacos 容器 healthy；Sentinel 容器运行。

前端页面可访问不代表后台业务流程已完成联调。

- Python 运行依赖已安装，pip check 和 Agent/MCP 模块导入通过；版本记录于 requirements-local.lock.txt。
- 本地 Compose 已降低 MySQL 缓冲池（256M）、Nacos 堆（512m）、Elasticsearch 堆（768m）、Sentinel 堆（256m），适配 16GB 电脑。

- Elasticsearch 已启动，集群健康接口 HTTP 200。
- MCP :7060/health 和 Agent :7050/health 均 HTTP 200；Agent 报 degraded，尚无真实 AI 对话验证。
- 降低内存后剩余约 2.4 GiB，Java 全服务启动仍受至少 4 GiB 空闲内存检查限制。

## 环境收尾（2026-11-01）
- 本地所有连接地址已统一；上传文件目录固定在项目 data/simlect/upload。
- 管理员账号为 admin，随机密码存放在 Simlect-backend/Simlect-agent/.env 的 ADMIN_PASSWORD 中，请仅在本机查看。
- Java 启动脚本已处理空 AI 密钥的本地占位回退，并适配 Python / Java 不同的 Embedding Base URL 格式。占位密钥无法调用真实 AI。
- 本轮仅完成配置与静态验证，没有启动应用服务。外部 AI 密钥需用户自行填写；真实支付宝证书及地图等第三方凭据仅使用相关功能时需要。

最新修复、真实流程验收和体验账号说明请查看 deploy/REPRODUCTION.md。历史内存与未验证状态仅对应当时检查时间；现已完成本地模拟支付流程验证。
