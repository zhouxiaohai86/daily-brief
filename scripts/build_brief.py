#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
daily-brief 自动构建脚本（GitHub Actions 用）
从公开 RSS 源抓取当日资讯，按五板块生成单文件 HTML 简报（v3 完整版式，密码保护 + 历史翻阅）。
版式模板: scripts/brief_template.html（与精编版 daily_brief_*.html 完全一致）。
用法:
  python build_brief.py --date 20260814 --out ../public/index.html [--briefs-json ../data/briefs.json]

防覆盖保护:
  若 --out 目标文件已包含精编修复版标记（renderBrief 历史机制），默认拒绝覆盖，
  自动改写输出到同目录 auto-YYYYMMDD.html；确认要强制覆盖时加 --force。
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
TEMPLATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "brief_template.html")

# 源: (名称, RSS URL, 板块分组关键字)
RSS_SOURCES = [
    ("IT之家", "https://www.ithome.com/rss/", ["科技", "AI", "芯片", "半导体", "苹果", "华为", "微软", "谷歌", "英伟达", "OpenAI", "大模型"]),
    ("爱范儿", "https://www.ifanr.com/feed", ["科技", "AI", "芯片", "苹果", "华为", "微软", "谷歌", "数码", "互联网"]),
    ("少数派", "https://sspai.com/feed", ["效率", "工具", "数码", "App", "自动化", "AI", "副业", "变现"]),
    ("新浪科技", "https://rss.sina.com.cn/tech/rollnews.xml", ["科技", "AI", "互联网", "手机", "数码"]),
    ("36氪", "https://36kr.com/feed", ["科技", "AI", "创业", "副业", "自由职业", "变现", "融资", "互联网", "跨境电商", "出海", "自媒体", "AI工具"]),
    ("人人都是产品经理", "https://www.woshipm.com/feed", ["产品", "运营", "变现", "自媒体", "增长", "AI", "电商", "内容", "副业", "接单"]),
    ("阮一峰的网络日志", "https://www.ruanyifeng.com/blog/atom.xml", ["周刊", "科技", "开源", "AI"]),
    ("INFLOW Network", "https://www.inflownetwork.com/feed/", ["TikTok", "tiktok", "Instagram", "influencer", "creator", "trend", "达人", "创作者", "短视频", "直播"]),
    ("白鲸出海", "https://www.baijingapp.com/feed", ["跨境电商", "出海", "Temu", "Shopee", "Lazada", "亚马逊", "独立站", "跨境", "电商", "TikTok"]),
    ("雨果跨境", "https://www.cifnews.com/rss", ["跨境电商", "出海", "亚马逊", "Temu", "TikTok", "选品", "Shopee", "独立站", "电商"]),
    ("Cointelegraph", "https://cointelegraph.com/rss", ["bitcoin", "ethereum", "crypto", "BTC", "ETH", "DeFi", "stablecoin", "blockchain", "Web3", "ETF", "altcoin", "Token", "Coinbase", "Binance", "mining", "NFT", "加密", "比特币", "以太坊", "区块链"]),
    ("优设网", "https://www.uisdc.com/feed", ["设计", "AI工具", "AIGC", "PS", "教程", "变现", "副业", "模板"]),
]
# 板块定义: (id, 序号, 标题, 图标, 关键字组)
SECTIONS = [
    ("sec1", "一", "科技速览", "📡", ["AI", "人工智能", "芯片", "半导体", "大模型", "OpenAI", "英伟达", "苹果", "华为", "微软", "谷歌", "科技", "开源", "机器人", "算力", "GPU", "数据中心", "存储"]),
    ("sec2", "二", "TikTok 趋势", "🔥", ["TikTok", "tiktok", "短视频", "达人", "美区", "直播电商", "内容电商", "抖音", "网红", "YouTube", "Temu", "直播带货", "商城", "GMV", "选品"]),
    ("sec3", "三", "电商动态", "🛒", ["电商", "跨境", "独立站", "亚马逊", "Temu", "Shein", "供应链", "出海", "物流", "天猫", "京东", "拼多多", "淘宝", "Shopee", "Lazada", "跨境电商", "选品", "海关", "外贸"]),
    ("sec4", "四", "加密货币", "₿", ["比特币", "以太坊", "加密", "区块链", "BTC", "ETH", "DeFi", "稳定币", "Web3", "Coinbase", "SEC", "ETF", "Token", "bitcoin", "crypto", "ethereum", "币安", "Binance", "挖矿", "NFT"]),
    ("sec5", "五", "副业机会", "💼", ["副业", "兼职", "变现", "自由职业", "零工", "赚钱", "AI工具", "数字人", "自媒体", "外包", "接单", "创业", "个体户", "灵活就业", "短视频带货", "直播带货", "闲鱼", "小红书", "公众号", "配音", "翻译", "Prompt", "Midjourney", "Stable Diffusion", "AIGC", "AI绘画", "AI视频", "内容创作", "图文带货", "分销", "Shopify", "Etsy", "dropshipping", "affiliate", "联盟营销", "知识付费", "被动收入", "远程工作", "居家办公", "赚外快", "轻资产", "个人IP"]),
]
MAX_PER_SECTION = 8
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
            for e in feed.entries[:40]:
                title = norm_text(getattr(e, "title", ""))
                link = getattr(e, "link", "")
                summary = norm_text(getattr(e, "summary", "") or getattr(e, "description", ""))
                published = norm_text(getattr(e, "published", ""))
                entries.append({"title": title, "link": link, "summary": summary[:260],
                                "published": published, "source": name})
        except Exception as ex:
            errors.append(f"{name}: {ex}")
    return entries, errors


