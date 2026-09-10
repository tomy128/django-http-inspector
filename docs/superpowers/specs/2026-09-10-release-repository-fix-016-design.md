# django-http-inspector 0.1.6 Release 修复设计

日期：2026-09-10
状态：用户已确认，独立评审通过

## 用户目标

修复 `publish-github-release` 在没有 `.git` checkout 时无法判断仓库的错误，并避免 README 截图在 PyPI 被固定宽高拉伸。

## 方案与取舍

保留 Release Job 不 checkout 源码的安全边界，在 `gh release create` 中增加 `--repo "$GITHUB_REPOSITORY"`。相比增加 checkout，这只提供缺失的仓库身份，不执行项目代码、不扩大权限，也不增加网络步骤。相比新增恢复 Workflow，当前只需修复以后版本的正常发布路径；已发布的 0.1.5 Release 可独立人工补建。

README 将带 `width`/`height` 的 HTML `<img>` 改为标准 Markdown 图片。由 GitHub/PyPI 容器决定可用宽度，浏览器按图片固有宽高比缩放，不增加可能被 PyPI sanitizer 移除的 style 属性。

## MVP 范围

- Workflow 增加显式 `--repo "$GITHUB_REPOSITORY"`；
- 契约测试锁定该参数，并继续保证 Release Job 不 checkout；
- README 图片移除固定尺寸；
- 项目版本、Changelog 和发布文档升级至 0.1.6；
- 运行完整测试、actionlint、build、Twine 和 wheel 独立安装验证。

## 风险与恢复

`GITHUB_REPOSITORY` 是 GitHub Actions 自动提供的 `owner/repository`，并由临时 `GITHUB_TOKEN` 的 `contents: write` 权限认证。0.1.5 已存在于 PyPI，不能重新执行完整发布；本次代码只用于新的 `v0.1.6` 标签。实现不创建标签、不推送远端、不调用 GitHub Release API。
