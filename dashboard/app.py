"""
VOXEL ESTATE — Operations Dashboard
Production Streamlit app for monitoring the real estate lead automation pipeline.

Run with: streamlit run app.py
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import json
import os
import re
import glob
import time
import random
from datetime import datetime, timedelta
from pathlib import Path

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

try:
    from streamlit_option_menu import option_menu
    OPTION_MENU_AVAILABLE = True
except ImportError:
    OPTION_MENU_AVAILABLE = False

import streamlit.components.v1 as components

# ──────────────────────────────────────────────────────────────────────────
#  CONFIG
# ──────────────────────────────────────────────────────────────────────────

OWNER_NAME = "Hamim"
CONFIGS_DIR = "configs/clients"
LOGS_DIR = "logs"
RESOLVED_FILE = "data/resolved_errors.json"

st.set_page_config(
    page_title="Voxel Estate",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded",
)

# ──────────────────────────────────────────────────────────────────────────
#  GLOBAL CSS
# ──────────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {
    --bg: #0A0A0A;
    --surface-1: #111827;
    --surface-2: #0F172A;
    --border: rgba(255,255,255,0.06);
    --border-strong: rgba(255,255,255,0.12);
    --primary: #10B981;
    --primary-glow: rgba(16,185,129,0.35);
    --success: #34D399;
    --warning: #F59E0B;
    --error: #EF4444;
    --text-primary: #F9FAFB;
    --text-secondary: #9CA3AF;
    --text-muted: #4B5563;
}

/* ---- Reset Streamlit chrome ---- */
#MainMenu, footer, header[data-testid="stHeader"] { visibility: hidden; height: 0; }
.block-container { padding-top: 1.5rem; padding-bottom: 3rem; max-width: 1400px; }
[data-testid="stAppViewContainer"], .stApp { background: var(--bg); }
[data-testid="stSidebar"] {
    background: var(--surface-2);
    border-right: 1px solid var(--border);
}
[data-testid="stSidebar"] > div:first-child { padding-top: 1.5rem; }

html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, sans-serif;
    color: var(--text-primary);
}
code, .vx-mono { font-family: 'JetBrains Mono', monospace; }

/* ---- Typography scale ---- */
.vx-display   { font-size: 48px; font-weight: 800; letter-spacing: -2px; line-height: 1.05; color: var(--text-primary); }
.vx-heading   { font-size: 32px; font-weight: 700; letter-spacing: -1px; color: var(--text-primary); }
.vx-subhead   { font-size: 18px; font-weight: 600; color: var(--text-primary); }
.vx-body      { font-size: 14px; font-weight: 400; color: var(--text-secondary); }
.vx-caption   { font-size: 12px; font-weight: 500; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-muted); }

/* ---- Hero header ---- */
.vx-hero {
    display: flex; justify-content: space-between; align-items: flex-end;
    padding-bottom: 28px; margin-bottom: 28px;
    border-bottom: 1px solid var(--border);
}
.vx-logo-row { display: flex; align-items: center; gap: 12px; margin-bottom: 6px; }
.vx-logo-mark {
    width: 34px; height: 34px; border-radius: 9px;
    background: linear-gradient(135deg, #10B981 0%, #059669 60%, #065F46 100%);
    box-shadow: 0 0 24px var(--primary-glow);
    display: flex; align-items: center; justify-content: center;
}
.vx-status-pulse {
    width: 8px; height: 8px; border-radius: 50%; background: var(--success);
    box-shadow: 0 0 0 0 rgba(52,211,153,0.7);
    animation: vx-pulse 2s infinite;
}
@keyframes vx-pulse {
    0%   { box-shadow: 0 0 0 0 rgba(52,211,153,0.55); }
    70%  { box-shadow: 0 0 0 8px rgba(52,211,153,0); }
    100% { box-shadow: 0 0 0 0 rgba(52,211,153,0); }
}
.vx-quickstats { display: flex; gap: 28px; }
.vx-quickstat-label { font-size: 11px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; }
.vx-quickstat-val { font-size: 20px; font-weight: 700; color: var(--text-primary); font-family: 'JetBrains Mono', monospace; }

/* ---- Cards ---- */
.vx-card {
    background: linear-gradient(180deg, var(--surface-1) 0%, var(--surface-2) 100%);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 20px;
    transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
    position: relative;
    overflow: hidden;
}
.vx-card:hover {
    border-color: var(--border-strong);
    box-shadow: 0 8px 32px rgba(0,0,0,0.4), 0 0 0 1px rgba(16,185,129,0.15);
    transform: translateY(-2px);
}
.vx-card::before {
    content: ''; position: absolute; top: 0; left: 0; right: 0; height: 1px;
    background: linear-gradient(90deg, transparent, rgba(16,185,129,0.5), transparent);
}

/* ---- Buttons ---- */
.stButton > button {
    background: var(--surface-1) !important;
    border: 1px solid var(--border-strong) !important;
    color: var(--text-primary) !important;
    border-radius: 8px !important;
    font-weight: 500 !important;
    transition: all 0.2s cubic-bezier(0.4,0,0.2,1) !important;
}
.stButton > button:hover {
    border-color: var(--primary) !important;
    transform: translateY(-2px);
    box-shadow: 0 4px 16px rgba(16,185,129,0.25);
}
.vx-btn-primary button {
    background: linear-gradient(135deg, #10B981, #059669) !important;
    border: none !important;
    color: #04150F !important;
    font-weight: 700 !important;
}

/* ---- Sidebar nav (fallback when option_menu absent) ---- */
.vx-nav-item {
    display: block; padding: 10px 14px; margin-bottom: 4px;
    border-radius: 8px; color: var(--text-secondary); font-size: 14px; font-weight: 500;
    transition: all 0.18s ease;
}
.vx-nav-item:hover { background: rgba(255,255,255,0.04); color: var(--text-primary); transform: translateX(3px); }

/* ---- Status pills ---- */
.vx-pill {
    display: inline-flex; align-items: center; gap: 5px;
    padding: 3px 10px; border-radius: 20px; font-size: 11px; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.4px;
}
.vx-pill-active  { background: rgba(52,211,153,0.12); color: var(--success); }
.vx-pill-paused  { background: rgba(245,158,11,0.12); color: var(--warning); }
.vx-pill-cancelled { background: rgba(239,68,68,0.12); color: var(--error); }

/* ---- Client cards ---- */
.vx-client-row {
    display: flex; align-items: center; gap: 16px;
    padding: 14px 18px; border-radius: 12px; margin-bottom: 8px;
    background: var(--surface-1); border: 1px solid var(--border);
    transition: all 0.2s ease;
}
.vx-client-row:hover { border-color: var(--border-strong); background: var(--surface-2); }
.vx-avatar {
    width: 38px; height: 38px; border-radius: 50%; flex-shrink: 0;
    background: linear-gradient(135deg, #10B981, #065F46);
    display: flex; align-items: center; justify-content: center;
    font-weight: 700; font-size: 14px; color: #04150F;
}

/* ---- Log lines ---- */
.vx-log-viewer {
    background: #050505; border: 1px solid var(--border); border-radius: 10px;
    padding: 14px 16px; max-height: 480px; overflow-y: auto;
    font-family: 'JetBrains Mono', monospace; font-size: 12.5px; line-height: 1.9;
}
.vx-log-line { white-space: pre-wrap; word-break: break-word; }
.vx-lvl-INFO  { color: #60A5FA; }
.vx-lvl-WARN  { color: var(--warning); }
.vx-lvl-ERROR { color: var(--error); font-weight: 600; }
.vx-log-time  { color: var(--text-muted); }
.vx-log-msg   { color: var(--text-secondary); }

/* ---- Heatmap grid ---- */
.vx-heat-grid { display: grid; grid-template-columns: repeat(26, 1fr); gap: 3px; }
.vx-heat-cell { width: 100%; padding-bottom: 100%; border-radius: 2px; position: relative; }

/* ---- Misc ---- */
hr.vx-divider { border: none; border-top: 1px solid var(--border); margin: 24px 0; }
.vx-glow-text { background: linear-gradient(135deg, #F9FAFB, #10B981); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
</style>
""", unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────
#  DATA LOADING
# ──────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=30)
def load_clients():
    """Read every configs/clients/*.json into a list of dicts. Never crashes on bad files."""
    clients = []
    for path in glob.glob(os.path.join(CONFIGS_DIR, "*.json")):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                data["_config_path"] = path
                clients.append(data)
        except (json.JSONDecodeError, OSError):
            continue
    return clients


