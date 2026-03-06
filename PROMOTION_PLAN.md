# Promotion Plan: ai-proof-careers.com

The core asset is credible, methodology-backed data on AI job resilience — a topic with massive public anxiety and media appetite. The strategy is to let the data do the talking and distribute it everywhere people are asking "is my job safe?"

---

## 1. SEO

**Strategy:** Rank for high-intent, long-tail queries like "is [job title] AI-proof" and "jobs safe from AI" by creating programmatic, data-driven pages for every occupation.

**Implementation:** Build individual occupation pages (e.g., `/occupation/registered-nurse`) with score breakdowns, key drivers, wage data, and growth projections — structured with schema markup and canonical URLs.

**Measurement:** Track keyword rankings and organic clicks in Google Search Console; iterate on page templates and internal linking based on which occupations gain traction first.

**Execution:**
- Build 1,000+ occupation pages from the CSV output — one page per occupation
- Target: `[Job Title] AI resilience`, `will AI replace [job title]`, `[job title] future job market`
- Add FAQ schema markup on each page answering "Is this job safe from AI?"
- Create a sitemap and submit to Google Search Console / Bing Webmaster Tools
- Internal linking: top-ranked jobs link to category pages (healthcare, trades, legal, etc.)
- Measure: weekly GSC impressions/clicks, Ahrefs/Semrush rank tracking for 20–30 target keywords

---

## 2. AEO (Answer Engine Optimization)

**Strategy:** Become the cited source when ChatGPT, Perplexity, and Claude answer "which jobs are AI-proof" by structuring data in a way AI systems can easily parse and attribute.

**Implementation:** Publish a structured, citable dataset (JSON-LD, open CSV download, methodology doc) alongside a concise "facts" page that AI crawlers can easily index and attribute.

**Measurement:** Manually query ChatGPT, Perplexity, Claude, and Gemini weekly with target questions; track how often ai-proof-careers.com is cited and what framing is used.

**Execution:**
- Publish a clean `/methodology` page that reads like an encyclopedia entry — clear attribution hooks (author, date, version, sources like O*NET and BLS)
- Add JSON-LD `Dataset` schema to the site
- Publish a downloadable `ai_resilience_scores.csv` with a CC license — AI systems favor citable open data
- Create a `/facts` or `/key-findings` page with quotable stats: "X% of jobs scored above 3.5", "Top 10 most resilient jobs include..."
- Write a blog post with a definitive title: "The Most Comprehensive Ranking of AI-Proof Jobs (2025)"
- Test weekly: query "which jobs are most resilient to AI?" across 4 AI assistants; log results in a simple tracking doc

---

## 3. Social

**Strategy:** Generate consistent shares by turning the data into emotionally resonant, shareable content — people want to know where their job lands.

**Implementation:** Run a weekly "Job of the Week" series on LinkedIn/X/Threads with the score, key drivers, and a hook — prioritize high-follower-count occupations (nurses, teachers, lawyers, engineers).

**Measurement:** Track reach, saves, and profile link clicks per post; double down on occupation categories and framing styles that outperform.

**Execution:**
- **LinkedIn:** Weekly posts with score card graphic for one occupation. Hook: "Surgeons score 4.8/5.0 on AI resilience. Here's why." Link to occupation page.
- **X/Threads:** Quick-take threads: "Top 10 AI-proof jobs ranked. The #1 might surprise you." Drive clicks to site.
- **TikTok/YouTube Shorts:** Short video format: "Is your job AI-proof? Here's what the data says." Use screen-recorded score breakdowns.
- **Reddit:** Participate in r/cscareerquestions, r/findapath, r/ArtificialIntelligence — answer questions with data, link naturally. Don't spam.
- Build a simple score-card image generator (Canva template or code-generated) to batch-create visuals for each occupation
- Measure: track via native analytics + UTM parameters on all links; monthly review of top-performing content types

---

## 4. PR

**Strategy:** Get picked up by tech, labor, and mainstream press as the primary data source for AI job displacement coverage.

**Implementation:** Pitch a "State of AI Job Resilience" data story to journalists at outlets covering AI/future of work (Wired, The Atlantic, Bloomberg, Fortune, Fast Company).

**Measurement:** Track media mentions via Google Alerts and Ahrefs; count referring domains from press and measure traffic spikes following coverage.

