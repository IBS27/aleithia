# Agent Configuration Documents Implementation Plan

> **SUPERSEDED** — This implementation plan was never executed. The project pivoted from "Not Palantir" to "Alethia" and adopted a single `CLAUDE.md` file instead of the 8-file `docs/agent/` approach described here. Preserved for historical reference.

> ~~**For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.~~

**Goal:** ~~Create 8 Claude Code configuration markdown documents that shape agent behavior for the "Not Palantir" data analysis platform.~~ (Superseded by CLAUDE.md)

**Architecture:** Flat `docs/agent/` directory with self-contained markdown files. `boot.md` is the entry point that references all others. Documents split into static context (identity, soul, tools, user) and dynamic state (heartbeat, active-tasks, learnings).

**Tech Stack:** Markdown files, no dependencies.

---

### Task 1: Create directory and boot.md

**Files:**
- Create: `docs/agent/boot.md`

**Step 1: Create the directory**

```bash
mkdir -p docs/agent
```

**Step 2: Write boot.md**

Create `docs/agent/boot.md` with this exact content:

```markdown
# Boot Sequence

## Load Order

Read these documents in order before starting any work:

1. `identity.md` — Who this project is
2. `soul.md` — How to think and decide
3. `tools.md` — What's available
4. `user.md` — Who you're working with
5. `heartbeat.md` — Current project state
6. `active-tasks.md` — What needs doing
7. `learnings.md` — What we've learned so far

## Environment Setup

Before writing any code, verify:

- [ ] Python virtual environment is active (`source venv/bin/activate`)
- [ ] Node modules installed (`npm install` in frontend/)
- [ ] FastAPI dev server can start (`uvicorn main:app --reload`)
- [ ] React dev server can start (`npm run dev` in frontend/)

## Pre-Flight Checks

- Run `git status` to understand current branch and working state
- Check `active-tasks.md` for current priorities
- Check `heartbeat.md` for known blockers
- Check `learnings.md` before solving a problem — it may already be solved

## Rules

- Always read the relevant source files before modifying them
- Commit after each completed task
- Update `heartbeat.md` when project status changes
- Update `learnings.md` when you discover something reusable
- Update `active-tasks.md` when tasks change status
```

**Step 3: Commit**

```bash
git add docs/agent/boot.md
git commit -m "docs: add agent boot sequence configuration"
```

---

### Task 2: Create identity.md

**Files:**
- Create: `docs/agent/identity.md`

**Step 1: Write identity.md**

Create `docs/agent/identity.md` with this exact content:

```markdown
# Identity

## Project

- **Name:** Not Palantir
- **Tagline:** We can't tell you what it is, but we know it's not Palantir.
- **Type:** Data analysis platform
- **Event:** HackIllinois 2026
- **Repo:** https://github.com/gt12889/hackillinois2026

## Mission

Build a data analysis platform that makes it easy to ingest, explore, and visualize datasets. Think Palantir-style capabilities — data fusion, interactive dashboards, pattern discovery — but built in a weekend.

## Constraints

- **Hackathon timeline:** Speed matters more than perfection
- **Team size:** Small team, every line of code should count
- **Scope:** MVP first, polish later
- **Demo-ready:** Must be presentable at judging

## Boundaries

**This project IS:**
- A data analysis and visualization platform
- A tool for exploring and querying datasets
- A hackathon prototype meant to impress judges

**This project IS NOT:**
- A production-grade enterprise system
- A Palantir clone (obviously)
- A general-purpose database tool
```

**Step 2: Commit**

```bash
git add docs/agent/identity.md
git commit -m "docs: add agent identity configuration"
```

---

### Task 3: Create soul.md

**Files:**
- Create: `docs/agent/soul.md`

**Step 1: Write soul.md**

Create `docs/agent/soul.md` with this exact content:

