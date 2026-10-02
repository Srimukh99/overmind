#!/usr/bin/env bash
# overmind installer: copies the core skills, plus any packs you choose, into each coding agent's skills folder.
# Usage: ./install.sh [--agent claude|codex|kiro|qwen|cursor|all] [--scope project|user] [--target DIR] [--pack NAME[,NAME]|all]
# Packs: regulated, data, k8s, apis-agents
set -euo pipefail

AGENT="all"; SCOPE="project"; TARGET="$PWD"; PACKS=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --agent) AGENT="$2"; shift 2 ;;
    --scope) SCOPE="$2"; shift 2 ;;
    --target) TARGET="$2"; shift 2 ;;
    --pack) PACKS="${PACKS:+$PACKS,}$2"; shift 2 ;;
    -h|--help) sed -n '2,4p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

ROOT="$(cd "$(dirname "$0")" && pwd)"
SRC="$ROOT/skills"
AVAILABLE="$(ls "$ROOT/packs" | tr '\n' ' ')"
if [[ "$PACKS" == "all" ]]; then PACKS="$(echo $AVAILABLE | tr ' ' ',')"; fi
for p in ${PACKS//,/ }; do
  [[ -d "$ROOT/packs/$p/skills" ]] || { echo "Unknown pack: $p (available: $AVAILABLE)" >&2; exit 1; }
done
base() { [[ "$SCOPE" == "user" ]] && echo "$HOME" || echo "$TARGET"; }

rel_for() {
  case "$1" in
    claude) echo ".claude/skills" ;;
    codex)  echo ".agents/skills" ;;   # Codex reads .agents/skills (repo) and ~/.agents/skills (user)
    kiro)   echo ".kiro/skills" ;;
    qwen)   echo ".qwen/skills" ;;     # Qwen Code
    cursor) echo ".cursor/skills" ;;   # Cursor also reads .claude/skills and .agents/skills
    *) echo "Unsupported agent: $1" >&2; exit 1 ;;
  esac
}

install_one() {
  local rel dest shown n_core n_pack=0
  rel="$(rel_for "$1")"; dest="$(base)/$rel"
  [[ "$SCOPE" == "user" ]] && shown="~/$rel" || shown="$rel"
  mkdir -p "$dest"
  cp -R "$SRC"/. "$dest"/
  n_core=$(ls "$SRC" | wc -l | tr -d ' ')
  for p in ${PACKS//,/ }; do
    cp -R "$ROOT/packs/$p/skills"/. "$dest"/
    n_pack=$((n_pack + $(ls "$ROOT/packs/$p/skills" | wc -l)))
  done
  # The docs show repo paths such as skills/debug/scripts/<script>. Point them at where the scripts now live.
  python3 - "$dest" "$shown" <<'PY'
import os, re, sys
dest, shown = sys.argv[1], sys.argv[2]
packs = re.compile(r'(?<![\w/-])packs/[\w-]+/skills/')
skills = re.compile(r'(?<![\w/.-])skills/')
for d, _, files in os.walk(dest):
    for f in files:
        if f.endswith('.md'):
            p = os.path.join(d, f)
            t = open(p, encoding='utf-8').read()
            n = skills.sub(shown + '/', packs.sub('skills/', t))
            if n != t:
                open(p, 'w', encoding='utf-8').write(n)
PY
  echo "✓ $1: $n_core core + $n_pack pack skills → $dest"
}

if [[ "$AGENT" == "all" ]]; then
  # Cursor reads .claude/skills and .agents/skills too, so it is left out of 'all' to avoid duplicate skills.
  for a in claude codex kiro qwen; do install_one "$a"; done
else
  install_one "$AGENT"
fi

# Codex and other AGENTS.md readers: add a one-line pointer to the boot skill.
if [[ "$SCOPE" == "project" && ( "$AGENT" == "all" || "$AGENT" == "codex" ) ]]; then
  AGENTS_FILE="$TARGET/AGENTS.md"
  if ! grep -q "overmind:boot" "$AGENTS_FILE" 2>/dev/null; then
    printf '\n<!-- overmind:boot -->\nBefore any task, use the `boot` skill to pick the right overmind skill. Run `vibe-check` before every commit.\n' >> "$AGENTS_FILE"
    echo "✓ Added overmind pointer to $AGENTS_FILE"
  fi
fi

echo
[[ -z "$PACKS" ]] && echo "Packs are optional: re-run with --pack regulated,data,k8s,apis-agents (or --pack all)."
echo "Cursor, GitHub Copilot, Gemini CLI and others: run  npx skills add Srimukh99/overmind"
