## Description
<!-- What does this PR do? Which issue does it close? -->
<!-- Example: Closes #4 — adds Base62 generation with SETNX -->

## Type of change
- [ ] `feat` — new feature
- [ ] `fix` — bug fix
- [ ] `docs` — documentation only
- [ ] `test` — tests only
- [ ] `chore` / `ci` / `refactor`

## What was built
<!-- Brief summary -->

## How to test
\`\`\`bash
docker compose up --build
curl -X POST ...
\`\`\`

## Checklist
- [ ] `uv run ruff check .` passes
- [ ] `uv run ruff format --check .` passes
- [ ] `uv run mypy app` passes
- [ ] `uv run pytest -v` passes
- [ ] Docs updated (JOURNAL / CHANGELOG / README)
- [ ] No secrets committed
