#!/usr/bin/env python3
"""drift: compare desired state (git: Terraform, manifests, GitOps) with current live state,
summarize the gap, and keep a state log so you can see when drift started.

Read-only: runs only plan/diff/get commands. Skips tools that aren't installed.

  python3 drift_check.py                   # auto-detect everything
  python3 drift_check.py --k8s-dir deploy/ --namespace prod
  python3 drift_check.py --history         # past results from .overmind/state.jsonl
"""
import argparse
import datetime
import glob
import json
import os
import re
import shutil
import subprocess
import sys

STATE_FILE = os.path.join(".overmind", "state.jsonl")


def run(cmd, cwd=None, timeout=600):
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except (OSError, subprocess.TimeoutExpired) as e:
        return 99, "", str(e)


# ---------- Terraform ----------
TF_ACTION = re.compile(r"#\s+(\S+)\s+(will be created|will be updated in-place|will be destroyed|must be replaced|will be read during apply|has changed|has been deleted)")


def parse_tf_plan(text):
    actions = {}
    for m in TF_ACTION.finditer(text):
        verb = {"will be created": "create", "will be updated in-place": "update", "will be destroyed": "destroy",
                "must be replaced": "replace", "has changed": "changed-outside-terraform",
                "has been deleted": "deleted-outside-terraform", "will be read during apply": "read"}[m.group(2)]
        if verb != "read":
            actions.setdefault(verb, []).append(m.group(1))
    summary = re.search(r"Plan: (\d+) to add, (\d+) to change, (\d+) to destroy", text)
    return {"actions": actions, "plan_line": summary.group(0) if summary else ("No changes" if "No changes." in text else None),
            "outside_changes": "changed outside of Terraform" in text}


def tf_roots(base):
    roots = set()
    for f in glob.glob(os.path.join(base, "**", "*.tf"), recursive=True):
        if "/.terraform/" in f or "/modules/" in f:
            continue
        with open(f, encoding="utf-8", errors="ignore") as fh:
            text = fh.read()
        if re.search(r'^\s*(?:backend\s+"|provider\s+")', text, re.M) or re.search(r"^\s*terraform\s*\{", text, re.M):
            roots.add(os.path.dirname(f) or ".")
    return sorted(roots)


def check_terraform(base):
    if not shutil.which("terraform"):
        return [{"source": "terraform", "status": "skipped", "note": "terraform not installed"}] if tf_roots(base) else []
    out = []
    for root in tf_roots(base):
        if not os.path.isdir(os.path.join(root, ".terraform")):
            out.append({"source": f"terraform:{root}", "status": "skipped", "note": "run terraform init first"})
            continue
        rc, so, se = run(["terraform", "plan", "-detailed-exitcode", "-lock=false", "-input=false", "-no-color"], cwd=root)
        if rc == 0:
            out.append({"source": f"terraform:{root}", "status": "in-sync"})
        elif rc == 2:
            out.append({"source": f"terraform:{root}", "status": "drift", **parse_tf_plan(so)})
        else:
            out.append({"source": f"terraform:{root}", "status": "error", "note": ((se or so).strip().splitlines() or ["unknown error"])[-1]})
    return out


# ---------- Kubernetes ----------
DIFF_HEADER = re.compile(r"^diff -u -N \S*/(?:LIVE|MERGED)-\d+/(\S+)", re.M)


def parse_kubectl_diff(text):
    seen = []
    for m in DIFF_HEADER.finditer(text):
        name = m.group(1)
        if name not in seen:
            seen.append(name)
    return seen


