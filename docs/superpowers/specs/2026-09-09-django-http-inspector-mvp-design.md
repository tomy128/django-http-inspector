# django-http-inspector MVP 设计

日期：2026-09-09

## 1. 用户目标

Django 开发者安装 django-http-inspector 并对项目入口做一次轻量包装后，继续运行：

```bash
python manage.py runserver
```

随后访问 `http://127.0.0.1:8000/__inspect/`，即可查看应用收到的 HTTP 请求、对应响应，并将请求重新发送到捕获时确定的完整有效 URL。产品面向本地开发和 webhook/API 调试，不负责公网穿透，也不充当业务反向代理。

## 2. 核心取舍

### 2.1 application wrapper，而非 Django middleware

Inspector UI 若作为普通 Django 路由，会经过项目自身的认证、租户、CSRF、重定向和限流 middleware，可能在抵达 Inspector view 前被拦截。django-http-inspector 因此包装 Django 的 WSGI/ASGI application，并在项目 middleware 链之前分流：

```text
Server
  ↓
django-http-inspector wrapper
  ├── /__inspect/* → Inspector 内置应用
  └── 其他路径      → Django application → 项目 middleware → view
```

这不是 reverse proxy：正常业务请求仍在同一进程中直接交给原 Django application。

### 2.2 真实 HTTP replay，而非进程内 handler 调用

Replay 必须重新向捕获时保存的完整有效 URL 发起真实 HTTP 请求。它可以再次经过 DNS、TLS、隧道、网关、服务器和完整 Django 请求链，语义与 ngrok replay 对齐。这里的 URL 是 wrapper 从 WSGI/ASGI 可观察信息重建的 replay target；MVP 不承诺恢复服务器收到之前的原始网络字节。

固定发送到 loopback 或直接调用 WSGI/ASGI callable 虽然更简单，但不能忠实复现网络和服务器层行为，因此不作为产品默认方案。

### 2.3 开发体验优先

MVP 使用项目现有 Django ORM 和数据库，不引入 Redis、Celery、独立前端工程或额外服务。默认仅在 `DEBUG=True` 时启用。

## 3. MVP 范围

### MVP 1.0 发布核心

- WSGI wrapper 和 Django 原生 `runserver` 支持。
- 捕获除 Inspector 自身和默认排除路径外的全部 HTTP 请求。
- 请求/响应列表、详情和清空。
- request/response headers、body、状态、耗时和大小展示。
- JSON、form 和 raw body 查看。
- 语义等价 Replay。
- Replay 到保存的捕获时完整有效 URL。
- 原请求与 replay 记录关联。
- body 截断、网络错误和捕获异常的明确状态。
- Inspector 自己的本机访问限制和请求伪造防护。

### MVP 1.1 紧随增量

- Edit & Replay。
- method/status/path 过滤与搜索。
- Copy as cURL。
- binary body 下载。

### 不包含

- 公网隧道和 reverse proxy。
- WebSocket、SSE 和 HTTP/2 专项捕获。
- 多用户、团队空间和云端同步。
- Redis、Celery 或后台保留任务。
- 可插拔存储系统。
- 完整生产环境部署支持。
- 第一阶段 ASGI wrapper；其接口边界在 MVP 中保留，但实现后置。

## 4. 接入接口

### 4.1 settings

```python
INSTALLED_APPS += ["django_http_inspector"]

DJANGO_HTTP_INSPECTOR = {
    "ENABLED": DEBUG,
    "PATH": "/__inspect/",
    "CAPTURE_MAX_BYTES": 1024 * 1024,
    "MAX_RECORDS": 1000,
    "EXCLUDE_PATHS": ["/static/", "/favicon.ico"],
    "TRUSTED_PROXY_CIDRS": [],
    "INSPECTOR_ALLOWED_HOSTS": ["localhost", "127.0.0.1", "[::1]"],
    "REPLAY_TIMEOUT": 10,
}
```

配置保持单层、数量有限。未配置时使用安全的开发期默认值。

### 4.2 WSGI

```python
from django.core.wsgi import get_wsgi_application
from django_http_inspector import InspectorWSGI

application = InspectorWSGI(get_wsgi_application())
```

用户执行迁移后继续使用 `python manage.py runserver`。

### 4.3 后续 ASGI

```python
from django.core.asgi import get_asgi_application
from django_http_inspector import InspectorASGI

application = InspectorASGI(get_asgi_application())
```

WSGI 与 ASGI wrapper 共用配置、存储、页面和 replay 服务，不复制产品逻辑。

## 5. 组件边界

