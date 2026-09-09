# django-http-inspector 独立 SQLite 存储设计

日期：2026-09-09

## 1. 用户目标

django-http-inspector 应当在安装并包装 WSGI application 后立即可用，不要求用户修改业务数据库或执行 Django migration。同时，请求记录需要跨 `runserver` 自动重载保留，避免内存存储造成调试上下文频繁丢失。

默认体验为：

```python
# settings.py（可选，全部字段都有默认值）
DJANGO_HTTP_INSPECTOR = {
    "ENABLED": DEBUG,
}
```

```python
# wsgi.py
from django.core.wsgi import get_wsgi_application
from django_http_inspector import InspectorWSGI

application = InspectorWSGI(get_wsgi_application())
```

用户不再需要把包加入 `INSTALLED_APPS`，也不需要运行 `manage.py migrate`。

## 2. 核心取舍

### 2.1 默认使用项目内独立 SQLite

默认数据库路径为：

```text
BASE_DIR/.django-http-inspector.sqlite3
```

这样可以同时满足：

- 不在 Django `default` 或其他业务数据库中创建表；
- 不依赖业务项目的 database engine、router 或 migration graph；
- `runserver` 重载和普通进程重启后保留记录；
- 数据按项目隔离，位置直观，删除文件即可重置；
- 使用 Python 标准库 `sqlite3`，不增加依赖和额外服务。

代价是项目目录会出现运行时文件。文档必须建议忽略主数据库文件及 WAL sidecar：

```gitignore
.django-http-inspector.sqlite3
.django-http-inspector.sqlite3-shm
.django-http-inspector.sqlite3-wal
```

### 2.2 不保留默认内存后端

内存存储最少侵入，但 `runserver` 自动重载会丢失记录，多进程下也会产生相互隔离的记录集。它不适合作为默认产品行为，MVP 不为其增加单独实现。

### 2.3 暂不提供 Django ORM 后端

同时维护独立 SQLite 和 Django ORM 会引入 repository 双实现、migration router、数据库兼容矩阵以及更多配置，但当前没有已验证的用户价值。MVP 删除现有 Django models 和 migrations，不提供 `STORAGE="django"`。未来只有在共享数据库或团队持久化需求得到验证后，再通过明确的 storage backend 边界增加，而不改变默认行为。

## 3. 配置语义

现有 `DJANGO_HTTP_INSPECTOR` 设置增加：

```python
DJANGO_HTTP_INSPECTOR = {
    "SQLITE_PATH": BASE_DIR / ".django-http-inspector.sqlite3",
}
```

规则如下：

- 未配置时，使用 `settings.BASE_DIR` 下的默认文件；
- 如果项目没有 `BASE_DIR`，使用当前工作目录；
- 接受 `str` 和 `os.PathLike`；
- 相对路径相对于 `BASE_DIR`，缺少 `BASE_DIR` 时相对于当前工作目录；
- 自动创建父目录；
- 空路径、目录路径或不可用路径给出明确配置/日志错误；
- 路径在 wrapper 初始化时解析并固定，单个 wrapper 生命周期内不随工作目录变化。

不增加 `STORAGE` 配置，因为 MVP 只有一个后端。避免为尚不存在的可插拔能力提前设计公共接口。

## 4. 组件边界

存储访问收敛到内部 repository：

```text
Capture ─┐
UI ──────┼── InspectorRepository ── sqlite3 ── 独立数据库文件
Replay ──┘
```

`InspectorRepository` 负责：

- 初始化和升级内部 schema；
- 创建、更新、查询和删除 Exchange；
- 创建、更新和查询 ReplayAttempt；
- 原子认领 replay correlation nonce；
- 根据 `MAX_RECORDS` 裁剪旧 Exchange；
- 将 SQLite rows 映射为供 capture、UI 和 replay 使用的简单记录对象。

Capture、UI 和 replay 不直接拼写 SQL，也不依赖 Django ORM。记录对象仅承载数据与少量展示需要的常量，不实现 active-record 行为。

## 5. Schema 与升级

独立数据库保留现有 `Exchange` 和 `ReplayAttempt` 的产品字段及关联语义。headers 和地址列表使用 JSON 文本，body 使用 BLOB，时间使用明确的 UTC 表示。主键使用 SQLite integer primary key；correlation nonce 保持唯一索引。

数据库初始化与 repository 初始化绑定：

1. 连接目标文件；
2. 设置连接级 pragmas；
3. 在事务中读取内部 schema version；
4. 新数据库创建当前 schema；
5. 旧数据库依次执行包内、单向、幂等边界清晰的升级步骤；
6. 数据库版本高于当前代码支持版本时拒绝读写并输出明确诊断，不能猜测降级。

版本信息使用 `PRAGMA user_version`。MVP 当前 schema 记为 version 1。升级失败必须回滚，不留下部分升级状态。

该数据库属于可删除的开发数据；文档需要说明删除文件会丢失历史记录，并会在下次启动自动重建。

## 6. 并发与生命周期

repository 不跨线程共享一个长期 `sqlite3.Connection`。每次逻辑操作创建短生命周期连接，并设置：

