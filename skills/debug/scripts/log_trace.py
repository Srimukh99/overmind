#!/usr/bin/env python3
"""log-trace: turn a raw log into a compact triage summary without an LLM reading it.

Finds the error, its category, stack frames that live in this repo, where the app runs
(Lambda, ECS, EKS/Kubernetes, EC2, ...) from both the log and the repo's IaC, and next steps.

  kubectl logs pod/x | python3 log_trace.py          # stdin
  python3 log_trace.py error.log --repo . --json
"""
import argparse
import json
import os
import re
import sys

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".terraform",
             "target", ".next", ".idea", ".worktrees", "vendor", ".tox", ".mypy_cache"}

FRAME_RULES = [
    ("python", re.compile(r'File "(?P<file>[^"]+)", line (?P<line>\d+), in (?P<func>\S+)'), "last"),
    ("java", re.compile(r'\bat (?P<func>[\w$.<>]+)\((?P<file>[\w$]+\.(?:java|kt|scala)):(?P<line>\d+)\)'), "first"),
    ("dotnet", re.compile(r'\bat (?P<func>[\w.<>`]+)\(.*?\) in (?P<file>\S+\.cs):line (?P<line>\d+)'), "first"),
    ("node", re.compile(r'\bat (?:(?P<func>[^\s(]+) \()?(?:file://)?(?P<file>[^\s():]+\.(?:js|mjs|cjs|ts|tsx|jsx)):(?P<line>\d+):\d+\)?'), "first"),
    ("go", re.compile(r'^\s*(?P<file>\S+\.go):(?P<line>\d+)'), "first"),
    ("ruby", re.compile(r'(?P<file>[^\s:]+\.rb):(?P<line>\d+):in'), "first"),
]

ERROR_RULES = [
    re.compile(r'\b(?P<err>[A-Za-z_][\w.$]*(?:Exception|Error|Fault))\b(?::\s*(?P<msg>.{0,160}))?'),
    re.compile(r'\b(?P<err>panic): (?P<msg>.{0,160})'),
    re.compile(r'\b(?P<err>FATAL|CRITICAL|ERROR)\b[:\s\]-]*(?P<msg>.{0,160})'),
]

CATEGORIES = [
    ("out-of-memory", r"OOMKilled|OutOfMemoryError|MemoryError|Cannot allocate memory|heap out of memory|signal: killed|exit code 137"),
    ("timeout", r"Task timed out after|timed? ?out\b|deadline exceeded|ETIMEDOUT|504 Gateway"),
    ("crash-loop", r"CrashLoopBackOff|Back-off restarting failed container"),
    ("image-pull", r"ImagePullBackOff|ErrImagePull|manifest unknown|pull access denied"),
    ("scheduling", r"FailedScheduling|Insufficient (?:cpu|memory)|didn't match.*(?:selector|affinity)|Unschedulable"),
    ("throttling", r"ThrottlingException|Rate exceeded|TooManyRequests|\b429\b|SlowDown"),
    ("auth/permission", r"AccessDenied|403 Forbidden|\b401\b|Unauthorized|not authorized to perform|InvalidClientTokenId|ExpiredToken|[Pp]ermission denied"),
    ("dns", r"ENOTFOUND|Name or service not known|no such host|NXDOMAIN|Temporary failure in name resolution"),
    ("connection", r"ECONNREFUSED|Connection refused|ECONNRESET|[Cc]onnection reset|no route to host|EHOSTUNREACH"),
    ("tls", r"certificate (?:has expired|verify failed)|x509:|SSL routines|CERT_HAS_EXPIRED"),
    ("disk", r"No space left on device|ENOSPC|DiskPressure"),
    ("database", r"deadlock detected|too many connections|could not connect to server|Lock wait timeout|SQLSTATE"),
    ("null/undefined", r"NullPointerException|'NoneType' object|Cannot read propert(?:y|ies) of (?:undefined|null)|nil pointer dereference"),
    ("config/missing", r"KeyError|environment variable|ConfigurationError|No such file or directory|ModuleNotFoundError|Cannot find module|ClassNotFoundException"),
]

