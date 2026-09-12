#!/usr/bin/env python3
"""班次出勤表——从提交时间反推各班次的值班时段（HTML+JS，Pages 可用）。

提交时间不会说谎：把每个班次（[A]/[B]/[C]/[D] 标记）的提交按时间排序，
相邻间隔超过 GAP_HOURS 即视为换班，由此聚类出"值班时段"（会话）。
页面按日渲染甘特条：每班次一行，条的位置和长度就是在岗时间段——
回答此前没人能回答的问题：昨夜谁在岗、几段、多久、是否重叠。

会话检测是启发式：小时级触发协议下班次提交通常成簇，2 小时无提交
基本可判定换班/收班。标记约定（提交带 [X] 前缀）落地前的提交无法
归属，不计入出勤。

用法：
    python tools/night_shifts.py            # 生成 site/shifts.html
    python tools/night_shifts.py --days 14

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
GAP_HOURS = 2.0  # 相邻提交间隔超过此值视为换班


def detect_sessions(commits: list[dict], gap_hours: float = GAP_HOURS) -> list[dict]:
    """把单个班次的提交聚成值班时段（会话）。

    commits 需含 iso date 与 lane；返回按开始时间排序的会话列表：
    {lane, start, end, count}。间隔超过 gap_hours 即切断。
    """
    by_lane: dict[str, list[dict]] = {}
    for c in commits:
        m = TAG_RE.match(c["subject"])
        if not m:
            continue  # 未标记提交无法归属班次
        by_lane.setdefault(m.group(1).upper(), []).append(c)

    sessions = []
    for lane, cs in by_lane.items():
        cs = sorted(cs, key=lambda c: c["date"])
        cur = None
        for c in cs:
            try:
                t = dt.datetime.fromisoformat(c["date"])
            except ValueError:
                continue
            if cur and (t - cur["end"]).total_seconds() <= gap_hours * 3600:
                cur["end"] = t
                cur["count"] += 1
            else:
                if cur:
                    sessions.append(cur)
                cur = {"lane": lane, "start": t, "end": t, "count": 1}
        if cur:
            sessions.append(cur)
    return sorted(sessions, key=lambda s: (s["start"], s["lane"]))


def collect_commits(repo: Path, days: int | None) -> list[dict]:
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
            commits.append({"hash": parts[0], "date": parts[1],
                            "subject": parts[2]})
    return commits


def build_html(data: dict) -> str:
    data_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return TEMPLATE.replace("__DATA__", data_json)


TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>班次出勤表</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; margin: 0; }
  body { background:linear-gradient(160deg,#0b1020,#141b34 60%,#1a1440);
         color:#dfe3ee; font:15px/1.6 "Segoe UI","Microsoft YaHei",sans-serif;
         min-height:100vh; padding:32px; }
  h1 { font-size:25px; } h1 small { color:#8a93b2; font-size:13px;
       font-weight:normal; margin-left:12px; }
  p.nav a { color:#9db4ff; text-decoration:none; margin-right:10px; }
  p.nav a:hover { text-decoration:underline; }
  section { background:rgba(255,255,255,.04); border-radius:14px;
            padding:20px 22px; margin:18px 0; border:1px solid rgba(255,255,255,.08); }
  h2 { font-size:16px; color:#aeb8dd; margin:0 0 6px;
       border-left:3px solid #5b6cff; padding-left:10px; }
  .dayrow { margin:14px 0 4px; color:#aeb8dd; font-weight:bold; font-size:15px; }
  .gantt { position:relative; background:rgba(255,255,255,.04);
           border-radius:10px; height:34px; margin:6px 0 10px; }
  .gantt .hourlabel { position:absolute; top:50%; transform:translateY(-50%);
                      color:#4a5273; font-size:11px; }
  .bar { position:absolute; top:50%; height:16px; transform:translateY(-50%);
         border-radius:8px; cursor:help; min-width:6px; }
  .rowlabel { color:#aeb8dd; font-size:13px; margin:8px 0 2px; }
  table { border-collapse:collapse; margin-top:8px; }
  th,td { padding:5px 14px; border-bottom:1px solid rgba(255,255,255,.08);
          text-align:left; font-size:14px; }
  th { color:#8a93b2; font-weight:normal; }
  .total { font-size:20px; color:#7ce8c1; }
  .legend { color:#8a93b2; font-size:12.5px; margin-top:10px; }
  .empty { color:#68719a; padding:16px; text-align:center; }
  footer { color:#5d6688; font-size:12.5px; margin-top:26px; text-align:center; }
  a { color:#9db4ff; text-decoration:none; }
</style>
</head>
<body>
<h1>🛰️ 班次出勤表 <small id="sub"></small></h1>
<p class="nav">
  <a href="index.html">🎛️ 驾驶舱</a><a href="docs.html">📚 图书馆</a>
  <a href="history.html">📅 大事记</a>· 本页（值班时段反推）</p>

<section>
  <h2>累计在岗时长</h2>
  <div id="totals"></div>
  <div class="legend">检测启发式：同一班次相邻提交间隔 ≤ 2 小时视为同一次值班；
    值班标记约定落地前的提交无法归属，不计入。</div>
</section>

<section>
  <h2>值班时段甘特图（按日，横轴 0–24 时）</h2>
  <div id="gantt"></div>
</section>

<footer><a href="index.html">🎛️ 驾驶舱</a> · <a href="docs.html">📚 图书馆</a> · <a href="history.html">📅 大事记</a> · <a href="sky.html">✨ 星图</a> · <a href="game.html">🔮 模拟器</a> · night-shift autopilot · tools/night_shifts.py</footer>

<script>
const DATA = __DATA__;
const SESSIONS = DATA.sessions;

const COLORS = { A:"#7c9cff", B:"#ffb86c", C:"#7ce8c1", D:"#ff9ecb" };
const NAMES = { A:"记忆基建", B:"棋手联赛", C:"无聊发明", D:"记录" };
const esc = s => String(s).replace(/[&<>"']/g,
  c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

document.getElementById("sub").textContent =
  `${DATA.generated} 生成 · ${SESSIONS.length} 段值班时段`;

document.getElementById("totals").innerHTML = (() => {
  const totals = {};
  for (const s of SESSIONS) {
    totals[s.lane] = totals[s.lane] || { hours: 0, sessions: 0, commits: 0 };
    totals[s.lane].hours += (s.endMin - s.startMin) / 60;
    totals[s.lane].sessions += 1;
    totals[s.lane].commits += s.count;
  }
  const rows = Object.keys(totals).sort().map(lane => {
    const t = totals[lane];
    return `<tr><td><b style="color:${COLORS[lane] || "#8a8f9d"}">${esc(lane)}</b>
      <small style="color:#68719a"> ${esc(NAMES[lane] || "")}</small></td>
      <td class="total">${t.hours >= 0.05 ? t.hours.toFixed(1) + " h"
        : Math.round(t.hours * 60) + " 分"}</td>
      <td>${t.sessions} 段</td><td>${t.commits} 提交</td>
      <td>${(t.commits / Math.max(t.hours, 0.1)).toFixed(1)} 提交/时</td></tr>`;
  }).join("");
  return `<table><tr><th>班次</th><th>累计在岗</th><th>时段数</th>
    <th>提交数</th><th>密度</th></tr>${rows}</table>`;
})();

// 甘特：按日分组，横轴为当日 0–24 时
const byDay = {};
for (const s of SESSIONS) {
  (byDay[s.day] = byDay[s.day] || []).push(s);
}
document.getElementById("gantt").innerHTML = Object.keys(byDay).sort()
  .reverse().map(day => {
    const rows = [...Object.keys(COLORS)].map(lane => {
      const bars = (byDay[day] || []).filter(s => s.lane === lane).map(s =>
        `<div class="bar" style="left:${(s.startMin / 1440 * 100).toFixed(2)}%;
          width:${Math.max(0.4, (s.endMin - s.startMin) / 1440 * 100).toFixed(2)}%;
          background:${COLORS[lane]}"
          title="${esc(lane)} ${esc(NAMES[lane] || "")}
 ${esc(s.startHHMM)}–${esc(s.endHHMM)} · ${s.count} 提交"></div>`).join("");
      return `<div class="rowlabel">${lane} ${esc(NAMES[lane] || "")}</div>
        <div class="gantt">${bars}
          <span class="hourlabel" style="left:2%">00</span>
          <span class="hourlabel" style="left:25%">06</span>
          <span class="hourlabel" style="left:50%">12</span>
          <span class="hourlabel" style="left:75%">18</span>
          <span class="hourlabel" style="right:2%">24</span></div>`;
    }).join("");
    return `<div class="dayrow">${esc(day)}</div>${rows}`;
  }).join("") || '<div class="empty">暂无可归属的值班时段</div>';
</script>
</body>
</html>"""


