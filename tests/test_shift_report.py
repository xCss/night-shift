"""shift_report.py 的单元测试。

运行：python -m unittest discover -s tests -v
"""

from __future__ import annotations

import datetime as dt
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import shift_report  # noqa: E402


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True, capture_output=True, text=True, encoding="utf-8",
    )


def make_repo(tmp: Path, commits: int = 2) -> Path:
    repo = tmp / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Tester")
    git(repo, "config", "user.email", "t@example.com")
    for i in range(commits):
        (repo / f"f{i}.txt").write_text(f"content {i}\n" * (i + 1),
                                        encoding="utf-8")
        git(repo, "add", ".")
        git(repo, "commit", "-q", "-m", f"commit {i}")
    return repo


class ParseSinceTests(unittest.TestCase):
    def test_since_same_day(self) -> None:
        now = dt.datetime(2026, 9, 11, 23, 0)
        args = type("A", (), {"since": "20:30", "hours": None})()
        got = shift_report.parse_since(args, now)
        self.assertEqual(got, now.replace(hour=20, minute=30,
                                          second=0, microsecond=0))

    def test_since_bad_format_exits(self) -> None:
        args = type("A", (), {"since": "abc", "hours": None})()
        with self.assertRaises(SystemExit):
            shift_report.parse_since(args)

    def test_since_crosses_midnight(self) -> None:
        # 夜班场景：早上 08:00 写 --since "23:05" 应指昨夜的 23:05
        now = dt.datetime(2026, 9, 12, 8, 0)
        args = type("A", (), {"since": "23:05", "hours": None})()
        got = shift_report.parse_since(args, now)
        self.assertEqual(got, dt.datetime(2026, 9, 11, 23, 5))

    def test_since_not_yet_reached_stays_today(self) -> None:
        # 统一语义：--since "HH:MM" 取该时刻最近一次出现。
        # 白天 14:00 写 --since "20:30" → 昨晚 20:30（昨晚以来的活动）
        now = dt.datetime(2026, 9, 11, 14, 0)
        args = type("A", (), {"since": "20:30", "hours": None})()
        got = shift_report.parse_since(args, now)
        self.assertEqual(got, dt.datetime(2026, 9, 10, 20, 30))

    def test_hours(self) -> None:
        args = type("A", (), {"since": None, "hours": 8.0})()
        got = shift_report.parse_since(args)
        self.assertLessEqual(got, dt.datetime.now() - dt.timedelta(hours=7.9))


class NumstatTests(unittest.TestCase):
    def test_parse(self) -> None:
        out = "\x00\n3\t1\ta.txt\n-\t-\tb.bin\n\x00\n"
        files, added, deleted = shift_report._parse_numstat_text(out)
        self.assertEqual(files, ["a.txt", "b.bin"])
        self.assertEqual(added, 3)
        self.assertEqual(deleted, 1)

    def test_parse_empty(self) -> None:
        self.assertEqual(shift_report._parse_numstat_text(""), ([], 0, 0))


class StatusTests(unittest.TestCase):
    def test_parse_staged_and_untracked(self) -> None:
        out = "M  a.txt\n?? b.txt\n M c.txt\n"
        staged, unstaged = shift_report._parse_status_text(out)
        self.assertEqual(staged, ["M  a.txt"])
        self.assertIn("?? b.txt", unstaged)
        self.assertIn(" M c.txt", unstaged)

    def test_parse_empty(self) -> None:
        self.assertEqual(shift_report._parse_status_text(""), ([], []))


class RepoIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = make_repo(Path(self._tmp.name))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_collect_commits(self) -> None:
        since = shift_report.git_since_iso(
            dt.datetime.now() - dt.timedelta(hours=1))
        commits = shift_report.collect_commits(self.repo, since)
        self.assertEqual([c["subject"] for c in commits], ["commit 1", "commit 0"])
        self.assertEqual(len(commits[0]["hash"]), 8)

    def test_collect_numstat_files(self) -> None:
        since = shift_report.git_since_iso(
            dt.datetime.now() - dt.timedelta(hours=1))
        files, added, deleted = shift_report.collect_numstat(self.repo, since)
        self.assertEqual(files, ["f0.txt", "f1.txt"])
        self.assertEqual(added, 3)
        self.assertEqual(deleted, 0)

    def test_status_clean(self) -> None:
        staged, unstaged = shift_report.collect_status(self.repo)
        self.assertEqual((staged, unstaged), ([], []))

    def test_status_with_untracked(self) -> None:
        (self.repo / "new.txt").write_text("x\n", encoding="utf-8")
        staged, unstaged = shift_report.collect_status(self.repo)
        self.assertEqual(staged, [])
        self.assertEqual(len(unstaged), 1)
        self.assertIn("new.txt", unstaged[0])

    def test_branch_head(self) -> None:
        branch, head = shift_report.collect_branch_head(self.repo)
        self.assertIn(branch, ("master", "main"))  # 随 git 版本/配置而定
        self.assertRegex(head, r"^[0-9a-f]{7,}$")

    def test_run_cmd_failure(self) -> None:
        code, _ = shift_report.run_cmd("exit 7", self.repo)
        self.assertEqual(code, 7)


class RenderTests(unittest.TestCase):
    def test_render_contains_all_sections(self) -> None:
        moment = dt.datetime(2026, 9, 11, 23, 30)
        since = dt.datetime(2026, 9, 11, 20, 0)
        md = shift_report.render(
            Path("."), "demo", "夜班C", moment, since, "main", "abc1234",
            commits=[{"hash": "abc12345", "author": "T", "date": "d",
                      "subject": "s"}],
            files=["a.py"], added=10, deleted=2,
            staged=[], unstaged=["?? new.txt"],
            test_cmd=None,
        )
        for section in shift_report.SECTIONS:
            self.assertIn(f"## {section}", md)
        self.assertIn("`abc12345` s", md)
        self.assertIn("new.txt", md)
        self.assertIn("未提交", md)

    def test_render_no_commits(self) -> None:
        md = shift_report.render(
            Path("."), "demo", "夜班C", dt.datetime(2026, 9, 11, 23, 30),
            dt.datetime(2026, 9, 11, 20, 0), "main", "abc1234",
            commits=[], files=[], added=0, deleted=0,
            staged=[], unstaged=[], test_cmd=None,
        )
        self.assertIn("本班次无提交", md)


class ProtocolAlignmentTests(unittest.TestCase):
    """校验章节与 AGENTS.md 交班记录协议要求的字段保持对齐。"""

    def test_protocol_required_sections_present(self) -> None:
        for section in shift_report.PROTOCOL_REQUIRED_SECTIONS:
            self.assertIn(section, shift_report.SECTIONS)
            self.assertIn(section, shift_report.JUDGEMENT_SECTIONS)

    def test_render_includes_protocol_sections(self) -> None:
        md = shift_report.render(
            Path("."), "demo", "夜班B", dt.datetime(2026, 9, 11, 23, 30),
            dt.datetime(2026, 9, 11, 20, 0), "main", "abc1234",
            commits=[], files=[], added=0, deleted=0,
            staged=[], unstaged=[], test_cmd=None,
        )
        for section in shift_report.PROTOCOL_REQUIRED_SECTIONS:
            self.assertIn(f"## {section}", md)


if __name__ == "__main__":
    unittest.main()
