# receipts

Every claim needs proof you produced just now.

| Claim | Proof |
| --- | --- |
| Tests pass | Test command output from this session showing 0 failures |
| Bug fixed | The original repro now behaves correctly |
| Regression test added | The test fails with the fix backed out and passes with it restored. A test never seen failing proves nothing about the bug |
| It builds | Build command output |
| Deployed | Health check or smoke test against the target |
| Faster / cheaper | Before and after numbers from the same measurement |
| Lint / types clean | Linter and type-checker output |
| A worker, subagent or teammate finished it | Their diff in version control, read by you, plus the checks re-run on the merged result |
| Everything asked for is done | The original request re-read, one line per requirement, each line carrying its own receipt |

## Words that mean the proof is missing

These are predictions. A receipt is an observation. If one of them is about to
go into a message, the command has not been run yet:

`should work` · `should be fine` · `looks right` · `looks correct` · `I think it works` ·
`I think it's fixed` · `probably` · `must be working` · `seems to work` ·
`basically done` · `mostly working` · `in theory` · `by inspection` ·
`obviously correct` · `simple enough that` · `I'm confident`

Replace the prediction with the command and its output, or write "unverified"
and why. Hedging is not a third option: a hedge still ships the claim.

The list is a sample, not a loophole. A reworded prediction ("ought to be good
now", "fingers crossed") is still a prediction, and celebrating is a claim too:
"Done!", "Perfect!" and "all green" report success as surely as "tests pass".
What makes a sentence honest is not its wording but what stands behind it: a
check from this turn, run after the last edit, that passed.

## Excuse and reality

| About to be said | What is actually true |
| --- | --- |
| "It's a one-line change" | One-line changes break builds. The edit took a minute; the check takes seconds |
| "The tests were passing before" | They passed on different code. Every earlier run expires the moment a file changes |
| "It's too hard to test here" | Then the claim is "unverified", not "done". Say which part is unproven |
| "The types check, so it works" | Types rule out a class of bugs, not this bug |
| "Only comments and docs changed" | Run the gate anyway. It costs seconds and catches the stray edit that rode along |
| "A subagent reported it done" | That is a report, not a result. Check the VCS diff: `git diff`, `git log -p`, `git status` for what was left untracked |
| "I did everything that was asked" | That is what is remembered being asked. Re-read the request and tick each requirement against the diff |
| "CI will catch it" | CI catches it after the claim was made, in front of everyone else |
| "It worked when I ran it earlier" | Earlier was before the last three edits. Run it again |
| "The quick check passed" | It proves the part it checked. Run the rest, or name what was not run |
| "The regression test passes" | So would a test that checks nothing. Back the fix out once and watch it fail |
| "This is the last step, I'll wrap up" | The end of a task is where shortcuts ship. The last claim needs the same receipt as the first |

## Requirements checklist

Before any "done", re-read the original request and write one line per
requirement, each with its own receipt:

```text
- [x] <requirement> — <command> → <key output line>
- [ ] <requirement> — not done: <what is left>
```

A requirement with no receipt is not done. A requirement that was never written
down was never checked: the list comes from the request, not from memory of it.

## Rules

- Run it now. Earlier runs don't count after code changed.
- Read the output; don't assume from the exit code alone.
- Partially done means saying "partially done" and listing what's left.
- If you can't run it, say "unverified" and why.
- Proof produced by someone else, agent or human, counts only once it has been read and the checks re-run here.

## Format

`Verified: <claim> — <command> → <key output line>`

The gate enforces the part a script can enforce. `references/vibe-check.md`
installs it as a Stop hook, which sends a turn back when its closing message:

- uses one of the words above outside quotes or code;
- reports success, in any words, with no check run this turn, only checks run
  before the last edit, or a last check that failed;
- or leaves the repo failing the gate.

Quote a phrase to talk about it. A claim the hook cannot see, such as a
subagent's report or a requirement nobody wrote down, is still yours to back.
