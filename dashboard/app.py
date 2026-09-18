"""
Voxel Estate — Monitoring Dashboard
Streamlit app to monitor pipeline runs, clients, and system health.

Run locally:
    streamlit run dashboard/app.py

Deploy:
    Push to GitHub → Streamlit Cloud auto-deploy
"""

import os
import sys
import json
from datetime import datetime, timedelta
from pathlib import Path

import streamlit as st
import pandas as pd

# ============================================================
# CONFIG
# ============================================================
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

CONFIG_DIR = PROJECT_ROOT / "configs" / "clients"
LOGS_DIR = PROJECT_ROOT / "logs"
DATA_CLIENTS_DIR = PROJECT_ROOT / "data" / "clients"

# Page config
st.set_page_config(
    page_title="Voxel Estate — Dashboard",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# STYLES
# ============================================================
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        color: #10B981;
        font-weight: 800;
        margin-bottom: 0;
    }
    .sub-header {
        color: #6B7280;
        font-size: 1rem;
        margin-bottom: 2rem;
    }
    .metric-card {
        background: #F9FAFB;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #10B981;
    }
    .success-box {
        background: #D1FAE5;
        padding: 0.75rem;
        border-radius: 6px;
        color: #065F46;
    }
    .error-box {
        background: #FEE2E2;
        padding: 0.75rem;
        border-radius: 6px;
        color: #991B1B;
    }
