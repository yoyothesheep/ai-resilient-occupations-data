#!/usr/bin/env python3
"""
Generate A12 Demand Elasticity scores for occupations using the LLM method.

This script feeds O*NET task data to Claude and asks it to estimate the quantity
response if the service gets 10-20% cheaper (looking for latent demand, greater
frequency, more customization, or new customers).

Outputs: data/intermediate/a12_elasticity_scores.csv
"""

import anthropic
import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path

from loaders import load_scores, load_task_table

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 8192
TOP_TASKS = 10
BATCH_SIZE = 10
SLEEP_SEC = 2

OUTPUT_FILE = Path("data/intermediate/a12_elasticity_scores.csv")


def build_prompt(batch: list[tuple[dict, list[str]]]) -> str:
    occ_list = ""
    for i, (occ, tasks) in enumerate(batch):
        title = occ.get('altpath simple title') or occ.get('Occupation')
        desc = occ.get('Description', '')
        task_str = chr(10).join(f'    - {t}' for t in tasks)
        occ_list += f"{i+1}. {title} (O*NET: {occ['Code']})\n   Description: {desc}\n   Top Tasks:\n{task_str}\n\n"
        
    return f"""You are an expert labor economist analyzing the price elasticity of demand for occupations in the face of AI automation.

We need to estimate the "Demand Elasticity" (A12) for the following {len(batch)} occupations:

{occ_list}
Imagine that AI automation reduces the cost of producing the relevant output of these jobs by 10-20% over a 2-3 year horizon. Will this lower price unlock massive new demand (highly elastic), or is the demand relatively fixed regardless of price (highly inelastic)?

Look for:
- Latent demand (people who want the service but currently can't afford it).
- Greater frequency of use.
- More customization or new customer segments.

Scale:
1 = Highly Inelastic: Demand is largely fixed. (e.g., Firefighters, Payroll Clerks).
2 = Somewhat Inelastic: Small demand expansion, but not enough to offset productivity gains.
3 = Unit Elastic: Demand grows proportionally to the price drop.
4 = Somewhat Elastic: Lower prices unlock significant new demand.
5 = Highly Elastic: Lower prices spark explosive demand growth, requiring MORE workers despite AI efficiency. (e.g., Software Developers, Graphic Designers).

Generate a JSON array of objects. Each object must have these fields:
[
  {{
    "onet_code": "XX-XXXX.XX",
    "score": <integer 1-5>,
    "justification": "One clear sentence explaining why."
  }}
]

Respond ONLY with the valid JSON array. Do not include any markdown formatting or extra text."""


def _parse_response(text: str) -> list[dict]:
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    return json.loads(text.strip())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="Process only N occupations (for testing)")
    parser.add_argument("--force", action="store_true", help="Regenerate all scores, ignoring existing")
    args = parser.parse_args()

    print("Loading data...")
    scores = load_scores()
    task_table = load_task_table()

    # Load existing scores to support resumable processing
    existing_codes = set()
    if OUTPUT_FILE.exists() and not args.force:
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                existing_codes.add(row["onet_code"])

    client = anthropic.Anthropic()
    
    # Prepare remaining occupations
    remaining = []
    for code, occ in scores.items():
        if code in existing_codes and not args.force:
            continue
            
        # Get top tasks
        rows = task_table.get(code, [])
        sorted_rows = sorted(rows, key=lambda r: float(r["task_weight"] or 0), reverse=True)
        tasks = [r["task_text"] for r in sorted_rows[:TOP_TASKS]]
        
        remaining.append((occ, tasks))

    print(f"Processing {len(remaining)} occupations (skipping {len(existing_codes)} already done)...")
    
    if not remaining:
        print("Nothing to do!")
        return

    batches = [remaining[i:i+BATCH_SIZE] for i in range(0, len(remaining), BATCH_SIZE)]
    total_batches = len(batches)
    print(f"📦 {total_batches} batches × {BATCH_SIZE} occupations")

    write_header = not OUTPUT_FILE.exists() or args.force
    if args.force:
        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["onet_code", "a12_score", "a12_justification"])
            writer.writeheader()
        write_header = False

    processed_count = 0
    
    for batch_idx, batch in enumerate(batches):
        print(f"\n── Batch {batch_idx+1}/{total_batches} ({len(batch)} occupations)")
        names = [o['Occupation'] for o, t in batch]
        print(f"   {', '.join(names[:3])}{'...' if len(names) > 3 else ''}")
        
        prompt = build_prompt(batch)
        
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                messages=[{"role": "user", "content": prompt}],
            )
            data_list = _parse_response(response.content[0].text)
            
            results = []
            for item in data_list:
                results.append({
                    "onet_code": item["onet_code"],
                    "a12_score": item["score"],
                    "a12_justification": item["justification"]
                })
            
            processed_count += len(results)
            
            # Save batch immediately (append)
            OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(OUTPUT_FILE, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=["onet_code", "a12_score", "a12_justification"])
                if write_header:
                    writer.writeheader()
                    write_header = False
                writer.writerows(results)
                
            print(f"   ✓ Saved {len(results)} scores.")
            
        except json.JSONDecodeError as e:
            print(f"   ✗ JSON parse error: {e}")
            continue
        except Exception as e:
            print(f"   ✗ Error processing batch: {e}")
            continue
            
        if args.limit > 0 and processed_count >= args.limit:
            print(f"\nReached limit of {args.limit}.")
            break
            
        import time
        if batch_idx < total_batches - 1:
            time.sleep(SLEEP_SEC)

    print(f"\n✓ Complete! Incremental results appended to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
