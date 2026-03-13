#!/usr/bin/env python3
"""
One-time script: joins altpath url + altpath simple title onto existing CSVs.

Updates in-place:
  data/intermediate/All_Occupations_ONET_enriched.csv
  data/output/ai_resilience_scores.csv
  data/top_no_degree_careers/ai_resilience_scores-associates-5.5.csv
  data/top_no_degree_careers/ai_resilience_scores-associates-5.5-enriched.csv
"""

import csv
from pathlib import Path

ROOT = Path(__file__).parent.parent
ALTPATH_CSV = ROOT / "data" / "input" / "SimpleJobTitles_altPathurl_202602201636.csv"

TARGETS = [
    ROOT / "data" / "intermediate" / "All_Occupations_ONET_enriched.csv",
    ROOT / "data" / "output" / "ai_resilience_scores.csv",
    ROOT / "data" / "top_no_degree_careers" / "ai_resilience_scores-associates-5.5.csv",
    ROOT / "data" / "top_no_degree_careers" / "ai_resilience_scores-associates-5.5-enriched.csv",
]

NEW_FIELDS = ["altpath url", "altpath simple title"]


def load_altpath() -> dict:
    lookup = {}
    with open(ALTPATH_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            code = row.get("Soc Code", "").strip()
            if code:
                lookup[code] = {
                    "altpath url": row.get("URL", "").strip(),
                    "altpath simple title": row.get("Simple Title", "").strip(),
                }
    print(f"Loaded {len(lookup)} altpath entries")
    return lookup


def join_csv(path: Path, altpath: dict) -> None:
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
        f.seek(0)
        existing_fields = csv.DictReader(f).fieldnames or []

    if "altpath url" in existing_fields:
        print(f"  Skipping {path.name} — already has altpath fields")
        return

    fieldnames = existing_fields + NEW_FIELDS
    matched = 0
    for row in rows:
        code = row.get("Code", "").strip()
        data = altpath.get(code, {})
        row["altpath url"] = data.get("altpath url", "")
        row["altpath simple title"] = data.get("altpath simple title", "")
        if data:
            matched += 1

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"  Updated {path.name}: {matched}/{len(rows)} rows matched")


if __name__ == "__main__":
    altpath = load_altpath()
    for target in TARGETS:
        if not target.exists():
            print(f"  Not found, skipping: {target.name}")
            continue
        join_csv(target, altpath)
    print("Done.")