- `journal_mode=WAL`，提高捕获写入和 UI 读取并发能力；
- 非零 `busy_timeout`，吸收短暂写锁竞争；
- `foreign_keys=ON`，保证关联行为；
- 明确事务边界，避免持锁跨网络 replay。

Schema 初始化使用进程内锁减少同一进程的重复工作，同时依赖 SQLite 事务处理多进程同时首次启动。初始化必须可重复进入。

SQLite 适合本地单项目开发，不承诺网络文件系统、多主机共享或高吞吐生产负载。多 worker 可以共享同一个本地文件，但 Inspector 仍是开发工具，不因此扩展为生产可观测平台。

## 7. 数据流

### 7.1 捕获

wrapper 创建 repository 并将其传给 capture。请求开始时创建 pending Exchange；响应完成或异常时更新同一记录并执行裁剪。存储异常只写入 `django_http_inspector` logger，不得阻断、替换或改变业务响应。

### 7.2 Inspector UI

Inspector 内置 WSGI app 使用同一个 repository 查询列表、详情和 attempts。Clear 操作在事务中删除 Inspector 数据，不操作任何 Django 数据库。

模板不能再依赖 Django app template discovery。Inspector 从安装包资源加载自身模板，并使用独立的 Django template engine 渲染；静态资源继续通过包资源提供。因此无需加入 `INSTALLED_APPS`。

### 7.3 Replay 与 correlation

Replay 先保存 ReplayAttempt，随后在不持有数据库事务的情况下完成 DNS、连接、TLS 和 HTTP 读写，再更新 attempt。replay 请求再次进入 wrapper 后，通过 repository 原子认领 correlation nonce 并关联新的 Exchange。一个 nonce 最多成功认领一次，重复 correlation 继续记录诊断。

真实原地址 HTTP replay 的既有语义、安全校验和无重定向策略不变。

## 8. 错误处理

- 路径配置类型或值非法：wrapper 初始化时抛出 `ImproperlyConfigured`；
- 父目录无法创建、数据库不可写、schema 不兼容：记录清晰错误，捕获功能降级但业务 application 仍可服务；
- 单次捕获写入失败：记录 exception，继续业务请求；
- Inspector UI 查询存储失败：返回 Inspector 自己的 500 诊断页面，不把异常送入 Django middleware；
- replay attempt 无法持久化：不发送真实 HTTP 请求，避免产生无法追踪的副作用；
- 数据库锁竞争超过 timeout：按对应操作的上述失败策略处理。

wrapper 初始化不能因为开发记录库暂时不可用而阻止整个 Django 服务启动。配置本身无效仍应快速失败，因为这属于可立即修复的确定性错误。

## 9. 安全与隐私

独立 SQLite 仍保存 headers、cookies、token、个人信息和请求/响应 body。默认项目内文件不会自动进入版本控制，README 和安全文档必须明确：

- 将数据库及 WAL sidecar 加入 `.gitignore`；
- 不提交、上传或共享该文件；
- Inspector 仅用于受控开发环境；
- 使用 Clear 或删除文件清理数据；
- 文件权限遵循创建进程的操作系统权限与 umask。

MVP 不自行实现数据库加密。Inspector 的 loopback 访问限制、Host 校验和 replay 防伪 token 保持不变。

## 10. 迁移现状与发布

当前包尚在首次发布准备阶段，可以直接移除 Django ORM 模型和 `migrations/`，不为未正式发布的数据格式建立兼容层。分发包名和 import 包名保持不变。

发布文档不再运行 `makemigrations --check`，改为验证：

- wheel 中不包含 Django migrations；
- wheel 安装后无需 `INSTALLED_APPS` 和 migrate；
- 临时项目首次捕获自动创建独立数据库和 schema；
- wrapper 重建后可读取先前记录。

由于运行时和接入语义发生显著变化，仍使用未发布的 `0.1.0` 构建产物即可；旧的本地 `dist/` 必须在重新构建前清理，避免误上传过时 artifact。

## 11. 验收标准

- 未加入 `django_http_inspector` 到 `INSTALLED_APPS` 时，捕获、UI 和 replay 全部工作；
- 未执行 Django migration 时，首次访问自动创建独立 SQLite 和 version 1 schema；
- wrapper/process 重建后历史 Exchange 和 ReplayAttempt 仍存在；
- Django `default` 数据库不产生 django-http-inspector 表或 migration 记录；
- 自定义相对和绝对 `SQLITE_PATH` 行为正确；
- 并发捕获与 UI 查询不会共享非法线程连接，锁等待有界；
- `MAX_RECORDS`、Clear、replay correlation 与真实 HTTP replay 行为保持正确；
- 数据库写入故障不影响业务响应，无法持久化 attempt 时不发送 replay；
- README、架构、安全、replay 和发布文档与新默认一致；
- 全部测试、wheel/sdist 构建、Twine 检查和干净环境 wheel 安装验证通过。

## 12. 后续演进

只有在真实需求出现后再考虑：

- 内存后端，用于完全无文件场景；
- Django database backend，用于用户显式选择的共享持久化；
- 自动保留时长或数据库大小上限；
- 数据导入导出；
- ASGI 下更细的并发优化。

这些能力不得改变独立 SQLite 的默认零迁移体验。
