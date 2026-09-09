# django-http-inspector 0.1.2 Replay 体验设计

日期：2026-09-09

## 1. 用户目标

本地调试 Django webhook/API 的开发者需要更短的 replay 路径：普通 replay 不应每次勾选重复确认；请求流应在捕获发生后自动出现；用户应能调整请求 Headers 和文本 Body 后，仍向原 Method、原完整 URL 发起真实 HTTP replay。

0.1.2 保持产品边界：它是请求检查与重放工具，不是通用 API 客户端。Method、URL 和 query target 不可编辑，原始 Exchange 永不修改。

## 2. 核心取舍

### 2.1 按钮点击即确认 replay 风险

移除现有 side-effects checkbox 和 `required` 约束。在 Replay 操作旁常驻显示：

```text
Replay sends a real request and may cause side effects.
```

点击 `Replay request` 或 `Replay edited request` 本身即表示用户确认真实副作用以及对私有/loopback target 的访问。操作不再出现二次确认，防伪 token、loopback client 限制、Host 检查、DNS 固定和禁止 redirect 保持不变。

### 2.2 增量 JSON 短轮询，而非 SSE 或整页刷新

客户端每 2 秒调用 package-owned JSON endpoint，并按 Exchange ID 合并列表。该方案在 WSGI `runserver` 下没有长连接占用，且不会替换详情 DOM 或破坏编辑草稿。

SSE 延迟更低，但增加连接生命周期、断线和 WSGI thread 成本；整页刷新会破坏 tab、滚动、选中项和编辑状态，两者均不进入 0.1.2。

### 2.3 渐进式编辑，而非永久输入框

默认详情保持高密度只读视图。点击 `Edit request` 后，仅 Request tab 的 Headers 和 Body 在原位置切换为编辑器。用户选择原始文本 Headers 编辑，因为复制粘贴优先于逐行控件。

## 3. 用户界面

### 3.1 只读状态

详情 header 展示只读 Method、URL、风险说明与两个操作：

```text
POST  https://example.test/webhook
Replay sends a real request and may cause side effects.

[Edit request]  [Replay request]
```

当原请求 body 被截断或读取不完整时，普通 Replay 与 Edit request 均禁用，并显示既有原因。当 body 是完整二进制时，普通 Replay 可用，Edit request 禁用并说明二进制 body 不可编辑。

### 3.2 编辑状态

点击 `Edit request` 后：

- Method 与完整 URL 保持只读；
- 明确显示 `Editing a replay copy. The original capture will not change.`；
- Headers 使用等宽原始文本编辑器，每行格式为 `Name: Value`；
- Body 使用等宽文本编辑器；
- 操作为 `Cancel`、`Reset`、`Replay edited request`；
- Cancel 回到只读状态，Reset 恢复当前 Exchange 的原始值；
- replay 完成或失败后保留编辑内容，方便继续调整；
- 编辑器错误就近显示，并把焦点移动到第一个错误字段；
- 有未提交改动时，点击其他请求或离开页面使用浏览器确认；Cancel 若有改动也确认。

键盘焦点、disabled、loading、error 状态沿用现有按钮与输入组件语言。发送期间按钮进入 disabled/loading，防止重复提交。所有状态过渡为 150–180ms ease-out，并尊重 `prefers-reduced-motion`。

### 3.3 Live 状态

右上状态由容易误解的静态 `Capturing` 改为真实反映列表同步状态：

- `Live`：最近一次轮询成功，绿色圆点；
- `Reconnecting…`：轮询失败，琥珀色圆点；
- `Paused`：页面处于 hidden 状态，灰色圆点。

新请求插入左侧顶部并更新计数，但当前选中的详情永不自动切换。编辑中的 Headers、Body、selection、光标与滚动位置不能被轮询触碰。新列表行只使用轻微状态进入效果；reduced motion 下立即出现。

## 4. 自动更新 API

新增只读 endpoint：

```text
GET /__inspect/api/exchanges?cursor=<opaque>&limit=200
```

接口每次返回完整的最多 200 条轻量列表快照及 opaque cursor：

