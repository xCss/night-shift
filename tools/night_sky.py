#!/usr/bin/env python3
"""提交星图——把仓库全部提交化作一片夜空（HTML+JS Canvas，Pages 可用）。

每一次提交都是一颗星：横轴是时间，纵轴由提交哈希决定（同一提交永远
在同一位置），颜色代表班次，同班次的星按时间连成星座线。星星以各自
的相位闪烁，偶有流星划过。悬停星上看那颗星的提交详情。

这是夜班系统的浪漫：工作过的痕迹成为天空里永久的光点。

用法：
    python tools/night_sky.py            # 生成 site/sky.html
    python tools/night_sky.py --days 30

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


def collect_stars(repo: Path, days: int | None) -> list[dict]:
    args = ["log", "--pretty=format:%h%x1f%H%x1f%ad%x1f%s", "--date=iso"]
    if days:
        since = (dt.datetime.now() - dt.timedelta(days=days)).strftime(
            "%Y-%m-%dT00:00:00")
        args.insert(1, f"--since={since}")
    out = run_git(repo, *args)
    stars = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split("\x1f")
        if len(parts) == 4:
            m = TAG_RE.match(parts[3])
            stars.append({
                "hash": parts[0], "full": parts[1], "date": parts[2],
                "subject": parts[3],
                "lane": m.group(1).upper() if m else "未标记",
            })
    return list(reversed(stars))  # 时间正序，星座线从左到右


def build_html(data: dict) -> str:
    data_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return TEMPLATE.replace("__DATA__", data_json)


TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>提交星图</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; margin: 0; }
  body { background:#05070f; color:#dfe3ee; overflow:hidden;
         font:15px/1.6 "Segoe UI","Microsoft YaHei",sans-serif; }
  canvas { display:block; }
  .hud { position:fixed; top:20px; left:24px; z-index:2; }
  h1 { font-size:20px; }
  h1 small { color:#8a93b2; font-size:12.5px; font-weight:normal; margin-left:10px; }
  .filters { margin-top:10px; }
  .filters button { background:rgba(255,255,255,.07); color:#dfe3ee;
    border:1px solid rgba(255,255,255,.15); border-radius:14px;
    padding:2px 12px; margin-right:6px; cursor:pointer; font-size:12.5px; }
  .filters button.active { background:#5b6cff; border-color:#5b6cff; }
  .nav { margin-top:12px; font-size:12.5px; }
  .nav a { color:#9db4ff; text-decoration:none; margin-right:10px; }
  #tooltip { position:fixed; display:none; z-index:3; pointer-events:none;
    background:rgba(10,14,30,.92); border:1px solid rgba(124,156,255,.4);
    border-radius:8px; padding:8px 12px; font-size:12.5px; max-width:420px; }
  #tooltip .sub { color:#aeb8dd; }
  #tooltip .meta { color:#68719a; font-size:11.5px; }
</style>
</head>
<body>
<canvas id="sky"></canvas>
<div class="hud">
  <h1>✨ 提交星图 <small id="sub"></small></h1>
  <div class="filters" id="filters"></div>
  <div class="nav">
    <a href="index.html">🎛️ 驾驶舱</a><a href="docs.html">📚 图书馆</a>
    <a href="history.html">📅 大事记</a><a href="shifts.html">🛰️ 出勤表</a>
  </div>
</div>
<div id="tooltip"></div>

<script>
const DATA = __DATA__;

const COLORS = { A:"#7c9cff", B:"#ffb86c", C:"#7ce8c1", D:"#ff9ecb",
                 "未标记":"#b9c4e0" };
let activeLane = "全部";

// 稳定伪随机：同一提交永远在同一片天空的同一位置
function hashRand(str, salt) {
  let h = 2166136261 ^ salt;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return ((h >>> 0) % 100000) / 100000;
}

const canvas = document.getElementById("sky");
const ctx = canvas.getContext("2d");
let W = 0, H = 0;
let stars = [];   // {x,y,r,color,phase,commit}
const lines = []; // {x1,y1,x2,y2,color}

function layout() {
  W = canvas.width = innerWidth;
  H = canvas.height = innerHeight;
  const times = DATA.stars
    .map(s => Date.parse(s.date)).filter(t => !isNaN(t));
  const tMin = times.length ? Math.min(...times) : 0;
  const tMax = times.length ? Math.max(...times) : 1;
  const span = Math.max(tMax - tMin, 1);
  const marginX = 40, marginY = 90;
  stars = DATA.stars.map(s => {
    const t = Date.parse(s.date);
    const x = marginX + (isNaN(t) ? 0 : (t - tMin) / span) * (W - marginX * 2);
    const y = marginY + hashRand(s.full, 7) * (H - marginY * 2);
    const tw = 1.6 + hashRand(s.full, 13) * 2.2;
    return { x, y, r: tw, color: COLORS[s.lane] || "#b9c4e0",
             phase: hashRand(s.full, 29) * Math.PI * 2,
             commit: s };
  });
  // 星座线：同班次相邻提交按时间相连
  lines.length = 0;
  const byLane = {};
  for (const s of DATA.stars) (byLane[s.lane] = byLane[s.lane] || []).push(s);
  for (const lane in byLane) {
    const cs = byLane[lane];
    for (let i = 1; i < cs.length; i++) {
      const a = stars[DATA.stars.indexOf(cs[i - 1])];
      const b = stars[DATA.stars.indexOf(cs[i])];
      if (a && b) lines.push({ x1: a.x, y1: a.y, x2: b.x, y2: b.y,
                               color: COLORS[lane] });
    }
  }
}

function frame() {
  // 视口晚于脚本就绪（或被调整）时自愈重排；
  // 用 setTimeout 而非 rAF——嵌入式 webview 的 rAF 可能永不触发
  if (W !== innerWidth || H !== innerHeight) layoutAndApply();
  draw(performance.now());
  document.title = `✨ 提交星图 · ${stars.length} 星`;
  setTimeout(frame, 50);
}

function draw(now) {
  ctx.clearRect(0, 0, W, H);
  // 星座线
  for (const l of lines) {
    ctx.strokeStyle = l.color + "22";
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(l.x1, l.y1); ctx.lineTo(l.x2, l.y2); ctx.stroke();
  }
  // 星星（相位闪烁）
  for (const s of stars) {
    const tw = 0.65 + 0.35 * Math.sin(now / 900 + s.phase);
    ctx.globalAlpha = tw;
    ctx.fillStyle = s.color;
    ctx.beginPath(); ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2); ctx.fill();
    ctx.globalAlpha = tw * 0.25;
    ctx.beginPath(); ctx.arc(s.x, s.y, s.r * 3, 0, Math.PI * 2); ctx.fill();
  }
  ctx.globalAlpha = 1;
  requestAnimationFrame(draw);
}

// 流星：每 9~18 秒一颗
function meteor() {
  const x0 = Math.random() * W * 0.7, y0 = Math.random() * H * 0.3;
  const len = 120 + Math.random() * 160;
  const t0 = performance.now();
  function fly() {
    const p = (performance.now() - t0) / 700;
    if (p > 1) return;
    const x = x0 + p * len, y = y0 + p * len * 0.35;
    ctx.strokeStyle = "rgba(220,230,255," + (0.8 * (1 - p)) + ")";
    ctx.lineWidth = 1.4;
    ctx.beginPath(); ctx.moveTo(x, y);
    ctx.lineTo(x - len * 0.08, y - len * 0.08 * 0.35); ctx.stroke();
    setTimeout(fly, 16);
  }
  fly();
  setTimeout(meteor, 9000 + Math.random() * 9000);
}

// 悬停：找最近的星
const tooltip = document.getElementById("tooltip");
canvas.addEventListener("mousemove", e => {
  let best = null, bestD = 18 * 18;
  for (const s of stars) {
    const dx = s.x - e.clientX, dy = s.y - e.clientY, d = dx * dx + dy * dy;
    if (d < bestD) { bestD = d; best = s; }
  }
  if (best) {
    tooltip.style.display = "block";
    tooltip.style.left = (e.clientX + 14) + "px";
    tooltip.style.top = (e.clientY + 14) + "px";
    const c = best.commit;
    tooltip.innerHTML =
      `<div class="sub">${esc(c.subject)}</div>` +
      `<div class="meta">${esc(c.hash)} · ${esc((c.date || "").slice(0, 16))}` +
      ` · ${esc(c.lane)}</div>`;
  } else {
    tooltip.style.display = "none";
  }
});

// 班次筛选
const filters = document.getElementById("filters");
const laneNames = { A:"记忆基建", B:"棋手联赛", C:"无聊发明", D:"记录", "未标记":"未标记" };
const lanes = ["全部", ...new Set(DATA.stars.map(s => s.lane))];
filters.innerHTML = lanes.map(l =>
  `<button data-l="${esc(l)}">${esc(l)}${l === "全部" ? "" : " " + esc(laneNames[l] || "")}</button>`).join("");
filters.addEventListener("click", e => {
  if (e.target.tagName !== "BUTTON") return;
  activeLane = e.target.dataset.l;
  filters.querySelectorAll("button").forEach(b =>
    b.classList.toggle("active", b.dataset.l === activeLane));
  applyFilter();
});
function applyFilter() {
  const visible = DATA.stars.filter(s => activeLane === "全部" || s.lane === activeLane);
  const visSet = new Set(visible);
  stars = stars.filter(s => visSet.has(s.commit));
}
function layoutAndApply() { layout(); applyFilter(); draw(performance.now()); }

addEventListener("resize", layoutAndApply);
try {
document.getElementById("sub").textContent =
  `${DATA.stars.length} 颗星 · ${DATA.repo}`;
window.__skyerr = "none";
} catch (e) { window.__skyerr = "L1: " + (e.stack || String(e)); }
try {
layoutAndApply();
frame();
window.__skyerr += " | L2: none";
} catch (e) { window.__skyerr += " | L2: " + (e.stack || String(e)); }
// 流星依赖 rAF；rAF 不触发的环境里星空保持静态（已同步绘制）
setTimeout(meteor, 5000);
</script>
</body>
</html>"""


