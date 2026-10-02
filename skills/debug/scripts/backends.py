#!/usr/bin/env python3
"""Backend registry: log query backends for every major cloud + vendor-neutral aggregators.

Each backend declares:
  key         stable id
  label       human name
  kind        "native" (tied to a cloud) or "aggregator" (vendor-neutral)
  cloud       cloud key for native backends, None for aggregators
  detect()    -> confidence 0..3 from repo signals + env + CLI presence
  build()     -> dict describing the query (never executed here)
  command()   -> argv list, read-only, for the resolved query

Nothing in this module executes a query. log_fetch.py runs commands.
"""
import os
import shutil
import subprocess

# ---------------------------------------------------------------- helpers

def _cli(name):
    return shutil.which(name) is not None


def _env_any(*names):
    return any(os.environ.get(n) for n in names)


def _cli_ok(argv, timeout=6):
    """True if a read-only CLI probe succeeds (used for auth checks)."""
    try:
        p = subprocess.run(argv, capture_output=True, timeout=timeout)
        return p.returncode == 0
    except Exception:
        return False


# ---------------------------------------------------------------- backends
# Every backend is a plain dict so the registry stays data, not class soup.

def _aws_detect(sig):
    c = 0
    if sig.get('provider_aws'):
        c += 2
    if _env_any('AWS_PROFILE', 'AWS_REGION', 'AWS_DEFAULT_REGION', 'AWS_ACCESS_KEY_ID'):
        c += 1
    if _cli('aws'):
        c += 1
    return min(c, 3)


def _aws_build(svc, since, limit, query):
    group = svc.get('log_group')
    if not group:
        return None
    q = {
        'backend': 'cloudwatch',
        'log_group': group,
        'since': since,
        'limit': limit,
        'filter': query,
    }
    if svc.get('log_stream_prefix'):
        q['stream_prefix'] = svc['log_stream_prefix']
    return q


def _aws_command(q):
    argv = ['aws', 'logs', 'tail', q['log_group'], '--since', q['since'], '--format', 'short']
    if q.get('stream_prefix'):
        argv += ['--log-stream-name-prefix', q['stream_prefix']]
    if q.get('filter'):
        argv += ['--filter-pattern', q['filter']]
    return argv


def _gcp_detect(sig):
    c = 0
    if sig.get('provider_gcp'):
        c += 2
    if _env_any('GOOGLE_CLOUD_PROJECT', 'GCLOUD_PROJECT', 'GOOGLE_APPLICATION_CREDENTIALS'):
        c += 1
    if _cli('gcloud'):
        c += 1
    return min(c, 3)


def _gcp_build(svc, since, limit, query):
    parts = []
    res = svc.get('gcp_resource_type')
    if res:
        parts.append('resource.type="%s"' % res)
    name = svc.get('gcp_resource_name') or svc.get('name')
    if name:
        parts.append('(resource.labels.container_name="%(n)s" OR '
                     'resource.labels.service_name="%(n)s" OR '
                     'resource.labels.function_name="%(n)s")' % {'n': name})
    parts.append('severity>=WARNING' if not query else 'textPayload:"%s"' % query)
    return {'backend': 'cloud-logging', 'filter': ' AND '.join(parts),
            'since': since, 'limit': limit,
            'project': svc.get('gcp_project') or os.environ.get('GOOGLE_CLOUD_PROJECT')}


def _gcp_command(q):
    argv = ['gcloud', 'logging', 'read', q['filter'],
            '--limit', str(q['limit']), '--format', 'value(timestamp,textPayload,jsonPayload)']
    if q.get('project'):
        argv += ['--project', q['project']]
    if q.get('since'):
        argv += ['--freshness', q['since']]
    return argv


def _azure_detect(sig):
    c = 0
    if sig.get('provider_azure'):
        c += 2
    if _env_any('AZURE_SUBSCRIPTION_ID', 'AZURE_TENANT_ID'):
        c += 1
    if _cli('az'):
        c += 1
    return min(c, 3)