```json
{
  "cursor": "...",
  "exchanges": [
    {
      "id": 42,
      "method": "POST",
      "path": "/webhook",
      "state": "complete",
      "response_status": 200,
      "duration_ms": 31.4,
      "created_at": "2026-09-09T08:00:00Z"
    }
  ],
  "total": 42
}
```

完整轻量快照能正确处理新增、pending 完成、裁剪和 Clear，不包含 headers/body，数据量可控。cursor 由快照中与列表展示相关的字段生成，用于客户端判断是否需要 DOM diff；未知 cursor 或 wrapper 重建不会漏数据。未来若数据规模证明有必要，再做真正增量传输。

客户端规则：

- 固定成功间隔 2 秒；
- 同时最多一个 fetch，上一请求未完成时不启动下一次；
- 失败后按 2s、4s、8s、最高 30s 退避；
- 成功后恢复 2 秒并切为 Live；
- `document.hidden` 时取消计时并显示 Paused，重新 visible 时立即请求；
- 使用 ID 合并、新记录置顶、变化记录原位更新、删除/clear 后按服务器快照校准；
- 当前选中行保持选中，但右侧详情不自动刷新或切换；
- endpoint 复用 Inspector 的 client/Host 安全检查，响应 `Cache-Control: no-store`；
- JSON 序列化和数据库失败返回 package-owned 500，不进入 Django middleware。

## 5. Edit & Replay 数据契约

新增 endpoint：

```text
POST /__inspect/requests/<exchange_id>/edit-replay
Content-Type: application/json
```

请求：

```json
{
  "token": "process-token",
  "headers_text": "Content-Type: application/json\nX-Retry: 2",
  "body_text": "{\"event\":\"invoice.paid\"}"
}
```

服务端始终从原 Exchange 读取 Method 与完整 URL，不接受对应覆盖字段。JSON request body 上限为 `CAPTURE_MAX_BYTES` 加 256 KiB 的 headers/envelope 预算；超过上限返回 413，不做部分解析。新增 413 状态文本。

### 5.1 Headers 解析

- 空行忽略；
- 每个非空行必须含第一个 `:` 分隔符；
- name 去除两端空白后必须符合 HTTP token 字符集合；
- value 只去除分隔符后的一个可选前导空格，保留其余可见内容；
- 拒绝 CR、LF 和其他控制字符；
- 保留顺序与重复 Header；
- 限制 header 行数、单行长度和总字符数，分别为 200、16 KiB、256 KiB；
- 解析错误返回 400 JSON，包含稳定 `code`、用户可读 `message` 和 1-based `line`，不创建 ReplayAttempt。

transport 继续移除 hop-by-hop headers、`Host`、`Content-Length` 与旧 correlation header，再根据实际 target/body 重建必要 header。UI 在编辑器下方常驻简短说明这一规范化行为。

### 5.2 Body 文本资格

只有 request body 捕获完整、未截断且可严格解码时才允许编辑。文本类型包括：

- `text/*`；
- `application/json` 与 `application/*+json`；
- `application/xml` 与 `application/*+xml`；
- `application/x-www-form-urlencoded`；
- 空 Content-Type 但 bytes 可严格 UTF-8 解码。

charset 从 Content-Type 参数读取；未声明时使用 UTF-8。未知 charset 或严格解码失败判定为不可编辑。提交时使用原始 charset 严格编码；编码失败返回 400，不发网。二进制 body 不提供 Base64 或替换字符编辑。

### 5.3 ReplayAttempt

Edit & Replay 不修改 Exchange。创建 pending ReplayAttempt 时保存用户编辑后、transport 规范化前的 Headers 列表和编码后的 body bytes，Method/URL 来自原 Exchange。只有 pending attempt 成功 commit 后才允许真实 HTTP 发送；最终结果更新失败不自动重试。这些字段已存在于 SQLite schema version 1，0.1.2 不升级 schema。

普通 Replay 继续保存原始捕获快照，但不再依赖 `confirm=yes`。两个操作都复用同一 replay service，Edit & Replay 只在进入 service 前产生经过验证的替代 headers/body。

## 6. 组件边界