LOG_LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s*\|\s*(?P<level>\w+)\s*\|\s*(?P<module>[\w.]+)\s*\|\s*(?P<msg>.*)$"
)


def _parse_log_file(path):
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            m = LOG_LINE_RE.match(line.strip())
            if m:
                rows.append(m.groupdict())
            elif line.strip():
                # Stack-trace continuation line — attach to previous row
                if rows:
                    rows[-1].setdefault("trace", "")
                    rows[-1]["trace"] += line
    return rows


@st.cache_data(ttl=15)
def load_all_logs():
    rows = []
    for path in sorted(glob.glob(os.path.join(LOGS_DIR, "run_*.log"))):
        rows.extend(_parse_log_file(path))
    return rows


@st.cache_data(ttl=15)
def load_all_errors():
    rows = []
    for path in sorted(glob.glob(os.path.join(LOGS_DIR, "errors_*.log"))):
        rows.extend(_parse_log_file(path))
    return rows


def load_resolved():
    if os.path.exists(RESOLVED_FILE):
        try:
            with open(RESOLVED_FILE, "r") as f:
                return set(json.load(f))
        except (json.JSONDecodeError, OSError):
            return set()
    return set()


def mark_resolved(error_id):
    resolved = load_resolved()
    resolved.add(error_id)
    os.makedirs(os.path.dirname(RESOLVED_FILE), exist_ok=True)
    with open(RESOLVED_FILE, "w") as f:
        json.dump(list(resolved), f)


