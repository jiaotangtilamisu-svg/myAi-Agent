# 本地复现与体验说明

从 [myAi-Agent](https://github.com/jiaotangtilamisu-svg/myAi-Agent) 下载源码后，在项目根目录执行下文的命令。

订单库初始化使用 [sql/05_order.sql](../sql/05_order.sql)，其中已修复 SQL 注释的引号。

## 已修复

- Nacos 注册地址与监听地址统一为 127.0.0.1，恢复网关、验证码、商品接口和微服务内部调用。
- 管理前端进程记录改为 admin-ui，避免与 Java 管理服务重名。
- JDK 临时目录固定为 E:\SimlectRuntime\tmp，解决旧 JDK 的 Windows 本地套接字初始化问题。
- HTTP 开发代理保留原始 Host，解决后台登录因 localhost / 127.0.0.1 不一致被同源校验拒绝的问题；保留同源校验。
- 补齐公开搜索接口 /api/search/products 并修复前端调用。
- 加入 8 个明确标注的本地演示商品、分类、图片、规格和库存；预热详情缓存并同步关键词索引。
- 建立随机密码的本地演示账号，首次登录后按原项目逻辑升级为 BCrypt。
- 电脑和手机支付页支持明确标注的本地模拟支付：生产模式禁止、必须登录、校验订单归属、使用服务端金额和原订单状态机，不产生真实扣款。

## 如何体验

1. 打开 Docker Desktop，在项目根目录执行 `powershell -ExecutionPolicy Bypass -File .\deploy\run-configured.ps1`。
2. 商城：http://127.0.0.1:6001/ ，后台：http://127.0.0.1:6002/admin/ 。旧页面先 Ctrl+F5 刷新。
3. 查看 `Simlect-backend/Simlect-agent/.env`：商城账号在 LOCAL_DEMO_EMAIL，密码在 LOCAL_DEMO_PASSWORD；后台账号在 ADMIN_ACCOUNT，密码在 ADMIN_PASSWORD。不要分享该文件。
4. 商城登录后选择演示商品、规格、数量，加入购物车或立即购买，添加演示地址并提交订单。
5. 支付页点击「确认模拟支付」，再去「我的订单」查看待发货状态。没有真实扣款或发货。

## 已验证

- 搜索接口回归 8 项通过：logs/search-fix-build.log。
- 模拟支付的生产禁用、订单归属、服务端金额测试 3 项通过：logs/local-payment-build.log。
- 商城前端构建通过：logs/web-final-build.log。
- 真实本地 HTTP 流程：验证码、登录、个人信息、分类、详情、搜索、加购、购物车、地址、下单、模拟支付、已支付订单、订单列表、退出均通过：logs/local-demo-smoke.log。
- 管理后台登录、会话检查、商品列表、退出通过；10 个 Java 服务健康接口均为 UP。

验收脚本 deploy/verify-local-demo.ps1 每次会创建演示订单并模拟支付，只适用于隔离的本地环境，不是只读检查。没有穷尽全部后台、售后、并发与外部服务分支。

## 与原站的区别

原体验站公开接口当时有 9 个顶级分类、15 个推荐商品。本地使用用户授权的演示数据，不是原站运营数据库或图片备份。源码一致不代表运营内容一致。

按用户选择，先完成本地商城及模拟支付。以下需要自己的凭据，当前不具备真实外部功能验证条件：

- AI 对话、向量检索：LLM_API_KEY、EMBEDDING_API_KEY。
- 邮箱注册和找回密码发信：ALIYUN_ACCESS_KEY_ID、ALIYUN_ACCESS_KEY_SECRET、ALIYUN_DM_ACCOUNT_NAME；当前用预置体验账号登录。
- 真实支付宝：商户配置和证书；当前只有本地模拟支付。
- 地图、第三方内容审核等需相应凭据。

本地使用 SEATA_ENABLED=false，不宣称生产分布式事务、真实物流、退款到账与线上完全一致。

## 维护

单独启动已停止的后端：`powershell -ExecutionPolicy Bypass -File .\deploy\run-configured.ps1 -Stage Java -Service search`，其他服务名见脚本参数。

重新准备演示搜索数据：`powershell -ExecutionPolicy Bypass -File .\deploy\seed-local-demo.ps1 -SyncSearch`。已存在商品采用 INSERT IGNORE 保留原记录。商品服务启动后直接导入新商品，需要重启商品服务预热布隆过滤器。

管理前端最终构建通过：logs/admin-final-build.log。启动脚本支持重复执行，已运行的服务不会因全量冷启动内存检查而被误拦。

发货二次确认修复：Delivery.vue 提交前通过管理员密码取得一次性操作票据；sensitiveConfirm.js 修正确认接口地址并归一化目标路径。管理端构建通过；确认接口、发货路径票据接受与重复使用拒绝均通过验证，仅使用不存在的测试订单，没有实际修改现有订单的发货状态。

商家回复与敏感操作统一修复：请求层对当前22个后端敏感接口在缺票据时先进行密码确认，取消或换票失败不提交业务请求；已有票据不重复弹窗。补齐既有 ConfirmSensitive 调用目标路径，商家回复补充 reload 事件声明和防重复提交。4项前端回归测试通过，包括后端注解覆盖、开发/生产路径、已有票据与取消流程。没有代替用户发表回复或修改真实订单。
