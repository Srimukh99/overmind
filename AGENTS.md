# AGENTS.md

This repo is **rubric**, a library of agent skills. When working on it:

- Use the `forge` skill for any new or edited skill.
- Run `python3 tools/lint_skills.py`, `python3 tools/check_layout.py` and `python3 -m unittest discover -s tests` before committing. `make check` runs all three, and the Stop hook in `.claude/settings.json` runs it when a turn tries to end.
- Run the gate: `python3 skills/ship/scripts/vibe_check.py`.
- Keep descriptions short; they are loaded into every session.

<!-- rubric:boot -->
Before any task, use the `boot` skill to pick the right rubric skill. Run `vibe-check` before every commit.

## Assistant vs. Project Boundaries
- Never commit or add third-party LLM client scripts, API integrations, or provider credentials to the project repository when the user provides model or provider references for assistant execution.
- Keep assistant configuration, keys, and model instructions strictly within session/agent context unless the user explicitly requests building a feature inside the codebase.

