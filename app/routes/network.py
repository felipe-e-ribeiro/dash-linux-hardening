import os
from pathlib import Path

from flask import Blueprint, flash, get_flashed_messages, redirect, request, url_for
from markupsafe import escape

from app import sources, store
from app.ui import base_html

bp = Blueprint("network", __name__)


def _list_nfs_xml(mount_path: str) -> list:
    if not mount_path:
        return []
    p = Path(mount_path)
    if not p.exists() or not p.is_dir():
        return []
    return sorted([f.name for f in p.glob("*.xml") if f.is_file()])


def _flash_block(msgs_with_cats: list) -> str:
    if not msgs_with_cats:
        return ""
    parts = []
    for cat, msg in msgs_with_cats:
        css = "flash-ok" if cat == "ok" else "flash"
        parts.append(f'<div class="{css}">{escape(msg)}</div>')
    return "".join(parts)


def _network_html(flash_msgs: list = None) -> str:
    nfs_default = os.environ.get("NFS_MOUNT_PATH", "")
    aws_region_default = os.environ.get("AWS_DEFAULT_REGION", "")
    xml_files = _list_nfs_xml(nfs_default)

    flash_block = _flash_block(flash_msgs or [])

    file_options = "".join(
        f'<option value="{escape(name)}">{escape(name)}</option>' for name in xml_files
    )
    file_picker = (
        f'<select name="filename" class="net-input net-select-multi" multiple>{file_options}</select>'
        if xml_files
        else '<input type="text" name="filename" class="net-input" placeholder="results.xml" />'
    )
    nfs_hint = (
        f'.xml files listed from {escape(nfs_default)} — hold Ctrl/Cmd to select multiple'
        if xml_files
        else 'path not mounted yet — type the filename manually'
    )

    body = f"""
{flash_block}
<div class="card">
  <div class="card-title">load from network source</div>

  <div class="tabs">
    <button type="button" class="tab active" data-tab="nfs">NFS</button>
    <button type="button" class="tab" data-tab="s3">S3</button>
  </div>

  <div class="tab-panel" id="panel-nfs">
    <form method="post" action="/network/load">
      <input type="hidden" name="source" value="nfs" />
      <label class="net-label">mount path</label>
      <input type="text" name="mount_path" class="net-input" value="{escape(nfs_default)}" placeholder="/mnt/nfs" required />
      <p class="net-hint">pre-filled from <code>NFS_MOUNT_PATH</code></p>

      <label class="net-label">XML files</label>
      {file_picker}
      <p class="net-hint">{nfs_hint}</p>

      <button type="submit" class="net-submit">Load NFS</button>
    </form>
  </div>

  <div class="tab-panel" id="panel-s3" style="display:none">
    <form method="post" action="/network/load">
      <input type="hidden" name="source" value="s3" />
      <label class="net-label">bucket</label>
      <input type="text" name="bucket" class="net-input" placeholder="my-compliance-bucket" required />

      <label class="net-label">keys (one per line)</label>
      <textarea name="key" class="net-input net-textarea" rows="4" placeholder="reports/server-01.xml&#10;reports/server-02.xml" required></textarea>

      <label class="net-label">region</label>
      <input type="text" name="region" class="net-input" value="{escape(aws_region_default)}" placeholder="us-east-1" />

      <p class="net-hint">
        credentials are read from <code>AWS_ACCESS_KEY_ID</code> / <code>AWS_SECRET_ACCESS_KEY</code>
        (or an attached IAM role) — never type credentials in this form
      </p>

      <button type="submit" class="net-submit">Load S3</button>
    </form>
  </div>
</div>

<style>
.tabs {{ display: flex; gap: 6px; margin-bottom: 18px; }}
.tab {{
  font-family: var(--font-mono); font-size: 12px; padding: 6px 14px;
  border-radius: 4px; border: 1px solid var(--border2);
  background: transparent; color: var(--muted); cursor: pointer; transition: all .15s;
}}
.tab:hover {{ border-color: var(--accent); color: var(--text); }}
.tab.active {{ background: rgba(0,212,255,0.1); border-color: var(--accent); color: var(--accent); }}

.net-label {{ display: block; font-family: var(--font-mono); font-size: 10px; color: var(--muted); text-transform: uppercase; letter-spacing: .08em; margin-top: 12px; margin-bottom: 4px; }}
.net-input {{
  width: 100%; background: var(--surface2); border: 1px solid var(--border2);
  color: var(--text); padding: 8px 10px; border-radius: 4px;
  font-family: var(--font-mono); font-size: 12px; box-sizing: border-box;
}}
.net-input:focus {{ outline: none; border-color: var(--accent); }}
.net-select-multi {{ min-height: 100px; padding: 4px; }}
.net-select-multi option {{ padding: 4px 6px; border-radius: 3px; }}
.net-textarea {{ resize: vertical; }}
.net-hint {{ font-family: var(--font-mono); font-size: 10px; color: var(--muted); margin-top: 4px; }}
.net-hint code {{ background: var(--surface2); padding: 1px 4px; border-radius: 3px; }}

.net-submit {{
  margin-top: 18px;
  font-family: var(--font-mono); font-size: 12px;
  background: rgba(0,212,255,0.1); border: 1px solid var(--accent);
  color: var(--accent); padding: 8px 18px; border-radius: 4px; cursor: pointer;
}}
.net-submit:hover {{ background: rgba(0,212,255,0.2); }}
</style>

<script>
document.querySelectorAll('.tab').forEach(t => {{
  t.addEventListener('click', () => {{
    document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
    t.classList.add('active');
    const target = t.dataset.tab;
    document.getElementById('panel-nfs').style.display = (target === 'nfs') ? 'block' : 'none';
    document.getElementById('panel-s3').style.display = (target === 's3') ? 'block' : 'none';
  }});
}});
</script>
"""
    return base_html("Network — OpenSCAP Dashboard", body, active="network")


