# Contributing

## Contribute data (no coding needed)
1. Copy `data/sample.jsonl` to `data/<your-handle>-<topic>.jsonl` (or run `ndc init` for one example record).
2. Add records following the schema in the README. Set `status` to `submitted`.
3. Run `ndc validate data/<file>.jsonl` and fix every error; read every warning.
4. Open a pull request using the template. A different person reviews with `ndc review`.
Read [docs/GOVERNANCE.md](docs/GOVERNANCE.md) first — especially what must never be submitted.

## Review data
```bash
ndc validate data/x.jsonl            # look at warnings
ndc review data/x.jsonl --id ID --status reviewed --reviewer YOU [--ack-warnings] [--notes "..."]
ndc review data/x.jsonl --id ID --status accepted --reviewer YOU2
```
Reject (`--status rejected`) anything personal, unnatural, offensive, or with unclear provenance.

## Contribute code
```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
ruff check . && python -m pytest -q
```
Core has no runtime dependencies. New checks need tests for both a positive and a *false-positive*
case (e.g. the phone-number check must not flag ordinary numbers like `१०` or `२०८२`).

## Good first issues (suggested)
- Nepali translations of the CLI messages and governance doc (needs native-speaker review).
- Add a profanity/offensive-content *reviewer aid* (word list with clear provenance and licence).
- Add an optional Hugging Face `datasets` export (kept out of core to stay dependency-free).
- Tune and document the near-duplicate threshold on larger real data.
- Citizenship / PAN / bank-account patterns for the PII check (with false-positive tests).
