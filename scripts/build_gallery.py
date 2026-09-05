#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动扫描仓库中的 .scripting 脚本，生成作品合集：
  1. README.md  末尾追加作品表格（幂等，重复运行只替换列表部分）
  2. gallery.html  独立画廊页面（适配 GitHub Pages，含搜索框）

由 .github/workflows/generate.yml 每次 push 后自动执行。
"""
import html
import json
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

REPO = "vvvvvveng/Scripting-releases"
BRANCH = "main"
SCRIPT_EXT = ".scripting"
IMAGE_DIR = Path("项目展示图")
# 文件名包含这些关键词的脚本不展示
SKIP_KEYWORDS = ["请勿下载"]
# 置顶脚本：名字包含这些关键词的排在最前面（可多写几个，越靠前越优先）
PIN_KEYWORDS = ["脚本管理工具", "🐝密码管理器"]


def import_url(file_name: str) -> str:
    """构造 Scripting 导入落地页链接（README 用）。

    下载地址走 github.io 域名（Pages 已启用），
    国内网络可正常访问，避免 raw.githubusercontent.com 被墙导致下载失败。
    落地页在桌面浏览器也能打开，适合放在 GitHub 网页上的 README。
    """
    raw = f"https://vvvvvveng.github.io/Scripting-releases/{file_name}"
    payload = quote(f'["{raw}"]', safe="")
    return f"https://scripting.fun/import_scripts?urls={payload}"


def import_scheme_url(file_name: str) -> str:
    """构造 Scripting 一键导入深链（gallery.html 用）。

    与落地页（scripting.fun/import_scripts）不同：深链直接用 scripting:// 自定义
    协议唤起 Scripting 应用导入页，不经过网页跳转。脚本内 WebView 展示 gallery 时，
    只需把非 http(s) 请求交给系统（Safari.openURL）即可正常弹出安装，
    各脚本无需再单独针对 scripting.fun 落地页写拦截逻辑。
    格式与 Scripting 官方 Script.createImportScriptsURLScheme 一致。
    """
    raw = f"https://vvvvvveng.github.io/Scripting-releases/{file_name}"
    payload = quote(f'["{raw}"]', safe="")
    return f"scripting://import_scripts?urls={payload}"


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


def format_time(ts: int) -> str:
    """把时间戳格式化为可读时间（北京时间，到分钟）。"""
    try:
        dt = datetime.fromtimestamp(ts, tz=timezone(timedelta(hours=8)))
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "--"


def read_version(file_name: str) -> str:
    """从 .scripting 包内 script.json 读取版本号，读不到返回空串。"""
    try:
        import zipfile

        with zipfile.ZipFile(file_name) as z:
            for name in z.namelist():
                if name.endswith("script.json"):
                    try:
                        v = json.loads(z.read(name)).get("version")
                    except Exception:
                        continue
                    if v:
                        return str(v)
    except Exception:
        pass
    return ""


def read_meta(file_name: str):
    """读取 .scripting 包内 script.json 的介绍与最近更新说明。

    介绍用 script.json 的 description（或 localizedDescriptions.zh）；
    最近更新说明用自定义字段 changelog（用户手动填写），取不到返回空串。
    """
    try:
        import zipfile

        with zipfile.ZipFile(file_name) as z:
            for name in z.namelist():
                if name.endswith("script.json"):
                    try:
                        data = json.loads(z.read(name))
                    except Exception:
                        continue
                    desc = data.get("description") or ""
                    ld = data.get("localizedDescriptions") or {}
                    if not desc:
                        desc = ld.get("zh") or ld.get("zh-Hans") or ""
                    changelog = data.get("changelog") or data.get("releaseNotes") or ""
                    return {"desc": str(desc), "changelog": str(changelog)}
    except Exception:
        pass
    return {"desc": "", "changelog": ""}


def human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{n} B"


def collect_images(script_stem: str):
    """收集 项目展示图/<脚本名>/ 目录下全部截图，按文件名序号自然排序。

    优先读子目录（支持多图按序号轮播）；子目录不存在或为空时，
    退回旧的平铺命名（项目展示图/<脚本名>.png）单张图。
    """
    imgs = []
    d = IMAGE_DIR / script_stem
    if d.is_dir():
        for p in d.iterdir():
            if p.is_file() and p.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
                imgs.append(p)

    if not imgs:
        for ext in (".png", ".jpg", ".jpeg", ".gif"):
            c = IMAGE_DIR / (script_stem + ext)
            if c.exists():
                imgs.append(c)
                break

    # 自然排序：按文件名中的数字排（1.png、2.png、…、10.png），无数字的按名字排
    def num_key(p: Path):
        m = re.search(r"(\d+)", p.stem)
        if m:
            return (0, int(m.group(1)), p.stem)
        return (1, 0, p.stem)

    imgs.sort(key=num_key)
    return imgs


def collect_entries():
    """收集根目录 .scripting 文件，并匹配项目展示图目录里的截图（可多张）。"""
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
        entries.append(
            {
                "name": s.stem,
                "file": s,
                "size": human_size(s.stat().st_size),
                "imgs": collect_images(s.stem),
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
        first_img = e["imgs"][0] if e["imgs"] else None
        img_md = (
            f"![{e['name']}]({quote(str(first_img), safe='/')})"
            if first_img
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
    # 卡片点击跳转 Scripting 一键导入页，长按卡片预览展示图。
    # 预览用 CSS 背景图而非 <img>：背景图不是"图片"，长按时不会触发
    # iOS 的选中/放大镜/图片菜单，预览图永远清晰原样显示。
    # 更新时间与版本号固定在卡片右下角。
    # 长按卡片预览展示图（长按设定与 2026-08-22 15:27 提交 8ce8e20000 一致：
    # Pointer Events + setPointerCapture，lightbox 用 touch-action:none /
    # user-select:none / pointer-events:none 保证真机长按稳定）。

    cards = []
    for e in entries:
        href = import_scheme_url(str(e["file"]))
        mtime = last_commit_time(str(e["file"]))
        preview = ""
        if e["imgs"]:
            # 每个脚本可有多张展示图（项目展示图/<脚本名>/1.png、2.png…），
            # 全部写进卡片，长按预览时按序轮播
            preview = "\n".join(
                '<img class="preview-src" src="{}" alt="" style="display:none">'.format(quote(str(p), safe="/"))
                for p in e["imgs"]
            )
        cards.append(
            '\n      <a class="card" href="{}" data-mtime="{}" target="_blank">\n'
            '        {}\n'
            '        <div class="meta">\n'
            '          <div class="name">{}</div>\n'
            '          <div class="time-bottom">\n'
            '            <span class="ver">v{}</span>\n'
            '            <span class="time">🕒 {}</span>\n'
            '          </div>\n'
            "        </div>\n"
            "      </a>".format(href, mtime, preview, e["name"], read_version(str(e["file"])), format_time(mtime))
        )

    page = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Scripting 作品合集</title>
<style>
  * { box-sizing: border-box; }
  body { margin: 0; font-family: -apple-system, "PingFang SC", "Helvetica Neue", sans-serif;
         background: #0d1117; color: #e6edf3; }
  header { position: relative; padding: 72px 20px 40px; text-align: center; }
  header h1 { margin: 0 0 8px; font-size: 28px; }
  header .subtitle { position: absolute; top: 22px; right: 24px; margin: 0;
                     color: #6e7681; font-size: 12px; }
  .btn-group { position: absolute; top: 14px; left: 24px; display: flex; gap: 10px; }
  .btn { display: inline-flex; align-items: center; gap: 6px; padding: 6px 14px;
         color: #c9d1d9; font-size: 12px; font-weight: 500; text-decoration: none;
         background: rgba(255,255,255,.05); border: 1px solid rgba(255,255,255,.14);
         border-radius: 8px; backdrop-filter: blur(8px);
         transition: background .15s, border-color .15s, color .15s; }
  .btn:hover { background: rgba(255,255,255,.12); border-color: rgba(255,255,255,.28); color: #fff; }
  .toolbar { max-width: 1080px; margin: 0 auto; padding: 0 20px; }
  .note-row { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-top: 10px; }
  .toolbar .note { margin: 0; color: #6e7681; font-size: 11px; }
  .search { width: 100%; box-sizing: border-box; padding: 8px 14px; background: #161b22; color: #e6edf3;
            border: 1px solid #30363d; border-radius: 8px; font-size: 16px; outline: none;
            transition: border-color .15s, box-shadow .15s; }
  .search:focus { border-color: #3fb950; box-shadow: 0 0 0 3px rgba(63,185,80,.15); }
  .search::placeholder { color: #8b949e; }
  .sort { padding: 8px 12px; background: #161b22; color: #e6edf3;
          border: 1px solid #30363d; border-radius: 8px; font-size: 13px; outline: none;
          cursor: pointer; transition: border-color .15s; }
  .sort:focus { border-color: #3fb950; }
  .gallery { max-width: 1080px; margin: 0 auto; padding: 4px 20px 60px;
             display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 20px; }
  .card { display: block; background: #161b22; border: 1px solid #30363d;
          border-radius: 12px; overflow: hidden; text-decoration: none; color: inherit;
          transition: transform .15s, border-color .15s;
          -webkit-touch-callout: none; -webkit-user-select: none; user-select: none; }
  .card:hover { transform: translateY(-4px); border-color: #3fb950; }
  .meta { position: relative; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 40px 14px 40px; }
  .time-bottom { position: absolute; bottom: 12px; left: 14px; right: 14px; margin-top: 0;
                 color: #6e7681; font-size: 10px;
                 display: flex; align-items: center; justify-content: space-between; }
  .name { font-size: 15px; font-weight: 600; text-align: center; overflow: hidden;
          text-overflow: ellipsis; white-space: nowrap; }
  .ver { display: inline-block; padding: 1px 9px; border-radius: 10px;
         background: rgba(63,185,80,.12); border: 1px solid rgba(63,185,80,.3);
         color: #3fb950; font-size: 11px; font-weight: 600; }
  .icon-btn { display: inline-flex; align-items: center; justify-content: center;
              width: 22px; height: 22px; padding: 0; border: none; background: transparent;
              font-size: 13px; line-height: 1; cursor: pointer; border-radius: 6px;
              color: #c9d1d9; transition: background .15s, transform .1s;
              -webkit-tap-highlight-color: transparent; }
  .icon-btn:hover { background: rgba(255,255,255,.12); color: #fff; }
  .icon-btn:active { transform: scale(.9); }
  .lightbox { position: fixed; inset: 0; background: rgba(0,0,0,.88); display: none;
              align-items: center; justify-content: center; z-index: 99;
              -webkit-touch-callout: none; -webkit-user-select: none; user-select: none;
              touch-action: none; }
  .lightbox.open { display: flex; }
  .lightbox-img { position: absolute; inset: 4%; border-radius: 8px;
                  background-repeat: no-repeat; background-position: center;
                  background-size: contain; box-shadow: 0 10px 40px rgba(0,0,0,.6);
                  pointer-events: none; opacity: 0;
                  transition: opacity .8s ease, transform .8s ease;
                  will-change: opacity, transform; }
  .lightbox-page { position: absolute; bottom: 26px; left: 50%; transform: translateX(-50%);
                   min-width: 46px; text-align: center; padding: 5px 12px; border-radius: 12px;
                   color: #e6edf3; font-size: 12px; font-weight: 600; letter-spacing: .5px;
                   background: rgba(22,27,34,.72); border: 1px solid rgba(255,255,255,.14);
                   -webkit-user-select: none; user-select: none; pointer-events: none;
                   opacity: 0; transition: opacity .15s; }
  .lightbox-page.show { opacity: 1; }
  .modal { position: fixed; inset: 0; background: rgba(0,0,0,.72); display: none;
           align-items: center; justify-content: center; z-index: 120; padding: 24px; }
  .modal.open { display: flex; }
  .modal-box { width: 100%; max-width: 520px; max-height: 78%;
               background: #161b22; border: 1px solid #30363d; border-radius: 14px;
               padding: 18px 20px; display: flex; flex-direction: column; gap: 12px;
               box-shadow: 0 10px 40px rgba(0,0,0,.6); }
  .modal-title { font-size: 16px; font-weight: 700; display: flex; justify-content: space-between;
                 align-items: center; gap: 10px; }
  .modal-body { color: #c9d1d9; font-size: 14px; line-height: 1.65; overflow-y: auto;
                white-space: pre-wrap; word-break: break-word; }
  .modal-close { align-self: flex-end; padding: 6px 16px; border: none; border-radius: 8px;
                 background: rgba(255,255,255,.1); color: #e6edf3; font-size: 13px;
                 cursor: pointer; transition: background .15s; }
  .modal-close:hover { background: rgba(255,255,255,.2); }
  footer { text-align: center; color: #484f58; font-size: 12px; padding-bottom: 40px; }
</style>
</head>
<body>
<header>
  <h1>🛠 Scripting 合集</h1>
  <p class="subtitle">由 WWWeng🐝 维护</p>
  <div class="btn-group">
    <a class="btn" href="https://t.me/wwwengshare">
      <svg viewBox="0 0 24 24" width="13" height="13" fill="currentColor" aria-hidden="true"><path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"/></svg>
      频道
    </a>
    <a class="btn" href="https://github.com/vvvvvveng?tab=repositories">
      <svg viewBox="0 0 16 16" width="13" height="13" fill="currentColor" aria-hidden="true"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8z"/></svg>
      仓库
    </a>
  </div>
</header>
<div class="toolbar">
  <input id="search" class="search" type="search" placeholder="🔍 搜索脚本…">
  <div class="note-row">
    <p class="note">注：长按卡片可预览脚本截图</p>
    <select id="sort" class="sort">
      <option value="default">默认排序</option>
      <option value="recent">最新修改</option>
    </select>
  </div>
</div>
<div class="gallery" id="gallery">__CARDS__
</div>
<div class="lightbox" id="lightbox">
  <div class="lightbox-img" id="lightboxImgA"></div>
  <div class="lightbox-img" id="lightboxImgB"></div>
  <div class="lightbox-page" id="lightboxPage"></div>
</div>
<div class="modal" id="modal">
  <div class="modal-box">
    <div class="modal-title"><span id="modalTitle"></span><button class="icon-btn" id="modalX" title="关闭">✕</button></div>
    <div class="modal-body" id="modalBody"></div>
    <button class="modal-close" id="modalClose">关闭</button>
  </div>
</div>
<footer>© WWWeng🐝 · vvvvvveng/Scripting-releases</footer>
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

  // 信息弹窗：软件介绍 / 最近更新说明
  const modal = document.getElementById('modal');
  const modalTitle = document.getElementById('modalTitle');
  const modalBody = document.getElementById('modalBody');
  function openModal(title, text) {
    modalTitle.textContent = title;
    modalBody.textContent = text;
    modal.classList.add('open');
  }
  function closeModal() { modal.classList.remove('open'); }
  modal.addEventListener('click', function (e) { if (e.target === modal) closeModal(); });
  document.getElementById('modalClose').addEventListener('click', closeModal);
  document.getElementById('modalX').addEventListener('click', closeModal);

  // 长按脚本名 → 全屏轮播预览截图（背景图，无选中/放大行为），松手退出。
  // 一个脚本可有多张展示图（项目展示图/<脚本名>/1.png、2.png…），
  // 长按后按序号自动轮播，底部页码指示当前第几张；单张则静态显示。
  // 用 Pointer Events + setPointerCapture：长按触发后 lightbox 覆盖层出现
  // 会遮挡手指下的卡片，iOS 26 可能因此对触摸序列派发取消/结束事件导致
  // 预览自动关闭；捕获指针后事件强制派发到卡片，遮挡不影响，
  // 按住多久预览就稳定显示多久。
  const lightbox = document.getElementById('lightbox');
  const lightboxImgA = document.getElementById('lightboxImgA');
  const lightboxImgB = document.getElementById('lightboxImgB');
  const lightboxPage = document.getElementById('lightboxPage');
  let pressTimer = null;
  let previewed = false;
  let suppressClick = false;
  let carouselTimer = null;
  let startX = 0, startY = 0;
  let curLayer = null;   // 当前显示的图层（A/B 交替）

  function stopCarousel() {
    if (carouselTimer) { clearInterval(carouselTimer); carouselTimer = null; }
  }

  function closeLightbox() {
    stopCarousel();
    lightbox.classList.remove('open');
    // 重置两层，下次打开从第一张干净开始
    [lightboxImgA, lightboxImgB].forEach(function (el) {
      el.style.transition = 'none';
      el.style.opacity = 0;
      el.style.transform = 'translateX(20px)';
      el.style.backgroundImage = '';
    });
    lightboxPage.classList.remove('show');
    previewed = false;
    curLayer = null;
  }
  lightbox.addEventListener('click', closeLightbox);

  // 显示第 i 张。animate=true 时交叉淡化 + 滑动：
  // 新图从右侧滑入淡入，旧图同时向左滑出淡出，中间无空白，比硬切顺滑。
  function showCarouselImage(imgs, i, animate) {
    const idx = ((i % imgs.length) + imgs.length) % imgs.length;
    if (imgs.length > 1) {
      lightboxPage.textContent = (idx + 1) + ' / ' + imgs.length;
      lightboxPage.classList.add('show');
    }
    const next = (curLayer === lightboxImgA) ? lightboxImgB : lightboxImgA;
    next.style.backgroundImage = "url('" + imgs[idx] + "')";
    if (animate && curLayer) {
      next.style.transition = 'none';            // 先把新图放到起始位（右侧）
      next.style.opacity = 0;
      next.style.transform = 'translateX(20px)';
      void next.offsetWidth;                      // 强制 reflow 提交起始状态
      next.style.transition = '';                 // 恢复过渡
      next.style.opacity = 1;                     // 新图淡入 + 从右滑入
      next.style.transform = 'translateX(0)';
      curLayer.style.opacity = 0;                 // 旧图淡出 + 向左滑出
      curLayer.style.transform = 'translateX(-20px)';
    } else {
      next.style.transition = 'none';
      next.style.opacity = 1;
      next.style.transform = 'translateX(0)';
      next.style.transition = '';
    }
    curLayer = next;
    return idx;
  }

  // 多图则每 2 秒自动切到下一张
  function startCarousel(imgs, from) {
    stopCarousel();
    if (imgs.length <= 1) return;
    let cur = from;
    carouselTimer = setInterval(function () {
      cur = showCarouselImage(imgs, cur + 1, true);
    }, 2000);
  }

  cards.forEach(function (card) {
    const srcEls = card.querySelectorAll('.preview-src');
    if (!srcEls.length) return;
    const imgs = Array.prototype.map.call(srcEls, function (el) { return el.getAttribute('src'); });

    // 只取消未触发的长按计时，不影响已经打开的预览
    function cancelPress() {
      if (pressTimer) { clearTimeout(pressTimer); pressTimer = null; }
    }
    // 真实松手：取消计时 + 关闭预览 + 拦截随后的 click
    function endPress() {
      cancelPress();
      if (previewed) {
        closeLightbox();
        suppressClick = true;
      }
    }
    function startPress(e) {
      cancelPress();
      suppressClick = false;    // 新的触摸/按压开始，重置拦截
      startX = e.clientX;
      startY = e.clientY;
      pressTimer = setTimeout(function () {
        previewed = true;
        stopCarousel();
        const first = showCarouselImage(imgs, 0, false);
        lightbox.classList.add('open');
        startCarousel(imgs, first);
      }, 450);
    }
    // 手指明显移动（滚动意图）才取消长按；微小抖动（iOS 常见）不影响
    function movePress(e) {
      if (Math.abs(e.clientX - startX) > 30 || Math.abs(e.clientY - startY) > 30) {
        if (previewed) { closeLightbox(); suppressClick = true; }
        cancelPress();
      }
    }

    card.addEventListener('pointerdown', function (e) {
      // 捕获指针：之后所有 pointer 事件强制派发到本卡片，
      // 即使 lightbox 覆盖层出现也不会被系统取消（iOS 26 防自动关闭关键）
      try { card.setPointerCapture(e.pointerId); } catch (err) {}
      startPress(e);
    });
    card.addEventListener('pointermove', movePress);
    card.addEventListener('pointerup', endPress);
    // 长按手势结束时系统可能发 pointercancel 而非 pointerup，同样关闭预览
    card.addEventListener('pointercancel', endPress);
    // 长按预览过 → 拦截 iOS 松手后补发的 click，避免误触导入
    card.addEventListener('click', function (e) {
      if (previewed || suppressClick) {
        e.preventDefault(); e.stopPropagation();
        previewed = false; suppressClick = false;
      }
    });
  });

  // 兜底：个别情况下松手的 pointerup 没派发到卡片（capture 失效等），
  // 全局松手时同样关闭预览，避免预览残留
  document.addEventListener('pointerup', function () {
    if (previewed) {
      closeLightbox();
      suppressClick = true;
    }
  });
</script>
</body>
</html>
"""
    page = page.replace("__CARDS__", "".join(cards))

    Path("gallery.html").write_text(page, encoding="utf-8")
    print("✅ gallery.html 已生成")


def main():
    entries = collect_entries()
    update_readme(entries)
    write_gallery(entries)


if __name__ == "__main__":
    main()