LOG_RUNTIME = {
    "lambda": r"\b(?:START|END|REPORT) RequestId:|Task timed out after|/aws/lambda/|Init Duration:|Runtime\.\w+|arn:aws:lambda:",
    "ecs": r"arn:aws:ecs:|ecs-agent|/ecs/|ECS_CONTAINER_METADATA|Fargate",
    "kubernetes": r"arn:aws:eks:|kubelet|CrashLoopBackOff|OOMKilled|ImagePullBackOff|FailedScheduling|\bpod/|kube-system|k8s\.io|\bnamespace[=:]",
    "ec2": r"\bi-[0-9a-f]{8,17}\b|cloud-init",
    "cloud-run": r"run\.googleapis\.com|K_SERVICE",
    "azure-functions": r"Microsoft\.Azure\.WebJobs|FUNCTIONS_WORKER_RUNTIME",
}

REPO_RUNTIME = [
    ("lambda", r'"aws_lambda_function"|AWS::Lambda::Function|AWS::Serverless::Function|lambda\.(?:Function|DockerImageFunction)\('),
    ("ecs", r'"aws_ecs_(?:service|task_definition)"|AWS::ECS::(?:Service|TaskDefinition)|ecs\.(?:FargateService|Ec2Service|FargateTaskDefinition)|ecs_patterns\.'),
    ("eks", r'"aws_eks_cluster"|AWS::EKS::Cluster|eks\.Cluster\('),
    ("kubernetes", r'^kind:\s*(?:Deployment|StatefulSet|DaemonSet|CronJob|Rollout)\b'),
    ("ec2", r'"aws_(?:instance|autoscaling_group|launch_template)"|AWS::EC2::Instance|AWS::AutoScaling::AutoScalingGroup'),
    ("aks", r'"azurerm_kubernetes_cluster"'),
    ("azure-functions", r'"azurerm_(?:linux_|windows_)?function_app"'),
    ("gke", r'"google_container_cluster"'),
    ("cloud-run", r'"google_cloud_run_(?:v2_)?service"'),
]
REPO_FILES = {"serverless.yml": "lambda", "serverless.yaml": "lambda", "template.yaml": None, "Chart.yaml": "kubernetes",
              "kustomization.yaml": "kubernetes", "docker-compose.yml": "docker-compose", "compose.yaml": "docker-compose",
              "fly.toml": "fly.io", "vercel.json": "vercel", "Procfile": "heroku-style", "app.yaml": None}
SCAN_EXT = (".tf", ".yaml", ".yml", ".json", ".ts", ".js", ".py", ".toml")

APP_HINTS = [
    ("lambda function", re.compile(r"/aws/lambda/(?P<name>[\w.-]+)|function:(?P<name2>[\w.-]+)")),
    ("ecs service", re.compile(r"/ecs/(?P<name>[\w.-]+)|service[/:](?P<name2>[\w-]+)")),
    ("kubernetes workload", re.compile(r"\b(?P<name>[a-z0-9]([a-z0-9-]*[a-z0-9])?)-[a-f0-9]{8,10}-[a-z0-9]{5}\b")),
]
ID_RULES = [
    ("request_id", re.compile(r"RequestId:\s*(?P<v>[0-9a-f-]{36})")),
    ("trace_id", re.compile(r"(?:trace[_-]?id|X-Amzn-Trace-Id)[=:\s\"]+(?P<v>[\w=;-]{8,})", re.I)),
    ("http_status", re.compile(r"\b(?:status|HTTP/\d\.\d\"?)\s*[=:]?\s*(?P<v>[45]\d\d)\b")),
]

