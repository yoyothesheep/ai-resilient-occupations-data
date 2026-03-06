#!/usr/bin/env python3
"""
Test the O*NET enrichment scraper on a sample of occupations.

Tests that the enrich_onet.py parser correctly extracts:
- Median wage
- Projected growth (numeric percent change from Employment Projections.csv)
- Projected job openings
- Education requirements
- Sample of reported job titles

Usage:
    python3 scripts/test_enrichment.py

Output:
    Prints formatted results to console
    Saves enrichment data to data/output/test_enrichment.csv
"""

import csv
from pathlib import Path
from enrich_onet import fetch_onet_data, load_employment_projections

INPUT_CSV = Path(__file__).parent.parent / "data" / "input" / "All_Occupations_ONET.csv"
OUTPUT_CSV = Path(__file__).parent.parent / "data" / "output" / "test_enrichment.csv"
SAMPLE_SIZE = 3

EXPECTED_FIELDS = [
    "median_wage",
    "projected_growth",
    "projected_job_openings",
    "education_top_2",
    "top_education_level",
    "top_education_rate",
    "sample_job_titles",
]


def load_sample_occupations(n: int) -> list[dict]:
    """Load first n occupations from input CSV."""
    with open(INPUT_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [row for i, row in enumerate(reader) if i < n]


def lookup_percent_change(code: str, growth_lookup: dict) -> str:
    """Look up Employment Percent Change for a code, trying with and without .00 suffix."""
    percent_change = growth_lookup.get(code, "")
    if not percent_change and code.endswith(".00"):
        percent_change = growth_lookup.get(code[:-3], "")
    return percent_change


def display_result(index: int, occupation: dict, enriched_data: dict, percent_change: str):
    """Display a single enriched result."""
    code = occupation["Code"]
    name = occupation["Occupation"]

    print(f"\n{'='*90}")
    print(f"[{index}] {code}: {name}")
    print(f"{'='*90}")

    print(f"  URL: {occupation['url']}\n")

    # Check for missing fields
    missing = [f for f in EXPECTED_FIELDS if f not in enriched_data or not enriched_data[f]]
    if missing:
        print(f"  ⚠ Missing fields: {', '.join(missing)}\n")

    print(f"  Median Wage:")
    print(f"    {enriched_data.get('median_wage', 'N/A')}\n")

    print(f"  Projected Growth (Employment Projections.csv):")
    print(f"    {percent_change if percent_change else 'N/A (no match in Employment Projections.csv)'}\n")

    print(f"  Projected Job Openings:")
    print(f"    {enriched_data.get('projected_job_openings', 'N/A')}\n")

    print(f"  Education (all levels):")
    print(f"    {enriched_data.get('education_top_2', 'N/A')}\n")

    print(f"  Top Education Level:")
    print(f"    {enriched_data.get('top_education_level', 'N/A')}")
    print(f"    ({enriched_data.get('top_education_rate', '')})\n")

    print(f"  Sample Job Titles:")
    titles = enriched_data.get("sample_job_titles", "N/A")
    if titles and len(titles) > 100:
        print(f"    {titles[:97]}...\n")
    else:
        print(f"    {titles}\n")


def verify_all_fields(results: list[dict], percent_changes: list[str]) -> bool:
    """Verify all results have the core expected fields and percent change values."""
    required_fields = [
        "median_wage",
        "projected_job_openings",
        "sample_job_titles",
    ]
    optional_fields = ["education_top_2", "top_education_level", "top_education_rate"]

    all_ok = True
    for i, (data, pct) in enumerate(zip(results, percent_changes), 1):
        missing = [f for f in required_fields if f not in data or not data[f]]
        issues = []
        if missing:
            issues.append(f"missing scrape fields: {', '.join(missing)}")
        if not pct:
            issues.append("no Employment Projections match")

        if issues:
            print(f"  ⚠ Result {i}: {'; '.join(issues)}")
            all_ok = False
        else:
            present_optional = [f for f in optional_fields if f in data and data[f]]
            print(f"  ✓ Result {i}: all required fields + {len(present_optional)}/{len(optional_fields)} optional + growth={pct}%")

    return all_ok


def main():
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)

    print(f"\n🧪 O*NET Enrichment Test")
    print(f"Scraping {SAMPLE_SIZE} sample occupations\n")

    # Load Employment Projections lookup
    print(f"🔄 Loading Employment Projections.csv...")
    growth_lookup = load_employment_projections()
    print(f"✓ Loaded {len(growth_lookup)} occupation growth projections\n")

    # Load sample occupations
    occupations = load_sample_occupations(SAMPLE_SIZE)
    if not occupations:
        print("Error: No occupations found in input CSV")
        return False

    print(f"✓ Loaded {len(occupations)} occupations:")
    for i, occ in enumerate(occupations, 1):
        print(f"  {i}. {occ['Occupation']} ({occ['Code']})")

    # Fetch enrichment data for each
    print(f"\n🔄 Fetching enrichment data from O*NET...\n")
    results = []
    percent_changes = []
    occupations_list = []
    for i, occ in enumerate(occupations, 1):
        code = occ["Code"]
        url = occ["url"]

        print(f"  [{i}/{len(occupations)}] Fetching {code}...", end="", flush=True)
        try:
            data = fetch_onet_data(url)
            pct = lookup_percent_change(code, growth_lookup)
            results.append(data)
            percent_changes.append(pct)
            occupations_list.append(occ)
            print(" ✓")
        except Exception as e:
            print(f" ✗ ({e})")
            return False

    # Display results
    print(f"\n✓ Successfully fetched {len(results)} occupations\n")
    for i, (occ, data, pct) in enumerate(zip(occupations_list, results, percent_changes), 1):
        display_result(i, occ, data, pct)

    # Verify all fields are present
    print(f"\n{'='*90}")
    print("VERIFICATION")
    print(f"{'='*90}\n")

    if not verify_all_fields(results, percent_changes):
        print("\n⚠ Some fields are missing or unmatched")
    else:
        print("\n✓ All expected fields present in all results!")

    # Write results to CSV — same format as All_Occupations_ONET_enriched.csv
    print(f"\n{'='*90}")
    print("WRITING OUTPUT CSV")
    print(f"{'='*90}\n")

    fieldnames = [
        "Job Zone", "Code", "Occupation", "Data-level", "url",
        "Median Wage", "Projected Growth", "Projected Job Openings",
        "Education", "Top Education Level", "Top Education Rate",
        "Sample Job Titles", "Job Description",
    ]

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for occ, enriched, pct in zip(occupations_list, results, percent_changes):
            writer.writerow({
                "Job Zone": occ["Job Zone"],
                "Code": occ["Code"],
                "Occupation": occ["Occupation"],
                "Data-level": occ["Data-level"],
                "url": occ["url"],
                "Median Wage": enriched.get("median_wage", ""),
                "Projected Growth": pct,
                "Projected Job Openings": enriched.get("projected_job_openings", ""),
                "Education": enriched.get("education_top_2", ""),
                "Top Education Level": enriched.get("top_education_level", ""),
                "Top Education Rate": enriched.get("top_education_rate", ""),
                "Sample Job Titles": enriched.get("sample_job_titles", ""),
                "Job Description": enriched.get("job_description", ""),
            })

    print(f"✓ Output saved to: {OUTPUT_CSV}")

    print(f"\n📊 CSV File Preview:")
    print(f"{'-'*90}")
    with open(OUTPUT_CSV, "r") as f:
        lines = f.readlines()
        for line in lines[:4]:
            print(line.rstrip())
        if len(lines) > 4:
            print(f"... ({len(lines) - 4} more rows)")

    return True


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