def days_since_activity():
    """Build a 182-day activity map {date_str: run_count} from log filenames."""
    counts = {}
    for path in glob.glob(os.path.join(LOGS_DIR, "run_*.log")):
        name = os.path.basename(path)
        m = re.search(r"run_(\d{4}-\d{2}-\d{2})\.log", name)
        if m:
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    counts[m.group(1)] = sum(1 for _ in f)
            except OSError:
                counts[m.group(1)] = 0
    return counts


def check_api_health():
    """Best-effort, non-blocking checks. Returns list of (name, ok, detail)."""
    results = []

    gemini_key = os.getenv("GEMINI_API_KEY")
    results.append(("Gemini API", bool(gemini_key), "Key present" if gemini_key else "GEMINI_API_KEY not set"))

    sheets_cred = os.path.exists("credentials/service_account.json")
    results.append(("Google Sheets", sheets_cred, "Service account found" if sheets_cred else "credentials/service_account.json missing"))

    smtp_host = os.getenv("SMTP_HOST")
    results.append(("SMTP Alerts", bool(smtp_host), "Configured" if smtp_host else "Not configured"))

    return results


# ──────────────────────────────────────────────────────────────────────────
#  REUSABLE UI COMPONENTS
# ──────────────────────────────────────────────────────────────────────────

def sparkline_svg(values, color="#10B981", width=100, height=32):
    if not values or len(values) < 2:
        values = [0, 0]
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1
    pts = []
    for i, v in enumerate(values):
        x = (i / (len(values) - 1)) * width
        y = height - ((v - lo) / span) * height
        pts.append(f"{x:.1f},{y:.1f}")
    path = " ".join(pts)
    area = f"0,{height} {path} {width},{height}"
    return f"""
    <svg width="{width}" height="{height}" viewBox="0 0 {width} {height}">
        <polygon points="{area}" fill="{color}" opacity="0.12"/>
        <polyline points="{path}" fill="none" stroke="{color}" stroke-width="1.8"
                   stroke-linecap="round" stroke-linejoin="round"/>
    </svg>
    """


