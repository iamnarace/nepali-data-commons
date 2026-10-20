"""``ndc`` command-line interface."""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .records import read_jsonl, validate_dataset
from .workflow import WorkflowError, export, remove, review, stats

TEMPLATE = {
    "id": "example-001", "text_ne": "यहाँ नेपाली वाक्य लेख्नुहोस्।", "text_en": "Write a Nepali sentence here.",
    "kind": "sentence", "domain": "everyday", "region": "", "contributor": "your-handle",
    "license": "CC0-1.0", "consent": True, "source_type": "original", "status": "submitted",
}


def _validate(a) -> int:
    rows = [r for p in a.files for r in read_jsonl(p)]
    findings = validate_dataset(rows, near_threshold=a.near_threshold)
    errors = [f for f in findings if f.severity == "error"]
    warns = [f for f in findings if f.severity == "warning"]
    if a.format == "json":
        print(json.dumps([f.__dict__ for f in findings], ensure_ascii=False, indent=2))
    else:
        for f in findings:
            print(f)
        print(f"{len(rows)} records: {len(errors)} errors, {len(warns)} warnings")
    return 1 if errors or (a.strict and warns) else 0


def _review(a) -> int:
    rec = review(a.file, a.id, a.status, a.reviewer, a.notes or "", a.ack_warnings, a.attests_fluent_nepali)
    print(f"{rec['id']} -> {rec['status']} (reviewer {rec['reviewer']})")
    return 0


def _remove(a) -> int:
    log = remove(a.file, a.id, a.reason)
    print(f"removed {a.id}; recorded in {log}")
    return 0


def _export(a) -> int:
    info = export(a.file, a.out, a.format, a.include_contributor, a.allow_mixed)
    print(f"exported {info['records']} records -> {info['file']} (card: {info['card']})")
    return 0


def _stats(a) -> int:
    print(json.dumps(stats(read_jsonl(a.file)), ensure_ascii=False, indent=2))
    return 0


def _init(a) -> int:
    print(json.dumps(TEMPLATE, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ndc", description=__doc__)
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate", help="check contribution files")
    v.add_argument("files", nargs="+")
    v.add_argument("--strict", action="store_true", help="treat warnings as failures")
    v.add_argument("--format", choices=["text", "json"], default="text")
    v.add_argument("--near-threshold", type=float, default=0.85)
    v.set_defaults(fn=_validate)
    r = sub.add_parser("review", help="move a record through the review workflow")
    r.add_argument("file")
    r.add_argument("--id", required=True)
    r.add_argument("--status", required=True, choices=["reviewed", "accepted", "rejected"])
    r.add_argument("--reviewer", required=True)
    r.add_argument("--notes")
    r.add_argument("--ack-warnings", action="store_true",
                   help="confirm you inspected the warnings (required to approve if any)")
    r.add_argument("--attests-fluent-nepali", action="store_true",
                   help="record that you, the reviewer, are a fluent Nepali speaker (self-declared, unverified)")
    r.set_defaults(fn=_review)
    d = sub.add_parser("remove", help="takedown: delete a record and log it (content-free)")
    d.add_argument("file")
    d.add_argument("--id", required=True)
    d.add_argument("--reason", required=True)
    d.set_defaults(fn=_remove)
    e = sub.add_parser("export", help="export accepted records plus a dataset card")
    e.add_argument("file")
    e.add_argument("--out", required=True)
    e.add_argument("--format", choices=["jsonl", "csv"], default="jsonl")
    e.add_argument("--include-contributor", action="store_true")
    e.add_argument("--allow-mixed", action="store_true")
    e.set_defaults(fn=_export)
    s = sub.add_parser("stats", help="counts by status, license, kind, region")
    s.add_argument("file")
    s.set_defaults(fn=_stats)
    i = sub.add_parser("init", help="print an example record to start from")
    i.set_defaults(fn=_init)
    a = p.parse_args(argv)
    try:
        return a.fn(a)
    except (WorkflowError, ValueError, OSError) as ex:
        print(f"error: {ex}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