def main() -> None:
    ensure_safe_stdout()
    parser = argparse.ArgumentParser(description="生成提交星图页面")
    parser.add_argument("--days", type=int, help="只看最近 N 天（默认全部）")
    parser.add_argument("--out", default="site", help="输出目录（默认 site/）")
    parser.add_argument("--serve", action="store_true",
                        help="生成后起本地服务预览")
    parser.add_argument("--port", type=int, default=8804)
    args = parser.parse_args()

    repo = Path.cwd()
    try:
        run_git(repo, "rev-parse", "--git-dir")
    except RuntimeError:
        sys.exit("当前目录不是 git 仓库。")
    repo_root = Path(run_git(repo, "rev-parse", "--show-toplevel").strip())

    data = {
        "repo": repo_root.name,
        "stars": collect_stars(repo_root, args.days),
    }
    out_dir = (repo_root / args.out).resolve()
    try:
        out_dir.relative_to(repo_root.resolve())
    except ValueError:
        sys.exit(f"--out 必须是仓库内的相对路径，收到: {args.out!r}")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "sky.html"
    out_path.write_text(build_html(data), encoding="utf-8")
    print(f"星图已生成: {out_path.relative_to(repo_root).as_posix()}"
          f"（{len(data['stars'])} 颗星）")

    if args.serve:
        import http.server
        handler = functools.partial(
            http.server.SimpleHTTPRequestHandler, directory=str(out_dir))
        print(f"serving {out_dir} at http://127.0.0.1:{args.port}/sky.html"
              " (Ctrl+C 退出)")
        http.server.ThreadingHTTPServer(
            ("127.0.0.1", args.port), handler).serve_forever()


if __name__ == "__main__":
    main()
