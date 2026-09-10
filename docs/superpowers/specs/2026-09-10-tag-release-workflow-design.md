# 标签驱动的 GitHub Release 与 PyPI 自动发布设计

日期：2026-09-10
状态：独立评审通过，待用户复核

## 1. 用户目标

维护者完成版本变更并推送 `v<version>` 标签后，GitHub Actions 自动测试、构建一次、通过 PyPI Trusted Publishing 上传，并创建带相同 wheel/sdist 的 GitHub Release。正常发布不再需要本地运行 Twine 或保管长期 PyPI API Token。

## 2. 核心取舍

采用 Build、PyPI、GitHub Release 三 Job 分离。相比单 Job，权限和失败位置清楚；相比 Draft Release 两阶段事务，维护成本更低。PyPI 成功后才创建 GitHub Release，避免 Release 页面宣称一个实际上未上传 PyPI 的版本。

GitHub 与 PyPI 无法形成原子事务：若 PyPI 成功而 GitHub Release 创建失败，PyPI 版本已不可撤销，维护者需要重新运行失败的 Release Job 或手动创建 Release。Workflow 不启用 `skip-existing`，避免重跑整个 Workflow 时把不同构建物误认为同一发布。

## 3. 触发与版本契约

文件为 `.github/workflows/release.yml`，只响应：

```yaml
on:
  push:
    tags:
      - "v*"
```

Build Job 在安装依赖和执行项目代码前使用 Python 3.12 标准库 `tomllib` 读取 `pyproject.toml`，要求 `GITHUB_REF_TYPE=tag`，并要求 `GITHUB_REF_NAME` 精确等于 `v` 加项目 version。`v0.1.5` 对应 `0.1.5`；缺 `v` 不触发，`v0.1.5-extra`、`v01.5` 或 tag/version 不一致均失败。Workflow 不修改版本、不创建或移动 tag。

首个由该 Workflow 发布的版本是 `0.1.5`（tag 为 `v0.1.5`）。已有 `v0.1.4` 标签保持不可变，不移动、不复用。

Workflow 不设置跨版本 `concurrency`。每个 tag 产生独立 Run 和独立 artifact，不同版本可以安全并行；PyPI 的版本不可覆盖语义提供最终保护。GitHub concurrency group 只保留一个等待任务，反而可能在连续推送三个标签时取消中间版本，因此不适合发布队列。

## 4. Build Job

Build Job 仅有 `contents: read`，使用 `ubuntu-latest`、固定完整提交 SHA 的 `actions/checkout`（`d23441a48e516b6c34aea4fa41551a30e30af803`，对应 v6，`persist-credentials: false`）和 `actions/setup-python`（`ece7cb06caefa5fff74198d8649806c4678c61a1`，对应 v6，Python 3.12）。执行：

1. 校验 tag/version 契约；
2. `python -m pip install -e ".[dev]"`；
3. `python tests/runtests.py`；
4. `python -m build`；
5. `python -m twine check dist/*`；
6. Python 脚本校验 `dist/` 恰好包含 `django_http_inspector-<version>.tar.gz` 与 `django_http_inspector-<version>-py3-none-any.whl`，没有额外 artifact；
7. 创建全新虚拟环境，仅安装刚构建的 wheel，验证公开包可导入、版本正确以及 Inspector 静态资源与模板随 wheel 安装；
8. 从 workspace 根目录执行 `sha256sum dist/* > SHA256SUMS`，使摘要条目使用 `dist/<filename>` 相对路径；
9. 固定完整提交 SHA 的 `actions/upload-artifact`（`043fb46d1a93c77aae656e7c1c64a875d1fc6a0a`，对应 v7）一次性上传 `dist/` 与 `SHA256SUMS`，artifact 名为 `python-package-distributions`，找不到文件时失败，保留 14 天。

测试与构建只发生一次。后续两个 Job 仅下载这份 artifact，不 checkout、不重新 build。

## 5. PyPI Job

`publish-pypi` 依赖 Build，运行于 GitHub Environment `pypi`。用户选择完全自动，因此 Environment 不设置 required reviewer。Job permissions 只声明：

```yaml
permissions:
  id-token: write
```

使用固定完整提交 SHA 的 `actions/download-artifact`（`3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c`，对应 v8）将 artifact 下载到 `release-artifact/`。校验步骤设置 `working-directory: release-artifact` 并执行 `sha256sum --check SHA256SUMS`，随后重新检查精确文件集合。固定完整提交 SHA 的 `pypa/gh-action-pypi-publish`（`dc37677b2e1c63e2034f94d8a5b11f265b73ba33`，release/v1）必须显式配置 `with: packages-dir: release-artifact/dist/`，发布到正式 PyPI。使用该 Action 默认启用的 PyPI provenance attestations；不传 username/password，不读取 repository secret，不启用 `skip-existing`。

PyPI 必须预先为 `django-http-inspector` 配置 Trusted Publisher：

```text
Owner:        tomy128
Repository:   django-http-inspector
Workflow:     release.yml
Environment:  pypi
```

OIDC publisher、仓库、Workflow 文件名或 Environment 任一不匹配时 Job 失败，不继续创建 GitHub Release。

## 6. GitHub Release Job

