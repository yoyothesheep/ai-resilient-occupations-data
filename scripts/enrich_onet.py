#!/usr/bin/env python3
"""
Enrich O*NET occupations CSV with wage, projected growth, and projected job openings
scraped from onetonline.org.

Uses a JSON cache for resumability if interrupted.
Outputs to intermediate and output CSV files in the data directory.
"""

import csv
import json
import re
import time
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

INPUT_CSV = Path(__file__).parent.parent / "data" / "input" / "All_Occupations_ONET.csv"
CACHE_FILE = Path(__file__).parent.parent / "data" / "intermediate" / "onet_enrichment_cache.json"
ENRICHMENT_ONLY_CSV = Path(__file__).parent.parent / "data" / "intermediate" / "onet_enrichment.csv"
ENRICHED_CSV = Path(__file__).parent.parent / "data" / "intermediate" / "All_Occupations_ONET_enriched.csv"

HEADERS = {"User-Agent": "Mozilla/5.0 (research project)"}
DELAY = 1.0  # seconds between requests to be polite


class OnetPageParser(HTMLParser):
    """Extract wage, growth, job openings, and education from an O*NET summary page."""

    def __init__(self):
        super().__init__()
        self._in_dt = False
        self._in_dd = False
        self._current_field = None
        self._capture = False
        self._text_buf = []
        self._in_education_list = False
        self._education_items = []

        self.median_wage = None
        self.projected_growth = None
        self.projected_job_openings = None
        self.education_top_2 = None  # Store top 2 education responses with %
        self.education_description = None  # Store descriptive education text (alternate format)

    def handle_starttag(self, tag, attrs):
        if tag == "dt":
            self._in_dt = True
            self._text_buf = []
        elif tag == "dd" and self._current_field:
            self._in_dd = True
            self._capture = True
            self._text_buf = []
        elif tag == "li" and self._in_education_list:
            # Starting a list item in education section
            self._text_buf = []

    def handle_endtag(self, tag):
        if tag == "dt":
            self._in_dt = False
            dt_text = "".join(self._text_buf).strip()
            if "Median wages" in dt_text:
                self._current_field = "wage"
            elif "Projected growth" in dt_text:
                self._current_field = "growth"
            elif "Projected job openings" in dt_text:
                self._current_field = "openings"
            elif dt_text == "Education":
                self._current_field = "education"
            else:
                self._current_field = None
        elif tag == "dd" and self._capture:
            self._in_dd = False
            self._capture = False
            dd_text = "".join(self._text_buf).strip()
            # Clean up whitespace
            dd_text = re.sub(r"\s+", " ", dd_text).strip()

            if self._current_field == "wage":
                self.median_wage = dd_text
            elif self._current_field == "growth":
                self.projected_growth = dd_text
            elif self._current_field == "openings":
                self.projected_job_openings = dd_text
            elif self._current_field == "education":
                self.education_description = dd_text

            self._current_field = None
        elif tag == "li" and self._in_education_list:
            # End of education list item
            li_text = "".join(self._text_buf).strip()
            if li_text and "%" in li_text:
                self._education_items.append(li_text)

    def handle_data(self, data):
        if self._in_dt or self._capture:
            self._text_buf.append(data)
        elif self._in_education_list:
            self._text_buf.append(data)

        # Detect when we're in education section
        if "How much education does a new hire need" in data or "Respondents said" in data:
            self._in_education_list = True

    def finalize_education(self):
        """Extract top 2 education responses after parsing is complete."""
        # If we have the standard format (with percentages), use that
        if self._education_items:
            # Clean and format each item
            cleaned_items = []
            for item in self._education_items:
                cleaned = self._clean_education_item(item)
                if cleaned:
                    cleaned_items.append(cleaned)

            # Sort by percentage (descending) and take top 2
            sorted_items = sorted(
                cleaned_items,
                key=lambda x: self._extract_percentage(x),
                reverse=True
            )
            self.education_top_2 = " | ".join(sorted_items[:2]) if sorted_items else ""

        # If we have the alternate format (descriptive text), extract degree level
        elif self.education_description:
            level = self._extract_degree_from_description(self.education_description)
            if level:
                self.education_top_2 = level  # Store without percentage

    @staticmethod
    def _extract_percentage(text):
        """Extract numeric percentage from text like '63% High school diploma'."""
        match = re.search(r"(\d+)\s*%", text)
        return int(match.group(1)) if match else 0

    @staticmethod
    def _clean_education_item(text):
        """Clean education item text to extract percentage and level."""
        # Clean whitespace
        text = re.sub(r"\s+", " ", text).strip()
        # Remove common artifacts
        text = text.replace("requiredmore info", "")
        text = text.replace("required", "").strip()
        text = text.replace("responded:", "").strip()
        # Extract percentage and education level
        match = re.search(r"(\d+)\s*%\s*(.*)", text)
        if match:
            pct = match.group(1)
            level = match.group(2).strip()
            return f"{pct}% {level}" if level else f"{pct}%"
        return ""

    @staticmethod
    def _extract_degree_from_description(text):
        """Extract degree level from descriptive education text.

        Example inputs:
        - "Most of these occupations require a four-year bachelor's degree, but some do not."
        - "A high school diploma is typically required."

        Returns the first matching degree level found, without percentage.
        """
        text_lower = text.lower()

        # Check for specific degree mentions (in order of preference)
        degree_patterns = [
            ("doctoral degree", "Doctoral degree"),
            ("phd", "Doctoral degree"),
            ("doctor of", "Doctoral degree"),
            ("master's degree", "Master's degree"),
            ("master degree", "Master's degree"),
            ("post-baccalaureate", "Post-baccalaureate certificate"),
            ("postbaccalaureate", "Post-baccalaureate certificate"),
            ("bachelor's degree", "Bachelor's degree"),
            ("bachelor degree", "Bachelor's degree"),
            ("associate's degree", "Associate's degree"),
            ("associate degree", "Associate's degree"),
            ("high school diploma", "High school diploma"),
            ("high school", "High school diploma"),
            ("secondary school", "High school diploma"),
            ("less than high school", "Less than high school diploma"),
        ]

        for pattern, level in degree_patterns:
            if pattern in text_lower:
                return level

        return ""


