"""Prompt builders for occupation card sections.

Each card section (risks, opportunities, howToAdapt, taskLabels) has its
own prompt builder that returns the JSON schema + instructions for that
section only. All prompt text lives here — generate_next_steps.py calls
these functions, never defines prompt strings inline.

The shared occupation context (tone guide, occupation data, AEI metrics,
approved sources) is built once by occupation_context() and prepended
to every section prompt.

Functions:
    occupation_context(occ, tasks, metrics, a_scores, tone_guide,
                       approved_sources, career_spec) → str
        Shared preamble: tone guide, career spec, occupation data block,
        task table, source rules. Every section prompt starts with this.

    risks_opps_prompt(code, low_data) → str
        JSON schema + instructions for risks + opportunities sections.
        Includes stat selection rules, statLabel format rules, citation
        prohibition in statLabel, low-data warnings.

    how_to_adapt_prompt() → str
        JSON schema for howToAdapt.alreadyIn, howToAdapt.thinkingOf,
        and howToAdapt.quotes[]. Quote quality rules, source diversity
        constraints.

    task_labels_prompt(tasks) → str
        JSON schema for taskLabels — short 3-5 word labels for each task.
        Includes the full task texts that need labeling.

    sources_prompt() → str
        JSON schema for sources[]. Always appended to content sections.

    build_full_prompt(occ, tasks, metrics, a_scores, tone_guide,
                      career_spec, approved_sources) → str
        Assembles all section prompts into one mega-prompt. Used by
        full-card mode. Equivalent to the former monolithic build_prompt().

    build_section_prompt(sections, occ, tasks, metrics, a_scores,
                         tone_guide, career_spec, approved_sources) → str
        Assembles only the specified section prompts. Used by --section
        flag. sections is a list like ["risks", "opportunities"].

Prompt rules (enforced in all section prompts):
    - statLabel: plain text only, no citations, 5-8 words, must
      complete a sentence after the stat number, must not end with a
      conjunction/preposition
    - body fields: inline [Name, Date] citations required, must resolve to sources[] by name
    - No em dashes, no prohibited phrases (see tone guide)
"""


# ── Shared context ────────────────────────────────────────────────────────────

def occupation_context(occ: dict, tasks: list, metrics: dict, a_scores: dict,
                       tone_guide: str, approved_sources: str = "",
                       career_spec: str = "") -> tuple[str, bool]:
    """Build the shared occupation context block prepended to every prompt.

    Returns (context_str, low_data) where low_data is True when no tasks
    have sufficient AEI signal (n >= 100).
    """
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
    w_auto = m.get("weighted_automation_pct", "unknown")
    w_aug = m.get("weighted_augmentation_pct", "unknown")

    tasks_with_signal = [t for t in tasks if t.get("n") is not None and t["n"] >= 100]
    low_data = len(tasks_with_signal) == 0

    task_lines = []
    for t in tasks:
        if t["n"] is not None:
            task_lines.append(
                f"  - {t['full']}\n"
                f"    weight={t.get('weight', '?')} | auto={t['auto']}% aug={t['aug']}% "
                f"success={t['success']}% n={t['n']}"
            )
        else:
            task_lines.append(f"  - {t['full']}\n    weight=? | no AEI data")
    task_block = "\n".join(task_lines)

    sample_titles = occ.get("Sample Job Titles", "").strip()
    common_names_line = f"Also known as: {sample_titles}\n" if sample_titles else ""

    career_spec_block = f"\n=== CAREER PAGE SPEC ===\n{career_spec}\n" if career_spec else ""

    context = f"""You are generating career page content for ai-proof-careers.com.

Below are your style rules. Follow them exactly.

=== TONE GUIDE ===
{tone_guide}
{career_spec_block}
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
- Do not cite the same source more than twice across the entire card (risks, opportunities, howToAdapt combined). Each section (risks.body, opportunities.body, howToAdapt.alreadyIn, howToAdapt.thinkingOf) must use at least 2 distinct sources internally — never repeat the same citation more than once within a single section.
- Use [Name, Date] inline citations (e.g. [NiemanLab, Mar 2024]) where Name exactly matches the "name" field of a source in sources[]. Do NOT use numeric citations like [1] or [2].
- NEVER cite: Gartner, IDC, Forrester, MarketsandMarkets — these are paywalled analyst firms with inflated projections and URL rot. Use the approved sources list instead.

{"⚠ LOW DATA WARNING: None of the tasks for this occupation have sufficient AEI data (n >= 100). The task chart on the career page will show ALL tasks in the 'AI hasn't figured these out' bucket. DO NOT cite external automation percentages (e.g. McKinsey industry estimates) as the risks stat — they will directly contradict the chart. Instead: (1) Keep risks.body brief and acknowledge limited AEI signal. (2) Use a hiring trend, job growth, or demand stat for risks.stat instead of an automation rate. (3) For opportunities, cite augmentation demand or skill premium stats." if low_data else ""}"""

    return context, low_data


