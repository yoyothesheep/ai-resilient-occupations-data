#!/usr/bin/env python3
"""
Score and rank all occupations using the Anthropic API.

Loads occupations from CSV, batches them, scores via Claude API, computes a
composite final ranking, and writes results to CSV sorted by ranking.
Supports resuming interrupted runs.

Usage:
    python3 scripts/score_occupations.py

Requirements:
    pip install anthropic
    export ANTHROPIC_API_KEY="sk-ant-v1-..."

Output:
    data/output/ai_resilience_scores.csv  — all occupations + scores + ranking
    data/output/score_log.txt             — progress log (for resuming)
"""

import anthropic
import csv
import json
import math
import os
import re
import time

# ── Configuration ────────────────────────────────────────────────────────────
ONET_CSV       = "data/intermediate/All_Occupations_ONET_enriched.csv"
SKILL_MD       = "docs/scoring-framework.md"
OUTPUT_CSV     = "data/output/ai_resilience_scores.csv"
LOG_FILE       = "data/output/score_log.txt"
BATCH_SIZE     = 10      # Occupations per API call
SLEEP_SEC      = 2       # Pause between batches (rate limit buffer)
START_BATCH    = 0       # Change to resume from specific batch
MODEL          = "claude-opus-4-6"
MAX_TOKENS     = 16000

SCORE_COLUMNS = [
    "Job Zone", "Code", "Occupation", "Data-level", "url",
    "Median Wage", "Projected Growth", "Employment Change, 2024-2034", "Projected Job Openings",
    "Education", "Top Education Level", "Top Education Rate",
    "Sample Job Titles", "Job Description",
    "role_resilience_score", "final_ranking", "key_drivers",
    "altpath url", "altpath simple title"
]

# ── Ranking configuration ────────────────────────────────────────────────────
W_RESILIENCE = 0.50
W_GROWTH     = 0.30
W_OPENINGS   = 0.20

# Growth normalization: prefers numeric "Employment Change, 2024-2034" (log-transformed + min-max).
# Falls back to "Projected Growth" string via GROWTH_MAP if numeric value is missing.
GROWTH_MAP = {
    "decline":              0.0,
    "little or no change":  0.2,
    "slower than average":  0.4,
    "average":              0.6,
    "faster than average":  0.8,
    "much faster than average": 1.0,
}

# ── Helper functions ──────────────────────────────────────────────────────────
def load_skill(path: str) -> str:
    with open(path, "r") as f:
        return f.read()

