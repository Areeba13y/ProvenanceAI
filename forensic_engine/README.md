# ProvenanceAI — Forensic Engine

Local, open-source digital evidence checks for images and WhatsApp screenshots.
Findings are indicators for a human investigator, never proof. A matching hash only
shows a file is unchanged since intake; it does not prove the original was authentic.

## Setup
```
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt pytest
```
Install ExifTool and make sure `exiftool -ver` works (otherwise a Pillow fallback is used).

## Try it
```
python make_samples.py                                   # synthetic sample images
python run_demo.py sample_data/edited.png                # analyse one image
python run_demo.py sample_data/photo_tampered.jpg        # OpenCV checks on a JPEG
python run_demo.py sample_data/original.png sample_data/edited.png   # compare two images
python -m pytest -q tests
```

## What is inside `forensic_engine/`
| File | Job |
|---|---|
| validation.py | checks the upload is a real image |
| hashing.py | SHA-256 fingerprint |
| custody.py | hash-chained chain-of-custody log (SQLite) |
| metadata.py | ExifTool metadata + careful findings |
| analysis.py | OpenCV: ELA and noise-consistency checks |
| compare.py | two-image comparison with highlighted changes |
| engine.py | ties it together, returns JSON-ready dicts |

## Use from the Streamlit app
```python
from forensic_engine import analyze_evidence, compare_evidence

result = analyze_evidence("screenshot.png")            # one image
diff   = compare_evidence("original.png", "edited.png")  # two versions
```
Both return plain dicts (`evidence_id`, `sha256`, `findings`, `artifacts`, `limitations`, ...).
Every finding has `severity` (info / notice / attention), `why_it_matters` and `unproven`.
Image outputs (overlay, comparison picture) are written to `workspace/results/`.

## Notes
- Use only synthetic or self-made samples; never commit real case evidence.
- ELA is not applied to PNG screenshots (it gives false alarms on lossless text images).
