import shutil

from forensic_engine import ForensicEngine


def test_text_change_is_localized(tmp_path):
    r = ForensicEngine(tmp_path).compare("sample_data/original.png", "sample_data/edited.png")
    assert r["ok"] and not r["same_file"]
    hit = [f for f in r["findings"] if f["type"] == "compare_regions_differ"]
    assert hit and "comparison_image" in r["artifacts"]
    # the third message (y ~ 202-252) is the one that changed
    assert any(b["y"] < 252 and b["y"] + b["h"] > 202 for b in hit[0]["regions"])


def test_identical_files(tmp_path):
    shutil.copy("sample_data/original.png", tmp_path / "copy.png")
    r = ForensicEngine(tmp_path / "ws").compare("sample_data/original.png", tmp_path / "copy.png")
    assert r["same_file"] and r["findings"][0]["type"] == "compare_identical_files"


def test_comparison_is_logged(tmp_path):
    e = ForensicEngine(tmp_path)
    r = e.compare("sample_data/original.png", "sample_data/edited.png")
    actions = [x["action"] for x in e.custody.entries(r["evidence_a"]["evidence_id"])]
    assert "COMPARISON" in actions and r["custody_chain_valid"]
