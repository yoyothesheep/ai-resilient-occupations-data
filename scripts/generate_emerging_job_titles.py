"""
generate_emerging_job_titles.py

Two-step script:
1. GENERATE: For a given cluster or set of O*NET codes, uses Claude to discover
   real-world job titles that map to each occupation but aren't in O*NET's
   Sample Job Titles. Appends new entries to emerging_job_titles.csv.
2. MERGE: Reads all entries from emerging_job_titles.csv and writes them into
   the "Emerging Job Titles" column of ai_resilience_scores.csv.

Usage:
    python3 scripts/generate_emerging_job_titles.py --merge-only
    python3 scripts/generate_emerging_job_titles.py --cluster office-admin
    python3 scripts/generate_emerging_job_titles.py --code 13-1161.00
    python3 scripts/generate_emerging_job_titles.py --all

--merge-only: skip generation, just sync emerging_job_titles.csv → scores CSV
--cluster:    generate titles for all occupations in a cluster
--code:       generate titles for a single occupation
--all:        generate titles for all occupations in scores CSV (slow)

Safe to re-run — generation skips codes that already have entries. Merge always
overwrites the column with current CSV state.
"""

import argparse
import csv
import json
import os
import sys
from collections import defaultdict

import anthropic

SCORES_PATH    = "data/output/ai_resilience_scores.csv"
TITLES_PATH    = "data/emerging_roles/emerging_job_titles.csv"
CLUSTER_ROLES  = "data/career_clusters/cluster_roles.csv"
COLUMN_NAME    = "Emerging Job Titles"
MODEL          = "claude-haiku-4-5-20251001"

TITLES_FIELDNAMES = ["onet_code", "job_title", "notes"]


# ── Load helpers ──────────────────────────────────────────────────────────────