# ── Section prompt fragments ──────────────────────────────────────────────────

def risks_opps_prompt(code: str, low_data: bool) -> str:
    """JSON schema + instructions for risks and opportunities sections.

    Includes stat selection rules, statLabel format constraints, citation
    prohibition in statLabel, and low-data warnings when AEI coverage
    is insufficient.
    """
    return f"""  "onet_code": "{code}",
  "risks": {{
    "body": "2–3 sentences about why AI is a genuine threat to this specific role's job prospects — not 'AI is advancing' but what specifically is being automated, commoditized, or consolidated in THIS occupation. Include a concrete displacement signal (posting decline, layoffs, role consolidation, or a specific task now handled by AI tools). Do NOT frame workforce shortages as risks — a shortage drives up demand and is good for workers. {"LOW DATA: Do NOT cite external automation percentages in this section — the task chart will show no AI activity and they will directly contradict each other. Focus on hiring trends, job growth projections, or platform displacement instead." if low_data else ""}Inline citations like [1] where sourced. NEVER mention task weight values or write phrases like '(weight 20.9)' — weight is an internal metric, not user-facing content. NEVER cite the number of AI conversations or interactions (e.g. 'across 2,800 AI interactions', 'n=702 observations') — these are internal dataset counts, not user-facing evidence. If citing AEI task automation rates, summarize the pattern in one sentence rather than listing rates per individual task; PREFER leading with an external displacement signal (posting trends, layoffs, platform consolidation) over AEI percentages — use AEI data as supporting color, not the headline. AVOID: vague 'AI will transform this field' framing, generic white-collar displacement narratives, repeating the role score. NEVER write phrases like 'this role scores X out of 5' or 'this role's resilience score reflects' — the score is displayed separately in the page header and must not appear in body prose. PREFER: name a specific task or workflow AI handles well in this role, cite a concrete displacement signal, connect it to what practitioners in THIS role actually experience.",
    "stat": "Pick the single most concrete, surprising number from the risks body. Set to null if no strong non-redundant stat exists. {"LOW DATA: Must NOT be an automation rate or AI task percentage — the task chart shows no AI activity and they will directly contradict." if low_data else ""} STAT SELECTION RULES — AVOID these (redundant with other page sections): task automation/augmentation %, employment growth %, salary figures, workforce shortage counts or unfilled job figures (shortages signal demand, not risk — use in opportunities instead). PREFER (in priority order): (1) Hiring trend shifts — YoY change in job postings, time-to-fill changes (Lightcast, Indeed Hiring Lab). (2) AI tool adoption rates among practitioners in THIS specific role (HubSpot State of Marketing, CMI, Stack Overflow Survey, etc). (3) Productivity/output impact — e.g. content volume increase, time-to-draft reduction. (4) Displacement signals — layoffs, role consolidation, posting declines, freelance rate compression (Upwork Research Institute). (5) WEF Future of Jobs net decline ranking or projected job loss figure. (6) Industry ad spend or budget shift away from human production toward AI tools. (7) Contract/freelance ratio shifts. (8) Career transition rates out of this role. LAST RESORT: BLS projected growth/decline % for this occupation — always available, always citable, acceptable when nothing better exists. It is OK to set stat to null rather than use a redundant stat type.",
    "statLabel": "Required if stat is non-null. 5–8 words max. Completes the sentence naturally AFTER the number — e.g. stat '-12%' + statLabel 'drop in marketing manager postings'. Do NOT repeat the number. Do NOT include a year or date in parentheses. NO inline citations like [1] — plain text only. Must not end with a conjunction or preposition.",
    "statSourceName": "Required if stat is non-null. Publisher name, e.g. 'Lightcast' or 'World Economic Forum'.",
    "statSourceTitle": "Required if stat is non-null. Full article or report title.",
    "statSourceDate": "Required if stat is non-null. Publication date as 'Mon YYYY', e.g. 'Jan 2025'.",
    "statSourceUrl": "Required if stat is non-null. Canonical URL. Must be a real, verifiable URL."
  }},
  "opportunities": {{
    "body": "2–3 sentences about why a skilled practitioner in this role is harder to replace than the risks section suggests — what tasks require human judgment, relationship, or accountability that AI cannot replicate, and what that means economically for practitioners who lean into it. Inline citations like [1]. NEVER mention numeric task weight values (e.g. 'weight 20.9') — say 'most important task' or 'core task' instead. NEVER cite the number of AI conversations or interactions (e.g. 'across 2,800 AI interactions', 'n=702 observations') — these are internal dataset counts, not user-facing evidence. If citing AEI augmentation or low-automation rates, summarize the pattern in one sentence rather than listing rates per task; PREFER leading with an external durability signal (trust requirements, regulatory constraints, client relationship data) over AEI percentages — use AEI data as supporting color, not the headline. AVOID: generic 'use AI as a tool' framing, vague upskilling advice, restating what the risks section already said, citing AI adoption rates without connecting to practitioner outcomes. CRITICAL: Stay within this role — do NOT describe opportunities by pivoting to a different job title or career path (e.g. 'web admins who move into cybersecurity' or 'those who transition to DevOps'). The opportunities section is about what makes THIS role durable, not about adjacent roles the person could move to. Career transitions belong in howToAdapt. PREFER: identify the specific tasks or client interactions where human judgment is irreplaceable in this role, name a concrete economic upside (premium, expanded scope, or a market the role now serves that it couldn't before), make it specific enough that a practitioner in this field would recognize it.",
    "stat": "Pick the single most concrete number from the opportunities body. Set to null if no strong non-redundant stat exists. MUST be completely different from the stat used in the risks section. Do not reuse the same statistic. STAT SELECTION RULES — AVOID these (redundant with other page sections): task automation/augmentation %, employment growth %, salary figures. PREFER (in priority order): (1) Skill or certification salary premiums. (2) Client/consumer trust or preference for human-produced content/advice (Pew, Edelman, Reuters Institute, Kantar). (3) Downstream demand creation or market expansion driven by AI — e.g. content volume growth creating more editorial/strategy need. (4) Regulatory or licensing barriers that structurally limit automation. (5) AI tool adoption rates showing human-AI collaboration patterns (HubSpot, CMI, Influencer Marketing Hub). (6) Industry investment in AI for this domain, or budget growth for AI-augmented roles. (7) Productivity multipliers from AI tools in this role — output per practitioner gains. (8) Demand growth for senior/strategic roles as AI handles execution-layer work. LAST RESORT: BLS projected growth/decline % for this occupation — always available, always citable, acceptable when nothing else fits. It is OK to set stat to null rather than use a redundant stat type.",
    "statLabel": "Required if stat is non-null. 5–8 words max. Completes the sentence naturally AFTER the number — e.g. stat '66%' + statLabel 'of developers now use AI coding tools'. Do NOT repeat the number. Do NOT include a year or date in parentheses. NO inline citations like [1] — plain text only. Must not end with a conjunction or preposition.",
    "statSourceName": "Required if stat is non-null. Publisher name.",
    "statSourceTitle": "Required if stat is non-null. Full article or report title.",
    "statSourceDate": "Required if stat is non-null. Publication date as 'Mon YYYY'.",
    "statSourceUrl": "Required if stat is non-null. Canonical URL. Must be a real, verifiable URL."
  }}"""