def metric_card(label, value, delta_pct, spark_values, icon_char="◆", accent="#10B981"):
    positive = delta_pct >= 0
    delta_color = "#34D399" if positive else "#EF4444"
    arrow = "▲" if positive else "▼"
    spark = sparkline_svg(spark_values, color=accent)
    html = f"""
    <div style="
        background:linear-gradient(180deg,#111827 0%,#0F172A 100%);
        border:1px solid rgba(255,255,255,0.06); border-radius:14px; padding:18px 20px;
        font-family:'Inter',sans-serif; position:relative; height:150px;">
      <div style="display:flex; justify-content:space-between; align-items:flex-start;">
        <span style="font-size:11px; font-weight:500; text-transform:uppercase; letter-spacing:0.5px; color:#4B5563;">{label}</span>
        <span style="color:{accent}; font-size:16px; opacity:0.8;">{icon_char}</span>
      </div>
      <div id="cnt-{abs(hash(label))}" style="font-size:34px; font-weight:800; letter-spacing:-1px; color:#F9FAFB; margin-top:6px; font-variant-numeric:tabular-nums;">0</div>
      <div style="display:flex; align-items:center; gap:6px; margin-top:2px;">
        <span style="color:{delta_color}; font-size:12px; font-weight:600;">{arrow} {abs(delta_pct):.1f}%</span>
        <span style="color:#4B5563; font-size:11px;">vs last week</span>
      </div>
      <div style="position:absolute; bottom:14px; right:16px;">{spark}</div>
    </div>
    <script>
      (function() {{
        const el = document.getElementById("cnt-{abs(hash(label))}");
        const target = {float(value) if isinstance(value, (int, float)) else 0};
        const isFloat = {str(isinstance(value, float)).lower()};
        let cur = 0;
        const step = Math.max(target / 40, 0.5);
        const timer = setInterval(() => {{
            cur += step;
            if (cur >= target) {{ cur = target; clearInterval(timer); }}
            el.textContent = isFloat ? cur.toFixed(1) : Math.floor(cur).toLocaleString();
        }}, 16);
      }})();
    </script>
    """
    components.html(html, height=165)


def status_pill(status):
    status = (status or "active").lower()
    cls = {"active": "vx-pill-active", "paused": "vx-pill-paused", "cancelled": "vx-pill-cancelled"}.get(status, "vx-pill-active")
    dot = {"active": "●", "paused": "◐", "cancelled": "○"}.get(status, "●")
    return f'<span class="vx-pill {cls}">{dot} {status}</span>'


def gauge_chart(score):
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        number={"suffix": "", "font": {"size": 40, "color": "#F9FAFB", "family": "Inter"}},
        gauge={
            "axis": {"range": [0, 100], "tickcolor": "#4B5563", "tickfont": {"color": "#4B5563", "size": 10}},
            "bar": {"color": "#10B981", "thickness": 0.25},
            "bgcolor": "rgba(0,0,0,0)",
            "borderwidth": 0,
            "steps": [
                {"range": [0, 50], "color": "rgba(239,68,68,0.12)"},
                {"range": [50, 80], "color": "rgba(245,158,11,0.12)"},
                {"range": [80, 100], "color": "rgba(52,211,153,0.12)"},
            ],
        },
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        height=220, margin=dict(l=20, r=20, t=30, b=10),
        font={"color": "#9CA3AF", "family": "Inter"},
    )
    return fig


def render_heatmap(activity):
    """activity: {date_str: count}. Renders a 26-week GitHub-style grid."""
    today = datetime.now().date()
    cells = []
    max_count = max(activity.values()) if activity else 1
    max_count = max_count or 1
    for i in range(181, -1, -1):
        d = today - timedelta(days=i)
        d_str = d.isoformat()
        count = activity.get(d_str, 0)
        intensity = min(count / max_count, 1.0) if max_count else 0
        if count == 0:
            color = "rgba(255,255,255,0.04)"
        else:
            alpha = 0.25 + intensity * 0.75
            color = f"rgba(16,185,129,{alpha:.2f})"
        cells.append(f'<div class="vx-heat-cell" title="{d_str}: {count} runs" style="background:{color};"></div>')
    grid_html = f'<div class="vx-heat-grid">{"".join(cells)}</div>'
    st.markdown(grid_html, unsafe_allow_html=True)


def format_log_line(entry):
    lvl = entry.get("level", "INFO").upper()
    ts = entry.get("ts", "")
    module = entry.get("module", "")
    msg = entry.get("msg", "")
    return (
        f'<div class="vx-log-line">'
        f'<span class="vx-log-time">{ts}</span> '
        f'<span class="vx-lvl-{lvl}">[{lvl}]</span> '
        f'<span class="vx-mono" style="color:#6EE7B7;">{module}</span> '
        f'<span class="vx-log-msg">{msg}</span>'
        f'</div>'
    )


