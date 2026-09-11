#!/usr/bin/env python3
"""夜班开工自检工具。

夜班系统有多名班次并发操作同一个仓库（2026-09-11 夜间实际发生过 README
覆盖冲突、日志段落踩踏、测试竞态）。本工具在开工时快速回答两个问题：

1. 仓库现在处于什么状态（分支、HEAD、最后提交、未提交改动）？
2. 是否有并行班次正在工作（最后提交距今是否很短）？

用法：
    python tools/shift_start.py                # 默认并发判定阈值 15 分钟
    python tools/shift_start.py --warn-minutes 30

仅依赖标准库与 git；只读，不修改任何文件。
"""

from __future__ import annotations

import argparse
import datetime as dt
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shift_report import _parse_status_text, run_git  # noqa: E402


def last_commit_time(repo: Path) -> dt.datetime | None:
    out = run_git(repo, "log", "-1", "--pretty=format:%cI", check=False)
    out = out.strip()
    if not out:
        return None
    try:
        parsed = dt.datetime.fromisoformat(out)
    except ValueError:
        return None
    # %cI 带 UTC 偏移；统一转成本地朴素时间，方便与 now 直接比较
    return parsed.astimezone().replace(tzinfo=None)


def describe_staleness(last: dt.datetime, now: dt.datetime,
                       warn_minutes: int = 15) -> tuple[str, bool]:
    """返回 (人读描述, 是否疑似并发活动)。阈值：warn_minutes 分钟内。"""
    delta = now - last
    minutes = int(delta.total_seconds() // 60)
    if minutes < 0:
        return f"未来时间戳（{last:%H:%M}），系统时钟或提交时间异常", True
    recent = minutes < warn_minutes
    if minutes < 1:
        desc = "1 分钟内"
    elif minutes < 60:
        desc = f"{minutes} 分钟前"
    else:
        desc = f"{minutes // 60} 小时 {minutes % 60} 分前"
    return desc, recent


def remote_sync_status(repo: Path, branch: str) -> str | None:
    """返回与 origin 上游的差距描述；无上游/无远程时返回 None。"""
    out = run_git(repo, "rev-list", "--left-right", "--count",
                  f"origin/{branch}...{branch}", check=False).strip()
    if not out:
        return None
    try:
        behind_s, ahead_s = out.split()
        behind, ahead = int(behind_s), int(ahead_s)
    except ValueError:
        return None
    if behind == 0 and ahead == 0:
        return "与远程同步"
    parts = []
    if ahead:
        parts.append(f"本地领先 {ahead} 个提交（未 push）")
    if behind:
        parts.append(f"远程领先 {behind} 个提交（本地落后）")
    return "；".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(description="夜班开工自检（只读）")
    parser.add_argument("--warn-minutes", type=int, default=15,
                        help="最后提交距今多少分钟内视为疑似并发活动（默认 15）")
    args = parser.parse_args()
    if args.warn_minutes < 1:
        sys.exit(f"--warn-minutes 需要正整数，收到: {args.warn_minutes}")

    repo = Path.cwd()
    try:
        run_git(repo, "rev-parse", "--git-dir")
    except RuntimeError:
        sys.exit("当前目录不是 git 仓库。")

    now = dt.datetime.now()
    branch = run_git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()
    head = run_git(repo, "rev-parse", "--short", "HEAD").strip()

    print(f"开工自检  {now:%Y-%m-%d %H:%M}")
    print(f"分支 {branch} @ {head}")

    sync = remote_sync_status(repo, branch)
    if sync:
        print(f"远程状态：{sync}")
        if "未 push" in sync:
            print("⚠️  本地提交尚未 push：CI 不会运行，其他机器看不到这些工作。"
                  "是否 push 见长期记忆待确认事项。")

    last = last_commit_time(repo)
    if last is None:
        print("最后提交：（无）")
    else:
        desc, recent = describe_staleness(last, now, args.warn_minutes)
        print(f"最后提交：{last:%H:%M}（{desc}）")
        if recent:
            print(f"⚠️  最后提交距今不足 {args.warn_minutes} 分钟："
                  "疑似有并行班次正在工作。开工前重新读取仓库状态，"
                  "编辑文件前先读最新版本，避免踩踏。")

    # 与 shift_report._parse_status_text 保持同一套判定（单一事实源），
    # 避免 AM/MM 这类"已暂存+工作区又改"的条目被漏报
    staged, unstaged = _parse_status_text(
        run_git(repo, "status", "--porcelain"))

    if staged or unstaged:
        print(f"未提交改动：{len(staged) + len(unstaged)} 项")
        for s in staged:
            print(f"  已暂存  {s}")
        for s in unstaged:
            print(f"  工作区  {s}")
        print("⚠️  工作区不干净：这些可能是并行班次未完成的工作，"
              "不要擅自提交或还原。")
    else:
        print("工作区干净。")

    print("提示：收尾时用 tools/shift_report.py 生成交班记录。")


if __name__ == "__main__":
    main()
