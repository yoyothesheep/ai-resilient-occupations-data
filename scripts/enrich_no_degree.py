#!/usr/bin/env python3
"""
Enrich top no-degree careers CSV with 10-year earnings model and career narrative.

Reads ENRICHMENT_INSTRUCTIONS.md as the system prompt, then sends each occupation
row to Claude and parses the returned JSON into enrichment columns.

Usage:
    python3 scripts/enrich_no_degree.py                  # all rows
    python3 scripts/enrich_no_degree.py --limit 10       # first N rows
    python3 scripts/enrich_no_degree.py --start 10       # resume from row index

Requirements:
    pip install anthropic
    export ANTHROPIC_API_KEY="sk-ant-..."

Output:
    data/top_no_degree_careers/ai_resilience_scores-associates-5.5-enriched.csv
"""

import anthropic
import csv
import json
import os
import re
import sys
import time
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE = Path(__file__).parent.parent / "data" / "top_no_degree_careers"
SOURCE_CSV   = BASE / "ai_resilience_scores-associates-5.5.csv"
OUTPUT_CSV   = BASE / "ai_resilience_scores-associates-5.5-enriched.csv"
INSTRUCTIONS = BASE / "ENRICHMENT_INSTRUCTIONS.md"

MODEL      = "claude-opus-4-6"
MAX_TOKENS = 4096
SLEEP_SEC  = 1

# New enrichment columns (in order)
ENRICHMENT_COLS = [
    "Median Annual Wage ($)",
    "Calculation Type",
    "Training Years",
    "Training Salary ($)",
    "Training Cost ($)",
    "Yr1 ($)", "Yr2 ($)", "Yr3 ($)", "Yr4 ($)", "Yr5 ($)",
    "Yr6 ($)", "Yr7 ($)", "Yr8 ($)", "Yr9 ($)", "Yr10 ($)",
    "10-Year Net Earnings ($)",
    "10-Year Net Earnings Calculation",
    "10-Year Net Earnings Calculation Model",
    "Difficulty Score",
    "Difficulty Score Explanation",
    "How to Get There",
    "Job Market",
    "Pension",
]

OUTPUT_FIELDNAMES = [
    "Job Zone", "Code", "Occupation", "url", "Median Wage", "Projected Growth",
    "Employment Change, 2024-2034", "Projected Job Openings", "Top Education Level",
    "Sample Job Titles", "Job Description", "role_resilience_score", "final_ranking", "key_drivers",
    "altpath url", "altpath simple title",
] + ENRICHMENT_COLS


def load_instructions() -> str:
    return INSTRUCTIONS.read_text(encoding="utf-8")


def parse_median_wage(wage_str: str) -> int:
    """Extract annual integer from e.g. '$49.50 hourly, $102,950 annual'"""
    m = re.search(r'\$([\d,]+)\s+annual', wage_str)
    if m:
        return int(m.group(1).replace(",", ""))
    return 0


def build_prompt(row: dict) -> str:
    median = parse_median_wage(row.get("Median Wage", ""))
    return f"""Enrich this occupation row for the top no-degree careers dataset.

Occupation: {row['Occupation']}
O*NET Code: {row['Code']}
Top Education Level: {row['Top Education Level']}
Median Wage: {row['Median Wage']} (parsed annual: ${median:,})
Projected Growth: {row['Projected Growth']}
Job Zone: {row['Job Zone']}
Sample Job Titles: {row['Sample Job Titles']}
Job Description: {row['Job Description']}

Follow the ENRICHMENT_INSTRUCTIONS exactly. Return ONLY a JSON object with these exact keys:
{{
  "Median Annual Wage ($)": <integer, parsed annual wage>,
  "Calculation Type": "ladder" or "linear",
  "Training Years": <float, e.g. 0, 0.5, 1, 2>,
  "Training Salary ($)": <integer, annualized wage paid during training; 0 if unpaid>,
  "Training Cost ($)": <integer, out-of-pocket cost>,
  "Yr1 ($)": <integer>,
  "Yr2 ($)": <integer>,
  "Yr3 ($)": <integer>,
  "Yr4 ($)": <integer>,
  "Yr5 ($)": <integer>,
  "Yr6 ($)": <integer>,
  "Yr7 ($)": <integer>,
  "Yr8 ($)": <integer>,
  "Yr9 ($)": <integer>,
  "Yr10 ($)": <integer>,
  "10-Year Net Earnings ($)": <integer, must equal sum(Yr1..Yr10) - Training Cost>,
  "10-Year Net Earnings Calculation": "<concise formula string>",
  "10-Year Net Earnings Calculation Model": "<2-part narrative: training description + earnings trajectory>",
  "Difficulty Score": "High", "Medium", or "Low",
  "Difficulty Score Explanation": "<2-3 sentences>",
  "How to Get There": "<step-by-step pathway with costs>",
  "Job Market": "<BLS growth, openings, supply/demand>",
  "Pension": "<retirement benefit description>"
}}

CRITICAL REMINDER: Year 1 must be the entry-level step, not the salary of this occupation. For manager/supervisor/senior roles, start at the junior role that feeds into it (see Canonical Paths and entry-level rules in the instructions).

Return only the JSON object, no other text."""


