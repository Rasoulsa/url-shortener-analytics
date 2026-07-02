# Contributing

## Branching Strategy

| Branch | Purpose |
|--------|---------|
| `main` | Protected. Always working. Tagged releases only. |
| `feat/<dayN>-<desc>` | New features → PR into main |
| `docs/<dayN>-<desc>` | Documentation → PR into main |
| `test/<dayN>-<desc>` | Tests → PR into main |
| `chore/<dayN>-<desc>` | Tooling, config → PR into main |
| `ci/<desc>` | CI/CD → PR into main |
| `fix/<desc>` | Bug fixes → PR into main |

## Commit Convention

- feat(shortener): add Base62 generation with SETNX uniqueness
- fix(redirect): correct 410 response on expired link
- docs(design): document caching strategy trade-offs
- test(auth): add API key validation tests
- chore(docker): add healthcheck to api service
- ci(github): add uv-based lint and test workflow

## Workflow

```bash
# 1. Branch from latest main
git checkout main && git pull
git checkout -b feat/dN-your-feature

# 2. Commit often
git commit -m "feat(scope): what and why"

# 3. Push and open PR into main
git push -u origin feat/dN-your-feature
# CI must pass before merge

# 4. Merge via GitHub PR (--no-ff), delete branch

# Release
git tag -a v1.0.0 -m "Release v1.0.0"
git push origin --tags
```
