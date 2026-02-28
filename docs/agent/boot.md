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
