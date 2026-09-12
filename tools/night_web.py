#!/usr/bin/env python3
"""夜班驾驶舱——夜班系统的可视化页面（HTML+JS，GitHub Pages 可用）。

数据由本工具采集并内嵌进一个自包含的 site/index.html；渲染与交互
（班次筛选、悬停详情）全部由浏览器端 JS 完成。无外部依赖、无构建
步骤、只用相对路径——把仓库推到 GitHub Pages（选择 site/ 目录）或
本地双击打开都能用。

用法：
    python tools/night_web.py            # 生成 site/index.html
    python tools/night_web.py --serve    # 生成并起本地服务预览
    python tools/night_web.py --hours 12

仅依赖标准库与 git。
"""

from __future__ import annotations

import argparse
import datetime as dt
import functools
import html
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from memory_check import find_pending_items  # noqa: E402
from shift_report import (  # noqa: E402
    collect_numstat,
    ensure_safe_stdout,
    git_since_iso,
    most_recent,
    run_cmd,
    run_git,
)

TAG_RE = re.compile(r"^\[([A-Za-z])\]\s*")
SHIFT_NAMES = {"A": "记忆基建", "B": "棋手联赛", "C": "无聊发明", "D": "记录"}


def collect_commits_full(repo: Path, since_iso: str,
                         limit: int = 200) -> list[dict]:
    out = run_git(repo, "log", f"--since={since_iso}", f"-n{limit}",
                  "--pretty=format:%h%x1f%H%x1f%an%x1f%ad%x1f%s",
                  "--date=iso")
    commits = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split("\x1f")
        if len(parts) == 5:
            m = TAG_RE.match(parts[4])
            lane = m.group(1).upper() if m else "未标记"
            commits.append({
                "hash": parts[0], "author": parts[2],
                "date": parts[3], "subject": parts[4], "lane": lane,
            })
    return list(reversed(commits))  # 时间正序，时间轴从左到右


def remote_sync(repo: Path, branch: str) -> str:
    out = run_git(repo, "rev-list", "--left-right", "--count",
                  f"origin/{branch}...{branch}", check=False).strip()
    try:
        behind_s, ahead_s = out.split()
        ahead, behind = int(ahead_s), int(behind_s)
    except ValueError:
        return "无远程跟踪"
    if not ahead and not behind:
        return "与远程同步"
    parts = []
    if ahead:
        parts.append(f"领先 {ahead} 提交未 push")
    if behind:
        parts.append(f"落后 {behind} 提交")
    return "，".join(parts)


def collect_pending(repo: Path) -> list[dict]:
    pending = []
    for d in ("memory", "handoff", "logs"):
        base = repo / d
        if not base.is_dir():
            continue
        for f in sorted(base.rglob("*.md")):
            if "morning-report" in f.name:
                continue  # 生成物不复述计数
            text = f.read_text(encoding="utf-8", errors="replace")
            rel = f.relative_to(repo).as_posix()
            for lineno, item in find_pending_items(text):
                pending.append({"file": rel, "line": lineno, "item": item})
    return pending


def latest_files(repo: Path, pattern: str, count: int = 3) -> list[str]:
    files = [f for f in repo.glob(pattern) if f.is_file()]
    return [f.relative_to(repo).as_posix()
            for f in sorted(files, key=lambda f: f.stat().st_mtime,
                            reverse=True)[:count]]


def gather_data(repo: Path, since: dt.datetime, moment: dt.datetime) -> dict:
    branch = run_git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()
    commits = collect_commits_full(repo, git_since_iso(since))
    files, added, deleted = collect_numstat(repo, git_since_iso(since))

    code, out = run_cmd("python -m unittest discover -s tests",
                        repo, timeout=300)
    tests_ok = None if "Ran 0 tests" in out else code == 0

    proc = subprocess.run(
        [sys.executable,
         str(Path(__file__).resolve().parent / "memory_check.py")],
        cwd=repo, capture_output=True, text=True, encoding="utf-8",
        errors="replace")

    return {
        "repo": repo.name,
        "generated": moment.strftime("%Y-%m-%d %H:%M"),
        "since": since.strftime("%Y-%m-%d %H:%M"),
        "branch": branch,
        "commits": commits,
        "added": added,
        "deleted": deleted,
        "files": len(files),
        "tests_ok": tests_ok,
        "tests_tail": out.splitlines()[-6:],
        "memory_ok": proc.returncode == 0,
        "pending": collect_pending(repo),
        "remote": remote_sync(repo, branch),
        "handoffs": latest_files(repo, "handoff/*.md"),
        "logs": latest_files(repo, "logs/*.md"),
    }


