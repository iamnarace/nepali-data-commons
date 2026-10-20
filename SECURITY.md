# Security policy

## Reporting a vulnerability
Use GitHub's private vulnerability reporting (Security tab → "Report a vulnerability"). If unavailable, open an issue
asking for a private contact channel **without** exploit details. Volunteer-maintained; no guaranteed response time.

## Threat model in brief
- Local CLI; no network access, no server. Contribution files are untrusted *data*.
- **CSV export is formula-injection safe:** cells starting with `=`, `+`, `-`, `@`, tab or CR get a leading apostrophe so
  spreadsheets show them as text. JSONL export is unchanged (raw values). Do not open untrusted CSV in tools that ignore
  this convention.
- File writes to the dataset are atomic (temp file + replace). Takedown logs contain id/reason/date only, never text.
- Personal-data and consent checks are **heuristics** that flag records for a human. They are not a privacy guarantee:
  names and addresses are not detected, and a clean validation does not mean a record is safe to publish.

## Automated checks in CI
`ruff`, `pytest -W error`, dataset validation on every `data/*.jsonl`, `bandit -r src`, `pip-audit` (dev dependencies; no
runtime dependencies), GitHub secret scanning + push protection, Dependabot security updates (+ weekly update PRs for
GitHub Actions and dev tools). These reduce risk; they do not prove absence of vulnerabilities.
