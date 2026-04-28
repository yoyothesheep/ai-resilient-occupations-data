# Career Page Content Spec

Rules for generating and reviewing occupation card content. This is the single source of truth for what goes in each section, how to populate it, and what to exclude.

See `docs/tone_guide_career_pages.md` for voice and writing style.
See `docs/data-schema.md` for the full JSON schema.

---

## Sections

### Page layout sections (top to bottom)

1. **Header** — title + score ring
2. **Hero metrics** — 3-column grid: Median Salary, Job Openings, Growth (10yr). Large numbers, not pills.
3. **Job description** — 2-sentence O*NET description + sample job title pills
4. **Why this score** — `keyDrivers`. Styled with tier-colored left border.
5. **Risks** — pull-stat callout + prose. Orange left border.
6. **Opportunities** — pull-stat callout + prose, optional subsections. Green left border.
7. **How AI Is Changing This Role, Task by Task** — section title is `text-sm font-extrabold` (larger than subsection titles). Three task groups, each with colored left border:
   - Automation group (orange): tasks where `auto > aug` and `n >= 100`
   - Augmentation group (blue): tasks where `aug > auto` and `n >= 100`
   - No-data group (gray): tasks where `n < 100` or null
   - Group headers should be Feynman-style observations, not instructions.
8. **Find [Role] Jobs** — state selector + O*NET link. Visually distinct CTA card.
9. **Explore Related Careers** — `relatedCareers`, sorted by AI score desc. See `relatedCareers` section.
10. **Sources** — numbered list matching inline `[n]` citations.

Sections 7, 8, 9 are separated from the narrative sections above by `border-t` dividers.

---

### `key_drivers`
One short paragraph. Explains *why* the role gets the score it gets — which structural factors dominate (physical presence, accountability, judgment, etc.).

- Do not cite AEI metrics directly — this is qualitative
- 2–3 sentences max
- See `docs/tone_guide_key_drivers.md` for full rubric

---

### `risks`

Schema: `{ summary: string, sections: [] }`

**`summary`** — 2–3 sentences. Lead with what AI is actually doing to the highest-weight tasks.

**Pull-stat** — a single standout number displayed large above the prose (e.g., "25% drop in entry-level tech hiring"). Pick the most concrete, surprising, or actionable stat from the prose. Must be sourced.

Rules:
- Name specific tasks. Never say "some tasks are being automated."
- Use `automation_pct` on high-weight tasks as the primary signal
- Exclude tasks where `onet_task_count < 100` — not enough real usage data
- If `ai_task_coverage_pct < 20%`: note that AI hasn't made much contact with this role yet. Short risks section is correct in that case — don't pad it
- Cite external data (BLS job growth, hiring trends) with inline `[n]` markers when available
- `sections[]` is optional — use only when there's a distinct sub-topic worth separating out
- **Never reference the role's AI resilience score or final ranking in prose.** Do not write "this role scores X out of 5" or "this role's resilience score reflects..." — the score is shown separately in the page header; restating it in body text is redundant and breaks the Feynman style rule.

---

### `opportunities`

Schema: `{ summary: string, sections: [{ title: string, body: string }] }`

**Pull-stat** — same as risks: a single standout number displayed large above the prose. Pick the most concrete stat that shows where human value persists. Must be sourced.

**`summary`** — 2–3 sentences. Lead with the strongest augmentation or durability signal.

**`sections[]`** — optional subsections, each a short paragraph. Use when there's a meaningfully distinct opportunity (e.g., augmented tasks vs. downstream demand).

Rules for what to include, in priority order:
1. **High/medium-weight tasks with high `augmentation_pct`** — human still in the loop; worth highlighting
2. **A9 score ≥ 3** — specialized expertise not easily replicated; mention as a differentiator
3. **A10 score ≥ 3** — directing/managing AI is a natural growth path
4. **Downstream demand** — when AI makes a category cheaper/faster, it often creates adjacent demand

