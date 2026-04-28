#!/usr/bin/env python3
"""
Generate industry page files from cluster data.

Writes two files to the site repo:
  src/data/industries/<slug>.ts        — cluster data export
  app/industry/<slug>/page.tsx         — Next.js route (full component)

Description is generated via Claude API, summarizing the cluster's AI resilience
landscape across all member occupations.

Usage:
    python3 scripts/generate_industry_page.py --cluster sales
    python3 scripts/generate_industry_page.py --cluster sales --force
"""

import anthropic
import argparse
import csv
import os
import re
import sys

# ── Config ────────────────────────────────────────────────────────────────────
from loaders import load_scores, SCORES_CSV, CLUSTER_ROLES as CLUSTER_ROLES_CSV
CLUSTERS_CSV      = "data/career_clusters/clusters.csv"
CARDS_DIR         = "data/output/cards"
TONE_GUIDE        = "docs/tone_guide_career_pages.md"
SITE_DIR          = "../ai-resilient-occupations-site"
INDUSTRIES_DIR    = os.path.join(SITE_DIR, "src/data/industries")
INDUSTRY_ROUTE    = os.path.join(SITE_DIR, "app/industry")

MODEL      = "claude-haiku-4-5-20251001"
MAX_TOKENS = 256


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


# load_scores() imported from loaders.py above.


# ── Slug helpers ──────────────────────────────────────────────────────────────

def title_to_slug(title: str) -> str:
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug.strip())
    slug = re.sub(r"-+", "-", slug)
    return slug


def career_slug(onet_code: str, occupation: str, scores: dict) -> str:
    simple = scores.get(onet_code, {}).get("altpath simple title", "").strip()
    return title_to_slug(simple if simple else occupation)


def cluster_to_const(cluster_id: str) -> str:
    """Convert cluster_id to SCREAMING_SNAKE_CASE constant name."""
    return cluster_id.upper().replace("-", "_") + "_CLUSTER"


def cluster_to_component(cluster_name: str) -> str:
    """Convert cluster name to PascalCase component name."""
    words = re.sub(r"[^a-zA-Z0-9\s]", "", cluster_name).split()
    return "".join(w.capitalize() for w in words) + "IndustryPage"


def cluster_to_data_slug(cluster_id: str, cluster_name: str) -> str:
    """Industry page URL slug — prefer cluster_id style."""
    return title_to_slug(cluster_name)


# ── Description generation ────────────────────────────────────────────────────

def generate_description(client: anthropic.Anthropic, cluster_name: str,
                         careers: list[dict], tone_guide: str, is_inline: bool = False) -> str:
    """Generate a 1-2 sentence description summarizing AI impact across the cluster."""
    career_lines = "\n".join(
        f"- {c['title']} (AI resilience tier {c['score']}/100, growth {c['growth']}, level {c['level']})"
        for c in careers
    )

    prompt = f"""You are writing a 1-2 sentence description for the "{cluster_name}" career cluster page on ai-proof-careers.com.

=== TONE GUIDE ===
{tone_guide}

=== END TONE GUIDE ===

You are writing a 1-2 sentence description for the "{cluster_name}" career cluster page on ai-proof-careers.com.

The cluster includes these occupations (AI resilience tier = how protected the role is from AI disruption, higher tier = more protected):
{career_lines}

Write 1-2 plain sentences that summarize the AI landscape for this cluster. Describe where the pressure is highest and where it is lowest, in plain human terms. Name the actual pattern: what kinds of work are more exposed vs. more protected.

Rules:
- NEVER mention scores, numbers, ratings, or percentages. No "39/100", no "62%", nothing like that.
- No em dashes. Use commas or short sentences instead.
- No jargon: no "future-proof", "upskill", "leverage", "resilience", "compression", "disruption"
- Write about the jobs, not the reader. Third person.
- Short, plain language. A high schooler should understand it immediately.
- Hard limit: 35 words or fewer. Count carefully.
- Do NOT reference scores or rankings to make a point. Describe the work itself.

Good example (31 words): "Routine transactional sales work is the most exposed to AI, while roles built around complex client relationships and technical judgment hold up better. Growth is concentrated at the senior end."

Respond ONLY with the description text. No preamble, no quotes around the output."""

    if is_inline:
        print("\n" + "="*80)
        print(prompt)
        print("="*80 + "\n")
        print("Paste the description text below, then press Enter + Ctrl-D:")
        try:
            return sys.stdin.read().strip()
        except KeyboardInterrupt:
            print("\nAborted.")
            sys.exit(130)

    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


