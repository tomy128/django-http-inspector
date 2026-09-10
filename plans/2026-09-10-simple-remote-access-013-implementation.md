# django-http-inspector 0.1.3 实施计划

日期：2026-09-10

依据：`docs/superpowers/specs/2026-09-10-simple-remote-access-design.md`

## 目标

新增严格布尔 `ALLOW_REMOTE` 配置，让开发者用一个显式开关允许任何可连接客户端访问 `/__inspect/`；默认 loopback-only、高级白名单、mutation 防伪与真实 Replay 语义保持不变。

## 步骤

1. 在 `InspectConfig` 与 `load_config()` 中增加严格布尔 `allow_remote`；仅允许字面量 `True`/`False`，远程模式跳过 client CIDR 的 loopback-only 限制，但保留现有高级字段解析。
2. 在 `request_allowed()` 增加远程模式快速分支，不修改 `mutation_allowed()` 或 replay target 逻辑。
3. 在启用 wrapper 初始化时输出每实例一次的无认证风险 warning，并确保 storage 初始化失败时提示仍先输出。
4. 扩展配置和安全单元测试：严格布尔矩阵、默认行为、高级配置兼容、任意 Host/client 和 mutation gate 不变性。
5. 扩展 WSGI 集成测试：远程客户端分别访问 index、asset、JSON API；关闭模式返回 403；Clear、Replay、Edit & Replay 的 token/Origin/Fetch-Site 拒绝与允许路径。
6. 同步 README、架构、安全、Changelog 和发布文档；版本升级到 0.1.3。
7. 运行全套测试、编译与差异检查，清理旧 dist 后构建 0.1.3，运行 Twine 检查和全新环境 wheel 安装。
8. 归档任务并提交单一实现 commit；不上传 PyPI，不创建 tag。

## 风险控制

- `ALLOW_REMOTE` 默认关闭，不根据 bind address 自动开启。
- warning 不宣称提供认证；能读取页面的人可以取得 mutation token。
- Replay 仍允许用户主动访问私网等目标，不把现有 DNS/peer 检查错误描述成 SSRF 防护。
- 不重构已发布的高级配置解析，不引入依赖、登录系统或策略引擎。
- 保留开始任务前 `wsgi.py` 中已有的未提交改动，不擅自删除或混入本任务提交。
