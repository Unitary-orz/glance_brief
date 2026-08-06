# Contributing

## Development principles

- Keep prefetch scripts source-first and runtime-independent.
- Do not commit credentials, chat IDs, live Cron IDs, or generated reports.
- Preserve output layout unless a format change is explicitly intended.
- Any format change must update the Prompt, output contract, and tests together.

## Checks

```bash
python3 -m py_compile \
  skills/agents-report/scripts/*.py \
  skills/noon-news/scripts/*.py
python3 -m unittest discover -s tests -p 'test_*.py'
git diff --check
```

## Commit style

Use Conventional Commits, for example:

```text
feat(news): add noon-news prefetch contract
fix(skill): preserve independent source line
refactor(repo): separate runtime adapters from skills
release(repo): publish v0.1.0
```

Keep a commit focused on one logical change when possible.