```text
django_http_inspector/
├── wrapper/       WSGI；后续增加 ASGI
├── capture/       请求、响应和异常的有界采集
├── replay/        URL 重建、header 规范化和 HTTP 发送
├── inspector/     /__inspect/* 的独立轻量 Web 应用
├── models/        Exchange 持久化与保留策略
├── templates/     服务端渲染页面
└── static/        少量原生 CSS/JavaScript
```

Inspector 内置应用可复用已初始化的 Django ORM、模板等基础能力，但不使用项目 URLConf 和 middleware。MVP 不引入另一套 Web 框架。

## 6. 捕获数据流

### 6.1 请求

wrapper 在调用 Django application 前捕获：

- method；
- 从 WSGI environ 重建的捕获时完整有效 URL；
- raw path 与 query string；
- headers；
- body 与实际大小；
- content type；
- client address；
- 开始时间。

wrapper 不预先消费整个 `wsgi.input`。它以 tee input 包装原输入流，在下游通过 `read()`、`readline()` 或迭代实际读取时同步复制前 N bytes，因此大请求不会因捕获而被完整读入内存，下游也维持原有读取时序。wrapper 记录声明的 `Content-Length`、实际观察字节数与 `captured_size`；下游未读完整 body、客户端断连或读取异常时标记 `request_body_incomplete=True`。

如果实现需要可回退缓冲，只能使用有明确内存阈值和关闭生命周期的 `SpooledTemporaryFile`。捕获失败只记录诊断日志，不得阻断业务请求。只有完整观察且未截断的请求体才允许语义等价 Replay。

### 6.2 捕获时完整有效 URL

URL 由 scheme、authority、path 和未经 parse/re-encode 的 query string 组成。WSGI 通常无法保证获得网络层原始 path bytes；若 server 提供 `RAW_URI`、`REQUEST_URI` 等非标准字段，django-http-inspector 保存其值并标明 server-specific provenance，否则使用 `SCRIPT_NAME`、`PATH_INFO` 等字段重建并标记为 reconstructed。

只有当 `REMOTE_ADDR` 命中 `TRUSTED_PROXY_CIDRS` 时，`Forwarded` 或 `X-Forwarded-*` 才参与重建。优先使用标准 `Forwarded`，其次使用 `X-Forwarded-Proto` 与 `X-Forwarded-Host`；多跳值选择与离应用最近且落在可信代理链中的一项。解析必须覆盖 IPv4、IPv6、显式端口、缺失 Host 和非法端口；无法无歧义重建时禁用 Replay 并展示原因。

捕获记录同时保存：

- replay URL；
- URL 各组成部分；
- URL 来源，例如 direct 或 trusted proxy；
- 原始相关 headers，便于用户判断。

无法可靠构造绝对 URL 时，记录仍可查看，但 Replay 按钮禁用并解释原因。

### 6.3 响应

wrapper 拦截 status 和 headers，并包装 WSGI iterable，在正常向客户端输出的同时复制不超过上限的响应 body。必须保留下游 iterable 的惰性、迭代顺序和 `close()` 行为。

对于流式响应，只保存前 N bytes 并标记 truncated，不为捕获而预先消费整个响应。

实现必须覆盖完整 WSGI 响应协议：正确透传 `start_response(status, headers, exc_info)` 的替换语义；透传并捕获 `start_response` 返回的遗留 `write()` callable；处理 iterable 在首次、途中及 `close()` 抛错；保证 `close()` 恰好调用一次。客户端提前断开或 iterable 未耗尽时标记 response incomplete。`wsgi.file_wrapper` 可以在捕获开启时明确降级，但不能破坏响应。HEAD、204 和 304 只记录协议上观察到的 body 行为，不自行制造 body。

### 6.4 异常

下游抛出异常时：

- 保存已获得的请求信息和精简异常摘要；
- 不吞掉或替换原异常；
- 不默认持久化完整 traceback；
- 让原 server/Django 错误机制继续处理。

## 7. 存储模型

核心实体为 `Exchange`：

- `id`, `created_at`, `completed_at`, `duration_ms`；
- `method`, `url`, `scheme`, `host`, `path`, `query_string`；
- `request_headers`, `request_body`, `request_content_type`；
- `request_declared_size`, `request_observed_size`, `request_captured_size`；
- `request_body_truncated`, `request_body_incomplete`；
- `client_addr`；
- `response_status`, `response_headers`, `response_body`；
- `response_size`, `response_body_truncated`, `response_body_incomplete`；
- `state`: pending / complete / application_error / replay_error；
- `error_summary`；
- `observed_replay_attempt`，可空关联到产生它的 outbound attempt。