def _azure_build(svc, since, limit, query):
    ws = svc.get('azure_workspace_id')
    if not ws:
        return None
    table = svc.get('azure_table') or 'ContainerLog'
    kql = ['%s' % table,
           '| where TimeGenerated > ago(%s)' % since]
    if svc.get('name'):
        kql.append('| where Computer contains "%s" or ContainerID contains "%s"'
                   % (svc['name'], svc['name']))
    if query:
        kql.append('| where LogEntry contains "%s"' % query)
    kql.append('| order by TimeGenerated desc | take %d' % limit)
    return {'backend': 'azure-monitor', 'workspace': ws,
            'kql': '\n'.join(kql), 'since': since, 'limit': limit}


def _azure_command(q):
    return ['az', 'monitor', 'log-analytics', 'query',
            '--workspace', q['workspace'], '--analytics-query', q['kql'],
            '--output', 'table']


def _oci_detect(sig):
    c = 2 if sig.get('provider_oci') else 0
    if _cli('oci'):
        c += 1
    if _env_any('OCI_CLI_PROFILE', 'OCI_COMPARTMENT_ID'):
        c += 1
    return min(c, 3)


def _oci_build(svc, since, limit, query):
    comp = svc.get('oci_compartment_id') or os.environ.get('OCI_COMPARTMENT_ID')
    if not comp:
        return None
    search = 'search "%s" | sort by datetime desc' % comp
    if query:
        search = 'search "%s" | where msg = \'%s\' | sort by datetime desc' % (comp, query)
    return {'backend': 'oci-logging', 'compartment': comp,
            'search': search, 'since': since, 'limit': limit}


def _oci_command(q):
    return ['oci', 'logging-search', 'search-logs',
            '--search-query', q['search'], '--limit', str(q['limit'])]


def _ibm_detect(sig):
    c = 2 if sig.get('provider_ibm') else 0
    if _cli('ibmcloud'):
        c += 1
    if _env_any('IBMCLOUD_API_KEY'):
        c += 1
    return min(c, 3)


def _ibm_build(svc, since, limit, query):
    inst = svc.get('ibm_instance')
    if not inst:
        return None
    return {'backend': 'ibm-log-analysis', 'instance': inst,
            'filter': query or svc.get('name'), 'since': since, 'limit': limit}


def _ibm_command(q):
    return ['ibmcloud', 'logging', 'tail', '--instance', q['instance'],
            '--query', q.get('filter') or '', '--limit', str(q['limit'])]


def _alibaba_detect(sig):
    c = 2 if sig.get('provider_alibaba') else 0
    if _cli('aliyun'):
        c += 1
    if _env_any('ALIBABA_CLOUD_ACCESS_KEY_ID', 'ALICLOUD_ACCESS_KEY'):
        c += 1
    return min(c, 3)


def _alibaba_build(svc, since, limit, query):
    project = svc.get('sls_project')
    logstore = svc.get('sls_logstore')
    if not (project and logstore):
        return None
    return {'backend': 'alibaba-sls', 'project': project, 'logstore': logstore,
            'query': query or '*', 'since': since, 'limit': limit}


def _alibaba_command(q):
    return ['aliyun', 'sls', 'GetLogs', '--project', q['project'],
            '--logstore', q['logstore'], '--query', q['query'],
            '--line', str(q['limit'])]


def _do_detect(sig):
    c = 2 if sig.get('provider_digitalocean') else 0
    if _cli('doctl'):
        c += 1
    if _env_any('DIGITALOCEAN_ACCESS_TOKEN'):
        c += 1
    return min(c, 3)


def _do_build(svc, since, limit, query):
    app = svc.get('do_app_id') or svc.get('name')
    if not app:
        return None
    return {'backend': 'digitalocean', 'app': app, 'component': svc.get('name'),
            'since': since, 'limit': limit, 'filter': query}


def _do_command(q):
    argv = ['doctl', 'apps', 'logs', q['app'], '--type', 'run', '--tail', str(q['limit'])]
    if q.get('component'):
        argv += ['--component', q['component']]
    return argv


def _scaleway_detect(sig):
    c = 2 if sig.get('provider_scaleway') else 0
    if _cli('scw'):
        c += 1
    return min(c, 3)


