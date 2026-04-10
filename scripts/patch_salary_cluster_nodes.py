#!/usr/bin/env python3
"""
Patch script: backfill salary into careerCluster nodes in occupation_cards.jsonl.
Reads salary from ai_resilience_scores.csv — no API calls needed.
"""
import csv
import json
from pathlib import Path

SCORES_CSV = Path("data/output/ai_resilience_scores.csv")
CARDS_JSONL = Path("data/output/occupation_cards.jsonl")


def format_salary(raw: str) -> str:
    # Format: "$66.38 hourly, $138,060 annual" — extract annual
    import re
    m = re.search(r'\$([\d,]+)\s+annual', raw)
    if m:
        return f"${int(m.group(1).replace(',', '')):,}"
    # Fallback: plain number
    plain = raw.replace(",", "").replace("$", "").strip()
    try:
        return f"${int(float(plain)):,}"
    except (ValueError, TypeError):
        return ""


def main():
    # Build code → salary lookup
    salary_by_code: dict[str, str] = {}
    with open(SCORES_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            code = row.get("Code", "").strip()
            salary = format_salary(row.get("Median Wage", ""))
            if code and salary:
                salary_by_code[code] = salary

    print(f"Loaded salary for {len(salary_by_code)} occupations")

    cards: dict[str, dict] = {}
    with open(CARDS_JSONL, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            card = json.loads(line)
            code = card.get("onet_code", "")
            cards[code] = card

    patched = 0
    for card in cards.values():
        cluster = card.get("careerCluster")
        if not cluster:
            continue
        for node in cluster:
            node_code = node.get("code", "")
            if node_code and node_code in salary_by_code:
                node["salary"] = salary_by_code[node_code]
                patched += 1

    with open(CARDS_JSONL, "w", encoding="utf-8") as f:
        for card in cards.values():
            f.write(json.dumps(card, ensure_ascii=False) + "\n")

    print(f"Patched {patched} cluster nodes with salary")
    print(f"Wrote {len(cards)} cards to {CARDS_JSONL}")


if __name__ == "__main__":
    main()
