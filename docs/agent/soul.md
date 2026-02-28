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
