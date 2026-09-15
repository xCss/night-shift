# 项目状态

> 本文件跟踪夜班系统自身以及被托管项目的状态、待办与已完成事项。
> 每次夜班结束时更新。带日期；完成的条目移入"已完成"并保留，便于回溯。

---

## 夜班系统自身

**状态**：基础设施已建立（2026-09-11，夜班A）

- 目录结构：`memory/`、`logs/`、`handoff/` 已创建并写入初始文件。
- 长期约束与决策：见 `memory/long-term-memory.md`。

### 待办

- [x] 【P1】等人工确认：B/C/D 班次职责、是否自动 push → [2026-09-12，人工确认] 职责定案（A=记忆基建、B=棋手联赛、C=无聊发明、D=记录）；push 归出版署班次，A/B/C/D 只 commit 本地。当前无待人工确认事项。
- [x] 【P1】交接目录命名冲突 → [2026-09-11，夜班C] 已解决：`tools/shift_report.py` 默认输出目录改为 `handoff/`，与夜班A的目录约定对齐；人工若另有裁决可用 `--out` 覆盖。
- [x] 【P2】`tools/shift_report.py` 入库 → [2026-09-11，夜班C] commit `a80df5b`，含 15 项单元测试（`python -m unittest discover -s tests`）与 README 文档。
- [ ] 【P2】后续夜班持续检查记忆文件的重复/冲突/过期信息，本条为常设任务。→ [2026-09-12，夜班C] 已工具化：`tools/memory_check.py`（提交哈希校验/「待确认」事项汇总/未来日期，只读，exit 1 可接 CI），记忆检查职责归夜班A：A 值班时执行此检查（CI 中亦自动运行）。
- [ ] 【P3】shift_report.py 归属过滤：工具侧已完成（`--shift-tag`，commit `a862b6e`，逐提交重算 numstat）。**待办收窄为**：各班次提交信息带 `[A]/[B]/[C]/[D]` 前缀（夜班C自 2026-09-12 起已示范），不标记则该功能空转。
- [x] 【P3】默认窗口跨午夜漏提交 → [2026-09-11，夜班B] 已解决：无参数时取最近一次 23:05（夜班窗口起点，`DEFAULT_SINCE`）。
- [ ] 【P3】按班次配置章节集合：工具侧已完成（`--profile`/`--sections`，commit `a862b6e`，C 模板已登记）。**待办收窄为**：A/B/D 拿到各自协议权威模板后在 `tools/shift_report.py` 的 `PROFILES` 登记。
- [x] 【P3】CI 未实测 → [2026-09-12，出版署] push 后 Actions 真实执行。首跑起连续暴露两个问题并当场修复：`test_append_preserves_crlf_line_endings` 平台缺陷（通用换行转换使 CRLF 检测失灵，Windows 靠写出翻译侥幸通过、Linux 上整份文档被改写成 LF，commit `9de819e`）；浅克隆致 memory_check 哈希校验全误报（改 `fetch-depth: 0`，commit `43f5641`）。三跑 CI 绿（3.12/3.13 unittest + memory_check）。
- [x] 【P1】shift_report `--append` 无锁读改写 → [2026-09-12，夜班C] 已修复：O_CREAT|O_EXCL 锁文件+重试+陈旧锁（>60s）接管，写入临时文件后 os.replace 原子替换；原子写顺带修掉了 write_text 的 


 双重翻译隐患。新增 4 项测试含两进程真实并发竞态验证（69/69 通过）。
- [ ] 【P2】生成物写入非原子（shift_report 非 append 分支 / morning_report）：并发读可能拿到截断文档，致 memory_check 误报。修法同上（os.replace）。
- [ ] 【P2】空仓库（无提交）运行任一工具会裸 traceback（rev-parse HEAD / git log exit 128 未捕获）。修法：check=False + 降级提示。
- [ ] 【P3】morning_report 体检结论与失败明细脱节（子进程 stdout 被丢弃，体检失败时晨报看不出原因）；测试命令硬编码，宜加 --test 参数。
- [ ] 【P3】memory_check known_short_hashes 把 rev-list 的 "commit <hash>" 头行词收进已知集合（`commit` 字样可通过哈希校验）；解析跳过头行即可。
- [ ] 【P3】测试输出含 ``` 时破坏生成的 Markdown 围栏（auto_fill_tests / run_suite）；检测后改用四反引号。
- [ ] 【P3】filter_by_shift_tag 用 8 位哈希 git show，前缀歧义时静默少算；collect_commits 保留全哈希并告警。
- [x] 【P1】morning_report `--since 25:00` 崩溃、`--hours 0/-3` 错窗口 → [2026-09-12，夜班C] 已修复：改用 shift_report.parse_since 统一校验。
- [x] 【P2】append_to_handoff 读文档无 errors 容错 → [2026-09-12，夜班C] 已修复：errors="replace"。
- [x] 【P1】`site/sky.html` 整页空白 → [2026-09-15，出版署] 视觉检查发现：`night_sky.py` 模板调用 `esc()` 却从未定义，脚本在顶层 `filters.innerHTML` 处即抛 `esc is not defined`，星图（canvas）从未绘制，页面只剩标题与导航。已补 `esc` 定义（与其余页面同款转义表），并补回归测试断言页面必须定义 `esc`。
- [x] 【P2】sky 筛选按钮「未标记 未标记」标签重复 → [2026-09-15，出版署]`laneNames["未标记"]="未标记"` 自我映射所致；改为无别名时不追加，回归测试断言不再出现自我映射。
- [x] 【P1】`docs.html` 在 GitHub Pages 模式（选 `site/` 为根）下所有文档 404 → [2026-09-15，出版署] 视觉检查发现：`fetch("../" + path)` 跳出发布根，正文区永远空白（`file://` 亦被 CORS 拦）。改为生成时把正文内嵌进 `const CONTENT`，`openDoc` 只用内嵌正文；`file://`/`--serve`/Pages 三模式均可读。README 说明同步更正。
- [x] 【P2】`index.html` 文档入口 `href="../handoff/..."` 同类根逃逸 → [2026-09-15，出版署] `--serve`（仓库根）下可用，但 Pages 选 `site/` 为根时 404。改为深链 `docs.html#<路径>`，`openDoc` 支持 hash 直达。
- [x] 【P2】站点导航缺口：`index.html`/`history.html` 缺星图链接 → [2026-09-15，出版署] 星图页面此前无法从首页到达；三处生成器补齐六页两两互链，并加导航回归测试。
- [x] 【P3】驾驶舱文档入口含图书馆不收的生成物（晨报）→ [2026-09-15，出版署] `latest_files` 补上与 memory_check/night_docs 一致的 `morning-report` 排除规则；加「驾驶舱入口必须存在于图书馆清单」的跨模块一致性测试。
- [ ] 【P3】shift_report 已知可接受限制（夜班B第二次值班评审记录，暂不修）：`--append AUTO` 哨兵值与同名文件冲突；status/numstat 对带引号路径（路径含特殊字符时）显示失真。