def extract_top_education(education_str: str) -> tuple:
    """
    Extract top education level and rate from education string.

    Handles two formats:
    1. Standard format: "63% High school diploma | 20% Some college"
       Output: ("High school diploma", "63%")
    2. Alternate format (no percentage): "Bachelor's degree"
       Output: ("Bachelor's degree", "")
    """
    if not education_str:
        return ("", "")

    # Standard format with pipe separator
    if "|" in education_str:
        # Get the first item (highest percentage)
        first_item = education_str.split("|")[0].strip()
        # Parse percentage and level
        match = re.match(r"(\d+%)\s+(.*)", first_item)
        if match:
            rate = match.group(1)
            level = match.group(2)
            return (level, rate)

    # Alternate format (no pipe, just education level, no percentage)
    else:
        # It's just an education level without percentage
        return (education_str.strip(), "")

    return ("", "")


def fetch_onet_data(url: str) -> dict:
    """Fetch and parse a single O*NET occupation page."""
    req = urllib.request.Request(url, headers=HEADERS)
    resp = urllib.request.urlopen(req, timeout=30)
    html = resp.read().decode("utf-8", errors="replace")

    parser = OnetPageParser()
    parser.feed(html)
    parser.finalize_education()

    education_top_2 = parser.education_top_2 or ""
    top_level, top_rate = extract_top_education(education_top_2)

    return {
        "median_wage": parser.median_wage or "",
        "projected_growth": parser.projected_growth or "",
        "projected_job_openings": parser.projected_job_openings or "",
        "education_top_2": education_top_2,
        "top_education_level": top_level,
        "top_education_rate": top_rate,
    }


