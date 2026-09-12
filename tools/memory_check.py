#!/usr/bin/env python3
"""夜班记忆体检工具（只读）。

自动化 project-status.md 的常设任务「持续检查记忆文件的重复/冲突/过期
信息」的一部分。扫描 memory/、handoff/、logs/ 下的 Markdown：

1. 提交哈希引用校验——引用的 7/8 位哈希必须在仓库历史中真实存在，
   防止笔误的哈希永久污染记忆；
2. 【待确认】事项汇总——跨文件列出所有待人工确认的位置，供下一班次
   向人工一次性提问；
3. 未来日期检查——形如 [2026-09-13] / 2026-09-13 的时间戳不应晚于
   今天（笔误或时钟错误的信号）。

用法：
    python tools/memory_check.py            # 扫描并报告，有问题 exit 1
    python tools/memory_check.py --dirs memory logs

只读，不修改任何文件；退出码可直接接入 CI。
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shift_report import run_git  # noqa: E402

DEFAULT_DIRS = ("memory", "handoff", "logs")
HASH_RE = re.compile(r"`([0-9a-f]{7,8})`")
PENDING_RE = re.compile(r"【待确认】[^\s，。；~（）\n][^，。；~（）\n]*")
DATE_RE = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")


def collect_markdown_files(repo: Path, dirs: tuple[str, ...]) -> list[Path]:
    files: list[Path] = []
    for d in dirs:
        base = repo / d
        if base.is_dir():
            for f in sorted(base.rglob("*.md")):
                # 晨报是生成物：其中复述的待确认事项不是独立来源，
                # 否则每天重复计数，越滚越多
                if "morning-report" not in f.name:
                    files.append(f)
    return files


def known_short_hashes(repo: Path) -> set[str]:
    """仓库中全部提交的 7 位与 8 位短哈希。"""
    out = run_git(repo, "rev-list", "--all",
                  "--pretty=format:%h %H", check=False)
    known: set[str] = set()
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) == 2:
            known.add(parts[0])
            known.add(parts[1][:8])
    return known


def check_hashes(text: str, known: set[str]) -> list[str]:
    problems = []
    for h in HASH_RE.findall(text):
        if h not in known:
            problems.append(h)
    return problems


def check_future_dates(text: str, today: dt.date) -> list[str]:
    problems = []
    for year, month, day in DATE_RE.findall(text):
        try:
            d = dt.date(int(year), int(month), int(day))
        except ValueError:
            continue  # 非法日期由专门的 linter 管，这里只查未来
        if d > today:
            problems.append(f"{year}-{month}-{day}")
    return problems


def find_pending_items(text: str) -> list[tuple[int, str]]:
    """返回 (行号, 事项)。行内代码片段（`...`）中的【待确认】不算数，
    那是文档在描述这个标记本身，不是真的待确认。"""
    items: list[tuple[int, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = re.sub(r"`[^`]*`", "", line)
        for m in PENDING_RE.finditer(stripped):
            items.append((lineno, m.group(0)))
    return items


def main() -> None:
    parser = argparse.ArgumentParser(description="夜班记忆体检（只读）")
    parser.add_argument("--dirs", nargs="*", default=list(DEFAULT_DIRS),
                        help="扫描目录（默认 memory handoff logs）")
    args = parser.parse_args()

    repo = Path.cwd()
    try:
        run_git(repo, "rev-parse", "--git-dir")
    except RuntimeError:
        sys.exit("当前目录不是 git 仓库。")

    today = dt.date.today()
    known = known_short_hashes(repo)
    files = collect_markdown_files(repo, tuple(args.dirs))
    if not files:
        print(f"未找到任何 Markdown（目录：{', '.join(args.dirs)}），无事可查。")
        return

    issues = 0
    total_pending = 0
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = path.relative_to(repo)
        for h in check_hashes(text, known):
            print(f"❌ {rel}: 引用了不存在的提交哈希 `{h}`")
            issues += 1
        for d in check_future_dates(text, today):
            print(f"❌ {rel}: 出现未来日期 {d}（笔误或时钟错误？）")
            issues += 1
        pending = find_pending_items(text)
        total_pending += len(pending)
        for lineno, item in pending:
            print(f"⏳ {rel}:{lineno}: {item}")
            # 待确认不是错误，不计入 issues

    print(f"扫描 {len(files)} 个文件：{issues} 个问题，"
          f"待人工确认事项共 {total_pending} 处。")
    sys.exit(1 if issues else 0)


if __name__ == "__main__":
    main()