`publish-github-release` 同时依赖 Build 和 PyPI，只有二者成功才执行。Job permissions 只声明 `contents: write`。使用与 PyPI Job 相同、固定 SHA 的 download action 将同一 artifact 下载到 `release-artifact/`，先以 `working-directory: release-artifact` 验证 `SHA256SUMS`，再验证精确文件集合，然后通过 runner 内置 GitHub CLI：

```bash
gh release create "$GITHUB_REF_NAME" \
  release-artifact/dist/* \
  release-artifact/SHA256SUMS \
  --verify-tag \
  --title "$GITHUB_REF_NAME" \
  --generate-notes
```

命令使用 `GH_TOKEN: ${{ github.token }}`。`--verify-tag` 要求标签真实存在；Release Notes 由 GitHub 生成；wheel、sdist 与校验文件作为 assets 附加。已存在同名 Release 时失败，不静默覆盖资产。

## 7. 权限与供应链边界

- Workflow 顶层默认 `permissions: {}`，每个 Job 仅增加所需权限；
- OIDC 权限只存在于 PyPI Job，不授予 Build 或 GitHub Release Job；
- `contents: write` 只存在于 Release Job，不授予执行项目测试/build 的 Job；
- checkout 不保留 credentials；
- PyPI 发布 action 单独处于最小 Job，除 artifact 下载和完整性检查外不执行项目代码；
- 所有外部 Action 固定到经过核对的完整提交 SHA，并在行尾注释对应稳定版本；后续通过 Dependabot 或人工 PR 审核更新，不跟随可移动 tag；
- 建议配置 Repository Ruleset，限制 `v*` 标签的创建、更新和删除权限，只允许维护者发布。

完全自动模式意味着任何有权修改默认分支上的 Workflow 并创建匹配 tag 的人都可能触发发布。Trusted Publishing 不是代码审核或账户授权的替代品。

## 8. 验证与文档

“精确文件集合”定义为：`release-artifact/` 根目录恰好包含普通文件 `SHA256SUMS` 和目录 `dist/`，`dist/` 恰好包含当前版本的普通 wheel 与 sdist；拒绝额外文件、额外目录及符号链接。

仓库测试读取 Workflow 文本，验证触发模式、三 Job 依赖、tag/version 校验入口、artifact 单次上传/两次下载、完整 SHA 固定、摘要工作目录、PyPI `packages-dir`、无 password/secret/skip-existing、OIDC 与 contents 写权限不越界。使用 `actionlint` 验证 GitHub Actions 语义和表达式，而不只做通用 YAML 解析；最终 GitHub runner 是行为验证来源。

`docs/releasing.md` 改为自动发布主路径，保留手动构建检查作为故障排查方式，并列出：

1. PyPI Trusted Publisher 配置；
2. GitHub `pypi` Environment 创建：名称必须精确为 `pypi`，不设置 required reviewers 或 wait timer，并将部署来源限制为匹配 `v*` 的标签；
3. 推荐 `v*` 标签 Repository Ruleset；
4. 发布命令；
5. 失败恢复：Build 失败时修复代码、提升版本并创建新 tag，不移动已推送 tag；PyPI 在零文件上传前因 Environment、OIDC 或临时故障失败时，修复后只重跑同一次 Run 的 `publish-pypi` 及其依赖失败而未运行的 Release Job，继续消费原 artifact；PyPI 部分上传时禁止全量重跑或用 Token 人工补传，由维护者先在 PyPI 核实状态，然后提升版本重新发布；PyPI 已完整成功而 GitHub Release 失败时，只重跑同一次 Run 的 `publish-github-release`，或从该 Run 下载并验证 artifact 后手动创建 Release。任何路径都不移动标签、不重建该 Run 的 artifact、不覆盖或重复上传已存在文件。

## 9. 验收标准

- 只有 `v*` tag push 触发；branch push 与 PR 不发布；
- tag 与 `pyproject.toml` version 不一致时在任何发布前失败；
- 完整 tests、build、Twine、wheel 独立安装/资源检查和精确 dist 文件检查通过后才上传 artifact；
- PyPI 与 GitHub Release 下载后均通过 `SHA256SUMS` 验证，并消费同一次 Build 产生的文件；
- 连续推送三个不同版本标签时会产生三个独立 Run，不因 concurrency 丢失中间发布；
- PyPI 使用 Trusted Publishing，无长期 secret；
- GitHub Release 只在 PyPI 成功后创建，自动 notes 且附加同一 artifact；
- permissions 按 Job 最小化，Build 不具备发布权限；
- Workflow 通过 `actionlint`、仓库契约测试和项目完整测试；
- 恢复演练覆盖 PyPI 零上传后的同 Run 重跑、部分上传时禁止全量重跑，以及 GitHub Release 失败后的单 Job 重跑；
- 文档足够让 `tomy128/django-http-inspector` 一次配置后通过 `git push origin vX.Y.Z` 发布。

## 10. 非目标与后续演进

MVP 不自动 bump version、生成 changelog、创建 tag、不发布 TestPyPI、不做 Draft Release 事务、不使用 API Token、不自动覆盖或跳过已存在版本。

若实际发布频率或多人维护导致一致性问题，再考虑 protected environment 人工批准或 Draft Release 两阶段；当前优先最短、可审计且无长期密钥的发布路径。