def main() -> None:
    ensure_safe_stdout()
    parser = argparse.ArgumentParser(description="生成班次出勤表页面")
    parser.add_argument("--days", type=int, help="只看最近 N 天（默认全部）")
    parser.add_argument("--out", default="site", help="输出目录（默认 site/）")
    parser.add_argument("--serve", action="store_true",
                        help="生成后起本地服务预览")
    parser.add_argument("--port", type=int, default=8803)
    args = parser.parse_args()

    repo = Path.cwd()
    try:
        run_git(repo, "rev-parse", "--git-dir")
    except RuntimeError:
        sys.exit("当前目录不是 git 仓库。")
    repo_root = Path(run_git(repo, "rev-parse", "--show-toplevel").strip())

    commits = collect_commits(repo_root, args.days)
    sessions = []
    for s in detect_sessions(commits):
        day = s["start"].strftime("%Y-%m-%d")
        sessions.append({
            "lane": s["lane"], "day": day,
            "startMin": s["start"].hour * 60 + s["start"].minute,
            "endMin": s["end"].hour * 60 + s["end"].minute,
            "startHHMM": s["start"].strftime("%H:%M"),
            "endHHMM": s["end"].strftime("%H:%M"),
            "count": s["count"],
        })

    data = {
        "generated": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "sessions": sessions,
    }
    out_dir = (repo_root / args.out).resolve()
    try:
        out_dir.relative_to(repo_root.resolve())
    except ValueError:
        sys.exit(f"--out 必须是仓库内的相对路径，收到: {args.out!r}")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "shifts.html"
    out_path.write_text(build_html(data), encoding="utf-8")
    print(f"出勤表已生成: {out_path.relative_to(repo_root).as_posix()}"
          f"（{len(sessions)} 段值班时段）")

    if args.serve:
        import http.server
        handler = functools.partial(
            http.server.SimpleHTTPRequestHandler, directory=str(out_dir))
        print(f"serving {out_dir} at http://127.0.0.1:{args.port}/shifts.html"
              " (Ctrl+C 退出)")
        http.server.ThreadingHTTPServer(
            ("127.0.0.1", args.port), handler).serve_forever()


if __name__ == "__main__":
    main()
