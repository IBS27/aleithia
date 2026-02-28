# Learnings

## Architecture Decisions

| Decision | Rationale | Date |
|----------|-----------|------|
| FastAPI + React | Fast to build, good DX, strong ecosystem | 2026-02-27 |
| Monolith over microservices | 36-hour hackathon — simplicity wins | 2026-02-28 |
| Modal as ENTIRE compute backbone | Pipelines + inference on one platform = genuinely ambitious for judges | 2026-02-28 |
| Llama 3.1 8B over 70B | Fits A10G, fast inference, $250 credits last longer | 2026-02-28 |
| OpenAI for chat generation | Best quality, separates concerns from Modal inference. $5K credits/member | 2026-02-28 |
| Live data over pre-curated | More ambitious demo, real-time relevance, stronger Modal submission | 2026-02-28 |
| Chicago focus | Local to HackIllinois, tangible demo, rich public APIs (Socrata, Legistar) | 2026-02-28 |
| Supermemory for context | Sponsor track — all 5 APIs: Profiles, Memory, Retrieval, Connectors, Multi-modal | 2026-02-27 |
| Cloudflare Pages for frontend | Sponsor track ($5K credits/member) + trivial deploy | 2026-02-28 |
| Solana deferred as stretch goal | Blockchain verification of data provenance — pursue if time permits | 2026-02-28 |
| Chat + Dashboard hybrid UX | Best of both worlds for UI/UX judges — interactive + visual | 2026-02-28 |
| Tailwind CSS | Rapid UI development, consistent design system | 2026-02-27 |
| Name: Alethia | Greek "unconcealment" — truth revealed, not constructed | 2026-02-27 |

## Judging Strategy

### What Wins Each Track

| Track | What Judges Want | How Alethia Delivers |
|-------|-----------------|---------------------|
| Best Voyager Hack ($5K) | Creativity, technical complexity, impact, execution | Live data pipelines + dual-model inference + social mission |
| Modal AI Inference | Ambitious inference on Modal solving real-world problem | ENTIRE compute backbone: 7 cron pipelines + Llama 3.1 8B + embeddings — not just API wrapping |
| Best UI/UX (Camera) | Intuitive, polished, delightful. Visual hierarchy, accessibility, seamless interaction | Chat + Dashboard hybrid with Chicago map, risk cards, streaming |
| Best Social Impact (Speakers) | Tangible positive change addressing pressing societal issue | Directly addresses regulatory inequity for small businesses |
| Supermemory (RayBans) | App that remembers, understands, adapts. Use multiple APIs | All 5 APIs: Profiles + Memory + Retrieval + Connectors + Multi-modal |
| OpenAI ($5K credits) | Use OpenAI API | Chat generation from RAG context |
| Cloudflare ($5K credits) | Use Cloudflare developer platform | Frontend on Cloudflare Pages |
| Solana (stretch) | Use Solana blockchain | Verification of regulatory data provenance — stretch goal |
| .Tech Domain (mic) | Register .tech domain | alethia.tech |

### Key Insight
The social impact narrative is our strongest differentiator. Every demo moment should reinforce: "Big companies have teams of lawyers and analysts. We give that same power to a coffee shop owner." The technical sophistication (Modal, Supermemory) serves this story.

### Demo Script: "Weeks to Seconds"

**Setup:** Visible timer on screen. Named persona throughout.

1. **Meet Maria.** She's opening a Mexican restaurant in **Pilsen, Chicago**. She has $80K savings, a family recipe book, and zero idea how to navigate Chicago's regulatory maze.

2. **The Problem (10 seconds).** "Right now, Maria has two choices: spend $5,000-$15,000 on lawyers and consultants who take 2-3 weeks... or guess and hope she doesn't get shut down."

3. **Start the timer.** Maria types: "Mexican restaurant, Pilsen." *Timer starts visibly counting.*

4. **Data floods in (show the pipeline).** "In the background, Alethia is pulling from 9 live data sources — City Council records, building permits, health inspections, Reddit discussions, Yelp trends, Census demographics, commercial real estate listings — all in parallel on Modal."

5. **Timer stops: 4.2 seconds.** "What cost $5K-$15K in billable hours just happened in 4.2 seconds. Free."

6. **Risk score card.** Maria's Pilsen restaurant scores 6.2/10 risk. *Click to expand.* Factor breakdown appears:
   - "3 new zoning regulations" — 40% weight, HIGH severity (from politics pipeline)
   - "Rising competition: 12 new restaurant permits in 90 days" — 25% weight (from Socrata)
   - "Positive neighborhood sentiment" — 15% weight, trending up (from Reddit)
   - "Foot traffic: HIGH based on CTA data" — 10% weight (from public data)
   - "Average review rating: 4.1/5 for area restaurants" — 10% weight (from Yelp)

7. **Heatmap toggle.** Switch between three layers on the Chicago map:
   - Regulatory density (where permits are hardest to get)
   - Business activity (where new businesses are opening)
   - Sentiment (what people are saying online)

8. **Vision pipeline demo.** "We didn't just use off-the-shelf models — we built a custom neighborhood detector. Paste a YouTube walking tour of Pilsen, and in 10 minutes our pipeline downloads the video, extracts frames, uses parallel AI agents to label every storefront and pedestrian, trains a custom YOLO model, and gives Maria a visual health score of her neighborhood."

9. **Chat.** Maria asks: "What permits do I need?" → Streaming response with specific permit names, links, estimated costs, and timeline — all sourced from live data.

10. **The closer.** "We're not replacing lawyers — we're giving every small business owner the intelligence that only big companies could afford. Maria's $80K goes into her restaurant, not into figuring out if she's allowed to open one."

## Domain Knowledge

### Regulatory Landscape
- Federal, state, and local regulations create a multi-layered compliance burden
- Key areas: employment law, environmental protection, consumer safety, taxation
- Regulations vary significantly by jurisdiction — location-aware analysis is critical
- Political landscape shifts can change regulatory requirements rapidly

### Target User
- Small business owners and startup founders
- Non-technical — UI must be approachable and jargon-free
- Time-poor — need actionable insights, not raw data
- Cannot afford legal teams or compliance analysts

## Bugs & Fixes

_None yet — document bugs and their solutions here as they arise._

## Patterns

_Document useful patterns discovered during development._

## Anti-Patterns

_Document things that didn't work so we don't repeat them._