```markdown
# Soul

## Mindset

This is a hackathon. Ship fast, iterate, be pragmatic. Perfect is the enemy of done.

## Decision Principles

1. **Simple over clever** — Write code a tired hackathon teammate can read at 3am
2. **MVP first** — Get it working, then make it good
3. **Delete over abstract** — If something isn't needed, remove it instead of abstracting it
4. **Commit often** — Small, working increments over big-bang changes
5. **Demo-driven** — Every feature should be visually demonstrable

## Code Style

### Python (Backend)
- Follow PEP 8
- Use type hints on function signatures
- Use f-strings for string formatting
- Prefer `pathlib.Path` over `os.path`
- Use pydantic models for API request/response schemas
- Keep functions short — if it scrolls, split it

### React (Frontend)
- Functional components only, no class components
- Use hooks for state and effects
- Props should be destructured in function parameters
- Use TypeScript if time permits, JavaScript if under pressure
- CSS modules or Tailwind — no inline styles

### General
- No dead code — delete it, don't comment it out
- No TODO comments without a matching entry in `active-tasks.md`
- Variable names should be descriptive — `dataset` not `d`, `user_query` not `q`

## Error Handling

- Backend: Let FastAPI handle HTTP errors with proper status codes. Use `HTTPException` for expected errors.
- Frontend: Show user-friendly error messages. Never show raw stack traces.
- Fail fast on startup (missing env vars, bad config). Fail gracefully at runtime.

## Communication

- Be direct and concise
- Lead with the answer, then explain
- When unsure between two approaches, present both with a recommendation
- Don't ask permission for obvious fixes — just do them
```

**Step 2: Commit**

```bash
git add docs/agent/soul.md
git commit -m "docs: add agent soul configuration"
```

---

### Task 4: Create tools.md

**Files:**
- Create: `docs/agent/tools.md`

**Step 1: Write tools.md**

Create `docs/agent/tools.md` with this exact content:

```markdown
# Tools

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Backend | Python 3.11+ | Server-side logic |
| API Framework | FastAPI | REST API endpoints |
| Data Processing | pandas, polars | Dataset manipulation |
| Frontend | React | User interface |
| Build Tool | Vite | Frontend bundling |
| Styling | Tailwind CSS | UI styling |

## Project Structure

```
hackillinois2026/
├── backend/
│   ├── main.py              # FastAPI app entry point
│   ├── requirements.txt     # Python dependencies
│   ├── routers/             # API route modules
│   ├── models/              # Pydantic models
│   ├── services/            # Business logic
│   └── tests/               # pytest tests
├── frontend/
│   ├── src/
│   │   ├── App.jsx          # Root component
│   │   ├── components/      # Reusable UI components
│   │   ├── pages/           # Page-level components
│   │   └── api/             # API client functions
│   ├── package.json
│   └── vite.config.js
├── docs/
│   └── agent/               # These config documents
└── README.md
```

## Commands

### Backend
```bash
# Setup
python -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt

# Run
uvicorn backend.main:app --reload --port 8000

# Test
pytest backend/tests/ -v

# Lint
ruff check backend/
```

### Frontend
```bash
# Setup
cd frontend && npm install

# Run
npm run dev

# Build
npm run build

# Lint
npm run lint
```

## Key Libraries

- **FastAPI:** Auto-generates OpenAPI docs at `/docs`
- **pandas:** Use for CSV/Excel ingestion and transforms
- **polars:** Use for large dataset performance-critical operations
- **pydantic:** All API models inherit from `BaseModel`
- **httpx:** Use for async HTTP requests if needed

## Database

TBD — Start with file-based storage (CSV/JSON uploads). Add SQLite or PostgreSQL if time permits.

## Deployment

TBD — Likely Vercel (frontend) + Railway/Render (backend) for demo.
```

**Step 2: Commit**

```bash
git add docs/agent/tools.md
git commit -m "docs: add agent tools configuration"
```

---

### Task 5: Create user.md

**Files:**
- Create: `docs/agent/user.md`

**Step 1: Write user.md**

Create `docs/agent/user.md` with this exact content:

```markdown
# User

## Team

- **Lead Developer:** Zhuoli Xie (gt12889)
- **Event:** HackIllinois 2026

## Workflow Preferences

- Prefers seeing the plan before implementation
- Values concise communication — lead with the answer
- Likes multiple-choice options when decisions are needed
- Wants commits after each logical unit of work

## Development Style

- Comfortable with Python and React
- Prefers FastAPI for backend work
- Uses Claude Code as primary development assistant
- Works in WSL2 (Linux on Windows)

## Communication

- Be direct, skip unnecessary caveats
- When presenting options, recommend one and explain why
- Don't over-explain standard patterns — focus on project-specific details
```

