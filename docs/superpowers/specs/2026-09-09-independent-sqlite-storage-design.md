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

独立数据库保留现有 `Exchange` 和 `ReplayAttempt` 的产品字段及关联语义。headers 和地址列表编码为 UTF-8 JSON 数组文本，body 使用 BLOB，布尔值使用受 `CHECK` 约束的 0/1 INTEGER，时间统一保存为带 `Z` 的 UTC ISO 8601 文本。Python 层读出时间后转换为 aware `datetime`，读出 JSON 后转换为 list。

Version 1 schema 等价于以下 DDL；实现可以调整 SQL 排版，但不能改变列、约束、索引和删除语义：

```sql
CREATE TABLE replay_attempt (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_exchange_id INTEGER NULL REFERENCES exchange_record(id) ON DELETE SET NULL,
    mode TEXT NOT NULL DEFAULT 'equivalent',
    submitted_at TEXT NOT NULL,
    completed_at TEXT NULL,
    state TEXT NOT NULL DEFAULT 'pending' CHECK (state IN ('pending', 'complete', 'error')),
    method TEXT NOT NULL,
    url TEXT NOT NULL,
    request_headers TEXT NOT NULL DEFAULT '[]',
    request_body BLOB NOT NULL DEFAULT X'',
    response_status INTEGER NULL,
    response_headers TEXT NOT NULL DEFAULT '[]',
    response_body BLOB NOT NULL DEFAULT X'',
    response_size INTEGER NOT NULL DEFAULT 0,
    response_body_truncated INTEGER NOT NULL DEFAULT 0 CHECK (response_body_truncated IN (0, 1)),
    error_stage TEXT NOT NULL DEFAULT '',
    error_summary TEXT NOT NULL DEFAULT '',
    correlation_nonce TEXT NOT NULL UNIQUE,
    correlation_claimed INTEGER NOT NULL DEFAULT 0 CHECK (correlation_claimed IN (0, 1)),
    peer_address TEXT NOT NULL DEFAULT '',
    target_addresses TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE exchange_record (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    completed_at TEXT NULL,
    duration_ms REAL NULL,
    method TEXT NOT NULL,
    url TEXT NOT NULL DEFAULT '',
    url_provenance TEXT NOT NULL DEFAULT 'reconstructed',
    scheme TEXT NOT NULL DEFAULT '',
    host TEXT NOT NULL DEFAULT '',
    path TEXT NOT NULL,
    query_string TEXT NOT NULL DEFAULT '',
    request_headers TEXT NOT NULL DEFAULT '[]',
    request_body BLOB NOT NULL DEFAULT X'',
    request_content_type TEXT NOT NULL DEFAULT '',
    request_declared_size INTEGER NULL,
    request_observed_size INTEGER NOT NULL DEFAULT 0,
    request_captured_size INTEGER NOT NULL DEFAULT 0,
    request_body_truncated INTEGER NOT NULL DEFAULT 0 CHECK (request_body_truncated IN (0, 1)),
    request_body_incomplete INTEGER NOT NULL DEFAULT 0 CHECK (request_body_incomplete IN (0, 1)),
    client_addr TEXT NOT NULL DEFAULT '',
    response_status INTEGER NULL,
    response_headers TEXT NOT NULL DEFAULT '[]',
    response_body BLOB NOT NULL DEFAULT X'',
    response_size INTEGER NOT NULL DEFAULT 0,
    response_body_truncated INTEGER NOT NULL DEFAULT 0 CHECK (response_body_truncated IN (0, 1)),
    response_body_incomplete INTEGER NOT NULL DEFAULT 0 CHECK (response_body_incomplete IN (0, 1)),
    state TEXT NOT NULL DEFAULT 'pending'
        CHECK (state IN ('pending', 'complete', 'application_error')),
    error_summary TEXT NOT NULL DEFAULT '',
    correlation_diagnostic TEXT NOT NULL DEFAULT '',
    observed_replay_attempt_id INTEGER NULL UNIQUE
        REFERENCES replay_attempt(id) ON DELETE SET NULL
);

CREATE INDEX exchange_record_order_idx ON exchange_record(created_at DESC, id DESC);
CREATE INDEX replay_attempt_source_order_idx
    ON replay_attempt(source_exchange_id, submitted_at DESC, id DESC);
```

SQLite 允许外键引用稍后创建的表，因此两个表和索引必须在同一 schema transaction 内创建。`correlation_nonce` 的 `UNIQUE` 约束提供唯一索引；`observed_replay_attempt_id UNIQUE` 保证一个 attempt 最多关联一个 observed Exchange。

