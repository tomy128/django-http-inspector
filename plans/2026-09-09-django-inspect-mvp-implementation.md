# django-inspect MVP 1.0 实施计划

日期：2026-09-09  
依据：[MVP 设计](../docs/superpowers/specs/2026-09-09-django-inspect-mvp-design.md)

## 目标

交付一个可安装的 Django 开发依赖。用户加入 `INSTALLED_APPS`、迁移数据库并用 `InspectorWSGI` 包装现有 application 后，仍执行 `python manage.py runserver`，即可在 `/__inspect/` 查看全部业务 HTTP exchange，并将完整、未截断的请求通过真实 HTTP 连接 replay 到捕获时的完整有效 URL。

## 核心 tradeoff

- 优先支持 Django 自带 WSGI `runserver`，ASGI 后置。
- 正常业务请求直接调用下游 WSGI application，不做代理。
- Replay 是真实 outbound HTTP 请求，因此接受 DNS/TLS/并发等复杂性。
- 请求捕获忠实于 WSGI 可观察信息，不承诺网络字节级原始数据。
- 1.0 只交付捕获、列表/详情、语义等价 Replay、失败展示、清空和安全边界；Edit & Replay、搜索与 Copy as cURL 属于 1.1。

## 技术基线

- 使用 `src/` package layout。
- runtime 只依赖 Django；HTTP replay transport 优先使用 Python 标准库，以避免为单一能力引入大依赖。
- 测试使用 Django 自带 test runner 与 `unittest`；若后续 pytest 能显著改善矩阵测试，再单独决策。
- HTML 由 Django template engine 服务端渲染；交互使用少量原生 JavaScript。
- CSS 与 JS 作为包内静态资源，由 Inspector 内置路由直接返回，不经过项目 staticfiles middleware。

## 预期结构

```text
pyproject.toml
README.md
src/django_inspect/
├── __init__.py
├── apps.py
├── config.py
├── models.py
├── migrations/0001_initial.py
├── wrapper/
│   ├── input.py
│   ├── response.py
│   └── wsgi.py
├── capture/
│   ├── exchange.py
│   ├── headers.py
│   └── url.py
├── replay/
│   ├── service.py
│   ├── transport.py
│   ├── target.py
│   └── correlation.py
├── inspector/
│   ├── app.py
│   ├── routing.py
│   ├── security.py
│   ├── views.py
│   └── presentation.py
├── templates/django_inspect/
│   ├── base.html
│   ├── index.html
│   └── exchange_detail.html
└── static/django_inspect/
    ├── inspect.css
    └── inspect.js
tests/
├── settings.py
├── urls.py
├── wsgi.py
├── test_config.py
├── test_input_capture.py
├── test_url_capture.py
├── test_response_capture.py
├── test_wrapper.py
├── test_models.py
├── test_inspector_security.py
├── test_inspector_ui.py
├── test_replay_target.py
├── test_replay_transport.py
└── test_end_to_end.py
```

每个模块只在确实出现对应职责时创建；实施中若一个小模块只有几行且没有独立测试价值，应合并到最近的边界，避免为目录图而抽象。

## 实施步骤

### 1. 建立可安装包和测试基座

文件：

- `pyproject.toml`
- `src/django_inspect/__init__.py`
- `src/django_inspect/apps.py`
- `tests/settings.py`
- `tests/urls.py`
- `tests/wsgi.py`
- `README.md`

工作：

1. 定义 package metadata、支持的 Python/Django 范围和 package data。
2. 创建最小 Django test project，使用临时 SQLite 数据库。
3. 暴露尚未实现的 `InspectorWSGI` 公共入口。
4. README 只写产品定位、非目标和预期三步接入，避免提前承诺未完成能力。

验证：

```bash
python -m unittest discover -s tests
python -m build
```

提交边界：`chore: scaffold installable django-inspect package`

### 2. 配置加载与路径判定

文件：

- `src/django_inspect/config.py`
- `tests/test_config.py`

工作：

