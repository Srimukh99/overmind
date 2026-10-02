# shape

Goal: agree on what to build before building it.

## Do

1. Read the relevant code, docs and recent commits. Note constraints you discover.
2. Ask only what the repo can't tell you, one question per message, multiple choice when possible.
3. Offer 2–3 approaches. For each: complexity, risk, cost, how hard it is to undo. Recommend one and say why.
4. Present the design in short sections and get a yes on each: data model, interfaces, flow, failure modes, testing, rollout.
5. Flag early anything touching regulated data, money movement, auth or external systems. These change the design (see `reg-*`, `review`).
6. Save the result to `docs/designs/YYYY-MM-DD-<topic>.md`.

## Keep it lean

- Cut anything the stated goal doesn't need.
- Prefer tech already in the repo over new dependencies.
- Make the first version small enough to ship and measure.

## Done when

The design file exists and the user approved it. Next: `references/blueprint.md`.