def build_html(data: dict) -> str:
    # </ 的转义防 </script> 逃逸；显示层转义由 JS 的 esc() 负责
    data_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return TEMPLATE.replace("__DATA__", data_json)


TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>夜班驾驶舱</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; margin: 0; }
  body { background: linear-gradient(160deg,#0b1020,#141b34 60%,#1a1440);
         color:#dfe3ee; font:15px/1.6 "Segoe UI","Microsoft YaHei",sans-serif;
         min-height:100vh; padding:32px; }
  h1 { font-size:26px; letter-spacing:1px; }
  h1 small { color:#8a93b2; font-size:14px; font-weight:normal; margin-left:12px; }
  h2 { font-size:16px; color:#aeb8dd; margin:0 0 12px;
       border-left:3px solid #5b6cff; padding-left:10px; }
  .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(210px,1fr));
          gap:16px; margin:20px 0; }
  .card { background:rgba(255,255,255,.05); border:1px solid rgba(255,255,255,.09);
          border-radius:12px; padding:16px 18px; }
  .card .k { color:#8a93b2; font-size:12px; letter-spacing:1px; }
  .card .v { font-size:22px; margin-top:6px; }
  .v.good { color:#7ce8c1; } .v.bad { color:#ff9ecb; }
  section { background:rgba(255,255,255,.04); border-radius:14px;
            padding:20px 22px; margin:18px 0; border:1px solid rgba(255,255,255,.08); }
  .lane { display:flex; align-items:center; margin:10px 0; }
  .lane-name { width:150px; flex:none; color:#aeb8dd; font-size:13px; }
  .lane-name small { color:#68719a; margin-left:6px; }
  .track { position:relative; flex:1; height:34px; background:rgba(255,255,255,.05);
           border-radius:17px;
           background-image:repeating-linear-gradient(90deg,transparent 0 9%,rgba(255,255,255,.12) 9% 10%); }
  .dot { position:absolute; top:50%; width:13px; height:13px; border-radius:50%;
         transform:translate(-50%,-50%); border:2px solid rgba(0,0,0,.4);
         cursor:pointer; }
  .dot:hover { transform:translate(-50%,-50%) scale(1.6); }
  .track.axis { height:18px; background:none; color:#68719a; font-size:12px; }
  .filters { margin:0 0 12px; }
  .filters button { background:rgba(255,255,255,.07); color:#dfe3ee;
                    border:1px solid rgba(255,255,255,.15); border-radius:14px;
                    padding:3px 14px; margin-right:8px; cursor:pointer; font-size:13px; }
  .filters button.active { background:#5b6cff; border-color:#5b6cff; }
  table { border-collapse:collapse; width:100%; }
  th,td { text-align:left; padding:6px 12px; border-bottom:1px solid rgba(255,255,255,.08); }
  th { color:#8a93b2; font-weight:normal; font-size:13px; }
  .pill { color:#0b1020; padding:2px 10px; border-radius:10px; font-weight:bold; font-size:13px; }
  .pending-item { padding:8px 12px; border-radius:8px; margin:6px 0;
                  background:rgba(255,158,203,.08); }
  .pending-item.ok { background:rgba(124,232,193,.1); }
  .pending-item small { display:block; color:#68719a; font-size:12px; }
  ul { padding-left:20px; } li { margin:4px 0; }
  a { color:#9db4ff; text-decoration:none; } a:hover { text-decoration:underline; }
  code { background:rgba(255,255,255,.08); padding:1px 6px; border-radius:5px; font-size:13px; }
  pre { background:rgba(0,0,0,.35); border-radius:8px; padding:12px; overflow:auto; font-size:12.5px; }
  .empty { color:#68719a; padding:20px; text-align:center; }
  footer { color:#5d6688; font-size:12.5px; margin-top:26px; text-align:center; }
</style>
</head>
<body>
<h1>🌙 夜班驾驶舱 <small id="subtitle"></small></h1>

<div class="grid" id="cards"></div>

<section>
  <h2>提交时间轴</h2>
  <div class="filters" id="filters"></div>
  <div id="lanes"></div>
  <p style="color:#68719a;font-size:12.5px;margin-top:8px">
  悬停气泡查看详情 · 点击上方按钮筛选班次 · 泳道空隙越大说明该班次沉默越久</p>
</section>

<div class="grid">
  <div class="card"><h2>班次贡献</h2><div id="stats"></div></div>
  <div class="card"><h2>待人工确认</h2><div id="pending"></div></div>
</div>

<div class="grid">
  <div class="card"><h2>最新交接文档</h2><ul id="handoffs"></ul></div>
  <div class="card"><h2>最新夜班日志</h2><ul id="logs"></ul></div>
</div>

<section>
  <h2>测试输出（末 6 行）</h2>
  <pre id="tests"></pre>
</section>

<footer><a href="docs.html" style="color:#9db4ff">📚 图书馆</a> · <a href="history.html" style="color:#9db4ff">📅 大事记</a><a href="shifts.html" style="color:#9db4ff">🛰️ 出勤表</a> · night-shift autopilot · 数据由 tools/night_web.py 采集 · 纯静态 HTML+JS，GitHub Pages 即开即用</footer>

<script>
const DATA = __DATA__;

const COLORS = { A:"#7c9cff", B:"#ffb86c", C:"#7ce8c1", D:"#ff9ecb", "未标记":"#8a8f9d" };
const NAMES = { A:"记忆基建", B:"棋手联赛", C:"无聊发明", D:"记录" };
const esc = s => String(s).replace(/[&<>"']/g,
  c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const badge = (ok, yes, no) => ok === null
  ? '<span class="v">未运行</span>'
  : `<span class="v ${ok ? "good" : "bad"}">${ok ? yes : no}</span>`;

document.getElementById("subtitle").textContent =
  `${DATA.repo} · 分支 ${DATA.branch} · 生成于 ${DATA.generated}`;

// 健康度卡片
const cards = [
  ["单元测试", badge(DATA.tests_ok, "✅ 通过", "❌ 失败")],
  ["记忆体检", badge(DATA.memory_ok, "✅ 通过", "❌ 有问题")],
  ["待人工确认", `<span class="v ${DATA.pending.length ? "bad" : "good"}">${DATA.pending.length} 项</span>`],
  ["远程同步", `<div class="v" style="font-size:15px">${esc(DATA.remote)}</div>`],
  ["本窗口代码量", `<div class="v" style="font-size:15px">+${DATA.added} / -${DATA.deleted}<br>
    <small style="color:#8a93b2">${DATA.files} 个文件 · ${DATA.commits.length} 提交</small></div>`],
];
document.getElementById("cards").innerHTML = cards.map(
  ([k, v]) => `<div class="card"><div class="k">${k}</div>${v}</div>`).join("");

// 时间轴：按班次泳道，气泡按时间定位
const times = DATA.commits
  .map(c => Date.parse(c.date)).filter(t => !isNaN(t));
const tMin = times.length ? Math.min(...times) : 0;
const tMax = times.length ? Math.max(...times) : 1;
const lanes = {};
for (const c of DATA.commits) (lanes[c.lane] = lanes[c.lane] || []).push(c);

function laneOrder() {
  const keys = Object.keys(lanes).filter(k => k !== "未标记").sort();
  if (lanes["未标记"]) keys.push("未标记");
  return keys;
}
function renderLanes(active) {
  const el = document.getElementById("lanes");
  if (!times.length) { el.innerHTML = '<div class="empty">窗口内没有提交</div>'; return; }
  const fmt = t => { const d = new Date(t);
    return `${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")} ${String(d.getHours()).padStart(2,"0")}:${String(d.getMinutes()).padStart(2,"0")}`; };
  const span = Math.max(tMax - tMin, 1);
  el.innerHTML = laneOrder().filter(k => active === "全部" || k === active)
    .map(lane => {
      const dots = lanes[lane].map(c => {
        const t = Date.parse(c.date);
        const pos = isNaN(t) ? 0 : Math.max(0, Math.min(100, (t - tMin) / span * 100));
        return `<span class="dot" style="left:${pos.toFixed(2)}%;background:${COLORS[lane]}"
          title="${esc(c.hash)} ${esc((c.date || "").slice(5, 16))} ${esc(c.subject)}"></span>`;
      }).join("");
      const name = NAMES[lane] || "未知";
      return `<div class="lane"><div class="lane-name">${esc(lane)}
        <small>${esc(name)}</small></div><div class="track">${dots}</div></div>`;
    }).join("")
    + `<div class="lane"><div class="lane-name"></div><div class="track axis">
       <span style="position:absolute;left:0">${esc(fmt(tMin))}</span>
       <span style="position:absolute;right:0">${esc(fmt(tMax))}</span></div></div>`;
}
const filters = document.getElementById("filters");
const btns = ["全部", ...laneOrder()].map(l =>
  `<button data-l="${esc(l)}">${esc(l)}</button>`).join("");
filters.innerHTML = btns;
let activeLane = "全部";
filters.addEventListener("click", e => {
  if (e.target.tagName !== "BUTTON") return;
  activeLane = e.target.dataset.l;
  filters.querySelectorAll("button").forEach(b =>
    b.classList.toggle("active", b.dataset.l === activeLane));
  renderLanes(activeLane);
});
filters.querySelector("button").classList.add("active");
renderLanes("全部");

// 班次贡献
document.getElementById("stats").innerHTML = `<table>
  <tr><th>班次</th><th>提交数</th></tr>
  ${laneOrder().map(l => `<tr><td>
    <span class="pill" style="background:${COLORS[l]}">${esc(l)}</span></td>
    <td>${lanes[l].length}</td></tr>`).join("")}</table>`
  || '<div class="empty">无</div>';

// 待人工确认
document.getElementById("pending").innerHTML = DATA.pending.length
  ? DATA.pending.map(p =>
      `<div class="pending-item">⚠️ ${esc(p.item)}<small>${esc(p.file)}:${p.line}</small></div>`).join("")
  : '<div class="pending-item ok">✅ 无待人工确认事项</div>';

// 文档与日志入口（相对路径，GitHub Pages 可直接点开）
const fileLink = f => `<li><a href="../${esc(f)}"><code>${esc(f)}</code></a></li>`;
document.getElementById("handoffs").innerHTML =
  DATA.handoffs.map(fileLink).join("") || "<li>暂无</li>";
document.getElementById("logs").innerHTML =
  DATA.logs.map(fileLink).join("") || "<li>暂无</li>";

// 测试输出
document.getElementById("tests").textContent =
  DATA.tests_tail.length ? DATA.tests_tail.join("\n") : "（未运行）";
</script>
</body>
</html>"""


def main() -> None:
    ensure_safe_stdout()
    parser = argparse.ArgumentParser(description="生成夜班驾驶舱页面")
    window = parser.add_mutually_exclusive_group()
    window.add_argument("--since", help="起点时间 HH:MM（取该时刻最近一次出现）")
    window.add_argument("--hours", type=float, help="覆盖最近 N 小时")
    parser.add_argument("--out", default="site", help="输出目录（默认 site/）")
    parser.add_argument("--serve", action="store_true",
                        help="生成后起本地服务预览")
    parser.add_argument("--port", type=int, default=8800)
    args = parser.parse_args()

    repo = Path.cwd()
    try:
        run_git(repo, "rev-parse", "--git-dir")
    except RuntimeError:
        sys.exit("当前目录不是 git 仓库。")
    repo_root = Path(run_git(repo, "rev-parse", "--show-toplevel").strip())

    moment = dt.datetime.now()
    if args.since:
        hh, mm = (int(x) for x in args.since.split(":"))
        since = most_recent(hh, mm, moment)
    elif args.hours:
        since = moment - dt.timedelta(hours=args.hours)
    else:
        since = most_recent(23, 5, moment)

    data = gather_data(repo_root, since, moment)
    out_dir = (repo_root / args.out).resolve()
    try:
        out_dir.relative_to(repo_root.resolve())
    except ValueError:
        sys.exit(f"--out 必须是仓库内的相对路径，收到: {args.out!r}")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "index.html"
    out_path.write_text(build_html(data), encoding="utf-8")
    print(f"驾驶舱已生成: {out_path.relative_to(repo_root).as_posix()}")

    if args.serve:
        import http.server
        handler = functools.partial(
            http.server.SimpleHTTPRequestHandler, directory=str(out_dir))
        print(f"serving {out_dir} at http://127.0.0.1:{args.port}/index.html"
              " (Ctrl+C 退出)")
        # ThreadingHTTPServer：单线程版会被浏览器的 keep-alive 连接卡死
        http.server.ThreadingHTTPServer(
            ("127.0.0.1", args.port), handler).serve_forever()


if __name__ == "__main__":
    main()
