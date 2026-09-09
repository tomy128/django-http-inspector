# django-http-inspector 0.1.2 实施计划

日期：2026-09-09

依据：`docs/superpowers/specs/2026-09-09-edit-and-live-replay-012-design.md`

## 目标

让普通 Replay 点击即发，为请求列表提供不打断当前详情的自动更新，并增加只允许修改 Headers 与文本 Body 的 Edit & Replay，同时保持 Method、完整 URL、安全边界和独立 SQLite 架构不变。

## 步骤

1. 增加纯函数编辑解析模块：Header 文本序列化/解析、Latin-1 与大小限制、Content-Type/charset 判定、文本 body 初始解码和提交编码。
2. 扩展 replay service，使 headers/body/mode 可作为经过验证的快照传入；普通 replay 固定 equivalent，编辑 replay 固定 edited。
3. 扩展 InspectorApp：普通 replay 移除 confirm 依赖；增加轻量列表 JSON endpoint；增加限量 JSON edit-replay endpoint及统一响应契约。
4. 更新服务端模板：常驻副作用提示、渐进式编辑 DOM、只读 Method/URL、编辑资格、初始 header/body 数据和真实 Live 状态。
5. 重写原生 JavaScript：2 秒完整轻量快照轮询、退避/可见性状态、ID diff、安全 DOM 构造、冻结详情、编辑/Reset/Cancel/dirty guard 和 JSON replay 状态。
6. 完善 CSS 的 editor、状态、loading、error、responsive 和 reduced-motion 表现，并运行 impeccable detector。
7. 增加单元与端到端测试：解析边界、MIME/charset、API 状态、私有 target、edited attempt 快照、原 Method/URL、轮询 payload 和页面结构。
8. 同步 README、PRODUCT、架构、安全、replay semantics、CHANGELOG 和发布文档；版本升级为 0.1.2。
9. 运行全套测试、编译检查、构建、Twine、wheel 内容检查和全新环境安装/运行 smoke test；dist 只保留 0.1.2。

## 风险控制

- 编辑校验在创建 ReplayAttempt 前完成。
- 客户端永不把服务端数据写入 `innerHTML`。
- 自动更新只操作列表节点，不替换详情 DOM。
- transport 开始前 pending attempt 必须提交，发送后失败不自动重试。
- 不引入前端框架、SSE 或新 Python 依赖。
- 不上传 PyPI、不创建 tag。