@bp.route("/network", methods=["GET"])
def network_form():
    msgs = get_flashed_messages(with_categories=True)
    return _network_html(msgs)


@bp.route("/network/load", methods=["POST"])
def network_load():
    source = (request.form.get("source") or "").lower()

    if source == "nfs":
        mount_path = (request.form.get("mount_path") or "").strip()
        filenames = [f.strip() for f in request.form.getlist("filename") if f.strip()]
        if not mount_path or not filenames:
            flash("Mount path and at least one filename are required.", "error")
            return redirect(url_for("network.network_form"))
        if not Path(mount_path).exists():
            flash(f"Mount path does not exist or is not mounted: {mount_path}", "error")
            return redirect(url_for("network.network_form"))

        loaded, errors = 0, []
        for filename in filenames:
            try:
                report = sources.load_nfs(mount_path, filename)
                store.add(report)
                loaded += 1
            except Exception as e:
                errors.append(f"{filename}: {e}")

        for err in errors:
            flash(f"Failed: {err}", "error")
        if loaded:
            flash(f"{loaded} report{'s' if loaded > 1 else ''} loaded from NFS.", "ok")
        if errors:
            return redirect(url_for("network.network_form"))
        return redirect(url_for("index.overview"))

    if source == "s3":
        bucket = (request.form.get("bucket") or "").strip()
        keys_raw = (request.form.get("key") or "").strip()
        keys = [k.strip() for k in keys_raw.splitlines() if k.strip()]
        region = (request.form.get("region") or "").strip()
        if not bucket or not keys:
            flash("Bucket and at least one key are required.", "error")
            return redirect(url_for("network.network_form"))

        loaded, errors = 0, []
        for key in keys:
            try:
                report = sources.load_s3(bucket, key, region)
                store.add(report)
                loaded += 1
            except Exception as e:
                from botocore.exceptions import ClientError, NoCredentialsError
                if isinstance(e, NoCredentialsError):
                    errors.append(f"{key}: AWS credentials not configured")
                elif isinstance(e, ClientError):
                    code = e.response.get("Error", {}).get("Code", "")
                    if code in {"NoSuchKey", "404"}:
                        errors.append(f"{key}: object not found in s3://{bucket}/")
                    else:
                        errors.append(f"{key}: {e}")
                else:
                    errors.append(f"{key}: {e}")

        for err in errors:
            flash(f"Failed: {err}", "error")
        if loaded:
            flash(f"{loaded} report{'s' if loaded > 1 else ''} loaded from S3.", "ok")
        if errors:
            return redirect(url_for("network.network_form"))
        return redirect(url_for("index.overview"))

    flash("Unknown source.", "error")
    return redirect(url_for("network.network_form"))
