#!/usr/bin/env python3
"""Build a service map from repo IaC: name -> runtime -> log location -> repo path.

Written once per repo to .overmind/services.json, then reused. Later lookups cost
one file read instead of a repo-wide scan. Read-only; never contacts a cloud.
"""
import json
import os
import re
import sys

SKIP_DIRS = {'.overmind', '.git', 'node_modules', '.venv', 'venv', '__pycache__', 'dist',
             'build', '.terraform', 'vendor', '.mypy_cache', '.pytest_cache'}
MAX_BYTES = 400000


def walk(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            yield os.path.join(dirpath, fn)


def read(path):
    try:
        if os.path.getsize(path) > MAX_BYTES:
            return ''
        with open(path, 'r', encoding='utf-8', errors='replace') as fh:
            return fh.read()
    except OSError:
        return ''


PROVIDER_PATTERNS = [
    ('provider_aws', re.compile(r'provider\s+"aws"|AWS::|aws_(lambda|ecs|eks|cloudwatch)_|amazonaws\.com')),
    ('provider_gcp', re.compile(r'provider\s+"google"|google_(cloud_run|container|cloudfunctions)|googleapis\.com')),
    ('provider_azure', re.compile(r'provider\s+"azurerm"|azurerm_|Microsoft\.(Web|ContainerService|Insights)')),
    ('provider_oci', re.compile(r'provider\s+"oci"|oci_(core|functions|containerengine)')),
    ('provider_ibm', re.compile(r'provider\s+"ibm"|ibm_(container|code_engine|function)')),
    ('provider_alibaba', re.compile(r'provider\s+"alicloud"|alicloud_')),
    ('provider_digitalocean', re.compile(r'provider\s+"digitalocean"|digitalocean_(app|kubernetes)')),
    ('provider_scaleway', re.compile(r'provider\s+"scaleway"|scaleway_')),
    ('provider_ovh', re.compile(r'provider\s+"ovh"|ovh_')),
    ('agent_datadog', re.compile(r'datadoghq|datadog-agent|DD_API_KEY|dd-trace')),
    ('agent_loki', re.compile(r'\bloki\b|logcli|LOKI_ADDR')),
    ('agent_promtail', re.compile(r'promtail')),
    ('agent_alloy', re.compile(r'grafana/alloy|grafana-alloy')),
    ('agent_splunk', re.compile(r'splunk|hec_token|SPLUNK_HEC')),
    ('agent_elastic', re.compile(r'elasticsearch|opensearch|filebeat|logstash')),
    ('agent_fluentd', re.compile(r'fluentd|fluent-bit|fluentbit')),
    ('shipper_fluentbit', re.compile(r'fluent-bit|fluentbit|aws-for-fluent-bit')),
    ('shipper_fluentd', re.compile(r'\bfluentd\b')),
    ('shipper_vector', re.compile(r'timberio/vector|vector\.(toml|yaml)|\[sinks\.|vector-agent')),
    ('shipper_containerinsights', re.compile(r'ContainerInsights|amazon-cloudwatch-observability|cloudwatch-agent')),
    ('shipper_logging_operator', re.compile(r'logging-operator|banzaicloud')),
    ('agent_newrelic', re.compile(r'newrelic|new-relic|NEW_RELIC')),
    ('agent_honeycomb', re.compile(r'honeycomb|libhoney')),
    ('agent_otel', re.compile(r'opentelemetry|otel-collector|OTEL_EXPORTER')),
]


def scan_signals(root):
    sig = {}
    for path in walk(root):
        ext = os.path.splitext(path)[1].lower()
        name = os.path.basename(path).lower()
        if ext not in ('.tf', '.tfvars', '.yaml', '.yml', '.json', '.hcl', '.toml', '.env') \
                and name not in ('dockerfile', 'makefile'):
            continue
        text = read(path)
        if not text:
            continue
        for key, pat in PROVIDER_PATTERNS:
            if key in sig:
                continue
            if pat.search(text):
                sig[key] = os.path.relpath(path, root)
    return sig


RE_TF_BLOCK = re.compile(r'resource\s+"([a-z0-9_]+)"\s+"([A-Za-z0-9_-]+)"\s*\{')
RE_TF_NAME = re.compile(r'\b(function_name|name|service_name|cluster_name)\s*=\s*"([^"]+)"')
RE_LOG_GROUP = re.compile(r'\b(log_group_name|name)\s*=\s*"(/[^"]+)"')


def _block_body(text, start):
    depth = 0
    i = text.index('{', start)
    for j in range(i, len(text)):
        if text[j] == '{':
            depth += 1
        elif text[j] == '}':
            depth -= 1
            if depth == 0:
                return text[i + 1:j]
    return text[i + 1:]


RUNTIME_BY_TF = {
    'aws_lambda_function': ('lambda', 'aws'),
    'aws_ecs_service': ('ecs', 'aws'),
    'aws_ecs_task_definition': ('ecs', 'aws'),
    'aws_eks_cluster': ('kubernetes', 'aws'),
    'aws_instance': ('ec2', 'aws'),
    'aws_apprunner_service': ('apprunner', 'aws'),
    'google_cloud_run_service': ('cloud-run', 'gcp'),
    'google_cloud_run_v2_service': ('cloud-run', 'gcp'),
    'google_cloudfunctions_function': ('cloud-functions', 'gcp'),
    'google_cloudfunctions2_function': ('cloud-functions', 'gcp'),
    'google_container_cluster': ('kubernetes', 'gcp'),
    'azurerm_linux_function_app': ('azure-functions', 'azure'),
    'azurerm_function_app': ('azure-functions', 'azure'),
    'azurerm_container_app': ('container-apps', 'azure'),
    'azurerm_kubernetes_cluster': ('kubernetes', 'azure'),
    'azurerm_linux_web_app': ('app-service', 'azure'),
    'oci_functions_function': ('oci-functions', 'oci'),
    'oci_containerengine_cluster': ('kubernetes', 'oci'),
    'ibm_code_engine_app': ('code-engine', 'ibm'),
    'ibm_container_vpc_cluster': ('kubernetes', 'ibm'),
    'alicloud_fc_function': ('fc', 'alibaba'),
    'alicloud_cs_managed_kubernetes': ('kubernetes', 'alibaba'),
    'digitalocean_app': ('do-app', 'digitalocean'),
    'digitalocean_kubernetes_cluster': ('kubernetes', 'digitalocean'),
    'scaleway_container': ('scaleway-container', 'scaleway'),
}

GCP_RESOURCE_TYPE = {
    'cloud-run': 'cloud_run_revision',
    'cloud-functions': 'cloud_function',
    'kubernetes': 'k8s_container',
}


def services_from_terraform(root, rel, text, out):
    for m in RE_TF_BLOCK.finditer(text):
        rtype, label = m.group(1), m.group(2)
        if rtype not in RUNTIME_BY_TF and rtype != 'aws_cloudwatch_log_group':
            continue
        body = _block_body(text, m.start())
        line = text[:m.start()].count('\n') + 1
        if rtype == 'aws_cloudwatch_log_group':
            lg = RE_LOG_GROUP.search(body)
            if lg:
                out.setdefault('_log_groups', []).append(lg.group(2))
            continue
        runtime, cloud = RUNTIME_BY_TF[rtype]
        nm = RE_TF_NAME.search(body)
        name = nm.group(2) if nm else label
        name = re.sub(r'\$\{[^}]+\}', '', name).strip('-_') or label
        svc = out.setdefault(name, {'name': name})
        svc['runtime'] = runtime
        svc['cloud'] = cloud
        if runtime == 'kubernetes':
            svc['kind'] = 'cluster'   # a managed cluster, not a workload running on it
        svc['iac_file'] = rel
        svc['iac_line'] = line
        if cloud == 'aws':
            if runtime == 'lambda':
                svc.setdefault('log_group', '/aws/lambda/%s' % name)
            elif runtime == 'ecs':
                svc.setdefault('log_group', '/ecs/%s' % name)
            elif runtime == 'kubernetes':
                svc.setdefault('log_group', '/aws/containerinsights/%s/application' % name)
            elif runtime == 'apprunner':
                svc.setdefault('log_group', '/aws/apprunner/%s' % name)
        elif cloud == 'gcp':
            svc.setdefault('gcp_resource_type', GCP_RESOURCE_TYPE.get(runtime, 'global'))
            svc.setdefault('gcp_resource_name', name)


RE_K8S_KIND = re.compile(r'^kind:\s*(\w+)', re.M)
RE_K8S_NAME = re.compile(r'^\s{2}name:\s*([A-Za-z0-9.-]+)', re.M)
RE_K8S_NS = re.compile(r'^\s{2}namespace:\s*([A-Za-z0-9.-]+)', re.M)
K8S_WORKLOADS = {'Deployment', 'StatefulSet', 'DaemonSet', 'CronJob', 'Job', 'Rollout'}


def services_from_k8s(root, rel, text, out):
    offset = 0
    for doc in text.split('\n---'):
        start = offset
        offset += len(doc) + 4
        km = RE_K8S_KIND.search(doc)
        if not km or km.group(1) not in K8S_WORKLOADS:
            continue
        nm = RE_K8S_NAME.search(doc)
        if not nm:
            continue
        name = nm.group(1)
        ns = RE_K8S_NS.search(doc)
        svc = out.setdefault(name, {'name': name})
        svc['runtime'] = 'kubernetes'
        svc.setdefault('cloud', None)
        svc['namespace'] = ns.group(1) if ns else 'default'
        svc['workload'] = km.group(1).lower() + '/' + name
        svc['iac_file'] = rel
        svc['iac_line'] = text[:start].count('\n') + 1
        svc.setdefault('loki_selector',
                       '{namespace="%s", app="%s"}' % (svc['namespace'], name))


def services_from_cfn(root, rel, text, out):
    if 'AWSTemplateFormatVersion' not in text and 'Transform: AWS::Serverless' not in text:
        return
    for m in re.finditer(r'^\s{2}([A-Za-z0-9]+):\s*\n\s{4}Type:\s*(AWS::[A-Za-z:]+)', text, re.M):
        logical, rtype = m.group(1), m.group(2)
        if 'Function' in rtype:
            runtime, lg = 'lambda', '/aws/lambda/%s' % logical
        elif 'ECS::Service' in rtype:
            runtime, lg = 'ecs', '/ecs/%s' % logical
        else:
            continue
        svc = out.setdefault(logical, {'name': logical})
        svc.update({'runtime': runtime, 'cloud': 'aws', 'log_group': lg,
                    'iac_file': rel, 'iac_line': text[:m.start()].count('\n') + 1})


def services_from_compose(root, rel, text, out):
    if 'services:' not in text:
        return
    for m in re.finditer(r'^\s{2}([A-Za-z0-9_-]+):\s*$', text, re.M):
        name = m.group(1)
        if name in ('volumes', 'networks', 'services', 'configs', 'secrets'):
            continue
        svc = out.setdefault(name, {'name': name})
        svc.setdefault('runtime', 'container')
        svc.setdefault('iac_file', rel)
        svc.setdefault('iac_line', text[:m.start()].count('\n') + 1)



# ----------------------------------------------------------- log shippers
# A shipper decides where container logs actually land. Detecting it beats
# assuming the cloud default, and the answer is cached in the service map.

SHIPPER_FILE_HINTS = re.compile(
    r'fluent-?bit|fluentd|vector|logging|cloudwatch|promtail|alloy|otel', re.I)

# sink -> backend key, read out of the shipper's own config
SHIPPER_SINKS = [
    ('cloudwatch', re.compile(
        r'\[OUTPUT\][^\[]*?Name\s+cloudwatch|Name\s+cloudwatch_logs|'
        r'type\s*=\s*"aws_cloudwatch_logs"|cloudwatch_logs', re.I | re.S)),
    ('loki', re.compile(r'Name\s+loki|type\s*=\s*"loki"|loki\.api\.v1\.push', re.I)),
    ('elastic', re.compile(
        r'Name\s+es\b|Name\s+opensearch|type\s*=\s*"elasticsearch"', re.I)),
    ('datadog', re.compile(r'Name\s+datadog|type\s*=\s*"datadog_logs"', re.I)),
    ('splunk', re.compile(r'Name\s+splunk|type\s*=\s*"splunk_hec_logs"', re.I)),
    ('cloud-logging', re.compile(
        r'Name\s+stackdriver|type\s*=\s*"gcp_stackdriver_logs"', re.I)),
    ('azure-monitor', re.compile(
        r'Name\s+azure\b|type\s*=\s*"azure_monitor_logs"', re.I)),
    ('new-relic', re.compile(r'Name\s+nrlogs|type\s*=\s*"new_relic_logs"', re.I)),
]

RE_CW_GROUP = re.compile(
    r'(?:log_group_name|log_group_template|group_name)\s*[=:]?\s*["\']?([/\w.\-${}]+)', re.I)


def detect_shippers(root):
    """Find log shippers and the backend each one writes to."""
    found = []
    for path in walk(root):
        bn = os.path.basename(path)
        ext = os.path.splitext(path)[1].lower()
        if ext not in ('.yaml', '.yml', '.conf', '.toml', '.tf', '.json', '.ini'):
            continue
        if not SHIPPER_FILE_HINTS.search(bn) and not SHIPPER_FILE_HINTS.search(path):
            continue
        text = read(path)
        if not text:
            continue
        low = text.lower()
        lowpath = path.lower()
        fluent_syntax = '[output]' in low and re.search(r'^\s*name\s+\S+', low, re.M)
        if ('fluent-bit' in low or 'fluentbit' in low or 'fluent-bit' in lowpath
                or 'fluentbit' in lowpath or fluent_syntax):
            kind = 'fluent-bit'
        elif re.search(r'\bfluentd\b', low):
            kind = 'fluentd'
        elif 'timberio/vector' in low or '[sinks.' in low or 'vector' in bn.lower():
            kind = 'vector'
        elif 'cloudwatch-agent' in low or 'containerinsights' in low:
            kind = 'container-insights'
        elif 'promtail' in low:
            kind = 'promtail'
        elif 'alloy' in low:
            kind = 'alloy'
        else:
            continue
        sinks = [key for key, pat in SHIPPER_SINKS if pat.search(text)]
        if kind == 'promtail' or kind == 'alloy':
            sinks = sinks or ['loki']
        if kind == 'container-insights':
            sinks = sinks or ['cloudwatch']
        entry = {'kind': kind, 'config': os.path.relpath(path, root), 'sinks': sinks}
        g = RE_CW_GROUP.search(text)
        if g and 'cloudwatch' in sinks:
            entry['log_group_hint'] = g.group(1)
        found.append(entry)
    # de-duplicate by (kind, first sink), keeping the richest entry
    seen, out = {}, []
    for e in found:
        k = (e['kind'], tuple(e['sinks']))
        if k not in seen or len(str(e)) > len(str(seen[k])):
            seen[k] = e
    for e in seen.values():
        out.append(e)
    return out

def find_source_path(root, name):
    candidates = {name, name.replace('-', '_'), name.replace('_', '-')}
    for dirpath, dirnames, _ in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for d in dirnames:
            if d in candidates:
                return os.path.relpath(os.path.join(dirpath, d), root)
    return None


def build(root):
    sig = scan_signals(root)
    shippers = detect_shippers(root)
    out = {}
    for path in walk(root):
        rel = os.path.relpath(path, root)
        ext = os.path.splitext(path)[1].lower()
        bn = os.path.basename(path).lower()
        if ext == '.tf':
            services_from_terraform(root, rel, read(path), out)
        elif ext in ('.yaml', '.yml'):
            text = read(path)
            if not text or '{{' in text[:2000]:
                continue
            if bn.startswith('docker-compose') or bn == 'compose.yaml':
                services_from_compose(root, rel, text, out)
            else:
                services_from_cfn(root, rel, text, out)
                services_from_k8s(root, rel, text, out)
    log_groups = out.pop('_log_groups', [])
    # Infer the hosting cloud for bare Kubernetes manifests from the managed
    # cluster declared in the same repo, and point them at its log location.
    clusters = [s for s in out.values()
                if s.get('runtime') == 'kubernetes' and s.get('cloud')]
    shipper_sinks = [sk for sh in shippers for sk in sh['sinks']]
    shipper_kinds = sorted(set(sh['kind'] for sh in shippers))
    group_hint = next((sh['log_group_hint'] for sh in shippers
                       if sh.get('log_group_hint')), None)
    if len(set(c['cloud'] for c in clusters)) == 1:
        host = clusters[0]
        for svc in out.values():
            if svc.get('runtime') == 'kubernetes' and not svc.get('cloud'):
                svc['cloud'] = host['cloud']
                svc['cluster'] = host['name']
                if host['cloud'] == 'aws':
                    svc.setdefault('log_group',
                                   '/aws/containerinsights/%s/application' % host['name'])
                    svc.setdefault('log_stream_prefix', svc['name'])
                elif host['cloud'] == 'gcp':
                    svc.setdefault('gcp_resource_type', 'k8s_container')
                    svc.setdefault('gcp_resource_name', svc['name'])
                elif host['cloud'] == 'azure':
                    svc.setdefault('azure_table', 'ContainerLogV2')
    for svc in out.values():
        # A cluster-level shipper (DaemonSet/ConfigMap) only covers pods.
        # ECS uses FireLens per task definition, handled by its own log group.
        if svc.get('runtime') == 'kubernetes' and shippers:
            svc['shipper'] = shipper_kinds[0] if len(shipper_kinds) == 1 else shipper_kinds
            if shipper_sinks:
                svc['ships_to'] = sorted(set(shipper_sinks))
            if group_hint and '${' not in group_hint and 'cloudwatch' in shipper_sinks:
                svc['log_group'] = group_hint
    for name, svc in out.items():
        if not svc.get('log_group'):
            for lg in log_groups:
                if name in lg:
                    svc['log_group'] = lg
                    break
        sp = find_source_path(root, name)
        if sp:
            svc['source_path'] = sp
    return {'version': 1, 'root': os.path.abspath(root),
            'signals': sig, 'shippers': shippers, 'services': out}


def save(root, data):
    d = os.path.join(root, '.overmind')
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, 'services.json')
    with open(p, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
    return p


def load(root):
    p = os.path.join(root, '.overmind', 'services.json')
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding='utf-8') as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(prog='service_map')
    ap.add_argument('root', nargs='?', default='.')
    ap.add_argument('--okf', nargs='?', const='docs/okf', metavar='DIR',
                    help='also write an Open Knowledge Format bundle (default dir: docs/okf)')
    a = ap.parse_args(argv[1:])
    root = a.root
    data = build(root)
    p = save(root, data)
    svcs = data['services']
    print('service map: %d services -> %s' % (len(svcs), os.path.relpath(p, root)))
    clouds = [k[9:] for k in data['signals'] if k.startswith('provider_')]
    aggs = [k[6:] for k in data['signals'] if k.startswith('agent_')]
    if clouds:
        print('clouds:      %s' % ', '.join(clouds))
    if aggs:
        print('aggregators: %s' % ', '.join(aggs))
    for sh in data.get('shippers', []):
        print('shipper:     %s -> %s  (%s)' %
              (sh['kind'], ', '.join(sh['sinks']) or 'destination unknown', sh['config']))
    for name in sorted(svcs)[:20]:
        s = svcs[name]
        where = s.get('log_group') or s.get('loki_selector') or s.get('gcp_resource_type') or '-'
        print('  %-28s %-14s %s' % (name[:28], s.get('runtime', '?'), where))
    if len(svcs) > 20:
        print('  ... %d more' % (len(svcs) - 20))
    if a.okf:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import okf
        out = a.okf if os.path.isabs(a.okf) else os.path.join(root, a.okf)
        written, added, removed = okf.export(data, out)
        docs, errors = okf.check(out)
        print('okf bundle:  %s (%d doc(s), %s)' % (os.path.relpath(out, root), docs,
              'conformant' if not errors else '%d error(s): %s' % (len(errors), errors[0])))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
