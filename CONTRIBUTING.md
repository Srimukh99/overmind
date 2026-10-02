# Contributing

1. Read `skills/forge/SKILL.md`; it defines the format and how to prove a skill helps.
2. One skill per pull request, with the 3 should-trigger and 2 should-not prompts you tested in the PR description.
3. CI must pass: skill lint, layout check, unit tests and vibe-check.
   Core stays at 14 skills or fewer. A new specialist skill goes in a pack under `packs/NAME/skills/`; a new job inside an existing skill goes in its `references/` folder.
4. Original wording only. If another project inspired an idea, credit it in the README.
5. Regulated-domain skills (`reg-*`) need a source for every rule and must stay labelled "not legal advice".
