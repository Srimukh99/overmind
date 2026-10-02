#!/usr/bin/env python3
"""crd-check: validate CustomResourceDefinitions, the custom resources that use them,
and removed or deprecated Kubernetes APIs in manifests. Read-only. Needs PyYAML.

  python3 crd_check.py [paths...] [--target 1.30] [--json]
Exit code 1 if any FAIL.
"""
import argparse
import json
import os
import re
import sys

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("crd-check needs PyYAML:  pip install pyyaml")

SKIP_DIRS = {".git", "node_modules", ".terraform", ".venv", "venv", "dist", "build", ".worktrees", "vendor", "charts"}

# (apiVersion, kind or "*") -> (removed_in, replacement)
REMOVED = {
    ("extensions/v1beta1", "Ingress"): ("1.22", "networking.k8s.io/v1"),
    ("extensions/v1beta1", "*"): ("1.16", "apps/v1 or networking.k8s.io/v1"),
    ("apps/v1beta1", "*"): ("1.16", "apps/v1"),
    ("apps/v1beta2", "*"): ("1.16", "apps/v1"),
    ("networking.k8s.io/v1beta1", "*"): ("1.22", "networking.k8s.io/v1"),
    ("apiextensions.k8s.io/v1beta1", "*"): ("1.22", "apiextensions.k8s.io/v1"),
    ("admissionregistration.k8s.io/v1beta1", "*"): ("1.22", "admissionregistration.k8s.io/v1"),
    ("rbac.authorization.k8s.io/v1beta1", "*"): ("1.22", "rbac.authorization.k8s.io/v1"),
    ("certificates.k8s.io/v1beta1", "*"): ("1.22", "certificates.k8s.io/v1"),
    ("scheduling.k8s.io/v1beta1", "*"): ("1.22", "scheduling.k8s.io/v1"),
    ("batch/v1beta1", "CronJob"): ("1.25", "batch/v1"),
    ("policy/v1beta1", "PodDisruptionBudget"): ("1.25", "policy/v1"),
    ("policy/v1beta1", "PodSecurityPolicy"): ("1.25", "Pod Security Admission (no replacement kind)"),
    ("autoscaling/v2beta1", "*"): ("1.25", "autoscaling/v2"),
    ("autoscaling/v2beta2", "*"): ("1.26", "autoscaling/v2"),
    ("discovery.k8s.io/v1beta1", "*"): ("1.25", "discovery.k8s.io/v1"),
    ("events.k8s.io/v1beta1", "*"): ("1.25", "events.k8s.io/v1"),
    ("storage.k8s.io/v1beta1", "CSIStorageCapacity"): ("1.27", "storage.k8s.io/v1"),
    ("flowcontrol.apiserver.k8s.io/v1beta1", "*"): ("1.26", "flowcontrol.apiserver.k8s.io/v1"),
    ("flowcontrol.apiserver.k8s.io/v1beta2", "*"): ("1.29", "flowcontrol.apiserver.k8s.io/v1"),
    ("flowcontrol.apiserver.k8s.io/v1beta3", "*"): ("1.32", "flowcontrol.apiserver.k8s.io/v1"),
}
BUILTIN_GROUPS = {"", "apps", "batch", "extensions", "policy", "autoscaling", "networking.k8s.io", "rbac.authorization.k8s.io",
                  "apiextensions.k8s.io", "admissionregistration.k8s.io", "storage.k8s.io", "scheduling.k8s.io",
                  "certificates.k8s.io", "coordination.k8s.io", "discovery.k8s.io", "events.k8s.io", "node.k8s.io",
                  "flowcontrol.apiserver.k8s.io", "authentication.k8s.io", "authorization.k8s.io", "resource.k8s.io"}


def ver(s):
    return tuple(int(x) for x in s.split("."))


def F(level, rule, msg, fix, file, line):
    return {"level": level, "rule": rule, "msg": msg, "fix": fix, "file": file, "line": line}


def load_docs(path):
    with open(path, encoding="utf-8", errors="ignore") as fh:
        text = fh.read()
    if "{{" in text:  # Helm templates: not plain YAML
        return []
    docs, line = [], 1
    for chunk in re.split(r"^---\s*$", text, flags=re.M):
        try:
            d = yaml.safe_load(chunk)
        except yaml.YAMLError:
            d = None
        if isinstance(d, dict) and "apiVersion" in d and "kind" in d:
            docs.append((d, line))
        line += chunk.count("\n") + 1
    return docs