def load_occupations(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    scoreable = [
        r for r in rows
        if r["Job Zone"] not in ("n/a", "") and r["Data-level"] == "Y"
    ]
    return scoreable

def build_prompt(occupations: list[dict], skill_text: str) -> str:
    occ_list = "\n".join(
        f"{i+1}. {r['Occupation']} (O*NET: {r['Code']}, Job Zone: {r['Job Zone']})"
        for i, r in enumerate(occupations)
    )

    scoring_prompt = f"""Score the following {len(occupations)} occupations using the AI-Resilience Scoring Skill.

OCCUPATIONS TO SCORE:
{occ_list}

Respond ONLY with a valid JSON array. Each element must include all 10 attribute scores:
{{
  "onet_code": "XX-XXXX.XX",
  "a1_physical_presence": <1-5>,
  "a2_trust_core_product": <1-5>,
  "a3_novel_judgment": <1-5>,
  "a4_legal_accountability": <1-5>,
  "a5_deep_org_context": <1-5>,
  "a6_political_navigation": <1-5>,
  "a7_creative_pov": <1-5>,
  "a8_changed_by_experience": <1-5>,
  "a9_expertise_underutilized": <1-5>,
  "a10_downstream_ai_mgmt": <1-5>,
  "role_resilience_score": <1.0-5.0>,
  "key_drivers": "2-3 sentences (reference which attributes drive the score)"
}}"""

    return f"""{skill_text}

---

{scoring_prompt}"""

def write_scores_to_csv(results: list[dict], output_path: str, source_lookup: dict, append: bool = False):
    """Write scored results to CSV file."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    mode = "a" if append and os.path.exists(output_path) else "w"
    write_header = mode == "w"

    with open(output_path, mode, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=SCORE_COLUMNS)
        if write_header:
            writer.writeheader()

        for result in results:
            code = result.get("onet_code")
            src = source_lookup.get(code, {})
            writer.writerow({
                "Job Zone": src.get("Job Zone", ""),
                "Code": src.get("Code", ""),
                "Occupation": src.get("Occupation", ""),
                "Data-level": src.get("Data-level", ""),
                "url": src.get("url", ""),
                "Median Wage": src.get("Median Wage", ""),
                "Projected Growth": src.get("Projected Growth", ""),
                "Employment Change, 2024-2034": src.get("Employment Change, 2024-2034", ""),
                "Projected Job Openings": src.get("Projected Job Openings", ""),
                "Education": src.get("Education", ""),
                "Top Education Level": src.get("Top Education Level", ""),
                "Top Education Rate": src.get("Top Education Rate", ""),
                "Sample Job Titles": src.get("Sample Job Titles", ""),
                "Job Description": src.get("Job Description", ""),
                "role_resilience_score": result.get("role_resilience_score", result.get("final_score", "")),
                "key_drivers": result.get("key_drivers", ""),
                "altpath url": src.get("altpath url", ""),
                "altpath simple title": src.get("altpath simple title", ""),
            })

def load_scored_codes(path: str) -> set:
    if not os.path.exists(path):
        return set()
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return {row["Code"] for row in reader}

def parse_response(text: str) -> list[dict]:
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    text = text.strip()
    return json.loads(text)

def log(msg: str):
    print(msg)
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(msg + "\n")

# ── Ranking ──────────────────────────────────────────────────────────────────
def _growth_from_string(s: str) -> float | None:
    """Map scraped Projected Growth string to a 0–1 normalized value via GROWTH_MAP."""
    s_lower = s.lower()
    for key, val in GROWTH_MAP.items():
        if key in s_lower:
            return val
    return None


def compute_rankings(csv_path: str):
    """Read scored CSV, compute final_ranking, rewrite sorted by ranking.

    Growth normalization: prefers numeric 'Employment Change, 2024-2034' (log-transformed +
    min-max scaled). Falls back to 'Projected Growth' string via GROWTH_MAP.
    """
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        return

    # Collect growth values: numeric where available, None otherwise (string fallback applied later)
    # sign(x) * log1p(|x|) handles negatives and compresses the -36 to +50 range
    numeric_growth = []
    for row in rows:
        raw = row.get("Employment Change, 2024-2034", "").strip()
        if raw:
            try:
                v = float(raw)
                numeric_growth.append(math.copysign(math.log1p(abs(v)), v))
            except ValueError:
                numeric_growth.append(None)
        else:
            numeric_growth.append(None)

    # Compute min/max across numeric values only (for min-max normalization)
    valid_numeric = [v for v in numeric_growth if v is not None]
    if valid_numeric:
        g_min = min(valid_numeric)
        g_max = max(valid_numeric)
        g_range = g_max - g_min if g_max != g_min else 1.0
    else:
        g_min = 0
        g_max = 1.0
        g_range = 1.0

    # Build final growth_values: numeric (normalized) where available, string-mapped as fallback
    growth_values = []
    for i, row in enumerate(rows):
        if numeric_growth[i] is not None:
            growth_values.append(("numeric", numeric_growth[i]))
        else:
            fallback = _growth_from_string(row.get("Projected Growth", ""))
            growth_values.append(("string", fallback) if fallback is not None else ("none", None))

    # Collect log-openings for normalization
    log_openings = []
    for row in rows:
        raw = row.get("Projected Job Openings", "").replace(",", "")
        if raw.isdigit() and int(raw) > 0:
            log_openings.append(math.log(int(raw)))
        else:
            log_openings.append(None)

    # Compute log_min and log_max for normalization
    valid_logs = [v for v in log_openings if v is not None]
    if valid_logs:
        log_min = min(valid_logs)
        log_max = max(valid_logs)
        log_range = log_max - log_min if log_max != log_min else 1.0
    else:
        log_min = 0
        log_max = 1.0
        log_range = 1.0

    for i, row in enumerate(rows):
        score_str = row.get("role_resilience_score", "")
        gtype, gval = growth_values[i]
        log_val = log_openings[i]

        r_norm = (float(score_str) - 1.0) / 4.0 if score_str else None
        if gtype == "numeric":
            g_norm = (gval - g_min) / g_range  # min-max normalized log-transformed value
        elif gtype == "string":
            g_norm = gval  # already 0–1 from GROWTH_MAP
        else:
            g_norm = None
        o_norm = (log_val - log_min) / log_range if log_val is not None else None

        # Weighted composite (no re-normalization for missing data)
        parts = []
        if r_norm is not None:
            parts.append(r_norm * W_RESILIENCE)
        if g_norm is not None:
            parts.append(g_norm * W_GROWTH)
        if o_norm is not None:
            parts.append(o_norm * W_OPENINGS)

        raw_score = sum(parts) if parts else 0.0

        row["final_ranking"] = round(raw_score, 3)

    # Sort by final_ranking descending
    rows.sort(key=lambda r: r.get("final_ranking", 0), reverse=True)

    # Write back with final_ranking included in SCORE_COLUMNS
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=SCORE_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    ranked_count = sum(1 for r in rows if r.get("final_ranking", 0) > 0)
    log(f"\n📊 Ranked {ranked_count} occupations. Top 10:")
    for r in rows[:10]:
        log(f"   {r['final_ranking']}  {r.get('role_resilience_score','?'):>4}  {r['Occupation']}")

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    skill_text   = load_skill(SKILL_MD)
    occupations  = load_occupations(ONET_CSV)
    scored_codes = load_scored_codes(OUTPUT_CSV)
    source_lookup = {o["Code"]: o for o in occupations}

    try:
        client = anthropic.Anthropic()
    except anthropic.AuthenticationError:
        log("\n✗ Authentication failed. Set ANTHROPIC_API_KEY environment variable:")
        log("   export ANTHROPIC_API_KEY=\"sk-ant-v1-...\"")
        return False

    remaining = [o for o in occupations if o["Code"] not in scored_codes]
    log(f"\n📊 Scoring {len(remaining)} occupations (skipping {len(scored_codes)} already done)")

    batches = [remaining[i:i+BATCH_SIZE] for i in range(0, len(remaining), BATCH_SIZE)]
    total   = len(batches)
    log(f"📦 {total} batches × {BATCH_SIZE} occupations\n")

    write_header = not os.path.exists(OUTPUT_CSV) or len(scored_codes) == 0

    for batch_idx, batch in enumerate(batches[START_BATCH:], start=START_BATCH):
        log(f"── Batch {batch_idx+1}/{total} ({len(batch)} occupations)")
        names = [o["Occupation"] for o in batch]
        log(f"   {', '.join(names[:3])}{'...' if len(names) > 3 else ''}")

        prompt = build_prompt(batch, skill_text)

        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=skill_text,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = response.content[0].text
            results = parse_response(raw)

            write_scores_to_csv(results, OUTPUT_CSV, source_lookup, append=not write_header)
            write_header = False

            # Log component scores for each occupation
            for result in results:
                code = result.get('onet_code')
                occ_name = source_lookup.get(code, {}).get('Occupation', code)
                score = result.get('role_resilience_score', '?')
                log(f"\n   {occ_name} ({code})")
                log(f"     Final Score: {score}")
                log(f"     A1 Physical Presence: {result.get('a1_physical_presence', '?')}")
                log(f"     A2 Trust Core Product: {result.get('a2_trust_core_product', '?')}")
                log(f"     A3 Novel Judgment: {result.get('a3_novel_judgment', '?')}")
                log(f"     A4 Legal Accountability: {result.get('a4_legal_accountability', '?')}")
                log(f"     A5 Deep Org Context: {result.get('a5_deep_org_context', '?')}")
                log(f"     A6 Political Navigation: {result.get('a6_political_navigation', '?')}")
                log(f"     A7 Creative POV: {result.get('a7_creative_pov', '?')}")
                log(f"     A8 Changed by Experience: {result.get('a8_changed_by_experience', '?')}")
                log(f"     A9 Expertise Underutilized: {result.get('a9_expertise_underutilized', '?')}")
                log(f"     A10 Downstream/AI Mgmt: {result.get('a10_downstream_ai_mgmt', '?')}")

            scores = [r.get('role_resilience_score', r.get('final_score')) for r in results]
            log(f"   ✓ Scored {len(results)}. Range: {min(scores):.1f}–{max(scores):.1f}")

        except json.JSONDecodeError as e:
            log(f"   ✗ JSON parse error: {e}")
            log(f"   Raw response: {raw[:300]}")
            continue

        except anthropic.RateLimitError:
            log(f"   ✗ Rate limited. Waiting 30s before retry...")
            time.sleep(30)
            continue

        except Exception as e:
            log(f"   ✗ API error: {e}")
            log("   Sleeping 30s before retry...")
            time.sleep(30)
            continue

        if batch_idx < total - 1:
            time.sleep(SLEEP_SEC)

    # Compute final rankings after all scoring is done
    log("\n── Computing final rankings...")
    compute_rankings(OUTPUT_CSV)

    log(f"\n✓ Complete! Results in {OUTPUT_CSV}\n")
    return True


def rerank():
    """
    Re-generate ai_resilience_scores.csv without calling the LLM.

    Merges existing role_resilience_score + key_drivers from the current output CSV
    with fresh enrichment data (Projected Growth, Sample Job Titles, etc.)
    from the enriched intermediate CSV, then recomputes final_ranking.

    Usage:
        python3 scripts/score_occupations.py --rerank
    """
    log("── Reranking: merging existing scores with fresh enrichment data...")

    if not os.path.exists(OUTPUT_CSV):
        log(f"✗ No existing scores found at {OUTPUT_CSV}")
        return False

    # Load existing scores (role_resilience_score + key_drivers), keyed by Code
    with open(OUTPUT_CSV, newline="", encoding="utf-8") as f:
        existing = {r["Code"]: r for r in csv.DictReader(f)}
    log(f"  Loaded {len(existing)} existing scores")

    # Load fresh enrichment data, keyed by Code
    enrichment = load_occupations(ONET_CSV)
    log(f"  Loaded {len(enrichment)} enriched occupations")

    # Merge: use enrichment for all fields, pull role_resilience_score + key_drivers from existing scores
    merged = []
    missing = 0
    for occ in enrichment:
        code = occ["Code"]
        scored = existing.get(code)
        if not scored or not scored.get("role_resilience_score"):
            missing += 1
            continue
        row = {col: "" for col in SCORE_COLUMNS}
        for col in SCORE_COLUMNS:
            if col in ("role_resilience_score", "key_drivers", "final_ranking"):
                row[col] = scored.get(col, "")
            else:
                row[col] = occ.get(col, "")
        merged.append(row)

    log(f"  Merged {len(merged)} occupations ({missing} skipped — no existing score)")

    # Write merged output (without final_ranking — compute_rankings will add it)
    os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=SCORE_COLUMNS)
        writer.writeheader()
        writer.writerows(merged)

    log(f"\n── Computing final rankings...")
    compute_rankings(OUTPUT_CSV)
    log(f"\n✓ Rerank complete! Results in {OUTPUT_CSV}\n")
    return True


if __name__ == "__main__":
    import sys
    if "--rerank" in sys.argv:
        success = rerank()
    else:
        success = main()
    exit(0 if success else 1)