Rules for what to exclude:
- **Do not cite tasks as "untouched opportunities" based on weight alone.** A high-weight task that AI simply hasn't automated yet is not automatically a strength — it may just be next. Only call out untouched tasks if there's a structural reason AI is unlikely to touch them (physical presence, judgment, accountability, etc.)
- Tasks with `onet_task_count < 100`: exclude
- Low-weight automated tasks: skip or mention briefly in Risks, not here

**Example of what not to do:**
> "The tasks AI hasn't touched — backups, site updates, testing — are worth watching as potential durable strengths."
→ *Wrong.* "Back up files" has weight 20.1 but no structural reason AI can't automate it. Don't cite it as an opportunity.

---

### `taskData` (chart data)

Unified list of top tasks by `task_weight`, regardless of AEI coverage. Used to power the "How AI Is Changing This Role" chart on the career page.

Fields: `task` (short label), `full` (full O*NET text, shown on hover), `auto`, `aug`, `success`, `n` (all null when no AEI data)

- Sort by `task_weight` descending
- Include tasks with and without AEI coverage — `auto` / `aug` are null when no AEI data
- Exclude tasks where `n < 100` (insufficient signal)
- Suggested max: top 10 by weight
- The chart renders null AEI fields as the "No data" group

---

### `top_automated_tasks`

Include up to 3 tasks. Requirements:
- `onet_task_count ≥ 100`
- `automation_pct > 0`
- Sort by `task_weight` descending (highest-impact first)

Fields: `task_text`, `automation_pct`, `task_weight`

---

### `top_augmented_tasks`

Include up to 3 tasks. Requirements:
- `onet_task_count ≥ 100`
- `augmentation_pct > 0`
- Sort by `task_weight` descending

Fields: `task_text`, `augmentation_pct`, `task_weight`

---

### `untouched_high_priority_tasks`

Tasks with no AEI signal (neither automated nor augmented) but high weight. Top 3 by `task_weight`.

Requirements:
- `onet_task_count ≥ 100`
- No AEI coverage (not in automated or augmented lists)

Note: these appear in the data but should **not** be framed as opportunities in prose unless there's a structural reason they're durable (see opportunities rules above).

---

### `sources`

Array of `{ id: string, name: string, title: string, date: string, url: string }`.

| Field | Description |
|---|---|
| `id` | Anchor slug, e.g. `src-1`, `src-2` — sequential, no gaps |
| `name` | Publisher name, e.g. `"Stack Overflow Blog"` |
| `title` | Article or report title |
| `date` | `"Mon YYYY"` format, e.g. `"Dec 2025"` |
| `url` | Direct link to the source page |

These are the **manually curated** sources for the risks/opportunities prose sections. The career map (cluster nodes) contributes its own sources automatically via `stat.sourceUrl` — those are appended after `data.sources` in the rendered list and get sequential numbers continuing from the last manual source.

**Citation numbering:** The page renders a unified numbered list: `data.sources` first (1…N), then unique career-map stat sources (N+1…). Inline citation markers in prose use `[n]` linking to `#src-n`. On career map cards, the stat box shows `[N] sourceName ↗` where N is the source's position in that unified list.

**For each career map emerging role stat**, populate all four fields on the `stat` object:
```ts
stat: {
  text: "The market stat sentence.",
  sourceName: "Publisher name",       // e.g. "LinkedIn Economic Graph"
  sourceTitle: "Report or article title", // e.g. "Future of Work Report: AI at Work"
  sourceDate: "Mon YYYY",             // e.g. "Nov 2023"
  sourceUrl: "https://...",           // validated live URL (no soft 404s)
}
```

- Prefer: BLS, O*NET, peer-reviewed labor economics, Stack Overflow annual survey, WEF, LinkedIn Economic Graph
- Avoid: punditry, vendor whitepapers, undated content, paywalled pages, URLs that return non-2xx or soft-404 ("currently being developed", "page not found")

---