1. 建立不可变配置对象与文档中的安全默认值。
2. 规范化 Inspector path 的有/无尾斜线形式。
3. 精确判断 Inspector、static、favicon 与用户排除路径，避免 `/__inspector` 等误匹配。
4. `DEBUG=False` 且未显式覆盖时关闭 wrapper。
5. 对非法大小、超时、CIDR 和 Host 配置 fail fast，并给出可执行错误信息。

验证重点：配置缺失、部分覆盖、非法类型、编码路径、双斜线、路径边界。

提交边界：`feat: add validated inspector configuration`

### 3. 数据模型与迁移

文件：

- `src/django_inspect/models.py`
- `src/django_inspect/migrations/0001_initial.py`
- `tests/test_models.py`

工作：

1. 实现 `Exchange` 与 `ReplayAttempt`。
2. JSON 字段保存 WSGI 可观察 request headers 与有序 response headers。
3. BinaryField 保存有界 body；明确 captured/observed/declared size 与 incomplete/truncated。
4. `ReplayAttempt` 保存完整发送快照、错误阶段、response 和 correlation nonce。
5. `source_exchange=SET_NULL`，确保源记录被清理后 attempt 仍自包含。
6. 实现最多记录数清理服务，不在 model `save()` 内隐藏复杂副作用。

验证重点：迁移可执行、状态约束、自关联、删除语义、保留策略不破坏 attempt。

提交边界：`feat: persist captured exchanges and replay attempts`

### 4. WSGI 输入流有界 tee

文件：

- `src/django_inspect/wrapper/input.py`
- `tests/test_input_capture.py`

工作：

1. 包装 `wsgi.input`，透传 `read()`、`readline()`、`readlines()` 和迭代协议。
2. 只复制前 `CAPTURE_MAX_BYTES`，不预读，不随大 body 线性占用内存。
3. 记录 declared、observed、captured sizes。
4. 下游未读完、断连或输入异常时标记 incomplete。
5. 定义 finalize 行为，不关闭不属于 wrapper 的原 input。

验证重点：不同 chunk size、混合 read/readline、空 body、100 MiB 生成流、读取异常、只读一部分。

提交边界：`feat: capture wsgi request bodies without pre-reading`

### 5. URL 与 headers 捕获

文件：

- `src/django_inspect/capture/url.py`
- `src/django_inspect/capture/headers.py`
- `tests/test_url_capture.py`

工作：

1. 从 WSGI environ 构建 replay URL，并保存 reconstructed/server-specific provenance。
2. 保持 query string 原始编码，不 parse/re-encode。
3. 仅对来自 `TRUSTED_PROXY_CIDRS` 的请求解析代理 headers。
4. 实现 `Forwarded` 优先级、多跳选择、IPv4/IPv6、端口与非法 authority 校验。
5. request headers 明确保存 WSGI 规范化视图，不伪造重复值或原始大小写。

验证重点：直连、可信/不可信代理、IPv6、显式端口、RAW_URI/REQUEST_URI、缺失 Host、控制字符。

提交边界：`feat: reconstruct replay targets from wsgi requests`

### 6. WSGI 响应包装与 Exchange 生命周期

文件：

- `src/django_inspect/wrapper/response.py`
- `src/django_inspect/capture/exchange.py`
- `src/django_inspect/wrapper/wsgi.py`
- `tests/test_response_capture.py`
- `tests/test_wrapper.py`

工作：

1. 实现 `InspectorWSGI` 的业务路径透传、pending Exchange 创建和最终状态更新。
2. 包装 `start_response`，保留 status、有序重复 headers、`exc_info` 替换语义和 legacy `write()`。
3. 惰性透传 response iterable，同时有界捕获 body。
4. iterable 首次/途中/close 异常、客户端提前停止与 close-once 正确落状态。
5. 兼容 `wsgi.file_wrapper`，允许有记录的性能降级但不破坏响应。
6. 数据库不可用或捕获内部异常时完全旁路，业务 status/headers/body 不变。