def _scaleway_build(svc, since, limit, query):
    if not svc.get('name'):
        return None
    return {'backend': 'scaleway', 'name': svc['name'], 'since': since,
            'limit': limit, 'filter': query}


def _scaleway_command(q):
    return ['scw', 'cockpit', 'logs', 'list', '--name', q['name'], '--limit', str(q['limit'])]


def _ovh_detect(sig):
    c = 2 if sig.get('provider_ovh') else 0
    if _env_any('OVH_APPLICATION_KEY'):
        c += 1
    return min(c, 3)


def _ovh_build(svc, since, limit, query):
    stream = svc.get('ovh_stream_id')
    if not stream:
        return None
    return {'backend': 'ovh-ldp', 'stream': stream, 'since': since,
            'limit': limit, 'filter': query}


def _ovh_command(q):
    # OVH Logs Data Platform is Graylog-compatible; queried over its API.
    return ['curl', '-sS', '-H', 'Authorization: Bearer ${OVH_LDP_TOKEN}',
            'https://${OVH_LDP_HOST}/api/search/universal/relative'
            '?query=%s&range=%s&limit=%d' % (q.get('filter') or '*', q['since'], q['limit'])]


# ---- vendor-neutral aggregators ----------------------------------------

def _loki_detect(sig):
    c = 0
    if sig.get('agent_loki') or sig.get('agent_promtail') or sig.get('agent_alloy'):
        c += 2
    if _env_any('LOKI_ADDR'):
        c += 1
    if _cli('logcli'):
        c += 1
    return min(c, 3)


def _loki_build(svc, since, limit, query):
    sel = svc.get('loki_selector')
    if not sel:
        app = svc.get('name')
        ns = svc.get('namespace')
        if not app:
            return None
        sel = '{app="%s"}' % app if not ns else '{namespace="%s", app="%s"}' % (ns, app)
    expr = sel if not query else '%s |= "%s"' % (sel, query)
    return {'backend': 'loki', 'expr': expr, 'since': since, 'limit': limit}


def _loki_command(q):
    return ['logcli', 'query', '--limit', str(q['limit']), '--since', q['since'],
            '--forward=false', q['expr']]


def _datadog_detect(sig):
    c = 0
    if sig.get('agent_datadog'):
        c += 2
    if _env_any('DD_API_KEY', 'DATADOG_API_KEY'):
        c += 1
    if _cli('datadog-ci') or _cli('dog'):
        c += 1
    return min(c, 3)


def _datadog_build(svc, since, limit, query):
    name = svc.get('name')
    if not name:
        return None
    q = 'service:%s' % name
    if svc.get('namespace'):
        q += ' kube_namespace:%s' % svc['namespace']
    q += ' status:error' if not query else ' "%s"' % query
    return {'backend': 'datadog', 'query': q, 'since': since, 'limit': limit}


def _datadog_command(q):
    return ['curl', '-sS', '-X', 'POST',
            'https://api.${DD_SITE:-datadoghq.com}/api/v2/logs/events/search',
            '-H', 'DD-API-KEY: ${DD_API_KEY}', '-H', 'DD-APPLICATION-KEY: ${DD_APP_KEY}',
            '-H', 'Content-Type: application/json',
            '-d', '{"filter":{"query":"%s","from":"now-%s"},"page":{"limit":%d}}'
            % (q['query'], q['since'], q['limit'])]


def _splunk_detect(sig):
    c = 0
    if sig.get('agent_splunk'):
        c += 2
    if _env_any('SPLUNK_HOST', 'SPLUNK_TOKEN'):
        c += 1
    return min(c, 3)


def _splunk_build(svc, since, limit, query):
    name = svc.get('name')
    if not name:
        return None
    idx = svc.get('splunk_index') or 'main'
    spl = 'search index=%s %s' % (idx, name)
    spl += ' error' if not query else ' "%s"' % query
    spl += ' | head %d' % limit
    return {'backend': 'splunk', 'spl': spl, 'since': since, 'limit': limit}


def _splunk_command(q):
    return ['curl', '-sS', '-u', '${SPLUNK_USER}:${SPLUNK_PASSWORD}',
            'https://${SPLUNK_HOST}:8089/services/search/jobs/export',
            '-d', 'search=%s' % q['spl'], '-d', 'output_mode=raw',
            '-d', 'earliest_time=-%s' % q['since']]


