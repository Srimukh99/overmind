---
name: forge
description: Use when creating a new overmind skill or editing an existing one.
---

# forge

## Format

- Folder name equals `name`: lowercase kebab-case, 20 characters or fewer, pack prefix for domain skills (`pg-`, `mongo-`, `snow-`, `dbx-`, `api-`, `agent-`, `reg-`).
- `description` starts with "Use when", names the words a user would actually type, and stays under about 40 words. It is always in context, so every word costs tokens on every request.
- Body under 200 lines, sections **When**, **Do**, **Done when**. Deep material goes in `references/`, loaded only when needed.
- A skill that covers several related jobs keeps one short `SKILL.md` with a table of situations and moves each job into its own file under `references/`. Keep core skills to 14 or fewer; specialist skills go in a pack under `packs/NAME/skills/`.
- Deterministic checks go in `scripts/`, not prose the model has to re-derive.
- No agent-specific tool names. Say "run the tests" or "search the repo".
- Original wording only. Credit any source that inspired the idea in the README.

## Prove it works

1. Write 3 prompts that should trigger the skill and 2 that should not.
2. Run them with and without the skill installed.
3. Keep the skill only if behaviour clearly improves. Otherwise cut or rewrite it.
4. Run `python3 tools/lint_skills.py` and fix every error.

## Done when

Lint passes, the trigger tests behave as expected, and the skill appears in the `boot` routing table.
