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
CLUSTER_ROLES_CSV = "data/career_clusters/cluster_roles.csv"
CLUSTERS_CSV      = "data/career_clusters/clusters.csv"
SCORES_CSV        = "data/output/ai_resilience_scores.csv"
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


def load_scores() -> dict:
    scores = {}
    with open(SCORES_CSV, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            scores[r["Code"]] = r
    return scores


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
                         careers: list[dict], tone_guide: str) -> str:
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

Write 1-2 plain sentences that summarize the AI landscape for this cluster. Describe where the pressure is highest and where it is lowest, in plain human terms. Name the actual pattern — what kinds of work are more exposed vs. more protected.

Rules:
- NEVER mention scores, numbers, ratings, or percentages. No "39/100", no "62%", nothing like that.
- No em dashes. Use commas or short sentences instead.
- No jargon: no "future-proof", "upskill", "leverage", "resilience"
- Write about the jobs, not the reader. Third person.
- Short, plain language. A high schooler should get it immediately.
- Under 40 words.

Good example: "Routine transactional sales work is the most exposed to AI, while roles built around complex relationships and technical judgment hold up better. Growth is concentrated at the senior end of the ladder."

Respond ONLY with the description, no preamble."""

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
    level_labels = {1: "Entry", 2: "Mid-Level", 3: "Senior", 4: "Lead / Specialist", 5: "Principal"}

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
  4: "Lead / Specialist",
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
    # Short display name for h1 (split on & or first word)
    h1_jsx = cluster_name.replace(" & ", " &amp; ")

    career_count = f"{{{{{{const_name}}.careers.length}}}}"
    title = f"{cluster_name} Careers: AI Resilience Guide"
    meta_desc = f"Compare {cluster_name.lower()} careers by AI resilience, growth, and career level — from entry-level to senior specialist roles."
    canonical = f"https://ai-proof-careers.com/industry/{page_slug}"

    return f'''"use client";

import {{ useState }} from "react";
import Link from "next/link";
import {{ {const_name}, LEVEL_LABELS, type IndustryCareer }} from "@/data/industries/{data_slug}";
import {{ getTier }} from "@/lib/careerUtils";
import {{ ArrowLeft }} from "lucide-react";
import {{ usePageMeta }} from "@/hooks/usePageMeta";

const TIER_BG: Record<string, string> = {{
  Strong:   `${{`#225560`}}0f`,
  Solid:    `${{`#5a9a6e`}}0f`,
  Shifting: `${{`#d97706`}}0f`,
  Exposed:  `${{`#ea580c`}}0f`,
  Risky:    `${{`#dc2626`}}0f`,
}};

type LevelFilter = "all" | 1 | 2 | 3 | 4 | 5;
type SortBy = "score" | "level";

const FILTER_TABS: {{ label: string; value: LevelFilter }}[] = [
  {{ label: "All Levels",      value: "all" }},
  {{ label: "Entry",           value: 1 }},
  {{ label: "Mid-Level",       value: 2 }},
  {{ label: "Senior",          value: 3 }},
  {{ label: "Lead",            value: 4 }},
  {{ label: "Principal",       value: 5 }},
];

function CareerCard({{ career }}: {{ career: IndustryCareer }}) {{
  const tier = getTier(career.score);
  const tierBg = TIER_BG[tier.label] ?? "#f5f5f5";

  return (
    <Link
      href={{`/career/${{career.slug}}`}}
      className="group flex items-center justify-between gap-6 rounded-2xl px-6 py-5 bg-white border border-border hover:border-foreground/20 hover:shadow-md transition-all duration-150"
    >
      <div className="flex-1 min-w-0">
        <h3 className="text-base font-extrabold text-foreground uppercase tracking-tight leading-none mb-2.5 truncate">
          {{career.title}}
        </h3>
        <div className="flex items-center gap-2 flex-wrap">
          <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-widest bg-white border border-border text-foreground/70">
            {{LEVEL_LABELS[career.level]}}
          </span>
          <span
            className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-extrabold uppercase tracking-widest border"
            style={{{{ color: tier.color, borderColor: `${{tier.color}}30`, background: tierBg }}}}
          >
            <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{{{ background: tier.color }}}} />
            {{tier.label}}
          </span>
        </div>
      </div>

      <div className="hidden sm:flex items-center gap-8 text-right shrink-0">
        <div className="flex flex-col gap-0.5 min-w-[80px]">
          <span className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground">Growth</span>
          <span
            className="text-sm font-black tabular-nums"
            style={{{{ color: career.growth.startsWith("+") && career.growth !== "+0%" ? "#225560" : "#ea580c" }}}}
          >
            {{career.growth}}
          </span>
        </div>
        <div className="flex flex-col gap-0.5 min-w-[100px]">
          <span className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground">Openings/yr</span>
          <span className="text-sm font-black tabular-nums text-foreground">{{career.openings}}</span>
        </div>
      </div>

      <div className="w-8 h-8 rounded-full bg-white border border-border flex items-center justify-center shrink-0 transition-transform duration-150 group-hover:translate-x-0.5 shadow-sm">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M5 12h14M12 5l7 7-7 7" />
        </svg>
      </div>
    </Link>
  );
}}

export default function {component_name}() {{
  usePageMeta({{
    title: "{title}",
    description: "{meta_desc}",
    canonical: "{canonical}",
  }});

  const [activeFilter, setActiveFilter] = useState<LevelFilter>("all");
  const [sortBy, setSortBy] = useState<SortBy>("score");

  const filtered = {const_name}.careers
    .filter((c) => activeFilter === "all" || c.level === activeFilter)
    .sort((a, b) =>
      sortBy === "score" ? b.score - a.score : b.level - a.level || b.score - a.score
    );

  return (
    <div className="min-h-screen px-3 md:px-6 lg:px-10 py-6">
      <div className="bg-background rounded-2xl md:rounded-3xl border border-border shadow-lg overflow-hidden flex flex-col lg:flex-row min-h-[calc(100vh-3rem)]">

        <aside className="hidden lg:flex lg:w-[340px] lg:shrink-0 lg:border-r border-border flex-col px-8 py-10 fixed top-6 bottom-6 overflow-y-auto" style={{{{ width: 340 }}}}>
          <Link
            href="/"
            className="inline-flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground/70 hover:text-foreground transition-colors group mb-10"
          >
            <ArrowLeft className="w-3.5 h-3.5 transition-transform group-hover:-translate-x-0.5" />
            Home
          </Link>

          <h1 className="text-4xl font-extrabold uppercase leading-[0.95] tracking-tight mb-4">
            {h1_jsx}
          </h1>

          <p className="text-sm text-muted-foreground leading-relaxed mb-2">
            {{{const_name}.description}}
          </p>

          <p className="text-sm text-muted-foreground leading-relaxed mb-2">
            Explore the career pages to see how AI is affecting each role, what skills to build, and how to navigate your next move.
          </p>

          <nav className="flex flex-col gap-1 mt-auto pt-6 border-t border-border">
            {{FILTER_TABS.map((tab) => {{
              const count = tab.value === "all"
                ? {const_name}.careers.length
                : {const_name}.careers.filter(c => c.level === tab.value).length;
              return (
                <button
                  key={{tab.value}}
                  onClick={{() => setActiveFilter(tab.value)}}
                  className="flex items-center justify-between text-left text-sm font-medium hover:text-foreground rounded-md px-2 py-0.5 -mx-2 hover:bg-foreground/10"
                  style={{{{ color: activeFilter === tab.value ? "hsl(var(--foreground))" : "hsl(var(--muted-foreground))", background: activeFilter === tab.value ? "hsl(var(--foreground) / 0.1)" : undefined, border: "none", cursor: "pointer" }}}}
                >
                  <span>{{tab.label}}</span>
                  <span className="text-[10px] font-bold tabular-nums" style={{{{ color: "hsl(var(--muted-foreground)/0.5)" }}}}>{{count}}</span>
                </button>
              );
            }})}}
          </nav>
        </aside>

        <main className="flex-1 min-w-0 px-6 lg:px-10 py-8 lg:ml-[340px]">

          <div className="lg:hidden flex gap-2 overflow-x-auto pb-2 mb-6">
            {{FILTER_TABS.map((tab) => (
              <button
                key={{tab.value}}
                onClick={{() => setActiveFilter(tab.value)}}
                className="shrink-0 px-3.5 py-1.5 rounded-full text-xs font-semibold transition-all duration-150 border"
                style={{{{
                  backgroundColor: activeFilter === tab.value ? "hsl(var(--foreground))" : "transparent",
                  color: activeFilter === tab.value ? "hsl(var(--background))" : "hsl(var(--muted-foreground))",
                  borderColor: activeFilter === tab.value ? "hsl(var(--foreground))" : "hsl(var(--border))",
                  cursor: "pointer",
                }}}}
              >
                {{tab.label}}
              </button>
            ))}}
          </div>

          <div className="flex items-center justify-between mb-5">
            <span className="text-xs text-muted-foreground">
              {{filtered.length}} career{{filtered.length !== 1 ? "s" : ""}}
            </span>
            <button
              onClick={{() => setSortBy(s => s === "score" ? "level" : "score")}}
              className="inline-flex items-center gap-1.5 text-xs font-semibold text-muted-foreground hover:text-foreground transition-colors px-3 py-1.5 rounded-full border border-border bg-secondary hover:bg-muted cursor-pointer"
            >
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M3 6h18M7 12h10M11 18h2" />
              </svg>
              Sort: {{sortBy === "score" ? "Resilience" : "Level"}}
            </button>
          </div>

          <div className="flex flex-col gap-2.5">
            {{filtered.map((career) => (
              <CareerCard key={{career.slug}} career={{career}} />
            ))}}
          </div>
        </main>

      </div>
    </div>
  );
}}
'''


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate industry page for a career cluster")
    parser.add_argument("--cluster", required=True, help="Cluster ID (e.g. sales)")
    parser.add_argument("--force", action="store_true", help="Overwrite existing files")
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

        # Parse growth
        raw_growth = occ.get("Projected Growth", "")
        pct = occ.get("Employment Change, 2024-2034", "")
        _GROWTH_LABEL_MAP = [
            ("Much faster than average", "+7%"),
            ("Faster than average",      "+5%"),
            ("Average",                  "+3%"),
            ("Slower than average",      "+1%"),
            ("Little or no change",      "0%"),
            ("Decline",                  "-1%"),
        ]
        try:
            pct_f = float(pct)
            rounded = round(pct_f)
            growth_str = f"+{rounded}%" if rounded > 0 else ("0%" if rounded == 0 else f"{rounded}%")
        except (ValueError, TypeError):
            growth_str = raw_growth  # keep raw string as fallback
            for key, label in _GROWTH_LABEL_MAP:
                if raw_growth.startswith(key):
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

    # Generate description via Claude
    print(f"\nGenerating description for '{cluster_name}' cluster...")
    try:
        client = anthropic.Anthropic()
        description = generate_description(client, cluster_name, careers, tone_guide)
        print(f"  → {description}")
    except Exception as e:
        print(f"  ✗ Claude error: {e}")
        description = f"Compare {cluster_name.lower()} careers by AI resilience score, growth, and career level."

    # Write files
    data_content = generate_data_file(cluster_id, cluster_name, description, careers, const_name)
    route_content = generate_route_file(cluster_name, page_slug, const_name, data_slug, component_name)

    os.makedirs(INDUSTRIES_DIR, exist_ok=True)
    os.makedirs(route_dir, exist_ok=True)

    with open(data_path, "w", encoding="utf-8") as f:
        f.write(data_content)
    with open(route_path, "w", encoding="utf-8") as f:
        f.write(route_content)

    print(f"\n  ✓ {data_path}")
    print(f"  ✓ {route_path}")
    print("\n✓ Done")


if __name__ == "__main__":
    main()
