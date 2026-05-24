import json

from flask import Blueprint, get_flashed_messages, jsonify
from markupsafe import escape

from app import store
from app.ui import base_html

bp = Blueprint("index", __name__)


def _score_class(score: int) -> str:
    if score >= 80:
        return "score-good"
    if score >= 60:
        return "score-warn"
    return "score-bad"


def _aggregate_categories(reports) -> dict:
    agg: dict = {}
    for r in reports:
        for cat, n in (r.get("categories") or {}).items():
            agg[cat] = agg.get(cat, 0) + n
    return agg


def _flash_block(msgs_with_cats: list) -> str:
    if not msgs_with_cats:
        return ""
    parts = []
    for cat, msg in msgs_with_cats:
        css = "flash-ok" if cat == "ok" else "flash"
        parts.append(f'<div class="{css}">{escape(msg)}</div>')
    return "".join(parts)


def _overview_html(reports, flash_msgs=None) -> str:
    fb = _flash_block(flash_msgs or [])
    if not reports:
        body = fb + """
<div class="card">
  <div class="card-title">overview</div>
  <div class="empty-state">
    no reports loaded<br><br>
    <a href="/import" style="color: var(--accent); text-decoration: none;">import an XCCDF file →</a>
    &nbsp;&nbsp;or&nbsp;&nbsp;
    <a href="/network" style="color: var(--accent); text-decoration: none;">load from NFS/S3 →</a>
  </div>
</div>
"""
        return base_html("Overview — OpenSCAP Dashboard", body, active="index")

    cards = []
    for r in reports:
        rid = r.get("id", "")
        host = escape(r.get("hostname", "unknown"))
        date = escape(r.get("scan_date", "n/a"))
        score = int(r.get("score", 0))
        sc = _score_class(score)
        passes = (r.get("results") or {}).get("pass", 0)
        fails = (r.get("results") or {}).get("fail", 0)
        source = escape(r.get("source", ""))
        cards.append(f"""
<a class="report-card" href="/report/{escape(rid)}">
  <div class="rc-head">
    <div class="rc-host">{host}</div>
    <div class="rc-score {sc}">{score}%</div>
  </div>
  <div class="rc-meta">scanned: {date}</div>
  <div class="rc-stats">
    <span class="rc-pass">✓ {passes}</span>
    <span class="rc-fail">✗ {fails}</span>
  </div>
  <div class="rc-source">{source}</div>
</a>""")

    agg = _aggregate_categories(reports)
    agg_sorted = sorted(agg.items(), key=lambda kv: kv[1], reverse=True)
    cat_labels = [k for k, _ in agg_sorted]
    cat_values = [v for _, v in agg_sorted]

    body = fb + f"""
<div class="card" style="margin-bottom:16px;">
  <div class="card-title">monitored environments — {len(reports)}</div>
  <div class="cards-grid">
    {''.join(cards)}
  </div>
</div>

<div class="card">
  <div class="card-title">aggregate failures by category</div>
  <div style="position:relative;" id="agg-wrap">
    <canvas id="agg-chart" role="img" aria-label="Aggregate failures by category"></canvas>
  </div>
</div>

<style>
.cards-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px; }}
.report-card {{
  background: var(--surface2); border: 1px solid var(--border);
  border-radius: 8px; padding: 16px; text-decoration: none; color: var(--text);
  transition: border-color .15s, transform .15s;
  display: block;
}}
.report-card:hover {{ border-color: var(--accent); transform: translateY(-1px); }}
.rc-head {{ display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 6px; }}
.rc-host {{ font-family: var(--font-mono); font-size: 13px; font-weight: 500; word-break: break-all; }}
.rc-score {{ font-family: var(--font-mono); font-size: 22px; font-weight: 300; }}
.score-good {{ color: var(--pass); }}
.score-warn {{ color: var(--warn); }}
.score-bad  {{ color: var(--fail); }}
.rc-meta {{ font-family: var(--font-mono); font-size: 11px; color: var(--muted); margin-bottom: 10px; }}
.rc-stats {{ display: flex; gap: 14px; font-family: var(--font-mono); font-size: 12px; }}
.rc-pass {{ color: var(--pass); }}
.rc-fail {{ color: var(--fail); }}
.rc-source {{ font-family: var(--font-mono); font-size: 10px; color: var(--muted); margin-top: 8px; word-break: break-all; }}
</style>

<script>
const CAT_LABELS = {json.dumps(cat_labels)};
const CAT_VALUES = {json.dumps(cat_values)};
const barH = Math.max(160, CAT_LABELS.length * 36 + 40);
document.getElementById('agg-wrap').style.height = barH + 'px';
new Chart(document.getElementById('agg-chart'), {{
  type: 'bar',
  data: {{ labels: CAT_LABELS, datasets: [{{ data: CAT_VALUES, backgroundColor: '#ef4444', borderRadius: 3, borderSkipped: false }}] }},
  options: {{ responsive: true, maintainAspectRatio: false, indexAxis: 'y',
    plugins: {{ legend: {{ display: false }}, tooltip: {{ callbacks: {{ label: c => ` ${{c.parsed}} failures` }} }} }},
    scales: {{
      x: {{ grid: {{ color: 'rgba(255,255,255,0.04)' }}, ticks: {{ color: '#6b7280', font: {{ family: "'IBM Plex Mono'" }} }} }},
      y: {{ grid: {{ display: false }}, ticks: {{ color: '#9ca3af', font: {{ family: "'IBM Plex Mono'", size: 11 }} }} }}
    }}
  }}
}});
</script>
"""
    return base_html("Overview — OpenSCAP Dashboard", body, active="index")


@bp.route("/", methods=["GET"])
def overview():
    msgs = get_flashed_messages(with_categories=True)
    return _overview_html(store.all(), flash_msgs=msgs)


@bp.route("/api/reports", methods=["GET"])
def api_reports():
    out = []
    for r in store.all():
        out.append({
            "id": r.get("id"),
            "hostname": r.get("hostname"),
            "scan_date": r.get("scan_date"),
            "score": r.get("score"),
            "pass": (r.get("results") or {}).get("pass", 0),
            "fail": (r.get("results") or {}).get("fail", 0),
            "source": r.get("source"),
            "loaded_at": r.get("loaded_at"),
        })
    return jsonify(out)