def summarize_workloads(data):
    """Desired vs current for Deployments, StatefulSets, DaemonSets."""
    problems = []
    for it in data.get("items", []):
        kind, md, spec, st = it.get("kind"), it.get("metadata", {}), it.get("spec", {}), it.get("status", {})
        name = f"{kind}/{md.get('namespace', 'default')}/{md.get('name')}"
        if kind == "DaemonSet":
            desired = st.get("desiredNumberScheduled", 0)
            ready, updated = st.get("numberReady", 0), st.get("updatedNumberScheduled", 0)
        else:
            desired = spec.get("replicas", 1)
            ready, updated = st.get("readyReplicas", 0), st.get("updatedReplicas", 0)
        issues = []
        if md.get("generation", 0) > st.get("observedGeneration", 0):
            issues.append("controller has not observed the latest spec")
        if updated < desired:
            issues.append(f"{updated}/{desired} updated")
        if ready < desired:
            issues.append(f"{ready}/{desired} ready")
        for c in st.get("conditions", []):
            if c.get("type") == "Progressing" and c.get("reason") == "ProgressDeadlineExceeded":
                issues.append("rollout stuck (ProgressDeadlineExceeded)")
            if c.get("type") == "Available" and c.get("status") == "False":
                issues.append("not available")
        if issues:
            problems.append({"resource": name, "issues": issues})
    return problems


BAD_WAIT = {"CrashLoopBackOff", "ImagePullBackOff", "ErrImagePull", "CreateContainerConfigError", "RunContainerError"}


def summarize_pods(data):
    bad = []
    for it in data.get("items", []):
        md, st = it.get("metadata", {}), it.get("status", {})
        name = f"pod/{md.get('namespace', 'default')}/{md.get('name')}"
        reasons = []
        if st.get("phase") == "Pending":
            for c in st.get("conditions", []):
                if c.get("reason") == "Unschedulable":
                    reasons.append("Unschedulable")
        for cs in st.get("containerStatuses", []) or []:
            w = (cs.get("state") or {}).get("waiting") or {}
            if w.get("reason") in BAD_WAIT:
                reasons.append(w["reason"])
            last = (cs.get("lastState") or {}).get("terminated") or {}
            if last.get("reason") == "OOMKilled":
                reasons.append("OOMKilled (last restart)")
            if cs.get("restartCount", 0) >= 5:
                reasons.append(f"{cs['restartCount']} restarts")
        if reasons:
            bad.append({"resource": name, "issues": sorted(set(reasons))})
    return bad


def summarize_gitops(argo, flux):
    out = []
    for it in (argo or {}).get("items", []):
        st = it.get("status", {})
        sync, health = (st.get("sync") or {}).get("status"), (st.get("health") or {}).get("status")
        if sync != "Synced" or health != "Healthy":
            out.append({"resource": f"argocd/{it['metadata']['name']}", "issues": [f"sync={sync}", f"health={health}"]})
    for it in (flux or {}).get("items", []):
        ready = next((c for c in it.get("status", {}).get("conditions", []) if c.get("type") == "Ready"), {})
        if ready.get("status") != "True":
            out.append({"resource": f"flux/{it['metadata']['name']}", "issues": [ready.get("reason", "not ready")]})
    return out


def kget(args, ns):
    scope = ["-n", ns] if ns else ["-A"]
    rc, so, _ = run(["kubectl", "get", *args, *scope, "-o", "json"], timeout=60)
    return json.loads(so) if rc == 0 and so.strip() else None


