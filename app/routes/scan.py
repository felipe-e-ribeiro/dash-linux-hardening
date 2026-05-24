import threading

from flask import Blueprint, abort, jsonify, redirect, request, url_for
from markupsafe import escape

from app import scan_state, scanner, scheduler
from app import targets as target_registry
from app import ssg_resolver
from app.ui import base_html

bp = Blueprint("scan", __name__)


# ---------------------------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------------------------

def _scan_html(flash_msgs: list = None) -> str:
    pub_key = scanner.get_public_key()
    all_targets = target_registry.all_targets()

    flash_block = ""
    if flash_msgs:
        for cat, msg in flash_msgs:
            css = "flash-ok" if cat == "ok" else "flash"
            flash_block += f'<div class="{css}">{escape(msg)}</div>'

    target_cards = ""
    for t in all_targets:
        tid = t["id"]
        host = escape(t["host"])
        port = t.get("port", 22)
        user = escape(t["username"])
        auth = escape(t.get("auth_type", "key"))
        profile = escape(t.get("profile") or "—")
        schedule = escape(t.get("schedule") or "manual only")
        status = t.get("last_status") or "never"
        last_scan = t.get("last_scan") or "—"
        last_error = escape(t.get("last_error") or "")
        os_info = ""
        if t.get("os_id"):
            os_info = f'<div class="tgt-meta">{escape(t["os_id"])} {escape(t.get("os_version",""))}</div>'

        history_rows = ""
        for h in (t.get("history") or []):
            h_status = h.get("status", "")
            h_css = "pass" if h_status == "success" else ("fail" if h_status == "failed" else "muted")
            h_rid = ""
            if h.get("report_id"):
                h_rid = f' <a href="/report/{escape(h["report_id"])}" style="color:var(--accent);font-size:10px;">→ report</a>'
            history_rows += f"""
<tr>
  <td class="mono small">{escape(h.get("ts",""))}</td>
  <td><span style="color:var(--{h_css})">{escape(h_status)}</span>{h_rid}</td>
  <td class="mono small" style="color:var(--fail);font-size:10px;">{escape(h.get("error") or "")}</td>
</tr>"""

        status_color = "pass" if status == "success" else ("fail" if status == "failed" else "muted")
        target_cards += f"""
<div class="card tgt-card" id="tgt-{tid}">
  <div class="tgt-head">
    <div>
      <div class="tgt-host">{user}@{host}:{port}</div>
      {os_info}
      <div class="tgt-meta">auth: {auth} · profile: {profile} · schedule: {schedule}</div>
    </div>
    <div class="tgt-actions">
      <span class="badge badge-{'pass' if status=='success' else ('fail' if status=='failed' else 'cat')}"
            id="status-badge-{tid}">{status}</span>
      <button class="scan-now-btn" onclick="triggerScan('{tid}')">▶ Scan Now</button>
      <form method="post" action="/scan/targets/{tid}/delete" style="display:inline"
            onsubmit="return confirm('Remove target {host}?')">
        <button class="del-btn">✕</button>
      </form>
    </div>
  </div>
  <div class="tgt-details">
    <div class="mono small" style="color:var(--muted)">last scan: {last_scan}</div>
    {f'<div class="mono small" style="color:var(--fail)">{last_error}</div>' if last_error else ''}
  </div>
  {f"""<div style="margin-top:12px;overflow-x:auto;">
    <table class="rules-table" style="font-size:11px;">
      <thead><tr><th>Timestamp</th><th>Status</th><th>Error</th></tr></thead>
      <tbody>{history_rows}</tbody>
    </table></div>""" if history_rows else ''}
</div>"""

    body = f"""
{flash_block}

<div class="card" style="margin-bottom:16px;">
  <div class="card-title">SSH public key — add to target servers</div>
  <div class="pubkey-wrap">
    <code class="pubkey-text" id="pubkey">{escape(pub_key)}</code>
    <button class="filter-btn" onclick="navigator.clipboard.writeText(document.getElementById('pubkey').textContent).then(()=>this.textContent='Copied!').catch(()=>{{}})" style="flex-shrink:0">Copy</button>
  </div>
  <p class="mono small" style="color:var(--muted);margin-top:8px;">
    Run on each target: <code style="background:var(--surface2);padding:2px 6px;border-radius:3px;">echo "{escape(pub_key)}" >> ~/.ssh/authorized_keys</code>
  </p>
</div>

<div class="card" style="margin-bottom:16px;">
  <div class="card-title">add target</div>
  <form method="post" action="/scan/targets" id="add-target-form">
    <div class="tgt-form-grid">
      <div>
        <label class="rh-label">host / IP</label>
        <input type="text" name="host" class="net-input" placeholder="192.168.1.100" required />
      </div>
      <div>
        <label class="rh-label">SSH port</label>
        <input type="number" name="port" class="net-input" value="22" min="1" max="65535" />
      </div>
      <div>
        <label class="rh-label">username</label>
        <input type="text" name="username" class="net-input" placeholder="root" required />
      </div>
      <div>
        <label class="rh-label">auth type</label>
        <select name="auth_type" class="net-input" onchange="togglePassword(this.value)">
          <option value="key">SSH Key (recommended)</option>
          <option value="password">Password</option>
        </select>
      </div>
    </div>
    <div id="password-field" style="display:none;margin-top:8px;">
      <label class="rh-label">password</label>
      <input type="password" name="password" class="net-input" placeholder="SSH password" autocomplete="off" />
    </div>
    <div id="custom-profile-field" style="display:none;margin-top:8px;">
      <label class="rh-label">custom profile ID</label>
      <input type="text" name="profile_custom" id="profile-custom-input" class="net-input"
             placeholder="xccdf_org.ssgproject.content_profile_cis" />
    </div>
    <div class="tgt-form-grid" style="margin-top:8px;">
      <div>
        <label class="rh-label">compliance profile</label>
        <select name="profile" id="profile-select" class="net-input" onchange="onProfileChange(this.value)">
          {''.join(f'<option value="{lbl}">{lbl}</option>' for lbl, _ in ssg_resolver.PROFILE_CATALOG)}
          <option value="__custom__">Custom (enter ID manually)…</option>
        </select>
      </div>
      <div>
        <label class="rh-label">schedule (cron or hours)</label>
        <input type="text" name="schedule" class="net-input" placeholder="24  or  0 2 * * *" />
      </div>
    </div>
    <button type="submit" class="net-submit" style="margin-top:12px;">Add Target</button>
  </form>
</div>

<div class="card-title" style="padding:0 0 12px 0;">targets ({len(all_targets)})</div>
{target_cards if target_cards else '<div class="empty-state">No targets configured. Add one above.</div>'}

<style>
.pubkey-wrap {{ display:flex; gap:10px; align-items:flex-start; }}
.pubkey-text {{ font-size:10px; word-break:break-all; background:var(--surface2); padding:8px 10px; border-radius:4px; flex:1; font-family:var(--font-mono); color:var(--muted); }}
.tgt-card {{ margin-bottom:12px; }}
.tgt-head {{ display:flex; justify-content:space-between; align-items:flex-start; gap:12px; flex-wrap:wrap; }}
.tgt-host {{ font-family:var(--font-mono); font-size:14px; font-weight:500; color:var(--text); }}
.tgt-meta {{ font-family:var(--font-mono); font-size:10px; color:var(--muted); margin-top:3px; }}
.tgt-actions {{ display:flex; gap:8px; align-items:center; flex-wrap:wrap; }}
.tgt-details {{ margin-top:8px; }}
.scan-now-btn {{
  font-family:var(--font-mono); font-size:11px; padding:4px 12px; border-radius:4px;
  border:1px solid var(--accent); background:rgba(0,212,255,0.08); color:var(--accent);
  cursor:pointer; transition:all .15s;
}}
.scan-now-btn:hover {{ background:rgba(0,212,255,0.18); }}
.scan-now-btn:disabled {{ opacity:.4; cursor:not-allowed; }}
.del-btn {{
  font-family:var(--font-mono); font-size:11px; padding:4px 8px; border-radius:4px;
  border:1px solid rgba(239,68,68,0.3); background:rgba(239,68,68,0.05); color:#fca5a5;
  cursor:pointer;
}}
.tgt-form-grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(200px,1fr)); gap:12px; }}
.mono {{ font-family:var(--font-mono); }}
.small {{ font-size:11px; }}
</style>

<script>
function togglePassword(val) {{
  document.getElementById('password-field').style.display = val === 'password' ? 'block' : 'none';
}}

function onProfileChange(val) {{
  const customDiv = document.getElementById('custom-profile-field');
  const customInput = document.getElementById('profile-custom-input');
  if (val === '__custom__') {{
    customDiv.style.display = 'block';
    customInput.required = true;
  }} else {{
    customDiv.style.display = 'none';
    customInput.required = false;
    customInput.value = '';
  }}
}}

// On submit: if custom profile selected, copy custom input value into the select
document.getElementById('add-target-form').addEventListener('submit', function(e) {{
  const sel = document.getElementById('profile-select');
  const customInput = document.getElementById('profile-custom-input');
  if (sel.value === '__custom__') {{
    if (!customInput.value.trim()) {{
      e.preventDefault();
      customInput.focus();
      return;
    }}
    sel.value = customInput.value.trim();
  }}
}});

function triggerScan(tid) {{
  const btn = document.querySelector(`#tgt-${{tid}} .scan-now-btn`);
  if (btn) {{ btn.disabled = true; btn.textContent = '⏳ Running…'; }}
  const badge = document.getElementById('status-badge-' + tid);
  if (badge) badge.textContent = 'running';

  fetch('/scan/targets/' + tid + '/run', {{method:'POST', headers:{{'Content-Type':'application/json'}}}})
    .then(r => r.json())
    .then(d => {{
      if (d.status === 'busy') {{
        if (btn) btn.textContent = '▶ Scan Now';
        if (btn) btn.disabled = false;
        alert('Scan already running for this target.');
        return;
      }}
      pollStatus(tid, btn, badge);
    }})
    .catch(() => {{
      if (btn) {{ btn.disabled = false; btn.textContent = '▶ Scan Now'; }}
    }});
}}

function pollStatus(tid, btn, badge) {{
  const iv = setInterval(() => {{
    fetch('/scan/targets/' + tid + '/status')
      .then(r => r.json())
      .then(d => {{
        if (d.status === 'running') return;
        clearInterval(iv);
        if (btn) {{ btn.disabled = false; btn.textContent = '▶ Scan Now'; }}
        if (badge) {{
          badge.textContent = d.status;
          badge.className = 'badge badge-' + (d.status === 'success' ? 'pass' : 'fail');
        }}
        if (d.status === 'success' && d.report_id) {{
          setTimeout(() => window.location.reload(), 800);
        }}
      }})
      .catch(() => clearInterval(iv));
  }}, 2000);
}}
</script>
"""
    return base_html("Scan — OpenSCAP Dashboard", body, active="scan")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@bp.route("/scan", methods=["GET"])
