# agents-report installation

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

CODEXRADAR_CONFIG="$PWD/skills/agents-report/config/codexradar_watch.json" \
AGENTS_RADAR_OUTPUT_DIR="$PWD/runtime-data/agents-radar" \
python3 skills/agents-report/scripts/agents_radar_prefetch.py
```

## Runtime run

Use `adapters/hermes/` or `adapters/openclaw/` to provide:

- `AGENTS_RADAR_COLLECTOR`
- `AGENTS_RADAR_OUTPUT_DIR`
- `CODEXRADAR_CONFIG`
- `AIHOT_V1_BASE`

## Verification

```bash
python3 -m py_compile skills/agents-report/scripts/*.py
python3 -m unittest discover -s tests -p 'test_*.py'
```