def check_kubernetes(k8s_dir, ns):
    if not shutil.which("kubectl"):
        return [{"source": "kubernetes", "status": "skipped", "note": "kubectl not installed"}]
    rc, _, se = run(["kubectl", "version", "--request-timeout=5s", "-o", "json"], timeout=15)
    if rc != 0:
        return [{"source": "kubernetes", "status": "skipped", "note": "no cluster reachable (check kube context)"}]
    out = []
    if k8s_dir:
        rc, so, se = run(["kubectl", "diff", "-R", "-f", k8s_dir], timeout=300)
        if rc == 0:
            out.append({"source": f"manifests:{k8s_dir}", "status": "in-sync"})
        elif rc == 1:
            out.append({"source": f"manifests:{k8s_dir}", "status": "drift", "resources": parse_kubectl_diff(so)})
        else:
            out.append({"source": f"manifests:{k8s_dir}", "status": "error", "note": se.strip()[-300:]})
    w = kget(["deploy,statefulset,daemonset"], ns)
    if w is not None:
        probs = summarize_workloads(w)
        out.append({"source": "rollouts", "status": "drift" if probs else "in-sync", "problems": probs})
    p = kget(["pods"], ns)
    if p is not None:
        bad = summarize_pods(p)
        out.append({"source": "pods", "status": "drift" if bad else "in-sync", "problems": bad})
    argo = kget(["applications.argoproj.io"], ns)
    flux = kget(["kustomizations.kustomize.toolkit.fluxcd.io"], ns)
    if argo is not None or flux is not None:
        g = summarize_gitops(argo, flux)
        out.append({"source": "gitops", "status": "drift" if g else "in-sync", "problems": g})
    if shutil.which("helm"):
        rc, so, _ = run(["helm", "list", "-A", "-o", "json"], timeout=60)
        if rc == 0 and so.strip():
            bad = [r for r in json.loads(so) if r.get("status") != "deployed"]
            out.append({"source": "helm", "status": "drift" if bad else "in-sync",
                        "problems": [{"resource": f"helm/{r['namespace']}/{r['name']}", "issues": [r.get("status")]} for r in bad]})
    return out


def git_sha():
    rc, so, _ = run(["git", "rev-parse", "--short", "HEAD"], timeout=10)
    return so.strip() if rc == 0 else None


def record(results):
    os.makedirs(".overmind", exist_ok=True)
    entry = {"at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), "desired_ref": git_sha(),
             "drift": [r["source"] for r in results if r["status"] == "drift"],
             "skipped": [r["source"] for r in results if r["status"] == "skipped"]}
    with open(STATE_FILE, "a") as fh:
        fh.write(json.dumps(entry) + "\n")
    return entry


def history(n):
    if not os.path.isfile(STATE_FILE):
        print("no history yet")
        return
    with open(STATE_FILE) as fh:
        rows = [json.loads(l) for l in fh if l.strip()][-n:]
    first = {}
    for r in rows:
        for s in r["drift"]:
            first.setdefault(s, r["at"])
    for r in rows:
        print(f"{r['at']}  ref={r['desired_ref']}  drift={', '.join(r['drift']) or 'none'}")
    still = rows[-1]["drift"] if rows else []
    for s in still:
        print(f"open drift: {s} (first seen {first.get(s)})")


def render(results):
    lines = ["drift"]
    for r in results:
        lines.append(f"{r['status'].upper():<8} {r['source']}" + (f"  ({r['note']})" if r.get("note") else ""))
        if r.get("plan_line"):
            lines.append(f"         {r['plan_line']}")
        for verb, items in (r.get("actions") or {}).items():
            lines.append(f"         {verb}: {', '.join(items[:8])}" + (f" (+{len(items) - 8})" if len(items) > 8 else ""))
        for name in (r.get("resources") or [])[:15]:
            lines.append(f"         differs: {name}")
        for p in (r.get("problems") or [])[:15]:
            lines.append(f"         {p['resource']}: {'; '.join(p['issues'])}")
    n = sum(r["status"] == "drift" for r in results)
    lines.append(f"drift: {n} source(s) out of sync, {len(results)} checked")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Desired vs current state")
    ap.add_argument("--tf-dir", default=".", help="where to look for Terraform roots")
    ap.add_argument("--k8s-dir", help="manifest directory to kubectl diff against the cluster")
    ap.add_argument("--namespace", "-n")
    ap.add_argument("--no-tf", action="store_true")
    ap.add_argument("--no-k8s", action="store_true")
    ap.add_argument("--history", type=int, nargs="?", const=20, help="show the last N recorded checks")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if a.history:
        history(a.history)
        return 0
    results = []
    if not a.no_tf:
        results += check_terraform(a.tf_dir)
    if not a.no_k8s:
        results += check_kubernetes(a.k8s_dir, a.namespace)
    entry = record(results)
    print(json.dumps({"results": results, "recorded": entry}, indent=2) if a.json else render(results))
    return 1 if entry["drift"] else 0


if __name__ == "__main__":
    sys.exit(main())
