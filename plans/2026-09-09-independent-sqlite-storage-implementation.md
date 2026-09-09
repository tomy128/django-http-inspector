# 独立 SQLite 存储实施计划

日期：2026-09-09

依据：`docs/superpowers/specs/2026-09-09-independent-sqlite-storage-design.md`

## 目标

以标准库 SQLite repository 替代 Django ORM，使默认接入不需要 `INSTALLED_APPS` 和 migration，同时保留 capture、Inspector UI、真实原地址 replay 与 correlation 能力。

## 实施步骤

1. 建立存储数据对象与 SQLite repository：实现配置路径解析、version 1 DDL、初始化、短连接 CRUD、裁剪、Clear、外键删除和原子 correlation。
2. 将 capture、replay 和 Inspector UI 从 ORM 改为 repository 注入；实现 pending attempt 提交后发送与发送后更新失败的明确结果。
3. 将模板渲染改为包资源加独立 `Engine`/`locmem.Loader`，移除对 app discovery 与项目 `TEMPLATES` 的依赖。
4. 删除 `models.py`、`apps.py` 和 `migrations/`，调整测试 settings，确保业务数据库不产生 Inspector schema。
5. 重写存储、wrapper、UI、replay 和端到端测试，补充路径、持久化、并发初始化、版本错误、锁超时与故障降级覆盖。
6. 同步 README、架构、安全、replay、发布文档和原 MVP 设计中的旧 ORM 前提。
7. 运行完整测试、构建 wheel/sdist、Twine 检查，并在最小 settings 的全新虚拟环境安装 wheel 验证资源和独立建库。

## 提交边界

这是一次不可独立拆分发布的存储迁移：运行时代码、测试、文档和分发产物必须保持同一版本语义，因此完成全部验收后形成一个实现提交；设计提交保持独立可追踪。

## 风险控制

- 所有数据库事务在真实 HTTP replay 前关闭。
- 捕获存储失败不改变业务响应。
- 初始 attempt 未提交时禁止发送 replay。
- 不实现未验证的第二存储后端。
- 不上传 PyPI，不创建 tag；发布仍由用户执行。
