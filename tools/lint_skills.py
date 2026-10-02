#!/usr/bin/env python3
"""Lint overmind skills against the open Agent Skills format and overmind's own rules.

Core skills live in skills/, optional packs in packs/NAME/skills/. A skill may keep
long material in references/*.md, linked from a table in its SKILL.md.
"""
import pathlib
import re
import sys

BASE = pathlib.Path(__file__).resolve().parent.parent
NAME_RX = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
CORE_MAX = 14


def frontmatter(text):
    if not text.startswith("---\n"):
        return None, text
    end = text.find("\n---", 4)
    if end == -1:
        return None, text
    meta = {}
    for line in text[4:end].splitlines():
        if ":" in line and not line.startswith(" "):
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
    return meta, text[end + 4:]


def check(skill_md, where, errors):
    folder = skill_md.parent.name
    meta, body = frontmatter(skill_md.read_text(encoding="utf-8"))
    if meta is None:
        errors.append(f"{where}: missing YAML frontmatter")
        return 0
    name, desc = meta.get("name", ""), meta.get("description", "")
    if name != folder:
        errors.append(f"{where}: name '{name}' must match folder")
    if not NAME_RX.match(name) or len(name) > 20:
        errors.append(f"{where}: name must be lowercase kebab-case, 20 chars max")
    if not desc.startswith("Use when"):
        errors.append(f"{where}: description must start with 'Use when'")
    if len(desc) > 400:
        errors.append(f"{where}: description is {len(desc)} chars (max 400)")
    if ": " in desc:
        errors.append(f"{where}: description contains ': ' which breaks YAML; rephrase or quote")
    if body.count("\n") > 200:
        errors.append(f"{where}: body is {body.count(chr(10))} lines (max 200; move detail to references/)")
    refdir = skill_md.parent / "references"
    linked = set(re.findall(r"references/([\w.-]+\.md)", body))
    present = {p.name for p in refdir.glob("*.md")} if refdir.is_dir() else set()
    for missing in sorted(linked - present):
        errors.append(f"{where}: links references/{missing} which does not exist")
    for orphan in sorted(present - linked):
        errors.append(f"{where}: references/{orphan} is not linked from SKILL.md")
    for p in sorted(refdir.glob("*.md")) if refdir.is_dir() else []:
        n = p.read_text(encoding="utf-8").count("\n")
        if n > 200:
            errors.append(f"{where}/references/{p.name}: {n} lines (max 200)")
    return len(desc)


def main():
    errors, core_chars, pack_chars = [], 0, 0
    core = sorted((BASE / "skills").glob("*/SKILL.md"))
    packs = sorted((BASE / "packs").glob("*/skills/*/SKILL.md"))
    for p in core:
        core_chars += check(p, f"skills/{p.parent.name}", errors)
    for p in packs:
        pack = p.parent.parent.parent.name
        pack_chars += check(p, f"packs/{pack}/skills/{p.parent.name}", errors)
    for d in sorted((BASE / "packs").glob("*")):
        if d.is_dir() and not (d / ".claude-plugin" / "plugin.json").exists():
            errors.append(f"packs/{d.name}: missing .claude-plugin/plugin.json")
    for e in errors:
        print(f"ERROR {e}")
    if len(core) > CORE_MAX:
        print(f"WARN  {len(core)} core skills; keep core to {CORE_MAX} or fewer and put specialist skills in a pack")
    print(f"lint: {len(core)} core + {len(packs)} pack skills, {len(errors)} errors, "
          f"~{core_chars // 4} tokens always loaded (core), ~{(core_chars + pack_chars) // 4} with every pack")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
