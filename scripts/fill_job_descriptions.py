#!/usr/bin/env python3
"""
One-time script to fill only the job_description field.
Keeps all existing cached data, only extracts and adds descriptions.
"""

import csv
import json
import time
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
INPUT_CSV = PROJECT_ROOT / "data" / "input" / "All_Occupations_ONET.csv"
CACHE_FILE = PROJECT_ROOT / "data" / "intermediate" / "onet_enrichment_cache.json"
OUTPUT_CSV = PROJECT_ROOT / "data" / "output" / "ai_resilience_scores.csv"

HEADERS = {"User-Agent": "Mozilla/5.0 (research project)"}
DELAY = 0.5


class DescriptionParser(HTMLParser):
    """Extract only the job description from an O*NET page."""

    def __init__(self):
        super().__init__()
        self._after_begin_content = False
        self._capturing_description = False
        self._description_buf = []
        self.job_description = None

    def handle_comment(self, data):
        if "begin content" in data:
            self._after_begin_content = True

    def handle_starttag(self, tag, attrs):
        if tag == "p" and self._after_begin_content and self.job_description is None:
            self._capturing_description = True
            self._description_buf = []

    def handle_endtag(self, tag):
        if tag == "p" and self._capturing_description:
            import re
            desc_text = "".join(self._description_buf).strip()
            desc_text = re.sub(r"\s+", " ", desc_text).strip()
            if desc_text:
                self.job_description = desc_text
            self._capturing_description = False
            self._after_begin_content = False

    def handle_data(self, data):
        if self._capturing_description:
            self._description_buf.append(data)


def fetch_description(url: str) -> str:
    """Fetch and extract only the job description from a page."""
    req = urllib.request.Request(url, headers=HEADERS)
    resp = urllib.request.urlopen(req, timeout=30)
    html = resp.read().decode("utf-8", errors="replace")

    parser = DescriptionParser()
    parser.feed(html)
    return parser.job_description or ""


def main():
    print("Loading cache...")
    enriched_data = {}
    if CACHE_FILE.exists():
        with open(CACHE_FILE) as f:
            enriched_data = json.load(f)

    print("Reading input CSV...")
    with open(INPUT_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    total = len(rows)
    filled_count = 0
    skipped_count = 0

    print(f"Processing {total} occupations...\n")

    for i, row in enumerate(rows):
        code = row["Code"]
        url = row["url"]

        # Skip if already has description
        if code in enriched_data and enriched_data[code].get("job_description"):
            skipped_count += 1
            continue

        print(f"[{i+1}/{total}] Fetching description for {code} - {row['Occupation']}...")

        try:
            description = fetch_description(url)
            if code not in enriched_data:
                enriched_data[code] = {}
            enriched_data[code]["job_description"] = description
            filled_count += 1
            print(f"  {description[:80]}..." if len(description) > 80 else f"  {description}")
        except Exception as e:
            print(f"  ERROR: {e}")
            if code not in enriched_data:
                enriched_data[code] = {}
            enriched_data[code]["job_description"] = ""

        # Save cache after each fetch
        with open(CACHE_FILE, "w") as f:
            json.dump(enriched_data, f, indent=2)

        time.sleep(DELAY)

    print(f"\nDone!")
    print(f"  Filled: {filled_count} descriptions")
    print(f"  Skipped (already filled): {skipped_count}")

    # Now update the output CSV with descriptions
    print(f"\nUpdating {OUTPUT_CSV}...")
    rows_out = []
    with open(OUTPUT_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames

        for row in reader:
            code = row["Code"]
            if code in enriched_data:
                row["Job Description"] = enriched_data[code].get("job_description", "")
            rows_out.append(row)

    # Add Job Description to fieldnames if not present
    if "Job Description" not in fieldnames:
        fieldnames = list(fieldnames) + ["Job Description"]

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows_out)

    print(f"✓ Updated output CSV with {filled_count} job descriptions")


if __name__ == "__main__":
    main()
