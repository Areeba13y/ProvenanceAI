"""Ties everything together and returns one JSON-ready dict per evidence file.

Areeba's Streamlit app only needs:
    from forensic_engine import analyze_evidence
    result = analyze_evidence("path/to/screenshot.png")
"""
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .analysis import analyze_image
from .compare import compare_images
from .custody import CustodyLog
from .hashing import sha256_file
from .metadata import extract_metadata, metadata_findings
from .validation import validate_image

LIMITATIONS = [
    "A matching hash only shows the file is unchanged since intake; it does not prove the original was authentic.",
    "Findings are indicators for a human investigator, not proof that evidence is genuine or fake.",
    "Missing or odd metadata is common in screenshots and messaging apps and is not suspicious by itself.",
]


class ForensicEngine:
    def __init__(self, workdir="workspace"):
        self.workdir = Path(workdir)
        self.store = self.workdir / "evidence_store"
        self.results = self.workdir / "results"
        self.store.mkdir(parents=True, exist_ok=True)
        self.results.mkdir(parents=True, exist_ok=True)
        self.custody = CustodyLog(self.workdir / "custody.db")

    def ingest(self, path):
        """Validate, hash, copy into the evidence store and log it."""
        ok, reason, info = validate_image(path)
        if not ok:
            return {"ok": False, "error": reason}
        path = Path(path)
        digest = sha256_file(path)
        existing = self.custody.find_by_hash(digest)
        if existing:
            self.custody.log(existing, "DUPLICATE_UPLOAD", {"name": path.name, "sha256": digest})
            return {"ok": True, "evidence_id": existing, "sha256": digest, "info": info,
                    "duplicate": True, "stored_path": self._stored(existing)}
        ev_id = self.custody.next_evidence_id()
        stored = self.store / f"{ev_id}{path.suffix.lower()}"
        shutil.copy2(path, stored)  # never touch the original upload
        stored.chmod(0o444)         # read-only
        self.custody.add_evidence(ev_id, path.name, digest, path.stat().st_size, stored)
        self.custody.log(ev_id, "INTAKE", {"name": path.name, "sha256": digest,
                                           "size_bytes": path.stat().st_size})
        return {"ok": True, "evidence_id": ev_id, "sha256": digest, "info": info,
                "duplicate": False, "stored_path": str(stored)}

    def _stored(self, ev_id):
        hits = list(self.store.glob(f"{ev_id}.*"))
        return str(hits[0]) if hits else None

    def verify_integrity(self, evidence_id):
        """Re-hash the stored copy and compare with the hash recorded at intake."""
        stored = self._stored(evidence_id)
        recorded = next((e["details"]["sha256"] for e in self.custody.entries(evidence_id)
                         if e["action"] == "INTAKE"), None)
        current = sha256_file(stored) if stored else None
        match = bool(current and current == recorded)
        self.custody.log(evidence_id, "INTEGRITY_CHECK", {"match": match})
        return {"recorded_sha256": recorded, "current_sha256": current, "match": match}

    def analyze(self, path):
        ing = self.ingest(path)
        if not ing["ok"]:
            return {"ok": False, "error": ing["error"], "findings": [], "limitations": LIMITATIONS}
        ev_id = ing["evidence_id"]
        integrity = self.verify_integrity(ev_id)

        meta = extract_metadata(ing["stored_path"])
        findings = metadata_findings(meta)
        self.custody.log(ev_id, "METADATA_ANALYSIS", {"source": meta["source"], "findings": len(findings)})

        try:
            img_result = analyze_image(ing["stored_path"], self.results, ev_id, ing["info"].get("format"))
        except Exception as exc:  # never let one check break the whole analysis
            img_result = {"findings": [{
                "type": "image_analysis_failed", "severity": "info",
                "title": "Image analysis could not run", "detail": f"{exc.__class__.__name__}: {exc}",
                "why_it_matters": "Visual checks are missing for this file.",
                "unproven": "No conclusion about the image content."}],
                "artifacts": {}, "metrics": {}}
        findings += img_result["findings"]
        self.custody.log(ev_id, "IMAGE_ANALYSIS", {"findings": len(img_result["findings"]),
                                                   "artifacts": sorted(img_result["artifacts"])})

        for i, f in enumerate(findings, 1):
            f["id"] = f"{ev_id}-F{i:02d}"
        chain_ok, broken = self.custody.verify_chain()
        result = {
            "ok": True,
            "evidence_id": ev_id,
            "original_name": Path(path).name,
            "sha256": ing["sha256"],
            "duplicate_upload": ing["duplicate"],
            "image": ing["info"],
            "integrity": integrity,
            "metadata": meta,
            "findings": findings,
            "artifacts": img_result["artifacts"],
            "analysis_metrics": img_result["metrics"],
            "custody_log": self.custody.entries(ev_id),
            "custody_chain_valid": chain_ok,
            "limitations": LIMITATIONS,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        (self.results / f"{ev_id}.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
        return result


def _compare(self, path_a, path_b):
    """Ingest two images and report where they differ."""
    ia, ib = self.ingest(path_a), self.ingest(path_b)
    for i in (ia, ib):
        if not i["ok"]:
            return {"ok": False, "error": i["error"], "findings": [], "limitations": LIMITATIONS}
    a_id, b_id = ia["evidence_id"], ib["evidence_id"]
    cmp_id = f"CMP-{a_id}-vs-{b_id}"
    artifacts, metrics = {}, {}
    if ia["sha256"] == ib["sha256"]:
        findings = [{"type": "compare_identical_files", "severity": "info",
                     "title": "The two files are byte-for-byte identical",
                     "detail": "Both files have the same SHA-256 hash.",
                     "why_it_matters": "There is no difference to report between them.",
                     "unproven": "Says nothing about whether the shared file is authentic."}]
    else:
        out_png = self.results / f"{cmp_id}.png"
        res = compare_images(ia["stored_path"], ib["stored_path"], out_png)
        findings, metrics = res["findings"], res["metrics"]
        artifacts["comparison_image"] = str(out_png)
    for i, f in enumerate(findings, 1):
        f["id"] = f"{cmp_id}-F{i:02d}"
    for me, other in ((a_id, b_id), (b_id, a_id)):
        self.custody.log(me, "COMPARISON", {"against": other, "findings": len(findings)})
    chain_ok, _ = self.custody.verify_chain()
    result = {
        "ok": True, "comparison_id": cmp_id,
        "evidence_a": {"evidence_id": a_id, "original_name": Path(path_a).name,
                       "sha256": ia["sha256"], "image": ia["info"]},
        "evidence_b": {"evidence_id": b_id, "original_name": Path(path_b).name,
                       "sha256": ib["sha256"], "image": ib["info"]},
        "same_file": ia["sha256"] == ib["sha256"],
        "findings": findings, "artifacts": artifacts, "metrics": metrics,
        "custody_chain_valid": chain_ok, "limitations": LIMITATIONS,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (self.results / f"{cmp_id}.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
    return result


ForensicEngine.compare = _compare


def compare_evidence(path_a, path_b, workdir="workspace"):
    """One-line helper for the UI: where do these two images differ?"""
    return ForensicEngine(workdir).compare(path_a, path_b)


def analyze_evidence(path, workdir="workspace"):
    """One-line helper for the UI."""
    return ForensicEngine(workdir).analyze(path)
