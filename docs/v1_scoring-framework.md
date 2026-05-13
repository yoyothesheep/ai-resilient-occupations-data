# AI-Resilience Job Scoring Skill

## Purpose
Score any occupation on a 1–5 AI-proof scale for resilience to AI displacement, then rank using labor market data.

**AI-Proof Score (1–5):**
- **1** = Highly vulnerable — most tasks automatable in near term
- **5** = Highly resilient — protected by hard defenses and/or actively benefits from AI's rise

**Final Ranking (0–1):** Composite of AI-proof score, projected growth, and job openings.

---

## Scoring Architecture

### AI-Proof Score

The AI-proof score is a **weighted blend of two groups**:
- **Resiliency Score (65% weight):** Attributes 1–8 — why AI can't take over
- **Opportunity Score (35% weight):** Attributes 9–10 — why AI's rise actively helps this role

`role_resilience_score = (Defensive Score × 0.65) + (Offensive Score × 0.35)`

Normalize to 1.0–5.0 range with one decimal place.

### Final Ranking

The final ranking combines the AI-proof score with labor market signals into a 0.0–1.0 composite:

`final_ranking = 0.50 × resilience_norm + 0.30 × growth_norm + 0.20 × openings_norm`

**Normalization:**
- `resilience_norm` = (role_resilience_score - 1) / 4
- `growth_norm` = see below
- `openings_norm` = log-transform + min-max scale (handles extreme skew in job opening counts)

**Growth normalization** uses the best available data per occupation:

1. **Preferred — `Employment Change, 2024-2034`** (numeric, from [BLS Employment Projections](https://data.bls.gov/projections/occupationProj)): Apply a sign-preserving log transform — `sign(x) × log1p(|x|)` — to compress the wide variance in percent changes (−36% to +50%). Then min-max scale across all occupations with numeric data to produce a 0–1 value.

2. **Fallback — `Projected Growth`** (category string scraped from O*NET): Used when an occupation isn't listed separately in BLS projections (e.g. specialty subcodes like `29-1141.03` Critical Care Nurses). Mapped ordinally to 0–1:

   | Category | Value |
   |----------|-------|
   | Decline | 0.0 |
   | Little or no change | 0.2 |
   | Slower than average | 0.4 |
   | Average | 0.6 |
   | Faster than average | 0.8 |
   | Much faster than average | 1.0 |

---

## Attribute Weights (within Defensive group)

| Tier | Attributes | Weight per Attribute |
|------|-----------|---------------------|
| High | A1 Physical Presence, A3 Novel Judgment, A4 Legal Accountability | 1.5× |
| Medium | A2 Trust as Core Product, A5 Deep Org Context, A8 Changed by Experience | 1.0× |
| Low | A6 Political Navigation, A7 Creative POV | 0.7× |

Defensive Score = weighted average of A1–A8 scores using above weights, normalized to 1–5.

Offensive Score = average of A9 and A10, normalized to 1–5.

---

## Per-Attribute Scoring Rubrics

### A1 — Physical Presence & Dexterity Required
*Weight: HIGH. Does the job require being physically present in unstructured environments and using hands-on dexterity that robots cannot reliably replicate?*

| Score | Description |
|-------|-------------|
| 1 | Fully remote-compatible, no physical interaction required |
| 2 | Some physical presence but in controlled/structured environments |
| 3 | Regular physical presence, moderate dexterity in semi-structured settings |
| 4 | Frequent unstructured physical environments, significant manual skill required |
| 5 | Core value is physical presence in highly unstructured environments; dexterity is irreplaceable |

### A2 — Trust is the Core Product
*Weight: MEDIUM. Do clients/patients/users buy a human relationship and accountability, not just information or output?*

| Score | Description |
|-------|-------------|
| 1 | Purely transactional — output is what matters, not who delivers it |
| 2 | Some relationship value but easily substituted |
| 3 | Relationship matters but is not the primary value delivered |
| 4 | Trust and human accountability are central to the service |
| 5 | The human relationship IS the product — AI delivery would fundamentally undermine value |

### A3 — Novel, Ambiguous Judgment in High-Stakes Situations
*Weight: HIGH. Does the job regularly require genuine reasoning in new, ambiguous situations where pattern-matching fails and mistakes have serious consequences?*

| Score | Description |
|-------|-------------|
| 1 | Tasks are well-defined with clear inputs/outputs; stakes are low |
| 2 | Some judgment required but within familiar, well-mapped scenarios |
| 3 | Regular judgment calls; moderate stakes; situations are varied but not genuinely novel |
| 4 | Frequent high-stakes judgment in ambiguous, novel situations |
| 5 | Core value is navigating genuinely unprecedented situations where failure is catastrophic |

### A4 — Legal or Ethical Accountability
*Weight: HIGH. Must a licensed/credentialed human be legally liable for decisions or outputs? Would society/law require human sign-off regardless of AI capability?*

| Score | Description |
|-------|-------------|
| 1 | No licensure, certification, or legal accountability required |
| 2 | Some credentials required but liability is limited or diffuse |
| 3 | Licensed role with meaningful but not exclusive accountability |
| 4 | Licensed professional with direct legal liability for decisions |
| 5 | Human must sign, stamp, certify, or render judgment by law — no AI substitute permitted |

### A5 — Deep Contextual Knowledge Built Over Time
*Weight: MEDIUM. Does the role depend heavily on accumulated institutional knowledge — knowing the history, the people, the workarounds — that AI cannot observe or replicate?*

| Score | Description |
|-------|-------------|
| 1 | Knowledge is general and transferable; any trained person could step in |
| 2 | Some organizational context helpful but not essential |
| 3 | Meaningful institutional knowledge needed; takes months to acquire |
| 4 | Deep org-specific knowledge is a major part of the role's value |
| 5 | Years of accumulated institutional knowledge is the core asset; loss would be severely disruptive |

### A6 — Political & Interpersonal Navigation
*Weight: LOW. Is the role's value substantially derived from coalition-building, managing stakeholder relationships, reading organizational dynamics, and negotiating competing agendas?*

| Score | Description |
|-------|-------------|
| 1 | Individual contributor with minimal stakeholder management |
| 2 | Some coordination but relationships are transactional |
| 3 | Regular stakeholder management in structured contexts |
| 4 | Political navigation across complex stakeholder landscapes is core to success |
| 5 | Role exists primarily to manage organizational dynamics and competing human agendas |

### A7 — Creative Work with a Genuine Point of View
*Weight: LOW. Does the market value this work specifically because it reflects a distinct human perspective, aesthetic, or cultural voice — where AI-generated work would be seen as inferior or inauthentic?*

| Score | Description |
|-------|-------------|
| 1 | Output is functional/utilitarian; human authorship irrelevant |
| 2 | Creativity valued but audience is indifferent to human vs AI origin |
| 3 | Human creativity preferred but AI-assisted work widely accepted |
| 4 | Distinct human perspective is a significant differentiator |
| 5 | The person IS the product; human authorship is the primary source of market value |

### A8 — Work That Requires Being Changed by the Experience
*Weight: MEDIUM. Does the role require a practitioner who genuinely grows, adapts, and is transformed through the human relationship — where that growth is inseparable from the value delivered?*

| Score | Description |
|-------|-------------|
| 1 | Delivery is one-directional; practitioner growth irrelevant to outcome |
| 2 | Adaptation occurs but is procedural, not relational |
| 3 | Practitioner adapts meaningfully but relationship is time-limited |
| 4 | Genuine two-way growth through the relationship is a significant part of value |
| 5 | The practitioner's ongoing transformation through the relationship is core to what makes the service work |

### A9 — Expertise Underutilized Due to Administrative/Volume Constraints
*Weight: OFFENSIVE. Does the role currently spend significant time on below-ceiling tasks (documentation, data gathering, routine comms) that AI will compress — freeing the expert to do more high-value work?*

| Score | Description |
|-------|-------------|
| 1 | Role is already optimized; little below-ceiling work exists |
| 2 | Some administrative burden but not a primary constraint |
| 3 | Meaningful portion of time (~20–30%) on below-ceiling tasks |
| 4 | Large portion of time (~30–50%) on below-ceiling tasks; productivity gain would be significant |
| 5 | Majority of time consumed by tasks well below skill ceiling; AI liberation would dramatically expand output and value |

### A10 — Downstream of Bottlenecks / Manages AI Systems
*Weight: OFFENSIVE. Will AI clearing upstream bottlenecks create more demand for this role? Or does this role sit in a position to manage, evaluate, and direct AI systems — making domain expertise more, not less, valuable?*

| Score | Description |
|-------|-------------|
| 1 | Role is directly in the path of automation; no downstream expansion likely |
| 2 | Limited downstream benefit; role may shrink slightly |
| 3 | Some downstream benefit or AI management opportunity |
| 4 | Clear downstream expansion as AI clears adjacent bottlenecks, or strong AI oversight role |
| 5 | Role is a direct beneficiary of AI-driven market expansion OR is the domain expert who directs/validates AI — demand will grow materially |

---

## Ceiling & Floor Rules

**Ceiling Rule:** If A1 + A3 + A4 all score ≤ 2, cap role_resilience_score at **2.5** regardless of other scores. A job with no hard defenses is fundamentally exposed.

**Floor Rule:** If A9 or A10 scores **5**, minimum role_resilience_score is **3.0**. A role that actively expands due to AI's rise has meaningful resilience even with weak defenses.

---

## Output Format

For each occupation, respond ONLY with this JSON structure:

```json
{
  "onet_code": "XX-XXXX.XX",
  "role_resilience_score": 4.2,
  "key_drivers": "2-3 sentences explaining the score"
}
```

### Key Drivers Requirements

**Key Drivers should:**
- Be written for a **high school reading level** (clear, accessible language)
- Explain **why** this job is resilient or vulnerable, not just **what** makes it so
- Be **human-centered**: focus on the actual work and people, not scoring mechanics
- Avoid ALL technical references: **NO** attribute names (A1, A2, etc.), **NO** scores in parentheses, **NO** terminology like "defensive" or "offensive"

**DO write:**
- "The work relies on physical presence in unpredictable environments that robots can't handle."
- "Clients specifically value the human relationship—they're buying trust, not just output."

**DON'T write:**
- "A1 scores high because…" or "(A1=4, A3=5)"
- "Defensive score is strong due to legal accountability (A4)"
- "Offensive advantages from A9 expertise underutilization"

---

## Calculation Steps

1. Score each attribute A1–A10 on 1–5
2. Calculate weighted defensive score:
   - High-weight attributes (A1, A3, A4): multiply score × 1.5
   - Medium-weight attributes (A2, A5, A8): multiply score × 1.0
   - Low-weight attributes (A6, A7): multiply score × 0.7
   - Sum all weighted scores, divide by sum of weights (1.5+1.0+1.5+1.5+1.0+0.7+0.7+1.0 = 8.9)
   - This gives Defensive Score on 1–5 scale
3. Calculate offensive score: average of A9 and A10
4. Apply ceiling/floor rules
5. role_resilience_score = (Defensive × 0.65) + (Offensive × 0.35)
6. Round to one decimal place
7. Compute final_ranking = weighted composite of role_resilience_score (50%), growth (30%), openings (20%), using numeric Employment Change where available, falling back to the Projected Growth category string

---

## Notes for Scoring

- Score based on the **typical practitioner** in the role, not the best-case or worst-case
- Consider what the role looks like **5 years from now** with continued AI advancement, not just today
- When in doubt on a score, ask: "If AI capability doubled tomorrow, would this attribute still protect the role?"
- The ONET Job Zone (1–5) is a useful signal: Zone 4–5 jobs tend to score higher on A3, A4, A5; Zone 1–2 jobs tend to score lower across defensive attributes but may score high on A1

---

## Tone & Clarity for Key Drivers

**See `docs/tone-guide.md`** for examples of clear, human-readable key_drivers and detailed guidance on avoiding technical notation.

**Golden rule:** Key drivers should make sense to anyone reading the results, not just the scoring team. Treat them as public-facing explanations.