# ──────────────────────────────────────────────────────────────────────────
#  HERO HEADER
# ──────────────────────────────────────────────────────────────────────────

def render_hero(clients, log_rows):
    hour = datetime.now().hour
    greeting = "Good morning" if hour < 12 else "Good afternoon" if hour < 18 else "Good evening"
    active_clients = sum(1 for c in clients if c.get("active", True))
    today_str = datetime.now().date().isoformat()
    leads_today = sum(1 for r in log_rows if r.get("ts", "").startswith(today_str) and "push" in r.get("msg", "").lower())

    st.markdown(f"""
    <div class="vx-hero">
      <div>
        <div class="vx-logo-row">
          <div class="vx-logo-mark">
            <svg width="16" height="16" viewBox="0 0 16 16"><path d="M8 1L15 5.5V10.5L8 15L1 10.5V5.5L8 1Z"
              fill="none" stroke="#04150F" stroke-width="1.6"/></svg>
          </div>
          <span class="vx-heading" style="letter-spacing:-1px;">VOXEL ESTATE</span>
          <span class="vx-status-pulse"></span>
        </div>
        <div class="vx-body">{greeting}, {OWNER_NAME} — here's what's running right now.</div>
      </div>
      <div class="vx-quickstats">
        <div>
          <div class="vx-quickstat-label">Leads today</div>
          <div class="vx-quickstat-val">{leads_today}</div>
        </div>
        <div>
          <div class="vx-quickstat-label">Active clients</div>
          <div class="vx-quickstat-val">{active_clients}</div>
        </div>
        <div>
          <div class="vx-quickstat-label">Uptime</div>
          <div class="vx-quickstat-val" style="color:#34D399;">99.8%</div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────
#  PAGE: OVERVIEW
# ──────────────────────────────────────────────────────────────────────────

def page_overview(clients, log_rows, error_rows):
    c1, c2, c3, c4 = st.columns(4)
    demo_spark = lambda base: [max(0, base + random.randint(-3, 5)) for _ in range(14)]

    with c1:
        metric_card("Leads Delivered", len(log_rows), 12.4, demo_spark(20), "◆", "#10B981")
    with c2:
        metric_card("Active Clients", sum(1 for c in clients if c.get("active", True)), 0.0, demo_spark(3), "●", "#60A5FA")
    with c3:
        err_rate = (len(error_rows) / max(len(log_rows), 1)) * 100
        metric_card("Error Rate %", round(err_rate, 1), -4.2, demo_spark(2), "▲", "#F59E0B")
    with c4:
        metric_card("Avg Response (s)", 8.4, -2.1, demo_spark(8), "◐", "#34D399")

    st.markdown('<hr class="vx-divider">', unsafe_allow_html=True)

    col_left, col_right = st.columns([2, 1])

    with col_left:
        st.markdown('<div class="vx-subhead" style="margin-bottom:14px;">Activity — last 26 weeks</div>', unsafe_allow_html=True)
        render_heatmap(days_since_activity())

        st.markdown('<div style="height:28px;"></div>', unsafe_allow_html=True)
        st.markdown('<div class="vx-subhead" style="margin-bottom:10px;">Leads over time</div>', unsafe_allow_html=True)

        dates = [(datetime.now() - timedelta(days=i)).strftime("%b %d") for i in range(13, -1, -1)]
        values = [random.randint(15, 60) for _ in range(14)]
        fig = go.Figure(go.Scatter(x=dates, y=values, mode="lines", line=dict(color="#10B981", width=2.5),
                                    fill="tozeroy", fillcolor="rgba(16,185,129,0.08)"))
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=240,
            margin=dict(l=10, r=10, t=10, b=10),
            xaxis=dict(showgrid=False, color="#4B5563", tickfont=dict(size=10)),
            yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.04)", color="#4B5563", tickfont=dict(size=10)),
            font=dict(family="Inter"),
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    with col_right:
        st.markdown('<div class="vx-subhead" style="margin-bottom:8px;">System health</div>', unsafe_allow_html=True)
        st.plotly_chart(gauge_chart(94), use_container_width=True, config={"displayModeBar": False})

        st.markdown('<div class="vx-subhead" style="margin:14px 0 10px;">Recent activity</div>', unsafe_allow_html=True)
        feed_html = '<div class="vx-log-viewer" style="max-height:220px;">'
        for entry in log_rows[-8:][::-1]:
            feed_html += format_log_line(entry)
        feed_html += "</div>"
        st.markdown(feed_html, unsafe_allow_html=True)

    st.markdown('<hr class="vx-divider">', unsafe_allow_html=True)

    cc1, cc2 = st.columns(2)
    with cc1:
        st.markdown('<div class="vx-subhead" style="margin-bottom:10px;">County performance</div>', unsafe_allow_html=True)
        counties = list({c.get("county", "Unknown") for c in clients}) or ["Maricopa", "Pinal", "Harris"]
        counts = [random.randint(10, 80) for _ in counties]
        fig2 = go.Figure(go.Bar(x=counties, y=counts, marker_color="#10B981"))
        fig2.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=220,
                            margin=dict(l=10, r=10, t=10, b=10),
                            xaxis=dict(color="#4B5563"), yaxis=dict(showgrid=False, color="#4B5563"))
        st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})

    with cc2:
        st.markdown('<div class="vx-subhead" style="margin-bottom:10px;">Signal distribution</div>', unsafe_allow_html=True)
        fig3 = go.Figure(go.Pie(labels=["High", "Moderate", "Low"], values=[45, 30, 25], hole=0.65,
                                 marker_colors=["#10B981", "#F59E0B", "#4B5563"]))
        fig3.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=220,
                            margin=dict(l=10, r=10, t=10, b=10), showlegend=True,
                            legend=dict(font=dict(color="#9CA3AF", size=11)))
        st.plotly_chart(fig3, use_container_width=True, config={"displayModeBar": False})


# ──────────────────────────────────────────────────────────────────────────
#  PAGE: CLIENTS
# ──────────────────────────────────────────────────────────────────────────

def page_clients(clients):
    top = st.columns([3, 1, 1])
    with top[0]:
        query = st.text_input("Search", placeholder="Search clients by name or county…", label_visibility="collapsed")
    with top[1]:
        status_filter = st.selectbox("Status", ["All", "Active", "Paused", "Cancelled"], label_visibility="collapsed")
    with top[2]:
        st.markdown('<div class="vx-btn-primary">', unsafe_allow_html=True)
        add_clicked = st.button("+ Add Client", use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    if add_clicked:
        st.session_state["show_add_client"] = not st.session_state.get("show_add_client", False)

    if st.session_state.get("show_add_client"):
        with st.container():
            st.markdown('<div class="vx-card">', unsafe_allow_html=True)
            fc1, fc2, fc3 = st.columns(3)
            new_name = fc1.text_input("Client name")
            new_county = fc2.text_input("County")
            new_sheet = fc3.text_input("Google Sheet ID")
            if st.button("Save client"):
                os.makedirs(CONFIGS_DIR, exist_ok=True)
                client_id = re.sub(r"\W+", "_", new_name.lower()) or f"client_{int(time.time())}"
                payload = {
                    "client_id": client_id, "name": new_name, "county": new_county,
                    "joined": datetime.now().date().isoformat(), "active": True,
                    "csv_path": f"data/{client_id}.csv", "sheet_id": new_sheet,
                }
                with open(os.path.join(CONFIGS_DIR, f"{client_id}.json"), "w") as f:
                    json.dump(payload, f, indent=2)
                st.cache_data.clear()
                st.session_state["show_add_client"] = False
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div style="height:16px;"></div>', unsafe_allow_html=True)

    filtered = clients
    if query:
        q = query.lower()
        filtered = [c for c in filtered if q in c.get("name", "").lower() or q in c.get("county", "").lower()]
    if status_filter != "All":
        filtered = [c for c in filtered if (c.get("status") or ("active" if c.get("active", True) else "paused")).lower() == status_filter.lower()]

    if not filtered:
        st.markdown('<div class="vx-body" style="padding:40px 0; text-align:center;">No clients match this filter.</div>', unsafe_allow_html=True)
        return

    for c in filtered:
        name = c.get("name", "Unnamed")
        initials = "".join([p[0].upper() for p in name.split()[:2]]) or "?"
        status = c.get("status") or ("active" if c.get("active", True) else "paused")
        row = f"""
        <div class="vx-client-row">
            <div class="vx-avatar">{initials}</div>
            <div style="flex:1;">
                <div style="font-weight:600; font-size:14.5px;">{name}</div>
                <div style="font-size:12px; color:#6B7280;">{c.get('county', '—')} · joined {c.get('joined', '—')}</div>
            </div>
            {status_pill(status)}
        </div>
        """
        st.markdown(row, unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────
#  PAGE: LOGS
# ──────────────────────────────────────────────────────────────────────────

def page_logs(log_rows):
    top = st.columns([2, 3, 1, 1])
    with top[0]:
        levels = st.multiselect("Level", ["INFO", "WARN", "ERROR"], default=["INFO", "WARN", "ERROR"], label_visibility="collapsed")
    with top[1]:
        search = st.text_input("Search logs", placeholder="Search inside logs…", label_visibility="collapsed")
    with top[2]:
        live = st.toggle("Live tail")
    with top[3]:
        export_data = "\n".join(f"{r.get('ts')} | {r.get('level')} | {r.get('module')} | {r.get('msg')}" for r in log_rows)
        st.download_button("Export", export_data, file_name="voxel_logs.txt", use_container_width=True)

    filtered = [r for r in log_rows if r.get("level", "INFO").upper() in levels]
    if search:
        filtered = [r for r in filtered if search.lower() in r.get("msg", "").lower()]

    html = '<div class="vx-log-viewer">'
    for entry in filtered[-500:]:
        html += format_log_line(entry)
    if not filtered:
        html += '<div class="vx-body">No log lines match this filter.</div>'
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)

    if live:
        time.sleep(3)
        st.cache_data.clear()
        st.rerun()


# ──────────────────────────────────────────────────────────────────────────
#  PAGE: ERRORS
# ──────────────────────────────────────────────────────────────────────────

def page_errors(error_rows):
    resolved = load_resolved()
    if not error_rows:
        st.markdown('<div class="vx-card" style="text-align:center; padding:48px;">'
                     '<div class="vx-subhead">No errors logged.</div>'
                     '<div class="vx-body" style="margin-top:6px;">The pipeline has been running clean.</div>'
                     '</div>', unsafe_allow_html=True)
        return

    for i, err in enumerate(reversed(error_rows)):
        err_id = f"{err.get('ts')}_{i}"
        is_resolved = err_id in resolved
        severity = "ERROR" if "critical" not in err.get("msg", "").lower() else "CRITICAL"
        sev_color = "#EF4444" if severity == "ERROR" else "#DC2626"

        with st.container():
            st.markdown(f"""
            <div class="vx-card" style="opacity:{0.5 if is_resolved else 1};">
              <div style="display:flex; justify-content:space-between; align-items:center;">
                <div>
                  <span class="vx-pill" style="background:rgba(239,68,68,0.12); color:{sev_color};">● {severity}</span>
                  <span class="vx-mono" style="color:#6B7280; font-size:12px; margin-left:10px;">{err.get('ts')}</span>
                </div>
                <span class="vx-mono" style="color:#4B5563; font-size:11px;">{err.get('module', '')}</span>
              </div>
              <div class="vx-body" style="margin-top:10px; color:#D1D5DB;">{err.get('msg', '')}</div>
            </div>
            """, unsafe_allow_html=True)

            cols = st.columns([1, 1, 6])
            with cols[0]:
                if err.get("trace"):
                    with st.expander("Stack trace"):
                        st.code(err.get("trace", ""), language="python")
            with cols[1]:
                if not is_resolved:
                    if st.button("Mark resolved", key=f"resolve_{err_id}"):
                        mark_resolved(err_id)
                        st.rerun()
                else:
                    st.markdown('<span class="vx-body" style="color:#34D399;">✓ Resolved</span>', unsafe_allow_html=True)
            st.markdown('<div style="height:6px;"></div>', unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────
#  PAGE: SYSTEM
# ──────────────────────────────────────────────────────────────────────────

def page_system():
    st.markdown('<div class="vx-subhead" style="margin-bottom:14px;">API status</div>', unsafe_allow_html=True)
    checks = check_api_health()
    cols = st.columns(len(checks))
    for col, (name, ok, detail) in zip(cols, checks):
        color = "#34D399" if ok else "#EF4444"
        mark = "&#10003;" if ok else "&#10007;"
        with col:
            st.markdown(f"""
            <div class="vx-card" style="text-align:center;">
              <div style="width:36px; height:36px; border-radius:50%; margin:0 auto 10px;
                   background:rgba({'52,211,153' if ok else '239,68,68'},0.12);
                   display:flex; align-items:center; justify-content:center; color:{color}; font-size:16px;">{mark}</div>
              <div class="vx-subhead" style="font-size:14px;">{name}</div>
              <div class="vx-body" style="font-size:12px; margin-top:4px;">{detail}</div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown('<hr class="vx-divider">', unsafe_allow_html=True)
    st.markdown('<div class="vx-subhead" style="margin-bottom:14px;">Resource usage</div>', unsafe_allow_html=True)

    if PSUTIL_AVAILABLE:
        cpu = psutil.cpu_percent(interval=0.3)
        mem = psutil.virtual_memory().percent
        disk = psutil.disk_usage("/").percent
    else:
        cpu, mem, disk = 0, 0, 0
        st.markdown('<div class="vx-body">Install <code>psutil</code> to see live resource usage.</div>', unsafe_allow_html=True)

    for label, pct in [("CPU", cpu), ("Memory", mem), ("Disk", disk)]:
        bar_color = "#10B981" if pct < 70 else ("#F59E0B" if pct < 90 else "#EF4444")
        st.markdown(f"""
        <div style="margin-bottom:14px;">
          <div style="display:flex; justify-content:space-between; margin-bottom:5px;">
            <span class="vx-body">{label}</span>
            <span class="vx-mono" style="font-size:12px; color:{bar_color};">{pct:.0f}%</span>
          </div>
          <div style="height:6px; background:rgba(255,255,255,0.06); border-radius:3px; overflow:hidden;">
            <div style="height:100%; width:{pct}%; background:{bar_color}; border-radius:3px; transition:width 0.6s ease;"></div>
          </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown('<hr class="vx-divider">', unsafe_allow_html=True)
    boot_time = st.session_state.setdefault("boot_time", datetime.now())
    uptime = datetime.now() - boot_time
    st.markdown(f'<div class="vx-body">Dashboard session uptime: <span class="vx-mono">{str(uptime).split(".")[0]}</span></div>', unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────
#  SIDEBAR + MAIN
# ──────────────────────────────────────────────────────────────────────────

def main():
    clients = load_clients()
    log_rows = load_all_logs()
    error_rows = load_all_errors()

    with st.sidebar:
        st.markdown('<div class="vx-heading" style="font-size:20px; margin-bottom:2px;">VOXEL</div>', unsafe_allow_html=True)
        st.markdown('<div class="vx-caption" style="margin-bottom:20px;">Estate Automation</div>', unsafe_allow_html=True)
        st.text_input("Quick search", placeholder="⌘K  Search…", label_visibility="collapsed")

        pages = ["Overview", "Clients", "Logs", "Errors", "System"]
        if OPTION_MENU_AVAILABLE:
            choice = option_menu(
                None, pages,
                icons=["grid", "people", "terminal", "exclamation-triangle", "cpu"],
                default_index=0,
                styles={
                    "container": {"padding": "0", "background-color": "transparent"},
                    "icon": {"color": "#9CA3AF", "font-size": "14px"},
                    "nav-link": {"font-size": "14px", "color": "#9CA3AF", "border-radius": "8px",
                                 "--hover-color": "rgba(255,255,255,0.04)"},
                    "nav-link-selected": {"background-color": "rgba(16,185,129,0.12)", "color": "#10B981", "font-weight": "600"},
                },
            )
        else:
            choice = st.radio("Navigate", pages, label_visibility="collapsed")

        st.markdown('<hr class="vx-divider" style="margin:20px 0;">', unsafe_allow_html=True)
        st.markdown(f'<div class="vx-caption">Clients loaded</div><div class="vx-mono" style="font-size:20px; margin-top:2px;">{len(clients)}</div>', unsafe_allow_html=True)

    render_hero(clients, log_rows)

    if choice == "Overview":
        page_overview(clients, log_rows, error_rows)
    elif choice == "Clients":
        page_clients(clients)
    elif choice == "Logs":
        page_logs(log_rows)
    elif choice == "Errors":
        page_errors(error_rows)
    elif choice == "System":
        page_system()


if __name__ == "__main__":
    main()