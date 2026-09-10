# django-http-inspector 0.1.5 自动发布实施计划

日期：2026-09-10

依据：`docs/superpowers/specs/2026-09-10-tag-release-workflow-design.md`

## 用户目标

维护者准备好版本后只需推送 `v<version>` 标签，即可自动测试、构建一次、通过 PyPI Trusted Publishing 发布，并用同一份经过校验的分发文件创建 GitHub Release。

## MVP 范围

1. 新增 `.github/workflows/release.yml`，仅由 `v*` tag push 触发。
2. 将项目版本升级为 `0.1.5`，同步公开版本与 Changelog。
3. Build Job 在执行项目代码前验证 tag/version，运行完整测试、build、Twine、精确文件校验和 wheel 独立安装/资源 smoke test。
4. Build Job 生成 `SHA256SUMS` 并只上传一次 artifact；PyPI 与 GitHub Release Job 分别下载、校验并消费它。
5. PyPI Job 使用 `pypi` Environment 和 OIDC Trusted Publishing；GitHub Release Job 在 PyPI 成功后用 `gh release create` 创建 release。
6. 增加无第三方依赖的发布校验脚本及 Workflow 契约测试，使用 `actionlint` 做 GitHub Actions 静态检查。
7. 将 `docs/releasing.md` 改为自动发布主路径，明确一次性外部配置、发布步骤与不可逆失败恢复。

## 实现顺序

1. 先增加发布校验脚本及其测试，覆盖 tag/version、Build 输出集合和下载后 artifact 集合。
2. 编写三 Job Workflow，所有外部 Action 固定完整 SHA，权限按 Job 最小化。
3. 增加 Workflow 契约测试，验证触发条件、依赖、artifact 流向、OIDC、`packages-dir`、权限和禁止项。
4. 升级 `pyproject.toml` 与包公开版本至 `0.1.5`，补充 Changelog。
5. 重写发布文档，并同步必要的架构/维护说明。
6. 运行校验脚本单测、项目全量测试、`actionlint`、构建、Twine、精确 artifact 检查及全新虚拟环境 wheel smoke test。
7. 完成任务归档并提交一个实现 commit；不创建或推送 `v0.1.5` 标签，不实际上传 PyPI 或创建 GitHub Release。

## 核心 tradeoff

- 不使用跨版本 concurrency：不同 tag 的 Run 相互隔离，避免 GitHub 只保留一个 pending Run 而丢失中间版本。
- PyPI 先于 GitHub Release：避免先展示未成功上传 PyPI 的版本，但接受 PyPI 成功、Release 失败时需要单独恢复 Release。
- 不使用 `skip-existing`：防止不可逆发布被静默掩盖；部分上传后必须提升版本，不使用长期 Token 人工补传。
- 增加小型标准库脚本，而不在 YAML 内堆叠复杂 shell：便于本地测试和维护，且不引入运行时依赖。

## 风险与验证

- Tag 与版本不一致必须在安装依赖、测试和发布前失败。
- 下载后的 artifact 必须拒绝额外文件、目录和符号链接，并通过 SHA-256 校验。
- Build Job 不拥有发布权限；PyPI Job 仅有 OIDC；Release Job 仅有 contents write。
- GitHub Environment 和 PyPI Trusted Publisher 属于仓库外配置，代码只能静态验证契约，首次真实发布仍是最终集成验证。

## 后续演进

只有在多人维护或发布频率显著提高后，再考虑人工审批 Environment、Draft Release 两阶段或专门的受控恢复 Workflow；本次不提前平台化。
