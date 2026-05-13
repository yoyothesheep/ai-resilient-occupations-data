# AI-Resilience Job Scoring Framework (V2)

## Purpose
Score any occupation on its resilience to AI displacement and categorize it into one of four OpenAI-defined transition archetypes.

**The Four Categories:**
- **Grow with AI**: High Exposure, High Demand Elasticity. (AI drives productivity and market expansion).
- **Will Reorganize**: High Exposure, Strong Human Necessity. (AI automates tasks, but human presence/trust remains strictly necessary).
- **Less Immediate Change**: Low Exposure. (AI cannot automate the core physical or relationship tasks).
- **High Automation Risk**: High Exposure, Weak Human Necessity, Low Demand Elasticity. (AI automates the core output, and making it cheaper does not unlock massive new demand).

---

## Scoring Architecture (V2)

The V2 framework evaluates **12 distinct attributes** (A1–A12). 

These 12 attributes are blended into **3 Core Filters**:
1. **Exposure Filter:** `(A11 + A9 + (6 - A3) + (6 - A5) + (6 - A7)) / 5.0`
2. **Necessity Filter:** `(A1×1.5 + A4×1.5 + A2×1.0 + A8×1.0 + A6×0.7) / 5.7`
3. **Elasticity Filter:** `(A12 + A10) / 2.0`

### Categorization Matrix
Occupations are assigned to a category using the following thresholds:
- `is_exposed` = Exposure ≥ 3.2
- `is_necessary` = Necessity ≥ 1.8
- `is_elastic` = Elasticity ≥ 3.5

| Exposed | Elastic | Necessary | Category |
|---------|---------|-----------|----------|
| Yes | Yes | — | Grow with AI |
| Yes | No | Yes | Will Reorganize |
| Yes | No | No | High Automation Risk |
| No | — | — | Less Immediate Change |

### Final Ranking (The Natural Math Blend)
To rank occupations *within* their categories, we calculate a 0.0–1.0 composite score:

`Final Rank = Necessity(35%) + Elasticity(25%) - Exposure Penalty(20%) + BLS Growth(15%) + BLS Openings(5%)`

*Note: BLS Growth and Openings are log-transformed and min-max scaled to prevent massive job counts from skewing the underlying AI resilience metrics.*

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
| 1 | Role is directly in the path of automation; no downstream expansion likely |
| 2 | Limited downstream benefit; role may shrink slightly |
| 3 | Some downstream benefit or AI management opportunity |
| 4 | Clear downstream expansion as AI clears adjacent bottlenecks, or strong AI oversight role |
| 5 | Role is a direct beneficiary of AI-driven market expansion OR is the domain expert who directs/validates AI — demand will grow materially |

### A11 — Observed Technical Exposure (Data Pipeline)
*Derived from O\*NET Auto-Enumerate Index (AEI).* Does not rely on LLM estimation. 
Calculated mathematically by mapping all O\*NET tasks for the role against the LLM AEI baseline.
- **1** = Minimal technical exposure
- **5** = Highly exposed to technical automation

### A12 — Demand Elasticity (LLM Batch Pipeline)
*Calculated via `generate_elasticity_scores.py`.* If AI dramatically lowers the cost/time of this occupation's core output, will market demand scale up to absorb the new efficiency?
- **1** = Inelastic. (e.g. Tax Preparation — making taxes cheaper doesn't make people file more taxes).
- **5** = Highly Elastic. (e.g. Software Engineering — making code cheaper causes companies to demand massively more software).

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

## Calculation Steps (Python Pipeline)

1. **A1-A10 Generation:** The LLM evaluates the occupation and outputs JSON containing 1-5 scores for attributes A1 through A10.
2. **A11 & A12 Loading:** The pipeline loads A11 (O*NET AEI) and A12 (Demand Elasticity).
3. **Filter Calculation:** The 3 core filters (Exposure, Necessity, Elasticity) are calculated via the formulas.
4. **Categorization:** Threshold logic runs to assign the occupation to one of the 4 OpenAI categories.
5. **Final Ranking:** The 0-100 `final_ranking` is computed via the Natural Math Blend to rank occupations within their tiers.

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
