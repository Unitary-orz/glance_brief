# noon-news installation

> **正式安装：** 从仓库根目录按 [INSTALL.md](../../INSTALL.md) 的 Agent
> 安装契约执行（`install/install.py` + 创建 Cron 任务）。以下为本地开发
> 运行方式，仅用于手工检查数据。

## Dependencies

- Python 3.10+
- `curl`
- `feedparser` for the RSS collector
- external news-aggregator and news-summary skills

## 安装依赖

完整仓库 checkout 时，从仓库根目录执行：

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

## Local run

From the repository root:

```bash
NEWS_AGGREGATOR_SCRIPT=/path/to/fetch_news.py \
NEWS_SUMMARY_SCRIPT=/path/to/fetch_rss.py \
python3 skills/noon-news/scripts/noon_news_prefetch.py
```

The script emits JSON and does not send a message.

## Runtime run

Use the runtime adapter to set:

- `NEWS_PYTHON`
- `NEWS_AGGREGATOR_SCRIPT`
- `NEWS_SUMMARY_SCRIPT`
- `AIHOT_V1_BASE`
- `NOON_AIHOT_WINDOW`（`24h` 或 `7d`）
- `NOON_AIHOT_LIMIT`

## Verification

```bash
python3 -m py_compile skills/noon-news/scripts/noon_news_prefetch.py
python3 -m unittest discover -s tests -p 'test_*.py'
```