### `keyDrivers`

Short prose (2–3 sentences) explaining why the role gets the score it does — which structural factors dominate (physical presence, accountability, judgment, etc.). Rendered as body text below the "Why this role is [tier]" heading.

- Do not cite AEI metrics directly — this is qualitative
- See `docs/tone_guide_key_drivers.md` for full rubric

---

### `risks.stat` / `opportunities.stat`

Pull-stat callout rendered large above the prose body. Three fields:

| Field | Type | Description |
|---|---|---|
| `stat` | string | The number itself, e.g. `"25%"` or `"66%"` |
| `statLabel` | string | Short phrase describing what the number means, e.g. `"drop in entry-level tech hiring, year-over-year (2024)"` |
| `statColor` | string | Hex color. Use `#ea580c` (orange) for risks, `#5a9a6e` (green) for opportunities |

Pick the single most concrete, surprising, or actionable stat from the section prose. Must be sourced (the corresponding inline `[n]` should appear in `body`).

---

### `howToAdapt`

Two short paragraphs rendering in the Opportunities section under separate headings:
- **"If you're already in this role"** → `alreadyIn`
- **"If you're thinking of entering this field"** → `thinkingOf`

Both are `ReactNode` (prose with optional inline citations). Written in Feynman style: concrete, actionable framing without jargon. Address the audience directly.

---

### `score`

Integer 0–100, computed as `final_ranking × 100`. Used to drive the score ring in the page header and tier label. Not the same as `role_resilience_score` (1.0–5.0).

---

### `sample_job_titles`

Rendered as pills below the job description. Sourced from O*NET sample job titles for this occupation.

---

### `relatedCareers` → "Explore Related Careers"

Up to 10 adjacent occupations. Generated by `scripts/adjacent_roles.py`.

**Display rules:**
- Sort by `role_resilience_score` descending — the point is to show higher-resilience options first
- Curate to ~6 roles. Drop roles that score lower than the current occupation unless they're a genuinely useful lateral move
- Each role card shows: title, openings/yr, growth %, AI resilience score + tier, fit sentence, learn list

**Fields:**

| Field | Type | Description |
|---|---|---|
| `code` | string | O*NET-SOC occupation code |
| `title` | string | Occupation title |
| `score` | number | `final_ranking × 100` (0–100 integer), same scale as page header score ring |
| `openings` | string | BLS annual job openings, formatted (e.g. `"31,300"`) |
| `growth` | string | BLS 10-year projected growth, formatted (e.g. `"+17%"`) |
| `fit` | string | One sentence explaining the lateral path. Feynman style: what's true, not what to do. |
| `learn` | string[] | 2–3 concrete skills that close the gap. Specific tools/frameworks, not vague categories. |

Similarity signals (all three used):
1. **Task text similarity** — sentence-transformer cosine similarity on weighted task embeddings
2. **Sample job title overlap** — same title string appears in both occupations' O*NET sample titles
3. **SOC family** — same 2-digit SOC prefix

---

## Data Confidence Flag

`low_data_confidence: true` when `ai_task_coverage_pct < 20%`.

When true: risks section should be short and acknowledge limited AEI coverage. Do not pad with speculation.

---

## Review Log

Structural decisions made batch-by-batch during manual review are documented here (not in `data/output/cards_review_log.md` — that file is deprecated as a spec source).

### Batch 1 — 2026-03-19 (LPN, Web Developer)
- Risks and opportunities use `{summary, sections[]}` — sections optional
- Inline `[n]` citation markers in prose, resolved by `sources` array
- Tasks with `onet_task_count < 100` excluded from task lists
- `low_data_confidence: true` when `ai_task_coverage_pct < 20%`
- Tier fields left null — to be populated once tier system is finalized
- Web Dev: "Back up files" (weight 20.1), "site tests" (13.9), "direct site updates" (14.8) were incorrectly cited as untouched opportunities — removed. High weight but no structural reason they're AI-resistant.