def scan_index():
    return _scan_html()


@bp.route("/scan/targets", methods=["POST"])
def add_target():
    data = request.form.to_dict()
    try:
        t = target_registry.add_target(data)
        if t.get("schedule"):
            scheduler.register_job(t)
        return redirect(url_for("scan.scan_index"))
    except ValueError as e:
        return _scan_html([("error", str(e))]), 400


@bp.route("/scan/targets/<tid>/edit", methods=["POST"])
def edit_target(tid: str):
    data = request.form.to_dict()
    try:
        t = target_registry.update_target(tid, data)
        scheduler.remove_job(tid)
        if t.get("schedule"):
            scheduler.register_job(t)
        return redirect(url_for("scan.scan_index"))
    except KeyError:
        abort(404)


@bp.route("/scan/targets/<tid>/delete", methods=["POST"])
def delete_target(tid: str):
    scheduler.remove_job(tid)
    target_registry.remove_target(tid)
    return redirect(url_for("scan.scan_index"))


@bp.route("/scan/targets/<tid>/run", methods=["POST"])
def run_scan(tid: str):
    if target_registry.get_target(tid) is None:
        return jsonify({"status": "error", "message": "Target not found"}), 404
    if scan_state.is_running(tid):
        return jsonify({"status": "busy", "message": "Scan already running"}), 409
    t = threading.Thread(
        target=scanner.run_scan_for_target, args=(tid,), daemon=True
    )
    t.start()
    return jsonify({"status": "started"})


@bp.route("/scan/targets/<tid>/status", methods=["GET"])
def scan_status(tid: str):
    if target_registry.get_target(tid) is None:
        abort(404)
    return jsonify(scan_state.get_state(tid))


@bp.route("/scan/targets/<tid>/profiles", methods=["GET"])
def list_profiles(tid: str):
    t = target_registry.get_target(tid)
    if t is None:
        abort(404)
    os_id = t.get("os_id")
    os_version = t.get("os_version")
    if not os_id or not os_version:
        return jsonify({"error": "OS not yet detected. Run a scan first."}), 400
    try:
        from pathlib import Path as P
        from app.scanner import _SSG_CACHE_DIR
        xccdf = ssg_resolver.resolve(os_id, os_version, _SSG_CACHE_DIR)
        profiles = ssg_resolver.list_profiles(xccdf)
        return jsonify(profiles)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
