#!/usr/bin/env python3
"""
Data integration tests for occupation_cards.jsonl and generated TSX career files.

Run structure tests:   pytest scripts/test_data_integrity.py -v
Run with URL checks:   pytest scripts/test_data_integrity.py -m network -v

register custom marks: add pytest.ini or pyproject.toml with [tool.pytest.ini_options] markers
"""
import json
import re
import urllib.request
import urllib.error
from pathlib import Path

import pytest

CARDS_JSONL   = Path("data/output/occupation_cards.jsonl")
CAREERS_DIR   = Path("../ai-resilient-occupations-site/src/data/careers")
REGISTRY_FILE = Path("../ai-resilient-occupations-site/src/data/careerPageRegistry.ts")

# Domains that block headless requests but are known-authoritative approved sources.
# 403/non-200 from these is not a dead link — flag for human verification only.
BOT_BLOCKED_DOMAINS = {
    "www.bls.gov",
    "bls.gov",
    "www.salesforce.com",
    "www.mckinsey.com",
    "www.nar.realtor",
    "www.pmi.org",
    "www.weforum.org",
    "www.zillow.com",
    "economicgraph.linkedin.com",
    "business.linkedin.com",
}

# ── Helpers ────────────────────────────────────────────────────────────────────

def load_cards() -> list[dict]:
    cards = []
    with open(CARDS_JSONL, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cards.append(json.loads(line))
    return cards


def career_slug(title: str) -> str:
    slug = title.lower()
    slug = re.sub(r"[,&]", "", slug)
    slug = re.sub(r"[\s/]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug


def load_registry_slugs() -> set[str]:
    if not REGISTRY_FILE.exists():
        return set()
    content = REGISTRY_FILE.read_text()
    return set(re.findall(r'"([\w-]+)"', content))


def url_domain(url: str) -> str:
    m = re.match(r"https?://([^/]+)", url)
    return m.group(1) if m else ""


CARDS = load_cards()
CARD_IDS = [c["onet_code"] for c in CARDS]
CARD_BY_CODE = {c["onet_code"]: c for c in CARDS}
REGISTRY_SLUGS = load_registry_slugs()

CLUSTER_BRANCHES_CSV = Path("data/career_clusters/cluster_branches.csv")

# ── JSONL: required top-level fields ──────────────────────────────────────────

REQUIRED_FIELDS = ["onet_code", "title", "score", "salary", "openings", "growth", "taskData", "sources", "keyDrivers", "jobTitles"]

@pytest.mark.parametrize("code", CARD_IDS)
def test_required_fields(code):
    card = next(c for c in CARDS if c["onet_code"] == code)
    for field in REQUIRED_FIELDS:
        assert field in card and card[field] not in (None, "", []), \
            f"{code}: missing or empty field '{field}' - (Tip: You can extract salary, growth, and openings from data/output/ai_resilience_scores.csv)"


# ── JSONL: source structure ────────────────────────────────────────────────────

@pytest.mark.parametrize("code", CARD_IDS)
def test_source_structure(code):
    card = next(c for c in CARDS if c["onet_code"] == code)
    for i, s in enumerate(card.get("sources", [])):
        ref = f"{code} sources[{i}]"
        assert s.get("id"),    f"{ref}: missing id"
        assert s.get("name"),  f"{ref}: missing name"
        assert s.get("url"),   f"{ref}: missing url"
        assert s.get("title"), f"{ref}: missing title — run scripts/patch_source_metadata.py to backfill"
        assert s.get("date"),  f"{ref}: missing date — run scripts/patch_source_metadata.py to backfill"


# ── JSONL: no dangling suffix (name-only sources must not have date) ───────────

@pytest.mark.parametrize("code", CARD_IDS)
def test_no_dangling_suffix(code):
    card = next(c for c in CARDS if c["onet_code"] == code)
    for i, s in enumerate(card.get("sources", [])):
        if not s.get("title") and s.get("date"):
            pytest.fail(
                f"{code} sources[{i}]: has date '{s['date']}' but no title — "
                f"will render as '- , {s['date']}'"
            )


# ── JSONL: cluster node stat sources ──────────────────────────────────────────

@pytest.mark.parametrize("code", CARD_IDS)
def test_cluster_stat_sources(code):
    card = next(c for c in CARDS if c["onet_code"] == code)
    for node in card.get("careerCluster", []):
        stat = node.get("stat") or {}
        if stat.get("sourceUrl"):
            assert stat.get("sourceName"),  f"{code} cluster '{node.get('title')}': missing sourceName"
            assert stat.get("sourceTitle"), f"{code} cluster '{node.get('title')}': missing sourceTitle"
            assert stat.get("sourceDate"),  f"{code} cluster '{node.get('title')}': missing sourceDate"


# ── JSONL: non-current non-emerging cluster nodes have transition fields ───────

@pytest.mark.parametrize("code", CARD_IDS)
def test_cluster_node_transition_fields(code):
    card = next(c for c in CARDS if c["onet_code"] == code)
    for node in card.get("careerCluster", []):
        if node.get("isCurrent") or node.get("isEmerging"):
            continue
        ref = f"{code} cluster node '{node.get('title')}'"
        for field in ("salary", "openings", "growth", "fit", "steps"):
            assert node.get(field) not in (None, "", []), \
                f"{ref}: missing or empty field '{field}'"


# ── JSONL: salary and openings format ─────────────────────────────────────────

SALARY_RE   = re.compile(r"^\$[\d,]+$")
OPENINGS_RE = re.compile(r"^[\d,]+$")

@pytest.mark.parametrize("code", CARD_IDS)
def test_salary_format(code):
    card = next(c for c in CARDS if c["onet_code"] == code)
    salary = card.get("salary", "")
    if salary:
        assert SALARY_RE.match(salary), f"{code}: malformed salary '{salary}'"

@pytest.mark.parametrize("code", CARD_IDS)
def test_openings_format(code):
    card = next(c for c in CARDS if c["onet_code"] == code)
    openings = card.get("openings", "")
    if openings:
        assert OPENINGS_RE.match(openings), f"{code}: malformed openings '{openings}'"


# ── JSONL: inline citation refs match sources ─────────────────────────────────

@pytest.mark.parametrize("code", CARD_IDS)
def test_inline_citation_refs(code):
    card = next(c for c in CARDS if c["onet_code"] == code)
    source_ids = {s["id"] for s in card.get("sources", [])}
    how_to_adapt = card.get("howToAdapt", {})
    for persona, content in how_to_adapt.items():
        if not isinstance(content, dict):
            continue
        for i, q in enumerate(content.get("quotes", [])):
            sid = q.get("sourceId")
            if sid:
                assert sid in source_ids, \
                    f"{code} howToAdapt[{persona}].quotes[{i}]: sourceId '{sid}' not in sources"


# ── TSX: registry ↔ actual files are in sync ──────────────────────────────────

def test_registry_matches_tsx_files():
    """careerPageRegistry.ts must exactly match the TSX files that exist on disk."""
    if not CAREERS_DIR.exists():
        pytest.skip("careers dir not found")
    on_disk = {f.stem for f in CAREERS_DIR.glob("*.tsx")}
    in_registry = REGISTRY_SLUGS

    missing_from_registry = on_disk - in_registry
    missing_from_disk = in_registry - on_disk

    errors = []
    if missing_from_registry:
        errors.append(
            f"TSX files exist but not in registry (re-run generate_career_pages.py --force):\n"
            + "\n".join(f"  {s}" for s in sorted(missing_from_registry))
        )
    if missing_from_disk:
        errors.append(
            f"Registry entries with no TSX file (stale registry or page not yet generated):\n"
            + "\n".join(f"  {s}" for s in sorted(missing_from_disk))
        )
    if errors:
        pytest.fail("\n\n".join(errors))


# ── TSX: cards that have pages match registry ─────────────────────────────────

@pytest.mark.parametrize("code", CARD_IDS)
def test_tsx_file_exists_if_in_registry(code):
    """If a card's slug is in the registry, the TSX file must exist."""
    card = next(c for c in CARDS if c["onet_code"] == code)
    slug = career_slug(card["title"])
    if slug not in REGISTRY_SLUGS:
        pytest.skip(f"{slug} not yet in registry — page not built yet")
    tsx = CAREERS_DIR / f"{slug}.tsx"
    assert tsx.exists(), f"{code} ('{card['title']}'): in registry but no TSX at {tsx}"


# ── TSX: no empty taskData ─────────────────────────────────────────────────────

def test_no_empty_task_data():
    if not CAREERS_DIR.exists():
        pytest.skip("careers dir not found")
    empty = [f.name for f in CAREERS_DIR.glob("*.tsx") if "taskData: []" in f.read_text()]
    assert not empty, f"TSX files with empty taskData: {empty}"


# ── TSX: source URL checks ─────────────────────────────────────────────────────

def _collect_tsx_source_urls() -> list[tuple[str, str]]:
    """Return (file_stem, url) for all non-empty source URLs in TSX files."""
    if not CAREERS_DIR.exists():
        return []
    results = []
    for tsx in sorted(CAREERS_DIR.glob("*.tsx")):
        content = tsx.read_text()
        sources_match = re.search(r'sources:\s*\[(.*?)\],?\s*\n\s*\}', content, re.DOTALL)
        if not sources_match:
            continue
        for entry in re.findall(r'\{([^}]+)\}', sources_match.group(1), re.DOTALL):
            url_m = re.search(r'\burl:\s*["\']([^"\']+)', entry)
            if url_m:
                results.append((tsx.stem, url_m.group(1)))
    return results


TSX_SOURCE_URLS = _collect_tsx_source_urls()


def test_source_urls_non_empty():
    """All source url fields must be non-empty strings."""
    if not CAREERS_DIR.exists():
        pytest.skip("careers dir not found")
    empty = []
    for tsx in sorted(CAREERS_DIR.glob("*.tsx")):
        content = tsx.read_text()
        sources_match = re.search(r'sources:\s*\[(.*?)\],?\s*\n\s*\}', content, re.DOTALL)
        if not sources_match:
            continue
        for i, entry in enumerate(re.findall(r'\{([^}]+)\}', sources_match.group(1), re.DOTALL)):
            url_m  = re.search(r'\burl:\s*["\']([^"\']*)', entry)
            title_m = re.search(r'\btitle:\s*["\']([^"\']+)', entry)
            if url_m and not url_m.group(1):
                empty.append(f"{tsx.stem} src-{i+1} '{title_m.group(1) if title_m else '?'}'")
    assert not empty, "Sources with empty url:\n" + "\n".join(empty)


@pytest.mark.network
@pytest.mark.parametrize("stem,url", TSX_SOURCE_URLS)
def test_source_url_reachable(stem, url):
    """Each source URL must be reachable and not redirect to an unrelated page.

    Follows redirects (like the pipeline does), then checks:
    - Final status is 200
    - Final URL is on the same domain and not drastically shorter (homepage redirect)

    Bot-blocked domains that return 403 are skipped for human verification.
    """
    import urllib.parse

    domain = url_domain(url)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        status = resp.status
        final_url = resp.url
    except urllib.error.HTTPError as e:
        status = e.code
        final_url = url
    except urllib.error.URLError as e:
        pytest.fail(f"{stem} | {url} — connection error: {e.reason}")
        return

    # Bot-blocked domains: skip for human verification
    # TODO: At publish time (publish-checklist C10), manually open these URLs
    # in a browser to confirm they're still live. Automated checks can't verify
    # bot-blocked domains.
    if status in (403, 406, 429) and domain in BOT_BLOCKED_DOMAINS:
        pytest.skip(
            f"{stem} | {url} — {status} from known bot-blocking domain ({domain}). "
            f"Human should verify manually at publish time."
        )

    if status == 404:
        pytest.fail(
            f"{stem} | {url}\n"
            f"  STATUS: 404 — page not found.\n"
            f"  FIX: Rerun generate_next_steps.py --code <code> to replace citation."
        )

    if not (200 <= status < 300):
        pytest.fail(
            f"{stem} | {url}\n"
            f"  STATUS: {status} — unexpected.\n"
            f"  FIX: Investigate manually."
        )

    # Check redirect destination
    if final_url != url:
        parsed_orig = urllib.parse.urlparse(url)
        parsed_final = urllib.parse.urlparse(final_url)
        if parsed_final.netloc and parsed_final.netloc != parsed_orig.netloc:
            pytest.fail(
                f"{stem} | {url}\n"
                f"  Redirected to different domain: {final_url}\n"
                f"  FIX: Rerun generate_next_steps.py --code <code> to replace citation."
            )
        orig_depth = len(parsed_orig.path.strip("/").split("/"))
        final_depth = len(parsed_final.path.strip("/").split("/"))
        if final_depth < orig_depth - 1 and len(parsed_final.path.strip("/")) < 5:
            pytest.fail(
                f"{stem} | {url}\n"
                f"  Redirected to likely homepage: {final_url}\n"
                f"  FIX: Rerun generate_next_steps.py --code <code> to replace citation."
            )


# ── TSX: stat cross-section duplication ───────────────────────────────────────

def _extract_section_stats(content: str, section_label: str) -> set[str]:
    """Return all percentage stats found in a named section (risks or opportunities)."""
    # Match the section object: { title: "...", body: (<>...</>) }
    pattern = rf'title:\s*"[^"]*{section_label}[^"]*".*?body:\s*\(<>(.*?)</>\s*\)'
    m = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
    if not m:
        return set()
    return set(re.findall(r'\b\d+%', m.group(1)))


EMERGING_ROLES_CSV = Path("data/emerging_roles/emerging_roles.csv")


BLOCKED_SOURCE_DOMAINS = {"marketsandmarkets", "gartner", "forrester", "idc.com"}


def test_no_single_source_sections():
    """Each howToAdapt and risks/opportunities section with 2+ citations must use at least 2 distinct sources."""
    if not CARDS_JSONL.exists():
        pytest.skip("occupation_cards.jsonl not found")
    bad = []
    with open(CARDS_JSONL) as f:
        for line in f:
            d = json.loads(line)
            adapt = d.get("howToAdapt") or {}
            sections = [
                ("risks.body", (d.get("risks") or {}).get("body", "")),
                ("opportunities.body", (d.get("opportunities") or {}).get("body", "")),
                ("howToAdapt.alreadyIn", adapt.get("alreadyIn", "")),
                ("howToAdapt.thinkingOf", adapt.get("thinkingOf", "")),
            ]
            for name, text in sections:
                citations = re.findall(r'\[(\d+)\]', str(text))
                # Flag sections where every citation is the same source.
                # Exception: AEI data sections legitimately cite the same source for different metrics.
                if len(citations) >= 2 and len(set(citations)) == 1:
                    text_lower = str(text).lower()
                    is_aei_multistat = "augmentation rate" in text_lower and "automation rate" in text_lower
                    if not is_aei_multistat:
                        bad.append(f"{d['onet_code']} {name}: [{citations[0]}] repeated {len(citations)}x")
    assert not bad, "Sections citing only one source:\n" + "\n".join(bad)


def test_no_blocked_sources_in_jsonl():
    """occupation_cards.jsonl must not cite Gartner, IDC, Forrester, or MarketsandMarkets."""
    if not CARDS_JSONL.exists():
        pytest.skip("occupation_cards.jsonl not found")
    bad = []
    with open(CARDS_JSONL) as f:
        for line in f:
            d = json.loads(line)
            for s in d.get("sources", []):
                combined = (s.get("url","") + s.get("name","")).lower()
                if any(b in combined for b in BLOCKED_SOURCE_DOMAINS):
                    bad.append(f"{d['onet_code']} sources: {s.get('name')} {s.get('url')}")
            for e in d.get("emergingCareers", []):
                stat = e.get("stat") or {}
                combined = (stat.get("sourceUrl","") + stat.get("sourceName","")).lower()
                if any(b in combined for b in BLOCKED_SOURCE_DOMAINS):
                    bad.append(f"{d['onet_code']} emerging/{e.get('title')}: {stat.get('sourceName')} {stat.get('sourceUrl')}")
    assert not bad, "Blocked sources found in JSONL:\n" + "\n".join(bad)


def test_no_blocked_sources_in_emerging_roles_csv():
    """emerging_roles.csv must not cite Gartner, IDC, Forrester, or MarketsandMarkets."""
    if not EMERGING_ROLES_CSV.exists():
        pytest.skip("emerging_roles.csv not found")
    import csv as _csv
    bad = []
    with open(EMERGING_ROLES_CSV, newline="") as f:
        for row in _csv.DictReader(f):
            combined = (row.get("stat_url","") + row.get("stat_source","")).lower()
            if any(b in combined for b in BLOCKED_SOURCE_DOMAINS):
                bad.append(f"{row['onet_code']} {row['emerging_title']}: {row['stat_source']} {row['stat_url']}")
    assert not bad, "Blocked sources found in emerging_roles.csv:\n" + "\n".join(bad)


def test_emerging_roles_core_tools_not_list_repr():
    """core_tools must be a plain comma-separated string, not a Python list repr."""
    if not EMERGING_ROLES_CSV.exists():
        pytest.skip("emerging_roles.csv not found")
    import csv
    bad = []
    with open(EMERGING_ROLES_CSV, newline="") as f:
        for row in csv.DictReader(f):
            t = row.get("core_tools", "").strip()
            if t.startswith("[") and t.endswith("]"):
                bad.append(f"{row['onet_code']} {row['emerging_title']}: {t!r}")
    assert not bad, "core_tools stored as Python list repr:\n" + "\n".join(bad)


def test_no_raw_weight_values_in_prose():
    """Prose must not contain raw numeric task weight values like '(weight 20.9)' or 'a weight of 21.8'."""
    if not CAREERS_DIR.exists():
        pytest.skip("careers dir not found")
    pattern = re.compile(r'\bweight\s+\d+[\d.]*|\ba weight of \d+[\d.]*|\(weight\s+[\d.]+\)', re.IGNORECASE)
    bad = []
    for tsx in sorted(CAREERS_DIR.glob("*.tsx")):
        for m in pattern.finditer(tsx.read_text()):
            bad.append(f"{tsx.stem}: {m.group()!r}")
    assert not bad, "Raw task weight values in prose:\n" + "\n".join(bad)


def test_howToAdapt_quotes_present():
    """Every card must have howToAdapt.quotes with at least 2 entries (one per persona)."""
    if not CARDS_JSONL.exists():
        pytest.skip("occupation_cards.jsonl not found")
    bad = []
    with open(CARDS_JSONL) as f:
        for line in f:
            d = json.loads(line)
            quotes = (d.get("howToAdapt") or {}).get("quotes") or []
            if len(quotes) < 2:
                bad.append(f"{d['onet_code']} {d.get('title', '')} — howToAdapt.quotes has {len(quotes)} entries (need ≥2)")
    assert not bad, "Cards missing howToAdapt quotes (regenerate via generate_next_steps.py):\n" + "\n".join(bad)


def test_tsx_howToAdapt_quotes_present():
    """TSX files must contain a quotes array in howToAdapt (catches JSONL→TSX drift)."""
    bad = []
    for tsx in sorted(CAREERS_DIR.glob("*.tsx")):
        content = tsx.read_text()
        if "howToAdapt:" in content and "quotes:" not in content:
            bad.append(tsx.stem)
    assert not bad, "TSX files have howToAdapt but no quotes (re-run generate_career_pages.py --force):\n" + "\n".join(bad)


def test_howToAdapt_quotes_diverse_sources():
    """Each persona's quotes in howToAdapt must not all cite the same source."""
    if not CARDS_JSONL.exists():
        pytest.skip("occupation_cards.jsonl not found")
    bad = []
    with open(CARDS_JSONL) as f:
        for line in f:
            d = json.loads(line)
            quotes = (d.get("howToAdapt") or {}).get("quotes", [])
            for persona in ("alreadyIn", "thinkingOf"):
                persona_quotes = [q for q in quotes if q.get("persona") == persona]
                if len(persona_quotes) >= 2:
                    src_ids = [q.get("sourceId") for q in persona_quotes if q.get("sourceId")]
                    if len(src_ids) >= 2 and len(set(src_ids)) == 1:
                        bad.append(f"{d['onet_code']} howToAdapt.quotes[{persona}]: all {len(src_ids)} quotes cite {src_ids[0]}")
    assert not bad, "howToAdapt quotes all from same source (regenerate via generate_next_steps.py):\n" + "\n".join(bad) + "\n\nTip: You must find a new, relevant quote from a new source. You cannot just change the source number but keep everything else the same!"


def test_emerging_roles_stat_has_title_and_date():
    """Every emerging role with a sourceName must also have sourceTitle and sourceDate in the JSONL."""
    if not CARDS_JSONL.exists():
        pytest.skip("occupation_cards.jsonl not found")
    bad = []
    with open(CARDS_JSONL) as f:
        for line in f:
            d = json.loads(line)
            for e in d.get("emergingCareers", []):
                s = e.get("stat", {})
                if s.get("sourceName") and (not s.get("sourceTitle") or not s.get("sourceDate")):
                    bad.append(f"{d['onet_code']} {e.get('title','?')}: has sourceName but missing sourceTitle/sourceDate")
    assert not bad, "Emerging role stats missing sourceTitle or sourceDate:\n" + "\n".join(bad)


def test_emerging_roles_stat_text_not_empty():
    """Every row in emerging_roles.csv must have stat_text populated."""
    if not EMERGING_ROLES_CSV.exists():
        pytest.skip("emerging_roles.csv not found")
    import csv
    bad = []
    with open(EMERGING_ROLES_CSV, newline="") as f:
        for row in csv.DictReader(f):
            if not row.get("stat_text", "").strip():
                bad.append(f"{row['onet_code']} {row['emerging_title']}: missing stat_text")
    assert not bad, (
        "Emerging roles missing stat_text (re-run generate_emerging_roles.py for affected clusters):\n"
        + "\n".join(bad)
    )


def test_emerging_roles_stat_text_not_empty_in_jsonl():
    """Every emergingCareer in occupation_cards.jsonl must have stat.text populated."""
    if not CARDS_JSONL.exists():
        pytest.skip("occupation_cards.jsonl not found")
    bad = []
    with open(CARDS_JSONL) as f:
        for line in f:
            d = json.loads(line)
            for e in d.get("emergingCareers", []):
                if not (e.get("stat") or {}).get("text", "").strip():
                    bad.append(f"{d['onet_code']} {e.get('title','?')}: missing stat.text")
    assert not bad, (
        "Emerging careers in JSONL missing stat.text:\n" + "\n".join(bad)
    )


_REDUNDANT_STAT_PATTERNS = [
    "automation rate", "augmentation rate", "automatable", "weighted automation",
    "projected employment", "employment growth", "job growth through",
    "projected job growth", "median annual", "median salary",
]


def test_no_redundant_pull_stats():
    """Pull stats in risks/opportunities must not duplicate data already on the page (task table, hero grid)."""
    if not CARDS_JSONL.exists():
        pytest.skip("occupation_cards.jsonl not found")
    bad = []
    with open(CARDS_JSONL) as f:
        for line in f:
            d = json.loads(line)
            for section in ("risks", "opportunities"):
                sec = d.get(section) or {}
                label = (sec.get("statLabel") or "").lower()
                stat = (sec.get("stat") or "").lower()
                combined = f"{stat} {label}"
                for pat in _REDUNDANT_STAT_PATTERNS:
                    if pat in combined:
                        bad.append(f"{d['onet_code']} {section}.stat: '{sec.get('stat')} {sec.get('statLabel')}' matches '{pat}'")
                        break
    assert not bad, (
        "Redundant pull stats (duplicate task table or hero grid data):\n"
        + "\n".join(bad)
    )


def test_no_empty_or_none_stats_in_narratives():
    """risks and opportunities must have actual stat and statLabel values, not 'None' or empty."""
    if not CARDS_JSONL.exists():
        pytest.skip("occupation_cards.jsonl not found")
    bad = []
    with open(CARDS_JSONL) as f:
        for line in f:
            d = json.loads(line)
            for section in ("risks", "opportunities"):
                sec = d.get(section)
                if not sec or not isinstance(sec, dict):
                    bad.append(f"{d['onet_code']}: missing {section} dictionary")
                    continue
                stat = sec.get("stat")
                label = sec.get("statLabel")
                if str(stat) in ("None", "", "none") or str(label) in ("None", "", "none"):
                    bad.append(f"{d['onet_code']} {section} stat/statLabel is missing/None")
                if "..." in str(label):
                    bad.append(f"{d['onet_code']} {section}.statLabel is truncated with '...'")
    assert not bad, (
        "Missing or 'None' stats in risks/opportunities sections:\n"
        + "\n".join(bad)
    )


def test_no_blocked_sources_in_tsx():
    """TSX source entries must not cite Gartner, IDC, Forrester, or MarketsandMarkets."""
    if not CAREERS_DIR.exists():
        pytest.skip("careers dir not found")
    # Match source objects: { id: ..., name: ..., url: ... }
    source_entry_re = re.compile(r'\{\s*id:\s*["\']src-[^"\']+["\'][^}]+\}', re.DOTALL)
    bad = []
    for tsx in sorted(CAREERS_DIR.glob("*.tsx")):
        content = tsx.read_text()
        for entry in source_entry_re.findall(content):
            entry_lower = entry.lower()
            for domain in BLOCKED_SOURCE_DOMAINS:
                if domain in entry_lower:
                    name_m = re.search(r'\bname:\s*["\']([^"\']+)', entry)
                    name = name_m.group(1) if name_m else "unknown"
                    bad.append(f"{tsx.stem}: source '{name}' matches blocked domain '{domain}'")
    assert not bad, "Blocked sources found in TSX source entries:\n" + "\n".join(bad)


def test_no_redundant_pull_stats_in_tsx():
    """Pull stats in TSX risks/opportunities must not duplicate task table or hero grid data."""
    if not CAREERS_DIR.exists():
        pytest.skip("careers dir not found")
    bad = []
    stat_label_re = re.compile(r'statLabel:\s*["\']([^"\']+)["\']', re.IGNORECASE)
    for tsx in sorted(CAREERS_DIR.glob("*.tsx")):
        content = tsx.read_text()
        for m in stat_label_re.finditer(content):
            label = m.group(1).lower()
            for pat in _REDUNDANT_STAT_PATTERNS:
                if pat in label:
                    bad.append(f"{tsx.stem}: statLabel '{m.group(1)}' matches redundant pattern '{pat}'")
                    break
    assert not bad, "Redundant pull stats in TSX:\n" + "\n".join(bad)


def test_no_stat_repeated_across_risks_and_opportunities():
    """A percentage stat that appears in risks should not reappear verbatim in opportunities."""
    if not CAREERS_DIR.exists():
        pytest.skip("careers dir not found")
    violations = []
    for tsx in sorted(CAREERS_DIR.glob("*.tsx")):
        content = tsx.read_text()
        risk_stats = _extract_section_stats(content, "Risk")
        opp_stats  = _extract_section_stats(content, "Opportunit")
        dupes = risk_stats & opp_stats
        if dupes:
            violations.append(f"{tsx.stem}: stat(s) {sorted(dupes)} appear in both risks and opportunities sections")
    assert not violations, "Cross-section stat duplication:\n" + "\n".join(violations)


# ── Industry pages ─────────────────────────────────────────────────────────────

INDUSTRIES_DIR = Path("../ai-resilient-occupations-site/src/data/industries")
INDUSTRY_ROUTES_DIR = Path("../ai-resilient-occupations-site/app/industry")

SCORE_RE    = re.compile(r'\bscore:\s*(\d+)')
GROWTH_RE   = re.compile(r'\bgrowth:\s*["\']([^"\']+)["\']')
OPENINGS_RE_IND = re.compile(r'\bopenings:\s*["\']([^"\']+)["\']')
LEVEL_RE    = re.compile(r'\blevel:\s*([1-5])\b')
SLUG_RE_IND = re.compile(r'\bslug:\s*["\']([^"\']+)["\']')
GROWTH_FMT  = re.compile(r'^[+\-~]?\d+%$')
OPENINGS_FMT_IND = re.compile(r'^[\d,]+$')


def _load_industry_files():
    if not INDUSTRIES_DIR.exists():
        return []
    return sorted(INDUSTRIES_DIR.glob("*.ts"))


INDUSTRY_FILES = _load_industry_files()
INDUSTRY_STEMS = [f.stem for f in INDUSTRY_FILES]


@pytest.mark.parametrize("stem", INDUSTRY_STEMS)
def test_industry_route_file_exists(stem):
    """Each industry .ts data file must have a corresponding app/industry/<slug>/page.tsx."""
    if not INDUSTRY_ROUTES_DIR.exists():
        pytest.skip("industry routes dir not found")
    route = INDUSTRY_ROUTES_DIR / stem / "page.tsx"
    assert route.exists(), f"Industry '{stem}': missing route file at {route}"


@pytest.mark.parametrize("stem", INDUSTRY_STEMS)
def test_industry_career_slugs_in_registry(stem):
    """Every career slug listed in an industry file must be in careerPageRegistry."""
    ts = INDUSTRIES_DIR / f"{stem}.ts"
    content = ts.read_text()
    slugs = SLUG_RE_IND.findall(content)
    missing = [s for s in slugs if s not in REGISTRY_SLUGS]
    assert not missing, (
        f"Industry '{stem}': career slugs not in careerPageRegistry "
        f"(run generate_career_pages.py for these occupations):\n"
        + "\n".join(f"  {s}" for s in missing)
    )


@pytest.mark.parametrize("stem", INDUSTRY_STEMS)
def test_industry_career_scores_valid(stem):
    """All career scores in industry files must be integers 0–100."""
    ts = INDUSTRIES_DIR / f"{stem}.ts"
    content = ts.read_text()
    bad = [s for s in SCORE_RE.findall(content) if not (0 <= int(s) <= 100)]
    assert not bad, f"Industry '{stem}': scores out of 0–100 range: {bad}"


@pytest.mark.parametrize("stem", INDUSTRY_STEMS)
def test_industry_career_growth_format(stem):
    """Growth values must be formatted like '+7%', '-3%', '~0%'."""
    ts = INDUSTRIES_DIR / f"{stem}.ts"
    content = ts.read_text()
    bad = [g for g in GROWTH_RE.findall(content) if not GROWTH_FMT.match(g)]
    assert not bad, f"Industry '{stem}': malformed growth values: {bad}"


@pytest.mark.parametrize("stem", INDUSTRY_STEMS)
def test_industry_career_openings_format(stem):
    """Openings values must be formatted like '31,300'."""
    ts = INDUSTRIES_DIR / f"{stem}.ts"
    content = ts.read_text()
    bad = [o for o in OPENINGS_RE_IND.findall(content) if not OPENINGS_FMT_IND.match(o)]
    assert not bad, f"Industry '{stem}': malformed openings values: {bad}"


@pytest.mark.parametrize("stem", INDUSTRY_STEMS)
def test_industry_career_levels_valid(stem):
    """All career levels must be 1–5."""
    ts = INDUSTRIES_DIR / f"{stem}.ts"
    content = ts.read_text()
    bad = [l for l in LEVEL_RE.findall(content) if int(l) not in range(1, 6)]
    assert not bad, f"Industry '{stem}': invalid level values: {bad}"


@pytest.mark.parametrize("stem", INDUSTRY_STEMS)
def test_industry_no_duplicate_slugs(stem):
    """No career slug should appear more than once in an industry file."""
    ts = INDUSTRIES_DIR / f"{stem}.ts"
    content = ts.read_text()
    slugs = SLUG_RE_IND.findall(content)
    seen, dupes = set(), []
    for s in slugs:
        if s in seen:
            dupes.append(s)
        seen.add(s)
    assert not dupes, f"Industry '{stem}': duplicate slugs: {dupes}"


def test_industry_level_labels_consistent():
    """LEVEL_LABELS in all industry files must use 'Lead or Specialist' for level 4."""
    if not INDUSTRIES_DIR.exists():
        pytest.skip("industries dir not found")
    bad = []
    label4_re = re.compile(r'4:\s*["\']([^"\']+)["\']')
    for ts in INDUSTRY_FILES:
        content = ts.read_text()
        m = label4_re.search(content)
        if m and m.group(1) != "Lead or Specialist":
            bad.append(f"{ts.stem}: level 4 label is '{m.group(1)}', expected 'Lead or Specialist'")
    assert not bad, "Inconsistent level 4 labels:\n" + "\n".join(bad)


@pytest.mark.parametrize("code", CARD_IDS)
def test_no_semicolons_in_emerging_titles(code):
    """Emerging job titles should be split by semicolon."""
    card = next(c for c in CARDS if c["onet_code"] == code)
    for title in card.get("emergingTitles", []):
        assert ";" not in title, f"{code}: semicolon found in emerging job title '{title}' (indicates failed split)"


@pytest.mark.parametrize("code", CARD_IDS)
def test_no_duplicate_stats(code):
    """Risks and opportunities should not use the exact same stat and statLabel."""
    card = next(c for c in CARDS if c["onet_code"] == code)
    risks = card.get("risks", {})
    opportunities = card.get("opportunities", {})
    
    risk_stat = risks.get("stat")
    opp_stat = opportunities.get("stat")
    risk_label = risks.get("statLabel")
    opp_label = opportunities.get("statLabel")
    
    if risk_stat and risk_stat == opp_stat:
        assert risk_label != opp_label, f"{code}: risks and opportunities have exact same stat ({risk_stat}) and label ({risk_label})"


@pytest.mark.parametrize("code", CARD_IDS)
def test_minimum_task_count(code):
    """Every card must have at least 7 real tasks in taskData."""
    card = next(c for c in CARDS if c["onet_code"] == code)
    tasks = card.get("taskData", [])
    assert len(tasks) >= 7, f"{code}: only {len(tasks)} tasks in taskData (minimum 7 required)"


@pytest.mark.parametrize("code", CARD_IDS)
def test_no_placeholder_tasks(code):
    """taskData must not contain fabricated placeholder tasks."""
    card = next(c for c in CARDS if c["onet_code"] == code)
    placeholder_sentinels = {
        "Perform core responsibilities for this occupation.",
        "Ensure compliance with regulations.",
        "Manage day-to-day operations.",
    }
    for t in card.get("taskData", []):
        assert t.get("full") not in placeholder_sentinels, (
            f"{code}: placeholder task found in taskData: '{t.get('full')}'"
        )


@pytest.mark.parametrize("code", CARD_IDS)
def test_static_task_intro(code):
    """Every card must have the exact standard static taskIntro."""
    card = next(c for c in CARDS if c["onet_code"] == code)
    standard = "Not all tasks are affected equally. Knowing which ones AI handles well, and which still need a human, is how to focus skill-building."
    intro = card.get("taskIntro")
    assert intro == standard, f"{code}: taskIntro is not the standard static string. Found: '{intro}'"


# ── Cross-cluster career map data ─────────────────────────────────────────────

def _load_cross_family_branches() -> list[dict]:
    """Load cross-family branches from cluster_branches.csv."""
    if not CLUSTER_BRANCHES_CSV.exists():
        return []
    import csv
    branches = []
    with open(CLUSTER_BRANCHES_CSV, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("is_cross_family") == "true":
                branches.append(r)
    return branches


CROSS_FAMILY_BRANCHES = _load_cross_family_branches()


def test_outbound_cross_family_in_career_map():
    """For each cross-family branch A→B, card A's careerCluster must include B with fit/steps."""
    if not CROSS_FAMILY_BRANCHES:
        pytest.skip("No cross-family branches defined")
    missing = []
    no_fit = []
    for branch in CROSS_FAMILY_BRANCHES:
        from_code = branch["from_onet_code"]
        to_code = branch["to_onet_code"]
        card = CARD_BY_CODE.get(from_code)
        if not card:
            continue  # card not yet generated — not a cross-cluster bug
        cluster_codes = {n.get("code") for n in card.get("careerCluster", [])}
        if to_code not in cluster_codes:
            missing.append(f"{from_code} → {to_code}: target missing from careerCluster")
            continue
        node = next(n for n in card["careerCluster"] if n.get("code") == to_code)
        if not node.get("fit") or not node.get("steps"):
            no_fit.append(f"{from_code} → {to_code}: present but missing fit/steps")
    errors = missing + no_fit
    assert not errors, (
        "Cross-family outbound targets missing from career map "
        "(run adjacent_roles.py --code <from_code>):\n" + "\n".join(errors)
    )


def test_inbound_cross_family_in_career_map():
    """For each cross-family branch A→B, card B's careerCluster must include A with isEntryPoint=true."""
    if not CROSS_FAMILY_BRANCHES:
        pytest.skip("No cross-family branches defined")
    missing = []
    no_entry_flag = []
    no_fit = []
    for branch in CROSS_FAMILY_BRANCHES:
        from_code = branch["from_onet_code"]
        to_code = branch["to_onet_code"]
        card = CARD_BY_CODE.get(to_code)
        if not card:
            continue  # card not yet generated
        cluster_codes = {n.get("code") for n in card.get("careerCluster", [])}
        if from_code not in cluster_codes:
            missing.append(f"{to_code} ← {from_code}: entry point missing from careerCluster")
            continue
        node = next(n for n in card["careerCluster"] if n.get("code") == from_code)
        if not node.get("isEntryPoint"):
            no_entry_flag.append(f"{to_code} ← {from_code}: present but missing isEntryPoint flag")
        if not node.get("fit") or not node.get("steps"):
            no_fit.append(f"{to_code} ← {from_code}: present but missing fit/steps")
    errors = missing + no_entry_flag + no_fit
    assert not errors, (
        "Cross-family inbound entry points missing from career map "
        "(run adjacent_roles.py --code <to_code>):\n" + "\n".join(errors)
    )

