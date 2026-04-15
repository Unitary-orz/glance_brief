#!/usr/bin/env python3
"""
agents-radar 生态日报 — RSS 原始内容抓取

脚本职责：
- 读取 RSS 并选出每个 source 的最新文章
- 支持按 block 号或章节名过滤输出
- 暴露文章元数据和结构线索，便于 LLM 后续归纳
"""

import html
import os
import re
import sys
import argparse
from datetime import datetime
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

FEED_URL = "https://duanyytop.github.io/agents-radar/feed.xml"
OUTPUT_DIR = "/root/.openclaw/workspace-lionclaw/data/news"
DEFAULT_TZ = "Asia/Shanghai"

SOURCE_RULES = {
    "ai-agents": {
        "label": "OpenClaw生态",
        "match_tokens": ("ai-agents",),
    },
    "ai-cli": {
        "label": "AI CLI工具横向对比",
        "match_tokens": ("ai-cli",),
    },
    "ai-trending": {
        "label": "AI开源趋势",
        "match_tokens": ("ai-trending",),
    },
}


def extract_date(text):
    if not text:
        return None
    match = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    return match.group(1) if match else None


def extract_entry_date(entry):
    link_date = extract_date(getattr(entry, "link", ""))
    if link_date:
        return link_date

    for field in ("published", "updated"):
        value = getattr(entry, field, None)
        date = extract_date(value)
        if date:
            return date
        if value:
            try:
                return parsedate_to_datetime(value).date().isoformat()
            except (TypeError, ValueError, IndexError):
                pass

    for field in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, field, None)
        if parsed:
            return datetime(*parsed[:6]).date().isoformat()

    return "未知"


def get_expected_report_date(now=None, tz_name=DEFAULT_TZ):
    tz = ZoneInfo(tz_name)
    current = now.astimezone(tz) if now else datetime.now(tz)
    return current.date().isoformat()


def validate_report_date(feeds, expected_date):
    dates = {source: extract_entry_date(entry) for source, entry in feeds.items()}
    unique_dates = {date for date in dates.values() if date and date != "未知"}

    if len(unique_dates) > 1:
        raise ValueError(f"mismatched report dates: {dates}")

    report_date = next(iter(unique_dates), "未知")
    if report_date != expected_date:
        raise ValueError(f"stale report date: expected {expected_date}, got {report_date}")

    return report_date


def match_source(entry):
    link = (getattr(entry, "link", "") or "").lower()
    for source_id, rule in SOURCE_RULES.items():
        if any(token in link for token in rule["match_tokens"]):
            return source_id
    return None


def is_chinese_text(text):
    return any(ord(char) > 127 for char in text or "")


def strip_html(text):
    if not text:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<hr\s*/?>", "\n__HR__\n", text)
    text = re.sub(r'<a href="[^"]+">([^<]+)</a>', r"\1", text)
    text = re.sub(r"<tr>", "\n", text)
    text = re.sub(r"</tr>", "", text)
    text = re.sub(r"<t[dh][^>]*>", " | ", text)
    text = re.sub(r"</t[dh]>", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def get_content(entry):
    if hasattr(entry, "content") and entry.content:
        return entry.content[0].value
    return entry.get("summary", "") or entry.get("description", "")


def split_blocks(text):
    blocks = [block.strip() for block in re.split(r"__HR__", text) if block.strip()]
    return blocks if blocks else [text.strip()]


def infer_block_title(block):
    # Try <h2> tag first
    match = re.search(r"<h2[^>]*>([^<]+)</h2>", block)
    if match:
        return match.group(1).strip()[:120]
    # Fall back to first non-empty line
    for line in block.splitlines():
        line = line.strip()
        if line:
            return line[:120]
    return "(empty)"


def parse_feed():
    import feedparser

    feed = feedparser.parse(FEED_URL)
    if getattr(feed, "bozo", False) and not getattr(feed, "entries", None):
        raise RuntimeError(f"RSS parse failed: {feed.bozo_exception!r}")

    results = {}
    for entry in feed.entries:
        source_id = match_source(entry)
        if not source_id:
            continue

        date = extract_entry_date(entry)
        if date == "未知":
            continue

        key = (source_id, date)
        current = results.get(key)
        if current is None:
            results[key] = entry
            continue

        current_title = getattr(current, "title", "")
        entry_title = getattr(entry, "title", "")
        if is_chinese_text(entry_title) and not is_chinese_text(current_title):
            results[key] = entry

    final = {}
    for (source_id, date), entry in results.items():
        if source_id not in final or date > extract_entry_date(final[source_id]):
            final[source_id] = entry
    return final


def format_entry(source_id, entry):
    rule = SOURCE_RULES[source_id]
    date = extract_entry_date(entry)
    content_html = get_content(entry)
    text = strip_html(content_html)
    blocks = split_blocks(text)

    lines = []
    lines.append(f"=== SOURCE: {source_id} | DATE: {date} ===")
    lines.append(f"LABEL: {rule['label']}")
    lines.append(f"TITLE: {getattr(entry, 'title', '').strip()}")
    lines.append(f"LINK: {getattr(entry, 'link', '').strip()}")
    lines.append(f"BLOCK_COUNT: {len(blocks)}")
    lines.append("")
    for index, block in enumerate(blocks, start=1):
        lines.append(f"--- BLOCK {index} | TITLE: {infer_block_title(block)} ---")
        lines.append(block)
        lines.append("")
    return "\n".join(lines).rstrip()


def save_output(output, report_date):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, f"agents-radar-{report_date}.txt")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(output)
    return output_path


