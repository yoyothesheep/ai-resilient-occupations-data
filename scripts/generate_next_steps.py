#!/usr/bin/env python3
"""Generate or patch occupation card sections.

Generates career page content for each occupation. Can produce a full card
or regenerate individual sections of an existing card.

Full card generates: risks, opportunities, howToAdapt, sources, taskData,
taskLabels, plus passthrough fields (score, salary, growth, jobTitles,
emergingTitles, keyDrivers).

Section mode (--section) regenerates only the specified section(s) of an
existing card, preserving all other fields. This replaces the former
patch_risks_opps.py and patch_task_data.py scripts.

Modes:
  Interactive (default): prints prompt, reads JSON from stdin.
  --print-prompt: prints prompt and exits (Claude Code inline workflow).
  --api: calls Claude API automatically. Requires ANTHROPIC_API_KEY.

Section mode:
  --section risks,opportunities   Regenerate only risks + opps
  --section tasks                 Recompute taskData (no API call)
  --section howToAdapt            Regenerate only howToAdapt + quotes

Usage:
    # Full card
    python3 scripts/generate_next_steps.py --code 15-1254.00 --api
    python3 scripts/generate_next_steps.py --cluster marketing --api

    # Patch single section
    python3 scripts/generate_next_steps.py --code 27-3043.00 --section risks,opportunities --api
    python3 scripts/generate_next_steps.py --cluster marketing --section tasks

    # Print section prompt only (Claude Code workflow)
    python3 scripts/generate_next_steps.py --code 27-3043.00 --section risks,opportunities --print-prompt
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

from loaders import (
    load_scores, load_task_table, load_occ_metrics, load_a_scores, load_text,
    get_cluster_codes,
    SCORES_CSV, SCORE_LOG, TONE_GUIDE, CAREER_SPEC, APPROVED_SOURCES,
)
from prompts import build_full_prompt, build_section_prompt

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
API_MODEL = "claude-opus-4-6"

TOP_N_TASKS   = 10   # tasks to include in taskData
MIN_LABEL_LEN = 15   # task labels shorter than this are considered missing/generic

STANDARD_TASK_INTRO = "Not all tasks are affected equally. Knowing which ones AI handles well, and which still need a human, is how to focus skill-building."


def load_existing_codes() -> set:
    """Return set of onet_codes already saved as individual card files."""
    from cards import load_existing_codes as _load
    return _load()


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


# ── Prompt builder (delegates to prompts.py) ─────────────────────────────────

def build_prompt(occ: dict, tasks: list, metrics: dict, a_scores: dict,
                 tone_guide: str, career_spec: str, approved_sources: str = "") -> str:
    """Build the full card prompt. Thin wrapper around prompts.build_full_prompt()."""
    return build_full_prompt(occ, tasks, metrics, a_scores, tone_guide, career_spec, approved_sources)



# ── Task label helpers (absorbed from patch_task_data.py) ─────────────────────

def needs_label(t: dict) -> bool:
    """True if a task dict is missing a proper short label."""
    return t["task"] == t["full"] or len(t["task"]) < MIN_LABEL_LEN or t["task"].endswith("…")


def build_label_prompt(tasks_needing_labels: list[dict]) -> str:
    """Build a prompt for Claude to author short task labels.

    tasks_needing_labels: list of {code, occupation, full} dicts.
    Returns a prompt string.
    """
    lines = []
    for i, item in enumerate(tasks_needing_labels, 1):
        lines.append(f'{i}. [{item["code"]} — {item["occupation"]}]\n   Full: "{item["full"]}"')

    return f"""You are writing short task label names for a career information site.

For each task below, write a SHORT label (3–6 words, title case, no period) that:
- Captures the core action and subject matter
- Is specific enough to distinguish from other tasks
- Reads naturally as a table row label

Tasks:
{chr(10).join(lines)}

