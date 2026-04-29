"""
pages/viewer.py  —  Pavadzīmju Uzskaitīšanas Sistēma
Ieliek šo failu mapē: OnlinePavadzimes/pages/viewer.py
"""

import streamlit as st
import pandas as pd
import json
import requests
import base64
import os
from io import StringIO

st.set_page_config(page_title="Pavadzīmju Uzskaitīšana", layout="wide")

# ---------------------------------------------------------------------------
# Konfigurācija (tāda pati kā app.py)
# ---------------------------------------------------------------------------

GITHUB_REPO           = "Andzhss/OnlinePavadzimes"
GITHUB_HISTORY_PATH   = "OnlinePavadzimes/invoice_history.csv"
GITHUB_TEST_HIST_PATH = "OnlinePavadzimes/test_invoice_history.csv"

# Lokālie faili (divi līmeņi augstāk no pages/)
BASE_DIR              = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_HISTORY_PATH    = os.path.join(BASE_DIR, "invoice_history.csv")
LOCAL_TEST_HIST_PATH  = os.path.join(BASE_DIR, "test_invoice_history.csv")

# ---------------------------------------------------------------------------
# Palīgfunkcijas
# ---------------------------------------------------------------------------

def get_github_token():
    token = st.secrets.get("GITHUB_TOKEN", "")
    return token.strip().strip('"').strip("'") if token else ""

def fetch_history_from_github(github_path):
    """Lejupielādē history CSV no GitHub, atgriež DataFrame vai None."""
    token = get_github_token()
    url   = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{github_path}"
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            content_b64 = r.json().get("content", "")
            if content_b64:
                content_str = base64.b64decode(content_b64).decode("utf-8")
                if "doc_id" in content_str:
                    return pd.read_csv(StringIO(content_str), dtype=str)
    except Exception as e:
        st.error(f"Kļūda ielādējot no GitHub: {e}")
    return None

def fetch_history_local(local_path):
    """Ielādē history CSV lokāli."""
    if os.path.exists(local_path):
        try:
            return pd.read_csv(local_path, dtype=str)
        except Exception:
            pass
    return None

def load_best_available(github_path, local_path, label=""):
    """Mēģina GitHub, ja neizdevās — lokālo failu."""
    df = fetch_history_from_github(github_path)
    if df is not None and not df.empty:
        return df, "github"
    df = fetch_history_local(local_path)
    if df is not None and not df.empty:
        return df, "local"
    return None, None

def parse_items_summary(items_str):
    """No JSON stringa izveido īsu produktu kopsavilkumu."""
    try:
        if not items_str or pd.isna(items_str):
            return "—"
        items = json.loads(items_str)
        if not items:
            return "—"
        names = [item.get('name', '') for item in items if item.get('name')]
        summary = "; ".join(names[:2])
        if len(names) > 2:
            summary += f" (+{len(names) - 2})"
        return summary
    except Exception:
        return str(items_str)[:60] if items_str else "—"

def get_last_invoice_number(df):
    """Atrod lielāko pavadzīmes numuru."""
    max_num = 0
    for doc_id in df['doc_id'].dropna():
        parts = str(doc_id).split()
        if len(parts) > 1 and parts[-1].isdigit():
            num = int(parts[-1])
            if num > max_num:
                max_num = num
    return max_num

# ---------------------------------------------------------------------------
# Galvenais skats
# ---------------------------------------------------------------------------

st.title("📋 Pavadzīmju Uzskaitīšanas Sistēma")
st.caption("SIA BRATUS — visu izrakstīto dokumentu pārskats")

# --- Izvēle: īstā vai testa vēsture ---
col_tabs_l, col_tabs_r = st.columns([2, 1])
with col_tabs_l:
    view_mode = st.radio(
        "Skatīt:",
        ["📄 Izrakstītās pavadzīmes", "🔄 Testa / Proformas dokumenti"],
        horizontal=True
    )
with col_tabs_r:
    sync_btn = st.button("🔄 Atjaunot no GitHub", use_container_width=True)

if view_mode == "📄 Izrakstītās pavadzīmes":
    gh_path    = GITHUB_HISTORY_PATH
    local_path = LOCAL_HISTORY_PATH
    cache_key  = "viewer_df_real"
else:
    gh_path    = GITHUB_TEST_HIST_PATH
    local_path = LOCAL_TEST_HIST_PATH
    cache_key  = "viewer_df_test"

# --- Datu ielāde ---
if sync_btn or cache_key not in st.session_state:
    with st.spinner("Ielādē datus..."):
        df, source = load_best_available(gh_path, local_path)
        if df is not None:
            st.session_state[cache_key] = df
            if source == "github" and sync_btn:
                st.success("✅ Dati atjaunoti no GitHub")
            elif source == "local":
                st.info("ℹ️ Dati ielādēti lokāli (GitHub nav pieejams vai nav Token)")
        else:
            st.session_state[cache_key] = None

df = st.session_state.get(cache_key)

# ---------------------------------------------------------------------------
# Galvenais saturs
# ---------------------------------------------------------------------------

if df is None or df.empty:
    st.info("📭 Nav datu. Nospiediet 'Atjaunot no GitHub' vai vispirms izveidojiet pavadzīmes.")
    st.stop()

# --- Statistikas josla ---
last_num = get_last_invoice_number(df)

