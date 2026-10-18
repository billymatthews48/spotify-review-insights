"""Build a local, offline labeling page for the golden 50 (human labels only; no model calls).

Usage: python evals/build_label_tool.py data/dataset/golden_50_to_label.csv
Writes evals/golden/label_golden_50.html. Open it in a browser, label, then "Download CSV"
and save the file as evals/golden/golden_50_labeled.csv.
Star ratings are hidden while labeling so labels come from the text, as the contract requires.
"""

import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main(src):
    with open(src, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    data = json.dumps(rows, ensure_ascii=False).replace("</", "<\\/")
    html = (HERE / "label_tool_template.html").read_text(encoding="utf-8").replace("__DATA__", data)
    out = HERE / "golden" / "label_golden_50.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"Wrote {out} ({len(rows)} reviews)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data/dataset/golden_50_to_label.csv")
