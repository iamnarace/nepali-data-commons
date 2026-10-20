import json
from pathlib import Path

import pytest

from nepali_data_commons.cli import main
from nepali_data_commons.records import read_jsonl, validate_dataset, validate_record
from nepali_data_commons.workflow import WorkflowError, export, remove, review

SAMPLE = Path(__file__).parent.parent / "data" / "sample.jsonl"
GOOD = {"id": "g1", "text_ne": "आज मौसम राम्रो छ।", "kind": "sentence", "license": "CC0-1.0",
        "consent": True, "source_type": "original", "status": "submitted", "contributor": "alice"}


def codes(findings, sev=None):
    return {f.code for f in findings if sev is None or f.severity == sev}


def test_sample_data_is_clean():
    assert validate_dataset(read_jsonl(SAMPLE)) == []


def test_good_record_has_no_findings():
    assert validate_record(GOOD) == []


@pytest.mark.parametrize("patch,code", [
    ({"consent": False}, "consent"),
    ({"license": "GPL-3.0"}, "license"),
    ({"text_ne": "This is only English text"}, "script"),
    ({"text_ne": "g]kfnsf] /fhwfgL sf7df08f}F ;xl/ x'G5 ;fy{s"}, "legacy-font"),
    ({"source_type": "licensed"}, "provenance"),
    ({"status": "done"}, "status"),
    ({"kind": "poem"}, "kind"),
    ({"extra": 1}, "unknown-field"),
    ({"text_ne": "x" * 3000}, "length"),
])
def test_errors(patch, code):
    assert code in codes(validate_record({**GOOD, **patch}), "error")


@pytest.mark.parametrize("patch,code", [
    ({"text_ne": "मेरो नम्बर ९८४१२३४५६७ हो।"}, "pii"),
    ({"text_en": "mail me: a@b.com"}, "pii"),
    ({"text_ne": "मेरो laptop बिग्रियो र office मा छ"}, "code-mixed"),
    ({"text_ne": "ाम राम"}, "malformed"),
])
def test_warnings(patch, code):
    f = validate_record({**GOOD, **patch})
    assert code in codes(f, "warning") and not codes(f, "error")


def test_missing_required_field():
    bad = {k: v for k, v in GOOD.items() if k != "license"}
    assert "missing-field" in codes(validate_record(bad), "error")


def test_dataset_level_duplicates_and_ids():
    base = "आज मौसम धेरै राम्रो छ"
    rows = [{**GOOD, "text_ne": base},
            {**GOOD, "id": "g2", "text_ne": base + " ।"},          # exact after normalisation
            {**GOOD, "id": "g3", "text_ne": base + " है"}]         # 3-gram Jaccard 0.88 -> near
    assert {"duplicate-text", "near-duplicate"} <= codes(validate_dataset(rows))
    assert "duplicate-id" in codes(validate_dataset([GOOD, {**GOOD, "text_ne": "म घर जान्छु।"}]))


def test_self_review_and_missing_reviewer_flagged():
    rows = [{**GOOD, "status": "accepted", "reviewer": "alice"},
            {**GOOD, "id": "g9", "text_ne": "म बजार जान्छु।", "status": "reviewed"}]
    c = codes(validate_dataset(rows), "error")
    assert {"self-review", "review"} <= c


def write(tmp_path, rows):
    p = tmp_path / "d.jsonl"
    p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    return p


def test_review_flow_and_rules(tmp_path):
    p = write(tmp_path, [GOOD])
    with pytest.raises(WorkflowError, match="differ"):
        review(p, "g1", "reviewed", "alice")
    with pytest.raises(WorkflowError, match="cannot move"):
        review(p, "g1", "accepted", "bob")  # must be reviewed first
    review(p, "g1", "reviewed", "bob", "looks natural")
    rec = review(p, "g1", "accepted", "carol")
    assert rec["status"] == "accepted" and read_jsonl(p)[0]["reviewer"] == "carol"
    assert [h["reviewer"] for h in rec["review_history"]] == ["bob", "carol"]
    assert validate_dataset(read_jsonl(p)) == []  # history field is schema-valid
    info = export(p, tmp_path / "pub.jsonl")
    assert "bob, carol" in Path(info["card"]).read_text(encoding="utf-8")
    with pytest.raises(WorkflowError, match="no record"):
        review(p, "zzz", "rejected", "bob")


