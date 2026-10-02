#!/usr/bin/env python3
"""iac-check: call out risky infrastructure design in Terraform, CloudFormation,
Kubernetes manifests and Dockerfiles. Dependency-free, read-only.

  python3 iac_check.py [paths...] [--json]
Exit code 1 if any FAIL.
"""
import argparse
import json
import os
import re
import sys

SKIP_DIRS = {".git", "node_modules", ".terraform", ".venv", "venv", "dist", "build", ".worktrees", "vendor"}
IGNORE = "iac-check: ignore"
OPEN_CIDR = r'"(?:0\.0\.0\.0/0|::/0)"'
SENSITIVE_PORTS = {22: "SSH", 3389: "RDP", 3306: "MySQL", 5432: "Postgres", 1433: "SQL Server", 27017: "MongoDB",
                   6379: "Redis", 9200: "Elasticsearch", 5601: "Kibana", 2379: "etcd", 10250: "kubelet", 11211: "Memcached"}


def F(level, rule, msg, fix):
    return {"level": level, "rule": rule, "msg": msg, "fix": fix}


# ---------------- Terraform ----------------
BLOCK_START = re.compile(r'^\s*(resource|data|module)\s+"([\w-]+)"(?:\s+"([\w-]+)")?\s*\{', re.M)


def tf_blocks(text):
    for m in BLOCK_START.finditer(text):
        depth, i = 0, m.end() - 1
        while i < len(text):
            c = text[i]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        yield m.group(2), m.group(3) or "", text[m.start():i + 1], text.count("\n", 0, m.start()) + 1


def has(body, rx):
    return re.search(rx, body, re.M) is not None


