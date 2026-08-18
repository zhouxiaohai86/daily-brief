#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
daily-brief 一键发布：把当日精编版内容插入 public/index.html 并部署到 Cloudflare Pages。

流程（四步，任一步失败即中止并报错）：
  1. 插入：替换 mainContent 为当日内容；BRIEFS 追加/更新当日条目；默认期切到当日
  2. 自检：运行 scripts/check_briefs.py 校验本地文件（BRIEFS 完整性、默认期标记、renderBrief）
  3. 部署：后台运行 wrangler pages deploy（API Token 环境变量认证，防交互挂起），轮询输出
  4. 复检：再次运行 check_briefs.py 校验线上

用法:
  python scripts/publish_daily.py --content <当日精编版内容.html> [--date 2026-08-18] [--label "2026年8月18日 · 星期二"]

说明:
  --date 默认取当天（UTC+8）；--label 默认自动生成中文日期标签。
  部署凭证从环境变量读取：CLOUDFLARE_API_TOKEN / CLOUDFLARE_ACCOUNT_ID（不写死在脚本/仓库）。
"""
import argparse
import datetime
import json
import os
import subprocess
import sys
import time

# ---------------- 配置 ----------------
REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML_PATH = os.path.join(REPO_DIR, "public", "index.html")
CHECK_SCRIPT = os.path.join(REPO_DIR, "scripts", "check_briefs.py")
PROJECT_NAME = "daily-brief"
BRANCH = "main"
MC_TAG = '<div class="main-content hidden" id="mainContent">'
B_MARKER = "const BRIEFS = "
DEPLOY_POLL_SEC = 3
DEPLOY_TIMEOUT_SEC = 180


def weekday_cn(dt):
    return "一二三四五六日"[dt.weekday()]


def default_label(date_str):
    dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
    return f"{dt.year}年{dt.month}月{dt.day}日 · 星期{weekday_cn(dt)}"


def find_array_end(text, start):
    """状态机：从 start 起找到顶层 ']' 的偏移（正确处理字符串与转义）"""
    n = len(text)
    in_str = False
    esc = False
    depth = 0
    i = start
    while i < n:
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    return -1


def insert_content(html_path, content, date_str, label):
    html = open(html_path, encoding="utf-8").read()
    content = content.strip()

    # 1) 替换 mainContent body
    mc_start = html.find(MC_TAG)
    script_start = html.find("<script", mc_start)
    if mc_start < 0 or script_start < mc_start:
        raise RuntimeError("未找到 mainContent 结构")
    mc_close = html.rfind("</div>", mc_start, script_start) + len("</div>")
    new_body = MC_TAG + "\n" + content + "\n</div>"
    html = html[:mc_start] + new_body + html[mc_close:]

    # 2) BRIEFS 追加/更新当日条目
    b_start = html.find(B_MARKER)
    if b_start < 0:
        raise RuntimeError("未找到 BRIEFS 数组")
    arr_end = find_array_end(html, b_start + len(B_MARKER))
    if arr_end < 0:
        raise RuntimeError("无法定位 BRIEFS 数组闭合")
    arr_text = html[b_start + len(B_MARKER):arr_end + 1]
    briefs = json.loads(arr_text)
    entry = {"date": date_str, "label": label, "content": content}
    idx = next((i for i, b in enumerate(briefs) if b.get("date") == date_str), None)
    if idx is None:
        briefs.append(entry)
        print(f"BRIEFS 追加 {date_str}")
    else:
        briefs[idx] = entry
        print(f"BRIEFS 更新 {date_str}")
    new_arr = json.dumps(briefs, ensure_ascii=False)
    html = html[:b_start + len(B_MARKER)] + new_arr + html[arr_end + 1:]

    # 3) 默认期切到当日（JS 硬编码 selected/findIndex 各一处）
    import re
    pat_sel = re.compile(r"b\.date === '(\d{4}-\d{2}-\d{2})' \? 'selected' : ''")
    pat_idx = re.compile(r"BRIEFS\.findIndex\(b => b\.date === '(\d{4}-\d{2}-\d{2})'\)")
    m1 = pat_sel.search(html)
    m2 = pat_idx.search(html)
    if not m1 or not m2:
        raise RuntimeError("未找到默认期 JS 标记")
    html = html[:m1.start()] + f"b.date === '{date_str}' ? 'selected' : ''" + html[m1.end():]
    html = html[:m2.start()] + f"BRIEFS.findIndex(b => b.date === '{date_str}')" + html[m2.end():]
    print(f"默认期已切换为 {date_str}")

    open(html_path, "w", encoding="utf-8").write(html)
    print(f"已写回 {html_path}（{len(html)} 字符）")


def run_check(extra_args=None):
    cmd = [sys.executable, CHECK_SCRIPT] + (extra_args or [])
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(r.stdout.strip())
    if r.stderr.strip():
        print("STDERR:", r.stderr.strip())
    return r.returncode == 0


def read_out(path):
    """兼容 PowerShell `*>` 重定向的 UTF-16 输出与 cmd 的 GBK 输出"""
    raw = open(path, "rb").read()
    for enc in ("utf-16", "utf-8-sig", "utf-8", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def deploy():
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    acct = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    if not token or not acct:
        raise RuntimeError("缺少环境变量 CLOUDFLARE_API_TOKEN / CLOUDFLARE_ACCOUNT_ID")
    out_file = os.path.join(REPO_DIR, "deploy_out.txt")
    if os.path.exists(out_file):
        os.remove(out_file)
    # 后台运行防挂起（wrangler 交互输出在 agent 会话可能阻塞）
    ps = (
        f'$env:CLOUDFLARE_API_TOKEN="{token}"; '
        f'$env:CLOUDFLARE_ACCOUNT_ID="{acct}"; '
        f'$env:CI="1"; '
        f'cd "{REPO_DIR}"; '
        f'npx wrangler pages deploy public --project-name={PROJECT_NAME} --branch={BRANCH} '
        f'--commit-dirty=true *> "{out_file}" 2>&1'
    )
    subprocess.Popen(["powershell", "-NoProfile", "-Command", ps], creationflags=subprocess.CREATE_NO_WINDOW)
    deadline = time.time() + DEPLOY_TIMEOUT_SEC
    while time.time() < deadline:
        time.sleep(DEPLOY_POLL_SEC)
        if os.path.exists(out_file) and os.path.getsize(out_file) > 0:
            text = read_out(out_file)
            if "Deployment complete" in text:
                print(text.strip())
                m = [ln for ln in text.splitlines() if "https://" in ln and "pages.dev" in ln]
                return m[-1].strip() if m else "已部署"
            if "Error" in text or "ERROR" in text or "✘" in text or "✗" in text:
                raise RuntimeError("部署失败:\n" + text)
    raise RuntimeError(f"部署超时（{DEPLOY_TIMEOUT_SEC}s）")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--content", required=True, help="当日精编版内容 HTML 文件路径")
    ap.add_argument("--date", default=None, help="YYYY-MM-DD，默认今天（UTC+8）")
    ap.add_argument("--label", default=None, help="日期显示标签，默认自动生成")
    ap.add_argument("--skip-deploy", action="store_true", help="只做插入+自检，不部署")
    args = ap.parse_args()

    if args.date:
        date_str = args.date
    else:
        date_str = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime("%Y-%m-%d")
    label = args.label or default_label(date_str)

    content_path = os.path.abspath(args.content)
    if not os.path.exists(content_path):
        print(f"FAIL 内容文件不存在: {content_path}")
        sys.exit(1)
    content = open(content_path, encoding="utf-8").read()

    print(f"== 1/4 插入内容 {date_str} ==")
    insert_content(HTML_PATH, content, date_str, label)

    print(f"\n== 2/4 本地自检 ==")
    if not run_check():
        print("FAIL 本地自检未通过，中止发布")
        sys.exit(1)

    if args.skip_deploy:
        print("\n已跳过部署（--skip-deploy）")
        sys.exit(0)

    print(f"\n== 3/4 部署到 Cloudflare Pages ==")
    url = deploy()
    print(f"部署完成: {url}")

    print(f"\n== 4/4 线上复检 ==")
    if not run_check():
        print("FAIL 线上复检未通过，请人工检查")
        sys.exit(1)
    print("OK 发布流程全部通过")


if __name__ == "__main__":
    main()
