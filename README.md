# night-shift

夜班持续工作系统的记忆仓库。运行协议见 [AGENTS.md](AGENTS.md)。

## 目录结构

| 路径 | 用途 |
| --- | --- |
| `memory/long-term-memory.md` | 长期记忆：长期约束、重要决策、待人工确认事项 |
| `memory/project-status.md` | 项目状态：待办、已完成事项 |
| `logs/` | 按日期的夜班工作日志（`YYYY-MM-DD.md`） |
| `handoff/` | 班次交接记录（A/B/C/D） |

## 使用约定

- 只记录具有长期价值的信息，不凭空创造事实；不确定的内容标注【待确认】。
- 每次夜班结束前：更新项目状态、写当日日志、更新交班记录、确认 Git 状态。
- 不在没有必要的情况下制造 Commit。
