# django-http-inspector 简化远程访问设计

日期：2026-09-10
状态：已由用户确认，待独立评审
目标版本：0.1.3

## 1. 用户目标

本地或局域网联调 Django 的开发者希望从另一台设备访问 `/__inspect/`，但不应被迫同时理解请求 Host、WSGI `REMOTE_ADDR` 和 CIDR。最短价值路径是一个显式开关：

```python
DJANGO_HTTP_INSPECTOR = {
    "ALLOW_REMOTE": True,
}
```

开启后，任何能够连接 Django 监听端口的客户端都可以访问 Inspector。该模式不提供身份认证，适用于用户明确控制网络边界的开发环境。

## 2. 核心取舍

`ALLOW_REMOTE=True` 用产品可用性换取访问控制强度。Inspector 会展示 headers、cookies、credentials、请求和响应 body，并允许发起真实 HTTP Replay，因此不适合作为公网服务。产品不假装一个 Host/CIDR 白名单组合能够替代认证：默认保持 loopback-only；用户显式开启远程模式后，应用完整接受这一风险。

相比 `ACCESS_MODE` 枚举，布尔开关与当前仅有的本机/远程两种状态匹配，认知成本更低。相比根据 server bind address 自动开放，显式配置不会因为 `runserver 0.0.0.0:8000`、容器端口映射或隧道而意外授权。

## 3. MVP 范围

包含：

- 新增严格布尔配置 `ALLOW_REMOTE`，默认 `False`；
- 开启时跳过 Inspector 请求的 Host 和客户端 CIDR 检查；
- 默认模式继续执行现有 Host + Client CIDR 双重检查；
- 保留 `INSPECTOR_ALLOWED_HOSTS` 与 `INSPECTOR_ALLOWED_CLIENT_CIDRS` 的兼容性；
- 开启时输出一次 warning 日志；
- 更新配置、安全和发布文档；
- 以 0.1.3 发布，因为 0.1.2 已生成并准备发布。

不包含：

- 密码、登录页、Session 或 Cookie 认证；
- 自动识别局域网、公网或 server bind address；
- 新的 allowlist/denylist 策略；
- 改变 Replay target、DNS 固定、redirect 或 correlation 语义。

## 4. 配置与兼容性

`InspectConfig` 增加：

```python
allow_remote: bool
```

配置加载只接受真正的 `bool`。`"true"`、`1`、`None` 等值抛出 `ImproperlyConfigured`，防止字符串 `"false"` 被普通 truthiness 误判为开启。

```text
ALLOW_REMOTE 未设置 / False
    → 校验 INSPECTOR_ALLOWED_HOSTS
    → 校验 INSPECTOR_ALLOWED_CLIENT_CIDRS

ALLOW_REMOTE=True
    → 不使用上述两项决定访问结果
    → 任意 HTTP Host 和 REMOTE_ADDR 可访问 Inspector
```

高级白名单字段不删除、不弃用。即使远程模式暂时忽略它们，配置加载仍验证其类型和 CIDR 格式，使关闭 `ALLOW_REMOTE` 后不会突然激活无效配置。现有的“客户端 CIDR 必须全部是 loopback”限制只在 `ALLOW_REMOTE=False` 时执行；否则合法的非 loopback CIDR 可以存在但不参与授权。

## 5. 请求与变更操作安全

`request_allowed(environ, config)` 的第一条分支是：

```python
if config.allow_remote:
    return True
```

它只控制包拥有的 `/__inspect/*` UI、assets 和 API 是否可访问，不控制业务 Django 路由，也不控制 outbound Replay 的目标 Host。

`mutation_allowed()` 保持不变：Clear、普通 Replay 和 Edit & Replay 仍要求进程随机 token；存在 `Origin` 时必须与当前 scheme + Host 同源；存在 `Sec-Fetch-Site` 时只接受 `same-origin` 或 `none`。这些机制用于降低跨站请求伪造风险，不构成远程用户身份认证。能读取 Inspector 页面的人也能取得 token 并执行变更操作，这是 `ALLOW_REMOTE=True` 的明确语义。

Replay 的 URL 仍只能来自捕获记录；只接受 HTTP(S)、不跟随 redirect、DNS 解析结果固定和 peer 分类检查不变。

## 6. 警告与错误处理

当 wrapper 初始化且 `ALLOW_REMOTE=True` 时，通过 `django_http_inspector` logger 输出一次 warning。单个 wrapper 实例只输出一次，文案明确：

- Inspector 无认证；
- 所有能连接服务的客户端可以读取捕获数据并触发 Replay；
- 不应暴露到公网或不受信任网络。

无效布尔值或无效高级配置继续在初始化阶段以 `ImproperlyConfigured` 失败，不静默降级。访问拒绝仍返回现有 `403 Inspector access denied.`。

## 7. 技术实现路径

- `config.py`：增加严格布尔解析与 `allow_remote` 字段；按模式调整 loopback-only 校验。
- `inspector/security.py`：在 `request_allowed` 中增加显式远程分支。
- `wrapper/wsgi.py`：初始化时输出一次风险 warning；不在每个请求重复记录。
- Tests：覆盖配置、request authorization、mutation 不变性和 wrapper warning。
- README、`docs/security.md`、Changelog、发布文档与版本元数据同步到 0.1.3。

数据捕获、独立 SQLite schema、模板、前端和 ReplayAttempt schema 均无需改变。

## 8. 验收标准

- 未配置时，loopback + 默认 Host 可以访问，任意非 loopback 或未知 Host 仍被拒绝；
- `ALLOW_REMOTE=True` 时，非 loopback客户端和任意 Host 可以加载 UI、assets 和 JSON API；
- 开启远程模式不会绕过 Clear/Replay/Edit & Replay 的 token、Origin 与 Fetch Metadata 校验；
- `ALLOW_REMOTE=False` 时现有高级白名单继续工作；
- `ALLOW_REMOTE` 非布尔值启动失败；
- 远程模式初始化输出一次明确 warning；
- 现有捕获、实时列表、Edit & Replay 和真实 HTTP Replay 测试无回归；
- 0.1.3 wheel/sdist、Twine check 和全新环境安装通过。

## 9. 风险与后续演进

主要风险是用户在公网、共享 Wi-Fi、容器公开端口或隧道环境误用远程模式。MVP 通过默认关闭、显式命名、启动 warning 和文档降低误用，但不承诺抵御能连接该端口的攻击者。

只有出现明确的远程共享需求后，后续版本才考虑带认证的访问模式。届时应增加新的配置而不是悄悄改变 `ALLOW_REMOTE=True` 的无认证语义，以保持向后兼容。