def iter_yaml(paths):
    for p in paths:
        if os.path.isfile(p):
            yield p
            continue
        for root, dirs, files in os.walk(p):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for f in files:
                if f.endswith((".yaml", ".yml")):
                    yield os.path.join(root, f)


def check_crd(d, file, line):
    out = []
    spec = d.get("spec") or {}
    names = spec.get("names") or {}
    group, plural = spec.get("group", ""), names.get("plural", "")
    name = (d.get("metadata") or {}).get("name", "")
    if name != f"{plural}.{group}":
        out.append(F("FAIL", "crd-name", f"metadata.name '{name}' must be '<plural>.<group>' ('{plural}.{group}')", "Rename to plural.group", file, line))
    if not names.get("kind"):
        out.append(F("FAIL", "crd-kind", "spec.names.kind missing", "Set spec.names.kind", file, line))
    if plural and plural != plural.lower():
        out.append(F("FAIL", "crd-plural-case", "spec.names.plural must be lowercase", "Lowercase the plural name", file, line))
    if spec.get("scope") not in ("Namespaced", "Cluster"):
        out.append(F("FAIL", "crd-scope", "spec.scope must be Namespaced or Cluster", "Set spec.scope", file, line))
    if spec.get("preserveUnknownFields") is True:
        out.append(F("FAIL", "crd-preserve-unknown", "preserveUnknownFields: true is not allowed in apiextensions.k8s.io/v1", "Remove it; use x-kubernetes-preserve-unknown-fields on specific subtrees", file, line))
    versions = spec.get("versions") or []
    if not versions:
        out.append(F("FAIL", "crd-no-versions", "No versions defined", "Add spec.versions", file, line))
        return out
    storage = [v for v in versions if v.get("storage")]
    if len(storage) != 1:
        out.append(F("FAIL", "crd-storage", f"Exactly one version must have storage: true (found {len(storage)})", "Mark one version as storage", file, line))
    if not any(v.get("served") for v in versions):
        out.append(F("FAIL", "crd-served", "No version is served", "Set served: true on at least one version", file, line))
    schemas = []
    for v in versions:
        schema = (v.get("schema") or {}).get("openAPIV3Schema")
        vn = v.get("name", "?")
        if not schema:
            out.append(F("FAIL", "crd-no-schema", f"Version {vn} has no openAPIV3Schema", "Add a structural schema", file, line))
            continue
        schemas.append(json.dumps(schema, sort_keys=True))
        if schema.get("x-kubernetes-preserve-unknown-fields") is True:
            out.append(F("WARN", "crd-schemaless", f"Version {vn} accepts any fields at the root (no validation)", "Define properties for spec and status", file, line))
        props = schema.get("properties") or {}
        if "status" in props and "status" not in (v.get("subresources") or {}):
            out.append(F("WARN", "crd-status-subresource", f"Version {vn} has a status field but no status subresource", "Add subresources: {status: {}} so controllers update status separately", file, line))
        if v.get("deprecated") and v.get("storage"):
            out.append(F("WARN", "crd-deprecated-storage", f"Deprecated version {vn} is the storage version", "Move storage to the newest version and migrate stored objects", file, line))
    if len(versions) > 1 and len(set(schemas)) > 1:
        strategy = ((spec.get("conversion") or {}).get("strategy")) or "None"
        if strategy == "None":
            out.append(F("WARN", "crd-conversion", "Multiple versions with different schemas but conversion strategy None", "Add a conversion webhook or keep schemas compatible", file, line))
    return out


def validate(obj, schema, path, out, file, line):
    """Light structural check: types, enums, required, and unknown fields that will be pruned."""
    if not isinstance(schema, dict) or schema.get("x-kubernetes-preserve-unknown-fields") or schema.get("x-kubernetes-int-or-string"):
        return
    t = schema.get("type")
    types = {"object": dict, "array": list, "string": str, "boolean": bool, "integer": int, "number": (int, float)}
    if t in types and obj is not None:
        ok = isinstance(obj, types[t]) and not (t in ("integer", "number") and isinstance(obj, bool))
        if not ok:
            out.append(F("FAIL", "cr-type", f"{path} should be {t}, got {type(obj).__name__}", "Fix the value type", file, line))
            return
    if "enum" in schema and obj not in schema["enum"]:
        out.append(F("FAIL", "cr-enum", f"{path}={obj!r} not in {schema['enum']}", "Use one of the allowed values", file, line))
    if isinstance(obj, dict):
        props = schema.get("properties")
        for req in schema.get("required", []):
            if req not in obj:
                out.append(F("FAIL", "cr-required", f"{path}.{req} is required", "Add the field", file, line))
        if props is not None and not schema.get("additionalProperties"):
            for k in obj:
                if k not in props:
                    out.append(F("WARN", "cr-unknown-field", f"{path}.{k} is not in the schema and will be silently dropped", "Fix the field name (typo?) or add it to the CRD schema", file, line))
        for k, v in obj.items():
            if props and k in props:
                validate(v, props[k], f"{path}.{k}", out, file, line)
            elif isinstance(schema.get("additionalProperties"), dict):
                validate(v, schema["additionalProperties"], f"{path}.{k}", out, file, line)
    if isinstance(obj, list) and isinstance(schema.get("items"), dict):
        for i, item in enumerate(obj):
            validate(item, schema["items"], f"{path}[{i}]", out, file, line)