def tf_rules(rtype, body):
    out = []
    if rtype in ("aws_s3_bucket", "aws_s3_bucket_acl") and has(body, r'acl\s*=\s*"public-read(?:-write)?"'):
        out.append(F("FAIL", "s3-public-acl", "S3 bucket ACL grants public read", "Use private ACL; serve public content via CloudFront with origin access control"))
    if rtype == "aws_s3_bucket_public_access_block" and has(body, r'(?:block_public_acls|block_public_policy|ignore_public_acls|restrict_public_buckets)\s*=\s*false'):
        out.append(F("FAIL", "s3-public-block-off", "S3 public access block is disabled", "Set all four public access block flags to true"))
    if rtype == "aws_s3_bucket_policy" and has(body, r'"Principal"\s*:\s*"\*"|Principal\s*=\s*"\*"|identifiers\s*=\s*\["\*"\]'):
        out.append(F("WARN", "s3-policy-wildcard-principal", "Bucket policy allows any principal", "Restrict Principal to specific roles or add strict conditions"))
    if rtype in ("aws_security_group", "aws_security_group_rule", "aws_vpc_security_group_ingress_rule"):
        ingress_bodies = re.findall(r'ingress\s*\{[^{}]*\}', body, re.S) if rtype == "aws_security_group" else [body]
        if rtype == "aws_security_group_rule" and not has(body, r'type\s*=\s*"ingress"'):
            ingress_bodies = []
        for ib in ingress_bodies:
            if has(ib, r'cidr_blocks\s*=\s*\[[^\]]*' + OPEN_CIDR) or has(ib, r'(?:cidr_ipv4|cidr_ipv6)\s*=\s*' + OPEN_CIDR) or has(ib, r'ipv6_cidr_blocks\s*=\s*\[[^\]]*"::/0"'):
                fp = re.search(r'from_port\s*=\s*(\d+)', ib)
                tp = re.search(r'to_port\s*=\s*(\d+)', ib)
                lo, hi = (int(fp.group(1)) if fp else 0), (int(tp.group(1)) if tp else 65535)
                hits = [f"{n} ({p})" for p, n in SENSITIVE_PORTS.items() if lo <= p <= hi]
                if lo == 0 and hi in (0, 65535):
                    out.append(F("FAIL", "sg-open-all", "Ingress open to the internet on all ports", "Restrict CIDRs and ports to what is needed"))
                elif hits:
                    out.append(F("FAIL", "sg-open-sensitive", f"Ingress open to the internet on {', '.join(hits)}", "Use SSM Session Manager or a VPN; never expose admin or data ports"))
                elif not ({lo, hi} <= {80, 443}):
                    out.append(F("WARN", "sg-open-world", f"Ingress open to the internet on ports {lo}-{hi}", "Confirm this is a public endpoint; otherwise restrict CIDRs"))
    if rtype in ("aws_db_instance", "aws_rds_cluster_instance"):
        if has(body, r'publicly_accessible\s*=\s*true'):
            out.append(F("FAIL", "rds-public", "Database is publicly accessible", "Set publicly_accessible = false; reach it through private subnets"))
        if rtype == "aws_db_instance" and not has(body, r'storage_encrypted\s*=\s*true'):
            out.append(F("WARN", "rds-unencrypted", "Database storage encryption not enabled", "Set storage_encrypted = true with a KMS key"))
        if rtype == "aws_db_instance" and not has(body, r'deletion_protection\s*=\s*true'):
            out.append(F("WARN", "rds-no-deletion-protection", "Deletion protection not enabled", "Set deletion_protection = true for production"))
    if rtype == "aws_rds_cluster" and not has(body, r'storage_encrypted\s*=\s*true'):
        out.append(F("WARN", "rds-unencrypted", "Aurora cluster storage encryption not enabled", "Set storage_encrypted = true"))
    if rtype == "aws_eks_cluster" and not has(body, r'endpoint_public_access\s*=\s*false'):
        if not has(body, r'public_access_cidrs\s*=\s*\[') or has(body, r'public_access_cidrs\s*=\s*\[[^\]]*' + OPEN_CIDR):
            out.append(F("FAIL", "eks-public-endpoint", "EKS API endpoint is public to the whole internet", "Set endpoint_public_access = false, or restrict public_access_cidrs"))
    if rtype == "aws_lambda_function_url" and has(body, r'authorization_type\s*=\s*"NONE"'):
        out.append(F("WARN", "lambda-url-no-auth", "Lambda function URL has no auth", "Use AWS_IAM, or put it behind API Gateway with auth"))
    if rtype in ("aws_iam_policy", "aws_iam_role_policy", "aws_iam_user_policy", "aws_iam_policy_document"):
        if has(body, r'"Action"\s*:\s*"\*"|actions\s*=\s*\["\*"\]|"Action"\s*:\s*\[\s*"\*"\s*\]'):
            out.append(F("FAIL", "iam-wildcard-action", "IAM policy allows every action", "List specific actions; grant least privilege"))
        elif has(body, r'"Action"\s*:\s*"[\w-]+:\*"|actions\s*=\s*\[[^\]]*"[\w-]+:\*"'):
            out.append(F("WARN", "iam-service-wildcard", "IAM policy allows all actions on a service", "Narrow to the actions actually used"))
    if rtype == "aws_iam_user_policy_attachment" or rtype == "aws_iam_access_key":
        out.append(F("WARN", "iam-user-credentials", "Long-lived IAM user credentials", "Prefer roles with short-lived credentials (SSO, IRSA, OIDC)"))
    if rtype == "aws_instance":
        if has(body, r'associate_public_ip_address\s*=\s*true'):
            out.append(F("WARN", "ec2-public-ip", "Instance gets a public IP", "Use private subnets behind a load balancer or NAT"))
        if not has(body, r'http_tokens\s*=\s*"required"'):
            out.append(F("WARN", "ec2-imdsv1", "IMDSv2 not enforced", 'Add metadata_options { http_tokens = "required" }'))
    if rtype == "aws_ebs_volume" and not has(body, r'encrypted\s*=\s*true'):
        out.append(F("WARN", "ebs-unencrypted", "EBS volume not encrypted", "Set encrypted = true"))
    if rtype in ("aws_elasticsearch_domain", "aws_opensearch_domain") and not has(body, r'vpc_options\s*\{'):
        out.append(F("WARN", "search-public", "Search domain not in a VPC", "Add vpc_options with private subnets"))
    if rtype == "aws_lb" and has(body, r'internal\s*=\s*false') and not has(body, r'drop_invalid_header_fields\s*=\s*true'):
        out.append(F("WARN", "alb-invalid-headers", "Public load balancer accepts invalid headers", "Set drop_invalid_header_fields = true"))
    if rtype in ("aws_cloudtrail",) and not has(body, r'enable_log_file_validation\s*=\s*true'):
        out.append(F("WARN", "cloudtrail-validation", "CloudTrail log file validation off", "Set enable_log_file_validation = true"))
    if rtype.startswith("azurerm_storage_account") and has(body, r'allow_nested_items_to_be_public\s*=\s*true|public_network_access_enabled\s*=\s*true'):
        out.append(F("WARN", "azure-storage-public", "Storage account allows public access", "Disable public access; use private endpoints"))
    if rtype == "google_storage_bucket_iam_member" and has(body, r'"allUsers"|"allAuthenticatedUsers"'):
        out.append(F("FAIL", "gcs-public", "GCS bucket granted to all users", "Remove allUsers/allAuthenticatedUsers"))
    if has(body, r'(?i)\b(?:password|secret|token|access_key)\s*=\s*"(?!\$\{)[^"\s]{8,}"'):
        out.append(F("FAIL", "tf-hardcoded-secret", "Secret value hard-coded in Terraform", "Read from Secrets Manager / SSM / Vault, or a sensitive variable"))
    return out


