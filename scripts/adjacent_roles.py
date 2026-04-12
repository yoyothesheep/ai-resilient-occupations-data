#!/usr/bin/env python3
"""
Generate relatedCareers content for occupation cards.

For each occupation, finds related careers using three methods in priority order:
  1. cluster_roles.csv — curated career cluster (advancements + specializations)
  2. Task text overlap — Jaccard similarity on task text word sets, weighted by task_weight
  3. SOC code similarity — same 5-digit prefix, then same 2-digit prefix

# TODO: replace method 2 Jaccard with sentence-transformer cosine similarity on task
# embeddings for better semantic matching (e.g. "wound care" ↔ "dressing changes").
# See: https://www.sbert.net/

For each (source, target) pair, calls Claude to generate:
  - fit:   one sentence explaining the lateral path (Feynman style)
  - learn: 2-3 concrete skills/tools to close the gap

Joins BLS data (score, openings, growth) from scores CSV.
Updates relatedCareers field in occupation_cards.jsonl in-place.

Usage:
    python3 scripts/adjacent_roles.py --code 29-2061.00
    python3 scripts/adjacent_roles.py --all
"""

import anthropic
import argparse
import csv
import json
import os
import re
import sys

# ── Config ────────────────────────────────────────────────────────────────────
SCORES_CSV       = "data/output/ai_resilience_scores.csv"
TASK_TABLE       = "data/intermediate/onet_economic_index_task_table.csv"
CLUSTER_ROLES    = "data/career_clusters/cluster_roles.csv"
CLUSTER_BRANCHES = "data/career_clusters/cluster_branches.csv"
OUTPUT_JSONL     = "data/output/occupation_cards.jsonl"

MAX_RELATED      = 6    # max related careers to show per occupation
JACCARD_THRESHOLD = 0.15 # minimum Jaccard score to count a task pair as overlapping

MODEL      = "claude-sonnet-4-6"
MAX_TOKENS = 1024
TOP_TASKS  = 6  # tasks to include per occupation in prompt context

STOPWORDS = {
    "able", "about", "after", "also", "area", "areas", "based", "been",
    "before", "between", "both", "but", "care", "common", "data", "each",
    "ensure", "from", "have", "help", "high", "identify", "include",
    "information", "into", "make", "may", "more", "most", "need", "needed",
    "other", "over", "perform", "prepare", "process", "provide", "related",
    "report", "required", "review", "same", "such", "than", "that", "their",
    "them", "then", "there", "these", "they", "this", "those", "through",
    "time", "under", "used", "using", "when", "where", "which", "while",
    "will", "with", "work", "working",
}

# ── Loaders ───────────────────────────────────────────────────────────────────

def load_scores() -> dict:
    with open(SCORES_CSV, newline="", encoding="utf-8") as f:
        return {r["Code"]: r for r in csv.DictReader(f)}