def how_to_adapt_prompt() -> str:
    """JSON schema for howToAdapt section: alreadyIn, thinkingOf, and quotes.

    Includes quote quality rules, source diversity constraints, and
    persona-specific writing instructions.
    """
    return """  "howToAdapt": {
    "alreadyIn": "3–4 sentences structured in two parts. Part 1 (immediate): one concrete action to take now. Part 2 (6-month): where to build depth over time — the areas AI handles worst for this specific role. Inline citations. Do NOT use em dashes.",
    "thinkingOf": "3–4 sentences for someone considering entering this field. Concrete portfolio or credential advice specific to this role — not generic 'learn AI tools' advice. Do NOT repeat statistics already cited in the risks section. Inline citations. Do NOT use em dashes. Do NOT cite the same source more than once within this section — each inline citation must reference a different source.",
    "quotes": [
      {
        "persona": "alreadyIn",
        "quote": "A quote that helps someone already in this role understand how their work is changing. Must come from sources[]. QUOTE SELECTION RULES — pick the BEST available from this priority list: (1) A named practitioner or leader describing a specific skill shift, workflow change, or strategic move in this role — e.g. 'We stopped hiring junior analysts for data cleaning and started hiring people who can interrogate what the model outputs' (HBR, named CTO). (2) A research finding that reveals HOW the role is shifting — not that it's shifting, but what specifically is different now vs. 2 years ago. E.g. 'Marketing teams that adopted AI content tools reduced production headcount 30% but increased spend on senior strategists' (McKinsey). (3) An industry-specific insight about where human judgment still wins — e.g. 'In complex commercial underwriting, AI models miss 40% of risk factors that experienced underwriters catch through relationship context' (industry report). NEVER USE: (a) Motivational platitudes ('Being good isn't good enough', 'Adapt or die'). (b) BLS statistics restated in quotation marks — 'Employment is projected to grow 7%' is not a quote. (c) Generic AI hype — 'AI will transform this field'. (d) Quotes shorter than 50 characters. (e) Bare percentages with no insight about what to DO or what's CHANGING. Good sources: GitHub Blog (github.blog) and Stack Overflow Blog (stackoverflow.blog) frequently publish named engineer, CTO, and exec quotes about AI changing their workflows — search these first for technology roles. Also: HBR interviews, MIT Sloan, practitioner blogs (Pragmatic Engineer, InfoQ), industry association reports with named commentators, NYT/WSJ interviewing professionals. A quote attributed to 'Sarah Vessels, GitHub Staff Engineer' or 'Thomas Dohmke, GitHub CEO' is far stronger than one attributed to a report — always search for the specific article and named person before falling back to a report summary. If no real practitioner quote exists, use a key finding from a research report — but attribute it to the report, not to a person.",
        "attribution": "Person's name and title (preferred), or 'Report Title, Publisher' if no named person",
        "sourceUrl": "https://..."
      },
      {
        "persona": "alreadyIn",
        "quote": "A SECOND quote covering a DIFFERENT angle than the first (e.g. first = tool adoption, second = where human judgment matters most). Same quality rules. Omit entirely if no meaningfully different second angle exists.",
        "attribution": "...",
        "sourceUrl": "https://..."
      },
      {
        "persona": "thinkingOf",
        "quote": "A quote that helps someone considering this field understand the entry landscape — what skills or credentials matter now, how hiring is changing, or what distinguishes strong candidates. NOT a generic growth stat. Same selection rules as alreadyIn: prefer named practitioners, industry-specific insights about entry paths, or research findings about what hiring managers value now vs. before AI. NEVER restate BLS projections as a quote.",
        "attribution": "...",
        "sourceUrl": "https://..."
      },
      {
        "persona": "thinkingOf",
        "quote": "A SECOND quote covering a DIFFERENT entry angle than the first. Same quality rules. Omit if no meaningfully different second angle exists.",
        "attribution": "...",
        "sourceUrl": "https://..."
      }
    ]
  }"""


