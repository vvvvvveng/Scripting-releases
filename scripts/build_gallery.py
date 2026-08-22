#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动扫描仓库中的 .scripting 脚本，生成作品合集：
  1. README.md  末尾追加作品表格（幂等，重复运行只替换列表部分）
  2. gallery.html  独立画廊页面（适配 GitHub Pages，含搜索框）

由 .github/workflows/generate.yml 每次 push 后自动执行。
"""
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

REPO = "vvvvveng/Scripting-releases"
BRANCH = "main"
SCRIPT_EXT = ".scripting"
IMAGE_DIR = Path("项目展示图")
# 文件名包含这些关键词的脚本不展示
SKIP_KEYWORDS = ["请勿下载"]
# 置顶脚本：名字包含这些关键词的排在最前面（可多写几个，越靠前越优先）
PIN_KEYWORDS = ["脚本管理工具"]


def import_url(file_name: str) -> str:
    """构造 Scripting 一键导入链接。

    下载地址走 github.io 域名（Pages 已启用），
    国内网络可正常访问，避免 raw.githubusercontent.com 被墙导致下载失败。
    """
    raw = f"https://vvvvvveng.github.io/Scripting-releases/{file_name}"
    payload = quote(f'["{raw}"]', safe="")
    return f"https://scripting.fun/import_scripts?urls={payload}"


def last_commit_time(file_name: str) -> int:
    """返回该文件最近一次提交的时间戳（秒）。

    Actions 里 git checkout 后所有文件 mtime 都相同，
    所以用 git log 取真实修改时间；取不到时退回文件系统 mtime。
    """
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%ct", "--", file_name],
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
        if out:
            return int(out)
    except Exception:
        pass
    try:
        return int(Path(file_name).stat().st_mtime)
    except Exception:
        return 0


def human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{n} B"


def collect_entries():
    """收集根目录 .scripting 文件，并匹配项目展示图目录里的同名图片。"""
    scripts = sorted(
        (
            p
            for p in Path(".").iterdir()
            if p.is_file()
            and p.suffix.lower() == SCRIPT_EXT
            and not any(k in p.name for k in SKIP_KEYWORDS)
        ),
        key=lambda p: (
            min(
                (i for i, k in enumerate(PIN_KEYWORDS) if k in p.stem),
                default=len(PIN_KEYWORDS),
            ),
            p.name,
        ),
    )

    entries = []
    for s in scripts:
        img = None
        for ext in (".png", ".jpg", ".jpeg", ".gif"):
            c = IMAGE_DIR / (s.stem + ext)
            if c.exists():
                img = c
                break
        entries.append(
            {
                "name": s.stem,
                "file": s,
                "size": human_size(s.stat().st_size),
                "img": img,
            }
        )
    return entries


def update_readme(entries):
    readme = Path("README.md")
    original = readme.read_text(encoding="utf-8") if readme.exists() else ""
    # 幂等：先移除旧的作品列表，只保留介绍部分
    original = re.sub(
        r"<!-- AUTO-GENERATED-START -->.*?<!-- AUTO-GENERATED-END -->",
        "",
        original,
        flags=re.S,
    ).rstrip() + "\n\n"

    rows = []
    for e in entries:
        img_md = (
            f"![{e['name']}]({quote(str(e['img']), safe='/')})"
            if e["img"]
            else "—"
        )
        file_rel = quote(str(e["file"]), safe="/")
        rows.append(
            f"| {img_md} | **{e['name']}** | {e['size']} | [一键导入]({import_url(str(e['file']))}) |"
        )

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    block = (
        "<!-- AUTO-GENERATED-START -->\n"
        "## 📦 作品合集\n\n"
        f"> 由 WWWeng🐝 维护 · 共 {len(entries)} 件作品 · 更新于 {now}\n\n"
        "| 展示 | 名称 | 大小 | 下载 |\n"
        "| --- | --- | --- | --- |\n"
        + "\n".join(rows)
        + "\n\n<!-- AUTO-GENERATED-END -->\n"
    )

    readme.write_text(original + block, encoding="utf-8")
    print(f"✅ README.md 已更新，共 {len(entries)} 件作品")


def write_gallery(entries):
    # 图片用相对路径（gallery.html 与 项目展示图/ 同处仓库根目录），
    # 这样在 GitHub Pages 上图片走 github.io 域名加载，国内访问更稳定。
    # 卡片点击跳转 Scripting 一键导入页。

    cards = []
    for e in entries:
        if e["img"]:
            thumb = f'<img src="{quote(str(e["img"]), safe="/")}" alt="{e["name"]}" loading="lazy">'
        else:
            thumb = '<div class="noimg">🖥️</div>'
        href = import_url(str(e["file"]))
        mtime = last_commit_time(str(e["file"]))
        cards.append(
            '\n      <a class="card" href="{}" data-mtime="{}" target="_blank">\n'
            '        <div class="thumb">{}</div>\n'
            '        <div class="meta">\n'
            '          <div class="name">{}</div>\n'
            '          <div class="size">{}</div>\n'
            "        </div>\n"
            "      </a>".format(href, mtime, thumb, e["name"], e["size"])
        )

    html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Scripting 作品合集</title>
<style>
  * { box-sizing: border-box; }
  body { margin: 0; font-family: -apple-system, "PingFang SC", "Helvetica Neue", sans-serif;
         background: #0d1117; color: #e6edf3; }
  header { position: relative; padding: 58px 20px 24px; text-align: center; }
  header h1 { margin: 0 0 8px; font-size: 28px; }
  header p { margin: 0; color: #8b949e; font-size: 14px; }
  .btn-group { position: absolute; top: 14px; right: 24px; display: flex; gap: 14px; }
  .btn { display: inline-flex; align-items: center; gap: 6px; padding: 6px 14px;
         color: #c9d1d9; font-size: 12px; font-weight: 500; text-decoration: none;
         background: rgba(255,255,255,.05); border: 1px solid rgba(255,255,255,.14);
         border-radius: 8px; backdrop-filter: blur(8px);
         transition: background .15s, border-color .15s, color .15s; }
  .btn:hover { background: rgba(255,255,255,.12); border-color: rgba(255,255,255,.28); color: #fff; }
  .toolbar { max-width: 1080px; margin: 0 auto 20px; padding: 0 20px;
             display: flex; justify-content: space-between; align-items: center; gap: 12px; }
  .search { width: 320px; padding: 8px 14px; background: #161b22; color: #e6edf3;
            border: 1px solid #30363d; border-radius: 8px; font-size: 16px; outline: none;
            transition: border-color .15s, box-shadow .15s; }
  .search:focus { border-color: #3fb950; box-shadow: 0 0 0 3px rgba(63,185,80,.15); }
  .search::placeholder { color: #8b949e; }
  .sort { padding: 8px 12px; background: #161b22; color: #e6edf3;
          border: 1px solid #30363d; border-radius: 8px; font-size: 13px; outline: none;
          cursor: pointer; transition: border-color .15s; }
  .sort:focus { border-color: #3fb950; }
  .gallery { max-width: 1080px; margin: 0 auto; padding: 8px 20px 60px;
             display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 20px; }
  .card { display: block; background: #161b22; border: 1px solid #30363d;
          border-radius: 12px; overflow: hidden; text-decoration: none; color: inherit;
          transition: transform .15s, border-color .15s; }
  .card:hover { transform: translateY(-4px); border-color: #3fb950; }
  .thumb { height: 340px; background: #0d1117; display: flex; align-items: center; justify-content: center; overflow: hidden; }
  .thumb img { width: 100%; height: 100%; object-fit: contain; }
  .noimg { font-size: 48px; opacity: .4; }
  .meta { display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 12px 14px; }
  .name { font-size: 15px; font-weight: 600; text-align: center; overflow: hidden;
          text-overflow: ellipsis; white-space: nowrap; max-width: 100%; }
  .size { color: #8b949e; font-size: 12px; }
  footer { text-align: center; color: #484f58; font-size: 12px; padding-bottom: 40px; }
</style>
</head>
<body>
<header>
  <h1>🛠 Scripting 作品合集</h1>
  <p>由 WWWeng🐝 维护 · 共 __COUNT__ 件作品</p>
  <div class="btn-group">
    <a class="btn" href="https://t.me/wwwengshare" target="_blank">
      <svg viewBox="0 0 24 24" width="13" height="13" fill="currentColor" aria-hidden="true"><path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"/></svg>
      频道
    </a>
    <a class="btn" href="https://github.com/vvvvvveng/Scripting-releases" target="_blank">
      <svg viewBox="0 0 16 16" width="13" height="13" fill="currentColor" aria-hidden="true"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8z"/></svg>
      仓库
    </a>
  </div>
</header>
<div class="toolbar">
  <input id="search" class="search" type="search" placeholder="🔍 搜索脚本…">
  <select id="sort" class="sort">
    <option value="default">默认排序</option>
    <option value="recent">最新修改</option>
  </select>
</div>
<div class="gallery" id="gallery">__CARDS__
</div>
<footer>© WWWeng🐝 · Generated by GitHub Actions · vvvvvveng/Scripting-releases</footer>
<script>
  const gallery = document.getElementById('gallery');
  const input = document.getElementById('search');
  const sortSel = document.getElementById('sort');
  const cards = Array.prototype.slice.call(gallery.querySelectorAll('.card'));
  const originalOrder = cards.slice();

  input.addEventListener('input', function () {
    const q = input.value.trim().toLowerCase();
    cards.forEach(function (card) {
      const name = card.querySelector('.name').textContent.toLowerCase();
      card.style.display = name.indexOf(q) !== -1 ? '' : 'none';
    });
  });

  sortSel.addEventListener('change', function () {
    let ordered;
    if (sortSel.value === 'recent') {
      ordered = cards.slice().sort(function (a, b) {
        return (parseInt(b.dataset.mtime, 10) || 0) - (parseInt(a.dataset.mtime, 10) || 0);
      });
    } else {
      ordered = originalOrder.slice();
    }
    ordered.forEach(function (card) { gallery.appendChild(card); });
  });
</script>
</body>
</html>
"""
    html = html.replace("__COUNT__", str(len(entries))).replace(
        "__CARDS__", "".join(cards)
    )

    Path("gallery.html").write_text(html, encoding="utf-8")
    print("✅ gallery.html 已生成")


def main():
    entries = collect_entries()
    update_readme(entries)
    write_gallery(entries)


if __name__ == "__main__":
    main()