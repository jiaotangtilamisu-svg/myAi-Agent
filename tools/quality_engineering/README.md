# 本地质量门

项目根目录执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\quality_engineering\run-regression.ps1
```

顺序执行完整Python测试、10个内存源码突变、离线Java全模块测试、商城/管理端Node测试及生产构建、14个本机服务健康检查；保存每门退出码、日志、JUnit和summary.json。各门失败继续收集后续门结果，最终返回非零；不自动改业务源码、重启服务或修业务数据。缺少本地既有虚拟环境/JDK/Maven依赖会明确失败，不安装/升级生产依赖。服务未运行时健康门明确失败，不冒称业务代码回归失败。

`run-python.ps1 -Mode focused/all/mutation`分别执行新增质量专项、完整Python或内存突变。测试API Key均为固定无效fixture，启用现有网络拦截；Java启用NoNetworkSecurityManager。真实API、浏览器和运行服务验收独立于本流水线，不因单元测试成功自动获得授权。

- scenarios.json：67个预算语料及5个独立路由场景，预期为静态人工可审阅数据。
- oracles.py：独立读取原始Fixture，验证预算、同SKU价格/库存、来源、政策及路由；不调用Agent判断自身。
- mutation_probe.py：仅内存替换10处Python函数判断，覆盖价格上下界/严格边界、偏好排序、负值、空召回、零库存、过期政策和退款保护。先验证原函数通过，再要求突变体失败；不改生产文件。这不是全项目突变覆盖率。
- features.json：三图26项最低功能+8项额外能力的源码/接口/前端/测试关联。测试关联率不是代码覆盖率或真实E2E通过率。

Fixture均为隔离测试数据，不导入正式商品或订单。随机种子3101/3102固定，可重放。故障注入不停止实际MySQL/Redis/ES/MCP。Java状态机使用新内存H2，测试JVM退出后释放；本机混合集成只使用随机唯一Redis测试命名空间并精确清理。

完整质量门不提供跳过Java的快捷参数，避免旧Java日志被误认为当前全量结果。局部定位可直接执行run-python.ps1。当前真实资金退款保持关闭；不得在此脚本中增加自动发布、金融或正式数据修改步骤。

`check-runtime.ps1`只读检查服务与两端入口，不读取登录凭据。`local_business_reads.py`是另行选择执行的混合集成：当前源码图→真实MCP/Gateway/Product/Stock/MySQL与政策ES读取；模型建议和状态通知明确Mock，未测试登录会话、消息持久化或浏览器完整交互，不替代真实LLM验收。只使用随机唯一Redis测试命名空间并在finally精确清理。