def task_labels_prompt(tasks: list[dict]) -> str:
    """JSON schema for taskLabels — maps full task text to short 3-5 word labels.

    Only included in full-card prompts (not section patches). Tasks section
    patching uses build_task_data() directly without a prompt.
    """
    return """  "taskLabels": {
    "Full task text here...": "3-5 word short label. Verb + object style. Use / for combined verbs (Write/analyze programs). Condense, don't truncate — capture the meaning, not the first N words."
  }"""


def sources_prompt() -> str:
    """JSON schema for sources array. Appended to every content section prompt."""
    return """  "sources": [
    {"name": "Publisher name", "title": "Article or report title", "date": "Mon YYYY", "url": "https://..."}
  ]
  NOTE: Every url in sources[] must be a specific article or report page — not a homepage. Find the real URL via web search before writing it. Never guess or construct a path from a known domain pattern."""


# ── Closing rules ─────────────────────────────────────────────────────────────

def _closing_rules(include_quotes: bool = True) -> str:
    """Shared rules appended after the JSON schema in every prompt."""
    rules = """Rules:
- All [Name, Date] inline citations must resolve to an entry in sources[] by the "name" field. Do NOT use numeric citations like [1].
- Every inline citation [Name, Date] in risks.body, opportunities.body, howToAdapt.alreadyIn, and howToAdapt.thinkingOf must have a matching entry in sources[] with the same "name". Missing entries will cause broken links on the page.
- statLabel must be plain text only — NO inline citations. The stat source is tracked separately via statSourceName/statSourceTitle/statSourceUrl. The stat does NOT need to appear in the body text — it is displayed separately as a pull-stat callout above the prose.
- SOURCE URLS: Before writing any url (in sources[] or quote sourceUrl fields), find the specific article or report page via web search. Never construct or guess a URL path. If web search returns no specific article, use the approved homepage URL and note it needs manual verification. Generic homepages (e.g. hbr.org/, upwork.com/research) are not acceptable as quote sourceUrls.
- Do not use "lean into", "AI is taking over", or other prohibited phrases from the tone guide"""

    if include_quotes:
        rules += """
- Quotes: sourceUrl must be the url of a source in sources[]. Each quote must help the reader understand how this specific role is changing or how to navigate it. All 4 must cover different topics. Every quote must pass this test: "Would this quote have been different 5 years ago?" If no, it's too generic. REJECT: (a) BLS statistics in quotation marks — that's not a quote, (b) motivational platitudes under 50 characters, (c) bare percentages with no insight about what's changing or what to do, (d) static credential requirements ("typically need a bachelor's degree"). At most 1 quote across all 4 slots may come from BLS Occupational Outlook Handbook — if you use it, the other 3 must come from different sources. Prefer practitioner voices: HBR, MIT Sloan, Pragmatic Engineer, InfoQ, industry association reports with named commentators, NYT/WSJ interviewing professionals."""

    rules += "\n- Respond ONLY with the JSON object, no other text"
    return rules


