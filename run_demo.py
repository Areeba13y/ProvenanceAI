"""Usage:
    python run_demo.py sample_data/edited.png                    # analyse one image
    python run_demo.py sample_data/original.png sample_data/edited.png   # compare two
"""
import json
import sys

from forensic_engine import analyze_evidence, compare_evidence

args = sys.argv[1:] or ["sample_data/original.png"]
result = compare_evidence(args[0], args[1]) if len(args) == 2 else analyze_evidence(args[0])
print(json.dumps(result, indent=2, ensure_ascii=False))
