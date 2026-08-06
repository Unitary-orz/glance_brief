#!/usr/bin/env python3
"""Pre-fetch news sources for the noon briefing cron job.

Runs the existing local news collectors and emits one structured JSON payload so
the cron agent only formats/summarizes real source data.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def python_with_modules(*modules: str) -> str:
    """Pick an interpreter that has the collector dependencies installed.

    Cron runs this wrapper with Hermes' venv Python. Some news skills depend on
    packages installed in the system Python, so child collectors must not blindly
    inherit sys.executable.
    """
    candidates = [os.environ.get("NEWS_PYTHON"), "/usr/bin/python3", sys.executable]
    for exe in [c for c in candidates if c]:
        code = "import importlib.util, sys; sys.exit(0 if all(importlib.util.find_spec(m) for m in %r) else 1)" % (modules,)
        try:
            proc = subprocess.run([exe, "-c", code], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        except OSError:
            continue
        if proc.returncode == 0:
            return exe
    return sys.executable

NEWS_AGG_PYTHON = python_with_modules("bs4", "requests")
RSS_PYTHON = python_with_modules("feedparser")

AIHOT_UA = os.environ.get(
    "AIHOT_USER_AGENT",
    "aihot-skill/0.3.6 (+https://aihot.virxact.com/aihot-skill/)",
)
AIHOT_BASE = os.environ.get("AIHOT_PUBLIC_BASE", "https://aihot.virxact.com/api/public")
AIHOT_SINCE_HOURS = int(os.environ.get("NOON_AIHOT_SINCE_HOURS", "24"))
AIHOT_TAKE = int(os.environ.get("NOON_AIHOT_TAKE", "20"))
NEWS_AGGREGATOR_SCRIPT = os.environ.get(
    "NEWS_AGGREGATOR_SCRIPT",
    "news-aggregator-skill/scripts/fetch_news.py",
)
NEWS_SUMMARY_SCRIPT = os.environ.get(
    "NEWS_SUMMARY_SCRIPT",
    "news-summary/scripts/fetch_rss.py",
)
NEWS_SOURCES = os.environ.get(
    "NOON_NEWS_SOURCES",
    "hackernews,github,producthunt,36kr,tencent,weibo,wallstreetcn,v2ex",
)
NEWS_LIMIT = os.environ.get("NOON_NEWS_LIMIT", "8")

COMMANDS = {
    "news_aggregator": [
        NEWS_AGG_PYTHON,
        NEWS_AGGREGATOR_SCRIPT,
        "--source",
        NEWS_SOURCES,
        "--limit",
        NEWS_LIMIT,
    ],
    "rss_summary": [
        RSS_PYTHON,
        NEWS_SUMMARY_SCRIPT,
    ],
}


def parse_jsonish(text: str) -> Any:
    text = text.strip()
    if not text:
        return {"raw_text": "", "parse_error": "stdout was empty"}
    fenced = re.fullmatch(r"```(?:json)?\s*\n?(.*?)\n?```", text, flags=re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw_text": text[:12000], "parse_error": "stdout was not JSON"}


def _normalize_source_items(parsed: Any) -> tuple[list[Any], str | None]:
    if isinstance(parsed, list):
        return parsed, None
    if isinstance(parsed, dict) and isinstance(parsed.get("items"), list):
        return parsed["items"], None
    if isinstance(parsed, dict) and parsed.get("parse_error"):
        return [], str(parsed["parse_error"])
    return [], "source JSON must be a list or an object with an items list"


def _source_failure(error: str, returncode: int | None = None, stderr: str = "") -> dict[str, Any]:
    return {
        "ok": False,
        "returncode": returncode,
        "stderr": stderr[-2000:],
        "items": [],
        "error": error,
    }


def run_source(name: str, cmd: list[str]) -> dict[str, Any]:
    missing = [p for p in cmd[1:2] if p.endswith(".py") and not Path(p).exists()]
    if missing:
        return _source_failure(f"missing script: {missing[0]}")
    try:
        proc = subprocess.run(cmd, text=True, capture_output=True, timeout=180, check=False)
    except subprocess.TimeoutExpired:
        return _source_failure(f"{name} timed out after 180 seconds")
    except OSError as exc:
        return _source_failure(f"{name} could not start: {exc}")

    parsed = parse_jsonish(proc.stdout)
    items, parse_error = _normalize_source_items(parsed)
    error = parse_error if proc.returncode == 0 else f"{name} exited with code {proc.returncode}"
    result = {
        "ok": proc.returncode == 0 and parse_error is None,
        "returncode": proc.returncode,
        "stderr": proc.stderr.strip()[-2000:],
        "items": items if proc.returncode == 0 and parse_error is None else [],
    }
    if error:
        result["error"] = error
    return result


def _curl_available() -> bool:
    return shutil.which("curl") is not None


def _aihot_since_iso() -> str:
    delta = timedelta(hours=AIHOT_SINCE_HOURS)
    return (datetime.now(timezone.utc) - delta).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_aihot() -> dict[str, Any]:
    """Pull aihot selected items from the last N hours for the AI section.

    Uses curl (not requests) so we don't add dependencies and don't accidentally
    send a default browser UA. Retries once on 5xx/timeout per aihot skill spec;
    returns a structured payload even on failure so the agent can degrade
    gracefully (e.g. fall back to V2EX items for AI section).
    """
    if not _curl_available():
        return {"ok": False, "error": "curl not found in PATH", "items": []}

    since = _aihot_since_iso()
    url = f"{AIHOT_BASE}/items?mode=selected&since={since}&take={AIHOT_TAKE}"

    last_err: str | None = None
    for attempt in (1, 2):
        try:
            proc = subprocess.run(
                [
                    "curl",
                    "-sS",
                    "--max-time",
                    "20",
                    "-H",
                    f"User-Agent: {AIHOT_UA}",
                    url,
                ],
                text=True,
                capture_output=True,
                check=False,
            )
        except OSError as exc:
            return {
                "ok": False,
                "error": f"curl could not start: {exc}",
                "since": since,
                "endpoint": url,
                "items": [],
            }
        if proc.returncode == 0 and proc.stdout.strip():
            parsed = parse_jsonish(proc.stdout)
            # aihot wraps items in {count, hasNext, nextCursor, items: [...]};
            # tolerate either shape (bare list or wrapped dict).
            if isinstance(parsed, list):
                items = parsed
            elif isinstance(parsed, dict) and isinstance(parsed.get("items"), list):
                items = parsed["items"]
            else:
                if isinstance(parsed, dict):
                    last_err = parsed.get("parse_error") or "aihot JSON has no items list"
                else:
                    last_err = "aihot returned unexpected payload shape"
                break  # parse error → don't retry
            return {
                "ok": True,
                "items": items,
                "count": len(items),
                "since": since,
                "take": AIHOT_TAKE,
                "endpoint": url,
            }
        last_err = (proc.stderr or "").strip() or f"curl exit {proc.returncode}"
        if attempt == 1:
            import time

            time.sleep(2)  # one backoff before the second attempt

    return {
        "ok": False,
        "error": last_err or "aihot fetch failed after retries",
        "since": since,
        "endpoint": url,
        "items": [],
    }


def main() -> None:
    payload = {"schema_version": 1, **{name: run_source(name, cmd) for name, cmd in COMMANDS.items()}}
    payload["aihot"] = fetch_aihot()
    payload["instructions"] = {
        "source_first": "最终简报只能使用这里抓到的来源；来源不足时明确说信息有限，不要编造。",
        "format": "Feishu markdown：列表项用 '- '，分隔线用 '---'。",
        "ai_section": "AI 主线以 aihot.items 为主信源；不足时用其它来源里 source 含 v2ex 的条目补；都为空就省略整段。",
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