def test_cannot_approve_errors_and_warnings_need_ack(tmp_path):
    p = write(tmp_path, [{**GOOD, "text_ne": "मेरो नम्बर ९८४१२३४५६७ हो।"},
                         {**GOOD, "id": "g2", "consent": False}])
    with pytest.raises(WorkflowError, match="warnings"):
        review(p, "g1", "reviewed", "bob")
    assert review(p, "g1", "reviewed", "bob", ack_warnings=True)["status"] == "reviewed"
    with pytest.raises(WorkflowError, match="errors"):
        review(p, "g2", "reviewed", "bob", ack_warnings=True)
    assert review(p, "g2", "rejected", "bob")["status"] == "rejected"  # rejecting is always allowed


def test_remove_logs_without_content(tmp_path):
    p = write(tmp_path, [GOOD, {**GOOD, "id": "g2", "text_ne": "म घर जान्छु।"}])
    log = remove(p, "g1", "contributor requested removal", now="2026-10-20T00:00:00Z")
    assert [r["id"] for r in read_jsonl(p)] == ["g2"]
    entry = json.loads(log.read_text(encoding="utf-8"))
    assert entry == {"id": "g1", "reason": "contributor requested removal", "date": "2026-10-20T00:00:00Z"}
    assert "मौसम" not in log.read_text(encoding="utf-8")
    with pytest.raises(WorkflowError):
        remove(p, "nope", "x")
    with pytest.raises(WorkflowError):
        remove(p, "g2", "  ")


def accepted(rid, text, lic="CC0-1.0", contributor="alice"):
    return {**GOOD, "id": rid, "text_ne": text, "license": lic, "status": "accepted",
            "reviewer": "bob", "contributor": contributor}


def test_export_only_accepted_hides_contributor_and_writes_card(tmp_path):
    p = write(tmp_path, [accepted("a", "म घर जान्छु।"), GOOD,
                         {**GOOD, "id": "r", "status": "rejected", "reviewer": "bob"}])
    info = export(p, tmp_path / "out" / "v1.jsonl", now="2026-10-20T00:00:00Z")
    rows = read_jsonl(info["file"])
    assert [r["id"] for r in rows] == ["a"] and "contributor" not in rows[0]
    card = Path(info["card"]).read_text(encoding="utf-8")
    assert info["sha256"] in card and "ndc remove" in card and "2026-10-20" in card
    info2 = export(p, tmp_path / "v1.csv", fmt="csv", include_contributor=True)
    assert "contributor" in Path(info2["file"]).read_text(encoding="utf-8").splitlines()[0]


def test_export_refuses_mixed_licenses_and_empty(tmp_path):
    p = write(tmp_path, [accepted("a", "म घर जान्छु।"), accepted("b", "म बजार जान्छु।", "CC-BY-4.0")])
    with pytest.raises(WorkflowError, match="several licenses"):
        export(p, tmp_path / "o.jsonl")
    assert export(p, tmp_path / "o.jsonl", allow_mixed_licenses=True)["records"] == 2
    with pytest.raises(WorkflowError, match="no accepted"):
        export(write(tmp_path, [GOOD]), tmp_path / "x.jsonl")


def test_cli_end_to_end(tmp_path, capsys):
    p = write(tmp_path, [GOOD])
    assert main(["validate", str(p)]) == 0
    assert main(["review", str(p), "--id", "g1", "--status", "reviewed", "--reviewer", "bob"]) == 0
    assert main(["review", str(p), "--id", "g1", "--status", "accepted", "--reviewer", "carol"]) == 0
    out = tmp_path / "pub.jsonl"
    assert main(["export", str(p), "--out", str(out)]) == 0
    assert main(["stats", str(p)]) == 0
    assert '"accepted": 1' in capsys.readouterr().out
    assert main(["remove", str(p), "--id", "g1", "--reason", "test"]) == 0
    assert main(["review", str(p), "--id", "g1", "--status", "reviewed", "--reviewer", "x"]) == 2
    p2 = tmp_path / "bad.jsonl"
    p2.write_text(json.dumps({**GOOD, "consent": False}) + "\n" + "{oops", encoding="utf-8")
    assert main(["validate", str(p2)]) == 2          # invalid JSON line -> clear error
    p2.write_text(json.dumps({**GOOD, "consent": False}) + "\n", encoding="utf-8")
    assert main(["validate", str(p2)]) == 1          # validation errors -> exit 1
    p2.write_text(json.dumps({**GOOD, "text_ne": "मेरो नम्बर ९८४१२३४५६७ हो।"}) + "\n", encoding="utf-8")
    assert main(["validate", str(p2)]) == 0
    assert main(["validate", str(p2), "--strict"]) == 1
    assert main(["init"]) == 0
