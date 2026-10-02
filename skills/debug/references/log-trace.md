# log-trace

Let the script read the log, not you. It returns a 15–25 line summary, so a 5,000-line log costs almost nothing.

## Do

1. Feed the log to the script without echoing it back into the conversation:
   - From a command: `kubectl logs <pod> --previous | python3 <this skill folder>/scripts/log_trace.py --repo .`
   - Other sources: `aws logs tail <group> --since 30m | ...`, `docker logs <id> 2>&1 | ...`
   - From a file: `python3 <this skill folder>/scripts/log_trace.py error.log --repo .`
   - Only if the user pasted it: write it to `/tmp/rubric.log` once, then run on that file.
2. Read the summary:
   - **error / category**: what failed (timeout, out-of-memory, auth, config/missing, ...).
   - **runtime**: Lambda, ECS, Kubernetes (EKS/AKS/GKE), EC2, Cloud Run, with evidence from the log and from the repo's IaC.
   - **app**: function, service or workload name, and the IaC file that defines it.
   - **start**: the in-repo file and line to open first. Library frames are skipped.
   - **next**: runtime-specific next steps.
3. Open only the `start` file and the `app` IaC file. Then continue with `references/hunt.md`.
4. If runtime is `unknown`, say so and ask where it runs; don't guess.

Use `--json` when another tool will consume the result.
