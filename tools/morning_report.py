#!/usr/bin/env python3
"""夜班晨报生成器——夜班系统向人类的每日交付。

夜班各班次各自记录（logs/、handoff/、memory/），但早上醒来的人不该
翻一堆文件拼凑昨晚发生了什么。本工具聚合一个夜班窗口的全部信息：

1. 提交总览：按 [A]/[B]/[C]/[D] 班次标记自动归属，未标记的单独分组；
2. 代码量：新增/删除行、触及文件数；
3. 测试与记忆体检：现场运行，把结果直接写进晨报；
4. 待人工确认清单：跨文件汇总全部【待确认】（来自 memory_check），
   这是晨报的核心——人对夜班系统唯一需要做的事就在这一节。

用法：
    python tools/morning_report.py                  # 覆盖最近一次 23:05 起
    python tools/morning_report.py --stdout         # 只打印不写文件
    python tools/morning_report.py --out handoff    # 输出目录（默认 handoff）

仅依赖标准库与 git；输出 `YYYY-MM-DD-morning-report.md`。
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from memory_check import collect_markdown_files, find_pending_items  # noqa: E402
from shift_report import (  # noqa: E402
    _parse_numstat_text,
    collect_commits,
    collect_numstat,
    git_since_iso,
    most_recent,
    run_cmd,
    run_git,
)

TAG_RE = re.compile(r"^\[([A-Za-z])\]\s*")


def attribute_commits(commits: list[dict]) -> dict[str, list[dict]]:
    """按提交信息的 [X] 前缀归属；无标记的归入「未标记」。"""
    grouped: dict[str, list[dict]] = {}
    for c in commits:
        m = TAG_RE.match(c["subject"])
        key = m.group(1).upper() if m else "未标记"
        grouped.setdefault(key, []).append(c)
    return grouped


def summarize(repo: Path, since: dt.datetime) -> dict:
    since_iso = git_since_iso(since)
    commits = collect_commits(repo, since_iso)
    files, added, deleted = collect_numstat(repo, since_iso)
    return {
        "commits": commits,
        "grouped": attribute_commits(commits),
        "files": files,
        "added": added,
        "deleted": deleted,
    }


def run_suite(repo: Path) -> tuple[bool, str]:
    code, output = run_cmd("python -m unittest discover -s tests",
                           repo, timeout=300)
    tail = "\n".join(output.splitlines()[-6:]) if output else "（无输出）"
    return code == 0, tail


def run_memory_check(repo: Path) -> tuple[bool, list[tuple[str, int, str]]]:
    """运行记忆体检，返回 (是否通过, 全部待确认事项)。"""
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parent / "memory_check.py")],
        cwd=repo, capture_output=True, text=True, encoding="utf-8",
        errors="replace",
    )
    pending: list[tuple[str, int, str]] = []
    known_files = set(collect_markdown_files(repo, ("memory", "handoff", "logs")))
    for f in known_files:
        text = f.read_text(encoding="utf-8", errors="replace")
        rel = str(f.relative_to(repo)).replace("\\", "/")
        for lineno, item in find_pending_items(text):
            pending.append((rel, lineno, item))
    return proc.returncode == 0, pending


def render(repo_name: str, moment: dt.datetime, since: dt.datetime,
           summary: dict, tests_ok: bool, tests_tail: str,
           memory_ok: bool, pending: list[tuple[str, int, str]]) -> str:
    buf = [f"# 夜班晨报 {moment:%Y-%m-%d}", ""]
    buf.append(f"- 覆盖时段：{since:%Y-%m-%d %H:%M} 起（{repo_name}）")
    buf.append("")

    buf.append("## 一句话总览")
    buf.append("")
    n = len(summary["commits"])
    groups = "、".join(f"{k} {len(v)}" for k, v in summary["grouped"].items())
    buf.append(f"- 昨夜 {n} 个提交（{groups or "无"}），"
               f"+{summary['added']} / -{summary['deleted']} 行，"
               f"触及 {len(summary['files'])} 个文件")
    buf.append(f"- 测试：{'✅ 通过' if tests_ok else '❌ 失败'}；"
               f"记忆体检：{'✅ 通过' if memory_ok else '❌ 有问题'}")
    buf.append("")

    buf.append("## 需要你做的事（待人工确认）")
    buf.append("")
    if pending:
        for rel, lineno, item in pending:
            buf.append(f"- [ ] {item}（{rel}:{lineno}）")
    else:
        buf.append("- 无。夜班系统当前没有任何等待你裁决的事项。")
    buf.append("")

    buf.append("## 提交明细（按班次归属）")
    buf.append("")
    for key in sorted(summary["grouped"]):
        buf.append(f"### 班次 {key}（{len(summary['grouped'][key])} 个提交）")
        buf.append("")
        for c in summary["grouped"][key]:
            buf.append(f"- `{c['hash']}` {c['subject']}")
        buf.append("")
    if "未标记" in summary["grouped"]:
        buf.append("> 提示：存在未标记提交。约定：提交信息以 `[A]/[B]/[C]/[D]` "
                   "开头即可被自动归属。")
        buf.append("")

    buf.append("## 测试输出（末 6 行）")
    buf.append("")
    buf.append("```")
    buf.append(tests_tail)
    buf.append("```")
    buf.append("")
    buf.append("---")
    buf.append(f"*由 tools/morning_report.py 生成于 {moment:%Y-%m-%d %H:%M:%S}。*")
    return "\n".join(buf) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="生成夜班晨报")
    window = parser.add_mutually_exclusive_group()
    window.add_argument("--since", help="起点时间 HH:MM（取该时刻最近一次出现）")
    window.add_argument("--hours", type=float, help="覆盖最近 N 小时")
    parser.add_argument("--out", default="handoff",
                        help="输出目录（默认 handoff/）")
    parser.add_argument("--stdout", action="store_true", help="只打印不写文件")
    args = parser.parse_args()

    repo = Path.cwd()
    try:
        run_git(repo, "rev-parse", "--git-dir")
    except RuntimeError:
        sys.exit("当前目录不是 git 仓库。")
    repo_root = Path(run_git(repo, "rev-parse", "--show-toplevel").strip())

    moment = dt.datetime.now()
    if args.since:
        try:
            hh, mm = map(int, args.since.split(":"))
        except ValueError:
            sys.exit(f"--since 需要 HH:MM 格式，收到: {args.since!r}")
        since = most_recent(hh, mm, moment)
    elif args.hours:
        since = moment - dt.timedelta(hours=args.hours)
    else:
        since = most_recent(*((23, 5)), now=moment)  # 夜班窗口起点

    summary = summarize(repo_root, since)
    tests_ok, tests_tail = run_suite(repo_root)
    memory_ok, pending = run_memory_check(repo_root)

    markdown = render(repo_root.name, moment, since, summary,
                      tests_ok, tests_tail, memory_ok, pending)

    if args.stdout:
        print(markdown)
        return

    out_dir = (repo_root / args.out).resolve()
    try:
        out_dir.relative_to(repo_root.resolve())
    except ValueError:
        sys.exit(f"--out 必须是仓库内的相对路径，收到: {args.out!r}")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{moment:%Y-%m-%d}-morning-report.md"
    counter = 1
    while out_path.exists():
        counter += 1
        out_path = out_dir / f"{out_path.stem}-{counter}{out_path.suffix}"
    out_path.write_text(markdown, encoding="utf-8")
    print(f"晨报已生成: {out_path.relative_to(repo_root)}")
    print(f"待人工确认 {len(pending)} 项。")


if __name__ == "__main__":
    main()
