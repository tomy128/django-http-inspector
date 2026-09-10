# django-http-inspector 0.1.4 Multipart 展示设计

日期：2026-09-10
状态：已由用户确认，待独立评审
目标版本：0.1.4

## 1. 用户目标与根因

开发者检查 `multipart/form-data` 时应直接看到有意义的字段和文件元数据，而不是 boundary 噪声或笼统的 `Binary body — preview unavailable`。当前展示器将整个 body 严格解码为 UTF-8：纯文本 multipart 恰好能显示 raw；任一文件 part 含非法 UTF-8 字节时整个预览失败。因此差异由 bytes 是否整体有效 UTF-8 决定，不是大小。

0.1.4 同时默认排除 Chrome DevTools 自动工作区探测请求，并统一 Edit & Replay 文案。

## 2. 核心取舍与 MVP

采用“结构化字段 + 文件元数据”，不显示文件 bytes。相比强制 raw 解码，它没有二进制乱码；相比 Parsed/Raw 双视图，它保持 MVP 简单。解析只用于 presentation，不改变存储、捕获或 Replay。

包含：

- 默认排除 `/.well-known/appspecific/com.chrome.devtools.json`；
- 将 UI 和当前用户文档中的 `Edit request` 改为 `Edit & Replay`；
- 为完整的 `multipart/form-data` request/response body 提供结构化展示；
- 文本字段保留顺序、重复项和空值；
- 文件字段只展示 field name、filename、media type 和捕获 payload 字节数；
- malformed/不支持结构安全回退到现有 raw/binary 展示；
- 版本升级到 0.1.4。

不包含文件内容预览/下载/解压、multipart 编辑器、Parsed/Raw 切换、字段脱敏策略或 Replay bytes 修改。Inspector 不按字段名隐藏 password/CSRF/token；安全文档继续明确敏感数据风险。

## 3. Multipart 识别与解析

只有 media type 大小写不敏感地等于 `multipart/form-data`、body 完整且 Content-Type 提供唯一非空 boundary 时才尝试解析；quoted boundary 合法。使用 Python 标准库，不新增依赖。解析函数接收 body bytes 和 Content-Type，返回纯数据结构而非 HTML：

```text
kind: field | file
name: string
value: string             # field only
filename: string          # file only
content_type: string      # file only，缺失时 application/octet-stream
size: non-negative int    # file only，捕获到的 part payload bytes
```

顺序与重复 name 原样保留。无 filename 参数是文本字段；存在 filename（包括空值）是文件。Content-Disposition 缺失/非 `form-data`、缺 name、malformed header、nested multipart 或结构无法可靠解析时，整个解析失败并回退，不输出半套结果。

文本 part 使用自身 Content-Type charset，未声明时为 UTF-8；严格解码失败使整体结构化解析回退。文件 part 永不解码。size 是从已捕获 body 解析出的 part payload bytes 长度，不声称等于上传前源文件大小。

输入 body 已受 `CAPTURE_MAX_BYTES` 限制；解析器仍限制 part 数量以及 name、filename、Content-Type 元数据长度，拒绝 nested multipart，不递归、不产生相对输入无界的副本。

## 4. 截断、不完整与回退

`present_body` 接收完整性信息，或由调用方只在完整时允许 multipart。request/response 的 `*_body_truncated` 或 `*_body_incomplete` 为真时不得结构化解析，继续沿用 raw/binary preview 和已有不完整提示。

解析失败的回退规则：整个 body 可严格 UTF-8 解码则返回 raw，否则返回 `Binary body — preview unavailable`。解析异常不传播到 Inspector 页面，也不影响业务响应。

## 5. UI

模板使用 Django 自动转义逐项渲染，不拼接 HTML、不使用 `safe`。示例：

```text
name        AIConsole
stage
version     v1.0.2
package     file.zip · application/zip · 18,342 B
```

字段 name、filename 和 Content-Type 在展示层有明确长度上限与省略标记；文本 value 位于可换行/滚动区域。文件 bytes 不进入 HTML。Body 类型标签为 `multipart`；合法空表单显示 `No form fields`。

按钮文字改为 `Edit & Replay`。进入后的编辑工作区、`Replay edited request`、只读 method/URL 和草稿行为不变。

## 6. Chrome 探测排除

默认 `EXCLUDE_PATHS` 增加 `/.well-known/appspecific/com.chrome.devtools.json`。这只阻止 Inspector 捕获，不拦截请求，Django/runserver 仍可能记录 404。用户显式设置 `EXCLUDE_PATHS` 时继续完整替换默认值，不改变合并语义。

## 7. Replay 与编辑边界

Repository 仍保存原始 bytes，普通 Replay 必须逐字节发送原捕获 body。`multipart/form-data` 不属于 Edit & Replay 支持的文本 media type，即使其所有 parts 恰好可解码，也不得开放编辑，避免破坏 boundary、Content-Length 或文件内容。

## 8. 技术路径

- `inspector/presentation.py`：增加有界 multipart 识别、解析和 presentation 数据；保留 JSON/form/raw。
- `inspector/app.py`：传递完整性并提供结构化 context。
- template/CSS：渲染字段和文件元数据；更新按钮文案。
- `replay/edit.py`：明确 multipart 不可编辑；service/transport 不改。
- `config.py`：增加 Chrome 默认排除路径。
- Tests：解析、HTML 防泄漏/转义、截断回退、默认排除、Replay bytes 和文案。
- README、PRODUCT、架构、安全、Changelog、发布文档与版本元数据同步。

## 9. 验收

- 默认不捕获 Chrome well-known 请求，自定义排除替换语义不变；
- UI 显示 `Edit & Replay`，不再显示旧按钮文案；
- 纯文本、重复/空/Unicode 字段依序展示；
- 带非 UTF-8 ZIP bytes 时仍显示字段及文件名、类型、精确捕获 payload size；
- quoted boundary/合法 charset 正确；malformed、nested、缺 disposition/name、非法文本 charset安全回退；
- 截断/读取不完整 request/response 不做结构化解析；
- 文件 bytes、HTML 和超长元数据不未经转义或无界进入页面；
- multipart Replay bytes 不变，Edit & Replay 不开放；
- 现有实时列表、远程访问和 Replay 无回归；
- 0.1.4 tests、wheel/sdist、Twine 和全新环境安装通过。

## 10. 风险与演进

标准库 MIME parser 可能宽容接受边缘格式，因此解析后必须再次验证 disposition、name、nested type 和完整结构。UI 必须把 size 表述为捕获 payload size。后续只有在真实需求出现后才设计 Raw 切换或受限下载。