def check_tf(path, text):
    findings = []
    for rtype, name, body, line in tf_blocks(text):
        if IGNORE in body:
            continue
        for f in tf_rules(rtype, body):
            f.update(file=path, line=line, resource=f"{rtype}.{name}")
            findings.append(f)
    return findings


# ---------------- Kubernetes ----------------
K8S_RULES = [
    (r'^\s*privileged:\s*true', "FAIL", "k8s-privileged", "Container runs privileged", "Remove privileged; grant specific capabilities if truly needed"),
    (r'^\s*host(?:Network|PID|IPC):\s*true', "FAIL", "k8s-host-namespace", "Pod shares the host network/PID/IPC namespace", "Remove hostNetwork/hostPID/hostIPC"),
    (r'^\s*hostPath:', "WARN", "k8s-hostpath", "hostPath volume mounts the node filesystem", "Use a PVC, emptyDir or a CSI driver"),
    (r'^\s*allowPrivilegeEscalation:\s*true', "WARN", "k8s-priv-escalation", "Privilege escalation allowed", "Set allowPrivilegeEscalation: false"),
    (r'^\s*runAsUser:\s*0\b|^\s*runAsNonRoot:\s*false', "WARN", "k8s-root", "Container runs as root", "Set runAsNonRoot: true and a non-zero runAsUser"),
    (r'^\s*image:\s*["\']?[^\s"\'@]+:latest["\']?\s*$', "WARN", "k8s-latest-tag", "Image uses the :latest tag", "Pin a version tag or digest so rollbacks are possible"),
    (r'^\s*-?\s*(?:SYS_ADMIN|NET_ADMIN|ALL)\s*$', "WARN", "k8s-capabilities", "Powerful Linux capability added", "Drop ALL and add only what is required"),
    (r'^\s*automountServiceAccountToken:\s*true', "WARN", "k8s-sa-token", "Service account token auto-mounted", "Set automountServiceAccountToken: false unless the pod calls the API"),
]
WORKLOAD = re.compile(r'^kind:\s*(Deployment|StatefulSet|DaemonSet|Job|CronJob|Pod|ReplicaSet|Rollout)\b', re.M)


