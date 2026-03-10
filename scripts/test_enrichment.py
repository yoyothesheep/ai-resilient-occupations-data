#!/usr/bin/env python3
"""
Test the O*NET enrichment pipeline on two sets of occupations:

1. First 5 rows of data/input/All_Occupations_ONET.csv — broad sanity check
   that the pipeline runs without errors on real input data.

2. 3 targeted test cases — verify each education fallback path works correctly:
   - Standard scrape: education survey <li> items present on page
   - DB fallback: page has no education <li> items, falls back to O*NET DB file
   - No education: page has no <li> items and code is absent from DB (SOC mismatch)

Usage:
    python3 scripts/test_enrichment.py

Output:
    Prints formatted results to console
    Saves enrichment data to data/output/test_enrichment.csv
"""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from enrich_onet import (
    fetch_onet_page,
    load_education_data,
    load_occupation_data,
    load_sample_titles,
    load_employment_projections,
    extract_top_education,
    _education_from_jobzone,
    INPUT_CSV,
)

OUTPUT_CSV = Path(__file__).parent.parent / "data" / "output" / "test_enrichment.csv"
INPUT_SAMPLE_COUNT = 5

# Targeted test cases: (code, url, description, expected_edu_source)
TEST_CASES = [
    (
        "53-2021.00",
        "https://www.onetonline.org/link/summary/53-2021.00",
        "Air Traffic Controllers — education <li> present on page",
        "scraped",
    ),
    (
        "53-2022.00",
        "https://www.onetonline.org/link/summary/53-2022.00",
        "Airfield Operations Specialists — no education <li>, falls back to DB",
        "db",
    ),
    (
        "13-2011.00",
        "https://www.onetonline.org/link/summary/13-2011.00",
        "Accountants and Auditors — no <li>, not in DB, falls back to Job Zone prose",
        "jobzone",
    ),
]


def run_case(code, url, label, expected_edu_source, db_education, db_descriptions, db_titles, growth_lookup):
    """Scrape and enrich a single occupation. Returns (result_dict, passed)."""
    print(f"{'='*80}")
    print(f"{code} — {label}")
    print(f"{'='*80}")
    print(f"  URL: {url}")

    try:
        scraped = fetch_onet_page(url)
        print(f"  Wage:    {scraped['median_wage'] or 'N/A'}")
        print(f"  Growth:  {scraped['projected_growth'] or 'N/A'}")
        print(f"  Opening: {scraped['projected_job_openings'] or 'N/A'}")
    except Exception as e:
        print(f"  ERROR scraping: {e}")
        return None, False

    # Education: 1) scraped <li>, 2) DB file, 3) Job Zone prose
    edu_str = scraped.get("education_top_2", "")
    edu_source = "none"
    top_level = top_rate = ""
    if edu_str:
        edu_source = "scraped"
        top_level, top_rate = extract_top_education(edu_str)
    else:
        db_edu = db_education.get(code, {})
        edu_str = db_edu.get("education_top_2", "")
        top_level = db_edu.get("top_education_level", "")
        top_rate = db_edu.get("top_education_rate", "")
        if edu_str:
            edu_source = "db"
        else:
            jz_text = scraped.get("jobzone_education_text", "")
            top_level = _education_from_jobzone(jz_text) if jz_text else ""
            if top_level:
                edu_str = top_level
                edu_source = "jobzone"

    print(f"  Education source: {edu_source}" + (f"  (expected: {expected_edu_source})" if expected_edu_source else ""))
    print(f"  Education: {edu_str or 'N/A'}")
    print(f"  Top Level: {top_level or 'N/A'} ({top_rate or 'N/A'})")

    desc = db_descriptions.get(code, "")
    titles = db_titles.get(code, "")
    percent_change = growth_lookup.get(code, "")
    if not percent_change and code.endswith(".00"):
        percent_change = growth_lookup.get(code[:-3], "")

    print(f"  Description: {desc[:80] + '...' if len(desc) > 80 else desc or 'N/A'}")
    print(f"  Titles: {titles[:80] + '...' if len(titles) > 80 else titles or 'N/A'}")
    print(f"  % Change: {percent_change or 'N/A'}")

    passed = True
    if expected_edu_source:
        passed = edu_source == expected_edu_source
        status = "PASS" if passed else "FAIL"
        print(f"\n  [{status}] Education source: got={edu_source!r}, expected={expected_edu_source!r}")
    print()

    return {
        "code": code,
        "description": label,
        "scraped": scraped,
        "edu_str": edu_str,
        "top_level": top_level,
        "top_rate": top_rate,
        "edu_source": edu_source,
        "desc": desc,
        "titles": titles,
        "percent_change": percent_change,
    }, passed


