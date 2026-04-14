#!/usr/bin/env python3
"""
Generate emerging AI career roles for an occupation.

Two modes:

  --code 15-1254.00
      Single-occupation mode. Uses score-tier logic to determine count:
        role_resilience_score ≤ 2.5   → 4 roles  (fragile/volatile)
        role_resilience_score 2.5–4.0 → 2 roles  (moderate)
        role_resilience_score > 4.0   → 0 roles  (solid/strong — skip)

  --cluster software-technology
      Cluster mode. Generates 2–4 roles for EVERY member of the cluster
      regardless of score tier, using a shared candidate pool for consistency:
        1. Seed pool with existing emerging_roles.csv entries for this cluster
        2. For each occupation (ordered by cluster level): generate 4–6 new
           candidates tailored to that occupation's skills
        3. Rank all candidates (pool + new) against this occupation and select
           top 2–4, ensuring they span at least 2 experience levels
        4. Each selected candidate joins the pool for subsequent occupations

      Each role is tagged with experience_level: "entry" / "mid" / "senior"

Claude generates title/description/tools/stat/fit/steps for each role.
Job search URLs are populated separately (by a human or Claude Code using web search).

Results are written to:
  data/emerging_roles/emerging_roles.csv  — one row per (onet_code, emerging_title)
  data/output/occupation_cards.jsonl       — emergingCareers field updated in-place

Usage:
    python3 scripts/generate_emerging_roles.py --code 15-1254.00
    python3 scripts/generate_emerging_roles.py --cluster software-technology
    python3 scripts/generate_emerging_roles.py --all
"""

import anthropic
import argparse
import csv
from datetime import datetime
import json
import os
import re
import sys
import urllib.request
import urllib.error

# ── Config ────────────────────────────────────────────────────────────────────
from loaders import load_scores, SCORES_CSV, CLUSTER_ROLES as CLUSTER_ROLES_CSV
EMERGING_CSV      = "data/emerging_roles/emerging_roles.csv"

MODEL      = "claude-haiku-4-5-20251001"
MAX_TOKENS = 2048

EMERGING_CSV_FIELDS = [
    "onet_code", "emerging_title", "description", "core_tools",
    "stat_text", "stat_source", "stat_title", "stat_date", "stat_url", "search_query",
    "job_search_url",       # populated by web search after generation
    "fit", "steps_json",
    "experience_level",     # integer 1–5 (1=Entry, 2=Mid-Level, 3=Senior, 4=Lead, 5=Principal)
]

CLUSTER_TARGET_COUNT = 3    # target per occupation in cluster mode


# ── Tier logic ────────────────────────────────────────────────────────────────

def emerging_count(score: float) -> int:
    if score <= 2.5:
        return 4
    elif score <= 4.0:
        return 2
    else:
        return 0


# ── I/O helpers ───────────────────────────────────────────────────────────────

# load_scores() imported from loaders.py above.

