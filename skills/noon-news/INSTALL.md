# noon-news installation

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
- `AIHOT_PUBLIC_BASE`
- `NOON_AIHOT_SINCE_HOURS`
- `NOON_AIHOT_TAKE`

## Verification

```bash
python3 -m py_compile skills/noon-news/scripts/noon_news_prefetch.py
python3 -m unittest discover -s tests -p 'test_*.py'
```