def main():
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)

    print("\nO*NET Enrichment Test")
    print(f"{'='*80}\n")

    # Load DB sources
    print("Loading O*NET DB files...")
    db_education = load_education_data()
    db_descriptions = load_occupation_data()
    db_titles = load_sample_titles()
    growth_lookup = load_employment_projections()
    print(f"  Education: {len(db_education)} occupations")
    print(f"  Descriptions: {len(db_descriptions)} occupations")
    print(f"  Titles: {len(db_titles)} occupations")
    print(f"  Growth projections: {len(growth_lookup)} occupations\n")

    results = []
    all_passed = True

    # --- Part 1: First N rows from input CSV (sanity check) ---
    print(f"\n{'#'*80}")
    print(f"# PART 1: First {INPUT_SAMPLE_COUNT} rows from All_Occupations_ONET.csv")
    print(f"{'#'*80}\n")
    with open(INPUT_CSV, newline="", encoding="utf-8") as f:
        input_rows = list(csv.DictReader(f))
    for row in input_rows[:INPUT_SAMPLE_COUNT]:
        result, passed = run_case(
            row["Code"], row["url"], row["Occupation"],
            expected_edu_source=None,
            db_education=db_education, db_descriptions=db_descriptions,
            db_titles=db_titles, growth_lookup=growth_lookup,
        )
        if result:
            results.append(result)
        if not passed:
            all_passed = False

    # --- Part 2: Targeted education-fallback test cases ---
    print(f"\n{'#'*80}")
    print(f"# PART 2: Targeted education fallback test cases")
    print(f"{'#'*80}\n")

    for code, url, description, expected_edu_source in TEST_CASES:
        result, passed = run_case(
            code, url, description, expected_edu_source,
            db_education=db_education, db_descriptions=db_descriptions,
            db_titles=db_titles, growth_lookup=growth_lookup,
        )
        if result:
            results.append(result)
        if not passed:
            all_passed = False

    # Write CSV
    fieldnames = [
        "Code", "Description", "Median Wage", "Projected Growth",
        "Employment Change, 2024-2034", "Projected Job Openings",
        "Education", "Top Education Level", "Top Education Rate",
        "Education Source", "Sample Job Titles", "Job Description",
    ]
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow({
                "Code": r["code"],
                "Description": r["description"],
                "Median Wage": r["scraped"].get("median_wage", ""),
                "Projected Growth": r["scraped"].get("projected_growth", ""),
                "Employment Change, 2024-2034": r["percent_change"],
                "Projected Job Openings": r["scraped"].get("projected_job_openings", ""),
                "Education": r["edu_str"],
                "Top Education Level": r["top_level"],
                "Top Education Rate": r["top_rate"],
                "Education Source": r["edu_source"],
                "Sample Job Titles": r["titles"],
                "Job Description": r["desc"],
            })

    print(f"{'='*80}")
    print(f"Output saved to: {OUTPUT_CSV}")
    overall = "ALL PASSED" if all_passed else "SOME FAILED"
    print(f"Result: {overall}\n")
    return all_passed


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
