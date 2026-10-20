# Language review: automated checks vs human review

**No record in `data/sample.jsonl` has been reviewed by a native Nepali speaker.** The six sentences were invented by the
maintainers with AI assistance purely to demonstrate the workflow. They are `status: submitted` and must not be treated as
verified Nepali data.

| Automated (`ndc validate`) — heuristics | Human review required |
|---|---|
| Devanagari share, malformed sequences (leading combining marks, double vowel signs, U+FFFD, stray ZWJ/ZWNJ), mixed digit systems | Spelling and grammar |
| Punctuation: sentences ending with `.` instead of `।`, no ending mark, space before the mark, repeated marks | Naturalness, register (तिमी/तपाईं/तँ), regional/dialect wording |
| `text_en` identical to `text_ne`, or mostly Devanagari | Translation accuracy and fluency in both directions |
| Possible phone numbers, emails, URLs, IDs, @handles | Names, addresses, culturally sensitive or offensive content |
| Exact and near duplicates | Whether near-duplicates are meaningful variants |

## Recording a language review
`ndc review ... --attests-fluent-nepali` records, in the record's `review_history`, that the reviewer **declares** they are
a fluent Nepali speaker. It is self-declared and unverified. The dataset card reports how many accepted records have such an
attestation, so users can see the difference between "a second person looked at it" and "a self-declared fluent speaker
approved it". Communities using this tool should publish who may review and require more than one reviewer where
quality matters (the tool does not enforce that).

## Checklist for sample-file reviewers
- [ ] Spelling/grammar correct; sentence-ending punctuation as intended.
- [ ] Translation faithful; alternatives noted in `review_notes`.
- [ ] Register appropriate and consistent; regional wording recorded in `region`.
- [ ] No personal data, no sensitive or offensive content.
