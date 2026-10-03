# The checks AGENTS.md requires before a commit.
#
# vibe_check.py --full prefers `make check` when this target exists, so the
# commit hook and the Stop hook run exactly these three commands. Never add the
# gate itself here: --full would then recurse into itself.
.PHONY: check
check:
	python3 tools/lint_skills.py
	python3 tools/check_layout.py
	python3 -m unittest discover -s tests
