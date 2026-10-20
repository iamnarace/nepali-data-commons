# Data governance and responsible contribution

This project handles *other people's language*. These rules are enforced by tooling where possible and
by review where not.

## What may be contributed
- Text you wrote yourself, or public-domain text, or text under a licence you can name (`CC0-1.0`,
  `CC-BY-4.0`, `CC-BY-SA-4.0`) with a `source_url` — the tool rejects other licences.
- Short, general-purpose language: phrases, sentences, paragraphs, dialogue you invented.

## What must never be contributed
- Private chats, emails, social-media posts of other people, call or voice recordings, anything you
  scraped without permission, text from sites whose terms forbid reuse.
- Personal data: names with contact details, phone numbers, email addresses, ID/account numbers,
  addresses. The validator *flags* these as warnings; a reviewer must reject or remove them.
- Hate speech, harassment, or sexually explicit/harmful content (no automatic filter exists — reviewers
  must reject it; this tool does not detect it).

## Consent
`consent: true` is the contributor's attestation that the points above are true. The tool cannot verify
it. False attestations are grounds for removal of all of that contributor's records.

## Review
`submitted → reviewed → accepted` (or `rejected`). The reviewer must differ from the contributor, must
inspect warnings (`--ack-warnings`), and is recorded in the record. Reviewer language expertise is not
verified by the software; projects using it should publish who may review and how.

## Corrections and removal
Anyone may request correction or removal via the *Correction or removal request* issue template.
Maintainers run `ndc remove`, which deletes the record and appends a content-free entry to
`<file>.takedowns.jsonl`, then re-export. Previously downloaded copies cannot be recalled — the dataset
card tells users to refresh.

## Limits of the automatic checks
Heuristics only: regexes for PII, Devanagari-script ratios, simple malformed-sequence rules, character
3-gram similarity. They have false positives and false negatives. They do not check translation quality,
factual correctness, naturalness, dialect, or offensiveness.
