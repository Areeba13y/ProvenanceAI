import sqlite3
from pathlib import Path

from forensic_engine import ForensicEngine


def fresh(tmp):
    return ForensicEngine(tmp)


def test_original_has_no_editor_findings(tmp_path):
    r = fresh(tmp_path).analyze("sample_data/original.png")
    assert r["ok"] and r["integrity"]["match"]
    assert not any(f["type"] == "metadata_software_tag" for f in r["findings"])


def test_edited_has_findings(tmp_path):
    r = fresh(tmp_path).analyze("sample_data/edited.png")
    types = {f["type"] for f in r["findings"]}
    assert {"metadata_software_tag", "metadata_date_mismatch"} <= types


def test_duplicate_upload_reuses_id(tmp_path):
    e = fresh(tmp_path)
    a = e.analyze("sample_data/original.png")
    b = e.analyze("sample_data/original.png")
    assert a["evidence_id"] == b["evidence_id"] and b["duplicate_upload"]


def test_bad_file_rejected(tmp_path):
    bad = tmp_path / "fake.png"
    bad.write_text("not an image")
    r = fresh(tmp_path / "ws").analyze(bad)
    assert not r["ok"]


def test_tampered_log_detected(tmp_path):
    e = fresh(tmp_path)
    e.analyze("sample_data/original.png")
    assert e.custody.verify_chain()[0]
    with sqlite3.connect(e.custody.db_path) as c:
        c.execute("UPDATE custody SET action='SOMETHING_ELSE' WHERE id=1")
    assert not e.custody.verify_chain()[0]


def test_tampered_file_detected(tmp_path):
    e = fresh(tmp_path)
    r = e.analyze("sample_data/original.png")
    p = Path(r["integrity"] and e._stored(r["evidence_id"]))
    p.chmod(0o644)
    p.write_bytes(p.read_bytes() + b"x")
    assert not e.verify_integrity(r["evidence_id"])["match"]
