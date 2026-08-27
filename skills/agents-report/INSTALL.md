# agents-report installation

> **正式安装：** 从仓库根目录按 [INSTALL.md](../../INSTALL.md) 的 Agent
> 安装契约执行（`install/install.py` + 创建 Cron 任务）。以下为本地开发
> 运行方式，仅用于手工检查数据。

## 依赖

- Python 3.10+
- `feedparser` only for the compatibility agents-radar collector
- AI HOT network access
- CodexRadar network access for the efficiency block
- A producer-owned local radar reader for the open-source section

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

LOCAL_OPEN_SOURCE_RADAR_READER="/path/to/local-radar-reader.py" \
CODEXRADAR_CONFIG="$PWD/skills/agents-report/config/codexradar_watch.json" \
python3 skills/agents-report/scripts/agents_radar_prefetch.py
```

## Runtime run

Use `adapters/hermes/` or `adapters/openclaw/` to provide:

### Current report path

- `LOCAL_OPEN_SOURCE_RADAR_READER`（独立本地雷达 reader；输出当天快照、质量状态、`hot_today`/`fresh_hot`/`new_projects` 和最终分类映射）
- `CODEXRADAR_CONFIG`
- `AIHOT_V1_BASE`

### Compatibility utilities only

- `AGENTS_RADAR_COLLECTOR`（旧版 collector）
- `AGENTS_RADAR_OUTPUT_DIR`（旧版 collector 输出）
- `AGENTS_RADAR_QUALITY_CONFIG`
- `AGENTS_RADAR_QUALITY_MODULE_DIR`（质量模块不与预取入口同目录时）

The reader integration is deliberately explicit. The core script does not
search Hermes/OpenClaw directories or infer a producer Job ID. Configure the
reader supplied by the independent local radar; if that reader parses the
independently delivered Markdown report, configure its report directory in the
runtime environment as well.

## Verification

```bash
python3 -m py_compile skills/agents-report/scripts/*.py
python3 -m unittest discover -s tests -p 'test_*.py'

# Check a rendered report without network access.
python3 skills/agents-report/scripts/agents_radar_quality_check.py \
  --report /path/to/report.md --strict
```
