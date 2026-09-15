#!/usr/bin/env python3
"""夜班大事记——全历史按日统计页（HTML+JS，GitHub Pages 可用）。

驾驶舱只看一个窗口，本页回答"这些天夜班系统整体运转得怎么样"：
按日期聚合全部提交，每天一条泳道（气泡按班次着色），配各班次每日
提交数的热力条。积累越久越有价值——周末连续值班时它就是编年史。

用法：
    python tools/night_history.py            # 生成 site/history.html
    python tools/night_history.py --days 30  # 只看最近 30 天（默认全部）

仅依赖标准库与 git。
"""

from __future__ import annotations

import argparse
import datetime as dt
import functools
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shift_report import ensure_safe_stdout, run_git  # noqa: E402

TAG_RE = re.compile(r"^\[([A-Za-z])\]\s*")
SHIFTS = ["A", "B", "C", "D"]


def collect_all_commits(repo: Path, days: int | None) -> list[dict]:
    args = ["log", "--pretty=format:%h%x1f%ad%x1f%s", "--date=iso"]
    if days:
        since = (dt.datetime.now() - dt.timedelta(days=days)).strftime(
            "%Y-%m-%dT00:00:00")
        args.insert(1, f"--since={since}")
    out = run_git(repo, *args)
    commits = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split("\x1f")
        if len(parts) == 3:
            m = TAG_RE.match(parts[2])
            lane = m.group(1).upper() if m else "未标记"
            commits.append({"hash": parts[0], "date": parts[1],
                            "subject": parts[2], "lane": lane})
    return commits


def group_by_day(commits: list[dict]) -> list[dict]:
    days: dict[str, list[dict]] = {}
    for c in commits:
        day = c["date"][:10]
        days.setdefault(day, []).append(c)
    return [{"day": day, "commits": sorted(cs, key=lambda c: c["date"])}
            for day, cs in sorted(days.items(), reverse=True)]


def build_html(data: dict) -> str:
    data_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return TEMPLATE.replace("__DATA__", data_json)


TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>夜班大事记</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; margin: 0; }
  body { background:linear-gradient(160deg,#0b1020,#141b34 60%,#1a1440);
         color:#dfe3ee; font:15px/1.6 "Segoe UI","Microsoft YaHei",sans-serif;
         min-height:100vh; padding:32px; }
  h1 { font-size:25px; } h1 small { color:#8a93b2; font-size:13px;
       font-weight:normal; margin-left:12px; }
  h2 { font-size:16px; color:#aeb8dd; margin:0 0 12px;
       border-left:3px solid #5b6cff; padding-left:10px; }
  section { background:rgba(255,255,255,.04); border-radius:14px;
            padding:20px 22px; margin:18px 0; border:1px solid rgba(255,255,255,.08); }
  .dayhead { display:flex; align-items:baseline; gap:14px; margin:16px 0 6px; }
  .dayhead .d { font-size:17px; color:#aeb8dd; font-weight:bold; }
  .dayhead .n { color:#68719a; font-size:12.5px; }
  .heat { display:flex; gap:4px; align-items:center; }
  .heat .cell { padding:1px 8px; border-radius:9px; font-size:12px;
                color:#0b1020; font-weight:bold; }
  .commitline { padding:3px 0 3px 18px; font-size:13.5px; color:#c6cde4; }
  .commitline code { background:rgba(255,255,255,.08); padding:1px 6px;
                     border-radius:5px; font-size:12.5px; margin-right:8px; }
  .legend { display:flex; gap:14px; margin:8px 0 0; color:#8a93b2; font-size:12.5px; }
  .legend b { padding:1px 8px; border-radius:9px; margin-right:4px; color:#0b1020; }
  a { color:#9db4ff; text-decoration:none; }
  a:hover { text-decoration:underline; }
  .empty { color:#68719a; padding:16px; text-align:center; }
  footer { color:#5d6688; font-size:12.5px; margin-top:26px; text-align:center; }
  details summary { cursor:pointer; color:#8a93b2; font-size:12.5px; }
</style>
</head>
<body>
<h1>📅 夜班大事记 <small id="sub"></small></h1>
<p style="margin:8px 0 0">
  <a href="index.html">🎛️ 驾驶舱</a> · <a href="docs.html">📚 图书馆</a> · 本页 · <a href="shifts.html">🛰️ 出勤表</a> · <a href="sky.html">✨ 星图</a> · <a href="game.html">🔮 模拟器</a></p>
<section>
  <h2>各班次每日提交热力</h2>
  <div id="heat"></div>
  <div class="legend" id="legend"></div>
</section>
<section>
  <h2>编年史（按日，点击展开提交明细）</h2>
  <div id="days"></div>
</section>
<footer>night-shift autopilot · tools/night_history.py · 纯静态 HTML+JS，GitHub Pages 即开即用</footer>

<script>
const DATA = __DATA__;

const COLORS = { A:"#7c9cff", B:"#ffb86c", C:"#7ce8c1", D:"#ff9ecb", "未标记":"#8a8f9d" };
const NAMES = { A:"记忆基建", B:"棋手联赛", C:"无聊发明", D:"记录" };
const SHIFTS = ["A", "B", "C", "D"];
const esc = s => String(s).replace(/[&<>"']/g,
  c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

document.getElementById("sub").textContent =
  `${DATA.generated} 生成 · 共 ${DATA.commits.length} 提交 · ${DATA.days.length} 天`;

// 每班次每日热力条
const byDayShift = {};
for (const c of DATA.commits) {
  const day = c.date.slice(0, 10);
  byDayShift[day] = byDayShift[day] || {};
  byDayShift[day][c.lane] = (byDayShift[day][c.lane] || 0) + 1;
}
const maxN = Math.max(1, ...Object.values(byDayShift)
  .map(d => Math.max(...Object.values(d))));
document.getElementById("heat").innerHTML =
  `<table style="border-collapse:collapse;width:100%">
   <tr><th style="text-align:left;padding:4px 12px;color:#8a93b2;font-weight:normal">日期</th>
   ${SHIFTS.map(s => `<th style="color:#8a93b2;font-weight:normal">${s}</th>`).join("")}
   <th style="color:#8a93b2;font-weight:normal">未标记</th></tr>
   ${DATA.days.map(d => `<tr>
     <td style="padding:4px 12px">${esc(d.day)}</td>
     ${[...SHIFTS, "未标记"].map(s => {
       const n = (byDayShift[d.day] || {})[s] || 0;
       const alpha = n ? (0.25 + 0.75 * n / maxN) : 0.06;
       return `<td style="text-align:center"><span class="cell"
         style="background:${COLORS[s]}${Math.round(alpha * 255).toString(16).padStart(2, "0")}">${n || "·"}</span></td>`;
     }).join("")}</tr>`).join("")}</table>`;
document.getElementById("legend").innerHTML =
  SHIFTS.map(s => `<span><b style="background:${COLORS[s]}">${s}</b>${NAMES[s]}</span>`).join("")
  + '<span><b style="background:#8a8f9d">未标记</b>约定前的历史提交</span>';

// 编年史
document.getElementById("days").innerHTML = DATA.days.map(d => {
  const items = d.commits.map(c =>
    `<div class="commitline"><code>${esc(c.hash)}</code>
     <b style="color:${COLORS[c.lane]}">[${esc(c.lane)}]</b> ${esc(c.subject)}</div>`).join("");
  return `<div class="dayhead"><span class="d">${esc(d.day)}</span>
    <span class="n">${d.commits.length} 提交</span></div>
    <details><summary>展开明细</summary>${items}</details>`;
}).join("") || '<div class="empty">还没有任何提交</div>';
</script>
</body>
</html>"""


def main() -> None:
    ensure_safe_stdout()
    parser = argparse.ArgumentParser(description="生成夜班大事记页面")
    parser.add_argument("--days", type=int, help="只看最近 N 天（默认全部历史）")
    parser.add_argument("--out", default="site", help="输出目录（默认 site/）")
    parser.add_argument("--serve", action="store_true",
                        help="生成后起本地服务预览")
    parser.add_argument("--port", type=int, default=8802)
    args = parser.parse_args()

    repo = Path.cwd()
    try:
        run_git(repo, "rev-parse", "--git-dir")
    except RuntimeError:
        sys.exit("当前目录不是 git 仓库。")
    repo_root = Path(run_git(repo, "rev-parse", "--show-toplevel").strip())

    commits = collect_all_commits(repo_root, args.days)
    data = {
        "generated": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "commits": commits,
        "days": group_by_day(commits),
    }

    out_dir = (repo_root / args.out).resolve()
    try:
        out_dir.relative_to(repo_root.resolve())
    except ValueError:
        sys.exit(f"--out 必须是仓库内的相对路径，收到: {args.out!r}")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "history.html"
    out_path.write_text(build_html(data), encoding="utf-8")
    print(f"大事记已生成: {out_path.relative_to(repo_root).as_posix()}"
          f"（{data['days'] and len(data['days']) or 0} 天 · {len(commits)} 提交）")

    if args.serve:
        import http.server
        handler = functools.partial(
            http.server.SimpleHTTPRequestHandler, directory=str(out_dir))
        print(f"serving {out_dir} at http://127.0.0.1:{args.port}/history.html"
              " (Ctrl+C 退出)")
        http.server.ThreadingHTTPServer(
            ("127.0.0.1", args.port), handler).serve_forever()


if __name__ == "__main__":
    main()