def scan(paths, target):
    docs = []
    for p in iter_yaml(paths):
        try:
            docs += [(d, os.path.relpath(p), ln) for d, ln in load_docs(p)]
        except OSError:
            pass
    findings, crds = [], {}
    for d, file, line in docs:
        api, kind = d["apiVersion"], d["kind"]
        rem = REMOVED.get((api, kind)) or REMOVED.get((api, "*"))
        if kind == "PodSecurityPolicy":
            rem = REMOVED[("policy/v1beta1", "PodSecurityPolicy")]
        if rem:
            removed_in, repl = rem
            level = "FAIL" if ver(removed_in) <= ver(target) else "WARN"
            findings.append(F(level, "k8s-removed-api", f"{kind} uses {api}, removed in Kubernetes {removed_in}", f"Migrate to {repl}", file, line))
        if kind == "CustomResourceDefinition":
            findings += check_crd(d, file, line)
            spec = d.get("spec") or {}
            crds[(spec.get("group"), (spec.get("names") or {}).get("kind"))] = (spec, file)
    for d, file, line in docs:
        api, kind = d["apiVersion"], d["kind"]
        group, _, version = api.rpartition("/")
        if group in BUILTIN_GROUPS or kind == "CustomResourceDefinition":
            continue
        match = crds.get((group, kind))
        if not match:
            continue
        spec, crd_file = match
        v = next((x for x in spec.get("versions") or [] if x.get("name") == version), None)
        if v is None:
            findings.append(F("FAIL", "cr-unknown-version", f"{kind} uses version {version}, not defined in {crd_file}", "Use a version the CRD defines", file, line))
            continue
        if not v.get("served"):
            findings.append(F("FAIL", "cr-version-not-served", f"{kind} {version} is not served", "Use a served version", file, line))
        if v.get("deprecated"):
            findings.append(F("WARN", "cr-deprecated-version", f"{kind} {version} is deprecated", "Move to the newest served version", file, line))
        schema = (v.get("schema") or {}).get("openAPIV3Schema") or {}
        body = {k: val for k, val in d.items() if k not in ("apiVersion", "kind", "metadata")}
        sub = dict(schema)
        if isinstance(sub.get("properties"), dict):
            sub["properties"] = {k: s for k, s in sub["properties"].items() if k not in ("apiVersion", "kind", "metadata")}
            sub["required"] = [r for r in sub.get("required", []) if r not in ("apiVersion", "kind", "metadata")]
        validate(body, sub, kind, findings, file, line)
    return findings, len(docs), len(crds)


def main(argv=None):
    ap = argparse.ArgumentParser(description="CRD, custom resource and Kubernetes API checks")
    ap.add_argument("paths", nargs="*", default=["."])
    ap.add_argument("--target", default="1.31", help="Kubernetes version you deploy to (default 1.31)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    findings, ndocs, ncrds = scan(a.paths, a.target)
    findings.sort(key=lambda f: (f["level"] != "FAIL", f["file"], f["line"]))
    if a.json:
        print(json.dumps({"documents": ndocs, "crds": ncrds, "findings": findings}, indent=2))
    else:
        for f in findings:
            print(f"{f['level']:<5} {f['file']}:{f['line']}  {f['rule']}: {f['msg']}\n      fix: {f['fix']}")
        fails = sum(f["level"] == "FAIL" for f in findings)
        print(f"crd-check: {fails} FAIL, {len(findings) - fails} WARN, {ndocs} manifests, {ncrds} CRDs, target k8s {a.target}")
    return 1 if any(f["level"] == "FAIL" for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
