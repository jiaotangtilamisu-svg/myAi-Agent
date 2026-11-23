# 第27阶段：DeepSeek响应超时专项诊断报告

日期：2026-11-03。本轮只检查本机源码和Mock，不调用真实DeepSeek/Embedding。

## 已知现场与不能推定的部分

此前唯一消息31在17:39:26.123收到HTTP200响应头、头部耗时250ms，但到17:39:45.756仍未返回完整模型响应，完整辅助过程20.797秒，TimeoutError、attempts=1、usage未知。不能把HTTP200当成生成成功，不能把未知费用填0。本轮没有重新读取真实响应或查询余额。

原日志只到响应头/最终超时，没有TCP包、完整body或每个字节的时间线；无法确认是DeepSeek生成等待、网络代理缓冲、保活空白数据、还是传输链路停顿。之前摘要503与本次非流式200后等待是不同事件，不能混作同一根因。未发现证据证明本次Key、模型或URL错误，亦未证明供应商已经恢复。

## 安装SDK实际读取流程

安装版本沿用langchain-openai1.7.3、openai3.42.0、httpx0.28.1，不升级依赖。主要源码位置（相对Agent的.venv/Lib/site-packages）：

1. openai/_base_client.py::_request与_client.send，约1722/1807行：非流式调用进入HTTPX。
2. httpx/_client.py::_send_handling_redirects，约1696行：response事件钩子在返回headers后执行，此时正文可能未读完。
3. httpx/_client.py::AsyncClient.send，约1636～1637行：非流式随后await response.aread()，需要把完整正文读完才返回。故响应头250ms之后仍可阻塞。
4. 同函数约1641行：读取失败/取消捕获BaseException并await response.aclose()；外层async with AsyncClient也关闭客户端。SDK在获得完整响应后才继续解析JSON/choices和usage。

原失败位于headers之后、policy_advice获得完整AIMessage之前；结合上述调用链，属于body读取/等待及SDK解析返回之前阶段，但原日志不足以定位具体网络包或服务商内部状态。新增phase=HEADERS/BODY/VALIDATE，只标记应用观察边界，不将其称为网络抓包。

## 超时、重试和代理处理

仅政策专用工厂显式设置httpx.Timeout：connect=5、read=20、write=5、pool=5秒；外层asyncio.timeout仍为20秒，覆盖客户端准备、读取和关闭，不再把客户端准备单独放在deadline之外。20秒是应用等待配置，不保证操作系统调度精确到毫秒，实际耗时须后续授权运行记录。

仍使用非流式、max_retries=0、max_tokens=512、thinking=disabled，保留既有DeepSeek端点和密钥读取。普通聊天仍流式，没有全局提高超时或开放备用服务商；SDK其他用途工厂的原重试策略未改，不能泛称全项目都是零重试。

现场有SDK关于系统代理检测/自定义transport的提示，但调用使用显式传入的AsyncClient。该提示不能证明具体请求经过哪个代理；HTTPX的trust_env/NO_PROXY等仍按既有配置，未改系统代理、证书或TLS验证，没有输出代理中的用户信息。没有进行额外的网络连通性探测或付费API测试。

日志仅记随机call_id、attempt、HTTP状态、阶段、耗时、异常类型和供应商usage；不写Key、Authorization、请求正文、订单或密码。无完整响应时usage未知，不推算计费Token。

## Mock覆盖与结论

- 真实SDK+MockTransport：正常200完整body及有效证据JSON成功；200但伪造Chunk失败。
- 200头部已到但body延迟：外层deadline取消，MODEL_TIMEOUT，仅1次模拟请求；响应流关闭。
- 503：MODEL_UPSTREAM_UNAVAILABLE，不自动重试，保留法规证据。
- 200正文中途ReadError：UNAVAILABLE/连接失败分类，保持单次尝试，响应流关闭。
- 200非法HTTP JSON及模型内容JSON：UNAVAILABLE/非法响应分类，不能写成成功。
- 401/400及连接失败继续由既有专项覆盖；普通聊天工厂的streaming配置不变。

