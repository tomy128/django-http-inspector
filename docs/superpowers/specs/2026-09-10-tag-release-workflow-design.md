# 标签驱动的 GitHub Release 与 PyPI 自动发布设计

日期：2026-09-10
状态：已由用户确认，待独立评审

## 1. 用户目标

维护者完成版本变更并推送 `v<version>` 标签后，GitHub Actions 自动测试、构建一次、通过 PyPI Trusted Publishing 上传，并创建带相同 wheel/sdist 的 GitHub Release。正常发布不再需要本地运行 Twine 或保管长期 PyPI API Token。

## 2. 核心取舍

采用 Build、PyPI、GitHub Release 三 Job 分离。相比单 Job，权限和失败位置清楚；相比 Draft Release 两阶段事务，维护成本更低。PyPI 成功后才创建 GitHub Release，避免 Release 页面宣称一个实际上未上传 PyPI 的版本。

GitHub 与 PyPI 无法形成原子事务：若 PyPI 成功而 GitHub Release 创建失败，PyPI 版本已不可撤销，维护者需要重新运行失败的 Release Job或手动创建 Release。Workflow 不启用 `skip-existing`，避免重跑整个 workflow 时把不同构建物误认为同一发布。

## 3. 触发与版本契约

文件为 `.github/workflows/release.yml`，只响应：

```yaml
on:
  push:
    tags:
      - "v*"
```

Build Job 在安装和构建前使用 Python 3.12 标准库 `tomllib` 读取 `pyproject.toml`，要求 tag 符合 `v` 加项目 version 的精确形式。`v0.1.4` 对应 `0.1.4`；缺 `v` 不触发，`v0.1.4-extra`、`v01.4` 或 tag/version 不一致均失败。Workflow 不修改版本、不创建或移动 tag。

同一 tag 使用 `concurrency.group` 串行执行，`cancel-in-progress: false`，避免发布任务被后续事件取消。

## 4. Build Job

Build Job 仅有 `contents: read`，使用 `ubuntu-latest`、`actions/checkout@v6`（`persist-credentials: false`）和 `actions/setup-python@v6`（Python 3.12）。执行：

1. `python -m pip install -e ".[dev]"`；
2. tag/version 精确校验；
3. `python tests/runtests.py`；
4. `python -m build`；
5. `python -m twine check dist/*`；
6. Python 脚本校验 `dist/` 恰好包含 `django_http_inspector-<version>.tar.gz` 与 `django_http_inspector-<version>-py3-none-any.whl`，没有额外 artifact；
7. `actions/upload-artifact@v5` 上传为 `python-package-distributions`，找不到文件时失败，并设置有限 retention。

测试与构建只发生一次。后续两个 Job仅下载这份 artifact，不 checkout、不重新 build。

## 5. PyPI Job

`publish-pypi` 依赖 Build，运行于 GitHub Environment `pypi`。用户选择完全自动，因此 Environment 不设置 required reviewer。Job permissions 只声明：

```yaml
permissions:
  id-token: write
```

使用 `actions/download-artifact@v6` 将 artifact 下载到 `dist/`，再使用 `pypa/gh-action-pypi-publish@release/v1` 默认发布到正式 PyPI。不传 username/password，不读取 repository secret，不启用 `skip-existing`。

PyPI 必须预先为 `django-http-inspector` 配置 Trusted Publisher：

```text
Owner:        tomy128
Repository:   django-http-inspector
Workflow:     release.yml
Environment:  pypi
```

OIDC publisher、仓库、workflow 文件名或 environment 任一不匹配时 Job 失败，不继续创建 GitHub Release。

## 6. GitHub Release Job

`publish-github-release` 同时依赖 Build 和 PyPI，只有二者成功才执行。Job permissions 只声明 `contents: write`。下载同一 artifact 到 `dist/`，通过 runner 内置 GitHub CLI：

```bash
gh release create "$GITHUB_REF_NAME" dist/* \
  --verify-tag \
  --title "$GITHUB_REF_NAME" \
  --generate-notes
```

命令使用 `GH_TOKEN: ${{ github.token }}`。`--verify-tag` 要求标签真实存在；Release Notes 由 GitHub 生成；wheel/sdist 作为 assets 附加。已存在同名 Release 时失败，不静默覆盖资产。

## 7. 权限与供应链边界

- Workflow 顶层默认 `permissions: {}`，每个 Job仅增加所需权限；
- OIDC 权限只存在于两步发布 Job，不授予 Build 或 GitHub Release Job；
- `contents: write` 只存在于 Release Job，不授予执行项目测试/build 的 Job；
- checkout 不保留 credentials；
- PyPI 发布 action 单独处于最小 Job，除 artifact 下载外不执行项目代码；
- 使用官方 GitHub actions 的当前稳定 major 与 PyPA 官方发布 action；MVP 不引入第三方 Release action；
- 建议配置 `v*` tag protection，只允许维护者创建或修改发布标签。

完全自动模式意味着任何有权修改默认分支上的 workflow 并创建匹配 tag 的人都可能触发发布。Trusted Publishing 不是代码审核或账户授权的替代品。

## 8. 验证与文档

仓库测试读取 workflow 文本，验证触发模式、三 Job依赖、tag/version 校验入口、artifact 单次上传/两次下载、无 password/secret/skip-existing、OIDC 与 contents 写权限不越界。使用本机可用 YAML parser 做语法检查；最终 GitHub runner 是行为验证来源。

`docs/releasing.md` 改为自动发布主路径，保留手动构建检查作为故障排查方式，并列出：

1. PyPI Trusted Publisher 配置；
2. GitHub `pypi` Environment 创建；
3. 推荐 tag protection；
4. 发布命令；
5. PyPI 成功而 Release 失败时只重跑失败 Job或手动创建 Release，不重建/重传同一 PyPI 版本。

## 9. 验收标准

- 只有 `v*` tag push 触发；branch push 与 PR 不发布；
- tag 与 `pyproject.toml` version 不一致时在任何发布前失败；
- 完整 tests、build、Twine 和精确 dist 文件检查通过后才上传 artifact；
- PyPI 使用 Trusted Publishing，无长期 secret；
- GitHub Release 只在 PyPI 成功后创建，自动 notes 且附加同一 artifact；
- permissions 按 Job最小化，build 不具备发布权限；
- workflow 静态检查和项目完整测试通过；
- 文档足够让 `tomy128/django-http-inspector` 一次配置后通过 `git push origin vX.Y.Z` 发布。

## 10. 非目标与后续演进

MVP 不自动 bump version、生成 changelog、创建 tag、不发布 TestPyPI、不做 Draft Release 事务、不使用 API Token、不自动覆盖或跳过已存在版本。

若实际发布频率或多人维护导致一致性问题，再考虑 protected environment 人工批准、Draft Release 两阶段或 artifact attestations；当前优先最短、可审计且无长期密钥的发布路径。
