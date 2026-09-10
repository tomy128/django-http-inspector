# django-http-inspector 0.1.4 实施计划

日期：2026-09-10

依据：`docs/superpowers/specs/2026-09-10-multipart-presentation-014-design.md`

## 目标

将完整 multipart/form-data 以有序字段和文件元数据展示，保留原始捕获与 Replay bytes；默认过滤 Chrome DevTools 探测噪声，并统一 `Edit & Replay` 文案。

## 步骤

1. 扩展 presentation 模块：定义 multipart 纯数据结构、Content-Type/boundary 预检、1 MiB 输入预算、标准库 MIME 解析、defects/结构/参数/CTE/控制字符/parts 与文本预算验证，以及 raw/binary 回退。
2. 将 `present_body` 调整为 `(text, kind, parts)` 契约；Inspector context 分别传入 request/response 完整性，并暴露两侧 multipart parts。
3. 更新模板与 CSS：紧凑呈现字段、重复项、空值及文件 captured-content size；增加 response 不完整提示；将按钮改为 `Edit & Replay`。
4. 明确 multipart 不可编辑；为 Chrome well-known 路径增加默认排除项，保留显式 `EXCLUDE_PATHS` 完整替换行为。
5. 增加 presentation、UI、wrapper、配置和 Replay 回归测试，覆盖正常 multipart、非 UTF-8 文件、boundary/defect/charset/CTE/control/resource limits、转义、四种完整性 flag 和 bytes 不变。
6. 使用 impeccable detector 检查模板/CSS；同步 README、PRODUCT、架构、安全、Changelog、发布文档及 0.1.4 版本。
7. 运行全套测试、Python/JS/diff 检查，清理旧 dist，构建并 Twine 校验 0.1.4，在全新环境安装 wheel。
8. 归档任务并提交单一实现 commit；不上传 PyPI、不创建 tag；保留任务开始前 `wsgi.py` 的用户未提交 import。

## 风险控制

- presentation parser 失败只回退，不影响 Inspector 页面或业务响应。
- 文件 bytes 永不进入 context/template，multipart Edit & Replay 始终禁用。
- 1 MiB 预览硬上限在 MIME parser 前执行；其余预算在渲染前执行。
- 不引入依赖，不递归 nested multipart，不改变 repository schema 或 replay transport。
