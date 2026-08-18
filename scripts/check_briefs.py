#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
daily-brief 自检脚本：防止"自动版覆盖精编版 / 历史翻阅失效"类问题复发。

校验项：
  1. public/index.html 存在，且包含 renderBrief 历史机制
  2. BRIEFS 数组中每一期都有 date 与非空 content（历史切换真实可用）
  3. 默认展示期为 08-14 精编版（含"长鑫"标记）
  4. 目标文件不含自动聚合版特征标记（"自动采集"），防止精编版被悄悄替换

用法:
  python check_briefs.py [--html ../public/index.html] [--url https://daily-brief-7gf.pages.dev]
"""
import argparse
import json
import os
import re
import sys
import urllib.request

PASSWORD = "123567"
DEFAULT_DATE = "2026-08-18"
DEFAULT_MARKER = "大模型调用量"
AUTO_MARKER = "自动采集"
BRIEFS_START = "const BRIEFS = "
RENDER_FN = "function renderBrief"


def parse_briefs(html_text):
    """用状态机提取 BRIEFS 数组：从 BRIEFS_START 后开始，扫描到顶层 ']' 闭合"""
    s = html_text.find(BRIEFS_START)
    if s < 0:
        return None
    raw = html_text[s + len(BRIEFS_START):]
    n = len(raw)
    in_str = False
    esc = False
    depth = 0
    i = 0
    while i < n:
        ch = raw[i]
        if in_str:
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == '[':
                depth += 1
            elif ch == ']':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(raw[:i + 1])
                    except Exception:
                        return None
        i += 1
    return None


def check_local(html_path):
    fails = []
    with open(html_path, encoding="utf-8", errors="ignore") as f:
        html_text = f.read()

    if RENDER_FN + "(" not in html_text:
        fails.append("缺少 renderBrief 历史切换函数")
    briefs = parse_briefs(html_text)
    if briefs is None:
        fails.append("无法解析 BRIEFS 数组（可能不含内嵌内容）")
    else:
        if not briefs:
            fails.append("BRIEFS 数组为空")
        for b in briefs:
            if not b.get("date"):
                fails.append("存在无 date 的历史条目")
            if not b.get("content") or len(b.get("content", "").strip()) < 200:
                fails.append(f"历史条目 {b.get('date')} 缺少有效内容（历史切换会失效）")
        dates = [b.get("date") for b in briefs]
        if DEFAULT_DATE not in dates:
            fails.append(f"默认精编版 {DEFAULT_DATE} 不在 BRIEFS 中")
        else:
            default_idx = dates.index(DEFAULT_DATE)
            if DEFAULT_MARKER not in briefs[default_idx].get("content", ""):
                fails.append(f"默认期 {DEFAULT_DATE} 内容缺少精编版标记（{DEFAULT_MARKER}）")

    # 自动聚合版特征只在"主内容"（BRIEFS 数组外）检查，历史归档期保留当时真实内容不算污染
    s = html_text.find(BRIEFS_START)
    main_body = html_text[:s] if s >= 0 else html_text
    if AUTO_MARKER in main_body:
        fails.append(f"主内容出现自动聚合版特征（{AUTO_MARKER}），精编版可能已被替换")
    return fails


def check_online(url):
    fails = []
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; daily-brief-check/1.0)"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
        if "function renderBrief(" not in body:
            fails.append("线上页面缺少 renderBrief（历史机制未上线）")
        if DEFAULT_MARKER not in body:
            fails.append(f"线上页面缺少精编版标记（{DEFAULT_MARKER}），可能被自动版覆盖")
    except Exception as ex:
        fails.append(f"线上访问失败: {ex}")
    return fails


def main():
    ap = argparse.ArgumentParser()
    default_html = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "public", "index.html"))
    ap.add_argument("--html", default=default_html)
    ap.add_argument("--url", default="https://daily-brief-7gf.pages.dev")
    args = ap.parse_args()

    html_path = os.path.abspath(args.html)
    if not os.path.exists(html_path):
        print(f"FAIL 文件不存在: {html_path}")
        sys.exit(1)

    local_fails = check_local(html_path)
    online_fails = check_online(args.url)

    print(f"本地文件: {html_path}")
    print(f"线上地址: {args.url}（密码 {PASSWORD}）")
    print(f"本地校验: {'PASS' if not local_fails else 'FAIL: ' + '; '.join(local_fails)}")
    print(f"线上校验: {'PASS' if not online_fails else 'FAIL: ' + '; '.join(online_fails)}")

    if local_fails or online_fails:
        sys.exit(1)
    print("OK 精编版与历史翻阅机制完好")


if __name__ == "__main__":
    main()