# ---------------- 分类 ----------------
def match_kw(blob, k):
    """关键词匹配：英文词用词边界（避免 DeFi 命中 defining），中文直接包含匹配"""
    if re.search(r"[A-Za-z]", k):
        return re.search(r"\b" + re.escape(k) + r"\b", blob, re.IGNORECASE) is not None
    return k in blob


def strip_noise(s):
    """去掉摘要中常见的营销尾缀，避免'关注公众号'等噪声参与关键词匹配"""
    s = re.sub(r"关注公众号[^\s。；;]*", "", s)
    s = re.sub(r"点击(下方|上面)?(链接|阅读原文|关注)[^\s。；;]*", "", s)
    s = re.sub(r"扫描二维码[^\s。；;]*", "", s)
    s = re.sub(r"(微信|公众号)[^\s。；;]*", "", s)
    return s


def classify(entries):
    buckets = {sid: [] for sid, *_ in SECTIONS}
    fallback_sid = SECTIONS[0][0]  # 科技速览兜底
    for item in entries:
        matched = False
        for sid, _no, _name, _icon, keywords in SECTIONS:
            # 副业/加密板块优先用标题匹配；副业用清洗后的摘要补充，避免"关注公众号"等噪声误命中
            if sid in ("sec5", "sec4"):
                blob = item["title"] + (" " + strip_noise(item["summary"]) if sid == "sec5" else "")
                # 负面新闻（操控舆论/犯罪/处罚等）不进副业机会板块
                if sid == "sec5" and any(w in blob for w in ["操控舆论", "被抓", "违法", "犯罪", "警方", "法院",
                                                              "判刑", "查处", "通报", "涉嫌", "诈骗", "查获",
                                                              "逮捕", "处罚", "罚款", "判刑"]):
                    continue
            else:
                blob = item["title"] + " " + item["summary"]
            if any(match_kw(blob, k) for k in keywords):
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
    # 副业板块保底：从全量条目中挑选强相关补位
    if len(buckets["sec5"]) < 6:
        STRONG = ["副业", "兼职", "变现", "自由职业", "零工", "赚钱", "接单", "外包", "灵活就业",
                  "数字人", "自媒体", "图文带货", "短视频带货", "直播带货", "分销", "闲鱼", "小红书",
                  "公众号", "配音", "翻译", "Prompt", "Midjourney", "Stable Diffusion", "AIGC",
                  "AI绘画", "AI视频", "Shopify", "Etsy", "dropshipping", "affiliate", "联盟营销",
                  "设计教程", "PPT模板", "简历", "副业项目", "居家办公", "远程工作", "被动收入", "赚外快",
                  "个人IP", "知识付费", "接活", "零成本", "轻资产", "副业"]
        seen = {it["title"][:40] for it in buckets["sec5"]}
        cands = [it for it in entries if it["title"][:40] not in seen]
        cands.sort(key=lambda x: len(x["title"]), reverse=True)
        for it in cands:
            if len(buckets["sec5"]) >= 6:
                break
            # 负面新闻不进副业板块
            if any(w in it["title"] + it["summary"] for w in ["操控舆论", "被抓", "违法", "犯罪", "警方", "法院",
                                                               "判刑", "查处", "通报", "涉嫌", "诈骗", "查获",
                                                               "逮捕", "处罚", "罚款"]):
                continue
            # 补位匹配用清洗后的摘要，避免噪声
            if any(k in it["title"] for k in STRONG) or any(k in strip_noise(it["summary"]) for k in STRONG):
                buckets["sec5"].append(it)
                seen.add(it["title"][:40])
    return buckets


