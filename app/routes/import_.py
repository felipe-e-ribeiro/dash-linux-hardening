from flask import Blueprint, flash, get_flashed_messages, redirect, request, url_for

from app import sources, store
from app.ui import base_html

bp = Blueprint("import_", __name__)


def _flash_block(msgs_with_cats: list) -> str:
    if not msgs_with_cats:
        return ""
    parts = []
    for cat, msg in msgs_with_cats:
        css = "flash-ok" if cat == "ok" else "flash"
        parts.append(f'<div class="{css}">{msg}</div>')
    return "".join(parts)


def _import_html(flash_msgs: list = None) -> str:
    flash_block = _flash_block(flash_msgs or [])
    body = f"""
{flash_block}
<div class="card" style="margin-bottom:16px;">
  <div class="card-title">import XCCDF reports</div>
  <form id="upload-form" method="post" action="/import" enctype="multipart/form-data">
    <div class="upload-area" id="upload-area"
         onclick="document.getElementById('xml-input').click()"
         ondragover="event.preventDefault(); this.style.borderColor='var(--accent)'"
         ondragleave="this.style.borderColor=''"
         ondrop="handleDrop(event)">
      <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
      </svg>
      <div><strong>Drop XCCDF files here</strong> or click to choose — multiple files supported</div>
      <p>Files are processed locally; nothing is sent over the internet.</p>
      <input type="file" id="xml-input" name="xml" accept=".xml" multiple style="display:none" onchange="showAndSubmit(this)">
      <p id="picked" style="margin-top:8px; color: var(--accent); display:none;"></p>
    </div>
  </form>
</div>
<style>
.upload-area {{
  border: 1px dashed var(--border2); border-radius: 8px;
  padding: 32px; text-align: center; cursor: pointer;
  transition: border-color .2s, background .2s;
  color: var(--muted);
}}
.upload-area:hover {{ border-color: var(--accent); background: rgba(0,212,255,0.03); }}
.upload-area svg {{ margin-bottom: 10px; opacity: .5; }}
.upload-area p {{ font-size: 13px; margin-top: 6px; }}
.upload-area strong {{ color: var(--text); }}
</style>
<script>
function showAndSubmit(input) {{
  const names = Array.from(input.files).map(f => f.name);
  if (!names.length) return;
  document.getElementById('picked').textContent = names.join(', ');
  document.getElementById('picked').style.display = 'block';
  document.getElementById('upload-form').submit();
}}

function handleDrop(e) {{
  e.preventDefault();
  document.getElementById('upload-area').style.borderColor = '';
  const files = e.dataTransfer.files;
  if (!files.length) return;
  const input = document.getElementById('xml-input');
  const dt = new DataTransfer();
  for (const f of files) dt.items.add(f);
  input.files = dt.files;
  const names = Array.from(files).map(f => f.name);
  document.getElementById('picked').textContent = names.join(', ');
  document.getElementById('picked').style.display = 'block';
  document.getElementById('upload-form').submit();
}}
</script>
"""
    return base_html("Import — OpenSCAP Dashboard", body, active="import")


@bp.route("/import", methods=["GET"])
def import_form():
    msgs = get_flashed_messages(with_categories=True)
    return _import_html(msgs)


@bp.route("/import", methods=["POST"])
def import_submit():
    files = [f for f in request.files.getlist("xml") if f and f.filename]
    if not files:
        flash("No file uploaded.")
        return redirect(url_for("import_.import_form"))

    loaded = 0
    errors = []
    for f in files:
        try:
            report = sources.load_upload(f.read(), filename=f.filename)
            store.add(report)
            loaded += 1
        except Exception as e:
            errors.append(f"{f.filename}: {e}")

    for err in errors:
        flash(f"Failed to parse: {err}", "error")
    if loaded:
        flash(f"{loaded} report{'s' if loaded > 1 else ''} loaded successfully.", "ok")

    if errors:
        return redirect(url_for("import_.import_form"))
    return redirect(url_for("index.overview"))
