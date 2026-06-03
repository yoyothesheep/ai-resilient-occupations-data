#!/usr/bin/env python3
"""Selective key_drivers migration.

Regenerate ONLY 'tension' careers (label <-> score disagreement); restore v1
key_drivers for everything else (replacing the category-era text).

tension = (Grow with AI AND score<=50) OR (High Automation Risk AND score>=38)

This script does the KEEP_V1 half: copies v1 key_drivers into the current CSV
for every non-tension career, leaves tension careers untouched (they are then
regenerated separately via score_occupations.py --patch-key-drivers).

Prints the comma-separated tension code list for the regen step.
"""
import csv

CUR = "data/output/ai_resilience_scores.csv"
V1  = "data/backup/v1/ai_resilience_scores.csv"


def score(row):
    try:
        return round(float(row["final_ranking"]) * 100)
    except (ValueError, KeyError):
        return 0


def is_tension(row):
    cat, sv = row["ai_category"], score(row)
    return (cat == "Grow with AI" and sv <= 50) or (cat == "High Automation Risk" and sv >= 38)


def main():
    v1 = {r["Code"]: r.get("key_drivers", "") for r in csv.DictReader(open(V1))}
    rows = list(csv.DictReader(open(CUR)))
    fieldnames = list(rows[0].keys())

    restored, regen_codes, missing_v1 = 0, [], []
    for r in rows:
        if is_tension(r):
            regen_codes.append(r["Code"])
            continue
        kd = v1.get(r["Code"])
        if kd:
            r["key_drivers"] = kd
            restored += 1
        else:
            missing_v1.append(r["Code"])

    with open(CUR, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    print(f"keep_v1 restored: {restored}")
    print(f"tension (regen): {len(regen_codes)}")
    if missing_v1:
        print(f"WARNING no v1 text (left as-is): {len(missing_v1)}: {missing_v1}")
    print("\nREGEN_CODES=" + ",".join(regen_codes))


if __name__ == "__main__":
    main()
