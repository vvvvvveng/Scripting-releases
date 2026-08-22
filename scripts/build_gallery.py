#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动扫描仓库中的 .scripting 脚本，生成作品合集：
  1. README.md  末尾追加作品表格（幂等，重复运行只替换列表部分）
  2. gallery.html  独立画廊页面（适配 GitHub Pages）

由 .github/workflows/generate.yml 每次 push 后自动执行。
"""
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

REPO = "vvvvveng/Scripting-releases"
BRANCH = "main"
SCRIPT_EXT = ".scripting"
IMAGE_DIR = Path("项目展示图")
# 文件名包含这些关键词的脚本不展示
SKIP_KEYWORDS = ["请勿下载"]


def import_url(file_name: str) -> str:
    """构造 Scripting 一键导入链接（带毫秒时间戳防缓存）。"""
    raw = (
        f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/{file_name}"
        f"?t={int(time.time() * 1000)}"
    )
    payload = quote(f'["{raw}"]', safe="")
    return f"https://scripting.fun/import_scripts?urls={payload}"


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
        key=lambda p: p.name,
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
            else "--"
        )
        file_rel = quote(str(e["file"]), safe="/")
        rows.append(
            f"| {img_md} | **{e['name']}** | {e['size']} | [一键导入]({import_url(str(e['file']))}) |"
        )

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    block = (
        "<!-- AUTO-GENERATED-START -->\n"
        "## 📦 作品合集\n\n"
        f"> 由 GitHub Actions 自动生成 · 共 {len(entries)} 件作品 · 更新于 {now}\n\n"
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
        cards.append(
            '\n      <a class="card" href="{}" target="_blank">\n'
            '        <div class="thumb">{}</div>\n'
            '        <div class="meta">\n'
            '          <div class="name">{}</div>\n'
            '          <div class="size">{}</div>\n'
            "        </div>\n"
            "      </a>".format(href, thumb, e["name"], e["size"])
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
  header { padding: 40px 20px 24px; text-align: center; }
  header h1 { margin: 0 0 8px; font-size: 28px; }
  header p { margin: 0; color: #8b949e; font-size: 14px; }
  .count { display: inline-block; margin-top: 12px; padding: 4px 14px;
           background: rgba(35,134,54,.13); color: #3fb950; border: 1px solid rgba(35,134,54,.33);
           border-radius: 20px; font-size: 13px; }
  .gallery { max-width: 1080px; margin: 0 auto; padding: 8px 20px 60px;
             display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 20px; }
  .card { display: block; background: #161b22; border: 1px solid #30363d;
          border-radius: 12px; overflow: hidden; text-decoration: none; color: inherit;
          transition: transform .15s, border-color .15s; }
  .card:hover { transform: translateY(-4px); border-color: #3fb950; }
★ .thumb { height: 340px; background: #0d1117; display: flex; align-items: center; justify-content: center; overflow: hidden; }
★ .thumb img { width: 100%; height: 100%; object-fit: contain; }
  .noimg { font-size: 48px; opacity: .4; }
  .meta { display: flex; align-items: center; justify-content: space-between; padding: 12px 14px; }
  .name { font-size: 15px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .size { color: #8b949e; font-size: 12px; flex-shrink: 0; margin-left: 10px; }
  footer { text-align: center; color: #484f58; font-size: 12px; padding-bottom: 40px; }
</style>
</head>
<body>
<header>
  <h1>🛠 Scripting 作品合集</h1>
  <p>由 GitHub Actions 自动生成 · 每次推送脚本后自动更新</p>
  <span class="count">共 __COUNT__ 件作品</span>
</header>
<div class="gallery">__CARDS__
</div>
<footer>Generated by GitHub Actions · vvvvvveng/Scripting-releases</footer>
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