def check_k8s(path, text):
    findings = []
    for doc in re.split(r'^---\s*$', text, flags=re.M):
        if not re.search(r'^apiVersion:', doc, re.M):
            continue
        offset = text.find(doc)
        base_line = text.count("\n", 0, max(offset, 0)) + 1
        for rx, level, rule, msg, fix in K8S_RULES:
            for m in re.finditer(rx, doc, re.M):
                line = doc.count("\n", 0, m.start()) + base_line
                if IGNORE not in doc.splitlines()[doc.count("\n", 0, m.start())]:
                    findings.append({**F(level, rule, msg, fix), "file": path, "line": line})
        if WORKLOAD.search(doc):
            line = base_line
            if "containers:" in doc and "limits:" not in doc:
                findings.append({**F("WARN", "k8s-no-limits", "Workload has no resource limits", "Set requests and limits for cpu and memory"), "file": path, "line": line})
            if re.search(r'^kind:\s*(Deployment|StatefulSet|DaemonSet|Rollout)', doc, re.M) and "readinessProbe:" not in doc:
                findings.append({**F("WARN", "k8s-no-readiness", "Workload has no readiness probe", "Add a readinessProbe so traffic waits for healthy pods"), "file": path, "line": line})
            if re.search(r'^\s*image:\s*["\']?[^\s:"\'@/]+(?:/[^\s:"\'@]+)*["\']?\s*$', doc, re.M):
                findings.append({**F("WARN", "k8s-untagged-image", "Image has no tag (defaults to latest)", "Pin a version tag or digest"), "file": path, "line": line})
        if re.search(r'^kind:\s*Service\b', doc, re.M) and re.search(r'type:\s*LoadBalancer', doc) and "loadBalancerSourceRanges" not in doc \
                and not re.search(r'aws-load-balancer-(?:internal|scheme):\s*["\']?(?:true|internal)', doc):
            findings.append({**F("WARN", "k8s-public-lb", "LoadBalancer Service open to the internet", "Add loadBalancerSourceRanges or make it internal"), "file": path, "line": base_line})
        if re.search(r'^kind:\s*(?:ClusterRoleBinding)\b', doc, re.M) and re.search(r'name:\s*cluster-admin', doc):
            findings.append({**F("FAIL", "k8s-cluster-admin", "Binding grants cluster-admin", "Create a narrow Role/ClusterRole instead"), "file": path, "line": base_line})
        if re.search(r'^kind:\s*Secret\b', doc, re.M) and re.search(r'^(?:data|stringData):', doc, re.M):
            findings.append({**F("FAIL", "k8s-secret-in-git", "Kubernetes Secret with data committed to the repo", "Use External Secrets, Sealed Secrets or SOPS"), "file": path, "line": base_line})
    return findings


# ---------------- CloudFormation ----------------
CFN_RULES = [
    (r'PubliclyAccessible["\']?\s*:\s*["\']?true', "FAIL", "rds-public", "Database is publicly accessible", "Set PubliclyAccessible: false"),
    (r'CidrIp["\']?\s*:\s*["\']?0\.0\.0\.0/0', "WARN", "sg-open-world", "Security group ingress open to the internet", "Restrict CidrIp; never expose admin or data ports"),
    (r'AccessControl["\']?\s*:\s*["\']?PublicRead', "FAIL", "s3-public-acl", "S3 bucket ACL grants public read", "Use a private bucket behind CloudFront"),
    (r'(?:BlockPublicAcls|BlockPublicPolicy|IgnorePublicAcls|RestrictPublicBuckets)["\']?\s*:\s*["\']?false', "FAIL", "s3-public-block-off", "S3 public access block disabled", "Set all four flags to true"),
    (r'"Action"\s*:\s*"\*"|Action:\s*["\']?\*["\']?\s*$', "FAIL", "iam-wildcard-action", "IAM policy allows every action", "List specific actions"),
    (r'StorageEncrypted["\']?\s*:\s*["\']?false', "WARN", "rds-unencrypted", "Database storage encryption off", "Set StorageEncrypted: true"),
]


def check_cfn(path, text):
    out = []
    for rx, level, rule, msg, fix in CFN_RULES:
        for m in re.finditer(rx, text, re.M):
            out.append({**F(level, rule, msg, fix), "file": path, "line": text.count("\n", 0, m.start()) + 1})
    return out