### 已完成

- [2026-09-11] 夜班A首次值班：从零搭建记忆系统（memory/、logs/、handoff/、README 说明），完成首次交班。
- [2026-09-11] 夜班C值班：创建并入库交班记录生成器 `tools/shift_report.py`（15 项单元测试通过），对齐 `handoff/` 目录约定，补齐「建议C关注」章节，生成本班交班记录。
- [2026-09-11] 夜班B值班：章节对齐 AGENTS.md 交班字段（新增今晚比赛/冠军方案/未完成问题/下一轮建议，commit `359b47d`）；修复跨午夜 `--since` 负窗口数据丢失 bug（`befa1a5`、`427013b`，语义统一为"该时刻最近一次出现"）；新增 GitHub Actions CI 在 push/PR 时自动跑测试（`16e4535`）。测试增至 19 项，全部通过。
- [2026-09-11] 夜班C续班：新增开工自检工具 `tools/shift_start.py`（并发班次活动检测，`4a077b7`）；实现 `shift_report.py --append` 直接产出持续交接文档（`9dba3b8`，响应夜班B建议）；修复非 ASCII 文件名转义显示（`8554444`）；建立 `handoff/night-shift-c-handoff.md` 持续交班文档。测试增至 28 项，全部通过。
- [2026-09-11] 夜班B第二次值班：评审子代理产出 15 项缺陷清单后修复两批——参数校验类（`--since` 越界、`--hours` 0/负数、互斥组、标题文件名净化、`--warn-minutes` 真实参与判定、AM/MM 漏报，`f1f26e9`）与数据完整性类（`--append` 围栏感知/页脚分隔线/CRLF 保留，`9b704f3`）、numstat 重命名展开与仓库根路径基准（`78ca280`）。测试增至 45 项，全部通过。

## 被托管的项目

（暂无。夜班系统目前只维护自身；一旦开始跟踪其他项目，在此登记项目名、路径限制说明与状态摘要。）

---

- [2026-09-12] 夜班C续班收尾：`--shift-tag` 归属过滤与 `--profile`/`--sections` 章节配置入库（`a862b6e`），两项 P3 收窄为纯约定问题；建立 `logs/2026-09-12.md`。
- [2026-09-12] 夜班C续班：发明 site/ 可视化家族（驾驶舱/图书馆/大事记/出勤表/星图五页互链）+ 夜班模拟器 `site/game.html`（首夜真实事件改编文字冒险，含完美/事故双结局）（驾驶舱 night_web + 图书馆 night_docs + 大事记 night_history + 出勤表 night_shifts + 星图 night_sky，全部 HTML+JS、相对路径、互链，GitHub Pages 选 site/ 即上线） `site/`（驾驶舱 night_web + 图书馆 night_docs + 大事记 night_history，全部 HTML+JS、相对路径、互链，GitHub Pages 选 site/ 目录即上线） `tools/night_docs.py`（Markdown 聚合阅读器，侧栏导航+标题过滤+客户端渲染）与夜班驾驶舱 `tools/night_web.py`（HTML+JS 静态面板，泳道时间轴/健康度/待确认卡片，GitHub Pages 可用，经浏览器截图验收） `tools/night_web.py`（HTML+JS 静态面板，泳道时间轴/健康度/待确认卡片，GitHub Pages 可用，经浏览器截图验收）与 `tools/morning_report.py` 晨报生成器（夜班→人类交付闭环，`27d5278`）与 `tools/memory_check.py` 记忆体检工具（`4c6893b`，7 项测试）；`shift_start.py` 增加远程同步状态显示（`9314793`）。

*最后更新：2026-09-11 夜班B（第二次值班）*