Respond with a JSON array of short labels in the same order:
["Label One", "Label Two", ...]"""


def prompt_for_labels(tasks_needing_labels: list[dict]) -> dict:
    """Print label prompt, read JSON from stdin.

    Returns {full_task_text: short_label} mapping.
    """
    prompt = build_label_prompt(tasks_needing_labels)

    print("\n" + "="*80)
    print("TASK LABEL PROMPT — paste into Claude Code and respond with JSON:")
    print("="*80)
    print(prompt)
    print("="*80)
    print("\nPaste the JSON array response below, then press Enter + Ctrl-D (or Ctrl-Z on Windows):")

    text = sys.stdin.read().strip()
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    labels = json.loads(text)

    if len(labels) != len(tasks_needing_labels):
        raise ValueError(f"Expected {len(tasks_needing_labels)} labels, got {len(labels)}")

    return {item["full"]: label for item, label in zip(tasks_needing_labels, labels)}


# ── Removed: old build_prompt() body ─────────────────────────────────────────
# Prompt building now lives in scripts/prompts.py. The build_prompt() wrapper
# above delegates to prompts.build_full_prompt().
# For section-only prompts, use prompts.build_section_prompt().




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
                       print_prompt_only: bool = False, api_mode: bool = False,
                       sections: list[str] | None = None):
    """Generate or patch one occupation card.

    sections=None generates a full card (all sections).
    sections=["risks", "opportunities"] patches only those sections of an
    existing card. sections=["tasks"] recomputes taskData without a prompt.
    """
    occ = scores.get(code)
    if not occ:
        print(f"  ✗ Code {code} not found in scores CSV")
        return

    print(f"\n── {occ['Occupation']} ({code})")

    tasks = build_task_data(code, task_table.get(code, []))

    # ── Section mode: tasks (no prompt, purely computational) ─────────
    if sections and sections == ["tasks"]:
        from cards import load_cards, save_card
        existing_cards = load_cards()
        if code not in existing_cards:
            print(f"  ✗ No existing card for {code} — run full generation first")
            return
        card = existing_cards[code]

        # Preserve existing good labels
        old_tasks = {t["full"]: t.get("task") for t in card.get("taskData", [])}
        for t in tasks:
            prior = old_tasks.get(t["full"])
            if prior and prior != t["full"] and len(prior) >= MIN_LABEL_LEN:
                t["task"] = prior

        # Collect tasks needing labels — will be batched across codes in main()
        card["_new_task_data"] = tasks
        card["_needs_labels"] = [
            {"code": code, "occupation": occ["Occupation"], "full": t["full"]}
            for t in tasks if needs_label(t)
        ]
        return card  # caller handles label prompt + save

    # ── Section mode: content sections (risks, opportunities, howToAdapt) ─
    if sections:
        prompt = build_section_prompt(
            sections, occ, tasks, occ_metrics, a_scores,
            tone_guide, career_spec, approved_sources
        )
    else:
        prompt = build_prompt(occ, tasks, occ_metrics, a_scores,
                              tone_guide, career_spec, approved_sources)

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

    generated = sanitize(generated)

    # Apply short labels from the interactive response (full card mode only)
    if not sections:
        task_labels = {k.strip(): v for k, v in generated.pop("taskLabels", {}).items()}
        for t in tasks:
            full = t["full"].strip()
            if full in task_labels:
                t["task"] = task_labels[full]
            else:
                prefix = full[:30].lower()
                match = next((v for k, v in task_labels.items() if k.lower().startswith(prefix[:20])), None)
                if match:
                    t["task"] = match
                elif t["task"] == t["full"]:
                    words = t["full"].split()
                    t["task"] = " ".join(words[:5]).rstrip(".,;") + ("…" if len(words) > 5 else "")

    # Validate source URLs and dates
    if "sources" in generated:
        print("  Validating sources...")
        validate_sources(generated["sources"])

    tasks_with_signal = [t for t in tasks if t.get("n") is not None and t["n"] >= 100]
    low_data = len(tasks_with_signal) == 0
    verify_generated(generated, low_data)

    if sections:
        # Section mode: merge into existing card
        from cards import load_cards, save_card
        existing_cards = load_cards()
        if code not in existing_cards:
            print(f"  ✗ No existing card for {code} — run full generation first")
            return
        card = existing_cards[code]

        # Overwrite only the requested sections
        if "risks" in sections or "opportunities" in sections:
            card["risks"] = generated.get("risks", {})
            card["opportunities"] = generated.get("opportunities", {})
        if "howToAdapt" in sections:
            card["howToAdapt"] = generated.get("howToAdapt", {})

        # Always update sources when patching content sections
        new_sources = generated.get("sources", [])
        if new_sources:
            card["sources"] = new_sources

        save_card(card)
        r_stat = card.get("risks", {}).get("stat")
        o_stat = card.get("opportunities", {}).get("stat")
        print(f"  ✓ Patched {code} — risks.stat={r_stat!r} opps.stat={o_stat!r}")
    else:
        # Full card mode
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
        print(f"\n  risks.body:\n    {generated.get('risks', {}).get('body', '')}")
        print(f"\n  opportunities.body:\n    {generated.get('opportunities', {}).get('body', '')}")
        print(f"\n  howToAdapt.alreadyIn:\n    {generated.get('howToAdapt', {}).get('alreadyIn', '')}")
        print(f"\n  howToAdapt.thinkingOf:\n    {generated.get('howToAdapt', {}).get('thinkingOf', '')}")

        append_career_page(card)


# ── Section: tasks batch handler ─────────────────────────────────────────────

def process_tasks_batch(codes: list[str], scores: dict, task_table: dict):
    """Recompute taskData for multiple codes, batch-prompting for missing labels.

    Absorbed from the former patch_task_data.py. Three phases:
    1. Compute new task data for all codes, collecting tasks needing labels
    2. Interactive prompt for all missing labels at once
    3. Apply labels and save
    """
    from cards import save_card

    all_cards = {}       # code -> card (with _new_task_data and _needs_labels)
    all_missing = []     # flat list of {code, occupation, full}

    for code in codes:
        result = process_occupation(
            code, scores, task_table, {}, {}, "", "",
            sections=["tasks"]
        )
        if result is None:
            continue
        all_cards[code] = result
        all_missing.extend(result.pop("_needs_labels", []))

    # Phase 2: interactive label prompt
    label_map = {}
    if all_missing:
        print(f"\n{len(all_missing)} tasks need short labels across {len(all_cards)} cards.")
        label_map = prompt_for_labels(all_missing)

    # Phase 3: apply labels and save
    print()
    changed = 0
    for code, card in all_cards.items():
        new_task_data = card.pop("_new_task_data")
        for t in new_task_data:
            if needs_label(t) and t["full"] in label_map:
                t["task"] = label_map[t["full"]]

        old_tasks = [t["full"] for t in card.get("taskData", [])]
        new_tasks = [t["full"] for t in new_task_data]
        task_changed = old_tasks != new_tasks

        card["taskData"] = new_task_data
        save_card(card)

        status = "CHANGED" if task_changed else "updated"
        print(f"  {status} {code} ({len(old_tasks)} → {len(new_task_data)} tasks)")
        if task_changed:
            changed += 1

    print(f"\nDone. {changed}/{len(all_cards)} cards had task order changes.")


def main():
    parser = argparse.ArgumentParser(
        description="Generate or patch occupation card sections"
    )
    parser.add_argument("--code", help="Single O*NET code to process")
    parser.add_argument("--cluster", help="All codes in this cluster (from cluster_roles.csv)")
    parser.add_argument("--batch", type=int, default=1,
                        help="Number of unprocessed occupations to run")
    parser.add_argument("--print-prompt", action="store_true",
                        help="Print the prompt and exit (Claude Code workflow)")
    parser.add_argument("--api", action="store_true",
                        help="Use Claude API instead of interactive stdin")
    parser.add_argument("--force", action="store_true",
                        help="Regenerate even if card already exists")
    parser.add_argument("--section",
                        help="Patch only specified sections (comma-separated): "
                             "risks,opportunities | tasks | howToAdapt")
    args = parser.parse_args()

    # Parse sections
    sections = None
    if args.section:
        sections = [s.strip() for s in args.section.split(",")]
        valid = {"risks", "opportunities", "tasks", "howToAdapt"}
        invalid = set(sections) - valid
        if invalid:
            print(f"Invalid section(s): {invalid}. Valid: {valid}")
            sys.exit(1)

    print("Loading data...")
    scores      = load_scores()
    task_table  = load_task_table()
    occ_metrics = load_occ_metrics()
    a_scores    = load_a_scores()
    existing    = load_existing_codes()
    tone_guide       = load_text(TONE_GUIDE)
    career_spec      = load_text(CAREER_SPEC)
    approved_sources = load_text(APPROVED_SOURCES)

    # Resolve codes
    if args.code:
        codes = [args.code]
    elif args.cluster:
        codes = get_cluster_codes(args.cluster)
        if not codes:
            print(f"No codes found for cluster '{args.cluster}'")
            sys.exit(1)
        print(f"Cluster '{args.cluster}': {len(codes)} codes")
    else:
        # Batch mode: next N unprocessed
        candidates = [
            r["Code"] for r in csv.DictReader(open(SCORES_CSV))
            if r["Code"] not in existing
            and r.get("role_resilience_score")
            and r.get("Data-level") == "Y"
        ]
        codes = candidates[:args.batch]
        print(f"Batch mode: {len(codes)} occupations (of {len(candidates)} remaining)")

    # Filter for --force in full-card mode (sections always re-process)
    if not sections and not args.force and not args.print_prompt:
        codes = [c for c in codes if c not in existing]
        if not codes:
            print("All codes already processed. Use --force to regenerate.")
            return

    # Special batch handling for tasks section
    if sections == ["tasks"]:
        process_tasks_batch(codes, scores, task_table)
        print("\n✓ Done")
        return

    # Process each code
    for code in codes:
        process_occupation(
            code, scores, task_table, occ_metrics, a_scores,
            tone_guide, career_spec, approved_sources,
            print_prompt_only=args.print_prompt,
            api_mode=args.api,
            sections=sections,
        )

    print("\n✓ Done")


if __name__ == "__main__":
    main()