total_amount = 0.0
try:
    # Summas ir formātā "1 234,56" — jāpārvērš
    totals = (
        df['total']
        .str.replace(' ', '', regex=False)
        .str.replace(',', '.', regex=False)
        .apply(pd.to_numeric, errors='coerce')
    )
    total_amount = totals.sum()
except Exception:
    pass

stat1, stat2, stat3 = st.columns(3)
with stat1:
    st.metric("📄 Pēdējā pavadzīme", f"BR {last_num:04d}" if last_num else "—")
with stat2:
    st.metric("📊 Kopā dokumenti", len(df))
with stat3:
    st.metric("💶 Kopējā apgrozījuma summa", f"€ {total_amount:,.2f}".replace(",", " "))

st.markdown("---")

# --- Filtri ---
st.subheader("🔍 Filtri")
f1, f2, f3 = st.columns(3)
with f1:
    search_client = st.text_input("Klients", placeholder="Meklēt pēc nosaukuma...")
with f2:
    all_types    = ["Visi"] + sorted(df['doc_type'].dropna().unique().tolist())
    filter_type  = st.selectbox("Dokumenta tips", all_types)
with f3:
    search_nr = st.text_input("Dokumenta Nr.", placeholder="piemēram BR 0052")

# Filtrēšana
filtered = df.copy()
if search_client:
    filtered = filtered[filtered['client_name'].str.contains(search_client, case=False, na=False)]
if filter_type != "Visi":
    filtered = filtered[filtered['doc_type'] == filter_type]
if search_nr:
    filtered = filtered[filtered['doc_id'].str.contains(search_nr, case=False, na=False)]

# --- Tabulas sagatavošana ---
display = filtered[['doc_id', 'date', 'client_name', 'doc_type', 'total', 'created_at']].copy()

if 'items' in filtered.columns:
    display.insert(4, 'produkti', filtered['items'].apply(parse_items_summary))

display = display.rename(columns={
    'doc_id':     'Nr.',
    'date':       'Datums',
    'client_name':'Klients',
    'doc_type':   'Tips',
    'total':      'Summa (EUR)',
    'created_at': 'Izveidots',
    'produkti':   'Produkti'
})

# Jaunākie pirmie
display = display.iloc[::-1].reset_index(drop=True)

col_order = [c for c in ['Nr.', 'Datums', 'Klients', 'Produkti', 'Summa (EUR)', 'Tips', 'Izveidots']
             if c in display.columns]

st.subheader(f"📋 Dokumentu saraksts  —  {len(filtered)} ieraksti")
st.dataframe(
    display[col_order],
    use_container_width=True,
    hide_index=True
)

# ---------------------------------------------------------------------------
# Detalizētais skats
# ---------------------------------------------------------------------------

st.markdown("---")
st.subheader("🔍 Detalizēts skats")

if filtered.empty:
    st.info("Nav dokumentu, kas atbilst filtriem.")
    st.stop()

# Dropdown ar jaunākajiem pirmajiem
doc_ids_ordered = list(reversed(filtered['doc_id'].tolist()))

selected_id = st.selectbox(
    "Izvēlies dokumentu:",
    doc_ids_ordered,
    format_func=lambda x: (
        f"{x}  —  "
        + filtered.loc[filtered['doc_id'] == x, 'client_name'].values[0]
        + "  ("
        + filtered.loc[filtered['doc_id'] == x, 'date'].values[0]
        + ")"
    )
)

sel = filtered[filtered['doc_id'] == selected_id].iloc[0]

# Kartiņa ar datiem
with st.container(border=True):
    h1, h2 = st.columns(2)

    with h1:
        st.markdown("#### 📄 Dokumenta dati")
        st.markdown(f"**Nr.:** {sel.get('doc_id', '—')}")
        st.markdown(f"**Tips:** {sel.get('doc_type', '—')}")
        st.markdown(f"**Datums:** {sel.get('date', '—')}")
        st.markdown(f"**Apmaksāt līdz:** {sel.get('due_date', '—')}")
        st.markdown(f"**Izveidots:** {sel.get('created_at', '—')}")

    with h2:
        st.markdown("#### 🏢 Klienta dati")
        st.markdown(f"**Klients:** {sel.get('client_name', '—')}")
        st.markdown(f"**Adrese:** {sel.get('client_address', '—')}")
        st.markdown(f"**Reģ. Nr.:** {sel.get('client_reg_no', '—')}")
        st.markdown(f"**PVN Nr.:** {sel.get('client_vat_no', '—')}")
        st.markdown(f"**💶 Kopā apmaksai:** **{sel.get('total', '—')} EUR**")

    # Pozīciju tabula
    items_str = sel.get('items', '[]')
    try:
        if pd.notna(items_str) and items_str:
            items = json.loads(items_str)
            if items:
                st.markdown("#### 📦 Pozīcijas")
                items_df = pd.DataFrame(items)
                col_map  = {
                    'seq':   'Nr.',
                    'name':  'Nosaukums',
                    'unit':  'Mērvienība',
                    'qty':   'Daudzums',
                    'price': 'Cena (EUR)',
                    'total': 'Kopā (EUR)'
                }
                valid = [c for c in col_map if c in items_df.columns]
                st.dataframe(
                    items_df[valid].rename(columns=col_map),
                    use_container_width=True,
                    hide_index=True
                )
    except Exception:
        pass

    # Komentāri
    comments = sel.get('comments', '')
    if comments and str(comments) not in ('', 'nan'):
        st.markdown(f"**💬 Komentāri:** {comments}")
