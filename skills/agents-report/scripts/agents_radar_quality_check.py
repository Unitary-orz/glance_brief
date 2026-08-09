#!/usr/bin/env python3
"""Check the latest rendered agents-radar report for open-source issues."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

from open_source_quality import (  # noqa: E402
    format_warnings,
    inspect_source_projects,
    load_quality_config,
    validate_rendered_report,
)


def latest_report(config: dict[str, object]) -> Path | None:
    raw_output_dir = str(config.get("cron_output_dir", "")).strip()
    if not raw_output_dir:
        return None
    output_dir = Path(raw_output_dir)
    files = sorted(output_dir.glob("*.md"), key=lambda path: path.stat().st_mtime)
    return files[-1] if files else None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="检查 agents-radar 最终报告或来源数据的质量契约。"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--report", type=Path, help="检查指定的最终 Markdown 报告")
    group.add_argument("--source", type=Path, help="检查指定的 agents-radar 原始抓取文本")
    parser.add_argument(
        "--latest",
        action="store_true",
        help="检查配置目录中最近一次最终报告（默认行为）",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="发现质量问题时以退出码 1 结束（默认仍返回 0，便于直接作为提醒脚本）",
    )
    parser.add_argument("--json", action="store_true", help="输出完整 JSON 结果")
    parser.add_argument("--config", type=Path, help="质量规则 JSON；默认读取环境变量或 Skill 配置")
    args = parser.parse_args()

    config = load_quality_config(args.config)
    target = args.report
    mode = "report"
    if args.source:
        target = args.source
        mode = "source"
    elif target is None:
        target = latest_report(config)

    if target is None:
        message = (
            "未找到最近一次 agents-radar 最终报告；"
            f"检查目录：{config['cron_output_dir']}"
        )
        print(message, file=sys.stderr)
        return 2

    try:
        text = target.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"无法读取 {target}: {exc}", file=sys.stderr)
        return 2

    result = (
        inspect_source_projects(text, config)
        if mode == "source"
        else validate_rendered_report(text, config)
    )
    result["mode"] = mode
    result["path"] = str(target)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_warnings(result))
        print(f"检查文件：{target}")

    if args.strict and not result.get("ok", False):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