</style>
""", unsafe_allow_html=True)


# ============================================================
# DATA LOADERS
# ============================================================
@st.cache_data(ttl=60)  # Cache for 60 seconds
def load_clients():
    """Load all client configs."""
    if not CONFIG_DIR.exists():
        return []

    clients = []
    for cfg_file in sorted(CONFIG_DIR.glob("*.json")):
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            cfg["_file"] = cfg_file.name
            clients.append(cfg)
        except Exception:
            continue
    return clients


@st.cache_data(ttl=60)
def load_logs(days=7):
    """Load recent log entries."""
    if not LOGS_DIR.exists():
        return pd.DataFrame()

    cutoff = datetime.now() - timedelta(days=days)
    logs = []

    for log_file in LOGS_DIR.glob("run_*.log"):
        try:
            # Extract date from filename
            date_str = log_file.stem.replace("run_", "")
            log_date = datetime.strptime(date_str, "%Y-%m-%d")
            if log_date < cutoff:
                continue

            with open(log_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    logs.append({
                        "date": log_date.strftime("%Y-%m-%d"),
                        "line": line,
                        "file": log_file.name,
                    })
        except Exception:
            continue

    return pd.DataFrame(logs)


@st.cache_data(ttl=60)
def load_errors(days=7):
    """Load recent errors."""
    if not LOGS_DIR.exists():
        return []

    cutoff = datetime.now() - timedelta(days=days)
    errors = []

    for err_file in LOGS_DIR.glob("errors_*.log"):
        try:
            date_str = err_file.stem.replace("errors_", "")
            err_date = datetime.strptime(date_str, "%Y-%m-%d")
            if err_date < cutoff:
                continue

            with open(err_file, "r", encoding="utf-8") as f:
                content = f.read()
                if content.strip():
                    errors.append({
                        "date": err_date.strftime("%Y-%m-%d"),
                        "content": content,
                    })
        except Exception:
            continue

    return errors


def get_last_run_info():
    """Get info about last pipeline run."""
    if not LOGS_DIR.exists():
        return None

    today = datetime.now().strftime("%Y-%m-%d")
    today_log = LOGS_DIR / f"run_{today}.log"

    if not today_log.exists():
        # Find most recent
        log_files = sorted(LOGS_DIR.glob("run_*.log"), reverse=True)
        if not log_files:
            return None
        today_log = log_files[0]

    try:
        with open(today_log, "r", encoding="utf-8") as f:
            lines = f.readlines()

        last_lines = [l.strip() for l in lines[-20:] if l.strip()]
        return {
            "file": today_log.name,
            "last_lines": last_lines[-5:],
            "total_lines": len(lines),
        }
    except Exception:
        return None


# ============================================================
# UI — HEADER
# ============================================================
st.markdown('<p class="main-header">🏠 Voxel Estate</p>', unsafe_allow_html=True)
st.markdown(
    '<p class="sub-header">Real Estate Lead Automation — Monitoring Dashboard</p>',
    unsafe_allow_html=True,
)

# ============================================================
# UI — SIDEBAR
# ============================================================
with st.sidebar:
    st.header("📊 Navigation")
    page = st.radio(
        "Go to",
        ["🏠 Overview", "👥 Clients", "📋 Logs", "⚠️ Errors", "⚙️ System"],
        label_visibility="collapsed",
    )

    st.divider()
    st.caption(f"Updated: {datetime.now().strftime('%H:%M:%S')}")

    if st.button("🔄 Refresh Data"):
        st.cache_data.clear()
        st.rerun()


# ============================================================
# PAGE — OVERVIEW
# ============================================================
if page == "🏠 Overview":
    st.header("Overview")

    clients = load_clients()
    active_clients = [c for c in clients if c.get("active", True)]

    # Metrics row
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Clients", len(clients))

    with col2:
        st.metric("Active Clients", len(active_clients))

    with col3:
        counties = set(c.get("county", "") for c in clients if c.get("county"))
        st.metric("Counties Covered", len(counties))

    with col4:
        st.metric("Status", "🟢 Online")

    st.divider()

    # Last run info
    st.subheader("📊 Last Pipeline Run")
    last_run = get_last_run_info()

    if last_run:
        st.markdown(f"**Log file:** `{last_run['file']}`")
        st.markdown(f"**Total log lines:** {last_run['total_lines']}")

        st.markdown("**Recent activity:**")
        for line in last_run["last_lines"]:
            st.code(line, language="text")
    else:
        st.info("No pipeline runs found. Run `python scripts/run_all_clients.py`")

    st.divider()

    # Recent errors summary
    errors = load_errors(days=7)
    if errors:
        st.subheader("⚠️ Recent Errors (Last 7 days)")
        st.error(f"Found {len(errors)} day(s) with errors")
        for err in errors[:3]:
            with st.expander(f"📅 {err['date']}"):
                st.code(err["content"][:1000], language="text")
    else:
        st.success("✅ No errors in last 7 days")


# ============================================================
# PAGE — CLIENTS
# ============================================================
elif page == "👥 Clients":
    st.header("Client Management")

    clients = load_clients()

    if not clients:
        st.warning("No clients configured. Run onboarding script to add clients.")
        st.code(
            "python scripts/onboard_client.py --name 'Client A' "
            "--sheet-id 'SHEET_ID' --county 'maricopa_az'",
            language="powershell",
        )
    else:
        for client in clients:
            with st.container():
                col1, col2, col3 = st.columns([3, 1, 1])

                with col1:
                    active_icon = "🟢" if client.get("active", True) else "🔴"
                    st.markdown(f"### {active_icon} {client.get('name', 'Unknown')}")
                    st.caption(f"ID: `{client.get('client_id')}`")

                with col2:
                    st.metric("County", client.get("county", "N/A"))

                with col3:
                    st.metric("Joined", client.get("joined", "N/A"))

                # CSV status
                csv_path = PROJECT_ROOT / client.get("csv_path", "")
                if csv_path.exists():
                    size_kb = csv_path.stat().st_size / 1024
                    st.caption(f"📁 CSV: `{client.get('csv_path')}` ({size_kb:.1f} KB)")
                else:
                    st.error(f"❌ CSV missing: `{client.get('csv_path')}`")

                st.divider()


# ============================================================
# PAGE — LOGS
# ============================================================
elif page == "📋 Logs":
    st.header("Recent Logs")

    days = st.slider("Days to show", 1, 30, 7)

    logs_df = load_logs(days=days)

    if logs_df.empty:
        st.info(f"No logs found in last {days} days")
    else:
        st.metric("Total log entries", len(logs_df))

        # Filter by date
        dates = sorted(logs_df["date"].unique(), reverse=True)
        selected_date = st.selectbox("Select date", dates)

        filtered = logs_df[logs_df["date"] == selected_date]

        st.markdown(f"**Entries for {selected_date}:** {len(filtered)}")
        st.code("\n".join(filtered["line"].tolist()[-100:]), language="text")


# ============================================================
# PAGE — ERRORS
# ============================================================
elif page == "⚠️ Errors":
    st.header("Error Logs")

    days = st.slider("Days to show", 1, 30, 7)
    errors = load_errors(days=days)

    if not errors:
        st.success(f"✅ No errors in last {days} days")
    else:
        st.error(f"⚠️ {len(errors)} day(s) with errors")

        for err in errors:
            with st.expander(f"📅 {err['date']}", expanded=(err == errors[0])):
                st.code(err["content"], language="text")


# ============================================================
# PAGE — SYSTEM
# ============================================================
elif page == "⚙️ System":
    st.header("System Status")

    # Environment check
    st.subheader("🔐 Environment")

    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        st.success("✅ `.env` file exists")
    else:
        st.error("❌ `.env` file missing")

    sa_file = PROJECT_ROOT / "credentials" / "service_account.json"
    if sa_file.exists():
        st.success("✅ Service Account JSON exists")
    else:
        st.error("❌ Service Account JSON missing")

    # Directory check
    st.subheader("📁 Directories")

    dirs = {
        "configs/clients": CONFIG_DIR,
        "data/clients": DATA_CLIENTS_DIR,
        "logs": LOGS_DIR,
        "src": PROJECT_ROOT / "src",
        "scripts": PROJECT_ROOT / "scripts",
    }

    for name, path in dirs.items():
        if path.exists():
            file_count = len(list(path.glob("*")))
            st.success(f"✅ `{name}/` ({file_count} items)")
        else:
            st.error(f"❌ `{name}/` missing")

    # Versions
    st.subheader("🔧 Versions")

    try:
        import pandas
        st.text(f"pandas: {pandas.__version__}")
    except ImportError:
        st.text("pandas: not installed")

    try:
        import streamlit
        st.text(f"streamlit: {streamlit.__version__}")
    except ImportError:
        pass

    # Python
    st.text(f"Python: {sys.version.split()[0]}")


# ============================================================
# FOOTER
# ============================================================
st.divider()
st.caption("Voxel Estate — Automated Motivated Seller Intelligence")
st.caption("voxelestate.netlify.app")