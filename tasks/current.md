# 当前任务

## [进行中] 发布 0.1.6 Release 修复
- 状态：进行中
- 目标：修复无 checkout 的 GitHub Release 创建失败，并让 README 截图保持比例自适应
- 验收：Release 命令显式指定仓库；README 无固定图片尺寸；0.1.6 版本、测试、Workflow 静态检查、构建和全新安装验证通过

### Brainstorming 检查项
- [x] 探索失败日志、Workflow、README 和仓库状态
- [x] 判断无需视觉辅助
- [x] 用户明确确认最小修复方案并授权不中断实施
- [x] 比较方案：checkout、显式 --repo、独立恢复 Workflow；采用显式 --repo
- [x] 设计：保持 Release Job 无 checkout，只修复仓库寻址；Markdown 图片原生自适应
- [x] 写入并独立评审简短规格
- [x] 制定实施计划
- [ ] 实现与验证
