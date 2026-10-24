"""Step 5: compare two versions of an image and highlight what differs.

Output is a list of changed regions plus a side-by-side picture (A | B | changes).
It shows WHERE two files differ; it cannot say which one is the original.
"""
from pathlib import Path

import cv2
import numpy as np

from .analysis import _read_bgr

DIFF_THRESHOLD = 25   # pixel difference (0-255) that counts as "changed"
MIN_AREA = 80         # ignore specks smaller than this many pixels
MERGE_KERNEL = 15     # join nearby changed pixels (e.g. letters of one word)
PANEL_MAX_H = 800


def _label(img, text):
    """Put the label in its own black strip above the image so nothing is covered."""
    strip = np.zeros((34, img.shape[1], 3), np.uint8)
    cv2.putText(strip, text, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    return np.vstack([strip, img])


def _panel(a, b, mask, regions, out_path):
    marked = a.copy()
    marked[mask > 0] = (0.4 * marked[mask > 0] + 0.6 * np.array([0, 0, 255])).astype(np.uint8)
    for r in regions:
        cv2.rectangle(marked, (r["x"], r["y"]), (r["x"] + r["w"], r["y"] + r["h"]), (0, 0, 255), 2)
    s = min(1.0, PANEL_MAX_H / a.shape[0])
    parts = [_label(cv2.resize(i, None, fx=s, fy=s, interpolation=cv2.INTER_AREA), t)
             for i, t in ((a, "A"), (b, "B"), (marked, "CHANGES"))]
    ok, enc = cv2.imencode(".png", np.hstack(parts))
    Path(out_path).write_bytes(enc.tobytes())


def compare_images(path_a, path_b, out_path):
    """Return {'findings', 'metrics'} and write the A|B|changes picture to out_path."""
    a, b = _read_bgr(path_a), _read_bgr(path_b)
    dims_a, dims_b = (a.shape[1], a.shape[0]), (b.shape[1], b.shape[0])
    resized = a.shape[:2] != b.shape[:2]
    if resized:
        b = cv2.resize(b, (a.shape[1], a.shape[0]), interpolation=cv2.INTER_AREA)

    diff = cv2.GaussianBlur(cv2.absdiff(a, b).max(axis=2), (5, 5), 0)
    raw = diff > DIFF_THRESHOLD
    mask = cv2.morphologyEx(raw.astype(np.uint8) * 255, cv2.MORPH_CLOSE,
                            np.ones((MERGE_KERNEL, MERGE_KERNEL), np.uint8))
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    regions = [{"x": int(x), "y": int(y), "w": int(w), "h": int(h), "area_px": int(area)}
               for x, y, w, h, area in stats[1:] if area >= MIN_AREA]
    regions.sort(key=lambda r: r["area_px"], reverse=True)

    findings = []
    if resized:
        findings.append({
            "type": "compare_size_differs", "severity": "notice",
            "title": "The two images have different dimensions",
            "detail": f"A is {dims_a[0]}x{dims_a[1]}, B is {dims_b[0]}x{dims_b[1]}; B was resized to A for comparison.",
            "why_it_matters": "Cropping, resizing or re-exporting changes dimensions and can cause apparent differences.",
            "unproven": "Does not show whether visible content was altered."})
    if regions:
        findings.append({
            "type": "compare_regions_differ", "severity": "attention",
            "title": f"{len(regions)} region(s) differ between the two versions",
            "detail": "Marked in the CHANGES panel of the comparison picture.",
            "why_it_matters": "Shows exactly where content is different between version A and version B.",
            "unproven": "Does not show which version is the original, who changed it, or why. "
                        "Re-compression or resizing can also cause small differences.",
            "regions": regions[:10]})
    else:
        findings.append({
            "type": "compare_no_visible_difference", "severity": "info",
            "title": "No visible pixel difference above the threshold",
            "detail": "The two images look the same at the sensitivity used.",
            "why_it_matters": "Any difference between the files is not visible in the image content.",
            "unproven": "Very subtle changes below the threshold would not be shown."})

    _panel(a, b, mask, regions, out_path)
    metrics = {"dimensions_a": dims_a, "dimensions_b": dims_b, "resized_for_comparison": resized,
               "changed_pixel_fraction": round(float(raw.mean()), 5), "region_count": len(regions),
               "threshold": DIFF_THRESHOLD}
    return {"findings": findings, "metrics": metrics}