数据库初始化与 repository 初始化绑定：

1. 连接目标文件并设置 `busy_timeout=1000` 和 `foreign_keys=ON`；
2. 在 autocommit 状态请求一次 `PRAGMA journal_mode=WAL`；若文件系统不支持 WAL，则保留 SQLite 返回的 journal mode、记录一次 warning 并继续；
3. 执行 `BEGIN IMMEDIATE` 获取 schema 写锁；
4. 获得锁后重新读取 `PRAGMA user_version`，不能使用加锁前的判断；
5. version 0 必须是空数据库，随后在当前事务中创建完整 schema，并仅在所有 DDL 成功后设置 `user_version=1`；version 0 若已存在 Inspector 表则视为不兼容；
6. 旧版本依次执行包内、单向的升级步骤，并仅在该步成功后更新版本；
7. 数据库版本高于当前代码支持版本时回滚并拒绝读写，不能猜测降级；
8. 提交后关闭初始化连接。竞争进程取得锁后会重新读取新版本并直接提交退出。

版本信息使用 `PRAGMA user_version`。MVP 当前 schema 记为 version 1。每个升级步骤的 DDL、数据变换和版本更新属于同一事务；升级失败必须回滚。未来多个版本按顺序逐级升级，禁止跳步。

该数据库属于可删除的开发数据；文档需要说明删除文件会丢失历史记录，并会在下次启动自动重建。

## 6. 并发与生命周期

repository 不跨线程共享一个长期 `sqlite3.Connection`。每次逻辑操作创建短生命周期连接。WAL 只在初始化时请求，不在每次操作重复切换；所有普通连接设置：

- 固定 `busy_timeout=1000ms`，吸收短暂写锁竞争且限制业务捕获等待；
- `foreign_keys=ON`，保证关联行为；
- 明确事务边界，避免持锁跨网络 replay。

单语句写入使用显式短事务；多语句写入和 read-modify-write 使用 `BEGIN IMMEDIATE`。读取使用普通只读事务。任何网络 replay 开始前必须提交并关闭数据库事务与连接。

Schema 初始化使用进程内锁减少同一进程的重复工作，同时使用上述 `BEGIN IMMEDIATE` 算法处理多进程同时首次启动。初始化必须可重复进入。

SQLite 适合本地单项目开发，不承诺网络文件系统、多主机共享或高吞吐生产负载。多 worker 可以共享同一个本地文件，但 Inspector 仍是开发工具，不因此扩展为生产可观测平台。

## 7. 数据流

### 7.1 捕获

wrapper 创建 repository 并将其传给 capture。请求开始时创建 pending Exchange；若请求带 correlation nonce，repository 在同一个短事务内完成“确认 attempt 为 pending 且未认领、将其标记为已认领、把 Exchange 关联到 attempt”。任一步失败则整体回滚，nonce 不得被消费。响应完成或异常时更新同一记录并执行裁剪。存储异常只写入 logger，不得阻断、替换或改变业务响应。

### 7.2 Inspector UI

Inspector 内置 WSGI app 使用同一个 repository 查询列表、详情和 attempts。Clear 操作在同一事务中删除两张表的全部 Inspector 数据，不操作任何 Django 数据库；UI 文案明确它同时清除请求和 replay 历史。

模板不能再依赖 Django app template discovery。Inspector 使用 `importlib.resources.files()` 读取包内全部模板内容，将它们交给启用 autoescape 的独立 `django.template.Engine` 与 `locmem.Loader`；这样模板继承仍能解析，也不假设 wheel 资源存在真实文件路径。使用 Django 内置 filters，模板缺失作为 Inspector 自身 500 诊断处理。静态资源继续通过包资源提供。因此无需项目配置 `TEMPLATES` 或加入 `INSTALLED_APPS`。

### 7.3 Replay 与 correlation

Replay 必须先在短事务中创建并成功提交 pending ReplayAttempt。只有 commit 成功后才允许 DNS 或任何网络发送；提交失败立即向 Inspector 返回错误，且 transport 不得被调用。随后关闭数据库连接，在不持有事务的情况下完成 HTTP 读写，再以 best effort 更新 attempt。真实请求发送后，最终状态更新失败意味着副作用已经发生但结果未能持久化：记录高严重度日志并向当前 UI 操作返回明确诊断，绝不自动重试 HTTP。

