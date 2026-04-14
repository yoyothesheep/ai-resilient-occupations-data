#!/usr/bin/env python3
"""
Generate career page content for each occupation.

For each occupation, produces: risks, opportunities, howToAdapt, sources.
Passes through: score, salary, openings, growth, jobTitles, keyDrivers, taskData.

Modes:
  Interactive (default): script prints a prompt, you paste it into Claude,
    then paste the JSON response back.
  --print-prompt: script prints the prompt and exits immediately (no API call,
    no stdin read). Claude Code reads the prompt output and authors the JSON
    directly, writing it to occupation_cards.jsonl via the Write tool.
  --api: script calls the Claude API automatically. Requires ANTHROPIC_API_KEY.

Inline workflow (Claude Code, no API key):
    python3 scripts/generate_next_steps.py --code 15-1254.00 --print-prompt
    # Claude Code reads the printed prompt, authors JSON, appends to JSONL.
    python3 scripts/generate_next_steps.py --code 15-1254.00 --print-prompt --force
    # --force re-generates even if the code already has a card.

Usage:
    python3 scripts/generate_next_steps.py --code 15-1254.00
    python3 scripts/generate_next_steps.py --batch 3   # next 3 unprocessed

Output:
    data/output/occupation_cards.jsonl  — one JSON object per line
"""

import argparse
import csv
import json
import os
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
API_MODEL = "claude-opus-4-6"

# ── Config ────────────────────────────────────────────────────────────────────
SCORES_CSV    = "data/output/ai_resilience_scores.csv"
TASK_TABLE    = "data/intermediate/onet_economic_index_task_table.csv"
OCC_METRICS   = "data/intermediate/onet_economic_index_metrics.csv"
SCORE_LOG     = "data/output/score_log.txt"
TONE_GUIDE       = "docs/tone_guide_career_pages.md"
CAREER_SPEC      = "docs/career_page_spec.md"
APPROVED_SOURCES = "docs/approved_sources.md"

TOP_N_TASKS   = 10   # tasks to include in taskData

STANDARD_TASK_INTRO = "Not all tasks are affected equally. Knowing which ones AI handles well, and which still need a human, is how to focus skill-building."

# ── Loaders ───────────────────────────────────────────────────────────────────

def load_scores() -> dict:
    """Load scores CSV keyed by onet_code."""
    with open(SCORES_CSV, newline="", encoding="utf-8") as f:
        return {r["Code"]: r for r in csv.DictReader(f)}