**Step 2: Commit**

```bash
git add docs/agent/user.md
git commit -m "docs: add agent user configuration"
```

---

### Task 6: Create heartbeat.md

**Files:**
- Create: `docs/agent/heartbeat.md`

**Step 1: Write heartbeat.md**

Create `docs/agent/heartbeat.md` with this exact content:

```markdown
# Heartbeat

**Last Updated:** 2026-02-27

## Project Phase

`[ ] Planning → [x] Setup → [ ] Core Features → [ ] Polish → [ ] Demo`

## Status

| Component | Status | Notes |
|-----------|--------|-------|
| Repository | Active | GitHub repo initialized |
| Backend | Not started | FastAPI project needs scaffolding |
| Frontend | Not started | React project needs scaffolding |
| Data Pipeline | Not started | — |
| Deployment | Not started | — |

## What's Working

- Git repository set up and connected to GitHub
- Agent configuration documents in place

## What's Broken

- Nothing yet — project just started

## Blockers

- None currently

## Recent Changes

- 2026-02-27: Project initialized, agent docs created
```

**Step 2: Commit**

```bash
git add docs/agent/heartbeat.md
git commit -m "docs: add agent heartbeat status tracker"
```

---

### Task 7: Create active-tasks.md

**Files:**
- Create: `docs/agent/active-tasks.md`

**Step 1: Write active-tasks.md**

Create `docs/agent/active-tasks.md` with this exact content:

```markdown
# Active Tasks

## Current Priority

| # | Task | Status | Owner |
|---|------|--------|-------|
| 1 | Scaffold FastAPI backend | TODO | — |
| 2 | Scaffold React frontend | TODO | — |
| 3 | Build data upload endpoint | TODO | — |
| 4 | Build dataset explorer UI | TODO | — |
| 5 | Add data visualization | TODO | — |

## Up Next

- Connect frontend to backend API
- Add interactive query/filter capabilities
- Polish UI for demo

## Completed

- [x] Initialize repository
- [x] Create agent configuration documents
```

**Step 2: Commit**

```bash
git add docs/agent/active-tasks.md
git commit -m "docs: add agent active-tasks tracker"
```

---

### Task 8: Create learnings.md

**Files:**
- Create: `docs/agent/learnings.md`

**Step 1: Write learnings.md**

Create `docs/agent/learnings.md` with this exact content:

```markdown
# Learnings

## Architecture Decisions

| Decision | Rationale | Date |
|----------|-----------|------|
| FastAPI + React | Fast to build, good DX, strong ecosystem | 2026-02-27 |
| pandas + polars | pandas for compatibility, polars for performance | 2026-02-27 |
| Flat agent docs | Simplicity over hierarchy for hackathon pace | 2026-02-27 |

## Bugs & Fixes

_None yet — document bugs and their solutions here as they arise._

## Patterns

_Document useful patterns discovered during development._

## Anti-Patterns

_Document things that didn't work so we don't repeat them._
```

**Step 2: Commit**

```bash
git add docs/agent/learnings.md
git commit -m "docs: add agent learnings tracker"
```

---

### Task 9: Final verification

**Step 1: Verify all files exist**

```bash
ls -la docs/agent/
```

Expected: 8 files (boot.md, identity.md, soul.md, heartbeat.md, tools.md, user.md, active-tasks.md, learnings.md)

**Step 2: Verify git log**

```bash
git log --oneline -10
```

Expected: 8 new commits, one per document.

---

## Diff: Plan vs Reality

This plan was never executed. The project pivoted before implementation.

```diff
- 9 tasks to create docs/agent/ directory with 8 markdown files
+ 0 tasks executed — entire plan superseded

- Project identity: "Not Palantir" data analysis platform
+ Project identity: "Alethia" Chicago Business Intelligence Platform

- Agent config approach: 8 separate files (boot, identity, soul, heartbeat, tools, user, active-tasks, learnings)
+ Agent config approach: single CLAUDE.md file in project root
+ Additional context: auto-memory files in ~/.claude/projects/*/memory/

- Tech stack documented: FastAPI + React + pandas/polars + SQLite
+ Tech stack actual: Modal serverless + Qwen3 8B + vLLM + YOLOv8n + React 19 + Tailwind v4
```