def _elastic_detect(sig):
    c = 0
    # Fluent Bit / Fluentd are shippers, not stores; they say nothing about Elastic.
    if sig.get('agent_elastic'):
        c += 2
    if _env_any('ELASTICSEARCH_URL', 'ES_URL', 'ELASTIC_CLOUD_ID'):
        c += 1
    return min(c, 3)


def _elastic_build(svc, since, limit, query):
    name = svc.get('name')
    if not name:
        return None
    idx = svc.get('es_index') or 'logs-*'
    term = query or 'error'
    return {'backend': 'elastic', 'index': idx,
            'q': '%s AND %s' % (name, term), 'since': since, 'limit': limit}


def _elastic_command(q):
    return ['curl', '-sS', '${ELASTICSEARCH_URL}/%s/_search' % q['index'],
            '-H', 'Content-Type: application/json',
            '-d', '{"size":%d,"sort":[{"@timestamp":"desc"}],'
                  '"query":{"bool":{"must":[{"query_string":{"query":"%s"}}],'
                  '"filter":[{"range":{"@timestamp":{"gte":"now-%s"}}}]}}}'
                  % (q['limit'], q['q'], q['since'])]


def _newrelic_detect(sig):
    c = 2 if sig.get('agent_newrelic') else 0
    if _env_any('NEW_RELIC_API_KEY', 'NEW_RELIC_LICENSE_KEY'):
        c += 1
    return min(c, 3)


def _newrelic_build(svc, since, limit, query):
    name = svc.get('name')
    if not name:
        return None
    nrql = "SELECT message FROM Log WHERE service.name = '%s'" % name
    if query:
        nrql += " AND message LIKE '%%%s%%'" % query
    nrql += " SINCE %s AGO LIMIT %d" % (since, limit)
    return {'backend': 'new-relic', 'nrql': nrql, 'since': since, 'limit': limit}


def _newrelic_command(q):
    return ['curl', '-sS', 'https://api.newrelic.com/graphql',
            '-H', 'Api-Key: ${NEW_RELIC_API_KEY}',
            '-H', 'Content-Type: application/json',
            '-d', '{"query":"{actor{account(id:${NEW_RELIC_ACCOUNT_ID})'
                  '{nrql(query:\\"%s\\"){results}}}}"}' % q['nrql']]


def _honeycomb_detect(sig):
    c = 2 if sig.get('agent_honeycomb') else 0
    if _env_any('HONEYCOMB_API_KEY', 'HNY_API_KEY'):
        c += 1
    return min(c, 3)


def _honeycomb_build(svc, since, limit, query):
    name = svc.get('name')
    if not name:
        return None
    return {'backend': 'honeycomb', 'dataset': svc.get('hny_dataset') or name,
            'filter': query or 'error', 'since': since, 'limit': limit}


def _honeycomb_command(q):
    return ['curl', '-sS', 'https://api.honeycomb.io/1/events/%s' % q['dataset'],
            '-H', 'X-Honeycomb-Team: ${HONEYCOMB_API_KEY}']


def _otel_detect(sig):
    c = 2 if sig.get('agent_otel') else 0
    if _env_any('OTEL_EXPORTER_OTLP_ENDPOINT'):
        c += 1
    return min(c, 3)


def _otel_build(svc, since, limit, query):
    # OTel collector is a shipper, not a store. Report where it ships to.
    return {'backend': 'otel-collector', 'note': 'collector detected; destination backend unknown',
            'service': svc.get('name'), 'since': since, 'limit': limit, 'filter': query}


def _otel_command(q):
    return None