replay 请求再次进入 wrapper 后，通过上一节定义的单个 repository 操作原子认领 correlation nonce 并关联新的 Exchange。只有 `state='pending' AND correlation_claimed=0` 的 attempt 可被认领；一个 nonce 最多成功认领一次。已认领 nonce 再次出现时，新 Exchange 保存 `duplicate-correlation` 诊断，但不改变既有关联。

删除语义固定如下：

- `MAX_RECORDS` 只裁剪最旧 Exchange；
- 删除 source Exchange 时 ReplayAttempt 保留，`source_exchange_id` 自动置空；
- 删除 observed Exchange 时 ReplayAttempt 保留；
- 删除 ReplayAttempt 时 observed Exchange 保留，`observed_replay_attempt_id` 自动置空；
- Clear 显式删除 Exchange 和 ReplayAttempt 两张表中的全部数据。

真实原地址 HTTP replay 的既有语义、安全校验和无重定向策略不变。

## 8. 错误处理

- 路径配置类型或值非法：wrapper 初始化时抛出 `ImproperlyConfigured`；
- 父目录无法创建、数据库不可写、schema 不兼容：记录一次清晰错误，wrapper 持有 unavailable repository；该 wrapper 生命周期内不逐请求重试，业务请求直接透传，重新创建 wrapper 时重新初始化；
- 单次捕获写入失败：记录 exception，继续业务请求；
- Inspector UI 在 repository unavailable 或查询失败时仍可进入，并返回包内、不依赖数据库模板的 500 诊断页面；
- pending replay attempt 未成功 commit：不发送真实 HTTP 请求；发送后的最终更新失败按第 7.3 节降级；
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
- wrapper 重建后可读取先前记录；
- wheel/sdist 包含 HTML、CSS、JavaScript 和所有 schema 升级代码；
- 最小 settings 不配置 `TEMPLATES`、不安装 Inspector app 时仍能渲染 UI。

由于 PyPI 已存在 `0.1.0`，独立 SQLite 行为作为补丁版本 `0.1.1` 发布；旧的本地 `dist/` 必须在重新构建前清理，避免误上传过时 artifact。

## 11. 验收标准

- 未加入 `django_http_inspector` 到 `INSTALLED_APPS` 时，捕获、UI 和 replay 全部工作；
- 未执行 Django migration 时，首次访问自动创建独立 SQLite 和 version 1 schema；
- wrapper/process 重建后历史 Exchange 和 ReplayAttempt 仍存在；
- Django `default` 数据库不产生 django-http-inspector 表或 migration 记录；
- 自定义相对和绝对 `SQLITE_PATH` 行为正确；
- 自动创建自定义父目录，生成的 WAL sidecar 不进入版本控制；
- 两个进程同时首次初始化只得到一份完整 version 1 schema；
- 升级中途失败回滚，过高 `user_version` 时业务仍服务且 UI 显示诊断；
- 并发捕获与 UI 查询不共享线程连接，覆盖 lock timeout；
- `MAX_RECORDS`、Clear、外键删除语义和真实 HTTP replay 保持正确；
- correlation 关联失败时 nonce 不被消费，并发请求至多一个成功关联；
- pending attempt commit 失败时 transport 不被调用；发送后最终更新失败不会自动重试；
- 启动时数据库不可用不会阻止业务服务，且不会逐请求重复记录初始化错误；
- README、架构、安全、replay 和发布文档与新默认一致；
- 全部测试、wheel/sdist 构建、Twine 检查和干净环境 wheel 安装验证通过。

## 12. 既有文档迁移清单

实施必须同步改写以下已知冲突：

- 原 MVP 设计的 2.3、4.1、4.2、5、7、11 和 12.3 节；
- `README.md` 的安装、接入、配置、开发和 `.gitignore` 指引；
- `docs/architecture.md` 的存储组件与数据流；
- `docs/security.md` 的数据库主文件、`-wal`、`-shm` 忽略与删除注意事项；
- `docs/replay-semantics.md` 的 attempt commit、correlation transaction 与发送后更新失败语义；
- `docs/releasing.md` 的 migration check，替换为最小 settings、资源内容和独立建库验证。

安装包不得继续包含 `models.py`、`migrations/` 或其他会诱导用户采用 Django ORM 接入的说明。

## 13. 后续演进

只有在真实需求出现后再考虑：

- 内存后端，用于完全无文件场景；
- Django database backend，用于用户显式选择的共享持久化；
- 自动保留时长或数据库大小上限；
- 数据导入导出；
- ASGI 下更细的并发优化。

这些能力不得改变独立 SQLite 的默认零迁移体验。
