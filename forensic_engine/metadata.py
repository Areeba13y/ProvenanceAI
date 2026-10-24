"""Step 4: metadata extraction with ExifTool (falls back to Pillow)."""
import json
import shutil
import subprocess
from PIL import Image
from PIL.ExifTags import TAGS

EDITING_SOFTWARE = ["photoshop", "gimp", "snapseed", "lightroom", "canva", "picsart",
                    "pixlr", "paint.net", "affinity", "facetune", "illustrator"]


def extract_metadata(path):
    """Return {'source': ..., 'fields': {...}}"""
    if shutil.which("exiftool"):
        try:
            out = subprocess.run(["exiftool", "-json", "-G1", "-a", str(path)],
                                 capture_output=True, text=True, timeout=30, check=True).stdout
            fields = json.loads(out)[0]
            for k in ("SourceFile", "ExifTool:ExifToolVersion", "System:FileName", "System:Directory"):
                fields.pop(k, None)
            return {"source": "exiftool", "fields": fields}
        except Exception:
            pass  # fall through to Pillow
    fields = {}
    # Pillow calls DateTime what ExifTool calls ModifyDate
    alias = {"DateTime": "ModifyDate"}
    try:
        with Image.open(path) as im:
            exif = im.getexif()
            for tag, val in exif.items():
                if tag == 0x8769:  # pointer to the Exif sub-section, read below
                    continue
                name = TAGS.get(tag, tag)
                fields[f"IFD0:{alias.get(name, name)}"] = str(val)
            # DateTimeOriginal and similar fields live in the Exif sub-section
            for tag, val in exif.get_ifd(0x8769).items():
                name = TAGS.get(tag, tag)
                fields[f"ExifIFD:{alias.get(name, name)}"] = str(val)
            for k, v in im.info.items():
                if isinstance(v, (str, int, float)):
                    fields[f"Info:{k}"] = str(v)
    except Exception:
        pass
    return {"source": "pillow-fallback", "fields": fields}


def _find(fields, *names):
    for k, v in fields.items():
        if k.split(":")[-1] in names:
            return str(v)
    return None


def metadata_findings(meta):
    """Turn raw metadata into careful, non-conclusive findings."""
    f = meta["fields"]
    out = []

    software = _find(f, "Software", "CreatorTool", "HistorySoftwareAgent")
    if software:
        hit = next((s for s in EDITING_SOFTWARE if s in software.lower()), None)
        out.append({
            "type": "metadata_software_tag",
            "severity": "notice" if hit else "info",
            "title": "Software tag found in metadata",
            "detail": f"Software field: '{software}'" + (" (a known image editor)." if hit else "."),
            "why_it_matters": "Shows which program last wrote this file. Editors leave tags, but normal tools (phone, export, share) can too.",
            "unproven": "Does not show whether the visible content was changed.",
        })

    original = _find(f, "DateTimeOriginal", "CreateDate")
    modified = _find(f, "ModifyDate")
    if original and modified and original != modified:
        out.append({
            "type": "metadata_date_mismatch",
            "severity": "notice",
            "title": "Capture date and modify date differ",
            "detail": f"Original/create: {original}; modified: {modified}.",
            "why_it_matters": "File was saved again after it was first created.",
            "unproven": "Re-saving also happens during harmless actions like rotating or compressing.",
        })

    if not any(k.startswith(("EXIF", "XMP", "IFD0", "ExifIFD")) for k in f):
        out.append({
            "type": "metadata_absent",
            "severity": "info",
            "title": "No camera/EXIF metadata present",
            "detail": "The file has no EXIF or XMP metadata.",
            "why_it_matters": "Limits what metadata analysis can say about origin.",
            "unproven": "WhatsApp and most social apps strip metadata automatically, so this alone is NOT suspicious.",
        })
    return out
