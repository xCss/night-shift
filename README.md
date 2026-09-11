# night-shift

夜班持续工作系统的记忆仓库。运行协议见 [AGENTS.md](AGENTS.md)。

## 目录结构

| 路径 | 用途 |
| --- | --- |
| `memory/long-term-memory.md` | 长期记忆：长期约束、重要决策、待人工确认事项 |
| `memory/project-status.md` | 项目状态：待办、已完成事项 |
| `logs/` | 按日期的夜班工作日志（`YYYY-MM-DD.md`） |
| `handoff/` | 班次交接记录（A/B/C/D） |
| `tools/` | 夜班自动化工具 |
| `tests/` | 工具的单元测试 |

## 工具

### `tools/shift_report.py` — 交班记录生成器

自动采集本班次的 git 活动（提交、改动文件、行数、未提交状态），按协议固定
章节生成交班记录 Markdown，默认写入 `handoff/`。判断类章节（今晚发现、
今晚比赛、冠军方案、今晚发明、未完成问题、最有价值成果、下一步、
下一轮建议、建议A/B/C/D）留为 TODO，由人或 AI 补全。

```bash
python tools/shift_report.py --title "夜班C"            # 覆盖最近一次 23:05 起（夜班窗口起点）
python tools/shift_report.py --hours 8 --title "夜班C"  # 覆盖最近 8 小时
python tools/shift_report.py --test "python -m unittest discover -s tests"  # 自动跑测试并写入记录
python tools/shift_report.py --stdout                    # 只打印不写文件
python tools/shift_report.py --append --title "夜班C"    # 追加进持续交接文档
```

- `--since "20:30"` 取该时刻**最近一次出现**：夜班跨午夜（23:05–08:05），早上生成记录时写 `"23:05"` 指昨夜的 23:05；`--out` 只接受仓库内相对路径（默认 `handoff`）。
- `--append` 把本次记录作为最新章节插入 `handoff/night-shift-<x>-handoff.md`（按 `--title` 中的班次字母推导，也可显式给相对路径），与夜班A确立的"单文件持续更新"交班约定一致；不加 `--append` 则新建按日期的独立文件。
- `--shift-tag C` 只统计提交信息以 `[C]` 开头的提交（班次归属过滤，约定落地后即用即生效；提交不带标记时结果为空）。
- `--profile C` 按预置的班次协议章节渲染（默认是各班次协议的并集）；`--sections "a,b"` 可显式指定章节。其他班次拿到权威模板后在 `tools/shift_report.py` 的 `PROFILES` 登记。
- 同一时段重复生成不覆盖旧记录，追加序号。
- 仅依赖 Python 3 标准库和 git。

### `tools/shift_start.py` — 开夜班自检

夜班系统有多名班次并发操作同一个仓库（2026-09-11 夜间实际发生过文件踩踏）。
开工时先运行，回答两个问题：仓库现在什么状态？是否有并行班次正在工作？

```bash
python tools/shift_start.py                  # 只读，不改任何文件
python tools/shift_start.py --warn-minutes 30
```

最后提交距今不足阈值（默认 15 分钟）或工作区不干净时会给出并发警告。

## 使用约定

- 只记录具有长期价值的信息，不凭空创造事实；不确定的内容标注【待确认】。
- 每次夜班结束前：更新项目状态、写当日日志、更新交班记录、确认 Git 状态。
- 不在没有必要的情况下制造 Commit。

## 测试

```bash
python -m unittest discover -s tests
```

测试在临时目录创建真实 git 仓库验证采集逻辑，不触碰本仓库状态。
