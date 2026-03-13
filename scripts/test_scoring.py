#!/usr/bin/env python3
"""
Test the scoring framework with 10 occupations using real data and the Claude API.

End-to-end test that scores a batch of occupations from the O*NET dataset,
computes rankings, and writes results to CSV.

Usage:
    export ANTHROPIC_API_KEY="sk-ant-v1-..."
    python3 scripts/test_scoring.py

Output:
    data/output/test_scores.csv
"""

import anthropic
import json
from score_occupations import (
    load_skill, load_occupations, write_scores_to_csv,
    parse_response, build_prompt, compute_rankings, SCORE_COLUMNS,
)

ONET_CSV = "data/intermediate/All_Occupations_ONET_enriched.csv"
SKILL_MD = "docs/scoring-framework.md"
OUTPUT_CSV = "data/output/test_scores.csv"
TEST_BATCH_SIZE = 3
MODEL = "claude-opus-4-6"
MAX_TOKENS = 4000

def verify_csv_columns(csv_path: str) -> bool:
    """Verify that output CSV contains all expected columns."""
    import csv
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        actual_cols = reader.fieldnames or []

    expected_cols = SCORE_COLUMNS

    missing = [c for c in expected_cols if c not in actual_cols]
    extra = [c for c in actual_cols if c not in expected_cols]

    print(f"\n✓ CSV Column Validation:")
    print(f"  Expected: {len(expected_cols)} columns")
    print(f"  Actual: {len(actual_cols)} columns")

    if missing:
        print(f"  ✗ Missing columns: {missing}")
        return False
    if extra:
        print(f"  ⚠ Extra columns: {extra}")

    print(f"  ✓ All expected columns present!")
    return True


def display_results(results: list[dict]):
    """Display scored results in a formatted table."""
    print("\n" + "="*80)
    print("✓ SCORING RESULTS")
    print("="*80 + "\n")

    print(f"{'O*NET Code':<12} {'Score':<8} {'Key Drivers':<60}")
    print("-" * 80)

    for result in results:
        code = result.get("onet_code", "")
        score = result.get("role_resilience_score", "")
        drivers = result.get("key_drivers", "")

        if len(drivers) > 57:
            drivers = drivers[:54] + "..."

        print(f"{code:<12} {score:<8} {drivers:<60}")

    print("-" * 80)
    print(f"Total scored: {len(results)}\n")

def main():
    print(f"\n🧪 AI-Resilience Scoring Test (Real Scores)")
    print(f"Testing with {TEST_BATCH_SIZE} occupations via Claude API\n")

    # Load data
    skill_text = load_skill(SKILL_MD)
    occupations = load_occupations(ONET_CSV)
    test_batch = occupations[:TEST_BATCH_SIZE]
    source_lookup = {o["Code"]: o for o in occupations}

    if not test_batch:
        print("Error: No occupations found")
        return False

    print(f"✓ Loaded {len(test_batch)} occupations:")
    for i, occ in enumerate(test_batch, 1):
        print(f"  {i}. {occ['Occupation']} ({occ['Code']})")

    # Initialize API client
    try:
        client = anthropic.Anthropic()
    except anthropic.AuthenticationError:
        print("\n✗ Authentication failed. Set ANTHROPIC_API_KEY environment variable:")
        print("   export ANTHROPIC_API_KEY=\"sk-ant-v1-...\"")
        return False

    # Build and send prompt
    print(f"\n✓ Generated scoring framework")
    prompt = build_prompt(test_batch, skill_text)

    try:
        print("🔄 Calling Claude API...")
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=skill_text,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.content[0].text
        results = parse_response(raw)
        print(f"✓ Received {len(results)} scores from API")

    except json.JSONDecodeError as e:
        print(f"✗ JSON parse error: {e}")
        print(f"Raw response: {raw[:300]}")
        return False

    except Exception as e:
        print(f"✗ API error: {e}")
        return False

    # Display results
    display_results(results)

    # Write to CSV and compute rankings
    write_scores_to_csv(results, OUTPUT_CSV, source_lookup, append=False)
    compute_rankings(OUTPUT_CSV)
    print(f"✓ Results written to: {OUTPUT_CSV}")

    # Verify all columns are present
    if not verify_csv_columns(OUTPUT_CSV):
        return False

    # Show CSV contents
    print(f"\n📊 CSV File Preview:")
    print("-" * 80)
    with open(OUTPUT_CSV, "r") as f:
        lines = f.readlines()
        for line in lines[:6]:
            print(line.rstrip())
    if len(lines) > 6:
        print(f"... ({len(lines) - 6} more rows)")
    print()

    return True

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
