# agents-report installation

> **正式安装：** 从仓库根目录按 [INSTALL.md](../../INSTALL.md) 的 Agent
> 安装契约执行（`install/install.py` + 创建 Cron 任务）。以下为本地开发
> 运行方式，仅用于手工检查数据。

## 依赖

- Python 3.10+
- `feedparser` for agents-radar collector
- AI HOT network access
- CodexRadar network access for the efficiency block

Hermes / OpenClaw adapters may provide a Python interpreter with the external news dependencies installed.

## 安装依赖

从完整仓库根目录执行：

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

## Local run

From the repository root:

```bash
cp skills/agents-report/config/codexradar_watch.example.json skills/agents-report/config/codexradar_watch.json
cp skills/agents-report/config/agents_radar_quality.example.json skills/agents-report/config/agents_radar_quality.json

CODEXRADAR_CONFIG="$PWD/skills/agents-report/config/codexradar_watch.json" \
AGENTS_RADAR_QUALITY_CONFIG="$PWD/skills/agents-report/config/agents_radar_quality.json" \
AGENTS_RADAR_OUTPUT_DIR="$PWD/runtime-data/agents-radar" \
python3 skills/agents-report/scripts/agents_radar_prefetch.py
```

## Runtime run

Use `adapters/hermes/` or `adapters/openclaw/` to provide:

- `AGENTS_RADAR_COLLECTOR`
- `AGENTS_RADAR_OUTPUT_DIR`
- `CODEXRADAR_CONFIG`
- `AGENTS_RADAR_QUALITY_CONFIG`
- `AGENTS_RADAR_QUALITY_MODULE_DIR`（质量模块不与预取入口同目录时）
- `AIHOT_V1_BASE`

## Verification

```bash
python3 -m py_compile skills/agents-report/scripts/*.py
python3 -m unittest discover -s tests -p 'test_*.py'

# Check a rendered report without network access.
python3 skills/agents-report/scripts/agents_radar_quality_check.py \
  --report /path/to/report.md --strict
```