验证重点：普通/流式/HEAD/204/304、多 `Set-Cookie`、write callable、异常、close-once、捕获开关等价性。

提交边界：`feat: capture complete wsgi request response exchanges`

### 7. Inspector 路由与自身安全

文件：

- `src/django_inspect/inspector/app.py`
- `src/django_inspect/inspector/routing.py`
- `src/django_inspect/inspector/security.py`
- `tests/test_inspector_security.py`

工作：

1. 在 wrapper 中将 `/__inspect/*` 分发到独立轻量 WSGI app，不调用业务 application。
2. 路由前校验 loopback client 与 `INSPECTOR_ALLOWED_HOSTS`。
3. wrapper 启动时生成进程级随机 token，随重启轮换。
4. 修改请求校验 token、Host、Origin 和 `Sec-Fetch-Site`；明确 header 缺失时的兼容回退。
5. 非 loopback 模式若未显式配置 CIDR、Host 与认证则拒绝启动。
6. 所有动态内容 HTML escape，静态资源仅从固定 package paths 返回。

验证重点：未知 Host、DNS rebinding Host、非 loopback、错误 token、跨站 Origin、路径穿越、Inspector 不经过项目 middleware。

提交边界：`feat: serve isolated and protected inspector routes`

### 8. 请求流与详情 UI

文件：

- `src/django_inspect/inspector/views.py`
- `src/django_inspect/inspector/presentation.py`
- `src/django_inspect/templates/django_inspect/base.html`
- `src/django_inspect/templates/django_inspect/index.html`
- `src/django_inspect/templates/django_inspect/exchange_detail.html`
- `src/django_inspect/static/django_inspect/inspect.css`
- `src/django_inspect/static/django_inspect/inspect.js`
- `tests/test_inspector_ui.py`

工作：

1. 建立 ngrok 式 master-detail 信息架构：左侧请求流，右侧详情。
2. 请求行显示时间、method、path、status 和 duration；当前项有明确选中状态。
3. Request/Response 一级 tabs；Headers/Query/Body/Raw 二级视图。
4. JSON/form 格式化失败时安全回退 Raw。
5. 覆盖 empty、pending、complete、4xx/5xx、application error、truncated 和 incomplete 状态。
6. 实现清空记录；1.0 先手动刷新，若不影响排期再加入温和轮询。
7. 窄屏切换为列表与详情两级导航；保证键盘焦点和状态文字。

设计约束：专业、克制、高密度；参考 ngrok 信息架构，不复制品牌、配色或资产。精确 tokens 在实现 UI 前写入 `DESIGN.md`。

验证重点：HTML 快照中的层级/转义/状态、键盘可达、窄屏无关键操作丢失、静态资源响应。

提交边界：`feat: add request stream and exchange detail interface`

### 9. Replay target 校验与固定解析

文件：

- `src/django_inspect/replay/target.py`
- `tests/test_replay_target.py`

工作：

1. 只接受 http/https，拒绝 userinfo、控制字符、非法 authority/port。
2. 解析全部 IP 并分类 public/private/loopback/link-local/reserved/metadata。
3. 风险目标要求 UI 二次确认，并把确认的解析结果写入 attempt 快照。
4. 连接固定使用已确认 IP，保留原 hostname 用于 Host 与 TLS SNI。
5. 若实际 peer 分类变化，在发送 HTTP/TLS 应用数据前中止。

验证重点：IPv4/IPv6、混合 DNS 结果、metadata、确认后 DNS rebinding、IDNA 与非法 URL。

提交边界：`feat: validate and pin replay destinations`

### 10. 真实 HTTP Replay transport

文件：

- `src/django_inspect/replay/transport.py`
- `src/django_inspect/replay/service.py`
- `tests/test_replay_transport.py`

工作：

1. 使用标准库 socket/http.client 构建能连接固定 IP、保留 Host 和 TLS SNI 的 transport。
2. 从保存请求移除 hop-by-hop headers，重算 Content-Length，并覆盖 Host。
3. 不读取环境代理，不自动跟随任何 redirect，执行标准 TLS 验证。
4. 有界读取 outbound response，不透明自动解压。
5. 将 validation/dns/connect/tls/timeout/write/read 结果完整写入 ReplayAttempt。
6. 设置连接、读取和总超时；目标线程/worker 耗尽时能够结束 attempt。