def main():
    # Create output directories
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    ENRICHMENT_ONLY_CSV.parent.mkdir(parents=True, exist_ok=True)
    ENRICHED_CSV.parent.mkdir(parents=True, exist_ok=True)

    # Load cache if it exists
    enriched_data = {}
    if CACHE_FILE.exists():
        with open(CACHE_FILE) as f:
            enriched_data = json.load(f)

    # Read input CSV
    with open(INPUT_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    total = len(rows)
    cached_count = sum(1 for r in rows if r["Code"] in enriched_data)
    print(f"Total occupations: {total}, already cached: {cached_count}")

    # Fetch data for occupations not in cache
    for i, row in enumerate(rows):
        code = row["Code"]
        if code in enriched_data:
            continue

        url = row["url"]
        print(f"[{i+1}/{total}] Fetching {code} - {row['Occupation']}...")
        try:
            data = fetch_onet_data(url)
            enriched_data[code] = data
            print(f"  Wage: {data['median_wage']}")
            print(f"  Growth: {data['projected_growth']}")
            print(f"  Openings: {data['projected_job_openings']}")
            print(f"  Education (top 2): {data['education_top_2']}")
            if data['top_education_level']:
                print(f"  Top Education: {data['top_education_rate']} {data['top_education_level']}")
        except Exception as e:
            print(f"  ERROR: {e}")
            enriched_data[code] = {
                "median_wage": "",
                "projected_growth": "",
                "projected_job_openings": "",
                "education_top_2": "",
                "top_education_level": "",
                "top_education_rate": "",
            }

        # Save cache after each fetch for resumability
        with open(CACHE_FILE, "w") as f:
            json.dump(enriched_data, f, indent=2)

        time.sleep(DELAY)

    # Write enriched CSV (avoid duplicating columns if already enriched)
    enrichment_cols = ["Median Wage", "Projected Growth", "Projected Job Openings", "Education", "Top Education Level", "Top Education Rate"]
    existing = list(rows[0].keys())
    fieldnames = existing + [c for c in enrichment_cols if c not in existing]

    # Write enrichment-only CSV (just the new fields)
    enrichment_fieldnames = ["Code", "Median Wage", "Projected Growth", "Projected Job Openings", "Education", "Top Education Level", "Top Education Rate"]
    with open(ENRICHMENT_ONLY_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=enrichment_fieldnames)
        writer.writeheader()
        for row in rows:
            code = row["Code"]
            enriched = enriched_data.get(code, {})
            writer.writerow({
                "Code": code,
                "Median Wage": enriched.get("median_wage", ""),
                "Projected Growth": enriched.get("projected_growth", ""),
                "Projected Job Openings": enriched.get("projected_job_openings", ""),
                "Education": enriched.get("education_top_2", ""),
                "Top Education Level": enriched.get("top_education_level", ""),
                "Top Education Rate": enriched.get("top_education_rate", ""),
            })

    # Write fully enriched CSV (all original columns + enrichment)
    with open(ENRICHED_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            code = row["Code"]
            enriched = enriched_data.get(code, {})
            row["Median Wage"] = enriched.get("median_wage", "")
            row["Projected Growth"] = enriched.get("projected_growth", "")
            row["Projected Job Openings"] = enriched.get("projected_job_openings", "")
            row["Education"] = enriched.get("education_top_2", "")
            row["Top Education Level"] = enriched.get("top_education_level", "")
            row["Top Education Rate"] = enriched.get("top_education_rate", "")
            writer.writerow(row)

    print(f"\nDone!")
    print(f"  Enrichment fields only: {ENRICHMENT_ONLY_CSV}")
    print(f"  Fully enriched CSV: {ENRICHED_CSV}")


if __name__ == "__main__":
    main()