def filter_sources(feeds, source_id=None):
    if not source_id:
        return feeds
    if source_id not in SOURCE_RULES:
        raise ValueError(f"unknown source: {source_id}")
    if source_id not in feeds:
        raise ValueError(f"source has no matching entry: {source_id}")
    return {source_id: feeds[source_id]}


def parse_sections(spec_str):
    """
    Parse --sections argument.
    Supports:
    - Numbers: "ai-agents:3,6,7"
    - Names: "ai-agents:今日速览,社区热点"
    - Mixed: "ai-agents:3,今日速览"
    - Ranges: "ai-agents:13-19"
    """
    if not spec_str:
        return None

    spec_str = spec_str.strip()
    result = {}

    source_prefixes = '|'.join(SOURCE_RULES.keys())
    parts = re.split(r'\s+(?=(?:' + source_prefixes + r'):)', spec_str)

    if len(parts) == 1 and re.search(r'(?:' + source_prefixes + r'):[^,]+,', parts[0]):
        parts = re.split(r'(?=(?:' + source_prefixes + r'):)', parts[0])
        parts = [p for p in parts if p.strip()]

    for part in parts:
        part = part.strip()
        if not part:
            continue

        source_id = None
        for sid in SOURCE_RULES:
            if part.startswith(sid + ":"):
                source_id = sid
                ranges = part[len(sid)+1:]
                break
        if not source_id:
            continue

        nums = set()
        names = set()
        for token in ranges.split(","):
            token = token.strip()
            if not token:
                continue
            if token.isdigit():
                nums.add(int(token))
            elif "-" in token:
                parts_ = token.split("-", 1)
                if len(parts_) == 2 and parts_[0].isdigit() and parts_[1].isdigit():
                    nums.update(range(int(parts_[0]), int(parts_[1]) + 1))
            else:
                names.add(token)

        if nums or names:
            result[source_id] = {"nums": nums, "names": names}

    return result if result else None


def format_entry_filtered(source_id, entry, filter_spec):
    """Output filtered blocks: by number OR by title name (substring match)."""
    rule = SOURCE_RULES[source_id]
    date = extract_entry_date(entry)
    content_html = get_content(entry)
    text = strip_html(content_html)
    blocks = split_blocks(text)

    wanted_nums = filter_spec.get("nums", set())
    wanted_names = {n.lower() for n in filter_spec.get("names", set())}

    lines = []
    lines.append(f"=== SOURCE: {source_id} | DATE: {date} ===")
    lines.append(f"LABEL: {rule['label']}")
    lines.append(f"TITLE: {getattr(entry, 'title', '').strip()}")
    lines.append(f"LINK: {getattr(entry, 'link', '').strip()}")
    lines.append(f"BLOCK_COUNT: {len(blocks)}")
    lines.append("")

    for index, block in enumerate(blocks, start=1):
        block_title = infer_block_title(block)
        title_lower = block_title.lower()

        if wanted_nums and index in wanted_nums:
            lines.append(f"--- BLOCK {index} | TITLE: {block_title} ---")
            lines.append(block)
            lines.append("")
        elif wanted_names:
            # Match if name appears in block title (case-insensitive)
            # Use first match only for names that appear in multiple places
            for name in wanted_names:
                if name.lower() in title_lower:
                    lines.append(f"--- BLOCK {index} | TITLE: {block_title} ---")
                    lines.append(block)
                    lines.append("")
                    # Remove used name to avoid duplicate matches
                    wanted_names.discard(name)
                    break

    return "\n".join(lines).rstrip()


def parse_args():
    parser = argparse.ArgumentParser(description="Fetch latest agents-radar RSS.")
    parser.add_argument("--source", choices=sorted(SOURCE_RULES.keys()),
                      help="只输出指定 source")
    parser.add_argument("--sections", type=str,
                      help="只输出指定 blocks/章节，例: ai-agents:今日速览,社区热点 ai-trending:3,4,6,7")
    return parser.parse_args()


def main():
    args = parse_args()
    feeds = parse_feed()
    if not feeds:
        print("ERROR: 未找到 agents-radar 报告", file=sys.stderr)
        return 1

    feeds = filter_sources(feeds, args.source)
    expected_date = get_expected_report_date()
    report_date = validate_report_date(feeds, expected_date)

    section_filter = parse_sections(args.sections)

    parts = []
    for source_id in SOURCE_RULES:
        entry = feeds.get(source_id)
        if not entry:
            continue
        if section_filter and source_id in section_filter:
            parts.append(format_entry_filtered(source_id, entry, section_filter[source_id]))
        elif section_filter:
            continue
        else:
            parts.append(format_entry(source_id, entry))

    output = "\n\n".join(parts)
    output_path = save_output(output, report_date)
    print(f"Output saved to: {output_path}")
    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())