REGISTRY = [
    # key, label, kind, cloud, detect, build, command
    {'key': 'cloudwatch', 'label': 'AWS CloudWatch Logs', 'kind': 'native', 'cloud': 'aws',
     'detect': _aws_detect, 'build': _aws_build, 'command': _aws_command,
     'needs': ['log_group']},
    {'key': 'cloud-logging', 'label': 'GCP Cloud Logging', 'kind': 'native', 'cloud': 'gcp',
     'detect': _gcp_detect, 'build': _gcp_build, 'command': _gcp_command,
     'needs': []},
    {'key': 'azure-monitor', 'label': 'Azure Monitor Log Analytics', 'kind': 'native',
     'cloud': 'azure', 'detect': _azure_detect, 'build': _azure_build,
     'command': _azure_command, 'needs': ['azure_workspace_id']},
    {'key': 'oci-logging', 'label': 'Oracle Cloud Logging', 'kind': 'native', 'cloud': 'oci',
     'detect': _oci_detect, 'build': _oci_build, 'command': _oci_command,
     'needs': ['oci_compartment_id']},
    {'key': 'ibm-log-analysis', 'label': 'IBM Cloud Logs', 'kind': 'native', 'cloud': 'ibm',
     'detect': _ibm_detect, 'build': _ibm_build, 'command': _ibm_command,
     'needs': ['ibm_instance']},
    {'key': 'alibaba-sls', 'label': 'Alibaba Cloud SLS', 'kind': 'native', 'cloud': 'alibaba',
     'detect': _alibaba_detect, 'build': _alibaba_build, 'command': _alibaba_command,
     'needs': ['sls_project', 'sls_logstore']},
    {'key': 'digitalocean', 'label': 'DigitalOcean App Platform logs', 'kind': 'native',
     'cloud': 'digitalocean', 'detect': _do_detect, 'build': _do_build,
     'command': _do_command, 'needs': []},
    {'key': 'scaleway', 'label': 'Scaleway Cockpit', 'kind': 'native', 'cloud': 'scaleway',
     'detect': _scaleway_detect, 'build': _scaleway_build, 'command': _scaleway_command,
     'needs': []},
    {'key': 'ovh-ldp', 'label': 'OVH Logs Data Platform', 'kind': 'native', 'cloud': 'ovh',
     'detect': _ovh_detect, 'build': _ovh_build, 'command': _ovh_command,
     'needs': ['ovh_stream_id']},
    {'key': 'loki', 'label': 'Grafana Loki', 'kind': 'aggregator', 'cloud': None,
     'detect': _loki_detect, 'build': _loki_build, 'command': _loki_command, 'needs': []},
    {'key': 'datadog', 'label': 'Datadog Logs', 'kind': 'aggregator', 'cloud': None,
     'detect': _datadog_detect, 'build': _datadog_build, 'command': _datadog_command,
     'needs': []},
    {'key': 'splunk', 'label': 'Splunk', 'kind': 'aggregator', 'cloud': None,
     'detect': _splunk_detect, 'build': _splunk_build, 'command': _splunk_command, 'needs': []},
    {'key': 'elastic', 'label': 'Elasticsearch / OpenSearch', 'kind': 'aggregator', 'cloud': None,
     'detect': _elastic_detect, 'build': _elastic_build, 'command': _elastic_command,
     'needs': []},
    {'key': 'new-relic', 'label': 'New Relic Logs', 'kind': 'aggregator', 'cloud': None,
     'detect': _newrelic_detect, 'build': _newrelic_build, 'command': _newrelic_command,
     'needs': []},
    {'key': 'honeycomb', 'label': 'Honeycomb', 'kind': 'aggregator', 'cloud': None,
     'detect': _honeycomb_detect, 'build': _honeycomb_build, 'command': _honeycomb_command,
     'needs': []},
    {'key': 'otel-collector', 'label': 'OpenTelemetry collector', 'kind': 'aggregator',
     'cloud': None, 'detect': _otel_detect, 'build': _otel_build, 'command': _otel_command,
     'needs': []},
]

BY_KEY = {b['key']: b for b in REGISTRY}


def rank(signals, prefer=None):
    """Return backends sorted by confidence. Aggregators outrank natives at equal score."""
    scored = []
    for b in REGISTRY:
        c = b['detect'](signals)
        if prefer and b['key'] == prefer:
            c = 99
        if c > 0:
            bonus = 0.5 if b['kind'] == 'aggregator' else 0.0
            scored.append((c + bonus, c, b))
    scored.sort(key=lambda t: -t[0])
    return [(c, b) for _, c, b in scored]