# ---------------- Dockerfile ----------------
def check_docker(path, text):
    out = []
    lines = text.splitlines()
    users = [l for l in lines if re.match(r'^\s*USER\s+', l, re.I)]
    if not users or re.match(r'^\s*USER\s+(?:root|0)\s*$', users[-1], re.I):
        out.append({**F("WARN", "docker-root", "Container runs as root", "Add a non-root USER at the end of the Dockerfile"), "file": path, "line": 1})
    for i, l in enumerate(lines, 1):
        if re.match(r'^\s*FROM\s+\S+:latest\b', l, re.I) or re.match(r'^\s*FROM\s+[^\s:@]+\s*(?:AS\s+\w+)?\s*$', l, re.I):
            if not re.match(r'^\s*FROM\s+scratch', l, re.I):
                out.append({**F("WARN", "docker-latest", "Base image not pinned", "Pin a version tag or digest"), "file": path, "line": i})
        if re.match(r'^\s*(?:ENV|ARG)\s+\w*(?:PASSWORD|SECRET|TOKEN|API_KEY)\w*[=\s]+\S+', l, re.I):
            out.append({**F("FAIL", "docker-secret", "Secret baked into the image", "Use build secrets (--mount=type=secret) or runtime env"), "file": path, "line": i})
        if re.match(r'^\s*ADD\s+https?://', l, re.I):
            out.append({**F("WARN", "docker-add-url", "ADD downloads a remote file without verification", "Use curl with a checksum, or COPY"), "file": path, "line": i})
    return out


def classify(path, text):
    base = os.path.basename(path)
    if path.endswith(".tf"):
        return "tf"
    if base == "Dockerfile" or base.startswith("Dockerfile.") or base.endswith(".dockerfile"):
        return "docker"
    if path.endswith((".yaml", ".yml", ".json", ".template")):
        if "AWSTemplateFormatVersion" in text or re.search(r'Type["\']?\s*:\s*["\']?AWS::', text):
            return "cfn"
        if re.search(r'^apiVersion:', text, re.M) and re.search(r'^kind:', text, re.M):
            return "k8s"
    return None


def iter_files(paths):
    for p in paths:
        if os.path.isfile(p):
            yield p
            continue
        for root, dirs, files in os.walk(p):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for f in files:
                yield os.path.join(root, f)


def scan(paths):
    findings, scanned = [], 0
    for p in iter_files(paths):
        try:
            if os.path.getsize(p) > 2_000_000:
                continue
            with open(p, encoding="utf-8", errors="ignore") as fh:
                text = fh.read()
        except OSError:
            continue
        kind = classify(p, text)
        if not kind:
            continue
        scanned += 1
        rel = os.path.relpath(p)
        findings += {"tf": check_tf, "k8s": check_k8s, "cfn": check_cfn, "docker": check_docker}[kind](rel, text)
    return findings, scanned


def main(argv=None):
    ap = argparse.ArgumentParser(description="Risky IaC design checks")
    ap.add_argument("paths", nargs="*", default=["."])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--fail-on", choices=["FAIL", "WARN"], default="FAIL")
    a = ap.parse_args(argv)
    findings, scanned = scan(a.paths)
    findings.sort(key=lambda f: (f["level"] != "FAIL", f["file"], f["line"]))
    if a.json:
        print(json.dumps({"scanned": scanned, "findings": findings}, indent=2))
    else:
        for f in findings:
            res = f" [{f['resource']}]" if f.get("resource") else ""
            print(f"{f['level']:<5} {f['file']}:{f['line']}{res}  {f['rule']}: {f['msg']}\n      fix: {f['fix']}")
        fails = sum(f["level"] == "FAIL" for f in findings)
        print(f"iac-check: {fails} FAIL, {len(findings) - fails} WARN, {scanned} IaC files scanned")
    bad = [f for f in findings if f["level"] == "FAIL" or a.fail_on == "WARN"]
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
