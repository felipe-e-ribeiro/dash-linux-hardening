from markupsafe import escape

BASE_CSS = r"""
:root {
  --bg: #0f1117;
  --surface: #161b25;
  --surface2: #1d2433;
  --border: rgba(255,255,255,0.07);
  --border2: rgba(255,255,255,0.13);
  --text: #e8eaf0;
  --muted: #6b7280;
  --pass: #22c55e;
  --fail: #ef4444;
  --warn: #f59e0b;
  --info: #3b82f6;
  --nc: #8b5cf6;
  --accent: #00d4ff;
  --font-mono: 'IBM Plex Mono', monospace;
  --font-sans: 'IBM Plex Sans', sans-serif;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: var(--bg); color: var(--text); font-family: var(--font-sans); font-size: 14px; min-height: 100vh; }

header.app-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 32px;
  border-bottom: 1px solid var(--border);
  background: var(--surface);
}
.logo { font-family: var(--font-mono); font-size: 15px; font-weight: 500; color: var(--accent); letter-spacing: .05em; display: flex; align-items: center; gap: 10px; }
.logo-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--accent); }
.nav { display: flex; gap: 18px; font-family: var(--font-mono); font-size: 12px; }
.nav a { color: var(--muted); text-decoration: none; transition: color .15s; }
.nav a:hover, .nav a.active { color: var(--accent); }

main { max-width: 1200px; margin: 0 auto; padding: 28px 32px; }

.card {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 8px; padding: 20px;
}
.card-title {
  font-family: var(--font-mono); font-size: 11px; font-weight: 500;
  text-transform: uppercase; letter-spacing: .08em; color: var(--muted);
  margin-bottom: 16px; display: flex; align-items: center; gap: 8px;
}
.card-title::before { content: ''; width: 3px; height: 12px; background: var(--accent); border-radius: 2px; }

.empty-state { text-align: center; padding: 40px; color: var(--muted); font-family: var(--font-mono); font-size: 13px; }

.flash { padding: 10px 14px; border-radius: 6px; margin-bottom: 16px; font-family: var(--font-mono); font-size: 12px;
  border: 1px solid rgba(239,68,68,0.3); background: rgba(239,68,68,0.08); color: #fca5a5; }
.flash-ok { padding: 10px 14px; border-radius: 6px; margin-bottom: 16px; font-family: var(--font-mono); font-size: 12px;
  border: 1px solid rgba(34,197,94,0.3); background: rgba(34,197,94,0.08); color: #86efac; }

button, input[type=submit] { font-family: var(--font-mono); }

::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: var(--bg); }
::-webkit-scrollbar-thumb { background: var(--surface2); border-radius: 3px; }
"""


def _header_html(active: str = "") -> str:
    def cls(name: str) -> str:
        return ' class="active"' if name == active else ""
    return f"""
<header class="app-header">
  <div class="logo"><div class="logo-dot"></div>openscap_dashboard</div>
  <nav class="nav">
    <a href="/"{cls("index")}>overview</a>
    <a href="/import"{cls("import")}>import</a>
    <a href="/network"{cls("network")}>network</a>
    <a href="/scan"{cls("scan")}>scan</a>
  </nav>
</header>
"""


def base_html(title: str, body: str, active: str = "", extra_head: str = "") -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{escape(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@300;400;500&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<style>{BASE_CSS}</style>
{extra_head}
</head>
<body>
{_header_html(active)}
<main>
{body}
</main>
</body>
</html>"""