请求 headers 保存 WSGI environ 可观察到的规范化形式，不承诺保留网络层大小写、顺序或重复字段，因为 WSGI server 可能已合并它们。响应 headers 使用 `start_response` 提供的列表结构，保留顺序和重复值。Body 按观察到的 bytes 保存，展示时再根据 content type 与 encoding 解码。

默认最多保留 1,000 条记录。新增数据后低频触发删除最旧记录，不增加后台任务。清理错误不影响请求处理。

Outbound replay 使用独立的 `ReplayAttempt`，不能用 inbound `Exchange` 代替：

- `id`, `source_exchange`, `mode`, `submitted_at`, `completed_at`, `state`；
- 实际发送的 method、URL、headers 和 body 快照；
- outbound response status、headers、body、大小与截断状态；
- `error_stage`: validation / dns / connect / tls / timeout / write / read；
- `error_summary`；
- 不可预测的 `correlation_nonce`；
- `observed_exchange`，可空。

保留策略不能因删除源 Exchange 而破坏历史 attempt；`ReplayAttempt` 保存完整发送快照，源记录删除时使用 `SET_NULL`。关联到 attempt 的新 Exchange 同样允许独立保留。

## 8. Replay 数据流

```text
Inspector UI
  ↓ POST /__inspect/api/replay
加载并校验保存记录
  ↓
重建 method + original URL + headers + body
  ↓
真正的 HTTP client 请求捕获时 URL
  ↓
原 endpoint / tunnel / gateway / server
  ↓
django-http-inspector wrapper 再次捕获
```

### 8.1 请求规范化

Replay 尽可能保持原请求不变，但必须移除或重算：

- `Content-Length`；
- `Connection`；
- `Keep-Alive`；
- `Transfer-Encoding`；
- 其他 hop-by-hop headers。

Replay 使用目标 URL 生成 `Host`；Edit & Replay 改变 origin 后绝不沿用旧 Host。它覆盖任何同名的用户输入关联 header，并添加携带随机 nonce 的 `X-Django-HTTP-Inspector-Replay`。nonce 使用恒定时间比较。只有 nonce 对应当前实例中尚未完成的 `ReplayAttempt` 时，wrapper 才尝试建立 `observed_exchange` 关联；该关联必须通过数据库条件更新或事务锁进行单次原子 claim。首个匹配 inbound 消费 nonce，后续携带相同 nonce 的请求不得关联，并记录 duplicate-correlation 诊断。该 header 不参与授权。

HTTP client 默认不读取环境代理配置，执行标准 TLS 证书验证，并按原始编码读取响应。301、302、303、307、308 均不自动跟随。响应自动解压若会改变保存字节，必须禁用或同时明确保存 wire encoding 与 decoded view；MVP 默认保存 HTTP client 观察到的原始响应 body。

默认不自动跟随 redirect，以免目标地址静默变化。网络连接、TLS、DNS、超时和响应读取错误都必须形成可查看的 replay attempt 结果，即使没有新的 inbound Exchange。

### 8.2 语义等价 Replay

- 使用保存的捕获时完整有效 URL、method、可重放 headers 和完整 body。
- 若 request body 已截断、未被下游完整读取或读取失败，则禁用 Replay。
- UI 明确列出不可避免的规范化：hop-by-hop headers 被移除、`Content-Length` 重算、Host 由 URL 生成、关联 header 被增加。因此它不是字节级 exact replay。
- 执行前在 UI 明确展示目标 URL 和副作用警告。

### 8.3 Edit & Replay（MVP 1.1）

允许编辑 URL、method、headers 和 body。修改后的值作为 replay attempt 快照保存，不修改原 Exchange。为确保首个可发布版本聚焦，该能力排在捕获、详情、语义等价 Replay 和失败展示之后。

修改 host、scheme 或 port 时给予显著警告。MVP 不通过偷偷替换为 loopback 来规避风险，因为这会破坏真实 replay 语义。

## 9. Inspector UI/UX

### 9.1 参考边界

参考 ngrok `:4040` 的高效信息架构：左侧请求流、右侧详情、清晰的 request/response 切换，以及详情上下文中的 replay。不得复制 ngrok 品牌标识、专有资产或逐像素视觉样式。

django-http-inspector 的视觉气质为专业、克制、高密度。使用 restrained 色彩策略：中性背景和表面承载大量数据，单一品牌色只用于主操作、选中项和焦点；HTTP method 与状态码使用克制的语义色。

### 9.2 桌面布局

