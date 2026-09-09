# 已归档任务

## [已完成] 设计并实现 0.1.2 Replay 体验升级
- 状态：已完成
- 目标：移除重复副作用勾选、实现实时请求更新，并支持 Edit & Replay
- 验收：交互规格经确认和评审；实时列表保留当前详情与编辑草稿；只读 method/URL 与可编辑 headers/text body 通过真实 HTTP replay；59 个测试、UI 静态检查、构建、Twine 和全新环境 wheel 安装通过

## [已完成] 发布 0.1.1 构建产物
- 状态：已完成
- 目标：将独立 SQLite 版本升级为 0.1.1，避免与 PyPI 已存在的 0.1.0 冲突
- 验收：版本元数据、Changelog 和发布文档一致；44 个测试、构建、Twine 与全新环境安装通过；dist 仅包含 0.1.1 wheel/sdist

## [已完成] 实现独立 SQLite 默认存储
- 状态：已完成
- 目标：将现有 Django ORM 存储替换为项目内独立 SQLite repository，实现零 migration、跨重载持久化
- 验收：44 个测试通过，覆盖业务库零写入、双进程初始化、锁超时、故障降级、真实 replay 和 correlation；wheel/sdist、Twine 与全新环境 wheel 安装验证通过

## [已完成] 设计独立 SQLite 默认存储
- 状态：已完成
- 目标：默认将 Inspector 记录保存在项目内独立 SQLite 文件中，不侵入 Django 业务数据库且可跨 runserver 重载保留
- 验收：配置、DDL、并发初始化、故障降级、replay 事务、资源加载和发布验收规格经用户确认及独立评审通过

## [已完成] 完成 django-http-inspector MVP 产品与技术设计
- 状态：已完成
- 目标：明确嵌入式 HTTP 捕获、原地址 replay、Inspector UI 与安全边界，并形成可评审设计文档
- 验收：设计覆盖用户目标、核心 tradeoff、MVP、技术路径、风险、演进方式和 ngrok :4040 风格 UI/UX

## [已完成] 制定 django-http-inspector MVP 1.0 实施计划
- 状态：已完成
- 目标：将已批准设计拆成可测试、可独立提交的实施步骤
- 验收：计划明确文件结构、开发顺序、每步验证方式、提交边界与实现风险

## [已完成] 实现 django-http-inspector MVP 1.0
- 状态：已完成
- 目标：完成 WSGI 请求捕获、隔离 Inspector UI、真实原地址 HTTP Replay 与安全边界
- 验收：30 个自动化测试通过，真实 HTTP replay 端到端关联成功，迁移无漂移，wheel/sdist 构建及元数据校验通过

## [已完成] 准备 PyPI 发布包
- 状态：已完成
- 目标：解决 distribution/import 名称冲突，完善发布元数据、构建验证和发布说明
- 验收：采用当前可用的 `django-http-inspector`，完成 distribution/import/app label 一致改名；30 个测试、干净构建、Twine 检查和全新环境 wheel 安装全部通过
