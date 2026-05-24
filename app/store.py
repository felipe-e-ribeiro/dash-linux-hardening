from threading import RLock

_reports: dict = {}
_lock = RLock()


def _report_id(report) -> str:
    host = (report.get('hostname') or 'unknown').strip()
    date = (report.get('scan_date') or '').strip()
    raw = f"{host}_{date}" if date else host
    return raw.replace(' ', '_')


def add(report) -> str:
    rid = _report_id(report)
    report['id'] = rid
    with _lock:
        _reports[rid] = report
    return rid


def get(rid):
    with _lock:
        return _reports.get(rid)


def all() -> list:
    with _lock:
        return list(_reports.values())


def clear() -> None:
    with _lock:
        _reports.clear()
