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

只有 media type 大小写不敏感地等于 `multipart/form-data`、body 完整且 Content-Type 提供唯一非空 boundary 时才尝试解析；quoted boundary 合法。实现使用 `email.parser.BytesParser(policy=email.policy.default)`，在 body 前构造仅含 `MIME-Version: 1.0` 和原始 `Content-Type` 的顶层 headers。拼接前拒绝整个 Content-Type 中的 CR/LF；并验证 boundary 唯一、非空、ASCII、1–70 字节。解析函数返回纯数据而非 HTML：

```text
kind: field | file
name: string
value: string             # field only
filename: string          # file only
content_type: string      # file only，缺失时 application/octet-stream
size: non-negative int    # file only，parser 解码后的捕获内容 bytes
```

顺序与重复 name 原样保留。无 filename/filename* 参数是文本字段；存在其中任一参数（包括空值）是文件。`name` 参数必须存在，但 `name=""` 合法。Content-Disposition 缺失/非 `form-data`、重复 name、重复 filename/filename*、malformed header、nested multipart 或结构无法可靠解析时，整体回退。RFC 2231 filename 参数由 `email.policy.default` 解码；未知 charset、参数 defect 或解码失败回退。解码后的 name、filename、Content-Type 含 NUL、CR、LF、C0/DEL 控制字符（包括 HTAB）时回退。

文本 part 使用自身 Content-Type charset，未声明时为 UTF-8；严格解码失败使整体回退。文件 part 永不显示内容。只接受缺失或 `7bit`、`8bit`、`binary` Content-Transfer-Encoding；base64、quoted-printable 和未知 CTE 回退。size 为 `part.get_payload(decode=True)` 返回 bytes 的长度，UI 称为 `captured content`，不声称是 wire octets 或上传前文件大小。

调用 parser 前设置 1 MiB body 硬上限，超过即回退。解析后最多 200 parts；单个 name/filename/Content-Type 最多 1 KiB Unicode code points；单个文本 value 最多 256 KiB；全部文本 value 最多 512 KiB。任何超限整体回退。1 MiB 输入上限保证 MIME tree 构造有界；nested multipart 一律拒绝且不递归。这些限制只影响预览，不影响保存或 Replay。

顶层与每个 part 的 `defects` 必须为空。包含 parts 时，原始 body 必须有起始 delimiter，并以 closing delimiter 后仅跟可选 CRLF 结束；零-part 表单允许唯一 boundary line 直接是 `--boundary--` 加可选 CRLF，此 closing delimiter 同时满足起始要求。缺 start/close、close 后仍有 delimiter、非空 preamble/epilogue均回退。只接受 CRLF delimiter framing。文件内容中的 boundary-like bytes 只有符合完整 CRLF delimiter grammar 时才可分隔。

## 4. 截断、不完整与回退

`present_body(body, content_type, *, complete=True)` 返回三元组 `(text, kind, parts)`。JSON/form/raw/binary 保持原 text/kind 且 `parts=None`；multipart 成功时为 `("", "multipart", ordered_parts)`。`app.context()` 分别使用 request 和 response 的 truncated/incomplete flags，并提供 `request_multipart_parts` 与 `response_multipart_parts`，不得串用。

任一 `*_body_truncated` 或 `*_body_incomplete` 为真时不得结构化解析，继续 raw/binary。现有 request warning 保持；Response tab 新增 response incomplete/truncated warning，明确 preview 不完整。

解析失败的回退规则：整个 body 可严格 UTF-8 解码则返回 raw，否则返回 `Binary body — preview unavailable`。解析异常不传播到 Inspector 页面，也不影响业务响应。

## 5. UI

模板使用 Django 自动转义逐项渲染，不拼接 HTML、不使用 `safe`。示例：

```text
name        AIConsole
stage
version     v1.0.2
package     file.zip · application/zip · 18,342 B
```

解析已拒绝超 1 KiB 的元数据，模板不再二次截断；文本 value 位于可换行/滚动区域。文件 bytes 不进入 HTML。Body 类型标签为 `multipart`；合法零-part 表单显示 `No form fields`。

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

- 默认不捕获 Chrome well-known 请求；显式空列表和自定义列表继续完整替换默认值；
- UI 显示 `Edit & Replay`，不再显示旧按钮文案；
- 纯文本、重复/空/Unicode 字段依序展示；
- 带非 UTF-8 ZIP bytes 时仍显示字段、文件名、类型和 parser 解码后的 captured-content size；payload 尾随 CRLF 不计入 payload；
- quoted boundary、合法 charset、filename* 正确；缺 closing boundary、parser defects、nested、缺 disposition/name、重复参数、非法 charset/control、非 identity CTE、非空 preamble/epilogue安全回退；
- boundary-like file bytes 不被错误分割；超 body/parts/元数据/文本预算回退；
- request/response truncated 和 incomplete 分别不解析，Response tab 显示不完整提示；
- 文件 bytes、恶意 HTML 和控制字符不进入页面或被自动转义；旧 JSON/form/raw/binary 语义兼容；
- multipart Replay bytes 不变，Edit & Replay 不开放；
- 现有实时列表、远程访问和 Replay 无回归；
- 0.1.4 tests、wheel/sdist、Twine 和全新环境安装通过。

## 10. 风险与演进

标准库 MIME parser 可能宽容接受边缘格式，因此解析后必须再次验证 disposition、name、nested type 和完整结构。UI 必须把 size 表述为 `captured content size`。后续只有在真实需求出现后才设计 Raw 切换或受限下载。
