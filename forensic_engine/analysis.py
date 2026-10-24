"""Step 4: OpenCV image-forensics checks.

These functions return INDICATORS for a human investigator, never verdicts.
Two checks:
  * ELA  (Error Level Analysis): re-compress the image and look for regions that
    react differently from their surroundings (most meaningful on JPEG files).
  * Noise residual: look for regions whose fine-grain noise differs from the rest.
"""
from pathlib import Path

import cv2
import numpy as np

BLOCK = 32          # analysis block size in pixels
Z_THRESHOLD = 6.0   # how far a block must stand out (robust z-score)
ELA_MIN_DIFF = 2.0  # ...and by at least this much in absolute ELA units
NOISE_MIN_DIFF = 0.6
MAX_LOCAL_FRACTION = 0.20   # if more than 20% of blocks flag, it is not "local"
MIN_NOISE_LEVEL = 0.25      # below this the image is too clean (typical screenshot)


def _read_bgr(path):
    # np.fromfile + imdecode also works for Windows paths with unicode characters
    data = np.fromfile(str(path), dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("could not decode image")
    return img


def _block_means(m, block=BLOCK):
    h, w = m.shape
    hb, wb = h // block, w // block
    if hb < 3 or wb < 3:
        return None
    m = m[:hb * block, :wb * block]
    return m.reshape(hb, block, wb, block).mean(axis=(1, 3))


def _robust_z(b):
    med = float(np.median(b))
    mad = float(np.median(np.abs(b - med)))
    return (b - med) / (1.4826 * mad + 1e-6), med


def _regions(flag_grid, block=BLOCK, limit=5):
    """Merge neighbouring flagged blocks into pixel rectangles."""
    n, _, stats, _ = cv2.connectedComponentsWithStats(flag_grid.astype(np.uint8), connectivity=8)
    out = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        out.append({"x": int(x * block), "y": int(y * block),
                    "w": int(w * block), "h": int(h * block), "blocks": int(area)})
    out.sort(key=lambda r: r["blocks"], reverse=True)
    return out[:limit]


def ela_map(img, quality=90):
    ok, enc = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    again = cv2.imdecode(enc, cv2.IMREAD_COLOR)
    return cv2.absdiff(img, again).astype(np.float32).mean(axis=2)


def noise_map(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    resid = gray.astype(np.float32) - cv2.medianBlur(gray, 3).astype(np.float32)
    return np.abs(resid)


def _detect(m, min_diff, two_sided):
    """Return (regions, metrics) for blocks that stand out from the rest."""
    b = _block_means(m)
    if b is None:
        return None, {"note": "image too small for block analysis"}
    z, med = _robust_z(b)
    dev = b - med
    flag = (z > Z_THRESHOLD) & (dev > min_diff)
    if two_sided:
        flag |= (z < -Z_THRESHOLD) & (dev < -min_diff)
    frac = float(flag.mean())
    metrics = {"median_level": round(med, 3), "flagged_fraction": round(frac, 4)}
    if frac == 0:
        return [], metrics
    if frac > MAX_LOCAL_FRACTION:
        metrics["note"] = "too widespread to be a localized anomaly"
        return None, metrics
    return _regions(flag), metrics


def _finding(ftype, severity, title, detail, why, unproven, regions=None):
    f = {"type": ftype, "severity": severity, "title": title, "detail": detail,
         "why_it_matters": why, "unproven": unproven}
    if regions:
        f["regions"] = regions
    return f


def _overlay(img, ela, regions_all, out_path):
    norm = np.clip(ela / max(float(np.percentile(ela, 99.5)), 1e-6), 0, 1)
    heat = cv2.applyColorMap((norm * 255).astype(np.uint8), cv2.COLORMAP_JET)
    out = cv2.addWeighted(img, 0.5, heat, 0.5, 0)
    for r in regions_all:
        cv2.rectangle(out, (r["x"], r["y"]), (r["x"] + r["w"], r["y"] + r["h"]), (255, 255, 255), 2)
    ok, enc = cv2.imencode(".png", out)
    Path(out_path).write_bytes(enc.tobytes())


def analyze_image(path, out_dir, evidence_id, image_format=None):
    """Run ELA + noise checks. Returns {'findings', 'artifacts', 'metrics'}."""
    img = _read_bgr(path)
    findings, metrics, flagged = [], {}, []
    fmt = (image_format or "").upper()

    # ---- ELA -----------------------------------------------------------
    ela = ela_map(img)
    checks_run = 0
    if fmt == "PNG":
        regions, m = [], {"note": "skipped: ELA is not meaningful on lossless PNG (text edges give false alarms)"}
    else:
        regions, m = _detect(ela, ELA_MIN_DIFF, two_sided=False)
        checks_run += 1
    metrics["ela"] = m
    if regions:
        flagged += regions
        findings.append(_finding(
            "image_ela_localized", "attention",
            "Region reacts differently to re-compression (ELA)",
            f"{len(regions)} region(s) stand out from the rest of the image.",
            "Parts of an image that were pasted in or edited separately can show a different compression history.",
            "Not proof of editing: sharp text, logos, borders and re-saved images can also stand out.",
            regions))
    elif regions is None:
        findings.append(_finding(
            "image_ela_widespread", "info", "ELA difference is spread across the whole image",
            "No single region stands out; the whole image shows a similar pattern.",
            "Usually means the whole image was compressed or re-saved the same way.",
            "Says nothing about whether a small part was edited."))

    if fmt == "PNG":
        findings.append(_finding(
            "image_ela_limited_png", "info", "ELA not applied to PNG screenshots",
            "PNG is lossless, so compression differences are weak or absent and text edges cause false alarms.",
            "ELA works best on JPEG photos; most screenshots are PNG.",
            "No ELA result is given for this file. Rely on metadata, OCR comparison and timeline checks instead."))

    # ---- Noise residual --------------------------------------------------
    noise = noise_map(img)
    nb = _block_means(noise)
    if nb is not None and float(np.median(nb)) < MIN_NOISE_LEVEL:
        metrics["noise"] = {"median_level": round(float(np.median(nb)), 3),
                            "note": "image has almost no fine noise (typical of screenshots)"}
        findings.append(_finding(
            "image_noise_not_applicable", "info", "Noise analysis not meaningful for this image",
            "The image has almost no fine-grain noise.",
            "Screenshots and graphics are clean, so noise patterns cannot be compared.",
            "No conclusion about editing can be drawn from noise here."))
    else:
        regions, m = _detect(noise, NOISE_MIN_DIFF, two_sided=True)
        checks_run += 1
        metrics["noise"] = m
        if regions:
            flagged += regions
            findings.append(_finding(
                "image_noise_inconsistent", "attention", "Fine-grain noise differs in some regions",
                f"{len(regions)} region(s) have noticeably different noise than the rest.",
                "Content added or retouched later can carry different noise than the original photo.",
                "Not proof: smooth objects, sky, blur and focus changes also vary in noise.",
                regions))

    if checks_run and not flagged and not any(f["severity"] == "attention" for f in findings):
        findings.append(_finding(
            "image_no_local_anomaly", "info", "No localized anomaly found by ELA/noise checks",
            "No region stood out in the checks that could be applied.",
            "These checks found nothing unusual.",
            "Does not prove the image is untouched: these checks miss many edits, especially text changes."))

    artifacts = {}
    if flagged:
        overlay_path = Path(out_dir) / f"{evidence_id}_analysis.png"
        _overlay(img, ela, flagged, overlay_path)
        artifacts["analysis_overlay"] = str(overlay_path)
    return {"findings": findings, "artifacts": artifacts, "metrics": metrics}