def load_task_table() -> dict:
    """Load task table keyed by onet_code → list of task rows."""
    table: dict[str, list] = {}
    with open(TASK_TABLE, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            code = row["onet_code"]
            table.setdefault(code, []).append(row)
    return table


def load_occ_metrics() -> dict:
    """Load occupation-level AEI metrics keyed by onet_code."""
    with open(OCC_METRICS, newline="", encoding="utf-8") as f:
        return {r["onet_code"]: r for r in csv.DictReader(f)}


def load_a_scores(log_path: str) -> dict:
    """
    Parse score_log.txt to extract A1-A10 per occupation.
    Returns dict: onet_code -> {a1: int, ..., a10: int}
    """
    a_scores: dict[str, dict] = {}
    pattern_occ = re.compile(r"^\s+(.+?)\s+\((\d{2}-\d{4}\.\d{2})\)")
    pattern_attr = re.compile(r"^\s+A(\d+)\s+.+?:\s+(\d+)")
    current_code = None

    with open(log_path, encoding="utf-8") as f:
        for line in f:
            m = pattern_occ.match(line)
            if m:
                current_code = m.group(2)
                a_scores[current_code] = {}
                continue
            if current_code:
                m2 = pattern_attr.match(line)
                if m2:
                    a_scores[current_code][f"a{m2.group(1)}"] = int(m2.group(2))
    return a_scores


def load_existing_codes() -> set:
    """Return set of onet_codes already saved as individual card files."""
    from cards import load_existing_codes as _load
    return _load()


def load_text(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


# ── Task data builder ─────────────────────────────────────────────────────────

def build_task_data(onet_code: str, task_rows: list) -> list:
    """
    Top N tasks by task_weight. Returns list of taskData dicts.
    AEI fields are None when not in AEI.
    Short labels are applied later from the interactive JSON response.
    """

    def safe_float(val):
        try:
            return round(float(val), 1) if val not in ("", None) else None
        except (ValueError, TypeError):
            return None

    def safe_int(val):
        try:
            return int(float(val)) if val not in ("", None) else None
        except (ValueError, TypeError):
            return None

    def aei_boost(r):
        """Confidence-scaled AEI boost: 1.0 → 1.5 as n goes 0 → 100."""
        base = float(r["task_weight"]) if r["task_weight"] else 0
        if r.get("in_aei", "").lower() != "true":
            return base
        try:
            n = int(float(r["onet_task_count"]))
        except (ValueError, TypeError):
            n = 0
        boost = 1.0 + 0.5 * min(n / 100.0, 1.0)
        return base * boost

    sorted_rows = sorted(task_rows, key=aei_boost, reverse=True)[:TOP_N_TASKS]

    result = []
    for r in sorted_rows:
        n = safe_int(r.get("onet_task_count"))
        has_signal = r.get("in_aei", "").lower() == "true" and n is not None
        result.append({
            "task":    r["task_text"],
            "full":    r["task_text"],
            "weight":  round(float(r["task_weight"]), 1) if r.get("task_weight") else None,
            "auto":    safe_float(r.get("automation_pct"))    if has_signal else None,
            "aug":     safe_float(r.get("augmentation_pct"))  if has_signal else None,
            "success": safe_float(r.get("task_success_pct"))  if has_signal else None,
            "n":       n if has_signal else None,
        })
    return result


# ── Prompt builder ────────────────────────────────────────────────────────────

def build_prompt(occ: dict, tasks: list, metrics: dict, a_scores: dict,
                 tone_guide: str, career_spec: str, approved_sources: str = "") -> str:
    code = occ["Code"]
    title = occ["Occupation"]
    score = occ.get("role_resilience_score", "?")
    final_ranking = occ.get("final_ranking", "")

    a = a_scores.get(code, {})
    a_block = "\n".join(
        f"  A{i}: {a.get(f'a{i}', '?')}" for i in range(1, 11)
    )

    m = metrics.get(code, {})
    coverage = m.get("ai_task_coverage_pct", "unknown")
    w_auto   = m.get("weighted_automation_pct", "unknown")
    w_aug    = m.get("weighted_augmentation_pct", "unknown")

    # Compute low data confidence from task data directly
    tasks_with_signal = [t for t in tasks if t.get("n") is not None and t["n"] >= 100]
    low_data = len(tasks_with_signal) == 0

    task_lines = []
    for t in tasks:
        if t["n"] is not None:
            task_lines.append(
                f"  - {t['full']}\n"
                f"    weight={t.get('weight','?')} | auto={t['auto']}% aug={t['aug']}% "
                f"success={t['success']}% n={t['n']}"
            )
        else:
            task_lines.append(f"  - {t['full']}\n    weight=? | no AEI data")

    task_block = "\n".join(task_lines)

    # Build common names line from sample job titles
    sample_titles = occ.get("Sample Job Titles", "").strip()
    if sample_titles:
        common_names_line = f"Also known as: {sample_titles}\n"
    else:
        common_names_line = ""

    return f"""You are generating career page content for ai-proof-careers.com.

Below are your style rules. Follow them exactly.

=== TONE GUIDE ===
{tone_guide}

=== CAREER PAGE SPEC ===
{career_spec}

=== OCCUPATION DATA ===
Title: {title}
{common_names_line}O*NET Code: {code}
Role Resilience Score: {score} / 5.0
Final Ranking: {final_ranking} (0–1 scale)

Attribute Scores (1–5):
{a_block}

AEI Coverage: {coverage}% of tasks observed in AI usage data
Weighted automation %: {w_auto}
Weighted augmentation %: {w_aug}

Top tasks by importance × frequency (with AEI data where available):
{task_block}

=== YOUR TASK ===

Search for 2–3 authoritative sources about AI's impact on this occupation ({title}). Use the common job titles listed above when searching, not the formal O*NET name. Select sources from the approved list below — prioritize domain-specific sources for this occupation type over generic ones.

=== APPROVED SOURCES ===
{approved_sources}
=== END APPROVED SOURCES ===

Rules:
- Prefer sources published within the last 2 years. Flag if best available is older than 12 months.
- BLS salary, openings, and growth data is already in our dataset — cite BLS as a source without fetching it.
- Always include a real canonical URL for every source. Do not leave url blank. URLs will be validated automatically.
- Do not cite the same source more than twice across the entire card (risks, opportunities, howToAdapt combined). Each section (risks.body, opportunities.body, howToAdapt.alreadyIn, howToAdapt.thinkingOf) must use at least 2 distinct sources internally — never repeat the same [N] more than once within a single section.
- NEVER cite: Gartner, IDC, Forrester, MarketsandMarkets — these are paywalled analyst firms with inflated projections and URL rot. Use the approved sources list instead.

{"⚠ LOW DATA WARNING: None of the tasks for this occupation have sufficient AEI data (n >= 100). The task chart on the career page will show ALL tasks in the 'AI hasn't figured these out' bucket. DO NOT cite external automation percentages (e.g. McKinsey industry estimates) as the risks stat — they will directly contradict the chart. Instead: (1) Keep risks.body brief and acknowledge limited AEI signal. (2) Use a hiring trend, job growth, or demand stat for risks.stat instead of an automation rate. (3) For opportunities, cite augmentation demand or skill premium stats." if low_data else ""}
Then generate the following JSON object. All prose must follow the tone guide.

{{
  "onet_code": "{code}",
  "risks": {{
    "body": "2–3 sentences about why AI is a genuine threat to this specific role's job prospects — not 'AI is advancing' but what specifically is being automated, commoditized, or consolidated in THIS occupation. Include a concrete displacement signal (posting decline, layoffs, role consolidation, or a specific task now handled by AI tools). Do NOT frame workforce shortages as risks — a shortage drives up demand and is good for workers. {"LOW DATA: Do NOT cite external automation percentages in this section — the task chart will show no AI activity and they will directly contradict each other. Focus on hiring trends, job growth projections, or platform displacement instead." if low_data else ""}Inline citations like [1] where sourced. NEVER mention task weight values or write phrases like '(weight 20.9)' — weight is an internal metric, not user-facing content. NEVER cite the number of AI conversations or interactions (e.g. 'across 2,800 AI interactions', 'n=702 observations') — these are internal dataset counts, not user-facing evidence. If citing AEI task automation rates, summarize the pattern in one sentence rather than listing rates per individual task; PREFER leading with an external displacement signal (posting trends, layoffs, platform consolidation) over AEI percentages — use AEI data as supporting color, not the headline. AVOID: vague 'AI will transform this field' framing, generic white-collar displacement narratives, repeating the role score. PREFER: name a specific task or workflow AI handles well in this role, cite a concrete displacement signal, connect it to what practitioners in THIS role actually experience.",
    "stat": "Pick the single most concrete, surprising number from the risks body. Set to null if no strong non-redundant stat exists. {"LOW DATA: Must NOT be an automation rate or AI task percentage — the task chart shows no AI activity and they will directly contradict." if low_data else ""} STAT SELECTION RULES — AVOID these (redundant with other page sections): task automation/augmentation %, employment growth %, salary figures. PREFER (in priority order): (1) Hiring trend shifts — YoY change in job postings, time-to-fill changes (Lightcast, Indeed Hiring Lab). (2) AI tool adoption rates among practitioners in THIS specific role (HubSpot State of Marketing, CMI, Stack Overflow Survey, etc). (3) Productivity/output impact — e.g. content volume increase, time-to-draft reduction. (4) Displacement signals — layoffs, role consolidation, posting declines, freelance rate compression (Upwork Research Institute). (5) WEF Future of Jobs net decline ranking or projected job loss figure. (6) Industry ad spend or budget shift away from human production toward AI tools. (7) Contract/freelance ratio shifts. (8) Career transition rates out of this role. LAST RESORT: BLS projected growth/decline % for this occupation — always available, always citable, acceptable when nothing better exists. It is OK to set stat to null rather than use a redundant stat type.",
    "statLabel": "Required if stat is non-null. Short phrase describing the stat. E.g. 'drop in entry-level tech hiring (2024)'",
    "statSourceName": "Required if stat is non-null. Publisher name, e.g. 'Lightcast' or 'World Economic Forum'.",
    "statSourceTitle": "Required if stat is non-null. Full article or report title.",
    "statSourceDate": "Required if stat is non-null. Publication date as 'Mon YYYY', e.g. 'Jan 2025'.",
    "statSourceUrl": "Required if stat is non-null. Canonical URL. Must be a real, verifiable URL."
  }},
  "opportunities": {{
    "body": "2–3 sentences about why a skilled practitioner in this role is harder to replace than the risks section suggests — what tasks require human judgment, relationship, or accountability that AI cannot replicate, and what that means economically for practitioners who lean into it. Inline citations like [1]. NEVER mention numeric task weight values (e.g. 'weight 20.9') — say 'most important task' or 'core task' instead. NEVER cite the number of AI conversations or interactions (e.g. 'across 2,800 AI interactions', 'n=702 observations') — these are internal dataset counts, not user-facing evidence. If citing AEI augmentation or low-automation rates, summarize the pattern in one sentence rather than listing rates per task; PREFER leading with an external durability signal (trust requirements, regulatory constraints, client relationship data) over AEI percentages — use AEI data as supporting color, not the headline. AVOID: generic 'use AI as a tool' framing, vague upskilling advice, restating what the risks section already said, citing AI adoption rates without connecting to practitioner outcomes. PREFER: identify the specific tasks or client interactions where human judgment is irreplaceable in this role, name a concrete economic upside (premium, expanded scope, or a market the role now serves that it couldn't before), make it specific enough that a practitioner in this field would recognize it.",
    "stat": "Pick the single most concrete number from the opportunities body. Set to null if no strong non-redundant stat exists. MUST be completely different from the stat used in the risks section. Do not reuse the same statistic. STAT SELECTION RULES — AVOID these (redundant with other page sections): task automation/augmentation %, employment growth %, salary figures. PREFER (in priority order): (1) Skill or certification salary premiums. (2) Client/consumer trust or preference for human-produced content/advice (Pew, Edelman, Reuters Institute, Kantar). (3) Downstream demand creation or market expansion driven by AI — e.g. content volume growth creating more editorial/strategy need. (4) Regulatory or licensing barriers that structurally limit automation. (5) AI tool adoption rates showing human-AI collaboration patterns (HubSpot, CMI, Influencer Marketing Hub). (6) Industry investment in AI for this domain, or budget growth for AI-augmented roles. (7) Productivity multipliers from AI tools in this role — output per practitioner gains. (8) Demand growth for senior/strategic roles as AI handles execution-layer work. LAST RESORT: BLS projected growth/decline % for this occupation — always available, always citable, acceptable when nothing else fits. It is OK to set stat to null rather than use a redundant stat type.",
    "statLabel": "Required if stat is non-null. 5–8 words max. Complete the sentence naturally after the number — e.g. '66%' + 'of developers report X'. Do NOT include a year or date in parentheses — mention it in the body instead.",
    "statSourceName": "Required if stat is non-null. Publisher name.",
    "statSourceTitle": "Required if stat is non-null. Full article or report title.",
    "statSourceDate": "Required if stat is non-null. Publication date as 'Mon YYYY'.",
    "statSourceUrl": "Required if stat is non-null. Canonical URL. Must be a real, verifiable URL."
  }},
  "howToAdapt": {{
    "alreadyIn": "3–4 sentences structured in two parts. Part 1 (immediate): one concrete action to take now. Part 2 (6-month): where to build depth over time — the areas AI handles worst for this specific role. Inline citations. Do NOT use em dashes.",
    "thinkingOf": "3–4 sentences for someone considering entering this field. Concrete portfolio or credential advice specific to this role — not generic 'learn AI tools' advice. Do NOT repeat statistics already cited in the risks section. Inline citations. Do NOT use em dashes. Do NOT cite the same source more than once within this section — each inline citation must reference a different source.",
    "quotes": [
      {{
        "persona": "alreadyIn",
        "quote": "A real quote from a named practitioner, industry leader, or research report about HOW to adapt in this role — a specific skill shift, tool adoption, or strategic move. Must reinforce the alreadyIn advice above. Must come from sources[]. QUOTE QUALITY RULES: (1) Prefer quotes from named individuals (practitioners, executives, researchers) over paraphrased data points. (2) NEVER manufacture a 'quote' by restating a BLS statistic or O*NET task description in quotation marks — that is not a quote. (3) Good sources for real quotes: HBR interviews, MIT Sloan, practitioner blogs (Pragmatic Engineer, InfoQ), industry association reports with practitioner commentary, major newspapers (NYT, WSJ) interviewing professionals. (4) If no real practitioner quote exists, use a key finding from a research report — but attribute it to the report, not to a person.",
        "attribution": "Person's name and title (preferred), or 'Report Title, Publisher' if no named person",
        "sourceId": "src-N"
      }},
      {{
        "persona": "alreadyIn",
        "quote": "A SECOND quote covering a DIFFERENT adaptation angle than the first (e.g. first = tool adoption, second = skill shift). Same quality rules as above. Omit entirely if no meaningfully different second angle exists.",
        "attribution": "...",
        "sourceId": "src-N"
      }},
      {{
        "persona": "thinkingOf",
        "quote": "A real quote about HOW to enter or position yourself in this field — credentials, portfolio approach, or entry strategy. NOT a generic growth stat. Same quality rules: prefer named practitioners, never manufacture quotes from BLS/O*NET data.",
        "attribution": "...",
        "sourceId": "src-N"
      }},
      {{
        "persona": "thinkingOf",
        "quote": "A SECOND quote covering a DIFFERENT entry angle than the first. Same quality rules. Omit if no meaningfully different second angle exists.",
        "attribution": "...",
        "sourceId": "src-N"
      }}
    ]
  }},
  "taskLabels": {{
    "Full task text here...": "3-5 word short label. Verb + object style. Use / for combined verbs (Write/analyze programs). Condense, don't truncate — capture the meaning, not the first N words."
  }},
  "sources": [
    {{"id": "src-1", "name": "Publisher name", "title": "Article or report title", "date": "Mon YYYY", "url": "https://..."}}
  ]
}}

Rules:
- All [n] inline citations must resolve to an entry in sources
- statLabel must end with a source citation like [n] matching a source in sources[]. The stat does NOT need to appear in the body text — it is displayed separately as a pull-stat callout above the prose.
- Do not use "lean into", "AI is taking over", or other prohibited phrases from the tone guide
- Quotes: each must be about adaptation or entry strategy, not generic job market stats. All 4 must cover different topics. A growth projection alone is not an adaptation quote — only use it if the quote also says what to DO about it. Do not use static credential requirements ("typically need a bachelor's degree") — these are timeless facts, not adaptation advice. Every quote must pass this test: "Would this quote have been different 5 years ago?" If no, it's too generic. At most 1 quote across all 4 slots may come from BLS Occupational Outlook Handbook — if you use it, the other 3 must come from different sources. NEVER restate a BLS statistic or O*NET task description in quotation marks and call it a "quote" — quotes must be real quotes from real people or key findings from research reports. Prefer practitioner voices: HBR, MIT Sloan, Pragmatic Engineer, InfoQ, industry association reports with named commentators, NYT/WSJ interviews.
- Respond ONLY with the JSON object, no other text
"""


# ── Interactive (inline) generation ──────────────────────────────────────────

def generate_career_page_interactive(prompt: str) -> dict:
    """Print the prompt and read the JSON response from stdin."""
    print("\n" + "="*80)
    print("PROMPT — paste this into your Claude conversation:")
    print("="*80)
    print(prompt)
    print("="*80)
    print("\nPaste the JSON response below, then press Enter + Ctrl-D (or Ctrl-Z on Windows):")
    text = sys.stdin.read().strip()
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    return json.loads(text)



# ── API generation ────────────────────────────────────────────────────────────

def parse_json_robust(text: str):
    """Extract first valid JSON object/array from text."""
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    text = text.strip()
    depth = 0
    in_string = False
    escape = False
    start_idx = -1
    for i, char in enumerate(text):
        if escape:
            escape = False
            continue
        if char == "\\":
            escape = True
            continue
        if char == '"' and not escape:
            in_string = not in_string
        if in_string:
            continue
        if char in "[{":
            if depth == 0:
                start_idx = i
            depth += 1
        elif char in "]}":
            depth -= 1
            if depth == 0 and start_idx != -1:
                return json.loads(text[start_idx:i + 1])
    return json.loads(text)


def generate_career_page_api(prompt: str) -> dict:
    """Call Claude API to generate career page JSON."""
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    import urllib.parse

    payload = json.dumps({
        "model": API_MODEL,
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        body = json.loads(resp.read())

    text = body["content"][0]["text"]
    return parse_json_robust(text)


# ── Pass-through builder ──────────────────────────────────────────────────────

def build_passthrough(occ: dict, task_data: list) -> dict:
    """Build all pass-through fields from enriched data."""
    final_ranking = float(occ.get("final_ranking", 0) or 0)

    # Format growth: prefer numeric Employment Change if available
    growth_raw = occ.get("Employment Change, 2024-2034", "").strip()
    if growth_raw:
        try:
            pct = float(growth_raw)
            rounded = round(pct)
            growth = f"+{rounded}%" if rounded > 0 else ("0%" if rounded == 0 else f"{rounded}%")
        except ValueError:
            growth = "N/A"
    else:
        # Fall back to Projected Growth string label
        _GROWTH_LABEL_MAP = [
            ("Much faster than average", "+7%"),
            ("Faster than average",      "+5%"),
            ("Average",                  "+3%"),
            ("Slower than average",      "+1%"),
            ("Little or no change",      "0%"),
            ("Decline",                  "-1%"),
        ]
        pg = occ.get("Projected Growth", "").strip()
        growth = pg  # keep raw string if no match
        for key, label in _GROWTH_LABEL_MAP:
            if pg.startswith(key):
                growth = label
                break

    # Format openings with comma separator
    openings_raw = occ.get("Projected Job Openings", "").replace(",", "").strip()
    try:
        openings = f"{int(openings_raw):,}"
    except ValueError:
        openings = occ.get("Projected Job Openings", "")

    # Parse job titles: merge single-word segments back onto the previous title
    # (e.g. "Air Traffic Control Specialist, Terminal" is one title, not two)
    raw_titles = [t.strip() for t in occ.get("Sample Job Titles", "").split(",") if t.strip()]
    titles = []
    for seg in raw_titles:
        if titles and " " not in seg:
            titles[-1] = titles[-1] + ", " + seg
        else:
            titles.append(seg)

    # Extract annual salary only (e.g. "$69.51 hourly, $144,580 annual" → "$144,580")
    wage_raw = occ.get("Median Wage", "")
    annual_match = re.search(r"(\$[\d,]+)\s+annual", wage_raw)
    salary = annual_match.group(1) if annual_match else wage_raw

    emerging_titles = [t.strip() for t in occ.get("Emerging Job Titles", "").split(";") if t.strip()]

    return {
        "score":          round(final_ranking * 100),
        "salary":         salary,
        "openings":       openings,
        "growth":         growth,
        "jobTitles":      titles,
        "emergingTitles": emerging_titles,
        "keyDrivers":     occ.get("key_drivers", ""),
        "taskData":       task_data,
    }


# ── Sanitizer ─────────────────────────────────────────────────────────────────

def sanitize(obj):
    """Recursively replace em-dashes with commas and normalize comma spacing in all string values."""
    if isinstance(obj, str):
        s = obj.replace("\u2014", ",")
        s = re.sub(r"\s*,\s*(?=[a-zA-Z])", ", ", s)  # normalize: word, word (not digits — avoids breaking "16,800")
        return s
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize(item) for item in obj]
    return obj


# ── URL + date validation ──────────────────────────────────────────────────────

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
        # Check if redirected — verify final URL is not a homepage or different domain
        final_url = resp.url
        if final_url != url:
            parsed_orig  = urllib.parse.urlparse(url)
            parsed_final = urllib.parse.urlparse(final_url)
            if parsed_final.netloc and parsed_final.netloc != parsed_orig.netloc:
                print(f"  ⚠ Cross-domain redirect: {url} → {final_url}")
                return False
            # Same-domain redirect: flag if final path is much shorter (likely homepage)
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


TRUSTED_DOMAINS = {
    "bls.gov", "onetcenter.org", "onetonline.org",
    "weforum.org", "mckinsey.com", "nber.org",
    "stackoverflow.co", "survey.stackoverflow.co",
    "github.blog", "github.com",
    "anthropic.com", "economicgraph.linkedin.com",
    "nar.realtor", "realtor.org",
}

def validate_sources(sources: list) -> list:
    """Check each source URL and date; warn and clear dead URLs; warn on old dates.

    Trusted domains (BLS, etc.) are still checked, but 403s are tolerated since
    these sites block headless requests. Other failures (404, bad redirects) are
    caught even for trusted domains.
    """
    import urllib.parse
    cutoff_year = datetime.now().year - 2
    for s in sources:
        url = s.get("url", "")
        if url:
            domain = urllib.parse.urlparse(url).netloc.lstrip("www.")
            is_trusted = any(domain == d or domain.endswith("." + d) for d in TRUSTED_DOMAINS)
            if not check_url(url):
                if is_trusted:
                    # Trusted domains often return 403 to bots — warn but keep URL
                    print(f"  ℹ Trusted domain URL not verifiable (likely bot-blocked): {url}")
                else:
                    print(f"  ⚠ Dead URL cleared: {url}")
                    s["url"] = ""
        date_str = s.get("date", "")
        if date_str:
            try:
                pub_date = datetime.strptime(date_str, "%b %Y")
                if pub_date.year < cutoff_year:
                    print(f"  ⚠ Source older than 2 years: {date_str} — {s.get('title', s.get('name', ''))}")
            except ValueError:
                pass
    return sources


# ── Writer ────────────────────────────────────────────────────────────────────

def append_career_page(card: dict):
    from cards import load_cards, save_card, CARDS_DIR
    existing = load_cards()
    onet_code = card["onet_code"]
    replaced = onet_code in existing
    # Preserve fields owned by other pipeline scripts (adjacent_roles.py)
    if replaced:
        for preserve_key in ("careerCluster", "adjacentRoles", "careerLadder"):
            if existing[onet_code].get(preserve_key):
                card.setdefault(preserve_key, existing[onet_code][preserve_key])
    save_card(card)
    action = "Replaced" if replaced else "Written"
    print(f"  ✓ {action} data/output/cards/{onet_code}.json")


# ── Main ──────────────────────────────────────────────────────────────────────

def verify_generated(generated: dict, low_data: bool):
    """
    Verify generated content for known quality issues. Logs warnings and auto-fixes
    where safe; otherwise prints a clear warning for manual review.
    """
    risks = generated.get("risks", {})
    opportunities = generated.get("opportunities", {})
    stat = risks.get("stat") or ""
    body = risks.get("body") or ""

    # Low-data check: external automation % in risks stat contradicts task chart
    if low_data and "%" in stat:
        automation_words = {"automat", "ai task", "task coverage", "of tasks"}
        label = (risks.get("statLabel") or "").lower()
        body_lower = body.lower()
        if any(w in label or w in body_lower for w in automation_words):
            print(f"  ⚠ VERIFY: low-data occupation but risks.stat looks like an automation rate: '{stat} {risks.get('statLabel')}' — consider rerunning with --force")

    # Citation check: all [n] markers in body/opportunities must resolve to a source
    # Also flag sections that repeat the same source without variety
    sources = {s["id"]: s for s in generated.get("sources", [])}
    sections = [
        ("risks.body", body),
        ("opportunities.body", (generated.get("opportunities") or {}).get("body") or ""),
        ("howToAdapt.alreadyIn", (generated.get("howToAdapt") or {}).get("alreadyIn") or ""),
        ("howToAdapt.thinkingOf", (generated.get("howToAdapt") or {}).get("thinkingOf") or ""),
    ]
    for section_name, text in sections:
        citations = re.findall(r'\[(\d+)\]', str(text))
        for match in citations:
            src_id = f"src-{match}"
            if src_id not in sources:
                print(f"  ⚠ VERIFY: {section_name} cites [{match}] but src-{match} not in sources[]")
        unique = set(citations)
        if len(citations) >= 2 and len(unique) == 1:
            print(f"  ⚠ VERIFY: {section_name} repeats the same source [{citations[0]}] for all citations — needs a second source")

    # Redundant stat check: flag stats that duplicate info already on the page
    # Also check if risks and opportunities have exactly the same stat and label
    r_stat = (risks.get("stat") or "").lower()
    o_stat = (opportunities.get("stat") or "").lower()
    r_label = (risks.get("statLabel") or "").lower()
    o_label = (opportunities.get("statLabel") or "").lower()
    
    if r_stat and o_stat and r_stat == o_stat and r_label == o_label:
        print(f"  ⚠ VERIFY: risks and opportunities have the exact same stat: '{r_stat} {r_label}'. Consider rerunning.")
    _REDUNDANT_PATTERNS = {
        "automation rate", "augmentation rate", "automatable", "weighted automation",
        "projected employment", "employment growth", "job growth through",
        "projected job growth", "median annual", "median salary",
    }
    for section_key in ("risks", "opportunities"):
        sec = generated.get(section_key) or {}
        s_label = (sec.get("statLabel") or "").lower()
        s_stat = (sec.get("stat") or "").lower()
        combined = f"{s_stat} {s_label}"
        for pat in _REDUNDANT_PATTERNS:
            if pat in combined:
                print(f"  ⚠ VERIFY: {section_key}.stat looks redundant with page data ('{pat}'): "
                      f"'{sec.get('stat')} {sec.get('statLabel')}' — prefer hiring trends, adoption rates, or skill premiums")
                break

    # Quote source check
    for q in (generated.get("howToAdapt") or {}).get("quotes", []):
        src_id = q.get("sourceId", "")
        if src_id and src_id not in sources:
            print(f"  ⚠ VERIFY: quote sourceId '{src_id}' not in sources[]")

    # Quote source diversity check
    for persona in ("alreadyIn", "thinkingOf"):
        pq = [q for q in (generated.get("howToAdapt") or {}).get("quotes", [])
              if q.get("persona") == persona]
        if len(pq) >= 2:
            ids = [q.get("sourceId") for q in pq if q.get("sourceId")]
            if len(ids) >= 2 and len(set(ids)) == 1:
                print(f"  ⚠ VERIFY: howToAdapt quotes[{persona}] all cite {ids[0]} — each quote needs a different source")


def process_occupation(code: str, scores: dict, task_table: dict, occ_metrics: dict,
                       a_scores: dict, tone_guide: str, career_spec: str,
                       approved_sources: str = "",
                       print_prompt_only: bool = False, api_mode: bool = False):
    occ = scores.get(code)
    if not occ:
        print(f"  ✗ Code {code} not found in scores CSV")
        return

    print(f"\n── {occ['Occupation']} ({code})")

    tasks = build_task_data(code, task_table.get(code, []))
    prompt = build_prompt(occ, tasks, occ_metrics, a_scores, tone_guide, career_spec, approved_sources)

    if print_prompt_only:
        print("\n" + "="*80)
        print(prompt)
        print("="*80)
        return

    if api_mode:
        print("  Calling Claude API...")
        generated = generate_career_page_api(prompt)
    else:
        generated = generate_career_page_interactive(prompt)

    # Apply short labels from the interactive response
    task_labels = {k.strip(): v for k, v in generated.pop("taskLabels", {}).items()}
    for t in tasks:
        full = t["full"].strip()
        if full in task_labels:
            t["task"] = task_labels[full]
        else:
            # Fuzzy match: find a key that starts with the first 30 chars of full text
            prefix = full[:30].lower()
            match = next((v for k, v in task_labels.items() if k.lower().startswith(prefix[:20])), None)
            if match:
                t["task"] = match
            elif t["task"] == t["full"]:
                # Last resort: first 5 words — should not happen if Claude returns taskLabels correctly
                words = t["full"].split()
                t["task"] = " ".join(words[:5]).rstrip(".,;") + ("…" if len(words) > 5 else "")

    # Validate source URLs and dates
    if "sources" in generated:
        print("  Validating sources...")
        validate_sources(generated["sources"])

    tasks_with_signal = [t for t in tasks if t.get("n") is not None and t["n"] >= 100]
    low_data = len(tasks_with_signal) == 0
    verify_generated(generated, low_data)

    passthrough = build_passthrough(occ, tasks)

    card = {
        "onet_code": code,
        "title":     occ["Occupation"],
        **passthrough,
        **generated,
        "taskIntro": STANDARD_TASK_INTRO,
    }

    # Pretty-print for review
    print("\n  Generated content:")
    print(f"  risks.stat:   {generated.get('risks', {}).get('stat')} — {generated.get('risks', {}).get('statLabel')}")
    print(f"  opps.stat:    {generated.get('opportunities', {}).get('stat')} — {generated.get('opportunities', {}).get('statLabel')}")
    print(f"  sources:      {len(generated.get('sources', []))} found")
    for s in generated.get("sources", []):
        print(f"    [{s['id']}] {s['name']}")
    print(f"\n  taskIntro:\n    {generated.get('taskIntro', '')}")
    print(f"\n  risks.body:\n    {generated.get('risks', {}).get('body', '')}")
    print(f"\n  opportunities.body:\n    {generated.get('opportunities', {}).get('body', '')}")
    print(f"\n  howToAdapt.alreadyIn:\n    {generated.get('howToAdapt', {}).get('alreadyIn', '')}")
    print(f"\n  howToAdapt.thinkingOf:\n    {generated.get('howToAdapt', {}).get('thinkingOf', '')}")

    append_career_page(sanitize(card))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--code",  help="Single O*NET code to process, e.g. 15-1254.00")
    parser.add_argument("--cluster", help="Process all codes in this cluster (from cluster_roles.csv)")
    parser.add_argument("--batch", type=int, default=1, help="Number of unprocessed occupations to run")
    parser.add_argument("--print-prompt", action="store_true", help="Print the prompt and exit (for use with Claude.ai)")
    parser.add_argument("--api", action="store_true", help="Use Claude API instead of interactive stdin")
    parser.add_argument("--force", action="store_true", help="Regenerate even if already in JSONL")
    args = parser.parse_args()

    print("Loading data...")
    scores      = load_scores()
    task_table  = load_task_table()
    occ_metrics = load_occ_metrics()
    a_scores    = load_a_scores(SCORE_LOG)
    existing    = load_existing_codes()
    tone_guide       = load_text(TONE_GUIDE)
    career_spec      = load_text(CAREER_SPEC)
    approved_sources = load_text(APPROVED_SOURCES)

    if args.code:
        if args.code in existing and not args.print_prompt and not args.force:
            print(f"  Already processed: {args.code}. Use --force to regenerate.")
            return
        process_occupation(args.code, scores, task_table, occ_metrics,
                           a_scores, tone_guide, career_spec, approved_sources,
                           print_prompt_only=args.print_prompt, api_mode=args.api)
    elif args.cluster:
        # Cluster mode: all codes in the cluster
        cluster_roles_path = "data/career_clusters/cluster_roles.csv"
        with open(cluster_roles_path, newline="", encoding="utf-8") as f:
            cluster_codes = [
                r["onet_code"] for r in csv.DictReader(f)
                if r.get("cluster_id") == args.cluster
            ]
        if not cluster_codes:
            print(f"No codes found for cluster '{args.cluster}'")
            return
        to_run = cluster_codes if args.force else [c for c in cluster_codes if c not in existing]
        print(f"Cluster '{args.cluster}': {len(to_run)} to process (of {len(cluster_codes)} total)")
        for code in to_run:
            process_occupation(code, scores, task_table, occ_metrics,
                               a_scores, tone_guide, career_spec, approved_sources,
                               print_prompt_only=args.print_prompt, api_mode=args.api)
    else:
        # Batch mode: next N unprocessed, scored occupations
        candidates = [
            r["Code"] for r in csv.DictReader(open(SCORES_CSV))
            if r["Code"] not in existing
            and r.get("role_resilience_score")
            and r.get("Data-level") == "Y"
        ]
        to_run = candidates[:args.batch]
        print(f"Batch mode: {len(to_run)} occupations (of {len(candidates)} remaining)")
        for code in to_run:
            process_occupation(code, scores, task_table, occ_metrics,
                               a_scores, tone_guide, career_spec, approved_sources,
                               print_prompt_only=args.print_prompt, api_mode=args.api)

    print("\n✓ Done")


if __name__ == "__main__":
    main()
