# django-http-inspector 0.1.6 Release 修复实施计划

日期：2026-09-10

依据：`docs/superpowers/specs/2026-09-10-release-repository-fix-016-design.md`

## 步骤

1. 在 GitHub Release 命令中增加 `--repo "$GITHUB_REPOSITORY"`，保留 Release Job 无 checkout。
2. 扩展 Workflow 契约测试，断言显式仓库参数和 Release Job 无 checkout。
3. 将 README 固定宽高 HTML 图片改成标准 Markdown 图片。
4. 将 `pyproject.toml`、公开 `__version__`、Changelog 和发布文档同步至 0.1.6。
5. 运行完整测试、actionlint、编译、0.1.6 build、Twine、精确 dist 校验和全新环境 wheel smoke test。
6. 归档任务并创建单一实现提交；不创建 tag、不推送、不调用远端发布 API。

## 验收

新的 `v0.1.6` Run 能在没有 `.git` 的 Release Job 中明确定位 `tomy128/django-http-inspector`；PyPI/Release 权限和 artifact 流程保持不变；README 图片不声明固定宽高。
