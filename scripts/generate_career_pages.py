#!/usr/bin/env python3
"""
Generate career page TSX files from occupation_cards.jsonl.

For each occupation, writes two files to the site repo:
  src/data/careers/<slug>.tsx   — CareerData export
  app/career/<slug>/page.tsx    — Next.js route

Usage:
    python3 scripts/generate_career_pages.py --code 41-2031.00
    python3 scripts/generate_career_pages.py --cluster sales
    python3 scripts/generate_career_pages.py --all
    python3 scripts/generate_career_pages.py --code 41-2031.00 --force
"""

from __future__ import annotations
import argparse
import csv
import json
import os
import re
import sys

# ── Config ────────────────────────────────────────────────────────────────────
CLUSTER_ROLES_CSV = "data/career_clusters/cluster_roles.csv"
CLUSTERS_CSV      = "data/career_clusters/clusters.csv"
SCORES_CSV        = "data/output/ai_resilience_scores.csv"
SITE_DIR          = "../ai-resilient-occupations-site"
CAREERS_DATA_DIR  = os.path.join(SITE_DIR, "src/data/careers")
CAREERS_ROUTE_DIR = os.path.join(SITE_DIR, "app/career")


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_cards() -> dict:
    from cards import load_cards as _load
    return _load()


def load_cluster_roles() -> dict:
    """Returns onet_code → {cluster_id, level, occupation, ...}"""
    roles = {}
    if not os.path.exists(CLUSTER_ROLES_CSV):
        return roles
    with open(CLUSTER_ROLES_CSV, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            roles[r["onet_code"]] = r
    return roles


def load_scores() -> dict:
    scores = {}
    with open(SCORES_CSV, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            scores[r["Code"]] = r
    return scores


def load_clusters() -> dict:
    """Returns cluster_id → {industry_slug, industry_display_name, ...}"""
    clusters = {}
    if not os.path.exists(CLUSTERS_CSV):
        return clusters
    with open(CLUSTERS_CSV, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            clusters[r["cluster_id"]] = r
    return clusters


def get_cluster_members(cluster_id: str, cluster_roles: dict) -> list[dict]:
    """Return all cluster members sorted by level."""
    members = [r for r in cluster_roles.values() if r["cluster_id"] == cluster_id]
    members.sort(key=lambda r: int(r.get("level", 99)))
    return members


def title_to_slug(title: str) -> str:
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug.strip())
    slug = re.sub(r"-+", "-", slug)
    return slug


def code_to_slug(onet_code: str, title: str, scores: dict) -> str:
    """Use altpath simple title if available, else fall back to full occupation title."""
    simple = scores.get(onet_code, {}).get("altpath simple title", "").strip()
    return title_to_slug(simple if simple else title)


def slug_to_var(slug: str) -> str:
    """Convert slug to camelCase variable name."""
    parts = slug.split("-")
    return parts[0] + "".join(p.capitalize() for p in parts[1:]) + "Data"


def slug_to_component(slug: str) -> str:
    """Convert slug to PascalCase component name."""
    return "".join(p.capitalize() for p in slug.split("-")) + "Page"


def citations_to_jsx(text: str) -> str:
    """Convert [1] inline citations to JSX anchor tags."""
    def replace(m):
        n = m.group(1)
        return (
            f'<sup><a href="#src-{n}" '
            f'className="text-primary font-bold hover:underline">[{n}]</a></sup>'
        )
    return re.sub(r"\[(\d+)\]", replace, text)


def text_to_jsx_fragment(text: str, indent: int = 2) -> str:
    """Convert plain text (with [n] citations) to a JSX fragment string."""
    text = text.replace("&", "&amp;").replace('"', "&quot;")
    text = citations_to_jsx(text)
    pad = "  " * indent
    return f"(\n{pad}  <>\n{pad}    {text}\n{pad}  </>\n{pad})"


def escape_tsx(s: str) -> str:
    """Escape a string for use inside TSX JSX."""
    return s.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")


def str_to_tsx_string(s: str) -> str:
    """Wrap a string in double quotes, escaping as needed."""
    escaped = s.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def nullable_string(s) -> str:
    if s is None or s == "":
        return "null"
    return str_to_tsx_string(str(s))


def build_task_row(task: dict) -> str:
    task_label = escape_tsx(task.get("task", ""))
    full = escape_tsx(task.get("full", task.get("task", "")))
    auto = task.get("auto")
    aug = task.get("aug")
    success = task.get("success")
    n = task.get("n")

    auto_s = str(auto) if auto is not None else "null"
    aug_s = str(aug) if aug is not None else "null"
    success_s = str(success) if success is not None else "null"
    n_s = str(int(n)) if n is not None else "null"

    return (
        f'    {{ task: "{task_label}", full: "{full}", '
        f'auto: {auto_s}, aug: {aug_s}, success: {success_s}, n: {n_s} }}'
    )


def build_cluster_node(node: dict, is_current: bool = False, is_emerging: bool = False) -> str:
    """Render a CareerClusterNode as TSX object literal."""
    lines = []

    level = node.get("level")
    if level is not None:
        lines.append(f"      level: {int(level)},")

    code = node.get("code")
    if code and not is_emerging:
        lines.append(f"      code: {str_to_tsx_string(code)},")

    lines.append(f"      title: {str_to_tsx_string(node.get('title', ''))},")
    lines.append(f"      isCurrent: {'true' if is_current else 'false'},")

    if is_emerging:
        lines.append("      isEmerging: true,")

    if node.get("isAdjacent"):
        lines.append("      isAdjacent: true,")

    score = node.get("score")
    if score is not None:
        lines.append(f"      score: {score},")

    relationship = node.get("relationship")
    if relationship:
        lines.append(f"      relationship: {str_to_tsx_string(relationship)},")

    salary = node.get("salary")
    if salary:
        lines.append(f"      salary: {str_to_tsx_string(str(salary))},")

    openings = node.get("openings")
    if openings:
        lines.append(f"      openings: {str_to_tsx_string(str(openings))},")

    growth = node.get("growth")
    if growth:
        lines.append(f"      growth: {str_to_tsx_string(str(growth))},")

    fit = node.get("fit")
    if fit:
        lines.append(f"      fit: {str_to_tsx_string(fit)},")

    steps = node.get("steps", [])
    if steps:
        steps_str = ", ".join(str_to_tsx_string(s) for s in steps)
        lines.append(f"      steps: [{steps_str}],")

    # Emerging-only fields
    description = node.get("description")
    if description:
        lines.append(f"      description: {str_to_tsx_string(description)},")

    core_tools = node.get("core_tools")
    if core_tools:
        # Normalize list repr to comma-separated string (Claude sometimes returns a list)
        if isinstance(core_tools, list):
            core_tools = ", ".join(str(v).strip() for v in core_tools)
        else:
            s = str(core_tools).strip()
            if s.startswith("[") and s.endswith("]"):
                import ast as _ast
                try:
                    parsed = _ast.literal_eval(s)
                    if isinstance(parsed, list):
                        s = ", ".join(str(v).strip() for v in parsed)
                except Exception:
                    pass
                core_tools = s
        lines.append(f"      core_tools: {str_to_tsx_string(core_tools)},")

    stat = node.get("stat")
    if stat and isinstance(stat, dict) and stat.get("text"):
        lines.append("      stat: {")
        lines.append(f"        text: {str_to_tsx_string(stat.get('text', ''))},")
        lines.append(f"        sourceName: {str_to_tsx_string(stat.get('sourceName', ''))},")
        if stat.get("sourceTitle"):
            lines.append(f"        sourceTitle: {str_to_tsx_string(stat.get('sourceTitle', ''))},")
        if stat.get("sourceDate"):
            lines.append(f"        sourceDate: {str_to_tsx_string(stat.get('sourceDate', ''))},")
        lines.append(f"        sourceUrl: {str_to_tsx_string(stat.get('sourceUrl', ''))},")
        lines.append("      },")

    job_search_url = node.get("job_search_url")
    if job_search_url:
        lines.append(f"      job_search_url: {str_to_tsx_string(job_search_url)},")

    return "    {\n" + "\n".join(lines) + "\n    }"


def build_career_cluster(card: dict, cluster_roles: dict, scores: dict) -> str:
    """Build the careerCluster array combining ladder + adjacent + emerging nodes."""
    onet_code = card["onet_code"]
    cluster_row = cluster_roles.get(onet_code)

    nodes = []
    seen_codes = set()

    # Build lookup of transition data from adjacent_roles.py output
    transition_by_code = {n["code"]: n for n in card.get("careerCluster", []) if n.get("code")}

    # 1. Cluster ladder nodes (all members, current marked), merging transition data if available
    if cluster_row:
        cluster_id = cluster_row["cluster_id"]
        members = get_cluster_members(cluster_id, cluster_roles)
        for m in members:
            m_code = m["onet_code"]
            m_score = scores.get(m_code, {}).get("role_resilience_score")
            m_simple = scores.get(m_code, {}).get("altpath simple title", "").strip()
            node = {
                "level": int(m["level"]),
                "code": m_code,
                "title": m_simple if m_simple else m["occupation"],
                "score": float(m_score) if m_score else None,
            }
            # Merge transition data (fit, steps, relationship, openings, growth) if available
            t = transition_by_code.get(m_code, {})
            for key in ("fit", "steps", "relationship", "salary", "openings", "growth", "isAdjacent"):
                if t.get(key):
                    node[key] = t[key]
            nodes.append(build_cluster_node(node, is_current=(m_code == onet_code)))
            seen_codes.add(m_code)

    # 2. Adjacent roles with fit/steps (skip bare ladder nodes and already-added codes)
    for adj in card.get("careerCluster", []):
        if not adj.get("fit"):
            continue
        adj_code = adj.get("code", "")
        if adj_code and adj_code in seen_codes:
            continue  # already in ladder, skip duplicate
        # Resolve level from cluster_roles if null
        adj_level = adj.get("level")
        if adj_level is None and adj_code in cluster_roles:
            adj_level = int(cluster_roles[adj_code]["level"])
        adj_score = scores.get(adj_code, {}).get("role_resilience_score")
        node = dict(adj)
        node["level"] = adj_level
        node["score"] = float(adj_score) if adj_score else None
        nodes.append(build_cluster_node(node, is_current=False, is_emerging=False))

    # 3. Emerging careers
    for ec in card.get("emergingCareers", []):
        exp = ec.get("experience_level", "2")
        try:
            level = int(exp)
        except (ValueError, TypeError):
            level = 2
        node = dict(ec)
        node["level"] = level
        nodes.append(build_cluster_node(node, is_current=False, is_emerging=True))

    return "[\n" + ",\n".join(nodes) + "\n  ]"


def build_quote(q: dict) -> str:
    persona = q.get("persona", "alreadyIn")
    quote = q.get("quote", "")
    attribution = q.get("attribution", "")
    source_id = q.get("sourceId", "src-1")
    return (
        f"      {{\n"
        f"        persona: {str_to_tsx_string(persona)} as const,\n"
        f"        quote: {str_to_tsx_string(quote)},\n"
        f"        attribution: {str_to_tsx_string(attribution)},\n"
        f"        sourceId: {str_to_tsx_string(source_id)},\n"
        f"      }}"
    )


def build_source(s: dict) -> str:
    return (
        f"    {{\n"
        f"      id: {str_to_tsx_string(s.get('id', ''))},\n"
        f"      name: {str_to_tsx_string(s.get('name', ''))},\n"
        f"      title: {str_to_tsx_string(s.get('title', ''))},\n"
        f"      date: {str_to_tsx_string(s.get('date', ''))},\n"
        f"      url: {str_to_tsx_string(s.get('url', ''))},\n"
        f"    }}"
    )


def generate_data_file(card: dict, cluster_roles: dict, scores: dict, var_name: str, title: str = "") -> str:
    """Generate the full src/data/careers/<slug>.tsx content."""
    onet_code = card.get("onet_code", "")
    if not title:
        title = card.get("title", "")
    score = card.get("score", 0)
    salary = card.get("salary", "")
    openings = card.get("openings", "")
    growth = card.get("growth", "")
    description = card.get("description") or scores.get(onet_code, {}).get("Job Description", "")
    onet_url = scores.get(onet_code, {}).get("url", "")
    job_titles = card.get("jobTitles", [])
    emerging_titles = card.get("emergingTitles") or [
        t.strip() for t in scores.get(onet_code, {}).get("Emerging Job Titles", "").split(";") if t.strip()
    ]
    key_drivers = scores.get(onet_code, {}).get("key_drivers", "") or card.get("keyDrivers", "")
    task_intro = card.get("taskIntro", "")

    risks = card.get("risks", {})
    risks_body = risks.get("body", "")
    risks_stat = nullable_string(risks.get("stat"))
    risks_stat_label = nullable_string(risks.get("statLabel"))
    risks_stat_source_name  = nullable_string(risks.get("statSourceName"))
    risks_stat_source_title = nullable_string(risks.get("statSourceTitle"))
    risks_stat_source_date  = nullable_string(risks.get("statSourceDate"))
    risks_stat_source_url   = nullable_string(risks.get("statSourceUrl"))

    opps = card.get("opportunities", {})
    opps_body = opps.get("body", "")
    opps_stat = nullable_string(opps.get("stat"))
    opps_stat_label = nullable_string(opps.get("statLabel"))
    opps_stat_source_name  = nullable_string(opps.get("statSourceName"))
    opps_stat_source_title = nullable_string(opps.get("statSourceTitle"))
    opps_stat_source_date  = nullable_string(opps.get("statSourceDate"))
    opps_stat_source_url   = nullable_string(opps.get("statSourceUrl"))

    how = card.get("howToAdapt", {})
    already_in = how.get("alreadyIn", "")
    thinking_of = how.get("thinkingOf", "")
    quotes = how.get("quotes", [])

    task_rows = card.get("taskData", [])
    sources = list(card.get("sources", []))

    # Merge stat sources into sources list (dedup by url)
    existing_urls = {s.get("url") for s in sources}
    for section, key in [(risks, "risks"), (opps, "opportunities")]:
        url = section.get("statSourceUrl")
        if url and url not in existing_urls:
            sources.append({
                "id": f"src-stat-{key}",
                "name": section.get("statSourceName", ""),
                "title": section.get("statSourceTitle", ""),
                "date": section.get("statSourceDate", ""),
                "url": url,
            })
            existing_urls.add(url)

    # Build job titles lists
    titles_str = "\n".join(f"    {str_to_tsx_string(t)}," for t in job_titles)
    emerging_titles_str = "\n".join(f"    {str_to_tsx_string(t)}," for t in emerging_titles)

    # Build task data
    tasks_str = ",\n".join(build_task_row(t) for t in task_rows)

    # Build quotes
    quotes_str = ",\n".join(build_quote(q) for q in quotes)

    # Build sources
    sources_str = ",\n".join(build_source(s) for s in sources)

    # Build career cluster
    career_cluster_str = build_career_cluster(card, cluster_roles, scores)

    lines = [
        'import type { CareerData } from "@/lib/careerUtils";',
        "",
        f"export const {var_name}: CareerData = {{",
        f"  title: {str_to_tsx_string(title)},",
        f"  url: {str_to_tsx_string(onet_url)},",
        f"  score: {score},",
        f"  salary: {str_to_tsx_string(salary)},",
        f"  openings: {str_to_tsx_string(openings)},",
        f"  growth: {str_to_tsx_string(growth)},",
        f"  description:",
        f"    {str_to_tsx_string(description)},",
        f"  jobTitles: [",
        titles_str,
        f"  ],",
        f"  emergingTitles: [",
        emerging_titles_str,
        f"  ],",
        f"  keyDrivers: {text_to_jsx_fragment(key_drivers, indent=1)},",
    ]

    if task_intro:
        lines.append(f"  taskIntro: {str_to_tsx_string(task_intro)},")

    risks_lines = [
        f"  risks: {{",
        f"    stat: {risks_stat},",
        f"    statLabel: {risks_stat_label},",
        f'    statColor: "#ea580c",',
    ]
    if risks.get("statSourceUrl"):
        risks_lines += [
            f"    statSourceName: {risks_stat_source_name},",
            f"    statSourceTitle: {risks_stat_source_title},",
            f"    statSourceDate: {risks_stat_source_date},",
            f"    statSourceUrl: {risks_stat_source_url},",
        ]
    risks_lines.append(f"    body: {text_to_jsx_fragment(risks_body, indent=2)},")
    risks_lines.append(f"  }},")

    opps_lines = [
        f"  opportunities: {{",
        f"    stat: {opps_stat},",
        f"    statLabel: {opps_stat_label},",
        f'    statColor: "#5a9a6e",',
    ]
    if opps.get("statSourceUrl"):
        opps_lines += [
            f"    statSourceName: {opps_stat_source_name},",
            f"    statSourceTitle: {opps_stat_source_title},",
            f"    statSourceDate: {opps_stat_source_date},",
            f"    statSourceUrl: {opps_stat_source_url},",
        ]
    opps_lines.append(f"    body: {text_to_jsx_fragment(opps_body, indent=2)},")
    opps_lines.append(f"  }},")

    lines += risks_lines + opps_lines
    lines += [
        f"  howToAdapt: {{",
        f"    alreadyIn: {text_to_jsx_fragment(already_in, indent=2)},",
        f"    thinkingOf: {text_to_jsx_fragment(thinking_of, indent=2)},",
    ]

    if quotes:
        lines += [
            f"    quotes: [",
            quotes_str,
            f"    ],",
        ]

    lines += [
        f"  }},",
        f"  taskData: [",
        tasks_str,
        f"  ],",
        f"  careerCluster: {career_cluster_str},",
        f"  sources: [",
        sources_str,
        f"  ],",
        f"}};",
        "",
    ]

    return "\n".join(lines)


def generate_route_file(slug: str, var_name: str, component_name: str,
                        industry_slug: str = "", industry_display_name: str = "") -> str:
    if industry_slug and industry_display_name:
        props = f'data={{{var_name}}} industrySlug="{industry_slug}" industryName="{industry_display_name}"'
    else:
        props = f"data={{{var_name}}}"
    return (
        f'import {{ getCareerMetadata }} from "@/lib/careerUtils";\n'
        f'import CareerDetailPage from "@/components/CareerDetailPage";\n'
        f'import {{ {var_name} }} from "@/data/careers/{slug}";\n'
        f"\n"
        f'export const metadata = getCareerMetadata({var_name}, "{slug}");\n'
        f"\n"
        f"export default function {component_name}() {{\n"
        f"  return <CareerDetailPage {props} />;\n"
        f"}}\n"
    )


def process_occupation(onet_code: str, cards: dict, cluster_roles: dict,
                       scores: dict, clusters: dict, force: bool = False) -> bool:
    card = cards.get(onet_code)
    if not card:
        print(f"  ✗ {onet_code} not found in data/output/cards/")
        return False

    onet_title = card.get("title", onet_code)
    simple = scores.get(onet_code, {}).get("altpath simple title", "").strip()
    title = simple if simple else onet_title
    slug = title_to_slug(title)
    var_name = slug_to_var(slug)
    component_name = slug_to_component(slug)

    # Look up industry breadcrumb from cluster
    cluster_row = cluster_roles.get(onet_code)
    industry_slug = ""
    industry_display_name = ""
    if cluster_row:
        cluster_data = clusters.get(cluster_row["cluster_id"], {})
        industry_slug = cluster_data.get("industry_slug", "").strip()
        industry_display_name = cluster_data.get("industry_display_name", "").strip()

    data_path = os.path.join(CAREERS_DATA_DIR, f"{slug}.tsx")
    route_dir = os.path.join(CAREERS_ROUTE_DIR, slug)
    route_path = os.path.join(route_dir, "page.tsx")

    if not force and os.path.exists(data_path):
        print(f"  ✓ Already exists: {slug} (use --force to overwrite)")
        return True

    print(f"\n── {title} ({onet_code})")
    print(f"   slug: {slug}")

    data_content = generate_data_file(card, cluster_roles, scores, var_name, title=title)
    route_content = generate_route_file(slug, var_name, component_name, industry_slug, industry_display_name)

    if not os.path.exists(CAREERS_DATA_DIR):
        try:
            os.makedirs(CAREERS_DATA_DIR, exist_ok=True)
        except Exception:
            pass
    if not os.path.exists(route_dir):
        try:
            os.makedirs(route_dir, exist_ok=True)
        except Exception:
            pass

    with open(data_path, "w", encoding="utf-8") as f:
        f.write(data_content)

    with open(route_path, "w", encoding="utf-8") as f:
        f.write(route_content)

    print(f"   ✓ {data_path}")
    print(f"   ✓ {route_path}")
    return True


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate career page TSX files from occupation_cards.jsonl")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--code", help="Single O*NET code")
    group.add_argument("--cluster", help="All occupations in a cluster")
    group.add_argument("--all", action="store_true", help="All occupations in cards JSONL")
    parser.add_argument("--force", action="store_true", help="Overwrite existing files")
    args = parser.parse_args()

    print("Loading data...")
    cards = load_cards()
    cluster_roles = load_cluster_roles()
    scores = load_scores()
    clusters = load_clusters()

    if args.code:
        process_occupation(args.code, cards, cluster_roles, scores, clusters, force=args.force)

    elif args.cluster:
        members = [r for r in cluster_roles.values() if r["cluster_id"] == args.cluster]
        members.sort(key=lambda r: int(r.get("level", 99)))
        if not members:
            print(f"✗ No roles found for cluster '{args.cluster}'")
            sys.exit(1)
        print(f"\n══ Cluster: {args.cluster} ({len(members)} roles) ══")
        for m in members:
            process_occupation(m["onet_code"], cards, cluster_roles, scores, clusters, force=args.force)

    elif args.all:
        for code in cards:
            process_occupation(code, cards, cluster_roles, scores, clusters, force=args.force)

    _regenerate_registry()
    print("\n✓ Done")


def _regenerate_registry():
    """Regenerate careerPageRegistry.ts from existing app/career/ directories.

    TODO: Remove this function (and its call above + the registry file) once all
    career pages are built. At that point every CareerClusterNode will have a page,
    so CareerDetailPage can link unconditionally. See docs/pipeline.md for context.
    """
    import os
    career_dir = os.path.join(SITE_DIR, "app", "career")
    slugs = sorted(
        d for d in os.listdir(career_dir)
        if os.path.isdir(os.path.join(career_dir, d))
    )
    slug_lines = ",\n  ".join(f'"{s}"' for s in slugs)
    registry = f"""// AUTO-GENERATED by scripts/generate_career_pages.py — do not edit manually.
// TODO: Once all career pages are built, this registry can be removed.
// Replace the slug-lookup in CareerDetailPage with a direct link on every node
// (since every node will have a page). See docs/pipeline.md for context.
export const CAREER_PAGE_SLUGS = new Set<string>([
  {slug_lines},
]);
"""
    registry_path = os.path.join(SITE_DIR, "src", "data", "careerPageRegistry.ts")
    with open(registry_path, "w") as f:
        f.write(registry)
    print(f"   ✓ careerPageRegistry.ts ({len(slugs)} slugs)")


if __name__ == "__main__":
    main()
