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
import shift_start  # noqa: E402


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

    def test_since_hour_out_of_range_exits(self) -> None:
        # 数字上合法但时间上越界（24:00）也应友好报错而非 traceback
        args = type("A", (), {"since": "24:00", "hours": None})()
        with self.assertRaises(SystemExit):
            shift_report.parse_since(args)

    def test_since_minute_out_of_range_exits(self) -> None:
        args = type("A", (), {"since": "12:99", "hours": None})()
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

    def test_hours_zero_exits(self) -> None:
        # 0 是假值：旧实现会静默回落到默认 23:05 窗口，必须显式报错
        args = type("A", (), {"since": None, "hours": 0})()
        with self.assertRaises(SystemExit):
            shift_report.parse_since(args)

    def test_hours_negative_exits(self) -> None:
        # 负数会产出"未来起点"的空报告，把参数错误伪装成正常空班次
        args = type("A", (), {"since": None, "hours": -5.0})()
        with self.assertRaises(SystemExit):
            shift_report.parse_since(args)


class SanitizeTests(unittest.TestCase):
    def test_sanitize_filename_part(self) -> None:
        # Windows 保留字符（半角冒号、斜杠等）不能进文件名
        self.assertEqual(shift_report.sanitize_filename_part("夜班C: x/y"),
                         "夜班C- x-y")
        self.assertEqual(shift_report.sanitize_filename_part('a*b?"c'),
                         "a-b-c")
        self.assertEqual(shift_report.sanitize_filename_part("夜班C：无聊"),
                         "夜班C：无聊")  # 全角冒号合法，原样保留

    def test_sanitize_empty_or_dots_falls_back(self) -> None:
        self.assertEqual(shift_report.sanitize_filename_part(""), "夜班")
        self.assertEqual(shift_report.sanitize_filename_part("..."), "夜班")


class NumstatTests(unittest.TestCase):
    def test_parse(self) -> None:
        out = "\x00\n3\t1\ta.txt\n-\t-\tb.bin\n\x00\n"
        files, added, deleted = shift_report._parse_numstat_text(out)
        self.assertEqual(files, ["a.txt", "b.bin"])
        self.assertEqual(added, 3)
        self.assertEqual(deleted, 1)

    def test_parse_empty(self) -> None:
        self.assertEqual(shift_report._parse_numstat_text(""), ([], 0, 0))

    def test_parse_rename_entries(self) -> None:
        # 重命名条目应展开为新旧两个路径，而不是原样当文件名展示
        out = "\x00\n3\t1\told.txt => new.txt\n\x00\n" \
              "2\t0\tdir/{a => b}/f.txt\n\x00\n"
        files, added, deleted = shift_report._parse_numstat_text(out)
        self.assertEqual(files, ["dir/a/f.txt", "dir/b/f.txt",
                                 "new.txt", "old.txt"])
        self.assertEqual((added, deleted), (5, 1))


class AutoFillTests(unittest.TestCase):
    """auto_fill_tests：测试命令执行与结果渲染。"""

    def test_success_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            text = shift_report.auto_fill_tests("echo hello", repo)
            self.assertIn("✅ 通过", text)
            self.assertIn("hello", text)

    def test_failing_command_shows_exit_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            text = shift_report.auto_fill_tests("git --no-such-flag", repo)
            self.assertIn("❌ 失败", text)
            self.assertIn("129", text)