Mock证明客户端会限时、关闭资源并走降级，不证明服务商实际20秒内生成成功。当前没有真实运行授权，也没有再次测试；服务商/链路更深层根因仍待授权后的有界观测。下一轮若要真实验收，应先审核加载必要服务并明确一次调用范围，本轮暂停。

## 本轮测试范围与实际结果

| 测试 | 通过 | 失败/错误 | 跳过 | 性质与范围 |
| --- | ---: | ---: | ---: | --- |
| Python Agent + tools/data_governance全部现有测试 | 571 | 0 | 0 | 独立测试环境、Mock/网络阻断；1条既有MCP弃用警告 |
| Java AgentMessageServiceImplTest | 9 | 0 | 0 | 仅Admin消息映射专项，包含2个新增大JSON/对象序列化用例 |
| 商城Node测试 | 27 | 0 | 0 | 包含5个新增政策展示、消息ID、保存失败及链接安全测试 |
| 实际Vue组件SSR | 2 | 0 | 0 | AgentChatItem使用标注TEST ONLY的测试夹具；内存路由替代浏览器路由，非真实业务联调 |
| 真实MySQL临时表 | 4 | 0 | 0 | 本地SQL/约240KB JSON往返、用户隔离、失败状态保护；不是模型验收 |

前端`npm run build`通过，包含vue-tsc类型检查及Vite生产构建，没有升级依赖。SSR包含图标组件的既有渲染警告，关键政策和错误内容断言通过；不是浏览器交互或真实模型测试。首轮缺少score的测试夹具、MySQL同名临时表冲突和SSR浏览器路由依赖错误均保留初次日志；修正测试夹具/隔离方式后通过，没有用业务数据掩盖失败。

Python571为本轮Agent与数据治理测试，Java9为本轮Admin专项。**此前Java349是Common229+Search120专项，第26阶段1034是选定8模块回归，均不能当作本次Java测试结果或全仓集成测试。** Java依赖模块在`-am`过程中仅编译，未匹配该测试类的模块没有计入通过；`-Dsurefire.failIfNoSpecifiedTests=false`不等于这些模块测试通过。

证据：`.cache/stage27-persistence/results/python-complete.xml/log`、`java-admin.log`及Admin JUnit XML、`frontend-tests-release.log`、`frontend-build-release.log`、`frontend-ssr.json/log/html`、`local-mysql-tests.json`。各层测试独立列出，不合计为真实API通过数量。

## 执行边界、加载状态及遗留项

- 本轮真实DeepSeek/Embedding调用均为0；HTTP200、延迟正文、503、连接断开和非法JSON均由MockTransport/假模型模拟。测试数据库连接仅访问本地MySQL，没有向模型发送真实法规或订单。
- 没有修改已发布法规、没有重新向量化61个Chunk、没有清空索引。最终只读确认仍61个向量。
- 没有修改商品、SKU、库存、订单，没有支付/退款/下单/邮件，没有.env变更或凭据输出。
- 没有重启任何服务，未提交Git；所有历史用户修改保留，关键源码和数据库备份均位于E盘`.cache/stage27-persistence/`且被Git忽略。
- **数据库迁移已经应用；Python/Java源码修复尚未重载到运行中的Agent/Admin。**前端Vite可加载改动，生产构建和组件SSR通过，但没有发送真实聊天消息验证页面。后续运行验收须单独安排必要服务加载，并另获真实模型授权；本轮停止。
- 历史消息31等原先biz_data=null没有被回填或改写。此次只扩容并修复未来写入；不能宣称恢复了此前未落库的完整结构。
- 数据库完全不可用时，连失败标记也可能无法持久化；会推送明确DB_PERSISTENCE_FAILED并记录日志，绝不伪称保存成功，恢复后仍需核实历史状态。没有增加外部文件保存敏感业务证据的旁路。