NEXT = {
    ("lambda", "timeout"): ["Compare the function's timeout in IaC with the REPORT Duration", "Check downstream calls for missing client timeouts or retries", "Look for cold-start Init Duration spikes"],
    ("lambda", "out-of-memory"): ["Raise memory_size in IaC or cut memory use; check REPORT Max Memory Used"],
    ("lambda", "auth/permission"): ["Check the function's IAM role policy for the denied action and resource"],
    ("ecs", "out-of-memory"): ["Check task/container memory in the task definition; look for exit code 137 in stopped tasks"],
    ("ecs", "*"): ["aws ecs describe-services and describe-tasks for stoppedReason", "Check the service's CloudWatch log group"],
    ("kubernetes", "out-of-memory"): ["kubectl describe pod <pod> for Last State OOMKilled", "Raise resources.limits.memory in the manifest or fix the leak"],
    ("kubernetes", "crash-loop"): ["kubectl logs <pod> --previous", "kubectl describe pod <pod> for exit code and events"],
    ("kubernetes", "image-pull"): ["Check image name and tag exist in the registry and node/IRSA pull permissions"],
    ("kubernetes", "scheduling"): ["kubectl describe pod <pod> events; compare requests with node capacity, selectors and taints"],
    ("kubernetes", "*"): ["kubectl get events -n <ns> --sort-by=.lastTimestamp", "kubectl rollout history deploy/<name> to spot a recent change"],
    ("*", "config/missing"): ["Compare required env vars and files with the deployed config (IaC, Helm values, task definition)"],
    ("*", "connection"): ["Check the target is up, security groups / network policies allow it, and the port is right"],
    ("*", "dns"): ["Check the hostname, VPC DNS settings and service discovery records"],
    ("*", "throttling"): ["Add backoff with jitter; check service quotas and concurrency limits"],
    ("*", "tls"): ["Check certificate expiry and the CA bundle in the image"],
    ("*", "database"): ["Check connection pool size vs max_connections and long-running locks"],
    ("*", "null/undefined"): ["Open the start-here frame; add a failing test for the missing value (red-green)"],
    ("*", "*"): ["Open the start-here frame; reproduce locally with the same input (hunt)"],
}


def read_text(path, limit=1_000_000):
    try:
        if os.path.getsize(path) > limit:
            return ""
        with open(path, encoding="utf-8", errors="ignore") as fh:
            return fh.read()
    except OSError:
        return ""


def walk_repo(repo):
    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            yield os.path.join(root, f)


def build_file_index(repo):
    index = {}
    for p in walk_repo(repo):
        rel = os.path.relpath(p, repo).replace(os.sep, "/")
        index.setdefault(os.path.basename(p), []).append(rel)
    return index


def resolve(frame_file, lang, func, index):
    """Map a frame's file to a path in this repo, or None if it's library code."""
    name = os.path.basename(frame_file.replace("\\", "/"))
    if lang == "java" and func and "." in func:
        cls = func.rsplit(".", 1)[0].split("$")[0]
        want = cls.replace(".", "/") + os.path.splitext(name)[1]
    else:
        want = frame_file.replace("\\", "/").lstrip("./")
    if any(s in want for s in ("site-packages", "node_modules", "/usr/lib", "dist-packages", "<frozen")):
        return None
    candidates = index.get(name, [])
    parts = want.split("/")
    best, best_len = None, 0
    for c in candidates:
        cparts = c.split("/")
        n = 0
        while n < min(len(parts), len(cparts)) and parts[-1 - n] == cparts[-1 - n]:
            n += 1
        if n > best_len:
            best, best_len = c, n
    if best and (best_len >= 2 or len(candidates) == 1):
        return best
    return None


def detect_repo_runtime(repo):
    found = {}
    for p in walk_repo(repo):
        base = os.path.basename(p)
        rel = os.path.relpath(p, repo).replace(os.sep, "/")
        if base in REPO_FILES and REPO_FILES[base]:
            found.setdefault(REPO_FILES[base], f"{rel}")
        if not base.endswith(SCAN_EXT) and base not in REPO_FILES:
            continue
        text = read_text(p)
        if not text:
            continue
        for runtime, rx in REPO_RUNTIME:
            m = re.search(rx, text, re.M)
            if m and runtime not in found:
                line = text.count("\n", 0, m.start()) + 1
                found[runtime] = f"{rel}:{line}"
    return found


def find_in_iac(repo, name):
    if not name or len(name) < 3:
        return None
    rx = re.compile(re.escape(name))
    for p in walk_repo(repo):
        if p.endswith((".tf", ".yaml", ".yml", ".json", ".ts", ".py")) and "test" not in p.lower():
            text = read_text(p)
            m = rx.search(text)
            if m:
                return f"{os.path.relpath(p, repo)}:{text.count(chr(10), 0, m.start()) + 1}"
    return None


