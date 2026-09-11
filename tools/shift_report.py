#!/usr/bin/env python3
"""夜班交班记录生成器。

自动化 AGENTS.md 夜班协议中最重复的部分：每次班次结束都要产出一份固定格式的
交班记录，章节与协议要求的字段对齐（比赛/冠军方案/测试/失败/未完成问题/
下一轮建议/建议A-D…）。

本工具扫描仓库的 git 活动，把可以自动采集的部分（提交、改动文件、行数统计、
未提交状态、测试结果）直接填好，判断类的部分留成待填占位符。

用法：
    python tools/shift_report.py                     # 覆盖最近一次 23:05（夜班窗口起点）以来
    python tools/shift_report.py --hours 8           # 覆盖最近 8 小时
    python tools/shift_report.py --since "23:05"     # 覆盖最近一次 23:05 以来（跨午夜安全）
    python tools/shift_report.py --test "python -m pytest -q"
    python tools/shift_report.py --out handoff --title "夜班C：无聊发明"
    python tools/shift_report.py --append --title "夜班C"   # 追加进持续交接文档

仅依赖标准库；只在 git 仓库内运行，输出默认写入 handoff/ 目录（与仓库
交接目录约定一致）。
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
import sys
from pathlib import Path

SECTIONS = [
    "今晚发现",
    "今晚比赛",
    "冠军方案",
    "今晚完成",
    "今晚发明",
    "实际修改",
    "实验",
    "测试",
    "失败",
    "未完成问题",
    "最有价值成果",
    "下一步",
    "下一轮建议",
    "建议A关注",
    "建议B关注",
    "建议C关注",
    "建议D记录",
]

# 判断类章节：工具无法替人下结论，生成待填占位符
JUDGEMENT_SECTIONS = {"今晚发现", "今晚比赛", "冠军方案", "今晚发明",
                      "未完成问题", "最有价值成果", "下一步", "下一轮建议",
                      "建议A关注", "建议B关注", "建议C关注", "建议D记录"}

# AGENTS.md 夜班B交班记录协议明确要求的字段，缺一不可；测试据此校验
PROTOCOL_REQUIRED_SECTIONS = ["今晚比赛", "冠军方案", "未完成问题",
                              "下一轮建议", "建议C关注", "建议D记录"]


def run_git(repo: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        # core.quotepath=off：非 ASCII 文件名（如中文）按原样输出，不转义
        ["git", "-c", "core.quotepath=off", "-C", str(repo), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 失败: {result.stderr.strip()}")
    return result.stdout


def run_cmd(cmd: str, repo: Path, timeout: int = 600) -> tuple[int, str]:
    """在仓库目录运行任意命令（通常用于测试），返回 (returncode, 输出)。"""
    try:
        result = subprocess.run(
            cmd, shell=True, cwd=repo,
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout,
        )
        return result.returncode, (result.stdout + result.stderr).strip()
    except subprocess.TimeoutExpired:
        return 124, f"命令超时（>{timeout}s）: {cmd}"


def parse_since(args: argparse.Namespace, now: dt.datetime | None = None) -> dt.datetime:
    now = now or dt.datetime.now()
    if args.since:
        try:
            hh, mm = map(int, args.since.split(":"))
        except ValueError:
            sys.exit(f"--since 需要 HH:MM 格式，收到: {args.since!r}")
        return most_recent(hh, mm, now)
    if args.hours:
        return now - dt.timedelta(hours=args.hours)
    # 夜班工具的默认窗口 = 夜班窗口起点（AGENTS.md：23:05–08:05）。
    # 早上生成记录时取昨夜 23:05，避免"当天 00:00"漏掉前半夜的提交。
    return most_recent(*DEFAULT_SINCE, now)


# 夜班窗口起点（AGENTS.md：正常工作 23:05–08:05）
DEFAULT_SINCE = (23, 5)


def most_recent(hh: int, mm: int, now: dt.datetime) -> dt.datetime:
    """HH:MM 在 now 之前最近一次出现的时刻（跨午夜安全）。"""
    since = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if since > now:
        since -= dt.timedelta(days=1)
    return since


def git_since_iso(moment: dt.datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%S")


def collect_commits(repo: Path, since_iso: str) -> list[dict]:
    out = run_git(repo, "log", f"--since={since_iso}",
                  "--pretty=format:%H%x1f%an%x1f%ad%x1f%s",
                  "--date=iso")
    commits = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split("\x1f")
        if len(parts) == 4:
            commits.append({
                "hash": parts[0][:8], "author": parts[1],
                "date": parts[2], "subject": parts[3],
            })
    return commits


def _parse_numstat_text(out: str) -> tuple[list[str], int, int]:
    """解析 git log --numstat 输出，返回 (文件列表, 新增行, 删除行)。"""
    files: dict[str, None] = {}
    added = deleted = 0
    for line in out.splitlines():
        line = line.strip()
        if not line or line == "\x00":
            continue
        match = re.match(r"^(\d+|-)\t(\d+|-)\t(.+)$", line)
        if not match:
            continue
        a, d, path = match.groups()
        files[path] = None
        if a != "-":
            added += int(a)
        if d != "-":
            deleted += int(d)
    return sorted(files), added, deleted


def collect_numstat(repo: Path, since_iso: str) -> tuple[list[str], int, int]:
    out = run_git(repo, "log", f"--since={since_iso}", "--numstat",
                  "--pretty=format:%x00")
    return _parse_numstat_text(out)


def _parse_status_text(out: str) -> tuple[list[str], list[str]]:
    """解析 git status --porcelain 输出，返回 (已暂存, 未提交)。"""
    staged, unstaged = [], []
    for line in out.splitlines():
        if not line.strip():
            continue
        status, path = line[:2], line[3:].strip()
        if status[0] not in (" ", "?"):
            staged.append(f"{status} {path}")
        if status[-1] != " " or status == "??":
            unstaged.append(f"{status} {path}")
    return staged, unstaged


def collect_status(repo: Path) -> tuple[list[str], list[str]]:
    return _parse_status_text(run_git(repo, "status", "--porcelain"))


def collect_branch_head(repo: Path) -> tuple[str, str]:
    branch = run_git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()
    head = run_git(repo, "rev-parse", "--short", "HEAD").strip()
    return branch, head


def demote_headings(markdown: str) -> str:
    """把二级及以下标题整体降一级，用于把整份记录嵌入持续交接文档。"""
    lines = []
    for line in markdown.splitlines():
        if re.match(r"^#{2,6} ", line):
            line = "#" + line
        lines.append(line)
    return "\n".join(lines)


def derive_handoff_path(title: str, out_dir: Path) -> Path | None:
    """从班次标题推导 A 式持续交接文档路径（夜班C → night-shift-c-handoff.md）。

    标题中识别不出班次字母时返回 None，需调用方要求显式给出文件。
    """
    match = re.search(r"夜班([A-Za-z])", title)
    if not match:
        return None
    letter = match.group(1).lower()
    return out_dir / f"night-shift-{letter}-handoff.md"


def append_to_handoff(target: Path, markdown: str, heading: str) -> bool:
    """把本次记录作为新章节并入持续交接文档，返回是否新建了文件。

    文件不存在：直接写入完整文档（含 H1 头）。
    文件已存在：在文件头与第一个既有章节之间插入新章节（最新在最上，
    与夜班A确立的持续更新约定一致），既有内容原样保留。嵌入时生成
    内容的标题整体降一级，H1 行被章节标题取代。
    """
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(markdown, encoding="utf-8")
        return True

    demoted = demote_headings(markdown).splitlines()
    idx = 0
    if demoted and demoted[0].startswith("# ") and not demoted[0].startswith("##"):
        idx = 1  # 原文档 H1（# 夜班X 交班记录）被 heading 取代
    while idx < len(demoted) and not demoted[idx].strip():
        idx += 1
    body = "\n".join(demoted[idx:]).strip()

    lines = target.read_text(encoding="utf-8").splitlines()
    insert_at = len(lines)
    for i, line in enumerate(lines):
        if line.startswith("## "):
            insert_at = i
            break
    block = [heading, "", body, "", "---", ""]
    lines[insert_at:insert_at] = block
    if not lines or lines[-1].strip():
        lines.append("")
    target.write_text("\n".join(lines), encoding="utf-8")
    return False


def auto_fill_changes(commits: list[dict], files: list[str],
                      added: int, deleted: int,
                      staged: list[str], unstaged: list[str]) -> str:
    lines = []
    if commits:
        lines.append(f"- {len(commits)} 个提交：")
        for c in commits:
            lines.append(f"  - `{c['hash']}` {c['subject']}（{c['author']}）")
    else:
        lines.append("- 本班次无提交")
    if files:
        lines.append(f"- 触及 {len(files)} 个文件（+{added} / -{deleted} 行）：")
        lines += [f"  - `{f}`" for f in files]
    else:
        lines.append("- 无文件改动")
    if staged:
        lines.append(f"- **未提交（已暂存）**：{len(staged)} 项：")
        lines += [f"  - `{s}`" for s in staged]
    if unstaged:
        lines.append(f"- **未提交（工作区/未跟踪）**：{len(unstaged)} 项：")
        lines += [f"  - `{s}`" for s in unstaged]
    if not staged and not unstaged:
        lines.append("- 工作区干净，无未提交改动")
    return "\n".join(lines)


def auto_fill_tests(test_cmd: str | None, repo: Path) -> str:
    if not test_cmd:
        return ("- （工具未运行测试）可用 `--test \"命令\"` 让工具自动执行并记录；"
                "手动跑过的测试记在 TODO 里")
    code, output = run_cmd(test_cmd, repo)
    verdict = "✅ 通过" if code == 0 else f"❌ 失败（exit {code}）"
    tail = "\n".join(output.splitlines()[-20:]) if output else "（无输出）"
    lines = [
        f"- 命令：`{test_cmd}`",
        f"- 结果：{verdict}",
        "- 输出（末 20 行）：",
        "  ```",
        *[f"  {l}" for l in tail.splitlines()],
        "  ```",
    ]
    return "\n".join(lines)


def render(repo: Path, repo_name: str, shift_title: str, moment: dt.datetime,
           since: dt.datetime, branch: str, head: str,
           commits: list[dict], files: list[str], added: int, deleted: int,
           staged: list[str], unstaged: list[str],
           test_cmd: str | None) -> str:
    buf = [f"# {shift_title} 交班记录", ""]
    buf.append(f"- 班次日期：{moment:%Y-%m-%d %H:%M}")
    buf.append(f"- 覆盖时段：{since:%Y-%m-%d %H:%M} 起")
    buf.append(f"- 仓库：`{repo_name}`（分支 `{branch}` @ `{head}`）")
    buf.append("")

    done_lines = [f"- `{c['hash']}` {c['subject']}" for c in commits] or \
        ["- 本班次无提交（TODO：列出完成的事项，即使未提交）"]
    auto = {
        "今晚完成": "\n".join(done_lines),
        "实际修改": auto_fill_changes(
            commits, files, added, deleted, staged, unstaged),
        "测试": auto_fill_tests(test_cmd, repo),
    }

    for section in SECTIONS:
        buf.append(f"## {section}")
        buf.append("")
        if section in auto:
            buf.append(auto[section])
        elif section == "失败":
            buf.append("- TODO（本班次遇到的失败/回滚/未成功尝试，若无则写「无」）")
        else:
            buf.append("- TODO")
        buf.append("")

    buf.append("---")
    buf.append(f"*由 tools/shift_report.py 自动生成于 {moment:%Y-%m-%d %H:%M:%S}，"
               "TODO 段落需人工补全。*")
    return "\n".join(buf) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="生成夜班交班记录")
    parser.add_argument("--since", help="起点时间 HH:MM（取该时刻最近一次出现，支持跨午夜班次）")
    parser.add_argument("--hours", type=float, help="覆盖最近 N 小时")
    parser.add_argument("--out", default="handoff",
                        help="输出目录（默认 handoff/，与仓库交接目录一致）")
    parser.add_argument("--title", default="夜班", help="班次标题（如：夜班C）")
    parser.add_argument("--test", help="班次结束前运行的测试命令")
    parser.add_argument("--stdout", action="store_true",
                        help="只打印不写文件")
    parser.add_argument("--append", nargs="?", const="AUTO", default=None,
                        metavar="FILE",
                        help=("追加到持续交接文档而不是新建按日期文件："
                              "不带值时按 --title 推导（夜班C → "
                              "night-shift-c-handoff.md），也可显式给相对路径"))
    args = parser.parse_args()

    repo = Path.cwd()
    try:
        run_git(repo, "rev-parse", "--git-dir")
    except RuntimeError:
        sys.exit("当前目录不是 git 仓库，工具无法工作。")

    moment = dt.datetime.now()
    since = parse_since(args)
    since_iso = git_since_iso(since)

    branch, head = collect_branch_head(repo)
    commits = collect_commits(repo, since_iso)
    files, added, deleted = collect_numstat(repo, since_iso)
    staged, unstaged = collect_status(repo)

    markdown = render(
        repo, repo.name, args.title, moment, since, branch, head,
        commits, files, added, deleted, staged, unstaged, args.test,
    )

    if args.stdout:
        print(markdown)
        return

    out_dir = (repo / args.out).resolve()
    try:
        out_dir.relative_to(repo.resolve())
    except ValueError:
        sys.exit(f"--out 必须是仓库内的相对路径，收到: {args.out!r}")
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.append:
        if args.append == "AUTO":
            target = derive_handoff_path(args.title, out_dir)
            if target is None:
                sys.exit(f"--append 无法从标题 {args.title!r} 推导班次文档，"
                         "请用 --append <相对路径> 显式指定。")
        else:
            target = (repo / args.append).resolve()
            try:
                target.relative_to(repo.resolve())
            except ValueError:
                sys.exit(f"--append 必须是仓库内的相对路径，收到: {args.append!r}")
        created = append_to_handoff(
            target, markdown, f"## {moment:%Y-%m-%d} {args.title}")
        action = "已创建" if created else "已追加新章节"
        print(f"交班记录{action}: {target.relative_to(repo)}")
        print(f"其中 {len(JUDGEMENT_SECTIONS)} 个判断类章节为 TODO，需人工补全。")
        return

    filename = f"{moment:%Y-%m-%d}-{args.title.replace('：', '-')}.md"
    out_path = out_dir / filename
    # 同一时段重复生成时不覆盖旧记录
    counter = 1
    while out_path.exists():
        counter += 1
        out_path = out_dir / f"{out_path.stem}-{counter}{out_path.suffix}"
    out_path.write_text(markdown, encoding="utf-8")
    print(f"交班记录已生成: {out_path.relative_to(repo)}")
    print(f"其中 {len(JUDGEMENT_SECTIONS)} 个判断类章节为 TODO，需人工补全。")


if __name__ == "__main__":
    main()
