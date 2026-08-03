#!/usr/bin/env python3
"""
Phase 2b: Map AEI tasks to O*NET occupation codes via exact Task ID join.

Release 2026-06-26 publishes `node_external_id` = the O*NET numeric Task ID
at the task hierarchy level, so this is now an exact join — no fuzzy text
matching. A Task ID identifies an (occupation, task) pair, not a task text,
so this is a strict join: if two occupations share identical task text under
different Task IDs, only the occupation AEI published under is matched. This
is a deliberate choice (see docs/pipeline.md) — no propagation to sibling
Task IDs with matching text.

Input:
- data/intermediate/economic_index_tasks_raw.csv
- data/input/onet_db/Task Statements.xlsx

Output:
- data/intermediate/economic_index_tasks_mapped.csv
"""

import pandas as pd
from pathlib import Path
import sys

TASKS_FILE = Path("data/intermediate/economic_index_tasks_raw.csv")
ONET_TASKS_FILE = Path("data/input/onet_db/Task Statements.xlsx")
OUTPUT_FILE = Path("data/intermediate/economic_index_tasks_mapped.csv")


def main():
    print("=" * 100)
    print("PHASE 2b: MAP AEI TASKS TO O*NET OCCUPATION CODES (EXACT TASK ID JOIN)")
    print("=" * 100)

    # Load AEI tasks
    aei = pd.read_csv(TASKS_FILE, dtype={"task_id": "string"})
    print(f"\nAEI tasks to map: {len(aei):,}")

    # Load O*NET task statements
    onet = pd.read_excel(
        ONET_TASKS_FILE,
        usecols=["O*NET-SOC Code", "Title", "Task ID", "Task"],
    )
    onet.columns = ["onet_code", "occupation_title", "task_id", "task_text_onet"]
    onet["task_id"] = onet["task_id"].astype("Int64").astype("string")
    print(f"O*NET task statements: {len(onet):,} ({onet['onet_code'].nunique():,} occupations)")

    merged = aei.merge(
        onet[["task_id", "onet_code", "occupation_title"]],
        on="task_id",
        how="left",
    )
    merged["match_type"] = merged["onet_code"].apply(lambda v: "id" if pd.notna(v) else "unmatched")

    matched = merged[merged["match_type"] == "id"]
    unmatched = merged[merged["match_type"] == "unmatched"]

    print(f"\nMatched:   {matched['task_id'].nunique():,} tasks ({len(matched):,} rows)")
    print(f"Unmatched: {unmatched['task_id'].nunique():,} tasks")
    print(f"Occupations covered: {matched['onet_code'].nunique():,}")

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(OUTPUT_FILE, index=False)
    print(f"\n✓ Saved: {OUTPUT_FILE}")

    if len(unmatched) > 0:
        print(f"\nUnmatched tasks (by usage):")
        for _, r in unmatched.sort_values("onet_task_pct", ascending=False).head(20).iterrows():
            print(f"  [{r['onet_task_pct']:>6.2f}%]  {r['task_text'][:80]}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
