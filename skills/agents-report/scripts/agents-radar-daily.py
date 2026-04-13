#!/usr/bin/env python3
"""
agents-radar 生态日报 — RSS 原始内容抓取
抓取三个报告：
  1. AI Agents 生态日报（OpenClaw 生态）
  2. AI CLI 工具社区动态日报
  3. AI 开源趋势日报（GitHub Trending）
拼接后输出结构化原始文本，格式化由模型完成。
"""

import sys
import re
import html

FEED_URL = "https://duanyytop.github.io/agents-radar/feed.xml"

def parse_feed():
    import feedparser
    feed = feedparser.parse(FEED_URL)
    results = {}
    for e in feed.entries:
        link = e.link.lower()
        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', link)
        date = date_match.group(1) if date_match else None
        if not date:
            continue
        title = e.title or ''
        is_chinese = any(ord(c) > 127 for c in title)

        # ai-agents: OpenClaw 生态日报（覆盖 OpenClaw 项目）
        if "ai-agents" in link and "2026" in link:
            key = ("agents", date)
            already_has = key in results
            prev_is_chinese = already_has and any(ord(c) > 127 for c in results[key].title)
            if not already_has or (is_chinese and not prev_is_chinese):
                results[key] = e

        # ai-cli: AI CLI 工具横向对比（Claude Code / Codex / Gemini CLI 等）
        if "ai-cli" in link and "2026" in link:
            key = ("cli", date)
            already_has = key in results
            prev_is_chinese = already_has and any(ord(c) > 127 for c in results[key].title)
            if not already_has or (is_chinese and not prev_is_chinese):
                results[key] = e

        # ai-trending: AI 开源趋势日报（GitHub Trending）
        if "ai-trending" in link and "2026" in link:
            key = ("trending", date)
            already_has = key in results
            prev_is_chinese = already_has and any(ord(c) > 127 for c in results[key].title)
            if not already_has or (is_chinese and not prev_is_chinese):
                results[key] = e

    # 去除日期后缀，按 kind 保留最新日期的那条
    final = {}
    for (kind, date), entry in results.items():
        if kind not in final or date > extract_date(final[kind].link):
            final[kind] = entry
    return final


def strip_html(text):
    if not text:
        return ""
    # 换行
    text = re.sub(r'<br\s*/?>', '\n', text)
    text = re.sub(r'<hr\s*/?>', '\n__HR__\n', text)
    # 链接文字
    text = re.sub(r'<a href="[^"]+">([^<]+)</a>', r'\1', text)
    # 表格：每行用 | 分隔
    text = re.sub(r'<tr>', '\n', text)
    text = re.sub(r'</tr>', '', text)
    text = re.sub(r'<t[dh][^>]*>', ' | ', text)
    text = re.sub(r'</t[dh]>', '', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = html.unescape(text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def extract_date(link):
    m = re.search(r'(\d{4}-\d{2}-\d{2})', link)
    return m.group(1) if m else "未知"


def get_content(entry):
    if hasattr(entry, 'content') and entry.content:
        return entry.content[0].value
    return entry.get('description', '')


def format_entry(entry, label):
    date = extract_date(entry.link)
    content_html = get_content(entry)
    text = strip_html(content_html)
    blocks = [b.strip() for b in re.split(r'__HR__', text) if b.strip()]

    lines = []
    lines.append(f"=== {label} | {date} ===")
    for i, block in enumerate(blocks):
        lines.append(f"--- 第{i+1}节 ---")
        lines.append(block[:3000])
        lines.append("")
    return '\n'.join(lines)


if __name__ == "__main__":
    feeds = parse_feed()
    if not feeds:
        print("ERROR: 未找到 agents-radar 报告", file=sys.stderr)
        sys.exit(1)

    parts = []
    if "agents" in feeds:
        parts.append(format_entry(feeds["agents"], "OpenClaw生态"))
    if "cli" in feeds:
        parts.append(format_entry(feeds["cli"], "AI CLI工具横向对比"))
    if "trending" in feeds:
        parts.append(format_entry(feeds["trending"], "AI开源趋势"))
    
    output = '\n\n'.join(parts)
    print(output)