```text
InspectorApp
├── GET 页面与轻量列表 JSON
├── POST 普通 replay
└── POST edit-replay
       ↓
Edit parser
├── parse_headers(text)
└── decode/encode editable body
       ↓
Replay service (method/url 固定，headers/body 可选快照)
       ↓
SQLite ReplayAttempt → real HTTP transport
```

解析和 body 资格判断放在独立、无 I/O 的模块，便于针对恶意输入和编码边界测试。页面路由、JSON/HTML response 与安全检查留在 InspectorApp。轮询控制和编辑状态只存在于原生 JavaScript，不引入前端框架。

## 7. 错误处理

- Headers/body validation：400 JSON，保留编辑草稿，不创建 attempt；
- JSON malformed：400 JSON；
- request envelope 过大：413 JSON；
- Exchange 不存在：404 JSON；
- body 不可编辑：409 JSON，普通 Replay 不受影响；
- pending attempt commit 失败：500 JSON，不调用 transport；
- transport validation/network 失败：200 JSON 返回已持久化 attempt 状态，让 UI 显示 replay 失败；
- 最终 attempt 更新失败：500 JSON 明确请求可能已经发送，绝不自动重试；
- 自动刷新失败：不清空现有列表，切为 Reconnecting 并退避；
- 自动刷新恢复：合并完整轻量快照，切回 Live。

任何 Inspector endpoint 错误都不能改变业务 Django application 的可用性。

## 8. 安全与隐私

编辑器会展示完整 Authorization/Cookie 等敏感 Headers，与当前详情页的数据敏感度一致。所有文本由模板 autoescape 或 DOM `textContent`/input value 处理，禁止通过 `innerHTML` 插入服务端数据。JSON mutation 仍验证 process token、Origin 和 `Sec-Fetch-Site`。

按钮点击替代 checkbox 后，常驻风险文案不可隐藏在 hover-only tooltip 中，保证键盘和触屏用户可见。服务端不会把浏览器提供的 Method/URL 当作 replay target。

## 9. 测试与验收

- 普通 Replay 页面没有 checkbox，点击按钮即可发送并仍经过 mutation security；
- 私有/loopback target 由按钮点击直接确认，不要求额外字段；
- 轻量列表 endpoint 不包含 headers/body，带 `no-store`，并覆盖新增、pending 完成、裁剪和 Clear；
- 客户端轮询只有一个 in-flight request，处理 Live/Reconnecting/Paused 和退避；
- 自动更新不切换详情、不覆盖 tab/滚动/编辑草稿；
- Method/URL 不出现在可编辑 payload 中，服务端忽略或拒绝伪造字段；
- Headers 原始文本解析覆盖重复项、空值、首个冒号、非法 name、控制字符、行数/单行/总大小；
- 文本 body 覆盖 UTF-8、显式 charset、JSON/XML/form、空 Content-Type、未知 charset、编码失败；
- 二进制、截断和 incomplete body 禁止编辑，但符合条件时仍可普通 Replay；
- 编辑 validation 失败不创建 attempt、不调用 transport；
- Edit & Replay 的 attempt 精确保存实际 Headers/body，原 Exchange 不变；
- 真实 HTTP 端到端验证 edited headers/body 到达原 Method/URL，correlation 正确；
- replay 完成/失败后草稿保留，Reset/Cancel/dirty navigation 行为正确；
- 无 JavaScript 时页面仍可查看并执行普通 Replay；自动刷新与编辑作为增强能力；
- impeccable detector、可见焦点、文本对比和 reduced-motion 检查通过；
- 全部 Python 测试、wheel/sdist、Twine 和全新环境安装验证通过；
- `dist/` 只包含 0.1.2，且包内/metadata 版本一致。

## 10. 文档与发布

同步更新 README、PRODUCT、架构、安全、replay semantics、CHANGELOG 和发布文档。版本从 0.1.1 升为 0.1.2。不得上传 PyPI 或创建 tag，发布仍由用户执行。

## 11. 后续演进

真实使用证明需要后，再考虑 SSE、更细增量 cursor、结构化 Headers 编辑切换、草稿持久化或 JSON 格式化。这些能力不能扩大 Method/URL 可编辑边界，也不能把产品变成在线 API 测试器。
