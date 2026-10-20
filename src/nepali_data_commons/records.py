"""Record schema, validation, and JSONL I/O."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import textcheck as tc

LICENSES = {"CC0-1.0", "CC-BY-4.0", "CC-BY-SA-4.0"}
STATUSES = ("submitted", "reviewed", "accepted", "rejected")
SOURCE_TYPES = {"original", "public-domain", "licensed"}
KINDS = {"phrase", "sentence", "paragraph", "dialogue", "other"}
REQUIRED = ("id", "text_ne", "kind", "license", "consent", "source_type", "status")
OPTIONAL = {"text_en", "domain", "region", "contributor", "source_url", "reviewer",
            "review_notes", "review_history", "created"}
MIN_DEV_RATIO = 0.4  # hard floor; code-mixed text above it is allowed but flagged
MAX_CHARS = 2000


@dataclass
class Finding:
    record_id: str
    severity: str  # "error" blocks acceptance; "warning" needs a human look
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.severity.upper():7} {self.record_id}: [{self.code}] {self.message}"


def read_jsonl(path: str | Path) -> list[dict]:
    rows = []
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError(f"{path}:{n}: invalid JSON ({e.msg})") from e
        if not isinstance(obj, dict):
            raise ValueError(f"{path}:{n}: each line must be a JSON object")
        rows.append(obj)
    return rows


def write_jsonl(path: str | Path, rows: list[dict]) -> None:
    """Atomic write: never leaves a half-written dataset file behind."""
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=path.parent or ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def validate_record(r: dict) -> list[Finding]:
    rid = str(r.get("id", "<no id>"))
    out: list[Finding] = []

    def err(code, msg):
        out.append(Finding(rid, "error", code, msg))

    def warn(code, msg):
        out.append(Finding(rid, "warning", code, msg))

    for k in REQUIRED:
        if k not in r or r[k] in (None, ""):
            err("missing-field", f"required field {k!r} is missing or empty")
    unknown = set(r) - set(REQUIRED) - OPTIONAL
    if unknown:
        err("unknown-field", f"unknown field(s): {sorted(unknown)}")
    if r.get("license") not in LICENSES and r.get("license"):
        err("license", f"license must be one of {sorted(LICENSES)}")
    if r.get("status") not in STATUSES and r.get("status"):
        err("status", f"status must be one of {list(STATUSES)}")
    if r.get("kind") not in KINDS and r.get("kind"):
        err("kind", f"kind must be one of {sorted(KINDS)}")
    if r.get("source_type") not in SOURCE_TYPES and r.get("source_type"):
        err("source-type", f"source_type must be one of {sorted(SOURCE_TYPES)}")
    if r.get("consent") is not True:
        err("consent", "contributor must attest consent/ownership (consent: true)")
    if r.get("source_type") in ("public-domain", "licensed") and not r.get("source_url"):
        err("provenance", "source_url is required when source_type is not 'original'")

    text = r.get("text_ne")
    if isinstance(text, str) and text.strip():
        if len(text) > MAX_CHARS:
            err("length", f"text_ne longer than {MAX_CHARS} characters")
        dev, lat = tc.script_ratio(text)
        if dev < MIN_DEV_RATIO:
            if tc.legacy_font_suspect(text):
                err("legacy-font", "looks like legacy-font text (e.g. Preeti); convert to Unicode")
            else:
                err("script", f"only {dev:.0%} Devanagari letters (need >= {MIN_DEV_RATIO:.0%})")
        elif lat > 0.2:
            warn("code-mixed", f"{lat:.0%} Latin letters: check this is intentional code-mixing")
        for issue in tc.devanagari_issues(text):
            warn("malformed", issue)
        for issue in tc.punctuation_issues(text, r.get("kind")):
            warn("punctuation", issue)
        for f in tc.pii_flags(text):
            warn("pii", f"possible personal data: {f}")
    elif "text_ne" in r:
        err("type", "text_ne must be a non-empty string")
    en = r.get("text_en")
    if isinstance(en, str) and isinstance(text, str) and en.strip() and \
            tc.normalize_for_dedup(en) == tc.normalize_for_dedup(text):
        warn("untranslated", "text_en is identical to text_ne")
    if isinstance(en, str) and en.strip() and tc.script_ratio(en)[0] > 0.2:
        warn("text-en-script", "text_en contains a large share of Devanagari; is it really English?")
    if isinstance(en, str):
        for f in tc.pii_flags(en):
            warn("pii", f"possible personal data in text_en: {f}")
    elif en is not None:
        err("type", "text_en must be a string")
    return out


def validate_dataset(rows: list[dict], *, near_threshold: float = 0.85) -> list[Finding]:
    findings: list[Finding] = []
    seen_ids: dict[str, int] = {}
    for r in rows:
        findings += validate_record(r)
        rid = str(r.get("id"))
        seen_ids[rid] = seen_ids.get(rid, 0) + 1
    for rid, c in seen_ids.items():
        if c > 1:
            findings.append(Finding(rid, "error", "duplicate-id", f"id used {c} times"))
    texts = {str(r["id"]): r["text_ne"] for r in rows
             if isinstance(r.get("text_ne"), str) and r.get("id") is not None}
    by_norm: dict[str, list[str]] = {}
    for k, v in texts.items():
        by_norm.setdefault(tc.normalize_for_dedup(v), []).append(k)
    exact_pairs = set()
    for ids in by_norm.values():
        for i in range(1, len(ids)):
            exact_pairs.add((ids[0], ids[i]))
            findings.append(Finding(ids[i], "error", "duplicate-text",
                                    f"same text as {ids[0]} after normalisation"))
    for a, b, j in tc.near_duplicates(texts, near_threshold):
        if (a, b) not in exact_pairs and tc.normalize_for_dedup(texts[a]) != tc.normalize_for_dedup(texts[b]):
            findings.append(Finding(b, "warning", "near-duplicate",
                                    f"similar to {a} (3-gram Jaccard {j})"))
    for r in rows:
        if r.get("status") in ("reviewed", "accepted"):
            if not r.get("reviewer"):
                findings.append(Finding(str(r.get("id")), "error", "review",
                                        "reviewed/accepted records need a reviewer"))
            elif r.get("reviewer") == r.get("contributor"):
                findings.append(Finding(str(r.get("id")), "error", "self-review",
                                        "reviewer must differ from contributor"))
    return findings
