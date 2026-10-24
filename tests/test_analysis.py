from forensic_engine import ForensicEngine


def types(r):
    return {f["type"] for f in r["findings"]}


def test_clean_jpeg_has_no_attention(tmp_path):
    r = ForensicEngine(tmp_path).analyze("sample_data/photo_original.jpg")
    assert not any(f["severity"] == "attention" for f in r["findings"])


def test_pasted_region_is_localized(tmp_path):
    r = ForensicEngine(tmp_path).analyze("sample_data/photo_tampered.jpg")
    hit = [f for f in r["findings"] if f["severity"] == "attention"]
    assert hit and "analysis_overlay" in r["artifacts"]
    # pasted area is x 220-340, y 150-230: a flagged region must overlap it
    boxes = [b for f in hit for b in f["regions"]]
    assert any(b["x"] < 340 and b["x"] + b["w"] > 220 and b["y"] < 230 and b["y"] + b["h"] > 150 for b in boxes)


def test_png_screenshot_gets_no_false_alarm(tmp_path):
    r = ForensicEngine(tmp_path).analyze("sample_data/original.png")
    assert not any(f["severity"] == "attention" for f in r["findings"])
    assert "image_ela_limited_png" in types(r)
