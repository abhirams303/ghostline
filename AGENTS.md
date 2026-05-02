<!-- context7 -->
Use Context7 MCP to fetch current documentation whenever the user asks about a library, framework, SDK, API, CLI tool, or cloud service -- even well-known ones like React, Next.js, Prisma, Express, Tailwind, Django, or Spring Boot. This includes API syntax, configuration, version migration, library-specific debugging, setup instructions, and CLI tool usage. Use even when you think you know the answer -- your training data may not reflect recent changes. Prefer this over web search for library docs.

Do not use for: refactoring, writing scripts from scratch, debugging business logic, code review, or general programming concepts.

## Steps

1. Always start with `resolve-library-id` using the library name and the user's question, unless the user provides an exact library ID in `/org/project` format
2. Pick the best match (ID format: `/org/project`) by: exact name match, description relevance, code snippet count, source reputation (High/Medium preferred), and benchmark score (higher is better). If results don't look right, try alternate names or queries (for example, `next.js` instead of `nextjs`, or rephrase the question). Use version-specific IDs when the user mentions a version
3. `query-docs` with the selected library ID and the user's full question, not a single keyword
4. Answer using the fetched docs
<!-- context7 -->

## Claude Skills

This workspace uses Claude-style skills stored in `C:\Users\lipey\.claude\skills`.

- Codex-visible mirrors live in `C:\Users\lipey\.codex\skills`
- Use `scripts/sync-claude-skills.ps1` to create missing junctions from the Claude skill directory into the Codex skill directory
- When the user references a Claude slash command like `/tdd` or `/review`, resolve it to the skill directory with the same name under `C:\Users\lipey\.claude\skills`
- If a requested Claude skill exists under `C:\Users\lipey\.claude\skills` but not under `C:\Users\lipey\.codex\skills`, run the sync script before continuing

Canonical source of truth: `C:\Users\lipey\.claude\skills`

## Project Context

Before making non-trivial changes, read `docs/PROJECT_CONTEXT.md`.

- Treat that file as the quickest project brief for architecture, current status, guardrails, and next priorities
- If you change contracts, collector posture, docs, or team workflows, keep `docs/PROJECT_CONTEXT.md` in sync
- If the README and `docs/PROJECT_CONTEXT.md` disagree, prefer the project-context file for implementation details and update the README
