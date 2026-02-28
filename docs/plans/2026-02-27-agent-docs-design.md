# Agent Configuration Documents Design

> **SUPERSEDED** — This design was written for the original "Not Palantir" concept before the project pivoted to "Alethia" (Chicago Business Intelligence Platform). The `docs/agent/` directory was never created. Agent configuration is now handled by `CLAUDE.md` in the project root (single-file approach). This document is preserved for historical reference.

**Date:** 2026-02-27
**Project:** Not Palantir (HackIllinois 2026) → Pivoted to Alethia
**Purpose:** Claude Code project-specific configuration documents (superseded by CLAUDE.md)

## Context

"Not Palantir" is a data analysis platform built at HackIllinois 2026. Tech stack: Python (FastAPI) backend + React frontend, with pandas/polars for data processing.

These 8 markdown documents configure Claude Code's behavior when working on this project. They live in `docs/agent/` as a flat directory structure.

## Document Specifications

### boot.md — Startup Instructions
Entry point Claude Code reads first.
- Load order for other docs
- Environment setup expectations (Python venv, Node for React)
- Pre-flight checks before starting work
- References to all other agent docs

### identity.md — Project Identity
- Project name, mission, team context
- HackIllinois 2026 hackathon constraints
- Project boundaries (what it IS and ISN'T)

### soul.md — Coding Philosophy & Values
- Hackathon mindset: ship fast, iterate, pragmatic over perfect
- Code style: PEP 8 + type hints (Python), functional components + hooks (React)
- Decision principles: simple over clever, MVP first
- Error handling and communication tone

### heartbeat.md — Project Status
Living document tracking:
- Overall project health/phase
- What's working, what's broken
- Current blockers
- Last updated timestamp

### tools.md — Tech Stack & Tooling
- Backend: Python 3.x, FastAPI, pandas/polars
- Frontend: React (Vite or Next.js)
- Dev tools: pytest, ESLint, Prettier
- Key CLI commands
- Database and deployment info

### user.md — User Profile & Preferences
- Team members and roles
- Workflow and communication preferences
- Skill levels for calibrated assistance

### active-tasks.md — Task Tracking
- Prioritized task list with status
- Dependencies between tasks
- Next up queue

### learnings.md — Accumulated Insights
- Bugs encountered and fixes
- Architectural decisions and rationale
- Patterns and anti-patterns discovered

## Structure

```
docs/agent/
├── boot.md
├── identity.md
├── soul.md
├── heartbeat.md
├── tools.md
├── user.md
├── active-tasks.md
└── learnings.md
```

## Decision Rationale

- **Flat directory** over nested: simplicity wins for a hackathon
- **Separate files** over monolith: easier to update individual sections
- **boot.md as entry point**: establishes load order and context

---

## Diff: Plan vs Reality

```diff
- Project: "Not Palantir" — generic data analysis platform
+ Project: "Alethia" — Chicago Business Intelligence Platform on Modal

- 8 separate markdown files in docs/agent/
+ Single CLAUDE.md file in project root (simpler, Claude Code native)

- Tech stack: FastAPI + React + pandas/polars
+ Tech stack: Modal (28+ serverless functions) + React 19 + vLLM + GPU inference

- Configuration: boot.md load order, heartbeat.md status, active-tasks.md tracking
+ Configuration: CLAUDE.md covers architecture, commands, patterns, deployment in one file
+ Additional: auto-memory in ~/.claude/projects/*/memory/MEMORY.md

- docs/agent/ directory with 8 files
+ docs/agent/ never created — CLAUDE.md approach proved sufficient
```