```text
┌────────────────────────────────────────────────────────────┐
│ django-http-inspector   Search / Filters              Clear       │
├──────────────────────┬─────────────────────────────────────┤
│ request stream       │ POST /webhooks/stripe       Replay │
│ time method path     │ URL · status · duration · size      │
│ status duration      ├─────────────────────────────────────┤
│                      │ Request | Response                   │
│ selected row         │ Headers | Query | Body | Raw         │
│                      │                                     │
└──────────────────────┴─────────────────────────────────────┘
```

列表是可扫描的 master pane，不使用卡片瀑布。详情是工作区，操作与当前请求绑定。列宽可调整属于后续增强，不进入 MVP。

### 9.3 页面和交互

- `/__inspect/`：请求列表与当前详情的 split view。
- `/__inspect/requests/<id>/`：可直接链接的详情状态；桌面仍在 split view 中选中对应行。
- `/__inspect/requests/<id>/replay/`：内联编辑工作区，而非默认弹窗。
- Request/Response 是一级 tabs；Headers、Query、Body、Raw 是二级内容切换。
- 新记录通过轻量轮询出现，不自动抢走当前选择；若实现排期影响 1.0，可先使用手动刷新。
- 用户位于列表顶部且未选中历史项时，可提供“跟随最新请求”；否则显示“有 N 条新请求”。
- JSON 格式化失败时回退到 Raw，不将合法但未知内容误报为错误。
- Copy 操作提供短暂、非阻塞反馈。

### 9.4 状态设计

必须覆盖：

- 首次使用空状态，说明如何产生第一条请求；
- pending 请求；
- complete；
- 4xx/5xx；
- application error；
- replay DNS/TLS/connect/timeout error；
- request/response body truncated；
- body 不可预览但可下载；
- 捕获记录已被保留策略删除；
- replay 已提交但尚未观察到对应 inbound 请求。

状态不能只依赖颜色，必须同时有文字或图标语义。

### 9.5 响应式

桌面优先。在窄屏下 split view 变为列表页与详情页的两级导航，不把两栏强行压缩。数据区允许必要的横向滚动，主操作保持可见。

### 9.6 可访问性

MVP 保证语义 HTML、键盘可达、可见焦点、基本对比度和 reduced-motion 降级，但完整 WCAG 2.1 AA 审计不作为本阶段发布门槛。

## 10. 安全边界

Inspector 绕过项目 middleware，因此必须有自己的防护：

- 默认仅在 `DEBUG=True` 启用；
- 默认仅允许 loopback 客户端访问 `/__inspect/*`；
- 在路由前校验 Inspector `Host`，默认仅允许 `localhost`、`127.0.0.1`、`[::1]` 及实际开发端口，未知 Host 直接拒绝，不能依赖 Django `ALLOWED_HOSTS`；
- 修改状态的 endpoint 同时校验不可预测 token、`Origin` 和 `Sec-Fetch-Site`。token 在 wrapper 启动时使用安全随机数生成，保存在进程内，随开发服务器重启轮换，并仅注入该进程返回的 Inspector HTML；它是进程级 token，不宣称是独立浏览器 session。浏览器请求提供 `Origin` 时必须与 Inspector origin 完全一致；`Sec-Fetch-Site` 存在时只接受 `same-origin`/`none`。兼容不发送这些 headers 的客户端时仍强制 token 与 Host 校验；
- 非 loopback 模式必须显式配置允许的 client CIDR 与 Inspector Host，并启用认证；仅显示警告不构成访问控制；
- 不把 replay correlation header 当成可信身份；
- HTML 展示 headers/body 时严格转义；
- 对完整 URL、认证 headers、Cookie 和 body 给出敏感信息提示；
- 不把 body 写入普通应用日志。

Replay target 可能指向公网、私网、loopback 或云元数据地址。这是产品真实 replay 能力的一部分，不能静默改写。URL parser 只接受 `http` 和 `https`，拒绝 userinfo、控制字符、非法 authority 和非法端口，并正确解析 IPv4/IPv6。执行前解析全部候选地址；私网、loopback、link-local、保留地址或已知云元数据地址必须加强确认。HTTP client 必须固定使用用户确认过的解析结果，或在发送任何 HTTP/TLS 应用数据前取得并校验实际 peer；若实际地址类别与确认时不同，则中止并要求重新确认，不能仅事后记录。redirect 默认禁用，因而不会引入未确认的新目标。后续可增加 allowlist，但 MVP 不设计复杂策略引擎。

## 11. 性能与失败策略

- 捕获上限默认 1 MiB，可配置。
- 捕获存储失败不影响业务响应。
- 数据库写入采用最简单可靠的同步路径；性能优化需由实际测量驱动。
- Replay 设置连接和总超时。
- 若 replay 目标最终回到线程/worker 已耗尽的同步服务，可能死锁；MVP 只保证默认多线程 `runserver` 的自回放。总超时必须终止 attempt，UI 区分 outbound timeout 与请求已发送但未观察到 inbound Exchange。
- UI 轮询频率保持温和，并在页面不可见时降频或暂停。

