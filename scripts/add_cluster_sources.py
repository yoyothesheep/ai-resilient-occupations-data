#!/usr/bin/env python3
"""
Generate and append industry-specific sources for a cluster to approved_sources.md.

Uses Claude to research authoritative sources for the cluster's occupation domain,
then appends a new section to docs/approved_sources.md.

Usage:
    python3 scripts/add_cluster_sources.py --cluster <cluster_id>
    python3 scripts/add_cluster_sources.py --cluster healthcare --force
"""

import anthropic
import argparse
import csv
import re
import sys

# ── Config ────────────────────────────────────────────────────────────────────
CLUSTER_ROLES_CSV = "data/career_clusters/cluster_roles.csv"
CLUSTERS_CSV      = "data/career_clusters/clusters.csv"
SCORES_CSV        = "data/output/ai_resilience_scores.csv"
APPROVED_SOURCES  = "docs/approved_sources.md"

MODEL      = "claude-sonnet-4-6"
MAX_TOKENS = 1024


# ── Loaders ───────────────────────────────────────────────────────────────────

def load_cluster_meta(cluster_id: str) -> dict:
    with open(CLUSTERS_CSV, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["cluster_id"] == cluster_id:
                return r
    return {}


def load_cluster_members(cluster_id: str) -> list[dict]:
    members = []
    with open(CLUSTER_ROLES_CSV, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["cluster_id"] == cluster_id:
                members.append(r)
    members.sort(key=lambda r: int(r.get("level", 99)))
    return members


def load_occupations(members: list[dict]) -> list[str]:
    codes = {m["onet_code"] for m in members}
    titles = []
    with open(SCORES_CSV, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["Code"] in codes:
                simple = r.get("altpath simple title", "").strip()
                titles.append(simple if simple else r["Title"])
    return titles


def section_exists(cluster_name: str) -> bool:
    with open(APPROVED_SOURCES, encoding="utf-8") as f:
        content = f.read()
    # Check for an existing section heading for this cluster
    heading = f"## {cluster_name}"
    return heading in content


# ── Prompt ────────────────────────────────────────────────────────────────────

def build_prompt(cluster_name: str, occupations: list[str]) -> str:
    occ_list = "\n".join(f"- {t}" for t in occupations)

    return f"""You are curating authoritative sources for a career intelligence site (ai-proof-careers.com).

We need a list of 6–10 industry-specific sources for the "{cluster_name}" career cluster, covering these occupations:
{occ_list}

These sources will be used by writers generating career page content about AI's impact on jobs. The sources must:
- Be real, named publications or annual reports with verifiable URLs (no paywalled analyst firms)
- Contain data, surveys, or research — NOT editorial opinion or vendor marketing
- Be relevant to tracking AI impact, hiring trends, job posting shifts, practitioner adoption, or skill demand in this domain
- Prioritize: annual practitioner surveys, government/association data, academic/think tank research, industry trade associations

BANNED sources (already covered by universal list or too low quality):
- Gartner, IDC, Forrester, MarketsandMarkets — paywalled, inflated projections
- Forbes contributor network, The New Stack, LinkedIn Learning blog
- Vendor blogs (e.g. Salesforce blog ≠ Salesforce State of Sales *report*)
- Career advice sites, Glassdoor editorial, Indeed editorial
- Generic AI sources already in our universal list (WEF, McKinsey, MIT Tech Review, BLS)

Format your response as a markdown section ONLY — no preamble, no explanation. Use this exact format:

## {cluster_name}

- **Source Name** — description of what data it contains and why it's useful for this cluster
- **Source Name** — description
[...continue for all sources]

Each line must name a specific, real publication. Include the type of data in the description (e.g. "annual practitioner survey", "job posting analytics", "industry salary benchmarks").
"""


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Add cluster-specific sources to approved_sources.md")
    parser.add_argument("--cluster", required=True, help="Cluster ID (e.g. healthcare)")
    parser.add_argument("--force", action="store_true", help="Overwrite existing section if present")
    parser.add_argument("--inline", action="store_true", help="Print prompt and read section from stdin (no API)")
    args = parser.parse_args()

    cluster_id = args.cluster

    meta = load_cluster_meta(cluster_id)
    if not meta:
        print(f"✗ Cluster '{cluster_id}' not found in clusters.csv")
        sys.exit(1)

    cluster_name = meta.get("cluster_name", cluster_id.replace("-", " ").title())
    members = load_cluster_members(cluster_id)
    if not members:
        print(f"✗ No roles found for cluster '{cluster_id}'")
        sys.exit(1)

    occupations = load_occupations(members)

    if section_exists(cluster_name) and not args.force:
        print(f"✓ Section '{cluster_name}' already exists in approved_sources.md (use --force to overwrite)")
        sys.exit(0)

    print(f"Generating sources for '{cluster_name}' ({len(occupations)} occupations)...")

    prompt = build_prompt(cluster_name, occupations)

    if args.inline:
        print("\n" + "="*80)
        print(prompt)
        print("="*80)
        print(f"\nPaste the markdown section below (## {cluster_name} heading + bullet list),")
        print("then press Enter + Ctrl-D:")
        try:
            section = sys.stdin.read().strip()
        except KeyboardInterrupt:
            print("\nAborted.")
            sys.exit(130)
    else:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        section = response.content[0].text.strip()

    # Ensure it starts with the expected heading
    if not section.startswith(f"## {cluster_name}"):
        section = f"## {cluster_name}\n\n" + section

    # If --force, replace existing section; otherwise append
    with open(APPROVED_SOURCES, encoding="utf-8") as f:
        content = f.read()

    if args.force and f"## {cluster_name}" in content:
        # Replace from this heading to the next ## heading (or EOF)
        pattern = rf"(## {re.escape(cluster_name)}.*?)(?=\n## |\Z)"
        content = re.sub(pattern, section, content, flags=re.DOTALL)
        print(f"  → Replaced existing section")
    else:
        # Find insertion point: before "## Avoid" section, or append at end
        avoid_marker = "\n## Avoid"
        if avoid_marker in content:
            idx = content.index(avoid_marker)
            content = content[:idx] + "\n" + section + "\n" + content[idx:]
        else:
            content = content.rstrip() + "\n\n" + section + "\n"
        print(f"  → Appended new section")

    with open(APPROVED_SOURCES, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"\n✓ {APPROVED_SOURCES} updated")
    print(f"\nGenerated section:\n{'-'*60}")
    print(section)


if __name__ == "__main__":
    main()
