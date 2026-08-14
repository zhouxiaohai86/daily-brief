#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
daily-brief 自动构建脚本（GitHub Actions 用）
从公开 RSS 源抓取当日资讯，按五板块生成单文件 HTML 简报（v3 版式，密码保护 + 历史翻阅）。
用法:
  python build_brief.py --date 20260814 --out ../public/index.html [--briefs-json ../data/briefs.json]
"""
import argparse
import datetime
import html
import json
import os
import re
import sys
import urllib.request

try:
    import feedparser
except ImportError:
    sys.exit("缺少依赖 feedparser，请先执行: pip install feedparser")

# ---------------- 配置 ----------------
PASSWORD = "123567"
PROJECT_NAME = "daily-brief"
# 源: (名称, RSS URL, 板块分组关键字)
RSS_SOURCES = [
    ("IT之家", "https://www.ithome.com/rss/", ["科技", "AI", "芯片", "半导体", "苹果", "华为", "微软", "谷歌", "英伟达", "OpenAI", "大模型"]),
    ("爱范儿", "https://www.ifanr.com/feed", ["科技", "AI", "芯片", "苹果", "华为", "微软", "谷歌", "数码", "互联网"]),
    ("少数派", "https://sspai.com/feed", ["效率", "工具", "数码", "App"]),
    ("新浪科技", "https://rss.sina.com.cn/tech/rollnews.xml", ["科技", "AI", "互联网", "手机", "数码"]),
    ("阮一峰的网络日志", "https://www.ruanyifeng.com/blog/atom.xml", ["周刊", "科技", "开源"]),
    ("INFLOW Network", "https://www.inflownetwork.com/feed/", ["TikTok", "tiktok", "Instagram", "influencer", "creator", "trend", "达人", "创作者", "短视频"]),
    ("白鲸出海", "https://www.baijingapp.com/feed", ["跨境电商", "出海", "Temu", "Shopee", "Lazada", "亚马逊", "独立站", "跨境", "电商"]),
    ("Odaily星球日报", "https://www.odaily.news/rss", ["比特币", "以太坊", "加密", "区块链", "DeFi", "稳定币", "Web3"]),
]
# 板块定义: (id, 序号, 标题, 图标, 关键字组)
SECTIONS = [
    ("sec1", "一", "科技速览", "📡", ["AI", "人工智能", "芯片", "半导体", "大模型", "OpenAI", "英伟达", "苹果", "华为", "微软", "谷歌", "科技", "开源", "机器人", "算力"]),
    ("sec2", "二", "TikTok 趋势", "🎬", ["TikTok", "tiktok", "短视频", "达人", "美区", "直播电商", "内容电商", "抖音", "网红", "YouTube", "Temu", "直播带货"]),
    ("sec3", "三", "电商动态", "🛒", ["电商", "跨境", "独立站", "亚马逊", "Temu", "Shein", "供应链", "出海", "物流", "天猫", "京东", "拼多多", "淘宝", "Shopee", "Lazada"]),
    ("sec4", "四", "加密货币", "₿", ["比特币", "以太坊", "加密", "区块链", "BTC", "ETH", "DeFi", "稳定币", "Web3", "Coinbase", "SEC", "ETF", "Token", "bitcoin", "crypto", "ethereum", "币安", "Binance", "挖矿", "NFT"]),
    ("sec5", "五", "副业机会", "💼", ["副业", "兼职", "变现", "自由职业", "零工", "赚钱", "AI 工具", "数字人", "自媒体", "课程", "模板", "外包", "接单", "创业", "个体户", "灵活就业"]),
]
MAX_PER_SECTION = 6
FETCH_TIMEOUT = 20
USER_AGENT = "Mozilla/5.0 (compatible; daily-brief-bot/1.0)"


# ---------------- 抓取 ----------------
def fetch_feed(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
        data = resp.read()
    return feedparser.parse(data)


def norm_text(s):
    return html.unescape(re.sub(r"\s+", " ", s or "")).strip()


def fetch_all():
    entries = []
    errors = []
    for name, url, _ in RSS_SOURCES:
        try:
            feed = fetch_feed(url)
            for e in feed.entries[:30]:
                title = norm_text(getattr(e, "title", ""))
                link = getattr(e, "link", "")
                summary = norm_text(getattr(e, "summary", "") or getattr(e, "description", ""))
                published = norm_text(getattr(e, "published", ""))
                entries.append({"title": title, "link": link, "summary": summary[:220],
                                "published": published, "source": name})
        except Exception as ex:
            errors.append(f"{name}: {ex}")
    return entries, errors


# ---------------- 分类 ----------------
def classify(entries):
    buckets = {sid: [] for sid, *_ in SECTIONS}
    fallback_sid = SECTIONS[0][0]  # 科技速览兜底
    for item in entries:
        blob = item["title"] + " " + item["summary"]
        matched = False
        for sid, _no, _name, _icon, keywords in SECTIONS:
            if any(k.lower() in blob.lower() for k in keywords):
                buckets[sid].append(item)
                matched = True
                break  # 只进第一个命中板块
        if not matched:
            buckets[fallback_sid].append(item)  # 未命中兜底进科技速览
    # 每板块去重并按标题长度取优质条目
    for sid in buckets:
        seen, uniq = set(), []
        for it in buckets[sid]:
            key = it["title"][:40]
            if key in seen:
                continue
            seen.add(key)
            uniq.append(it)
        uniq.sort(key=lambda x: len(x["title"]), reverse=True)
        buckets[sid] = uniq[:MAX_PER_SECTION]
    return buckets


# ---------------- HTML 生成 ----------------
def esc(s):
    return html.escape(s or "", quote=True)


def render_items(items):
    if not items:
        return '    <div class="item"><div class="item-desc">今日暂无相关条目。</div></div>\n'
    out = []
    for i, it in enumerate(items, 1):
        src = esc(it["source"])
        tag_cls = "tag-hot" if i == 1 else "tag-source"
        out.append(f'''  <div class="item">
    <div class="item-header">
      <div class="item-title">{esc(it["title"])}</div>
      <span class="tag {tag_cls}">{src}</span>
    </div>
    <div class="item-desc">{esc(it["summary"]) or "（无摘要）"}</div>
    <div class="item-meta">
      <a class="source-link" href="{esc(it["link"])}" target="_blank" rel="noopener">原文链接 ↗</a>
      · 来自 RSS 自动采集
    </div>
  </div>
''')
    return "\n".join(out)


def render_sections(buckets):
    parts = []
    for sid, no, name, icon, _kw in SECTIONS:
        parts.append(f'''<!-- ===== {name} ===== -->
<div class="section" id="{sid}">
  <div class="section-title"><span class="sec-no">{no}</span><span class="icon">{icon}</span> {name}<span class="sec-line"></span></div>

{render_items(buckets[sid])}
</div>
''')
    return "\n".join(parts)


def render_quick_hits(buckets):
    lis = []
    for idx, (sid, no, name, _icon, _kw) in enumerate(SECTIONS, 1):
        first = buckets[sid][0] if buckets[sid] else None
        txt = esc(first["title"]) if first else "暂无条目"
        lis.append(f'    <li><span class="qh-no">{idx:02d}</span><div class="qh-body"><div class="qh-cat">{name}</div><div class="qh-txt">{txt}</div></div></li>')
    return "\n".join(lis)


def build_html(date_str, date_label, buckets, briefs, total, source_names):
    quick = render_quick_hits(buckets)
    body = render_sections(buckets)
    briefs_js = json.dumps(briefs, ensure_ascii=False)
    sources = " / ".join(source_names)
    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
<title>每日情报简报 · {date_label}</title>
<style>
:root {{
  --bg:#eef0f4; --bg-soft:#e7eaf0; --card:#fff;
  --ink:#111827; --ink-2:#374151; --ink-3:#6b7280; --ink-4:#9ca3af;
  --brand:#c41e3a; --brand-2:#a01830; --brand-soft:#fdeef0;
  --hero1:#161a2b; --hero2:#232845; --hero3:#3a1c33;
  --line:#e5e7eb; --line-soft:#f0f1f4; --link:#1d4ed8;
  --ok:#059669; --warn:#d97706; --danger:#dc2626;
  --tag-source-bg:#eef2ff; --tag-source-fg:#4338ca;
  --tag-rpm-bg:#ecfdf5; --tag-rpm-fg:#047857;
  --tag-warn-bg:#fef2f2; --tag-warn-fg:#b91c1c;
  --tag-hot-bg:#fffbeb; --tag-hot-fg:#b45309;
  --tag-info-bg:#f3f4f6; --tag-info-fg:#4b5563;
  --fs-xs:11px; --fs-sm:12.5px; --fs-md:13.5px; --fs-body:15px; --fs-lg:16.5px; --fs-xl:19px; --fs-2xl:24px; --fs-3xl:30px;
  --sp-1:4px; --sp-2:8px; --sp-3:12px; --sp-4:16px; --sp-5:20px; --sp-6:24px; --sp-8:32px;
  --r-sm:8px; --r-md:14px; --r-lg:20px;
  --shadow-card:0 1px 2px rgba(17,24,39,.04),0 4px 14px rgba(17,24,39,.05);
  --shadow-pop:0 12px 40px rgba(17,24,39,.16);
  --shadow-hero:0 12px 32px rgba(22,26,43,.28);
  --t-fast:150ms ease; --t-base:260ms cubic-bezier(.4,0,.2,1);
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
html {{ scroll-behavior:smooth; scroll-padding-top:64px; }}
body {{ background:var(--bg); color:var(--ink); font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei","Segoe UI",sans-serif; line-height:1.75; font-size:var(--fs-body); padding:0 0 56px; -webkit-text-size-adjust:100%; }}
a {{ color:inherit; text-decoration:none; }}
button {{ font-family:inherit; }}
.hidden {{ display:none !important; }}

.password-overlay {{ position:fixed; inset:0; z-index:9999; display:flex; align-items:center; justify-content:center; background:radial-gradient(circle at 30% 20%, rgba(196,30,58,.28), transparent 45%), linear-gradient(160deg, var(--hero1), var(--hero2) 55%, var(--hero3)); }}
.password-brand {{ position:absolute; top:48px; letter-spacing:4px; font-size:var(--fs-sm); color:rgba(255,255,255,.55); }}
.password-box {{ width:min(340px, 86vw); background:rgba(255,255,255,.97); border-radius:var(--r-lg); padding:40px 28px 28px; text-align:center; box-shadow:var(--shadow-pop); backdrop-filter:blur(6px); }}
.password-box h2 {{ font-size:var(--fs-xl); margin-bottom:4px; color:var(--ink); }}
.password-box .sub {{ color:var(--ink-3); font-size:var(--fs-sm); margin-bottom:24px; }}
.pw-field {{ display:flex; align-items:center; justify-content:center; gap:8px; margin-bottom:16px; }}
.pw-field input {{ width:180px; padding:12px 14px; border:1px solid var(--line); border-radius:var(--r-md); text-align:center; letter-spacing:6px; font-size:var(--fs-lg); }}
.pw-field input:focus {{ border-color:var(--brand); outline:none; }}
.pw-toggle {{ border:none; background:transparent; font-size:18px; cursor:pointer; }}
#pwBtn {{ width:100%; padding:13px; border:none; border-radius:var(--r-md); background:linear-gradient(135deg, var(--brand), var(--brand-2)); color:#fff; font-size:var(--fs-body); font-weight:600; cursor:pointer; box-shadow:0 8px 20px rgba(196,30,58,.32); transition:var(--t-fast); }}
#pwBtn:hover {{ transform:translateY(-1px); box-shadow:0 10px 22px rgba(196,30,58,.38); }}
.error {{ display:none; color:var(--danger); font-size:var(--fs-sm); margin-top:12px; }}
.error.show {{ display:block; }}
.pw-hint {{ margin-top:14px; color:var(--ink-4); font-size:var(--fs-xs); }}
.shake {{ animation:shake .4s; }}
@keyframes shake {{ 0%,100%{{transform:translateX(0)}} 25%{{transform:translateX(-6px)}} 75%{{transform:translateX(6px)}} }}

.history-bar {{ position:sticky; top:0; z-index:100; display:flex; align-items:center; gap:10px; padding:12px 16px; background:rgba(238,240,244,.92); backdrop-filter:blur(8px); border-bottom:1px solid var(--line); }}
.nav-btn {{ padding:8px 14px; border:1px solid var(--line); border-radius:var(--r-md); background:var(--card); color:var(--ink-2); font-size:var(--fs-sm); cursor:pointer; }}
.nav-btn:disabled {{ opacity:.4; cursor:not-allowed; }}
#dateSelect {{ flex:1; min-width:0; padding:8px 10px; border:1px solid var(--line); border-radius:var(--r-md); background:var(--card); font-size:var(--fs-sm); color:var(--ink); }}
.today-chip {{ display:none; padding:4px 10px; border-radius:999px; background:var(--brand-soft); color:var(--brand); font-size:var(--fs-xs); font-weight:600; }}

.main-content {{ max-width:750px; margin:0 auto; padding:0 16px; }}
.hero {{ margin:16px 0 0; padding:36px 22px 30px; border-radius:var(--r-lg); background:linear-gradient(135deg, var(--hero1), var(--hero2) 55%, var(--hero3)); color:#fff; box-shadow:var(--shadow-hero); }}
.hero-top {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:16px; }}
.hero-kicker {{ letter-spacing:3px; font-size:var(--fs-xs); color:rgba(255,255,255,.6); }}
.hero-live {{ padding:4px 10px; border-radius:999px; background:rgba(255,255,255,.14); font-size:var(--fs-xs); }}
.hero h1 {{ font-size:var(--fs-3xl); margin-bottom:6px; }}
.hero h1 .accent {{ color:#ff8a9a; }}
.hero .date {{ color:rgba(255,255,255,.75); font-size:var(--fs-md); margin-bottom:16px; }}
.stats-row {{ display:flex; flex-wrap:wrap; gap:8px; }}
.stat-pill {{ padding:6px 12px; border-radius:999px; background:rgba(255,255,255,.12); font-size:var(--fs-sm); }}
.stat-pill b {{ color:#ffd9a0; }}

.quick-hits {{ margin:-20px 8px 0; position:relative; background:var(--card); border-radius:var(--r-lg); box-shadow:var(--shadow-pop); padding:18px 18px 8px; }}
.qh-head {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; }}
.qh-title {{ font-weight:700; font-size:var(--fs-lg); position:relative; padding-left:12px; }}
.qh-title::before {{ content:""; position:absolute; left:0; top:4px; bottom:4px; width:4px; border-radius:2px; background:linear-gradient(var(--brand), #ff5c77); }}
.qh-more {{ color:var(--ink-4); font-size:var(--fs-xs); letter-spacing:1px; }}
.qh-list {{ list-style:none; }}
.qh-list li {{ display:flex; gap:10px; padding:9px 0; border-bottom:1px solid var(--line-soft); }}
.qh-list li:last-child {{ border-bottom:none; }}
.qh-no {{ font-weight:700; color:var(--brand); font-size:var(--fs-sm); }}
.qh-cat {{ font-size:var(--fs-xs); color:var(--ink-4); margin-bottom:2px; }}
.qh-txt {{ font-size:var(--fs-md); color:var(--ink-2); line-height:1.5; }}

.section-nav {{ position:sticky; top:52px; z-index:90; display:flex; gap:8px; overflow-x:auto; padding:12px 4px; margin:4px -4px 0; }}
.section-nav a {{ flex:0 0 auto; display:inline-flex; align-items:center; gap:6px; padding:8px 14px; border:1px solid var(--line); border-radius:999px; background:var(--card); color:var(--ink-2); font-size:var(--fs-sm); }}
.section-nav .nav-no {{ width:20px; height:20px; border-radius:50%; background:var(--brand-soft); color:var(--brand); font-size:var(--fs-xs); display:inline-flex; align-items:center; justify-content:center; }}

.section {{ background:var(--card); border-radius:var(--r-lg); box-shadow:var(--shadow-card); padding:20px 18px; margin-top:16px; }}
.section-title {{ display:flex; align-items:center; gap:8px; font-size:var(--fs-xl); font-weight:700; margin-bottom:16px; }}
.sec-no {{ width:26px; height:26px; border-radius:8px; background:linear-gradient(135deg, var(--brand), var(--brand-2)); color:#fff; font-size:var(--fs-sm); display:inline-flex; align-items:center; justify-content:center; }}
.sec-line {{ flex:1; height:1px; background:var(--line); margin-left:8px; }}
.item {{ padding:14px 0; border-bottom:1px solid var(--line-soft); }}
.item:last-child {{ border-bottom:none; }}
.item-header {{ display:flex; justify-content:space-between; align-items:flex-start; gap:8px; margin-bottom:6px; }}
.item-title {{ font-size:var(--fs-lg); font-weight:600; color:var(--ink); line-height:1.45; }}
.tag {{ flex:0 0 auto; padding:3px 10px; border-radius:999px; font-size:var(--fs-xs); font-weight:500; }}
.tag-hot {{ background:var(--tag-hot-bg); color:var(--tag-hot-fg); }}
.tag-source {{ background:var(--tag-source-bg); color:var(--tag-source-fg); }}
.tag-warn {{ background:var(--tag-warn-bg); color:var(--tag-warn-fg); }}
.tag-rpm {{ background:var(--tag-rpm-bg); color:var(--tag-rpm-fg); }}
.item-desc {{ color:var(--ink-2); font-size:var(--fs-md); margin-bottom:8px; }}
.item-desc b {{ color:var(--ink); }}
.item-meta {{ color:var(--ink-4); font-size:var(--fs-xs); }}
.source-link {{ color:var(--link); }}
.source-link:hover {{ text-decoration:underline; }}

.footer-note {{ text-align:center; color:var(--ink-4); font-size:var(--fs-xs); padding:24px 16px 0; }}
.empty-state {{ text-align:center; color:var(--ink-3); padding:60px 0; }}

@media print {{
  .password-overlay, .history-bar, .section-nav, .quick-hits, .hero {{ display:none !important; }}
  body {{ background:#fff; padding:0; }}
}}
</style>
</head>
<body>

<div class="password-overlay" id="pwOverlay">
  <div class="password-brand">DAILY INTELLIGENCE BRIEF</div>
  <div class="password-box" id="pwBox">
    <h2>每日情报简报</h2>
    <div class="sub">请输入访问密码</div>
    <div class="pw-field">
      <input type="password" id="pwInput" placeholder="····" maxlength="20" autocomplete="off" autofocus>
      <button type="button" class="pw-toggle" id="pwToggle" aria-label="显示/隐藏密码">👁</button>
    </div>
    <button type="button" id="pwBtn">进入</button>
    <div class="error" id="pwError">密码错误，请重试</div>
    <div class="pw-hint">密码由管理员提供</div>
  </div>
</div>

<div class="history-bar hidden" id="historyBar">
  <button class="nav-btn" id="btnPrev" disabled>&lt; 前一天</button>
  <select id="dateSelect" aria-label="选择简报日期"></select>
  <button class="nav-btn" id="btnNext" disabled>后一天 &gt;</button>
  <span class="today-chip" id="todayChip">今天</span>
</div>

<div class="main-content hidden" id="mainContent">

<div class="hero">
  <div class="hero-top">
    <span class="hero-kicker">DAILY INTELLIGENCE BRIEF</span>
    <span class="hero-live">每日更新</span>
  </div>
  <h1>每日情报<span class="accent">简报</span></h1>
  <div class="date">{date_label}</div>
  <div class="stats-row">
    <span class="stat-pill"><b>5</b> 大板块</span>
    <span class="stat-pill"><b>{total}</b> 条信息</span>
    <span class="stat-pill"><b>{len(RSS_SOURCES)}</b> RSS 源</span>
    <span class="stat-pill">自动采集</span>
  </div>
</div>

<div class="quick-hits">
  <div class="qh-head">
    <div class="qh-title">今日速览</div>
    <div class="qh-more">Quick Hits</div>
  </div>
  <ul class="qh-list">
{quick}
  </ul>
</div>

<div class="section-nav">
  <a href="#sec1"><span class="nav-no">一</span>科技速览</a>
  <a href="#sec2"><span class="nav-no">二</span>TikTok 趋势</a>
  <a href="#sec3"><span class="nav-no">三</span>电商动态</a>
  <a href="#sec4"><span class="nav-no">四</span>加密货币</a>
  <a href="#sec5"><span class="nav-no">五</span>副业机会</a>
</div>

{body}

<div class="footer-note">
  数据源: {sources}
</div>

</div>

<script>
const PASSWORD = "{PASSWORD}";
const BRIEFS = {briefs_js};

const pwOverlay = document.getElementById('pwOverlay');
const pwBox = document.getElementById('pwBox');
const pwInput = document.getElementById('pwInput');
const pwToggle = document.getElementById('pwToggle');
const pwError = document.getElementById('pwError');
const historyBar = document.getElementById('historyBar');
const mainContent = document.getElementById('mainContent');
const todayChip = document.getElementById('todayChip');

function checkPassword() {{
  if (pwInput.value === PASSWORD) {{
    pwOverlay.classList.add('hidden');
    historyBar.classList.remove('hidden');
    mainContent.classList.remove('hidden');
    initHistoryBar();
  }} else {{
    pwError.classList.add('show');
    pwBox.classList.remove('shake');
    void pwBox.offsetWidth;
    pwBox.classList.add('shake');
    pwInput.value = '';
    pwInput.focus();
  }}
}}
pwInput.addEventListener('keydown', function(e) {{ if (e.key === 'Enter') checkPassword(); }});
document.getElementById('pwBtn').addEventListener('click', checkPassword);
pwToggle.addEventListener('click', function() {{
  const isPw = pwInput.type === 'password';
  pwInput.type = isPw ? 'text' : 'password';
  pwToggle.textContent = isPw ? '🙈' : '👁';
  pwInput.focus();
}});
pwInput.addEventListener('input', function() {{ pwError.classList.remove('show'); }});

function initHistoryBar() {{
  const select = document.getElementById('dateSelect');
  if (!BRIEFS.length) {{
    select.innerHTML = '<option>暂无历史</option>';
    select.disabled = true;
    document.getElementById('btnPrev').disabled = true;
    document.getElementById('btnNext').disabled = true;
    const content = document.querySelector('.main-content');
    if (content) content.innerHTML = '<div class="empty-state">今日简报暂未生成，请稍后再来。</div>';
    return;
  }}
  select.innerHTML = BRIEFS.map((b, i) =>
    `<option value="${{i}}" ${{i === BRIEFS.length - 1 ? 'selected' : ''}}>${{b.label}}</option>`
  ).join('');
  select.addEventListener('change', function() {{ updateNavButtons(); }});
  document.getElementById('btnPrev').addEventListener('click', () => navigate(-1));
  document.getElementById('btnNext').addEventListener('click', () => navigate(1));
  const today = new Date();
  const todayStr = today.getFullYear() + '-' + String(today.getMonth()+1).padStart(2,'0') + '-' + String(today.getDate()).padStart(2,'0');
  if (BRIEFS.some(b => b.date === todayStr)) todayChip.style.display = 'inline-block';
  updateNavButtons();
}}
function navigate(dir) {{
  const select = document.getElementById('dateSelect');
  const newIdx = parseInt(select.value) + dir;
  if (newIdx >= 0 && newIdx < BRIEFS.length) {{
    select.value = newIdx;
    select.dispatchEvent(new Event('change'));
  }}
}}
function updateNavButtons() {{
  const idx = parseInt(document.getElementById('dateSelect').value);
  document.getElementById('btnPrev').disabled = idx <= 0;
  document.getElementById('btnNext').disabled = idx >= BRIEFS.length - 1;
}}
pwOverlay.addEventListener('click', function(e) {{ if (e.target === pwOverlay) pwInput.focus(); }});
</script>

</body>
</html>
'''


# ---------------- 主流程 ----------------
def weekday_cn(dt):
    return "一二三四五六日"[dt.weekday()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="YYYYMMDD，默认今天（UTC+8）")
    ap.add_argument("--out", default="../public/index.html")
    ap.add_argument("--briefs-json", default="../data/briefs.json")
    args = ap.parse_args()

    if args.date:
        dt = datetime.datetime.strptime(args.date, "%Y%m%d")
    else:
        dt = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
    date_str = dt.strftime("%Y-%m-%d")
    date_label = f"{dt.year} 年 {dt.month} 月 {dt.day} 日 · 星期{weekday_cn(dt)}"

    entries, errors = fetch_all()
    buckets = classify(entries)
    total = sum(len(v) for v in buckets.values())

    # 历史数组：读取 + 追加当日
    briefs = []
    if os.path.exists(args.briefs_json):
        try:
            with open(args.briefs_json, encoding="utf-8") as f:
                briefs = json.load(f)
        except Exception:
            briefs = []
    if not any(b.get("date") == date_str for b in briefs):
        briefs.append({"date": date_str, "label": date_label})
    os.makedirs(os.path.dirname(args.briefs_json) or ".", exist_ok=True)
    with open(args.briefs_json, "w", encoding="utf-8") as f:
        json.dump(briefs, f, ensure_ascii=False, indent=2)

    source_names = [n for n, *_ in RSS_SOURCES]
    html_out = build_html(date_str, date_label, buckets, briefs, total, source_names)

    out_path = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_out)

    print(f"OK date={date_str} total={total} out={out_path}")
    for sid, no, name, _icon, _kw in SECTIONS:
        print(f"  [{no}] {name}: {len(buckets[sid])} 条")
    if errors:
        print("WARN 部分源抓取失败:", "; ".join(errors))
    if total == 0:
        print("FATAL 所有源均无条目，部署中止")
        sys.exit(2)


if __name__ == "__main__":
    main()