def call_claude(client: anthropic.Anthropic, system: str, prompt: str) -> dict:
    resp = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.content[0].text.strip()

    # Extract JSON from response
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if not m:
        raise ValueError(f"No JSON found in response:\n{text[:500]}")
    return json.loads(m.group(0))


def validate_row(data: dict, occupation: str) -> list[str]:
    """Return list of warning strings for the enriched row."""
    warnings = []

    yr_sum = sum(int(data.get(f"Yr{i} ($)", 0)) for i in range(1, 11))
    training_cost = int(data.get("Training Cost ($)", 0))
    stated_net = int(data.get("10-Year Net Earnings ($)", 0))
    if yr_sum - training_cost != stated_net:
        warnings.append(
            f"NET MISMATCH: sum(Yr1..Yr10)={yr_sum} - cost={training_cost} = {yr_sum-training_cost}, stated={stated_net}"
        )

    yr1 = int(data.get("Yr1 ($)", 0))
    median = int(data.get("Median Annual Wage ($)", 0))
    if median > 0 and yr1 > median * 0.75:
        warnings.append(
            f"Yr1 (${yr1:,}) is >75% of BLS median (${median:,}) — may be starting too high"
        )

    return warnings


def main():
    # Parse args
    limit = None
    start = 0
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--limit" and i + 1 < len(args):
            limit = int(args[i + 1])
        if arg == "--start" and i + 1 < len(args):
            start = int(args[i + 1])

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    system_prompt = load_instructions()

    with open(SOURCE_CSV, newline="", encoding="utf-8") as f:
        source_rows = list(csv.DictReader(f))

    # Load existing output to support resume
    existing = {}
    if OUTPUT_CSV.exists():
        with open(OUTPUT_CSV, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                existing[row["Code"]] = row

    rows_to_process = source_rows[start:]
    if limit is not None:
        rows_to_process = rows_to_process[:limit]

    print(f"Enriching {len(rows_to_process)} rows (start={start}, limit={limit})")
    print(f"Model: {MODEL}\n")

    results = list(existing.values()) if start == 0 else []
    # Pre-populate with existing if resuming
    if start > 0:
        for row in source_rows[:start]:
            if row["Code"] in existing:
                results.append(existing[row["Code"]])

    for i, row in enumerate(rows_to_process):
        code = row["Code"]
        occupation = row["Occupation"]
        idx = start + i + 1

        # Skip if already enriched and resuming
        if code in existing and start > 0:
            print(f"[{idx:3}] SKIP (already done): {code} {occupation}")
            continue

        print(f"[{idx:3}] {code}  {occupation}")

        try:
            prompt = build_prompt(row)
            data = call_claude(client, system_prompt, prompt)

            warnings = validate_row(data, occupation)
            for w in warnings:
                print(f"       ⚠ {w}")

            # Merge enrichment into source row
            enriched = dict(row)
            for col in ENRICHMENT_COLS:
                enriched[col] = str(data.get(col, ""))

            results.append(enriched)

            # Write after each row (safe resume)
            with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDNAMES, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(results)

        except Exception as e:
            print(f"       ERROR: {e}")
            # Write empty enrichment placeholder so we can see what failed
            enriched = dict(row)
            for col in ENRICHMENT_COLS:
                enriched[col] = "ERROR"
            results.append(enriched)

        if i < len(rows_to_process) - 1:
            time.sleep(SLEEP_SEC)

    print(f"\nDone. {len(results)} rows written to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
