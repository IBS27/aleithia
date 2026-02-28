# City Graph — Chicago Business Intelligence Platform

A platform that ingests the digital exhaust of Chicago — news, council meetings, Reddit chatter, permit filings, transit data, review platforms — and fuses it into a continuously updated "city graph." Nodes represent entities (neighborhoods, regulations, businesses, demographics) and edges encode relationships with confidence scores. A reasoning engine traces causal and correlational pathways to produce structured risk-and-opportunity briefs for specific business decisions (e.g., "Should I open a restaurant in Logan Square?").

## Tech Stack

- **Frontend:** React 19 + TypeScript + Vite
- **Backend:** FastAPI (Python 3.12)
- **Compute:** Modal (serverless functions for data ingestion and enrichment)
- **Local dev:** Docker Compose

## Architecture

1. **Ingestion layer** — Modal cron functions scrape/poll heterogeneous sources (Reddit, Chicago Data Portal, RSS feeds, Yelp/Google APIs, Legistar) and normalize into a common event schema. See `data_sources.md` for full source catalog.
2. **Enrichment layer** — LLM-powered entity extraction, sentiment analysis, geo-tagging, and policy direction inference.
3. **City graph** — Entities and weighted relationships updated continuously from enriched events.
4. **Reasoning layer** — Given a business decision, traverses the graph to produce a quantified argument for/against with transparent assumptions and sources.

## Project Structure

```
backend/       — FastAPI app, routes for Modal job submission and polling
frontend/      — React UI
modal/         — Modal function definitions (scrapers, enrichment pipelines)
data_sources.md — Detailed catalog of all data ingestion pipelines
```
