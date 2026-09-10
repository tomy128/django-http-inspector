# 当前任务

## [进行中] 自动化 GitHub Release 与 PyPI 发布
- 状态：进行中
- 目标：推送版本标签后自动测试、构建、创建 GitHub Release 并通过 Trusted Publishing 上传 PyPI
- 验收：触发与版本校验、最小权限、artifact 单次构建、GitHub Release、PyPI OIDC、失败语义和配置文档经确认；Workflow 可静态验证并提交

### Brainstorming 检查项
- [x] 探索打包、发布文档、仓库状态和现行官方指南
- [x] 判断无需视觉辅助
- [x] 确认标签格式与版本一致性策略
- [x] 确认发布审批语义
- [x] 比较 2–3 种 Workflow 方案
- [x] 分节确认设计
- [x] 编写并提交设计规格
- [x] 独立评审规格并修正
- [ ] 用户复核书面规格
- [ ] 制定实施计划
- [ ] 实现与验证