# ── Assembled prompts ─────────────────────────────────────────────────────────

def build_full_prompt(occ: dict, tasks: list, metrics: dict, a_scores: dict,
                      tone_guide: str, career_spec: str,
                      approved_sources: str = "") -> str:
    """Assemble the full card prompt (all sections).

    Equivalent to the former monolithic build_prompt() in generate_next_steps.py.
    Used when generating a complete new card (no --section flag).
    """
    context, low_data = occupation_context(
        occ, tasks, metrics, a_scores, tone_guide, approved_sources, career_spec
    )
    code = occ["Code"]

    json_block = "\n".join([
        "Then generate the following JSON object. All prose must follow the tone guide.",
        "",
        "{",
        risks_opps_prompt(code, low_data) + ",",
        how_to_adapt_prompt() + ",",
        task_labels_prompt(tasks) + ",",
        sources_prompt(),
        "}",
    ])

    return f"{context}\n{json_block}\n\n{_closing_rules(include_quotes=True)}"


def build_section_prompt(sections: list[str], occ: dict, tasks: list,
                         metrics: dict, a_scores: dict, tone_guide: str,
                         career_spec: str = "",
                         approved_sources: str = "") -> str:
    """Assemble a prompt for only the specified sections.

    Used by --section flag to regenerate specific parts of an existing card.
    sections is a list like ["risks", "opportunities"] or ["howToAdapt"].

    Valid section names:
        "risks", "opportunities" — always generated together
        "howToAdapt"             — adaptation advice + quotes
    """
    context, low_data = occupation_context(
        occ, tasks, metrics, a_scores, tone_guide, approved_sources, career_spec
    )
    code = occ["Code"]

    parts = []
    has_quotes = False

    # risks and opportunities are always generated together
    if "risks" in sections or "opportunities" in sections:
        parts.append(risks_opps_prompt(code, low_data))

    if "howToAdapt" in sections:
        parts.append(how_to_adapt_prompt())
        has_quotes = True

    # sources always included with any content section
    parts.append(sources_prompt())

    json_block = "\n".join([
        "Then generate the following JSON object. All prose must follow the tone guide.",
        "",
        "{",
        ",\n".join(parts),
        "}",
    ])

    return f"{context}\n{json_block}\n\n{_closing_rules(include_quotes=has_quotes)}"
