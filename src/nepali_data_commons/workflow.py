"""Review workflow, takedowns, export and dataset card generation."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .records import read_jsonl, validate_dataset, validate_record, write_jsonl

TRANSITIONS = {
    "submitted": {"reviewed", "rejected"},
    "reviewed": {"accepted", "rejected"},
    "accepted": {"rejected"},
    "rejected": set(),
}
EXPORT_FIELDS = ["id", "text_ne", "text_en", "kind", "domain", "region", "license",
                 "source_type", "source_url"]


class WorkflowError(ValueError):
    pass


_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(value):
    """Neutralise spreadsheet formula injection: a cell starting with = + - @ (or tab/CR) is prefixed with
    an apostrophe, which Excel/LibreOffice/Sheets show as plain text. Only affects the CSV export."""
    if isinstance(value, str) and value.startswith(_FORMULA_START):
        return "'" + value
    return value


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def review(path, record_id: str, status: str, reviewer: str, notes: str = "",
           ack_warnings: bool = False, attests_fluent_nepali: bool = False) -> dict:
    if not reviewer or not reviewer.strip():
        raise WorkflowError("a reviewer name/handle is required")
    rows = read_jsonl(path)
    rec = next((r for r in rows if str(r.get("id")) == record_id), None)
    if rec is None:
        raise WorkflowError(f"no record with id {record_id!r}")
    cur = rec.get("status")
    if status not in TRANSITIONS.get(cur, set()):
        raise WorkflowError(f"cannot move {record_id!r} from {cur!r} to {status!r}")
    if reviewer == rec.get("contributor"):
        raise WorkflowError("reviewer must differ from the contributor")
    if status in ("reviewed", "accepted"):
        probe = {**rec, "status": status, "reviewer": reviewer}
        findings = validate_record(probe)
        errors = [f for f in findings if f.severity == "error"]
        if errors:
            raise WorkflowError("cannot approve a record with errors: "
                                + "; ".join(f"{f.code}: {f.message}" for f in errors))
        warnings = [f for f in findings if f.severity == "warning"]
        if warnings and not ack_warnings:
            raise WorkflowError("record has warnings; inspect them and re-run with --ack-warnings: "
                                + "; ".join(f"{f.code}: {f.message}" for f in warnings))
    rec["status"] = status
    rec["reviewer"] = reviewer
    rec.setdefault("review_history", []).append(
        {"status": status, "reviewer": reviewer, "date": _now(),
         "attests_fluent_nepali": bool(attests_fluent_nepali)})
    if notes:
        rec["review_notes"] = notes
    write_jsonl(path, rows)
    return rec


def remove(path, record_id: str, reason: str, now: str | None = None) -> Path:
    """Remove a record and append a content-free entry to ``<file>.takedowns.jsonl``."""
    if not reason.strip():
        raise WorkflowError("a reason is required (it is recorded in the takedown log)")
    rows = read_jsonl(path)
    kept = [r for r in rows if str(r.get("id")) != record_id]
    if len(kept) == len(rows):
        raise WorkflowError(f"no record with id {record_id!r}")
    write_jsonl(path, kept)
    log = Path(str(path) + ".takedowns.jsonl")
    with log.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"id": record_id, "reason": reason, "date": now or _now()},
                           ensure_ascii=False) + "\n")
    return log


def export(path, out, fmt: str = "jsonl", include_contributor: bool = False,
           allow_mixed_licenses: bool = False, now: str | None = None) -> dict:
    rows = read_jsonl(path)
    accepted = [r for r in rows if r.get("status") == "accepted"]
    if not accepted:
        raise WorkflowError("no accepted records to export")
    errors = [f for f in validate_dataset(rows) if f.severity == "error"
              and any(str(r.get("id")) == f.record_id and r.get("status") == "accepted"
                      for r in rows)]
    if errors:
        raise WorkflowError("accepted records have errors: " + "; ".join(str(e) for e in errors[:5]))
    lic = Counter(r["license"] for r in accepted)
    if len(lic) > 1 and not allow_mixed_licenses:
        raise WorkflowError(f"accepted records use several licenses {dict(lic)}; export one license "
                            "at a time or pass --allow-mixed (the per-row license column is kept)")
    fields = EXPORT_FIELDS + (["contributor"] if include_contributor else [])
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "jsonl":
        with out.open("w", encoding="utf-8") as f:
            for r in accepted:
                f.write(json.dumps({k: r.get(k) for k in fields if k in r}, ensure_ascii=False) + "\n")
    elif fmt == "csv":
        # utf-8-sig: the BOM makes Excel open Devanagari correctly; csv_safe blocks formula injection.
        with out.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            for r in accepted:
                w.writerow({k: csv_safe(r.get(k, "")) for k in fields})
    else:
        raise WorkflowError("format must be jsonl or csv")
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    card = out.with_name(out.stem + ".DATASET_CARD.md")
    card.write_text(dataset_card(rows, accepted, out.name, digest, now), encoding="utf-8")
    return {"records": len(accepted), "sha256": digest, "card": str(card), "file": str(out)}


def stats(rows: list[dict]) -> dict:
    return {
        "records": len(rows),
        "status": dict(Counter(r.get("status") for r in rows)),
        "license": dict(Counter(r.get("license") for r in rows)),
        "kind": dict(Counter(r.get("kind") for r in rows)),
        "with_english": sum(1 for r in rows if r.get("text_en")),
        "regions": dict(Counter(r.get("region") or "unspecified" for r in rows)),
        "domains": dict(Counter(r.get("domain") or "unspecified" for r in rows)),
    }


def dataset_card(rows, accepted, filename: str, digest: str, now: str | None = None) -> str:
    s = stats(accepted)
    fluent = sum(1 for r in accepted
                 if any(h.get("attests_fluent_nepali") for h in r.get("review_history", [])))
    reviewers = sorted({h["reviewer"] for r in accepted for h in r.get("review_history", [])}
                       | {r["reviewer"] for r in accepted if r.get("reviewer")})
    lines = [
        f"# Dataset card: {filename}", "",
        f"- Generated: {now or _now()} by nepali-data-commons",
        f"- Records exported: {len(accepted)} (of {len(rows)} in the working file)",
        f"- SHA-256 of exported file: `{digest}`",
        f"- Licenses: {s['license']}",
        f"- Records with English text: {s['with_english']}",
        f"- Kinds: {s['kind']}", f"- Regions (self-reported): {s['regions']}",
        f"- Domains (self-reported): {s['domains']}",
        f"- Reviewers (handles): {', '.join(reviewers) or 'none'}",
        f"- Accepted records with a reviewer who *attested* fluent Nepali: {fluent} of {len(accepted)} "
        "(self-declared; not verified by this tool)", "",
        "## Provenance", "",
        "Each row carries `license`, `source_type` and (when not original) `source_url`. Contributors "
        "attested ownership/consent at submission (`consent: true`). The attestation is not independently "
        "verified.", "",
        "## Quality process", "",
        "Rows passed automatic checks (schema, Devanagari share, malformed sequences, possible personal "
        "data, duplicates) and were accepted by a reviewer different from the contributor. Automatic checks "
        "are heuristics; a passing row is not guaranteed to be correct, natural or free of personal data.", "",
        "## Known limitations", "",
        "- Not a representative sample of Nepali speakers; region/domain fields are self-reported and sparse.",
        "- Reviewer expertise is not verified by this tool.",
        "- Counts above describe this export only.", "",
        "## Corrections and removal", "",
        "Open an issue with the row `id`. Removal is performed with `ndc remove`, which deletes the row and "
        "records a content-free entry (id, reason, date) in `<file>.takedowns.jsonl`. Re-export afterwards; "
        "downstream users should refresh to the latest version.",
    ]
    return "\n".join(lines) + "\n"