## 12. 测试与验收

### 12.1 单元测试

- WSGI environ 读取与 body 恢复。
- tee input 的 `read`、`readline`、迭代、未读完、断连和读取异常。
- URL 重建和可信代理规则。
- 重复 headers、hop-by-hop headers 与 Content-Length 处理。
- `start_response` 的 `exc_info`/`write()`、response iterable 透传、截断、途中异常和 close-once。
- replay 关联与失败状态。
- 保留策略。
- Inspector 路由隔离和路径边界，避免 `/__inspector` 被误匹配。

### 12.2 集成测试

- 自定义认证/租户 middleware 会阻止普通请求，但无法拦截 Inspector UI。
- 默认多线程 `runserver` 下发起请求、捕获、语义等价 Replay，并观察第二条 inbound record。
- 通过临时 HTTP endpoint 验证 replay 命中保存 URL 的 scheme、hostname、port、path 和原始编码 query，而非 loopback 替代地址。
- JSON、form、binary、empty body、streaming response 和异常响应。
- 截断请求不能 replay。
- DNS、TLS、连接拒绝和 timeout 形成可读错误。
- 单线程目标不会无限挂起，而会超时并持久化 ReplayAttempt。
- DNS 在确认与连接阶段从公网地址变化为私网/loopback/link-local/reserved/metadata 地址时，在发送请求数据前中止。
- 并发携带相同 correlation nonce 的请求中只有一个能原子关联 attempt，其余记录重复关联诊断。
- 未知 Host、非 loopback client、错误 token 和跨站 Origin 均被 Inspector 拒绝。
- 编码路径、双斜线和 Inspector 配置路径有/无尾斜线时均不递归捕获自身。

### 12.3 MVP 验收

- 三步接入：安装 app、包装 WSGI application、迁移数据库。
- 原 `python manage.py runserver` 工作流不变。
- `/__inspect/` 不受项目 middleware 影响。
- 默认捕获全部业务 HTTP 请求，排除 Inspector 和默认噪声路径。
- 可以检查 request/response。
- Replay 使用真实 HTTP 请求访问保存的捕获时完整有效 URL。
- Replay 结果与原请求关联。
- 捕获失败不改变业务响应。
- UI 达到专业、克制、高密度的开发工具体验，并采用 ngrok 式 master-detail 信息架构。

以下断言必须由自动化测试直接证明：

- 捕获开启与关闭时，相同请求的业务 status、headers 和 body 一致。
- 面对 100 MiB request body，捕获内存不随 body 线性增长，且只保留配置上限。
- 下游分块读取时获得与未包装 application 相同的字节序列。
- 流式响应首字节不等待完整响应；中途失败仍恰好调用一次 `close()` 并标记 incomplete/error。
- 重复响应 headers（包括多个 `Set-Cookie`）的顺序和值保持不变。
- 截断、未完整观察或读取失败的请求不能 Replay。
- DNS、TLS、connect、timeout 和 read failure 分别生成持久化 `ReplayAttempt`。
- 数据库不可用时业务请求仍成功，且 Inspector 错误不会被递归捕获。

## 13. 风险

- WSGI 能提供的信息不是完全原始的网络字节，server 可能已经规范化 header/path。
- 经代理时若不显式信任转发 headers，保存 URL 可能不是外部 URL；若盲目信任又会产生伪造风险。
- 保存请求体会处理密钥、Cookie 和个人数据。
- Replay 会真实触发支付、发信、写库等副作用。
- 原始 host 可被攻击者控制，点击 Replay 可能访问敏感网络位置。
- 大 body、streaming response 和高请求量可能造成内存或数据库压力。
- 在单线程/单 worker 服务上 replay 回当前服务可能阻塞。
- Inspector 的独立 Web 层如果扩张过快，可能演变成另一套不易维护的框架。

## 14. 后续演进

按真实反馈依次考虑：

1. ASGI wrapper，与 WSGI 共享核心模块。
2. 更精确的 request diff、replay diff 和链路视图。
3. 可配置敏感字段脱敏和 capture allow/deny rules。
4. `inspectserver` 便捷命令，但不覆盖 `runserver`。
5. 导出 cURL、Python、pytest fixture。
6. 数据保留期限和手动 pin 记录。
7. 在确有需求时增加 WebSocket/SSE 专项能力。

不优先建设多租户云平台、隧道协议、通用 API 网关或插件系统。