def load_scores() -> list[dict]:
    with open(SCORES_PATH, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_existing_titles() -> dict[str, list[str]]:
    """Returns {onet_code: [job_title, ...]}"""
    titles = defaultdict(list)
    if not os.path.exists(TITLES_PATH):
        return titles
    with open(TITLES_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            code = row["onet_code"].strip()
            title = row["job_title"].strip()
            if code and title:
                titles[code].append(title)
    return titles


def load_cluster_codes(cluster_id: str) -> list[str]:
    codes = []
    with open(CLUSTER_ROLES, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["cluster_id"] == cluster_id:
                codes.append(row["onet_code"])
    return codes


# ── Generation ────────────────────────────────────────────────────────────────

PROMPT_TEMPLATE = """You are a labor market researcher. Given an O*NET occupation, identify real-world job titles that:
- Are commonly used in actual job postings for this role
- Do NOT appear in O*NET's official "Sample Job Titles" list
- Are searched frequently on job boards (not niche or made-up)
- Map meaningfully to this occupation's actual work

Occupation: {occupation} ({onet_code})
O*NET Sample Job Titles: {sample_titles}

Return a JSON array of objects. Each object has:
- "job_title": the real-world title as it appears in job postings
- "notes": one sentence explaining why it maps here and what's different from the O*NET title

Return 2–5 titles. Return an empty array [] if O*NET's sample titles already cover common usage well.
Return only valid JSON, no other text."""


def generate_titles_for_occupation(client: anthropic.Anthropic, occ: dict) -> list[dict]:
    """Calls Claude to generate job title aliases for one occupation."""
    prompt = PROMPT_TEMPLATE.format(
        occupation=occ["Occupation"],
        onet_code=occ["Code"],
        sample_titles=occ.get("Sample Job Titles", "").strip() or "(none listed)",
    )
    msg = client.messages.create(
        model=MODEL,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    try:
        results = json.loads(raw)
        return [{"onet_code": occ["Code"], "job_title": r["job_title"], "notes": r.get("notes", "")}
                for r in results if r.get("job_title")]
    except (json.JSONDecodeError, KeyError) as e:
        print(f"  ⚠ Parse error for {occ['Code']}: {e}")
        return []


def append_titles(new_rows: list[dict]):
    """Appends new rows to emerging_job_titles.csv."""
    file_exists = os.path.exists(TITLES_PATH)
    with open(TITLES_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=TITLES_FIELDNAMES)
        if not file_exists:
            writer.writeheader()
        writer.writerows(new_rows)


def print_prompts_for_occupations(occupations: list[dict], existing: dict[str, list[str]]):
    """Print all prompts to stdout without calling the API (inline Claude Code workflow).

    For each occupation not already in existing, prints the prompt wrapped in
    delimiters so Claude Code can read them and author JSON responses directly.
    Claude Code then writes the resulting rows to the CSV via append_titles().
    """
    skipped = 0
    printed = 0
    for occ in occupations:
        code = occ["Code"]
        if code in existing:
            skipped += 1
            continue
        prompt = PROMPT_TEMPLATE.format(
            occupation=occ["Occupation"],
            onet_code=code,
            sample_titles=occ.get("Sample Job Titles", "").strip() or "(none listed)",
        )
        print(f"\n{'='*80}")
        print(f"── {occ['Occupation']} ({code})")
        print(f"{'='*80}")
        print(prompt)
        print(f"{'='*80}")
        printed += 1
    print(f"\n✓ Done. {printed} prompts printed. {skipped} skipped (already have entries).")
    print("Author JSON arrays for each occupation above, then call append_titles() to save.")


def generate(occupations: list[dict], existing: dict[str, list[str]]):
    client = anthropic.Anthropic()
    skipped = 0
    total_new = 0

    for occ in occupations:
        code = occ["Code"]
        if code in existing:
            skipped += 1
            continue
        print(f"  Generating titles for {occ['Occupation']} ({code})...")
        new_rows = generate_titles_for_occupation(client, occ)
        if new_rows:
            append_titles(new_rows)
            total_new += len(new_rows)
            print(f"    → {len(new_rows)} titles added: {[r['job_title'] for r in new_rows]}")
        else:
            print(f"    → 0 titles (O*NET sample titles sufficient)")

    print(f"\nGeneration complete. {total_new} new titles added. {skipped} occupations skipped (already have entries).")


# ── Merge ─────────────────────────────────────────────────────────────────────

def merge():
    titles_by_code = load_existing_titles()

    with open(SCORES_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames[:]
        rows = list(reader)

    if COLUMN_NAME not in fieldnames:
        fieldnames.append(COLUMN_NAME)

    updated = 0
    for row in rows:
        code = row["Code"].strip()
        titles = titles_by_code.get(code, [])
        row[COLUMN_NAME] = "; ".join(titles) if titles else ""
        if titles:
            updated += 1

    with open(SCORES_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    total = sum(len(v) for v in titles_by_code.values())
    print(f"Merged {total} titles across {len(titles_by_code)} codes into {updated} rows in {SCORES_PATH}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--merge-only", action="store_true", help="Skip generation, just sync CSV → scores")
    group.add_argument("--cluster", help="Generate titles for all occupations in a cluster")
    group.add_argument("--code", help="Generate titles for a single O*NET code")
    group.add_argument("--all", action="store_true", help="Generate titles for all occupations")
    parser.add_argument("--print-prompts", action="store_true",
                        help="Print all prompts to stdout without calling the API (inline Claude Code workflow)")
    args = parser.parse_args()

    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    if args.merge_only:
        merge()
        return

    scores = load_scores()
    scores_by_code = {r["Code"]: r for r in scores}
    existing = load_existing_titles()

    if args.cluster:
        codes = load_cluster_codes(args.cluster)
        if not codes:
            print(f"No occupations found for cluster '{args.cluster}'")
            sys.exit(1)
        occupations = [scores_by_code[c] for c in codes if c in scores_by_code]
        print(f"Generating titles for {len(occupations)} occupations in cluster '{args.cluster}'...")
    elif args.code:
        if args.code not in scores_by_code:
            print(f"Code {args.code} not found in scores CSV")
            sys.exit(1)
        occupations = [scores_by_code[args.code]]
    elif args.all:
        occupations = scores
        print(f"Generating titles for all {len(occupations)} occupations...")
    else:
        parser.print_help()
        sys.exit(1)

    if args.print_prompts:
        print_prompts_for_occupations(occupations, existing)
        return

    generate(occupations, existing)
    print("\nMerging into scores CSV...")
    merge()


if __name__ == "__main__":
    main()