# ---------------- HTML 生成 ----------------
def esc(s):
    return html.escape(s or "", quote=True)


def render_items(items):
    if not items:
        return '    <div class="item"><div class="item-header"><div class="item-title">今日暂无相关条目</div></div><div class="item-desc">自动采集暂无命中，请稍后再看。</div></div>\n'
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
      <a class="source-link" href="{esc(it["link"])}" target="_blank" rel="noopener">原文（{src}）</a>
      · 自动采集
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


def render_section_nav():
    links = []
    for sid, no, name, _icon, _kw in SECTIONS:
        links.append(f'  <a href="#{sid}"><span class="nav-no">{no}</span>{name}</a>')
    return "\n".join(links)


# 精编修复版保护标记：目标文件含此特征时视为"人工精编版"，禁止自动构建覆盖
PROTECTED_MARKER = "function renderBrief("


def is_protected_target(out_path):
    """检测目标 HTML 是否已是含 renderBrief 历史机制的精编修复版"""
    if not os.path.exists(out_path):
        return False
    try:
        with open(out_path, encoding="utf-8", errors="ignore") as f:
            return PROTECTED_MARKER in f.read()
    except Exception:
        return False


def build_html(date_str, date_label, buckets, briefs, total, source_names):
    with open(TEMPLATE_FILE, encoding="utf-8") as f:
        tpl = f.read()

    quick = render_quick_hits(buckets)
    body = render_sections(buckets)
    nav = render_section_nav()
    briefs_js = json.dumps(briefs, ensure_ascii=False)
    sources = " / ".join(source_names)

    tpl = (tpl
           .replace("__DATE_LABEL__", date_label)
           .replace("__TOTAL__", str(total))
           .replace("__SOURCES__", str(len(RSS_SOURCES)))
           .replace("__QUICK_HITS__", quick)
           .replace("__SECTION_NAV__", nav)
           .replace("__BODY__", body)
           .replace("__SOURCE_LIST__", sources)
           .replace("__PASSWORD__", PASSWORD)
           .replace("__BRIEFS__", briefs_js))
    return tpl


# ---------------- 主流程 ----------------
def weekday_cn(dt):
    return "一二三四五六日"[dt.weekday()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="YYYYMMDD，默认今天（UTC+8）")
    ap.add_argument("--out", default="../public/index.html")
    ap.add_argument("--briefs-json", default="../data/briefs.json")
    ap.add_argument("--force", action="store_true", help="强制覆盖目标文件（跳过精编版保护）")
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

    # 防覆盖熔断：目标若是精编修复版（含 renderBrief 历史机制），自动构建不得覆盖，
    # 改写输出到旁路文件，避免重演"CI 自动聚合版冲掉精编内容"事故
    if is_protected_target(out_path) and not args.force:
        fallback = os.path.join(os.path.dirname(out_path), f"auto-{date_str}.html")
        print(f"BLOCKED 目标 {out_path} 是精编修复版（含 renderBrief），为避免覆盖历史内容，本次输出改写为 {fallback}")
        print("        如确需强制覆盖，请显式加 --force")
        out_path = fallback

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
