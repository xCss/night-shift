#!/usr/bin/env python3
"""夜班图书馆——夜班系统全部文档的聚合阅读器（HTML+JS，GitHub Pages 可用）。

驾驶舱看状态，图书馆读全文。本工具扫描 memory/、handoff/、logs/ 下的
Markdown，生成 site/docs.html + site/docs-manifest.json（相对路径清单）；
浏览器端 JS 拉取 Markdown、用内置迷你渲染器转 HTML，提供侧栏导航、
全文搜索（客户端过滤）。README.md 也收录，方便 Pages 首页直达。

用法：
    python tools/night_docs.py            # 生成 site/docs.html 与清单
    python tools/night_docs.py --serve    # 本地预览 http://127.0.0.1:8801/docs.html

仅依赖标准库。注意：fetch 相对路径的 Markdown 在 GitHub Pages / 本地
HTTP 服务下工作；直接双击 file:// 打开会被浏览器 CORS 拦截（用 --serve）。
"""

from __future__ import annotations

import argparse
import datetime as dt
import functools
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shift_report import ensure_safe_stdout, run_git  # noqa: E402

COLLECT_DIRS = ("memory", "handoff", "logs")


def collect_docs(repo: Path) -> list[dict]:
    docs = []
    for d in COLLECT_DIRS:
        base = repo / d
        if not base.is_dir():
            continue
        for f in sorted(base.rglob("*.md")):
            if "morning-report" in f.name:
                continue  # 生成物在驾驶舱/晨报里已有入口
            stat = f.stat()
            docs.append({
                "path": f.relative_to(repo).as_posix(),
                "dir": d,
                "size": stat.st_size,
                "mtime": dt.datetime.fromtimestamp(
                    stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
            })
    readme = repo / "README.md"
    if readme.is_file():
        docs.insert(0, {"path": "README.md", "dir": "根目录",
                        "size": readme.stat().st_size,
                        "mtime": dt.datetime.fromtimestamp(
                            readme.stat().st_mtime).strftime("%Y-%m-%d %H:%M")})
    return docs


def build_html(manifest: dict) -> str:
    data_json = json.dumps(manifest, ensure_ascii=False).replace("</", "<\\/")
    return TEMPLATE.replace("__DATA__", data_json)


TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>夜班图书馆</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; margin: 0; }
  body { background:#0b1020; color:#dfe3ee;
         font:15px/1.7 "Segoe UI","Microsoft YaHei",sans-serif;
         display:flex; min-height:100vh; }
  aside { width:300px; flex:none; background:#0d1326;
          border-right:1px solid rgba(255,255,255,.08);
          padding:20px 16px; overflow:auto; height:100vh; position:sticky; top:0; }
  h1 { font-size:19px; margin-bottom:4px; }
  .sub { color:#68719a; font-size:12px; margin-bottom:14px; }
  #search { width:100%; background:rgba(255,255,255,.06); color:#dfe3ee;
            border:1px solid rgba(255,255,255,.15); border-radius:8px;
            padding:7px 10px; font-size:14px; margin-bottom:12px; }
  .group { color:#8a93b2; font-size:12px; letter-spacing:1px;
           margin:14px 0 4px; text-transform:uppercase; }
  .doc { display:block; padding:6px 10px; border-radius:7px; cursor:pointer;
         color:#c6cde4; font-size:13.5px; }
  .doc:hover { background:rgba(255,255,255,.07); }
  .doc.active { background:#5b6cff; color:#fff; }
  .doc small { display:block; color:#68719a; font-size:11px; }
  .doc.hidden { display:none; }
  main { flex:1; padding:34px 44px; max-width:900px; }
  #content h1 { font-size:26px; margin:18px 0 12px; }
  #content h2 { font-size:20px; margin:22px 0 10px; color:#aeb8dd;
                border-left:3px solid #5b6cff; padding-left:10px; }
  #content h3 { font-size:16px; margin:16px 0 8px; color:#aeb8dd; }
  #content p { margin:10px 0; }
  #content ul, #content ol { margin:10px 0 10px 24px; }
  #content li { margin:4px 0; }
  #content code { background:rgba(255,255,255,.09); padding:1px 6px;
                  border-radius:5px; font-size:13px; color:#a8d5ff; }
  #content pre { background:rgba(0,0,0,.4); border-radius:10px; padding:14px;
                 overflow:auto; margin:12px 0; }
  #content pre code { background:none; padding:0; color:#c8e0ff; }
  #content blockquote { border-left:3px solid #5b6cff; padding:4px 14px;
                        color:#9aa3c4; margin:10px 0; background:rgba(91,108,255,.06); }
  #content table { border-collapse:collapse; margin:12px 0; }
  #content th, #content td { border:1px solid rgba(255,255,255,.15);
                             padding:5px 12px; font-size:14px; }
  #content hr { border:none; border-top:1px solid rgba(255,255,255,.12); margin:18px 0; }
  #content a { color:#9db4ff; }
  .meta { color:#68719a; font-size:12.5px; margin-bottom:18px; }
  .back { color:#9db4ff; cursor:pointer; font-size:13px; }
  .loading { color:#68719a; }
  footer { color:#5d6688; font-size:12px; margin-top:40px; text-align:center; }
</style>
</head>
<body>
<aside>
  <h1>📚 夜班图书馆</h1>
  <div class="sub" id="sub"></div>
  <input id="search" placeholder="筛选文档标题…">
  <div id="toc"></div>
</aside>
<main>
  <div id="welcome">
    <h1>📚 夜班图书馆</h1>
    <p class="meta">左侧选择一份文档阅读；搜索框按标题过滤。</p>
    <p>驾驶舱（site/index.html）看系统状态，这里读全部细节：
       长期记忆、项目状态、各班次交接、每日日志。</p>
  </div>
  <div id="content" style="display:none">
    <span class="back" id="back">← 返回书架</span>
    <div class="meta" id="docmeta"></div>
    <div id="body"></div>
  </div>
  <footer><a href="index.html" style="color:#9db4ff">🎛️ 驾驶舱</a> · <a href="history.html" style="color:#9db4ff">📅 大事记</a><a href="shifts.html" style="color:#9db4ff">🛰️ 出勤表</a><a href="game.html" style="color:#9db4ff">🔮 模拟器</a> · night-shift autopilot · tools/night_docs.py · Markdown 客户端渲染，GitHub Pages 即开即用</footer>
</main>
<script>
const DATA = __DATA__;

const esc = s => String(s).replace(/[&<>"']/g,
  c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

// 迷你 Markdown 渲染器：标题/列表/围栏代码/引用/表格/行内样式/链接。
// 逐行状态机；先转义一切 HTML，再按语法包标签，故无注入面。
function renderMd(src) {
  const lines = src.replace(/\r\n/g, "\n").split("\n");
  const out = [];
  let inCode = false, listType = null;
  const closeList = () => { if (listType) { out.push(`</${listType}>`); listType = null; } };
  const inline = s => s
    .replace(/`([^`]+)`/g, (_, c) => "<code>" + c + "</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>")
    .replace(/~~([^~]+)~~/g, "<del>$1</del>")
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g,
      (m, t, u) => u.startsWith("http") ? `<a href="${u}">${t}</a>` : m);
  for (const raw of lines) {
    const line = esc(raw);
    if (line.startsWith("```")) {
      closeList();
      out.push(inCode ? "</code></pre>" : "<pre><code>");
      inCode = !inCode;
      continue;
    }
    if (inCode) { out.push(line); continue; }
    const h = line.match(/^(#{1,4}) (.*)$/);
    if (h) { closeList(); out.push(`<h${h[1].length}>${inline(h[2])}</h${h[1].length}>`); continue; }
    if (/^\s*[-*] /.test(line)) {
      if (listType !== "ul") { closeList(); out.push("<ul>"); listType = "ul"; }
      out.push(`<li>${inline(line.replace(/^\s*[-*] /, ""))}</li>`); continue;
    }
    if (/^\s*\d+\. /.test(line)) {
      if (listType !== "ol") { closeList(); out.push("<ol>"); listType = "ol"; }
      out.push(`<li>${inline(line.replace(/^\s*\d+\. /, ""))}</li>`); continue;
    }
    closeList();
    if (line.startsWith("&gt; ")) { out.push(`<blockquote>${inline(line.slice(5))}</blockquote>`); continue; }
    if (/^\s*\|.*\|\s*$/.test(line)) {
      const cells = line.split("|").slice(1, -1).map(c => c.trim());
      if (cells.every(c => /^:?-+:?$/.test(c))) continue;  // 分隔行
      out.push(`<tr>${cells.map(c => `<td style="padding:4px 12px">${inline(c)}</td>`).join("")}</tr>`);
      continue;
    }
    if (line.trim() === "---") { out.push("<hr>"); continue; }
    if (line.trim() === "") continue;
    out.push(`<p>${inline(line)}</p>`);
  }
  closeList();
  if (inCode) out.push("</code></pre>");
  return out.join("\n").replace(/(<tr>[\s\S]*?<tr>)/, "<table>$1")
    .replace(/(<tr>(?:(?!<\/table>).)*<\/tr>)(?!.*<table)/s, "$1</table>");
}

let currentFetch = null;
async function openDoc(path, mtime, size) {
  document.getElementById("welcome").style.display = "none";
  const content = document.getElementById("content");
  content.style.display = "block";
  const body = document.getElementById("body");
  body.innerHTML = '<div class="loading">加载中…</div>';
  document.getElementById("docmeta").textContent =
    `${path} · ${mtime} · ${(size / 1024).toFixed(1)} KB`;
  try {
    if (currentFetch) currentFetch.abort();
    currentFetch = new AbortController();
    const resp = await fetch("../" + path, { signal: currentFetch.signal });
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    body.innerHTML = renderMd(await resp.text());
  } catch (e) {
    if (e.name === "AbortError") return;
    body.innerHTML = `<p>加载失败：${esc(String(e))}<br>
      本页需要 HTTP 服务（GitHub Pages 或 --serve 本地预览），直接双击
      file:// 打开会被浏览器 CORS 拦截。</p>`;
  }
  content.scrollIntoView();
  document.querySelectorAll(".doc").forEach(d =>
    d.classList.toggle("active", d.dataset.path === path));
}

function buildToc(filter) {
  const toc = document.getElementById("toc");
  const groups = {};
  for (const d of DATA.docs) {
    if (filter && !d.path.toLowerCase().includes(filter)) continue;
    (groups[d.dir] = groups[d.dir] || []).push(d);
  }
  toc.innerHTML = Object.entries(groups).map(([dir, docs]) =>
    `<div class="group">${esc(dir)}</div>` + docs.map(d =>
      `<span class="doc" data-path="${esc(d.path)}">${esc(d.path.split("/").pop())}
       <small>${esc(d.mtime)} · ${(d.size / 1024).toFixed(1)} KB</small></span>`).join("")
  ).join("") || '<div class="doc hidden"></div><div class="group">无匹配文档</div>';
}
document.getElementById("toc").addEventListener("click", e => {
  const doc = e.target.closest(".doc");
  if (!doc || !doc.dataset.path) return;
  const meta = DATA.docs.find(d => d.path === doc.dataset.path);
  openDoc(doc.dataset.path, meta.mtime, meta.size);
});
document.getElementById("search").addEventListener("input", e =>
  buildToc(e.target.value.toLowerCase()));
document.getElementById("back").addEventListener("click", () => {
  document.getElementById("content").style.display = "none";
  document.getElementById("welcome").style.display = "block";
});

document.getElementById("sub").textContent =
  `${DATA.docs.length} 份文档 · 生成于 ${DATA.generated}`;
buildToc("");
</script>
</body>
</html>"""


def main() -> None:
    ensure_safe_stdout()
    parser = argparse.ArgumentParser(description="生成夜班图书馆页面")
    parser.add_argument("--out", default="site", help="输出目录（默认 site/）")
    parser.add_argument("--serve", action="store_true",
                        help="生成后起本地服务预览")
    parser.add_argument("--port", type=int, default=8801)
    args = parser.parse_args()

    repo = Path.cwd()
    try:
        run_git(repo, "rev-parse", "--git-dir")
    except RuntimeError:
        sys.exit("当前目录不是 git 仓库。")
    repo_root = Path(run_git(repo, "rev-parse", "--show-toplevel").strip())

    manifest = {
        "generated": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "docs": collect_docs(repo_root),
    }
    out_dir = (repo_root / args.out).resolve()
    try:
        out_dir.relative_to(repo_root.resolve())
    except ValueError:
        sys.exit(f"--out 必须是仓库内的相对路径，收到: {args.out!r}")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "docs.html").write_text(build_html(manifest), encoding="utf-8")
    (out_dir / "docs-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"图书馆已生成: {(out_dir / 'docs.html').relative_to(repo_root).as_posix()}"
          f"（{len(manifest['docs'])} 份文档）")

    if args.serve:
        import http.server
        handler = functools.partial(
            http.server.SimpleHTTPRequestHandler, directory=str(repo_root))
        print(f"serving repo root at http://127.0.0.1:{args.port}/site/docs.html"
              " (Ctrl+C 退出)")
        http.server.ThreadingHTTPServer(
            ("127.0.0.1", args.port), handler).serve_forever()


if __name__ == "__main__":
    main()
