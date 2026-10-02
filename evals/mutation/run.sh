#!/bin/sh
# Two suites that both pass; mutation testing shows which one actually checks anything. Needs pytest + hypothesis.
set -e
here=$(cd "$(dirname "$0")" && pwd); overmind=$(cd "$here/../.." && pwd)
for suite in weak strong; do
  d=$(mktemp -d); mkdir -p "$d/tests"
  printf '[tool.pytest.ini_options]\npythonpath = ["."]\n' > "$d/pyproject.toml"
  (cd "$d" && git init -q && git add pyproject.toml && git -c user.email=e@e -c user.name=e commit -qm base)
  cp "$here/pricing.py" "$d/" && cp "$here/$suite/test_pricing.py" "$d/tests/"
  echo "== $suite =="; python3 "$overmind/skills/build/scripts/loop.py" mutate --repo "$d" --min 80 || true
  rm -rf "$d"
done
