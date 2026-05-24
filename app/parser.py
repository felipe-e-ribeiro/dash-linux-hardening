import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

NS = {
    'xccdf': 'http://checklists.nist.gov/xccdf/1.2',
    'xccdf11': 'http://checklists.nist.gov/xccdf/1.1',
}


def _element_text(el):
    if el is None:
        return ''
    return ' '.join(''.join(el.itertext()).split())


def parse_xccdf(filepath, source=""):
    tree = ET.parse(filepath)
    root = tree.getroot()

    tag = root.tag
    if 'xccdf/1.2' in tag:
        ns = NS['xccdf']
    else:
        ns = NS['xccdf11']

    def q(name):
        return f'{{{ns}}}{name}'

    rule_index = {}
    for rule_el in root.findall(f'.//{q("Rule")}'):
        rid = rule_el.get('id', '')
        if not rid:
            continue
        fix_bash, fix_ansible = '', ''
        for fix_el in rule_el.findall(q('fix')):
            system = fix_el.get('system', '')
            text = ''.join(fix_el.itertext()).strip()
            if 'script:sh' in system:
                fix_bash = text
            elif 'ansible' in system:
                fix_ansible = text
        rule_index[rid] = {
            'title': _element_text(rule_el.find(q('title'))),
            'description': _element_text(rule_el.find(q('description'))),
            'fix_bash': fix_bash,
            'fix_ansible': fix_ansible,
        }

    results = {'pass': 0, 'fail': 0, 'notchecked': 0, 'notapplicable': 0,
               'error': 0, 'unknown': 0}
    rules = []
    categories = {}

    benchmark_title = 'OpenSCAP Scan'
    title_el = root.find(f'.//{q("title")}')
    if title_el is not None and title_el.text:
        benchmark_title = title_el.text

    test_results = root.findall(f'.//{q("TestResult")}')
    hostname = 'unknown'
    scan_date = ''
    profile_id = ''
    score_val = None
    score_max = None

    if test_results:
        tr = test_results[-1]
        target = tr.find(f'{q("target")}')
        if target is not None and target.text:
            hostname = target.text.strip()
        scan_date = tr.get('start-time', tr.get('end-time', ''))[:16].replace('T', ' ')

        profile_el = tr.find(f'{q("profile")}')
        if profile_el is not None:
            profile_id = profile_el.get('idref', '')

        score_el = tr.find(f'{q("score")}')
        if score_el is not None:
            try:
                score_val = float(score_el.text or 0)
                score_max = float(score_el.get('maximum', 100))
            except Exception:
                pass

        for rr in tr.findall(f'{q("rule-result")}'):
            rule_id = rr.get('idref', '')
            severity = rr.get('severity', 'unknown')
            result_el = rr.find(f'{q("result")}')
            result = result_el.text.strip() if result_el is not None else 'unknown'

            result_key = result if result in results else 'unknown'
            results[result_key] += 1

            if result == 'fail':
                meta = rule_index.get(rule_id, {})
                title = meta.get('title') or rule_id.split('.')[-1].replace('_', ' ').strip()
                if len(title) > 120:
                    title = title[:117] + '...'
                description = meta.get('description', '')
                if len(description) > 600:
                    description = description[:597] + '...'

                cat = 'Other'
                rid_lower = rule_id.lower()
                if any(x in rid_lower for x in ['ssh', 'password', 'account', 'user', 'login', 'pam', 'sudo', 'usb']):
                    cat = 'Access Control'
                elif any(x in rid_lower for x in ['audit', 'rsyslog', 'log', 'syslog']):
                    cat = 'Audit & Logging'
                elif any(x in rid_lower for x in ['firewall', 'network', 'ipv6', 'tcp', 'iptables', 'nftables']):
                    cat = 'Network'
                elif any(x in rid_lower for x in ['crypto', 'tls', 'ssl', 'cipher', 'mac', 'fips', 'encrypt']):
                    cat = 'Cryptography'
                elif any(x in rid_lower for x in ['package', 'software', 'rpm', 'dnf', 'yum', 'aide']):
                    cat = 'Software'
                elif any(x in rid_lower for x in ['kernel', 'sysctl', 'boot', 'grub']):
                    cat = 'Kernel & Boot'
                elif any(x in rid_lower for x in ['mount', 'file', 'perm', 'dir', 'tmp', 'var']):
                    cat = 'Filesystem'

                categories[cat] = categories.get(cat, 0) + 1

                sev_map = {
                    'high': 'high', 'medium': 'medium', 'low': 'low',
                    'critical': 'high', 'info': 'low', 'unknown': 'medium'
                }
                rules.append({
                    'id': rule_id,
                    'title': title,
                    'description': description,
                    'severity': sev_map.get(severity, 'medium'),
                    'category': cat,
                    'result': result,
                    'fix_bash': meta.get('fix_bash', ''),
                    'fix_ansible': meta.get('fix_ansible', ''),
                })

    total = results['pass'] + results['fail']
    if score_val is not None and score_max:
        score_pct = round((score_val / score_max) * 100)
    elif total > 0:
        score_pct = round((results['pass'] / total) * 100)
    else:
        score_pct = 0

    fail_total = len(rules)

    return {
        'hostname': hostname,
        'scan_date': scan_date,
        'profile': profile_id,
        'benchmark': benchmark_title,
        'score': score_pct,
        'results': results,
        'total': sum(results.values()),
        'rules': rules[:200],
        'fail_total': fail_total,
        'categories': categories,
        'filename': Path(filepath).name,
        'source': source,
        'loaded_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
    }
