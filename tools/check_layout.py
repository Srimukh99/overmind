#!/usr/bin/env python3
"""Layout integrity: nothing orphaned, nothing dangling.

  1. every script lives in exactly one skill and is mentioned by that skill (or its references)
  2. every script path mentioned in docs, CI or the installer exists
  3. no document points at a retired skill name (merged into another skill in v0.6)
  4. old names that still exist as gates (vibe-check, log-trace, log-fetch) have a reference file
  5. boot lists every core skill and every pack skill
"""
import pathlib
import re
import sys

BASE = pathlib.Path(__file__).resolve().parent.parent
RETIRED = {"shape", "blueprint", "prove-it", "sandbox", "hunt", "trace-back", "second-look",
           "weigh-in", "threat-check", "receipts", "land", "preflight", "slo"}
GATES = {"vibe-check": ("ship", "vibe-check"), "log-trace": ("debug", "log-trace"),
         "log-fetch": ("debug", "log-fetch")}
TEXT = (".md", ".yml", ".yaml", ".sh", ".json")
SKIP_DIRS = {".git", "__pycache__", ".rubric"}
UPGRADE = re.compile(r"<!-- upgrade:start -->.*?<!-- upgrade:end -->", re.S)


def skill_dirs(root):
    return sorted(list((root / "skills").glob("*/SKILL.md")) + list((root / "packs").glob("*/skills/*/SKILL.md")))


def text_files(root):
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.suffix in TEXT and not (set(p.relative_to(root).parts) & SKIP_DIRS):
            yield p


def run(root=BASE):
    root = pathlib.Path(root)
    errors = []
    # 1. scripts: unique and reachable
    seen = {}
    for md in skill_dirs(root):
        d = md.parent
        docs = md.read_text(encoding="utf-8") + "".join(
            p.read_text(encoding="utf-8") for p in (d / "references").glob("*.md")) if (d / "references").is_dir() \
            else md.read_text(encoding="utf-8")
        for s in sorted((d / "scripts").glob("*.py")) if (d / "scripts").is_dir() else []:
            if s.name in seen:
                errors.append(f"script {s.name} exists in both {seen[s.name]} and {d.name}")
            seen[s.name] = d.name
            if s.name not in docs:
                errors.append(f"{d.name}: script {s.name} is never mentioned, so an agent cannot find it")
    # 2. documented paths exist
    path_rx = re.compile(r"((?:skills|packs)/[\w./-]+?\.(?:py|sh))")
    for p in text_files(root):
        if p.name == "CHANGELOG.md":
            continue
        for m in set(path_rx.findall(UPGRADE.sub("", p.read_text(encoding="utf-8")))):
            if "NAME" in m or "*" in m:
                continue
            if not (root / m).exists():
                errors.append(f"{p.relative_to(root)}: mentions {m}, which does not exist")
    # 3. retired names
    name_rx = re.compile(r"`(%s)`" % "|".join(map(re.escape, sorted(RETIRED))))
    for p in text_files(root):
        if p.suffix != ".md" or p.name == "CHANGELOG.md":
            continue
        t = UPGRADE.sub("", p.read_text(encoding="utf-8"))
        for m in sorted(set(name_rx.findall(t))):
            errors.append(f"{p.relative_to(root)}: refers to retired skill `{m}`")
    # 4. gates resolve
    for gate, (skill, part) in GATES.items():
        if not (root / "skills" / skill / "references" / f"{part}.md").exists():
            errors.append(f"gate `{gate}` has no skills/{skill}/references/{part}.md")
    # 5. boot lists everything
    boot = (root / "skills" / "boot" / "SKILL.md").read_text(encoding="utf-8")
    for md in skill_dirs(root):
        n = md.parent.name
        if n != "boot" and f"`{n}`" not in boot:
            errors.append(f"boot does not list `{n}`")
    return errors, len(seen)


def main():
    errors, scripts = run()
    for e in errors:
        print("ERROR", e)
    print(f"layout: {scripts} scripts, {len(errors)} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