class StatusTests(unittest.TestCase):
    def test_parse_staged_and_untracked(self) -> None:
        out = "M  a.txt\n?? b.txt\n M c.txt\n"
        staged, unstaged = shift_report._parse_status_text(out)
        self.assertEqual(staged, ["M  a.txt"])
        self.assertIn("?? b.txt", unstaged)
        self.assertIn(" M c.txt", unstaged)

    def test_parse_empty(self) -> None:
        self.assertEqual(shift_report._parse_status_text(""), ([], []))

    def test_parse_staged_plus_worktree_entries(self) -> None:
        # AM/MM = 已暂存后又改：应同时出现在两个清单里；
        # 纯暂存重命名（R ）只进已暂存，不进工作区
        out = "AM a.txt\nMM b.txt\nR  c.txt -> d.txt\n M e.txt\n"
        staged, unstaged = shift_report._parse_status_text(out)
        self.assertIn("AM a.txt", staged)
        self.assertIn("AM a.txt", unstaged)
        self.assertIn("MM b.txt", staged)
        self.assertIn("MM b.txt", unstaged)
        self.assertTrue(any(s.startswith("R ") for s in staged))
        self.assertNotIn("R  c.txt -> d.txt", unstaged)
        self.assertIn(" M e.txt", unstaged)


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

    def test_numstat_decodes_non_ascii_filenames(self) -> None:
        # 中文文件名不该被 git 转义成八进制（core.quotepath=off）
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            (repo / "夜班记录.md").write_text("内容\n", encoding="utf-8")
            git(repo, "add", ".")
            git(repo, "commit", "-q", "-m", "中文文件")
            since = shift_report.git_since_iso(
                dt.datetime.now() - dt.timedelta(hours=1))
            files, _, _ = shift_report.collect_numstat(repo, since)
            self.assertIn("夜班记录.md", files)

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

    def test_out_dir_is_relative_to_repo_root_from_subdir(self) -> None:
        # 在仓库子目录里运行时，--out 仍以仓库根为基准（与报错文案一致）
        script = (Path(__file__).resolve().parent.parent
                  / "tools" / "shift_report.py")
        (self.repo / "sub").mkdir()
        result = subprocess.run(
            [sys.executable, str(script), "--hours", "1",
             "--title", "夜班T", "--out", "handoff"],
            cwd=self.repo / "sub", capture_output=True, text=True,
            encoding="utf-8", errors="replace")
        self.assertEqual(result.returncode, 0, result.stderr)
        handoff = self.repo / "handoff"
        self.assertTrue(handoff.is_dir(), result.stdout)
        self.assertTrue(any("夜班T" in p.name for p in handoff.iterdir()))

    def test_same_day_repeat_does_not_overwrite(self) -> None:
        # README 承诺：同一时段重复生成不覆盖旧记录，追加序号
        script = (Path(__file__).resolve().parent.parent
                  / "tools" / "shift_report.py")
        for _ in range(2):
            result = subprocess.run(
                [sys.executable, str(script), "--hours", "1",
                 "--title", "夜班T", "--out", "handoff"],
                cwd=self.repo, capture_output=True, text=True,
                encoding="utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, result.stderr)
        handoff = self.repo / "handoff"
        names = sorted(p.name for p in handoff.iterdir())
        self.assertEqual(len(names), 2)
        self.assertTrue(any("-2" in n for n in names))  # 第二份带序号
        self.assertTrue(any(n.endswith("夜班T.md") for n in names))  # 第一份原样


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


class ShiftStartTests(unittest.TestCase):
    """shift_start.py：开工自检的时间新鲜度判定与集成。"""

    def test_remote_sync_no_upstream_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            self.assertIsNone(
                shift_start.remote_sync_status(repo, "main"))

    def test_staleness_recent(self) -> None:
        now = dt.datetime(2026, 9, 11, 23, 40)
        desc, recent = shift_start.describe_staleness(
            dt.datetime(2026, 9, 11, 23, 35), now)
        self.assertTrue(recent)
        self.assertEqual(desc, "5 分钟前")

    def test_staleness_old(self) -> None:
        now = dt.datetime(2026, 9, 11, 23, 40)
        desc, recent = shift_start.describe_staleness(
            dt.datetime(2026, 9, 11, 20, 0), now)
        self.assertFalse(recent)
        self.assertEqual(desc, "3 小时 40 分前")

    def test_staleness_future_is_suspicious(self) -> None:
        now = dt.datetime(2026, 9, 11, 23, 40)
        desc, recent = shift_start.describe_staleness(
            dt.datetime(2026, 9, 11, 23, 41), now)
        self.assertTrue(recent)
        self.assertIn("异常", desc)

    def test_last_commit_time_naive_local(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            last = shift_start.last_commit_time(repo)
            self.assertIsNotNone(last)
            self.assertIsNone(last.tzinfo)  # 必须是朴素时间，避免相减报错
            self.assertLessEqual(last, dt.datetime.now())

    def test_staleness_custom_threshold_is_honored(self) -> None:
        # --warn-minutes 必须真实参与判定，而不只是改提示文案
        now = dt.datetime(2026, 9, 11, 23, 40)
        last = dt.datetime(2026, 9, 11, 23, 20)  # 20 分钟前
        self.assertTrue(shift_start.describe_staleness(
            last, now, warn_minutes=30)[1])
        self.assertFalse(shift_start.describe_staleness(
            last, now, warn_minutes=15)[1])

    def test_staleness_exactly_threshold_not_recent(self) -> None:
        # "不足 N 分钟"是开区间：恰好 15 分钟前不应报警
        now = dt.datetime(2026, 9, 11, 23, 40)
        desc, recent = shift_start.describe_staleness(
            dt.datetime(2026, 9, 11, 23, 25), now)
        self.assertFalse(recent)
        self.assertEqual(desc, "15 分钟前")


class AppendTests(unittest.TestCase):
    """--append 模式：追加进持续交接文档而不是新建按日期文件。"""

    def test_derive_handoff_path(self) -> None:
        out = Path("handoff")
        self.assertEqual(shift_report.derive_handoff_path("夜班C", out),
                         out / "night-shift-c-handoff.md")
        self.assertEqual(shift_report.derive_handoff_path("夜班B：棋手联赛", out),
                         out / "night-shift-b-handoff.md")
        self.assertIsNone(shift_report.derive_handoff_path("值班", out))

    def test_demote_headings(self) -> None:
        md = "# T\n\n## A\n\n### B\n\ntext"
        self.assertEqual(shift_report.demote_headings(md),
                         "# T\n\n### A\n\n#### B\n\ntext")

    def test_demote_skips_code_fence(self) -> None:
        # 围栏内的 "## 行" 是内容不是标题，降级会篡改数据
        md = "# T\n\n## A\n\n```\n## not-a-heading\n```\n"
        out = shift_report.demote_headings(md)
        self.assertIn("### A", out)
        self.assertIn("\n## not-a-heading\n", out)

    def _sample_markdown(self) -> str:
        return ("# 夜班C 交班记录\n"
                "\n"
                "- 班次日期：2026-09-11 23:00\n"
                "\n"
                "## 今晚发现\n"
                "\n"
                "- x\n"
                "\n"
                "---\n"
                "*生成*")

    def test_append_creates_file_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "night-shift-c-handoff.md"
            created = shift_report.append_to_handoff(
                target, self._sample_markdown(), "## 2026-09-11 夜班C")
            self.assertTrue(created)
            text = target.read_text(encoding="utf-8")
            self.assertIn("# 夜班C 交班记录", text)

    def test_append_inserts_newest_section_on_top(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "night-shift-c-handoff.md"
            target.write_text(
                "# 夜班C交班记录\n"
                "> 简介\n"
                "\n"
                "---\n"
                "\n"
                "## 2026-09-10 旧章节\n"
                "\n"
                "- 旧内容\n",
                encoding="utf-8")
            created = shift_report.append_to_handoff(
                target, self._sample_markdown(), "## 2026-09-11 夜班C")
            self.assertFalse(created)
            text = target.read_text(encoding="utf-8")
            new_pos = text.index("## 2026-09-11 夜班C")
            old_pos = text.index("## 2026-09-10 旧章节")
            self.assertLess(new_pos, old_pos)
            # 嵌入内容降级：## 今晚发现 → ### 今晚发现（行级匹配，避免子串误判）
            self.assertIn("### 今晚发现", text)
            self.assertNotIn("\n## 今晚发现", text)
            self.assertIn("- 旧内容", text)  # 既有内容保留

    def test_append_skips_heading_inside_fence_in_target(self) -> None:
        # 目标文档围栏内的 "## " 是内容：插入点必须落在围栏后的真实章节前
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "handoff.md"
            target.write_text(
                "# 夜班C交班记录\n"
                "> 简介\n"
                "\n"
                "```\n"
                "## 示例标题\n"
                "```\n"
                "\n"
                "## 2026-09-10 旧章节\n"
                "\n"
                "- 旧内容\n",
                encoding="utf-8")
            shift_report.append_to_handoff(
                target, self._sample_markdown(), "## 2026-09-11 夜班C")
            text = target.read_text(encoding="utf-8")
            new_pos = text.index("## 2026-09-11 夜班C")
            self.assertGreater(new_pos, text.index("## 示例标题"))
            self.assertLess(new_pos, text.index("## 2026-09-10 旧章节"))
            # 围栏内容原样保留
            self.assertIn("## 示例标题", text)

    def test_append_preserves_crlf_line_endings(self) -> None:
        # Windows 检出的文档常为 CRLF：追加不应把整份文档改写成 LF
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "handoff.md"
            target.write_bytes(
                "# 夜班C交班记录\r\n> 简介\r\n\r\n## 2026-09-10 旧章节\r\n\r\n- 旧内容\r\n"
                .encode("utf-8"))
            shift_report.append_to_handoff(
                target, self._sample_markdown(), "## 2026-09-11 夜班C")
            data = target.read_bytes()
            self.assertIn("- 旧内容\r\n".encode("utf-8"), data)
            self.assertIn("## 2026-09-11 夜班C\r\n".encode("utf-8"), data)
            # 除去 CRLF 后不应残留任何裸 LF（否则说明有行被改成了 LF 行尾）
            self.assertEqual(data.replace(b"\r\n", b"").count(b"\n"), 0)

    def test_append_drops_footer_separator(self) -> None:
        # 渲染页脚自带 "---"：追加时去掉，避免与外层追加分隔线相邻重复
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "handoff.md"
            target.write_text("# 夜班C交班记录\n\n## 2026-09-10 旧章节\n\n- 旧\n",
                              encoding="utf-8")
            md = ("# 夜班C 交班记录\n\n## 今晚发现\n\n- x\n\n"
                  "---\n"
                  "*由 tools/shift_report.py 自动生成于 2026-09-11 23:00:00，"
                  "TODO 段落需人工补全。*\n")
            shift_report.append_to_handoff(
                target, md, "## 2026-09-11 夜班C")
            text = target.read_text(encoding="utf-8")
            self.assertIn("*由 tools/shift_report.py 自动生成于", text)  # 署名保留
            self.assertNotIn("---\n*由 tools/shift_report.py", text)  # 页脚分隔线已去
            self.assertNotIn("---\n---", text)


class ShiftTagTests(unittest.TestCase):
    """--shift-tag：按提交信息前缀过滤班次归属，numstat 逐提交重算。"""

    def test_filter_and_numstat(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp), commits=0)
            (repo / "c.txt").write_text("c\n", encoding="utf-8")
            git(repo, "add", ".")
            git(repo, "commit", "-q", "-m", "[C] 归属C的提交")
            (repo / "b.txt").write_text("b\nb\n", encoding="utf-8")
            git(repo, "add", ".")
            git(repo, "commit", "-q", "-m", "无标记提交")
            all_commits = shift_report.collect_commits(
                repo, shift_report.git_since_iso(
                    dt.datetime.now() - dt.timedelta(hours=1)))
            self.assertEqual(len(all_commits), 2)

            matched, files, added, deleted = shift_report.filter_by_shift_tag(
                repo, all_commits, "C")
            self.assertEqual(len(matched), 1)
            self.assertEqual(matched[0]["subject"], "[C] 归属C的提交")
            self.assertEqual(files, ["c.txt"])
            self.assertEqual((added, deleted), (1, 0))

            empty, _, _, _ = shift_report.filter_by_shift_tag(
                repo, all_commits, "D")
            self.assertEqual(empty, [])


class ResolveSectionsTests(unittest.TestCase):
    def test_default_union(self) -> None:
        self.assertEqual(shift_report.resolve_sections(None, None),
                         shift_report.SECTIONS)

    def test_profile_c(self) -> None:
        got = shift_report.resolve_sections("C", None)
        self.assertIn("今晚发现", got)
        self.assertNotIn("今晚比赛", got)  # C 协议没有 B 的比赛章节

    def test_unknown_profile_exits(self) -> None:
        with self.assertRaises(SystemExit):
            shift_report.resolve_sections("X", None)

    def test_sections_override(self) -> None:
        got = shift_report.resolve_sections(None, "测试, 实际修改，失败")
        self.assertEqual(got, ["测试", "实际修改", "失败"])

    def test_both_given_exits(self) -> None:
        with self.assertRaises(SystemExit):
            shift_report.resolve_sections("C", "测试")

    def test_render_with_profile_c(self) -> None:
        md = shift_report.render(
            Path("."), "demo", "夜班C", dt.datetime(2026, 9, 12, 0, 10),
            dt.datetime(2026, 9, 11, 23, 20), "main", "abc1234",
            commits=[], files=[], added=0, deleted=0,
            staged=[], unstaged=[], test_cmd=None,
            sections=shift_report.resolve_sections("C", None),
        )
        self.assertIn("## 今晚发明", md)
        self.assertNotIn("## 今晚比赛", md)


if __name__ == "__main__":
    unittest.main()
