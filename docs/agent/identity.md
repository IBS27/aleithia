# Identity

## Project

- **Name:** Alethia (working title: "Not Palantir")
- **Meaning:** Greek for "unconcealment" — the philosophical concept of truth as something revealed, not constructed
- **Tagline:** Democratizing regulatory intelligence for small businesses
- **Type:** AI-powered regulatory and business intelligence platform
- **Event:** HackIllinois 2026
- **Repo:** https://github.com/IBS27/aleithia

## Tracks & Judging Criteria

### Best Voyager Hack (General Track)
Awarded for exceptional innovation, functionality, and overall excellence. Judges look for: **creativity, technical complexity, impact, and execution.** Must demonstrate pushing boundaries of what's possible in 36 hours.

### Best AI Inference — Modal (Sponsor Track)
Modal is AI infrastructure for developers (used by Ramp, Suno, Lovable). Offers flexible GPU compute, code sandboxes, and storage. Judges want: **ambitious applications running inference on Modal to solve a real-world problem.**
- Credits code: `VVN-YQS-E55` — redeem $250 at modal.com/credits
- Prize claimed in Siebel Center immediately after closing ceremony

### Best UI/UX Design (Challenge Track)
Awarded to the most **intuitive, polished, and delightful** user experience. Judges evaluate: **thoughtful design decisions, strong visual hierarchy, accessibility, and seamless interaction — from first impression to final click.** The product must feel effortless to use and look great doing it.

### Best Social Impact (Challenge Track)
Recognizes the project with the most significant potential for **positive change or addressing a pressing societal issue.** Can address environmental concerns, accessibility, social injustices, and more. Must aim to make a **tangible difference** in the world.

### Best Use of Supermemory (Sponsor Track)
Use Supermemory's Context Engineering APIs to build an app that **remembers, understands, and adapts** to its users. Leverage: Retrieval, Memory, User Profiles, Connectors, or Multi-modal Extractors — or combine them all.
- Free tier available; top up at Supermemory booth if credits run out

### Best Use of OpenAI API (Sponsor Track)
Use OpenAI API in your project. $5K API credits per member.

### Best Use of Cloudflare Developer Platform (Sponsor Track)
Use Cloudflare's developer platform (Pages, Workers, etc.). $5K credits per member.

### Best Use of Solana (Sponsor Track) — STRETCH GOAL
Stretch goal — blockchain-based verification of regulatory data provenance. Lower priority than core tracks but worth pursuing if time permits. Transparent, immutable audit trail for compliance recommendations.

## Problem Statement

The modern business environment is defined by a labyrinthine web of regulatory constraints — federal, state, and local — spanning employment law, environmental protection, consumer safety, taxation, and more. Beyond compliance, businesses must adapt to shifting political landscapes, dynamic consumer sentiment, and unique regional logistical challenges.

**The core inequity:** This complexity disproportionately impacts small businesses and startups. Large firms employ teams of general counsels, lobbyists, and data analysts to navigate these data streams, making informed decisions that minimize risk and capitalize on regulatory nuances. Small businesses cannot afford this.

## Mission

Democratize high-level, data-driven regulatory and business intelligence. Give small business owners and startup builders the same caliber of operational intelligence that large corporations achieve through expensive in-house teams.

## What Alethia Does

1. **Aggregates** live Chicago-area data — local news, city council activity, Reddit/Yelp sentiment, public records (CTA, crime, permits) — via Modal cron pipelines
2. **Analyzes** this data using Llama 3.1 8B + embeddings on Modal GPUs to identify critical risks and opportunities
3. **Translates** complex findings into actionable, context-specific recommendations via OpenAI chat generation
4. **Remembers** each user's business context via Supermemory — the app gets smarter over time
5. **Reveals** hidden risks and opportunities that small business owners would otherwise miss

## Constraints

- **Hackathon timeline:** 36 hours — speed matters more than perfection
- **Team size:** Small team, every line of code should count
- **Scope:** MVP first, polish later
- **Demo-ready:** Must be presentable and compelling at judging
- **Multi-track:** Design for UI/UX and social impact judging criteria

## Boundaries

**This project IS:**
- A regulatory and business intelligence platform for small businesses
- An AI-powered tool that aggregates and analyzes multi-jurisdictional data
- A social impact project that levels the playing field
- A hackathon prototype with polished UI/UX for demo

**This project IS NOT:**
- Legal advice (always disclaim)
- A replacement for a lawyer or CPA
- A production-grade enterprise compliance system
- A general-purpose data analysis tool