def load_task_table() -> dict:
    table: dict[str, list] = {}
    with open(TASK_TABLE, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            table.setdefault(row["onet_code"], []).append(row)
    return table


def load_cluster_data() -> tuple[dict, dict]:
    """
    Returns:
      role_index:   onet_code → {cluster_id, level, is_canonical, ...}
      cluster_roles: cluster_id → [role rows sorted by level]
    """
    role_index = {}
    cluster_roles: dict[str, list] = {}
    with open(CLUSTER_ROLES, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            role_index[r["onet_code"]] = r
            cluster_roles.setdefault(r["cluster_id"], []).append(r)
    for fid in cluster_roles:
        cluster_roles[fid].sort(key=lambda r: int(r["level"]))
    return role_index, cluster_roles


def load_branch_index() -> dict:
    """Returns (from_onet_code, to_onet_code) -> full branch row from cluster_branches.csv."""
    index = {}
    with open(CLUSTER_BRANCHES, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            index[(r["from_onet_code"], r["to_onet_code"])] = r
    return index


def load_jsonl() -> dict:
    """Load occupation_cards.jsonl as dict keyed by onet_code."""
    cards = {}
    if not os.path.exists(OUTPUT_JSONL):
        return cards
    with open(OUTPUT_JSONL, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    card = json.loads(line)
                    cards[card["onet_code"]] = card
                except (json.JSONDecodeError, KeyError):
                    pass
    return cards




def save_jsonl(cards: dict):
    """Write all cards back to JSONL."""
    with open(OUTPUT_JSONL, "w", encoding="utf-8") as f:
        for card in cards.values():
            f.write(json.dumps(card, ensure_ascii=False) + "\n")


# ── Method 1: Career cluster ───────────────────────────────────────────────────

def derive_related_from_cluster(source_code: str,
                                role_index: dict,
                                cluster_roles: dict,
                                branch_index: dict,
                                scores: dict) -> list[tuple[str, str, str]]:
    """
    Returns (onet_code, relationship_type, notes) for roles related via career cluster,
    including same-cluster members, outbound cross-family branches, and inbound
    cross-family branches (entry points). Sorted by final_ranking desc.

    relationship_type priority:
      1. cluster_branches.csv transition_type if an explicit branch exists
      2. level-based fallback: higher level → "progression", same level → "specialization"

    For inbound cross-family branches, relationship_type is "entry_from" — the target
    role commonly feeds into the source role.

    notes: curated transition guidance from cluster_branches.csv, or "" if no branch exists.
    """
    source = role_index.get(source_code)
    if not source:
        return []

    source_level = int(source["level"])
    cluster = cluster_roles.get(source["cluster_id"], [])

    candidates = []
    seen_codes = set()
    for role in cluster:
        code = role["onet_code"]
        if code == source_code:
            continue
        level = int(role["level"])
        if level < source_level - 1:
            continue  # skip roles 2+ levels below; 1 level below allowed as less_trained

        branch = branch_index.get((source_code, code))
        if branch:
            rel_type = branch["transition_type"]
            notes = branch.get("notes", "")
        else:
            if level > source_level:
                rel_type = "progression"
            elif level == source_level:
                rel_type = "specialization"
            else:  # level == source_level - 1
                rel_type = "less_trained"
            notes = ""

        ranking = float(scores.get(code, {}).get("final_ranking", 0) or 0)
        candidates.append((ranking, code, rel_type, notes))
        seen_codes.add(code)

    # Outbound cross-family branches: source → target in a different cluster
    for (from_code, to_code), branch in branch_index.items():
        if from_code != source_code or branch.get("is_cross_family") != "true":
            continue
        if to_code in seen_codes:
            continue
        ranking = float(scores.get(to_code, {}).get("final_ranking", 0) or 0)
        candidates.append((ranking, to_code, branch["transition_type"], branch.get("notes", "")))
        seen_codes.add(to_code)

    # Inbound cross-family branches: external role → source (entry points into this role)
    for (from_code, to_code), branch in branch_index.items():
        if to_code != source_code or branch.get("is_cross_family") != "true":
            continue
        if from_code in seen_codes:
            continue
        ranking = float(scores.get(from_code, {}).get("final_ranking", 0) or 0)
        candidates.append((ranking, from_code, "entry_from", branch.get("notes", "")))
        seen_codes.add(from_code)

    candidates.sort(reverse=True)
    # No cap: include all curated cluster roles regardless of MAX_RELATED
    return [(code, rel_type, notes) for _, code, rel_type, notes in candidates]


# ── Method 2: Task text overlap (Jaccard) ────────────────────────────────────

def task_words(text: str) -> frozenset:
    """Normalize task text to a set of significant words."""
    return frozenset(
        w for w in re.findall(r"[a-z]{4,}", text.lower())
        if w not in STOPWORDS
    )


def build_task_overlap_index(task_table: dict) -> dict[str, list[tuple[str, float, frozenset]]]:
    """
    Returns onet_code -> [(task_text, task_weight, word_set), ...]
    sorted by task_weight descending.
    """
    index = {}
    for code, rows in task_table.items():
        entries = []
        for row in rows:
            weight = float(row.get("task_weight") or 0)
            words = task_words(row["task_text"])
            if words:
                entries.append((row["task_text"], weight, words))
        entries.sort(key=lambda x: x[1], reverse=True)
        index[code] = entries
    return index


def jaccard(a: frozenset, b: frozenset) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def find_by_task_overlap(source_code: str,
                          overlap_index: dict,
                          exclude: set,
                          n: int) -> list[tuple[str, str]]:
    """
    For each source task, find best Jaccard match in every candidate occupation.
    Overlap score = sum of source_task_weight × best_jaccard for tasks above threshold.
    """
    source_tasks = overlap_index.get(source_code, [])
    if not source_tasks:
        return []

    candidate_scores: dict[str, float] = {}
    for _, s_weight, s_words in source_tasks:
        for code, t_tasks in overlap_index.items():
            if code == source_code or code in exclude:
                continue
            best = max((jaccard(s_words, t_words) for _, _, t_words in t_tasks), default=0.0)
            if best >= JACCARD_THRESHOLD:
                candidate_scores[code] = candidate_scores.get(code, 0.0) + s_weight * best

    sorted_candidates = sorted(candidate_scores.items(), key=lambda x: x[1], reverse=True)
    return [(code, "adjacent") for code, _ in sorted_candidates[:n]]


# ── Method 3: SOC code similarity ────────────────────────────────────────────

def find_by_soc_similarity(source_code: str,
                            scores: dict,
                            exclude: set,
                            n: int) -> list[tuple[str, str]]:
    """
    Returns occupations with matching SOC prefix, sorted by final_ranking desc.
    Prefers same 5-digit prefix (XX-XXX), falls back to same 2-digit (XX-).
    """
    prefix5 = source_code[:5]
    prefix2 = source_code[:2]

    matches5, matches2 = [], []
    for code, occ in scores.items():
        if code == source_code or code in exclude:
            continue
        ranking = float(occ.get("final_ranking", 0) or 0)
        if code[:5] == prefix5:
            matches5.append((ranking, code))
        elif code[:2] == prefix2:
            matches2.append((ranking, code))

    matches5.sort(reverse=True)
    matches2.sort(reverse=True)

    result = [(code, "specialization") for _, code in matches5]
    result += [(code, "related") for _, code in matches2]
    return result[:n]


# ── Helpers ───────────────────────────────────────────────────────────────────

def top_tasks(code: str, task_table: dict, n: int = TOP_TASKS) -> list[str]:
    rows = task_table.get(code, [])
    sorted_rows = sorted(rows, key=lambda r: float(r["task_weight"] or 0), reverse=True)
    return [r["task_text"] for r in sorted_rows[:n]]


JOB_ZONE_TO_LEVEL = {1: 1, 2: 1, 3: 2, 4: 3, 5: 4}

def job_zone_to_level(occ: dict, code: str) -> int:
    raw = occ.get("Job Zone", "")
    try:
        zone = int(float(raw))
        level = JOB_ZONE_TO_LEVEL.get(zone)
        if level is None:
            print(f"  ⚠ Unexpected Job Zone {zone!r} for {code} — defaulting to 2")
            return 2
        return level
    except (ValueError, TypeError):
        print(f"  ⚠ Missing Job Zone for {code} — defaulting to 2")
        return 2


def format_growth(occ: dict) -> str:
    raw = occ.get("Employment Change, 2024-2034", "").strip()
    if raw:
        try:
            pct = float(raw)
            rounded = round(pct)
            return f"+{rounded}%" if rounded > 0 else ("0%" if rounded == 0 else f"{rounded}%")
        except ValueError:
            pass
    # Fall back to qualitative Projected Growth label
    _GROWTH_LABEL_MAP = [
        ("Much faster than average", "+7%"),
        ("Faster than average",      "+5%"),
        ("Average",                  "+3%"),
        ("Slower than average",      "+1%"),
        ("Little or no change",      "0%"),
        ("Decline",                  "-1%"),
    ]
    pg = occ.get("Projected Growth", "").strip()
    for key, label in _GROWTH_LABEL_MAP:
        if pg.startswith(key):
            return label
    return "N/A"


def format_openings(occ: dict) -> str:
    raw = occ.get("Projected Job Openings", "").replace(",", "").strip()
    try:
        return f"{int(raw):,}"
    except ValueError:
        return occ.get("Projected Job Openings", "")


def format_salary(occ: dict) -> str:
    import re
    raw = occ.get("Median Wage", "")
    m = re.search(r'\$([\d,]+)\s+annual', raw)
    if m:
        return f"${int(m.group(1).replace(',', '')):,}"
    plain = raw.replace(",", "").replace("$", "").strip()
    try:
        return f"${int(float(plain)):,}"
    except (ValueError, TypeError):
        return ""


# ── Prompt ────────────────────────────────────────────────────────────────────

REL_TYPE_CONTEXT = {
    "progression":    "The target role is a step up from the source role — broader scope, more responsibility, or a higher credential required.",
    "specialization": "The target role is at the same level but focused on a specific setting, population, or subspecialty.",
    "lateral":        "The target role is a sideways move into a different track or field — similar standing, different focus.",
    "less_trained":   "The target role requires less training than the source role — a step down in credential or scope.",
    "adjacent":       "The target role is in a different field but shares significant task overlap with the source role.",
    "related":        "The target role shares tasks or occupational cluster with the source role.",
}


def build_prompt(source_occ: dict, source_tasks: list[str],
                 target_occ: dict, target_tasks: list[str],
                 rel_type: str = "related", notes: str = "") -> str:
    rel_context = REL_TYPE_CONTEXT.get(rel_type, REL_TYPE_CONTEXT["related"])
    notes_section = f"\nCurated transition note: {notes}\n" if notes else ""

    return f"""You are helping someone who works as a {source_occ['Occupation']} understand how they could move into a {target_occ['Occupation']} role.

Relationship context: {rel_context}{notes_section}
Source role: {source_occ['Occupation']}
Top tasks:
{chr(10).join(f'  - {t}' for t in source_tasks)}

Target role: {target_occ['Occupation']}
Top tasks:
{chr(10).join(f'  - {t}' for t in target_tasks)}

Generate a JSON object with two fields:

{{
  "fit": "One sentence. State what's true about the overlap -- what experience carries over and what the key difference is. Feynman style: plain language, no jargon, no instructions. Don't say 'leverage' or 'lean into'. If it's a step up, say so plainly.",
  "steps": ["Concrete step 1", "Concrete step 2", "Concrete step 3"]
}}

Rules for fit:
- One sentence only
- State facts about the overlap, not advice
- Be honest about direction: if relationship_type is "progression", say it's a step up — never call it lateral. If "specialization" or "lateral", say it's a lateral move. If "less_trained", say it's a step down.

Rules for steps:
- 2-3 items maximum
- Each item is a short action phrase, 5-10 words max — no full sentences
- Name the specific credential, tool, or action only
- If a curated transition note is provided, use it to anchor the steps -- treat it as ground truth about the path
- Good: "Pass the NCLEX-RN", "Earn AWS Solutions Architect cert", "Build 3 full-stack portfolio projects"
- Bad: "Take a course to learn about project management so you can demonstrate your skills to employers"

Respond ONLY with the JSON object."""


# ── Generation (API or interactive) ──────────────────────────────────────────

def _parse_fit_learn_response(text: str) -> dict:
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    return json.loads(text.strip())


def generate_fit_learn(client,
                       source_occ: dict, source_tasks: list,
                       target_occ: dict, target_tasks: list,
                       rel_type: str = "related", notes: str = "",
                       interactive: bool = False,
                       print_prompts: bool = False) -> dict | None:
    """
    Returns parsed dict, or None if print_prompts=True (caller must collect responses separately).
    """
    prompt = build_prompt(source_occ, source_tasks, target_occ, target_tasks, rel_type, notes)
    if print_prompts:
        print("\n" + "="*80)
        print(f"PROMPT — {source_occ['Occupation']} → {target_occ['Occupation']}")
        print("="*80)
        print(prompt)
        return None
    if interactive:
        print("\n" + "="*80)
        print(f"PROMPT — {source_occ['Occupation']} → {target_occ['Occupation']}")
        print("="*80)
        print(prompt)
        print("="*80)
        print("\nPaste JSON response, then Enter + Ctrl-D:")
        text = sys.stdin.read().strip()
        return _parse_fit_learn_response(text)
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    return _parse_fit_learn_response(response.content[0].text)


# ── Main ──────────────────────────────────────────────────────────────────────

def process_occupation(source_code: str, scores: dict,
                       task_table: dict, overlap_index: dict,
                       cards: dict, role_index: dict, cluster_roles: dict,
                       branch_index: dict, client,
                       interactive: bool = False,
                       skip_existing: bool = False,
                       print_prompts: bool = False) -> bool:
    source_occ = scores.get(source_code)
    if not source_occ:
        print(f"  ✗ {source_code} not found in scores CSV")
        return False

    print(f"\n── {source_occ['Occupation']} ({source_code})")
    source_tasks = top_tasks(source_code, task_table)

    pairs: list[tuple[str, str, str]] = []
    seen: set[str] = set()

    # Method 1: career cluster
    cluster_pairs = derive_related_from_cluster(source_code, role_index, cluster_roles, branch_index, scores)
    for p in cluster_pairs:
        if p[0] not in seen:
            pairs.append(p)
            seen.add(p[0])
    if cluster_pairs:
        print(f"  Method 1 (cluster):   {len(cluster_pairs)} roles")

    # Method 2: task overlap (no curated notes)
    if len(pairs) < MAX_RELATED:
        overlap_pairs = find_by_task_overlap(
            source_code, overlap_index, seen, MAX_RELATED - len(pairs)
        )
        for p in overlap_pairs:
            if p[0] not in seen:
                pairs.append((p[0], p[1], ""))
                seen.add(p[0])
        if overlap_pairs:
            print(f"  Method 2 (overlap):  {len(overlap_pairs)} roles")

    # Method 3: SOC similarity (no curated notes)
    if len(pairs) < MAX_RELATED:
        soc_pairs = find_by_soc_similarity(source_code, scores, seen, MAX_RELATED - len(pairs))
        for p in soc_pairs:
            if p[0] not in seen:
                pairs.append((p[0], p[1], ""))
                seen.add(p[0])
        if soc_pairs:
            print(f"  Method 3 (SOC):      {len(soc_pairs)} roles")

    if not pairs:
        print(f"  ✗ No related careers found")
        return False

    source_ranking = float(source_occ.get("final_ranking", 0) or 0)
    source_cluster_level = int(role_index[source_code]["level"]) if source_code in role_index else None
    RANKING_DROP_THRESHOLD = 0.15  # drop targets more than 15 pts below source
    filtered_pairs = []
    for target_code, rel_type, notes in pairs:
        target_occ = scores.get(target_code)
        if not target_occ:
            continue
        target_ranking = float(target_occ.get("final_ranking", 0) or 0)

        # Drop if meaningfully lower final_ranking — but only for task-overlap/SOC results,
        # not curated cluster roles (which are always worth including regardless of ranking)
        if rel_type in ("adjacent", "related") and source_ranking - target_ranking > RANKING_DROP_THRESHOLD:
            print(f"  ✗ Skipping {target_occ['Occupation']} — ranking too low ({target_ranking:.2f} vs source {source_ranking:.2f})")
            continue

        # For non-cluster pairs: drop lower cluster level within the same cluster
        if rel_type in ("adjacent", "related"):
            if source_cluster_level is not None:
                target_cluster = role_index.get(target_code)
                if target_cluster and target_cluster.get("cluster_id") == role_index[source_code].get("cluster_id"):
                    if int(target_cluster["level"]) < source_cluster_level:
                        print(f"  ✗ Skipping {target_occ['Occupation']} — lower cluster level")
                        continue

        filtered_pairs.append((target_code, rel_type, notes))

    pairs = filtered_pairs

    if not pairs:
        print(f"  ✗ No related careers remain after filtering")
        return False

    # Build existing node index to support skip_existing
    existing_nodes_by_code = {
        node["code"]: node
        for node in (cards.get(source_code, {}).get("careerCluster") or [])
        if node.get("code")
    }

    realistic_careers = []
    aspirational_careers = []
    for target_code, rel_type, notes in pairs:
        target_occ = scores.get(target_code)
        if not target_occ:
            print(f"  ✗ Target {target_code} not in scores CSV — skipping")
            continue

        # Skip if this pair already has generated fit+steps data
        if skip_existing:
            existing = existing_nodes_by_code.get(target_code)
            if existing and existing.get("fit") and existing.get("steps"):
                print(f"  ↩ {target_occ['Occupation']} ({target_code}) — already generated, skipping")
                continue

        note_indicator = f" [note: {notes[:60]}…]" if notes else ""
        print(f"  → {target_occ['Occupation']} ({target_code}) [{rel_type}]{note_indicator}")
        target_tasks = top_tasks(target_code, task_table)

        # For entry_from: the target_code is the feeder role that transitions INTO
        # source. Swap source/target in the prompt so it reads "helping someone who
        # works as {feeder} move into {source}". Use the branch's transition_type.
        if rel_type == "entry_from":
            branch_row = branch_index.get((target_code, source_code), {})
            prompt_rel_type = branch_row.get("transition_type", "lateral")
            result = generate_fit_learn(client, target_occ, target_tasks,
                                        source_occ, source_tasks, prompt_rel_type, notes,
                                        interactive=interactive,
                                        print_prompts=print_prompts)
        else:
            result = generate_fit_learn(client, source_occ, source_tasks,
                                        target_occ, target_tasks, rel_type, notes,
                                        interactive=interactive,
                                        print_prompts=print_prompts)
        if print_prompts:
            continue  # don't process result — just printing
        final_ranking = float(target_occ.get("final_ranking", 0) or 0)

        # Look up branch — check both directions for cross-family
        branch = branch_index.get((source_code, target_code))
        if not branch:
            branch = branch_index.get((target_code, source_code))
        training_duration = float(branch.get("training_duration_years", 0) or 0) if branch else 0.0
        is_cross_family = branch.get("is_cross_family") == "true" if branch else False

        target_cluster_entry = role_index.get(target_code)
        if target_cluster_entry:
            target_cluster_level = int(target_cluster_entry["level"])
        else:
            target_cluster_level = None
        level_jump = (target_cluster_level - source_cluster_level) if (source_cluster_level is not None and target_cluster_level is not None) else 0

        try:
            source_zone = int(float(source_occ.get("Job Zone", 0)))
            target_zone = int(float(target_occ.get("Job Zone", 0)))
            zone_jump = (target_zone - source_zone) if (source_zone > 0 and target_zone > 0) else 0
        except (ValueError, TypeError):
            zone_jump = 0

        # Cross-family: cluster levels are in different reference frames, use Job Zone only
        effective_level_jump = zone_jump if is_cross_family else level_jump

        # It's realistic if the training is <= 1 year AND neither level nor Job Zone jump is 2+
        if training_duration <= 1.0 and effective_level_jump <= 1 and zone_jump <= 1:
            transition_category = "realistic"
            target_list = realistic_careers
        else:
            transition_category = "aspirational"
            target_list = aspirational_careers

        target_list.append({
            "code":         target_code,
            "title":        target_occ.get("altpath simple title", "").strip() or target_occ["Occupation"],
            "relationship": rel_type,
            "category":     transition_category,
            "training_duration_years": training_duration,
            "score":        round(final_ranking * 100),
            "salary":       format_salary(target_occ),
            "openings":     format_openings(target_occ),
            "growth":       format_growth(target_occ),
            "fit":          result.get("fit", ""),
            "steps":        result.get("steps", result.get("learn", [])),
        })
        print(f"    fit:   {result.get('fit', '')}")
        print(f"    steps: {result.get('steps', result.get('learn', []))}")

    all_transitions = realistic_careers + aspirational_careers
    all_transitions.sort(key=lambda r: r["score"], reverse=True)

    if source_code not in cards:
        cards[source_code] = {"onet_code": source_code}

    # Build a lookup from code → transition data, then merge into careerCluster nodes.
    # careerCluster stores the full node list including transition detail fields.
    transition_by_code = {r["code"]: r for r in all_transitions}

    existing_cluster = cards[source_code].get("careerCluster") or []
    # Index existing nodes by code (or title for emerging)
    cluster_by_key: dict[str, dict] = {}
    for node in existing_cluster:
        key = node.get("code") or node.get("title")
        cluster_by_key[key] = node

    # Determine which codes are in the same cluster as source
    source_cluster_id = role_index[source_code]["cluster_id"] if source_code in role_index else None

    # Upsert: merge transition data into existing cluster nodes, or add new nodes
    for code, t in transition_by_code.items():
        target_cluster = role_index.get(code)
        in_same_cluster = (
            target_cluster is not None and
            source_cluster_id is not None and
            target_cluster["cluster_id"] == source_cluster_id
        )
        is_adjacent = not in_same_cluster

        if code in cluster_by_key:
            node = cluster_by_key[code]
        else:
            # Resolve level: same-cluster uses cluster level; cross-cluster uses
            # target's own cluster level if available, else Job Zone fallback
            if in_same_cluster:
                resolved_level = int(target_cluster["level"])
            elif target_cluster:
                resolved_level = int(target_cluster["level"])
            else:
                target_occ_data = scores.get(code, {})
                resolved_level = job_zone_to_level(target_occ_data, code)
            node = {
                "code": code,
                "title": t["title"],
                "level": resolved_level,
                "isCurrent": False,
            }
            cluster_by_key[code] = node

        if is_adjacent:
            node["isAdjacent"] = True
        if t["relationship"] == "entry_from":
            node["isEntryPoint"] = True
        node["relationship"] = t["relationship"]
        node["salary"]       = t["salary"]
        node["openings"]     = t["openings"]
        node["growth"]       = t["growth"]
        node["fit"]          = t["fit"]
        node["steps"]        = t["steps"]

    cards[source_code]["careerCluster"] = list(cluster_by_key.values())

    save_jsonl(cards)
    print(f"\n  ✓ Updated careerCluster transitions for {source_occ['Occupation']}")
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--code", help="Single O*NET code to process")
    parser.add_argument("--all",  action="store_true", help="Process all codes in scores CSV")
    parser.add_argument("--interactive", action="store_true",
                        help="Print prompts to stdout and read JSON responses from stdin (no API key needed)")
    parser.add_argument("--print-prompts", action="store_true",
                        help="Print all prompts to stdout without waiting for responses (for Claude Code inline workflow)")
    parser.add_argument("--skip-existing", action="store_true",
                        help="Skip pairs that already have fit+steps data in careerCluster")
    args = parser.parse_args()

    if not args.code and not args.all:
        parser.print_help()
        sys.exit(1)

    print("Loading data...")
    scores        = load_scores()
    task_table    = load_task_table()
    cards         = load_jsonl()
    role_index, cluster_roles = load_cluster_data()
    branch_index  = load_branch_index()

    print("Building task overlap index...")
    overlap_index = build_task_overlap_index(task_table)

    print_prompts = getattr(args, "print_prompts", False)

    client = None
    if not args.interactive and not print_prompts:
        try:
            client = anthropic.Anthropic()
        except Exception as e:
            print(f"✗ Anthropic client error: {e}")
            sys.exit(1)

    codes = list(scores.keys()) if args.all else [args.code]

    skip_existing = getattr(args, "skip_existing", False)

    for code in codes:
        process_occupation(code, scores, task_table, overlap_index,
                           cards, role_index, cluster_roles, branch_index, client,
                           interactive=args.interactive,
                           skip_existing=skip_existing,
                           print_prompts=print_prompts)

    print("\n✓ Done")


if __name__ == "__main__":
    main()