def analyze(log, repo):
    lines = log.splitlines()
    index = build_file_index(repo)

    error = None
    for i, line in enumerate(lines, 1):
        for rx in ERROR_RULES:
            m = rx.search(line)
            if m:
                cand = {"type": m.group("err"), "message": (m.group("msg") or "").strip(), "log_line": i}
                if error is None or (error["type"] in ("ERROR", "FATAL", "CRITICAL") and cand["type"] not in ("ERROR", "FATAL", "CRITICAL")):
                    error = cand
                break

    categories = [name for name, rx in CATEGORIES if re.search(rx, log)]

    frames, lang_seen = [], None
    for line in lines:
        for lang, rx, _ in FRAME_RULES:
            m = rx.search(line)
            if m:
                gd = m.groupdict()
                repo_path = resolve(gd["file"], lang, gd.get("func"), index)
                frames.append({"lang": lang, "file": gd["file"], "line": int(gd["line"]), "func": gd.get("func"), "repo_path": repo_path})
                lang_seen = lang_seen or lang
                break
    in_repo = [f for f in frames if f["repo_path"]]
    start_here = None
    if in_repo:
        order = next(o for l, _, o in FRAME_RULES if l == in_repo[0]["lang"])
        start_here = in_repo[-1] if order == "last" else in_repo[0]

    log_scores = {rt: len(re.findall(rx, log)) for rt, rx in LOG_RUNTIME.items()}
    log_scores = {k: v for k, v in log_scores.items() if v}
    repo_rt = detect_repo_runtime(repo)

    def norm(rt):
        return "kubernetes" if rt in ("eks", "aks", "gke", "kubernetes") else rt
    scores = {}
    for rt, n in log_scores.items():
        scores[rt] = scores.get(rt, 0) + 2 * n
    for rt in repo_rt:
        scores[norm(rt)] = scores.get(norm(rt), 0) + 1
    runtime = max(scores, key=scores.get) if scores else "unknown"

    app = None
    for label, rx in APP_HINTS:
        m = rx.search(log)
        if m:
            name = m.group("name") or (m.groupdict().get("name2"))
            if name:
                app = {"kind": label, "name": name, "iac": find_in_iac(repo, name)}
                break

    ids = {}
    for key, rx in ID_RULES:
        m = rx.search(log)
        if m:
            ids[key] = m.group("v")

    steps = []
    for cat in (categories or ["*"]):
        for key in ((runtime, cat), (runtime, "*"), ("*", cat)):
            for s in NEXT.get(key, []):
                if s not in steps:
                    steps.append(s)
    if not steps:
        steps = NEXT[("*", "*")]
    if start_here and NEXT[("*", "*")][0] not in steps:
        steps.insert(0, NEXT[("*", "*")][0])

    return {
        "error": error, "categories": categories, "runtime": runtime,
        "runtime_evidence": {"log": log_scores, "repo": repo_rt},
        "app": app, "start_here": start_here,
        "frames_in_repo": in_repo[:12], "frames_outside_repo": len(frames) - len(in_repo),
        "ids": ids, "log_lines": len(lines), "next_steps": steps[:6],
    }


def render(r):
    out = ["log-trace"]
    e = r["error"]
    out.append(f"error:    {e['type']}: {e['message']}  (log line {e['log_line']})" if e else "error:    none matched")
    out.append(f"category: {', '.join(r['categories']) or 'unclassified'}")
    ev = r["runtime_evidence"]
    out.append(f"runtime:  {r['runtime']}  [log: {ev['log'] or '-'}; repo: {ev['repo'] or '-'}]")
    if r["app"]:
        a = r["app"]
        out.append(f"app:      {a['kind']} '{a['name']}'" + (f" → {a['iac']}" if a["iac"] else " (not found in repo IaC)"))
    if r["start_here"]:
        s = r["start_here"]
        out.append(f"start:    {s['repo_path']}:{s['line']}" + (f" in {s['func']}" if s["func"] else ""))
    if r["frames_in_repo"]:
        out.append("frames in this repo:")
        out += [f"  {f['repo_path']}:{f['line']}" + (f" {f['func']}" if f["func"] else "") for f in r["frames_in_repo"]]
    out.append(f"frames outside repo: {r['frames_outside_repo']} (skipped)")
    if r["ids"]:
        out.append("ids:      " + ", ".join(f"{k}={v}" for k, v in r["ids"].items()))
    out.append("next:")
    out += [f"  {i}. {s}" for i, s in enumerate(r["next_steps"], 1)]
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Compact triage summary for a log")
    ap.add_argument("logfile", nargs="?", help="log file (default: stdin)")
    ap.add_argument("--repo", default=".", help="repo root to map frames and IaC (default: .)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    log = read_text(a.logfile, limit=50_000_000) if a.logfile else sys.stdin.read()
    r = analyze(log, a.repo)
    print(json.dumps(r, indent=2) if a.json else render(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