# ── File generation ───────────────────────────────────────────────────────────

def generate_data_file(cluster_id: str, cluster_name: str, description: str,
                       careers: list[dict], const_name: str) -> str:
    career_lines = []
    current_level = None
    level_labels = {1: "Entry", 2: "Mid-Level", 3: "Senior", 4: "Lead or Specialist", 5: "Principal"}

    for c in careers:
        lvl = c["level"]
        if lvl != current_level:
            current_level = lvl
            career_lines.append(f"    // Level {lvl} — {level_labels.get(lvl, '')}")
        career_lines.append(
            f'    {{ title: "{c["title"]}", slug: "{c["slug"]}", '
            f'score: {c["score"]}, growth: "{c["growth"]}", openings: "{c["openings"]}", level: {lvl} }},'
        )

    careers_block = "\n".join(career_lines)

    return f"""export type IndustryCareer = {{
  title: string;
  slug: string;
  score: number;
  growth: string;
  openings: string;
  level: 1 | 2 | 3 | 4 | 5;
}};

export const LEVEL_LABELS: Record<number, string> = {{
  1: "Entry",
  2: "Mid-Level",
  3: "Senior",
  4: "Lead or Specialist",
  5: "Principal",
}};

export const {const_name} = {{
  name: "{cluster_name}",
  description:
    "{description}",
  careers: [
{careers_block}
  ] satisfies IndustryCareer[],
}};
"""


def generate_route_file(cluster_name: str, page_slug: str, const_name: str,
                        data_slug: str, component_name: str) -> str:
    title = f"{cluster_name} Careers: AI Resilience Guide"
    meta_desc = (
        f"Compare {cluster_name.lower()} careers by AI resilience, growth, and career level"
        " — from entry-level to principal roles."
    )
    canonical = f"https://www.ai-proof-careers.com/industry/{page_slug}"

    lines = [
        'import { Metadata } from "next";',
        f'import {{ IndustryPageLayout }} from "@/components/IndustryPageLayout";',
        f'import {{ {const_name} }} from "@/data/industries/{data_slug}";',
        "",
        "export const metadata: Metadata = {",
        f'  title: "{title}",',
        f'  description: "{meta_desc}",',
        f'  alternates: {{ canonical: "{canonical}" }},',
        "  openGraph: {",
        '    type: "website",',
        f'    title: "{title}",',
        f'    description: "{meta_desc}",',
        f'    url: "{canonical}",',
        '    images: ["/career-guides-thumbnail.png"],',
        "  },",
        "  twitter: {",
        '    card: "summary_large_image",',
        f'    title: "{title}",',
        f'    description: "{meta_desc}",',
        '    images: ["/career-guides-thumbnail.png"],',
        "  },",
        "};",
        "",
        f"export default function {component_name}() {{",
        "  return (",
        "    <IndustryPageLayout",
        f'      cluster={{{const_name}}}',
        "      meta={{",
        f'        title: "{title}",',
        f'        description: "{meta_desc}",',
        f'        canonical: "{canonical}",',
        "      }}",
        "    />",
        "  );",
        "}",
        "",
    ]
    return "\n".join(lines)



# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate industry page for a career cluster")
    parser.add_argument("--cluster", required=True, help="Cluster ID (e.g. sales)")
    parser.add_argument("--force", action="store_true", help="Overwrite existing files")
    parser.add_argument("--inline", action="store_true", help="Run interactively via stdin without API")
    args = parser.parse_args()

    cluster_id = args.cluster

    print("Loading data...")
    scores = load_scores()
    with open(TONE_GUIDE, encoding="utf-8") as f:
        tone_guide = f.read()
    meta = load_cluster_meta(cluster_id)
    members = load_cluster_members(cluster_id)

    if not members:
        print(f"✗ No roles found for cluster '{cluster_id}'")
        sys.exit(1)

    cluster_name = meta.get("cluster_name", cluster_id.replace("-", " ").title())
    const_name = cluster_to_const(cluster_id)
    data_slug = cluster_to_data_slug(cluster_id, cluster_name)
    page_slug = data_slug
    component_name = cluster_to_component(cluster_name)

    data_path = os.path.join(INDUSTRIES_DIR, f"{data_slug}.ts")
    route_dir = os.path.join(INDUSTRY_ROUTE, page_slug)
    route_path = os.path.join(route_dir, "page.tsx")

    if not args.force and os.path.exists(data_path):
        print(f"✓ Already exists: {data_slug} (use --force to overwrite)")
        sys.exit(0)

    # Build careers list
    careers = []
    for m in members:
        code = m["onet_code"]
        occ = scores.get(code, {})
        slug = career_slug(code, m["occupation"], scores)

        # Parse growth — same logic as generate_next_steps.py
        _GROWTH_LABEL_MAP = [
            ("Much faster than average", "+7%"),
            ("Faster than average",      "+5%"),
            ("Average",                  "+3%"),
            ("Slower than average",      "+1%"),
            ("Little or no change",      "0%"),
            ("Decline",                  "-1%"),
        ]
        growth_raw = occ.get("Employment Change, 2024-2034", "").strip()
        if growth_raw:
            try:
                pct_f = float(growth_raw)
                rounded = round(pct_f)
                growth_str = f"+{rounded}%" if rounded > 0 else ("0%" if rounded == 0 else f"{rounded}%")
            except ValueError:
                growth_str = "N/A"
        else:
            pg = occ.get("Projected Growth", "").strip()
            growth_str = pg
            for key, label in _GROWTH_LABEL_MAP:
                if pg.startswith(key):
                    growth_str = label
                    break

        openings = occ.get("Projected Job Openings", "")
        try:
            openings_str = f"{int(float(openings.replace(',', ''))):,}" if openings else "N/A"
        except (ValueError, TypeError):
            openings_str = openings or "N/A"

        score_raw = occ.get("final_ranking", "0")
        try:
            score_int = round(float(score_raw) * 100)
        except (ValueError, TypeError):
            score_int = 0

        simple_title = occ.get("altpath simple title", "").strip()
        careers.append({
            "title": simple_title if simple_title else m["occupation"],
            "slug": slug,
            "score": score_int,
            "growth": growth_str,
            "openings": openings_str,
            "level": int(m.get("level", 1)),
        })

    # Generate description via Claude or inline
    print(f"\nGenerating description for '{cluster_name}' cluster...")
    if args.inline:
        description = generate_description(None, cluster_name, careers, tone_guide, is_inline=True)
        print(f"  → {description}")
    else:
        try:
            client = anthropic.Anthropic()
            description = generate_description(client, cluster_name, careers, tone_guide, is_inline=False)
            print(f"  → {description}")
        except Exception as e:
            print(f"  ✗ Claude API error: {e}")
            print("  Falling back to inline mode...")
            description = generate_description(None, cluster_name, careers, tone_guide, is_inline=True)
            print(f"  → {description}")

    # Write files
    data_content = generate_data_file(cluster_id, cluster_name, description, careers, const_name)
    route_content = generate_route_file(cluster_name, page_slug, const_name, data_slug, component_name)

    try:
        os.makedirs(INDUSTRIES_DIR, exist_ok=True)
    except FileExistsError:
        pass

    try:
        os.makedirs(route_dir, exist_ok=True)
    except FileExistsError:
        pass

    with open(data_path, "w", encoding="utf-8") as f:
        f.write(data_content)
    with open(route_path, "w", encoding="utf-8") as f:
        f.write(route_content)

    print(f"\n  ✓ {data_path}")
    print(f"  ✓ {route_path}")
    print("\n✓ Done")


if __name__ == "__main__":
    main()