验证重点：实际 HTTP/TLS 临时服务器、目标 host/port/path/query、Host/SNI、redirect、压缩响应、各失败阶段。

提交边界：`feat: replay captured requests over real http connections`

### 11. Replay 关联与 Inspector 操作

文件：

- `src/django_inspect/replay/correlation.py`
- `src/django_inspect/inspector/views.py`
- `src/django_inspect/templates/django_inspect/exchange_detail.html`
- `tests/test_end_to_end.py`

工作：

1. 创建随机 nonce，覆盖同名原 header，并用恒定时间比较。
2. 通过数据库条件更新或事务锁单次原子 claim inbound Exchange。
3. 重复 nonce 不关联，并写 duplicate-correlation 诊断。
4. 详情页显示完整目标、规范化差异、副作用提示与 Replay 按钮。
5. 截断、incomplete 或无法构建 URL 时禁用 Replay 并解释原因。
6. UI 展示 outbound attempt、实际 peer、response 或失败阶段，以及是否观察到 inbound Exchange。

验证重点：并发相同 nonce 只有一个关联、伪造 nonce、目标返回但无 inbound、默认多线程 runserver 自回放。

提交边界：`feat: connect replay attempts to captured requests`

### 12. 文档、示例和发布验收

文件：

- `README.md`
- `docs/architecture.md`
- `docs/security.md`
- `docs/replay-semantics.md`
- `CHANGELOG.md`

工作：

1. 写清安装、迁移、WSGI 包装和 `/__inspect/` 使用方式。
2. 明确 Django 自带 runserver 是 WSGI、ASGI 属于后续阶段。
3. 记录 WSGI headers/path 可观察性限制和“语义等价”含义。
4. 记录敏感数据、真实副作用、SSRF/DNS rebinding 与非 loopback 风险。
5. 明确只保证默认多线程 runserver 自回放，不支持 `--nothreading`。
6. 运行完整测试、构建 wheel/sdist，并在一个真实示例项目中手动完成 capture → inspect → replay。

验证：

```bash
python -m unittest discover -s tests
python -m build
python -m twine check dist/*
```

提交边界：`docs: document installation security and replay semantics`

## 端到端发布门槛

1. 捕获开启和关闭时业务 response 等价。
2. 100 MiB body 测试证明捕获内存不线性增长。
3. 流式 response 首字节不等待完整 response。
4. Inspector 不经过用户 middleware，未知 Host/来源/伪造请求被拒绝。
5. Replay 命中保存 URL 的 scheme、hostname、port、path 和 query，不替换为 loopback。
6. Replay 经过真实 HTTP server，并产生可关联的新 inbound Exchange。
7. DNS rebinding 在发出应用数据前中止。
8. 所有 outbound 失败均持久化为可读 ReplayAttempt。
9. wheel 与 sdist 可安装，迁移可在空数据库执行。
10. README 中的三步接入从零可复现。

## 风险控制

- 先完成透明捕获，再建设 UI；避免漂亮界面掩盖协议错误。
- Replay transport 与 UI 分离，通过纯数据命令调用，便于精确测试。
- 不为了 ASGI 提前抽象 protocol-neutral adapter；只共享已经稳定的纯业务模块。
- 标准库 HTTP transport 若在 TLS/SNI、固定解析或响应语义上变得难以可靠维护，应在独立决策记录中比较 `httpcore`/`urllib3`，而不是临时堆补丁。
- 每个阶段独立提交，不把脚手架、协议核心、UI 和文档混入同一 commit。

## 开始实施前的阻塞项

当前目录不是 Git 仓库，无法执行项目要求的“一任务一 commit”。开始写代码前需要用户授权初始化 Git 仓库，或提供实际 Git 工作树位置。