**Execution:**
- Write a 1-page "data story" press release: key findings, methodology credibility (O*NET + BLS sourced, Claude-scored), downloadable data
- Identify 20–30 journalists who have written AI/labor stories in the last 6 months — use tools like Muck Rack or manually search bylines
- Personalize pitches: reference their prior piece, offer exclusive "first look" at the data
- Time outreach around AI news cycles (new model releases, BLS job reports, layoff announcements) when the topic is hot
- Create a `/press` page with high-res assets, key stats, and a press contact
- Hook: "The first methodology-backed, occupation-level dataset scoring AI resilience across 1,000+ jobs"
- Measure: Google Alerts for domain mentions, Ahrefs referring domains weekly

---

## 5. Partnerships

**Strategy:** Embed the data into platforms where job seekers, career counselors, and HR professionals already live.

**Implementation:** Partner with job boards (Indeed, LinkedIn, Glassdoor via their editorial teams), career platforms (LinkedIn Learning, Coursera), and university career centers to license or link the data.

**Measurement:** Track referral traffic from partner links and co-branded content; measure whether partnership pages drive repeat visits or email signups.

**Execution:**
- **Job boards:** Pitch Indeed/Glassdoor editorial teams on a co-branded "AI resilience score" tag or article series — they have audience + you have unique data
- **Career counselors/coaches:** Offer a free "Career Counselor Toolkit" download that includes the dataset + how to use it with clients; build a list of counselors as a distribution channel
- **University career centers:** Email career center directors at 20–50 universities with a free data license for student advising; they love credible, third-party data
- **HR/recruiting influencers:** Identify 10–20 LinkedIn creators with large HR/recruiting audiences; offer early access + co-create content
- **AI newsletters:** Get featured in The Rundown, TLDR AI, Ben's Bites, Superhuman — they reach exactly the right audience
- Measure: UTM-tagged links per partner, monthly referral traffic report

---

## 6. Email / Content Marketing

**Strategy:** Build a direct audience of people anxious about AI and their careers — the topic has repeat engagement potential as AI evolves.

**Implementation:** Launch a weekly or bi-weekly newsletter with new occupation deep-dives, score updates as methodology evolves, and curated AI/labor news with the lens of the scoring framework.

**Measurement:** Track open rate, click rate, and subscriber growth; iterate on subject lines and content formats based on engagement data.

**Execution:**
- Add an email capture to the site — offer "Get your occupation's full breakdown" or "Download the full dataset" as a lead magnet
- Use Beehiiv, ConvertKit, or Substack — Substack has built-in discovery if you're consistent
- Content calendar: 50% occupation spotlights, 25% methodology/behind-the-scenes, 25% AI/labor news
- Repurpose newsletter content as blog posts for SEO
- Measure: Beehiiv/Substack native analytics; 30% open rate is a good benchmark to target

---

## 7. Data Community

**Strategy:** Get the dataset cited in academic papers, policy discussions, and data journalism pieces by making it the most accessible, rigorous open dataset in this space.

**Implementation:** Publish the full dataset on Kaggle, Hugging Face Datasets, and GitHub with detailed methodology — communities there actively share and cite quality datasets.

**Measurement:** Track dataset downloads, Kaggle/HF upvotes, and GitHub stars; watch for derivative work (blog posts, papers) citing the dataset.

**Execution:**
- Upload `ai_resilience_scores.csv` to Kaggle with a competition-style description and methodology overview
- Post to Hugging Face Datasets — it's increasingly cited in AI research
- Pin the GitHub repo and write a polished README (already done — just needs a "cite this" section)
- Post in r/datasets, r/datascience, Hacker News (Show HN)
- Measure: Kaggle download count, HF dataset views, GitHub stars, inbound links from academic/data sites via Ahrefs

---

## Priority Order

| Priority | Channel | Why |
|---|---|---|
| 1 | **SEO (occupation pages)** | Highest long-term leverage, owned traffic |
| 2 | **AEO** | AI assistants are the new Google for this query type |
| 3 | **PR** | One good pickup → massive referral traffic spike |
| 4 | **Social (LinkedIn)** | Highest ROI social channel for career/professional data |
| 5 | **Email** | Builds owned audience for longevity |
| 6 | **Partnerships** | Slower but compounds over time |
| 7 | **Data community** | Credibility signal; drives academic/press citations |