def load_cluster_roles(cluster_id: str) -> list[dict]:
    """Return list of cluster role dicts for the given cluster, ordered by level."""
    roles = []
    with open(CLUSTER_ROLES_CSV, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["cluster_id"] == cluster_id:
                roles.append(r)
    roles.sort(key=lambda r: int(r.get("level", 99)))
    return roles


def lookup_cluster_role(onet_code: str) -> dict | None:
    """Return the cluster_roles row for a single O*NET code, or None if not in any cluster."""
    if not os.path.exists(CLUSTER_ROLES_CSV):
        return None
    with open(CLUSTER_ROLES_CSV, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["onet_code"] == onet_code:
                return r
    return None


def load_emerging_csv() -> dict:
    """Returns (onet_code, emerging_title) → row dict."""
    index = {}
    if not os.path.exists(EMERGING_CSV):
        return index
    with open(EMERGING_CSV, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            index[(r["onet_code"], r["emerging_title"])] = r
    return index


def save_emerging_csv(rows: dict):
    with open(EMERGING_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=EMERGING_CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows.values():
            writer.writerow(row)


from cards import load_cards as load_jsonl, save_cards as save_jsonl


# ── Claude helpers ────────────────────────────────────────────────────────────

def _normalize_tools(value) -> str:
    """Normalize core_tools to a comma-separated string regardless of input type."""
    if isinstance(value, list):
        return ", ".join(str(v).strip() for v in value)
    s = str(value).strip()
    # Handle Python list repr: ['LangChain', 'OpenAI API']
    if s.startswith("[") and s.endswith("]"):
        import ast
        try:
            parsed = ast.literal_eval(s)
            if isinstance(parsed, list):
                return ", ".join(str(v).strip() for v in parsed)
        except Exception:
            pass
    return s


def parse_json(text: str):
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    text = text.strip()

    # Extract the first valid JSON object/array (handles extra text after JSON)
    depth = 0
    in_string = False
    escape = False
    start_idx = -1

    for i, char in enumerate(text):
        if escape:
            escape = False
            continue
        if char == '\\':
            escape = True
            continue
        if char == '"' and not escape:
            in_string = not in_string
        if in_string:
            continue

        if char in '[{':
            if depth == 0:
                start_idx = i
            depth += 1
        elif char in ']}':
            depth -= 1
            if depth == 0 and start_idx != -1:
                return json.loads(text[start_idx:i+1])

    # Fallback: try parsing the whole string
    return json.loads(text)


_SOFT_404_PHRASES = [
    "currently being developed",
    "page not found",
    "404",
    "no longer available",
    "has been removed",
    "content not found",
    "doesn't exist",
    "does not exist",
    "we couldn't find",
    "we could not find",
]


def check_url(url: str) -> bool:
    """Return True if URL is reachable and not a soft 404 or cross-domain redirect."""
    import urllib.parse
    if not url:
        return False
    try:
        original_domain = urllib.parse.urlparse(url).netloc
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=10)
        if not (200 <= resp.status < 300):
            return False
        final_url = resp.url
        if final_url != url:
            parsed_orig  = urllib.parse.urlparse(url)
            parsed_final = urllib.parse.urlparse(final_url)
            if parsed_final.netloc and parsed_final.netloc != parsed_orig.netloc:
                print(f"  ⚠ Cross-domain redirect: {url} → {final_url}")
                return False
            if len(parsed_final.path.strip("/")) < len(parsed_orig.path.strip("/")) // 2:
                print(f"  ⚠ Redirect to shorter path (possible homepage): {url} → {final_url}")
                return False
        snippet = resp.read(4096).decode("utf-8", errors="replace").lower()
        for phrase in _SOFT_404_PHRASES:
            if phrase in snippet:
                return False
        return True
    except Exception:
        return False


def _card_context_snippet(card: dict | None) -> str:
    """Extract a short narrative snippet from an occupation card to ground candidate generation."""
    if not card:
        return ""
    parts = []
    for field in ("keyDrivers", "risksBody", "opportunitiesBody", "alreadyIn", "thinkingOf"):
        val = card.get(field, "")
        if val and isinstance(val, str) and len(val) > 20:
            parts.append(val.strip())
    if not parts:
        return ""
    combined = " ".join(parts)
    # Trim to ~800 chars so we don't blow the token budget
    if len(combined) > 800:
        combined = combined[:797] + "..."
    return f"\n\nContext from this occupation's career page (use this to surface roles that are consistent with trends already discussed):\n{combined}"


def build_combined_prompt(occupation: str, n: int,
                          cluster_level: int | None = None,
                          card: dict | None = None) -> str:
    """Build a single combined prompt that generates candidates, selects top n, and produces
    fit/steps — collapsing the 3-call API workflow into one prompt for inline Claude Code use."""
    level_map = {1: "entry-level (0-2yr)", 2: "junior-mid (1-3yr)",
                 3: "mid-level (3-5yr)", 4: "senior (5-10yr)", 5: "expert (10+yr)"}
    level_hint = ""
    if cluster_level is not None:
        allowed = allowed_experience_levels(cluster_level)
        allowed_str = " or ".join(str(x) for x in sorted(allowed))
        level_hint = (
            f"\n\nThis occupation sits at career level {cluster_level} "
            f"({level_map.get(cluster_level, '')}). Only include roles where "
            f"experience_level is {allowed_str} — same level or one step up."
        )
    card_hint = _card_context_snippet(card)

    return f"""You are an expert AI career strategist. Generate exactly {n} emerging AI-adjacent career roles that a {occupation} could pivot into within 2–5 years. Focus on roles that are genuinely being hired for today.{level_hint}{card_hint}

For each role, return a JSON object with ALL of these fields:
- "emerging_title": The new job title
- "description": 1–2 sentences of day-to-day work
- "core_tools": 2–3 specific AI tools or platforms (comma-separated string)
- "search_query": Exact query to find job postings (e.g. '"AI Risk Analyst" jobs 2025')
- "stat_text": One compelling market stat about demand or growth for this role
- "stat_source": Organization that published the stat (e.g. "LinkedIn Economic Graph")
- "stat_title": Report or article title
- "stat_date": "Mon YYYY" — must be within the last 2 years, or omit entirely
- "stat_url": Real verifiable URL only; omit if uncertain. Prefer BLS/WEF/GitHub/Stack Overflow. Never Gartner/IDC/Forrester.
- "experience_level": Integer 1–5 (1=Entry, 2=Mid, 3=Senior, 4=Lead, 5=Principal)
- "fit": One sentence — what carries over from {occupation} and what new paradigm they must shift into. Plain language.
- "steps": Array of 2–3 short action phrases, each naming a specific credential, tool, or project

The {n} roles must span at least 2 different experience_level values.
Return ONLY a valid JSON array of {n} objects."""


def interactive_mode_for_code(source_code: str, scores: dict,
                              emerging_rows: dict, cards: dict) -> bool:
    """Print combined prompt for one occupation, read JSON from stdin, save.

    Interactive inline workflow: prints the prompt, reads a JSON array from
    stdin (paste response + Ctrl-D), validates, and saves to CSV + JSONL.
    """
    occ = scores.get(source_code)
    if not occ:
        print(f"  ✗ {source_code} not found in scores CSV")
        return False

    occupation = occ["Occupation"]
    cluster_row = lookup_cluster_role(source_code)
    cluster_level = int(cluster_row["level"]) if cluster_row else None

    try:
        score = float(occ.get("role_resilience_score") or 0)
    except ValueError:
        score = 0.0
    n = emerging_count(score)
    if n == 0:
        print(f"  ✓ {occupation} — strong occupation, no emerging roles needed")
        return True

    existing_card = cards.get(source_code)
    prompt = build_combined_prompt(occupation, n, cluster_level=cluster_level, card=existing_card)

    print(f"\n{'='*80}")
    print(f"── {occupation} ({source_code})  level={cluster_level}  → {n} roles needed")
    print(f"{'='*80}")
    print(prompt)
    print(f"{'='*80}")
    print(f"\nPaste JSON array of {n} emerging roles, then Enter + Ctrl-D:")

    try:
        text = sys.stdin.read().strip()
    except KeyboardInterrupt:
        print("\nAborted.")
        return False

    try:
        candidates = json.loads(text)
    except json.JSONDecodeError as e:
        print(f"  ✗ JSON parse error: {e}")
        return False

    if not isinstance(candidates, list):
        print("  ✗ Expected a JSON array")
        return False

    emerging_list = []
    for candidate in candidates[:n]:
        fit   = candidate.get("fit", "")
        steps = candidate.get("steps", [])
        row = _candidate_to_row(source_code, candidate, fit, steps)
        emerging_rows[(source_code, candidate.get("emerging_title", ""))] = row
        emerging_list.append(_row_to_output(row))

    if source_code not in cards:
        cards[source_code] = {"onet_code": source_code}
    cards[source_code]["emergingCareers"] = emerging_list

    save_emerging_csv(emerging_rows)
    save_jsonl(cards)
    print(f"\n  ✓ Saved {len(emerging_list)} emerging roles for {occupation}")
    return True


def print_prompts_for_cluster(cluster_id: str, scores: dict,
                               emerging_rows: dict, cards: dict) -> None:
    """Print combined prompts for each occupation in a cluster (inline Claude Code workflow).

    Claude Code reads each printed prompt, authors a JSON array, then writes
    the rows to emerging_roles.csv and the cards to occupation_cards.jsonl
    using save_emerging_csv() and save_jsonl() (alias for save_cards()) directly.
    """
    cluster_roles = load_cluster_roles(cluster_id)
    if not cluster_roles:
        print(f"✗ No roles found for cluster '{cluster_id}'")
        return

    cluster_codes = {r["onet_code"] for r in cluster_roles}

    print(f"\n══ Cluster: {cluster_id} ({len(cluster_roles)} roles) — PRINT-PROMPTS MODE ══")
    print("Author JSON arrays for each occupation below, then call save_emerging_csv/save_jsonl.")

    for role in cluster_roles:
        source_code   = role["onet_code"]
        occupation    = role["occupation"]
        cluster_level = int(role.get("level", 3))

        occ = scores.get(source_code)
        if not occ:
            print(f"\n  ✗ {source_code} not found in scores — skipping")
            continue

        # Skip if already have enough entries
        cached = [r for (code, _), r in emerging_rows.items() if code == source_code]
        if len(cached) >= CLUSTER_TARGET_COUNT:
            print(f"\n  ✓ {occupation} ({source_code}) — already has {len(cached)} rows, skipping")
            continue

        existing_card = cards.get(source_code)
        prompt = build_combined_prompt(occupation, CLUSTER_TARGET_COUNT,
                                       cluster_level=cluster_level, card=existing_card)

        print(f"\n{'='*80}")
        print(f"── {occupation} ({source_code})  level={cluster_level}")
        print(f"{'='*80}")
        print(prompt)
        print(f"{'='*80}")

    print(f"\n✓ Done printing prompts for cluster '{cluster_id}'.")


def generate_candidates(client: anthropic.Anthropic, occupation: str, n: int,
                        cluster_level: int | None = None,
                        card: dict | None = None) -> list[dict]:
    level_hint = ""
    if cluster_level is not None:
        level_map = {1: "entry-level (0-2 years experience)", 2: "junior to mid-level (1-3 years)",
                     3: "mid-level (3-5 years)", 4: "senior (5-10 years)", 5: "expert/staff (10+ years)"}
        allowed = allowed_experience_levels(cluster_level)
        allowed_str = " or ".join(str(x) for x in sorted(allowed))
        level_hint = (
            f"\n\nThis occupation sits at career level {cluster_level} "
            f"({level_map.get(cluster_level, '')}). Only suggest roles where "
            f"experience_level is {allowed_str} (integer) — same level or one step up, "
            f"not a senior leap from an entry role."
        )

    card_hint = _card_context_snippet(card)

    prompt = f"""You are an expert AI career strategist analyzing the O*NET occupation: {occupation}.

Suggest exactly {n} emerging, AI-centric niche careers that a {occupation} could uniquely pivot into within the next 2–5 years. Focus on roles that are genuinely being hired for today or will be within 2 years — real job titles people are searching for, not invented labels.{level_hint}{card_hint}

For each role return a JSON object with exactly these keys:
- "emerging_title": The new job title (e.g. "AI Integration Engineer")
- "description": 1–2 sentences describing what the person does day-to-day
- "core_tools": 2–3 specific AI tools or platforms (e.g. "LangChain, OpenAI API")
- "search_query": Exact search query to find real job postings (e.g. '"AI Integration Engineer" jobs 2025')
- "stat_text": One compelling market stat about demand or growth for this role
- "stat_source": Name of the organization that published the stat (e.g. "LinkedIn Economic Graph")
- "stat_title": Title of the specific report or article the stat comes from (e.g. "Future of Work Report: AI at Work")
- "stat_date": Publication date as "Mon YYYY" (e.g. "Jan 2024") — must be within the last 2 years; omit if unknown or older
- "stat_url": URL to the source (real, verifiable URLs only — no invented URLs; only include if you are confident the URL resolves). Prefer: Google Cloud/AWS/GitHub/Anthropic/CNCF/Stack Overflow/WEF/BLS. Avoid: Gartner, IDC, Forrester, MarketsandMarkets (paywalls, URL rot).
- "experience_level": Integer 1–5 matching the career level scale (1=Entry 0-2yr, 2=Mid-Level 2-5yr, 3=Senior 5-8yr, 4=Lead/Specialist 8-12yr, 5=Principal 12+yr) — the minimum level needed to be competitive for this role

Return ONLY a valid JSON array of {n} objects with exactly those keys."""

    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    return parse_json(response.content[0].text)


def allowed_experience_levels(cluster_level: int | None) -> set[int]:
    """Return the set of numeric experience levels (1–5) appropriate for a given cluster level.

    experience_level uses the same 1–5 scale as the career cluster:
      1 = Entry, 2 = Mid-Level, 3 = Senior, 4 = Lead/Specialist, 5 = Principal

    Emerging roles should be at the same level or one level above the reference
    career — accessible pivots, not aspirational leaps.
      L1 cluster → levels {1, 2}
      L2 cluster → levels {2, 3}
      L3 cluster → levels {3, 4}
      L4 cluster → levels {4, 5}
      L5 cluster → levels {5}
    """
    if cluster_level is None:
        return {1, 2, 3, 4, 5}
    return {cluster_level, min(cluster_level + 1, 5)}


LEVEL_LABELS = {1: "Entry", 2: "Mid-Level", 3: "Senior", 4: "Lead/Specialist", 5: "Principal"}


def filter_by_level(candidates: list[dict], cluster_level: int | None) -> list[dict]:
    """Remove candidates whose experience_level is too far above the cluster level."""
    allowed = allowed_experience_levels(cluster_level)
    filtered = [c for c in candidates
                if _parse_exp_level(c.get("experience_level")) in allowed]
    # If filtering removes everything, fall back to full list rather than returning nothing
    return filtered if filtered else candidates


def _parse_exp_level(val) -> int:
    """Coerce experience_level to int (1–5). Accepts int, int-as-string, or legacy strings."""
    if val is None:
        return 2
    try:
        n = int(val)
        return max(1, min(5, n))
    except (ValueError, TypeError):
        pass
    # Legacy string fallback
    return {"entry": 1, "mid": 2, "senior": 3}.get(str(val).lower(), 2)


def rank_candidates(client: anthropic.Anthropic, occupation: str,
                    candidates: list[dict], select_n: int,
                    cluster_level: int | None = None) -> list[dict]:
    """Ask Claude to rank candidates by fit for this occupation and return top select_n."""
    level_hint = ""
    if cluster_level is not None:
        level_map = {1: "entry-level (0-2yr)", 2: "junior-mid (1-3yr)",
                     3: "mid-level (3-5yr)", 4: "senior (5-10yr)", 5: "expert (10+yr)"}
        level_hint = f" Career level: {cluster_level} ({level_map.get(cluster_level, '')})."

    candidates_text = json.dumps(
        [{"index": i, "title": c["emerging_title"], "description": c.get("description", ""),
          "experience_level": c.get("experience_level", "mid")} for i, c in enumerate(candidates)],
        indent=2
    )

    prompt = f"""You are selecting the best emerging AI career pivots for someone currently working as a {occupation}.{level_hint}

Here are {len(candidates)} candidate roles:

{candidates_text}

Select the best {select_n} candidates for this specific occupation. Criteria:
1. Strong skills transfer — the occupation's core tasks and knowledge directly apply
2. Real market demand — these roles exist and are growing
3. Experience level spread — the selected set must include at least 2 different experience_level values (entry/mid/senior), so people at different career stages have options
4. Avoid redundancy — don't pick two roles that are nearly identical

Return ONLY a JSON array of the selected candidate indices (e.g. [0, 3, 5])."""

    response = client.messages.create(
        model=MODEL,
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )
    indices = parse_json(response.content[0].text)
    return [candidates[i] for i in indices if 0 <= i < len(candidates)]


def generate_fit_steps(client: anthropic.Anthropic, occupation: str,
                       title: str, description: str, core_tools: str) -> dict:
    prompt = f"""You are helping someone who works as a {occupation} understand how they could move into the emerging AI role: {title}.

Role description: {description}
Core tools: {core_tools}

Generate a JSON object with exactly two fields:
{{
  "fit": "One sentence. State what carries over from their current role and the key new paradigm they must shift into. Plain language, no jargon, no 'leverage' or 'lean into'.",
  "steps": ["Concrete step 1 (5–10 words)", "Concrete step 2", "Concrete step 3"]
}}

Rules:
- fit: one sentence, factual, honest about direction
- steps: 2–3 items, each a short action phrase naming a specific credential, tool, or project

Respond ONLY with the JSON object."""

    response = client.messages.create(
        model=MODEL,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    return parse_json(response.content[0].text)


# ── Candidate → row/output helpers ───────────────────────────────────────────

_BLOCKED_SOURCES = {"gartner", "idc", "forrester", "marketsandmarkets"}


def _warn_blocked_source(source_code: str, candidate: dict):
    """Warn if a generated emerging role cites a blocked source."""
    combined = (candidate.get("stat_source", "") + " " + candidate.get("stat_url", "")).lower()
    for blocked in _BLOCKED_SOURCES:
        if blocked in combined:
            title = candidate.get("emerging_title", "?")
            print(f"  ⚠ BLOCKED SOURCE: {source_code} {title} cites {blocked} — "
                  f"replace with an approved source from docs/approved_sources.md")
            return


def _candidate_to_row(source_code: str, candidate: dict, fit: str, steps: list) -> dict:
    _warn_blocked_source(source_code, candidate)
    return {
        "onet_code":        source_code,
        "emerging_title":   candidate.get("emerging_title", "Unknown Role"),
        "description":      candidate.get("description", ""),
        "core_tools":       _normalize_tools(candidate.get("core_tools", "")),
        "stat_text":        candidate.get("stat_text", ""),
        "stat_source":      candidate.get("stat_source", ""),
        "stat_title":       candidate.get("stat_title", ""),
        "stat_date":        candidate.get("stat_date", ""),
        "stat_url":         candidate.get("stat_url", ""),
        "search_query":     candidate.get("search_query", ""),
        "job_search_url":   "",
        "fit":              fit,
        "steps_json":       json.dumps(steps, ensure_ascii=False),
        "experience_level": candidate.get("experience_level", "mid"),
    }


def _row_to_output(r: dict) -> dict:
    try:
        steps = json.loads(r.get("steps_json") or "[]")
    except json.JSONDecodeError:
        steps = []
    return {
        "title":           r["emerging_title"],
        "description":     r.get("description", ""),
        "core_tools":      r.get("core_tools", ""),
        "experience_level": r.get("experience_level", "mid"),
        "stat": {
            "text":        r.get("stat_text", ""),
            "sourceName":  r.get("stat_source", ""),
            "sourceTitle": r.get("stat_title", ""),
            "sourceDate":  r.get("stat_date", ""),
            "sourceUrl":   r.get("stat_url", ""),
        },
        "search_query":    r.get("search_query", ""),
        "job_search_url":  r.get("job_search_url", ""),
        "fit":             r.get("fit", ""),
        "steps":           steps,
    }


def _rows_to_output(rows: list[dict]) -> list[dict]:
    return [_row_to_output(r) for r in rows]


# ── Single-occupation mode ────────────────────────────────────────────────────

def process_occupation(source_code: str, scores: dict,
                       emerging_rows: dict, cards: dict,
                       client: anthropic.Anthropic) -> bool:
    occ = scores.get(source_code)
    if not occ:
        print(f"  ✗ {source_code} not found in scores CSV")
        return False

    try:
        score = float(occ.get("role_resilience_score") or 0)
    except ValueError:
        score = 0.0

    occupation = occ["Occupation"]

    # Look up cluster membership to get level and pool
    cluster_row = lookup_cluster_role(source_code)
    cluster_level = int(cluster_row["level"]) if cluster_row else None
    cluster_id    = cluster_row["cluster_id"] if cluster_row else None

    n = emerging_count(score)
    print(f"\n── {occupation} ({source_code})  score={score:.1f}  level={cluster_level}  → {n} emerging roles")

    if n == 0:
        print("  ✓ Solid/strong occupation — no emerging roles needed")
        return True

    # Use cached rows if we already have enough and not forced
    cached = [r for (code, _), r in emerging_rows.items()
              if code == source_code and r.get("stat_text", "").strip()]
    if len(cached) >= n:
        print(f"  → Using {len(cached)} cached rows from emerging_roles.csv")
        emerging_list = _rows_to_output(cached)
    else:
        # 1. Seed pool from other cluster members' existing emerging roles
        pool: list[dict] = []
        if cluster_id:
            cluster_codes = {r["onet_code"] for r in load_cluster_roles(cluster_id)}
            for (code, _), row in emerging_rows.items():
                if code in cluster_codes and code != source_code:
                    pool.append({
                        "emerging_title":   row["emerging_title"],
                        "description":      row.get("description", ""),
                        "core_tools":       row.get("core_tools", ""),
                        "stat_text":        row.get("stat_text", ""),
                        "stat_source":      row.get("stat_source", ""),
                        "stat_title":       row.get("stat_title", ""),
                        "stat_date":        row.get("stat_date", ""),
                        "stat_url":         row.get("stat_url", ""),
                        "search_query":     row.get("search_query", ""),
                        "experience_level": row.get("experience_level", "2"),
                        "_from_cache":      True,
                    })
        # Validate pool candidates' dates — clear stale stats before they enter ranking
        cutoff_year_pool = datetime.now().year - 2
        for candidate in pool:
            date_str = candidate.get("stat_date", "")
            if date_str:
                try:
                    pub_date = datetime.strptime(date_str, "%b %Y")
                    if pub_date.year < cutoff_year_pool:
                        print(f"    ⚠ Pool stat date older than 2 years: {date_str} ({candidate['emerging_title']}) — clearing")
                        for field in ("stat_url", "stat_source", "stat_title", "stat_date", "stat_text"):
                            candidate[field] = ""
                except ValueError:
                    pass
        print(f"  → Pool from cluster: {len(pool)} roles")

        # 2. Generate fresh candidates
        existing_card = cards.get(source_code)
        print(f"  → Generating 5 new candidates via Claude...")
        try:
            new_candidates = generate_candidates(client, occupation, 5,
                                                 cluster_level=cluster_level,
                                                 card=existing_card)
        except Exception as e:
            print(f"  ✗ Failed to generate candidates: {e}")
            return False

        # Validate stat URLs and dates on new candidates
        cutoff_year = datetime.now().year - 2
        for candidate in new_candidates:
            url = candidate.get("stat_url", "")
            if url:
                ok = check_url(url)
                print(f"    URL {'✓' if ok else '✗ (cleared)'}: {url}")
                if not ok:
                    for field in ("stat_url", "stat_source", "stat_title", "stat_date", "stat_text"):
                        candidate[field] = ""
                    continue
            date_str = candidate.get("stat_date", "")
            if date_str:
                try:
                    pub_date = datetime.strptime(date_str, "%b %Y")
                    if pub_date.year < cutoff_year:
                        print(f"    ⚠ Stat date older than 2 years: {date_str} — clearing")
                        for field in ("stat_url", "stat_source", "stat_title", "stat_date", "stat_text"):
                            candidate[field] = ""
                except ValueError:
                    pass

        # 3. Combine pool + new (deduplicate by title), filter by level
        pool_titles = {c["emerging_title"].lower() for c in pool}
        truly_new = [c for c in new_candidates
                     if c["emerging_title"].lower() not in pool_titles]
        all_candidates = filter_by_level(pool + truly_new, cluster_level)
        print(f"  → Pool: {len(pool)} | New: {len(truly_new)} | Level-filtered: {len(all_candidates)}")

        # 4. Rank all candidates by proximity to this occupation, select top n
        try:
            selected = rank_candidates(client, occupation, all_candidates,
                                       n, cluster_level=cluster_level)
        except Exception as e:
            print(f"  ✗ Ranking failed: {e} — using first {n} new candidates")
            selected = new_candidates[:n]

        print(f"  → Selected: {[c['emerging_title'] for c in selected]}")

        # 5. Generate occupation-specific fit/steps for each selected role
        emerging_list = []
        for candidate in selected:
            title = candidate.get("emerging_title", "Unknown Role")
            desc  = candidate.get("description", "")
            tools = candidate.get("core_tools", "")
            print(f"  → fit/steps: {title}")

            try:
                result = generate_fit_steps(client, occupation, title, desc, tools)
            except Exception as e:
                print(f"    ✗ fit/steps failed: {e}")
                result = {"fit": "", "steps": []}

            fit   = result.get("fit", "")
            steps = result.get("steps", [])
            print(f"    fit: {fit[:90]}")
            print(f"    steps: {steps}")

            row = _candidate_to_row(source_code, candidate, fit, steps)
            emerging_rows[(source_code, title)] = row
            emerging_list.append(_row_to_output(row))

    if source_code not in cards:
        cards[source_code] = {"onet_code": source_code}
    cards[source_code]["emergingCareers"] = emerging_list

    save_emerging_csv(emerging_rows)
    save_jsonl(cards)
    print(f"\n  ✓ Wrote {len(emerging_list)} emerging roles for {occ['Occupation']}")
    print(f"  ℹ  job_search_url fields are empty — run web search step to populate them")
    return True


# ── Cluster mode ──────────────────────────────────────────────────────────────

def process_cluster(cluster_id: str, scores: dict,
                    emerging_rows: dict, cards: dict,
                    client: anthropic.Anthropic) -> None:
    cluster_roles = load_cluster_roles(cluster_id)
    if not cluster_roles:
        print(f"✗ No roles found for cluster '{cluster_id}'")
        return

    print(f"\n══ Cluster: {cluster_id} ({len(cluster_roles)} roles) ══")

    # Seed the pool with any existing emerging roles for this cluster
    cluster_codes = {r["onet_code"] for r in cluster_roles}
    pool: list[dict] = []  # list of candidate dicts (with onet_code of origin)
    for (code, _), row in emerging_rows.items():
        if code in cluster_codes:
            # Convert existing CSV row to candidate format
            pool.append({
                "emerging_title":  row["emerging_title"],
                "description":     row.get("description", ""),
                "core_tools":      row.get("core_tools", ""),
                "stat_text":       row.get("stat_text", ""),
                "stat_source":     row.get("stat_source", ""),
                "stat_title":      row.get("stat_title", ""),
                "stat_date":       row.get("stat_date", ""),
                "stat_url":        row.get("stat_url", ""),
                "search_query":    row.get("search_query", ""),
                "experience_level": row.get("experience_level", "mid"),
                "_from_cache":     True,
            })
    # Validate pool dates — clear stale stats before they enter ranking
    cutoff_year_pool = datetime.now().year - 2
    for candidate in pool:
        date_str = candidate.get("stat_date", "")
        if date_str:
            try:
                pub_date = datetime.strptime(date_str, "%b %Y")
                if pub_date.year < cutoff_year_pool:
                    print(f"  ⚠ Pool stat date older than 2 years: {date_str} ({candidate['emerging_title']}) — clearing")
                    for field in ("stat_url", "stat_source", "stat_title", "stat_date", "stat_text"):
                        candidate[field] = ""
            except ValueError:
                pass
    print(f"  Seeded pool with {len(pool)} existing roles")

    for role in cluster_roles:
        source_code  = role["onet_code"]
        occupation   = role["occupation"]
        cluster_level = int(role.get("level", 3))

        occ = scores.get(source_code)
        if not occ:
            print(f"\n  ✗ {source_code} not found in scores CSV — skipping")
            continue

        print(f"\n── {occupation} ({source_code})  level={cluster_level}")

        # Generate fresh candidates tailored to this occupation
        # Pass card content so Claude surfaces roles consistent with page narrative
        existing_card = cards.get(source_code)
        try:
            print(f"  → Generating 5 new candidates via Claude...")
            new_candidates = generate_candidates(client, occupation, 5,
                                                 cluster_level=cluster_level,
                                                 card=existing_card)
        except Exception as e:
            print(f"  ✗ Failed to generate candidates: {e}")
            continue

        # Validate stat URLs and dates on new candidates
        cutoff_year = datetime.now().year - 2
        for candidate in new_candidates:
            url = candidate.get("stat_url", "")
            if url:
                ok = check_url(url)
                print(f"    URL {'✓' if ok else '✗ (cleared)'}: {url}")
                if not ok:
                    for field in ("stat_url", "stat_source", "stat_title", "stat_date", "stat_text"):
                        candidate[field] = ""
                    continue
            date_str = candidate.get("stat_date", "")
            if date_str:
                try:
                    pub_date = datetime.strptime(date_str, "%b %Y")
                    if pub_date.year < cutoff_year:
                        print(f"    ⚠ Stat date older than 2 years: {date_str} — clearing")
                        for field in ("stat_url", "stat_source", "stat_title", "stat_date", "stat_text"):
                            candidate[field] = ""
                except ValueError:
                    pass

        # Combine pool + new candidates (deduplicate by title)
        pool_titles = {c["emerging_title"].lower() for c in pool}
        truly_new = [c for c in new_candidates
                     if c["emerging_title"].lower() not in pool_titles]
        all_candidates = filter_by_level(pool + truly_new, cluster_level)
        print(f"  → Pool: {len(pool)} | New: {len(truly_new)} | Level-filtered: {len(all_candidates)}")

        # Rank and select top CLUSTER_TARGET_COUNT
        try:
            selected = rank_candidates(client, occupation, all_candidates,
                                       CLUSTER_TARGET_COUNT, cluster_level=cluster_level)
        except Exception as e:
            print(f"  ✗ Ranking failed: {e} — using first {CLUSTER_TARGET_COUNT} new candidates")
            selected = new_candidates[:CLUSTER_TARGET_COUNT]

        print(f"  → Selected: {[c['emerging_title'] for c in selected]}")

        # Generate fit/steps for each selected candidate
        emerging_list = []
        for candidate in selected:
            title = candidate.get("emerging_title", "Unknown Role")
            desc  = candidate.get("description", "")
            tools = candidate.get("core_tools", "")
            print(f"  → fit/steps: {title}")

            try:
                result = generate_fit_steps(client, occupation, title, desc, tools)
            except Exception as e:
                print(f"    ✗ fit/steps failed: {e}")
                result = {"fit": "", "steps": []}

            fit   = result.get("fit", "")
            steps = result.get("steps", [])
            print(f"    fit: {fit[:90]}")

            row = _candidate_to_row(source_code, candidate, fit, steps)
            emerging_rows[(source_code, title)] = row
            emerging_list.append(_row_to_output(row))

        # Add selected candidates to the pool for subsequent occupations
        for candidate in selected:
            title = candidate["emerging_title"].lower()
            if title not in {c["emerging_title"].lower() for c in pool}:
                pool.append(candidate)

        if source_code not in cards:
            cards[source_code] = {"onet_code": source_code}
        cards[source_code]["emergingCareers"] = emerging_list

        save_emerging_csv(emerging_rows)
        save_jsonl(cards)
        print(f"  ✓ Wrote {len(emerging_list)} emerging roles")

    print(f"\n✓ Cluster '{cluster_id}' complete. Final pool size: {len(pool)}")
    print(f"  ℹ  job_search_url fields are empty — run web search step to populate them")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--code",    help="Single O*NET code to process")
    parser.add_argument("--cluster", help="Process all roles in a career cluster (e.g. web-developer)")
    parser.add_argument("--all",     action="store_true", help="Process all codes in scores CSV")
    parser.add_argument("--print-prompts", action="store_true",
                        help="Print combined prompts to stdout without calling the API "
                             "(inline Claude Code workflow — use with --cluster)")
    parser.add_argument("--interactive", action="store_true",
                        help="Print prompt, read JSON from stdin, save (use with --code)")
    args = parser.parse_args()

    if not args.code and not args.cluster and not args.all:
        parser.print_help()
        sys.exit(1)

    print("Loading data...")
    scores        = load_scores()
    emerging_rows = load_emerging_csv()
    cards         = load_jsonl()

    if args.print_prompts:
        if not args.cluster:
            print("--print-prompts requires --cluster")
            sys.exit(1)
        print_prompts_for_cluster(args.cluster, scores, emerging_rows, cards)
        return

    if args.interactive:
        if not args.code:
            print("--interactive requires --code")
            sys.exit(1)
        success = interactive_mode_for_code(args.code, scores, emerging_rows, cards)
        sys.exit(0 if success else 1)

    try:
        client = anthropic.Anthropic()
    except Exception as e:
        print(f"✗ Anthropic client error: {e}")
        sys.exit(1)

    if args.cluster:
        process_cluster(args.cluster, scores, emerging_rows, cards, client)
    elif args.all:
        for code in scores:
            process_occupation(code, scores, emerging_rows, cards, client)
    else:
        process_occupation(args.code, scores, emerging_rows, cards, client)

    print("\n✓ Done")


if __name__ == "__main__":
    main()
