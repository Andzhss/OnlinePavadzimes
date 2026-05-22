import streamlit as st
import datetime
import pandas as pd
import json
import os
import io
import requests
import base64

# --- Google Bibliotēkas ---
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from utils import scrape_lursoft, money_to_words_lv
from pdf_generator import generate_pdf
from docx_generator import generate_docx

# --- Konfigurācija ---
st.set_page_config(page_title="SIA BRATUS Invoice Generator", layout="wide")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_FILE = os.path.join(BASE_DIR, "credentials.json")
TOKEN_FILE = os.path.join(BASE_DIR, "token.json")

# Lokālie CSV faili
LOCAL_PRESETS_PATH    = os.path.join(BASE_DIR, "presets.csv")
LOCAL_HISTORY_PATH    = os.path.join(BASE_DIR, "invoice_history.csv")
LOCAL_TEST_HIST_PATH  = os.path.join(BASE_DIR, "test_invoice_history.csv")

# GitHub ceļi (repozitorijā)
GITHUB_REPO            = "Andzhss/OnlinePavadzimes"
GITHUB_PRESETS_PATH    = "OnlinePavadzimes/presets.csv"
GITHUB_HISTORY_PATH    = "OnlinePavadzimes/invoice_history.csv"
GITHUB_TEST_HIST_PATH  = "OnlinePavadzimes/test_invoice_history.csv"

# Google Drive
GOOGLE_DRIVE_FOLDER_ID = "1vqhkHGH9WAMaFnXtduyyjYdEzHMx0iX9"
SCOPES = ['https://www.googleapis.com/auth/drive.file']

# CSV kolonnas vēsturei
HISTORY_COLS = [
    'doc_id', 'date', 'due_date', 'client_name', 'client_address',
    'client_reg_no', 'client_vat_no', 'doc_type', 'total',
    'items', 'comments', 'created_at'
]

# ---------------------------------------------------------------------------
# GitHub palīgfunkcijas
# ---------------------------------------------------------------------------

def get_github_token():
    token = st.secrets.get("GITHUB_TOKEN", "")
    return token.strip().strip('"').strip("'") if token else ""

def fetch_csv_from_github(github_path):
    """Atgriež CSV saturu kā tekstu vai None, ja neizdevās."""
    token = get_github_token()
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{github_path}"
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            content_b64 = r.json().get("content", "")
            if content_b64:
                return base64.b64decode(content_b64).decode("utf-8")
    except Exception:
        pass
    return None

def push_csv_to_github(df, github_path, commit_message="Update CSV via App"):
    """Saglabā DataFrame kā CSV uz GitHub. Atgriež (True/False, ziņojums)."""
    token = get_github_token()
    if not token:
        return False, "Nav GitHub Token"
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{github_path}"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }
        r = requests.get(url, headers=headers, timeout=10)
        sha = r.json().get("sha", "") if r.status_code == 200 else ""

        csv_content = df.to_csv(index=False)
        encoded = base64.b64encode(csv_content.encode("utf-8")).decode("utf-8")

        data = {"message": commit_message, "content": encoded, "branch": "main"}
        if sha:
            data["sha"] = sha

        put_r = requests.put(url, headers=headers, json=data, timeout=15)
        if put_r.status_code in [200, 201]:
            return True, "Veiksmīgi saglabāts GitHub!"
        else:
            return False, f"GitHub kļūda ({put_r.status_code})"
    except Exception as e:
        return False, str(e)

# ---------------------------------------------------------------------------
# Google Drive funkcijas
# ---------------------------------------------------------------------------

def get_drive_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        except Exception:
            os.remove(TOKEN_FILE)
            creds = None
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            with open(TOKEN_FILE, 'w') as f:
                f.write(creds.to_json())
        except Exception:
            if os.path.exists(TOKEN_FILE):
                os.remove(TOKEN_FILE)
            creds = None
    if creds and creds.valid:
        return build('drive', 'v3', credentials=creds)
    return None

def upload_to_drive(file_buffer, filename, mime_type):
    try:
        service = get_drive_service()
        if not service:
            return False
        file_metadata = {'name': filename, 'parents': [GOOGLE_DRIVE_FOLDER_ID]}
        file_buffer.seek(0)
        media = MediaIoBaseUpload(file_buffer, mimetype=mime_type, resumable=True)
        service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        file_buffer.seek(0)
        return True
    except Exception as e:
        st.error(f"❌ Kļūda Google Drive: {e}")
        return False

# ---------------------------------------------------------------------------
# Vēstures funkcijas (CSV bāzētas)
# ---------------------------------------------------------------------------

def load_history(local_path):
    """Ielādē vēsturi no lokālā CSV. Atgriež sarakstu ar dict."""
    if not os.path.exists(local_path):
        return []
    try:
        df = pd.read_csv(local_path, dtype=str)
        if df.empty:
            return []
        records = []
        for _, row in df.iterrows():
            rec = row.to_dict()
            items_str = rec.get('items', '[]')
            try:
                rec['items'] = json.loads(items_str) if pd.notna(items_str) and items_str else []
            except Exception:
                rec['items'] = []
            records.append(rec)
        return records
    except Exception:
        return []

def _history_to_df(history):
    """Pārvērš vēstures sarakstu par DataFrame CSV saglabāšanai."""
    rows = []
    for entry in history:
        row = {col: entry.get(col, '') for col in HISTORY_COLS}
        if isinstance(row['items'], list):
            row['items'] = json.dumps(row['items'], ensure_ascii=False)
        rows.append(row)
    return pd.DataFrame(rows, columns=HISTORY_COLS) if rows else pd.DataFrame(columns=HISTORY_COLS)

def save_to_history(invoice_data, local_path, github_path):
    """Saglabā pavadzīmi lokālā CSV un augšupielādē GitHub."""
    history = load_history(local_path)
    new_entry = {
        'doc_id':          invoice_data['doc_id'],
        'date':            invoice_data['date'],
        'due_date':        invoice_data.get('due_date', ''),
        'client_name':     invoice_data['client_name'],
        'client_address':  invoice_data.get('client_address', ''),
        'client_reg_no':   invoice_data.get('client_reg_no', ''),
        'client_vat_no':   invoice_data.get('client_vat_no', ''),
        'doc_type':        invoice_data['doc_type'],
        'total':           invoice_data.get('total', '0,00'),
        'items':           invoice_data.get('items', []),
        'comments':        invoice_data.get('comments', ''),
        'created_at':      datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    # Atjaunina vai pievieno
    updated = False
    for i, entry in enumerate(history):
        if entry.get('doc_id') == new_entry['doc_id']:
            history[i] = new_entry
            updated = True
            break
    if not updated:
        history.append(new_entry)

    # Saglabā lokāli
    df = _history_to_df(history)
    df.to_csv(local_path, index=False, encoding='utf-8')

    # Saglabā GitHub
    if get_github_token():
        push_csv_to_github(df, github_path, f"Pievieno {invoice_data['doc_id']}")

def sync_history_from_github(local_path, github_path):
    """Lejupielādē vēsturi no GitHub un saglabā lokāli."""
    content = fetch_csv_from_github(github_path)
    if content and 'doc_id' in content:
        with open(local_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False

def get_next_invoice_number(history):
    if not history:
        return 49
    max_num = 0
    for entry in history:
        parts = str(entry.get('doc_id', '')).split()
        if len(parts) > 1 and parts[-1].isdigit():
            num = int(parts[-1])
            if num > max_num:
                max_num = num
    return max_num + 1

# ---------------------------------------------------------------------------
# Pavadzīmes ielāde formā
# ---------------------------------------------------------------------------

def load_invoice_into_form(entry):
    """Ielādē vēstures ierakstu formas laukos."""
    doc_id = str(entry.get('doc_id', ''))
    parts = doc_id.split()
    if len(parts) > 1 and parts[-1].isdigit():
        st.session_state.doc_number_input = int(parts[-1])

    st.session_state.client_data = {
        'name':    entry.get('client_name', ''),
        'address': entry.get('client_address', ''),
        'reg_no':  entry.get('client_reg_no', ''),
        'vat_no':  entry.get('client_vat_no', '')
    }

    items_raw = entry.get('items', [])
    items_list = []
    for item in items_raw:
        try:
            qty   = float(item.get('raw_qty', item.get('qty', 0)) or 0)
            price = float(item.get('raw_price', 0) or 0)
        except Exception:
            qty, price = 0.0, 0.0
        items_list.append({
            "NOSAUKUMS":   item.get('name', ''),
            "Mērvienība":  item.get('unit', ''),
            "DAUDZUMS":    qty,
            "CENA (EUR)":  price
        })
    if items_list:
        st.session_state.items_df = pd.DataFrame(items_list)

    loaded_type = entry.get('doc_type', 'Pavadzīme')
    proforma_map = {
        "Proformas pavadzīme":     "Pavadzīme",
        "Proformas rēķins":        "Rēķins",
        "Proformas avansa rēķins": "Avansa rēķins"
    }
    loaded_type = proforma_map.get(loaded_type, loaded_type)
    st.session_state.loaded_doc_type    = loaded_type
    st.session_state.loaded_comments    = entry.get('comments', '')

    try:
        date_str = entry.get('date', '')
        if date_str:
            st.session_state.loaded_doc_date = datetime.datetime.strptime(date_str, "%d.%m.%Y").date()
        due_str = entry.get('due_date', '')
        if due_str:
            st.session_state.loaded_due_date = datetime.datetime.strptime(due_str, "%d.%m.%Y").date()
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Lejupielādes callback
# ---------------------------------------------------------------------------

def handle_download(invoice_data, file_buffer, filename, mime_type, is_proforma):
    if is_proforma:
        save_to_history(invoice_data, LOCAL_TEST_HIST_PATH, GITHUB_TEST_HIST_PATH)
        st.toast("✅ Proformas dokuments saglabāts vēsturē (GitHub)", icon="💾")
    else:
        save_to_history(invoice_data, LOCAL_HISTORY_PATH, GITHUB_HISTORY_PATH)
        if get_drive_service():
            success = upload_to_drive(file_buffer, filename, mime_type)
            if success:
                st.toast(f"✅ Saglabāts Drive: {filename}", icon="☁️")
            else:
                st.toast("⚠️ Kļūda saglabājot Drive", icon="❌")
        else:
            st.toast("Nav pieslēgts Google Drive (tikai lejupielādēts)", icon="⚠️")

# ---------------------------------------------------------------------------
# Sagataves
# ---------------------------------------------------------------------------

def load_presets():
    default_df = pd.DataFrame(columns=["NOSAUKUMS", "Mērvienība", "CENA (EUR)"])
    if os.path.exists(LOCAL_PRESETS_PATH):
        try:
            df = pd.read_csv(LOCAL_PRESETS_PATH)
            if df.empty or "NOSAUKUMS" not in df.columns:
                return default_df
            return df
        except Exception:
            return default_df
    return default_df

def save_presets(df):
    df.to_csv(LOCAL_PRESETS_PATH, index=False)

# ---------------------------------------------------------------------------
# render_presets_app
# ---------------------------------------------------------------------------

def render_presets_app():
    st.header("Produktu un Pakalpojumu Sagataves")
    st.write("Šeit varat pievienot, labot un dzēst biežāk izmantotos produktus.")

    github_token = get_github_token()
    if not github_token:
        st.warning("⚠️ GitHub Token nav atrasts. Izmaiņas tiks saglabātas tikai lokāli un pēc servera restartēšanas pazudīs.")
        with st.expander("Kā pieslēgt GitHub Token?"):
            st.markdown("1. Dodieties uz Streamlit Cloud → Manage app → Settings → Secrets.")
            st.markdown("2. Ievadiet:")
            st.code('GITHUB_TOKEN = "ghp_Jusu_GitHub_Token"')

    if "preset_editor_key" not in st.session_state:
        st.session_state.preset_editor_key = 0

    if st.button("⬇️ Importēt no GitHub (Atjaunot)"):
        content = fetch_csv_from_github(GITHUB_PRESETS_PATH)
        if content and "NOSAUKUMS" in content and "CENA (EUR)" in content:
            with open(LOCAL_PRESETS_PATH, "w", encoding='utf-8') as f:
                f.write(content)
            st.success("Sagataves veiksmīgi ielādētas no GitHub!")
            st.session_state.preset_editor_key += 1
            st.rerun()
        else:
            st.error("Neizdevās ielādēt sagataves no GitHub (pārbaudiet Token un faila esamību).")

    presets_df = load_presets()
    edited_presets = st.data_editor(
        presets_df,
        key=f"presets_editor_{st.session_state.preset_editor_key}",
        num_rows="dynamic",
        width="stretch",
        column_config={"CENA (EUR)": st.column_config.NumberColumn(format="%.2f", step=0.01)}
    )

    if st.button("💾 Saglabāt izmaiņas sagatavēs"):
        save_presets(edited_presets)
        if github_token:
            with st.spinner("Saglabā GitHub repozitorijā..."):
                success, msg = push_csv_to_github(edited_presets, GITHUB_PRESETS_PATH, "Update presets.csv via App")
                if success:
                    st.success(f"Saglabāts lokāli un {msg}")
                else:
                    st.warning(f"Lokāli saglabāts, bet GitHub kļūda: {msg}")
        else:
            st.success("Saglabāts lokāli! (Nav GitHub Token)")

# ---------------------------------------------------------------------------
# render_invoice_app
# ---------------------------------------------------------------------------

def render_invoice_app():
    history      = load_history(LOCAL_HISTORY_PATH)
    test_history = load_history(LOCAL_TEST_HIST_PATH)
    next_number  = get_next_invoice_number(history)

    st.sidebar.header("Rēķina iestatījumi")

    # --- Sinhronizācija no GitHub ---
    if st.sidebar.button("☁️ Ielādēt vēsturi no GitHub"):
        ok1 = sync_history_from_github(LOCAL_HISTORY_PATH, GITHUB_HISTORY_PATH)
        ok2 = sync_history_from_github(LOCAL_TEST_HIST_PATH, GITHUB_TEST_HIST_PATH)
        if ok1 or ok2:
            st.sidebar.success("Vēsture atjaunota!")
            st.rerun()
        else:
            st.sidebar.warning("Neizdevās sinhronizēt (tukša vēsture vai nav Token)")

    # --- Dokumenta numurs ---
    if 'doc_number_input' not in st.session_state:
        st.session_state.doc_number_input = next_number

    doc_number_input = st.sidebar.number_input(
        "Dokumenta Nr.", min_value=1, value=st.session_state.doc_number_input, step=1
    )
    doc_id = f"BR {doc_number_input:04d}"
    st.sidebar.markdown(f"**Dokumenta ID:** {doc_id}")

    # Pēdējās pavadzīmes numurs
    if history:
        last_num = get_next_invoice_number(history) - 1
        st.sidebar.info(f"📋 Pēdējā pavadzīme: **BR {last_num:04d}**")

    # --- Datumi ---
    default_doc_date = st.session_state.get('loaded_doc_date', datetime.date.today())
    doc_date = st.sidebar.date_input("Datums", default_doc_date)

    default_due_date = st.session_state.get('loaded_due_date', doc_date + datetime.timedelta(days=14))
    due_date = st.sidebar.date_input("Apmaksāt līdz", default_due_date)

    # --- Dokumenta tips ---
    doc_types = ["Pavadzīme", "Rēķins", "Avansa rēķins", "E-rēķins"]
    dt_index = 0
    if 'loaded_doc_type' in st.session_state and st.session_state.loaded_doc_type in doc_types:
        dt_index = doc_types.index(st.session_state.loaded_doc_type)
    doc_type = st.sidebar.selectbox("Dokumenta tips", doc_types, index=dt_index)

    st.sidebar.markdown("---")

    # --- Iepriekšējo pavadzīmju ielāde (īstās) ---
    st.sidebar.subheader("📂 Atvērt iepriekšējo pavadzīmi")
    if history:
        hist_options = {
            f"{e['doc_id']} — {e.get('client_name', '')} ({e.get('date', '')})": e
            for e in reversed(history)
        }
        selected_hist_label = st.sidebar.selectbox(
            "Izvēlies dokumentu", list(hist_options.keys()), key="hist_select"
        )
        if st.sidebar.button("📂 Ielādēt izvēlēto", key="load_hist_btn"):
            load_invoice_into_form(hist_options[selected_hist_label])
            st.rerun()
    else:
        st.sidebar.info("Nav saglabātu pavadzīmju.")

    st.sidebar.markdown("---")

    # --- Testa pavadzīmju ielāde ---
    st.sidebar.subheader("🔄 Testa pavadzīmju ielāde")
    if test_history:
        test_options = {
            f"{t['doc_id']} — {t.get('client_name', '')} ({t.get('date', '')})": t
            for t in reversed(test_history)
        }
        selected_test_label = st.sidebar.selectbox("Izvēlies testa dokumentu", list(test_options.keys()))
        if st.sidebar.button("Ielādēt izvēlēto", key="load_test_btn"):
            load_invoice_into_form(test_options[selected_test_label])
            st.rerun()
    else:
        st.sidebar.info("Nav saglabātu testa pavadzīmju.")

    st.sidebar.markdown("---")

    # --- Google Drive ---
    st.sidebar.subheader("Google Drive")
    if GOOGLE_DRIVE_FOLDER_ID:
        drive_url = f"https://drive.google.com/drive/folders/{GOOGLE_DRIVE_FOLDER_ID}"
        st.sidebar.link_button("📂 Atvērt Google Drive mapi", drive_url)

    service = get_drive_service()
    if service:
        st.sidebar.success("✅ Pieslēgts")
        if st.sidebar.button("Atslēgties"):
            if os.path.exists(TOKEN_FILE):
                os.remove(TOKEN_FILE)
            st.rerun()
    else:
        st.sidebar.warning("❌ Nav pieslēgts")
        if os.path.exists(CREDENTIALS_FILE):
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_FILE, SCOPES, redirect_uri='urn:ietf:wg:oauth:2.0:oob'
            )
            auth_url, _ = flow.authorization_url(prompt='consent')
            st.sidebar.markdown(f"**[1. Klikšķini šeit, lai autorizētos Google]({auth_url})**")
            auth_code = st.sidebar.text_input("2. Iekopē kodu šeit:")
            if st.sidebar.button("3. Apstiprināt kodu"):
                if auth_code:
                    try:
                        flow.fetch_token(code=auth_code)
                        creds = flow.credentials
                        with open(TOKEN_FILE, 'w') as token_file:
                            token_file.write(creds.to_json())
                        st.success("Veiksmīgi pieslēgts!")
                        st.rerun()
                    except Exception as e:
                        st.sidebar.error(f"Kļūda: {e}")
                else:
                    st.sidebar.error("Lūdzu ievadi kodu!")
        else:
            st.sidebar.error("Trūkst credentials.json faila!")

    st.sidebar.markdown("---")

    # --- Datu pārvaldība ---
    st.sidebar.subheader("Datu pārvaldība")
    if 'confirm_delete_history' not in st.session_state:
        st.session_state.confirm_delete_history = False

    if st.sidebar.button("🗑️ Dzēst visu rēķinu vēsturi"):
        st.session_state.confirm_delete_history = True

    if st.session_state.confirm_delete_history:
        st.sidebar.error("Vai tiešām dzēst visu vēsturi? Nevar atsaukt.")
        col_del_1, col_del_2 = st.sidebar.columns(2)
        if col_del_1.button("Jā, dzēst"):
            for p in [LOCAL_HISTORY_PATH, LOCAL_TEST_HIST_PATH]:
                if os.path.exists(p):
                    os.remove(p)
            st.session_state.confirm_delete_history = False
            st.rerun()
        if col_del_2.button("Atcelt"):
            st.session_state.confirm_delete_history = False
            st.rerun()

    # -----------------------------------------------------------------------
    # Klienta dati
    # -----------------------------------------------------------------------

    if 'client_data' not in st.session_state:
        st.session_state.client_data = {'name': '', 'address': '', 'reg_no': '', 'vat_no': ''}
    if 'e_invoice_data' not in st.session_state:
        st.session_state.e_invoice_data = {
            'receiver_name': '', 'receiver_reg_no': '', 'receiver_address': '',
            'customer_name': '', 'customer_reg_no': '', 'customer_address': ''
        }

    if doc_type != "E-rēķins":
        st.header("Klients")
        col1, col2 = st.columns([1, 1])
        with col1:
            lursoft_url = st.text_input("Lursoft saite")
            scrape_btn  = st.button("Ielādēt datus no Lursoft")
            if scrape_btn and lursoft_url:
                with st.spinner("Datu ielasīšana..."):
                    scraped = scrape_lursoft(lursoft_url)
                    if scraped:
                        if scraped.get('name'):    st.session_state.client_data['name']    = scraped['name']
                        if scraped.get('address'): st.session_state.client_data['address'] = scraped['address']
                        if scraped.get('reg_no'):  st.session_state.client_data['reg_no']  = scraped['reg_no']
                        st.session_state.client_data['vat_no'] = "LV" + scraped.get('reg_no', '')
                        st.success("Dati veiksmīgi ielasīti!")
                        st.rerun()
                    else:
                        st.error("Neizdevās ielasīt datus.")
        with col2:
            st.session_state.client_data['name']    = st.text_input("Nosaukums",  value=st.session_state.client_data['name'])
            st.session_state.client_data['address'] = st.text_input("Adrese",     value=st.session_state.client_data['address'])
            st.session_state.client_data['reg_no']  = st.text_input("Reģ. Nr.",  value=st.session_state.client_data['reg_no'])
            st.session_state.client_data['vat_no']  = st.text_input("PVN Nr.",   value=st.session_state.client_data['vat_no'])
    else:
        st.header("Saņēmējs un Pasūtītājs")
        col_rec, col_cus = st.columns(2)
        with col_rec:
            st.subheader("Saņēmējs")
            rec_name = st.text_input("Iestādes nosaukums (Saņēmējs)", value=st.session_state.e_invoice_data.get('receiver_name', ''), key='rec_n')
            rec_reg  = st.text_input("Reģistrācijas numurs (Saņēmējs)", value=st.session_state.e_invoice_data.get('receiver_reg_no', ''), key='rec_r')
            rec_addr = st.text_input("Juridiskā adrese (Saņēmējs)", value=st.session_state.e_invoice_data.get('receiver_address', ''), key='rec_a')
            st.session_state.e_invoice_data['receiver_name']    = rec_name
            st.session_state.e_invoice_data['receiver_reg_no']  = rec_reg
            st.session_state.e_invoice_data['receiver_address'] = rec_addr
        with col_cus:
            st.subheader("Pasūtītājs")
            cus_name = st.text_input("Nosaukums (Pasūtītājs)", value=st.session_state.e_invoice_data.get('customer_name', ''), key='cus_n')
            cus_reg  = st.text_input("Reģistrācijas numurs (Pasūtītājs)", value=st.session_state.e_invoice_data.get('customer_reg_no', ''), key='cus_r')
            cus_addr = st.text_input("Juridiskā adrese (Pasūtītājs)", value=st.session_state.e_invoice_data.get('customer_address', ''), key='cus_a')
            st.session_state.e_invoice_data['customer_name']    = cus_name
            st.session_state.e_invoice_data['customer_reg_no']  = cus_reg
            st.session_state.e_invoice_data['customer_address'] = cus_addr

    # -----------------------------------------------------------------------
    # Preces / Pakalpojumi
    # -----------------------------------------------------------------------

    st.markdown("---")
    st.header("Preces / Pakalpojumi")

    if 'items_df' not in st.session_state:
        initial_data = [{"NOSAUKUMS": "Lāzeriekārta; modeļa nr.: KH7050; 80W", "Mērvienība": "Gab.", "DAUDZUMS": 1.00, "CENA (EUR)": 4505.00}]
        st.session_state.items_df = pd.DataFrame(initial_data)

    st.subheader("Pievienot no sagatavēm")
    presets_df = load_presets()
    if not presets_df.empty:
        p_col1, p_col2, p_col3 = st.columns([3, 1, 1])
        with p_col1:
            preset_options     = presets_df['NOSAUKUMS'].tolist()
            selected_preset    = st.selectbox("Izvēlieties produktu", preset_options)
        with p_col2:
            preset_qty = st.number_input("Daudzums", min_value=0.01, value=1.00, step=0.01)
        with p_col3:
            st.write("")
            st.write("")
            if st.button("➕ Pievienot tabulai"):
                sel_row  = presets_df[presets_df['NOSAUKUMS'] == selected_preset].iloc[0]
                new_item = {
                    "NOSAUKUMS":  sel_row['NOSAUKUMS'],
                    "Mērvienība": sel_row['Mērvienība'],
                    "DAUDZUMS":   preset_qty,
                    "CENA (EUR)": sel_row['CENA (EUR)']
                }
                st.session_state.items_df = pd.concat(
                    [st.session_state.items_df, pd.DataFrame([new_item])], ignore_index=True
                )
                st.rerun()
    else:
        st.info("Sagatavju saraksts ir tukšs. Pievienojiet tos cilnē 'Produktu sagataves'.")

    display_df = st.session_state.items_df.copy()
    display_df['DAUDZUMS']         = pd.to_numeric(display_df['DAUDZUMS'],         errors='coerce').fillna(0)
    display_df['CENA (EUR)']       = pd.to_numeric(display_df['CENA (EUR)'],       errors='coerce').fillna(0)
    display_df['Cena kopā (EUR)']  = display_df['DAUDZUMS'] * display_df['CENA (EUR)']

    edited_df = st.data_editor(
        display_df, num_rows="dynamic", width="stretch", hide_index=False,
        column_config={
            "CENA (EUR)":      st.column_config.NumberColumn(format="%.2f"),
            "DAUDZUMS":        st.column_config.NumberColumn(format="%.2f", step=0.01),
            "Cena kopā (EUR)": st.column_config.NumberColumn("Cena kopā (EUR)", disabled=True, format="%.2f")
        }
    )

    if st.button("🔄 Pārrēķināt summas"):
        st.session_state.items_df = edited_df.drop(columns=['Cena kopā (EUR)'], errors='ignore')
        st.rerun()

    # -----------------------------------------------------------------------
    # Aprēķini
    # -----------------------------------------------------------------------

    subtotal, vat, total                 = 0.0, 0.0, 0.0
    advance_payment, advance_percent     = 0.0, 0.0
    discount_eur, discount_percent       = 0.0, 0.0
    subtotal_after_discount              = 0.0
    amount_words                         = ""
    calc_df                              = edited_df.copy()

    def fmt_curr(val):
        return f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", " ")

    try:
        if not edited_df.empty:
            calc_df['DAUDZUMS']   = pd.to_numeric(calc_df['DAUDZUMS'],   errors='coerce').fillna(0)
            calc_df['CENA (EUR)'] = pd.to_numeric(calc_df['CENA (EUR)'], errors='coerce').fillna(0)
            calc_df['KOPĀ (EUR)'] = calc_df['DAUDZUMS'] * calc_df['CENA (EUR)']
            subtotal = calc_df['KOPĀ (EUR)'].sum()

            st.markdown("### Atlaide")
            discount_type = st.radio("Atlaides veids:", ["Nav atlaides", "Procentos (%)", "Ciparos (EUR)"], horizontal=True)
            if discount_type == "Procentos (%)":
                discount_percent = st.number_input("Atlaides procenti (%)", 0.0, 100.0, 0.0, 5.0)
                discount_eur     = subtotal * (discount_percent / 100)
            elif discount_type == "Ciparos (EUR)":
                discount_eur     = st.number_input("Atlaides summa (EUR)", 0.0, subtotal, 0.0, 10.0)
                discount_percent = (discount_eur / subtotal * 100) if subtotal > 0 else 0

            subtotal_after_discount = subtotal - discount_eur
            vat   = subtotal_after_discount * 0.21
            total = subtotal_after_discount + vat

            if doc_type == "Avansa rēķins":
                st.markdown("### Avansa iestatījumi")
                calc_method = st.radio("Aprēķina veids:", ["Ciparos (EUR)", "Procentos (%)"], horizontal=True)
                if calc_method == "Ciparos (EUR)":
                    advance_payment = st.number_input("Summa (EUR)", 0.0, total, total, 10.0)
                    advance_percent = (advance_payment / total * 100) if total > 0 else 0
                else:
                    advance_percent = st.number_input("Procenti (%)", 0.0, 100.0, 50.0, 5.0)
                    advance_payment = total * (advance_percent / 100)

                _, t_col2 = st.columns([3, 1])
                with t_col2:
                    st.markdown(f"Kopējā pasūtījuma summa: € {fmt_curr(total)}")
                    st.markdown(f"**APMAKSĀJAMAIS AVANSS ({int(round(advance_percent))}%):** € {fmt_curr(advance_payment)}")
                amount_words = money_to_words_lv(advance_payment)
                st.info(f"**Summa vārdiem (Avanss):** {amount_words}")
            else:
                advance_payment = total
                _, t_col2 = st.columns([3, 1])
                with t_col2:
                    st.markdown(f"**KOPĀ (bez PVN un atlaides):** € {fmt_curr(subtotal)}")
                    if discount_eur > 0:
                        st.markdown(f"**Atlaides apjoms ({discount_percent:g}%):** € -{fmt_curr(discount_eur)}")
                        st.markdown(f"**Kopā ar atlaidi (bez PVN):** € {fmt_curr(subtotal_after_discount)}")
                    st.markdown(f"**PVN (21%):** € {fmt_curr(vat)}")
                    st.markdown(f"**KOPUMĀ APMAKSAI:** € {fmt_curr(total)}")
                amount_words = money_to_words_lv(total)
                st.info(f"**Summa vārdiem:** {amount_words}")
    except Exception as e:
        st.error(f"Kļūda aprēķinos: {e}")

    # -----------------------------------------------------------------------
    # Komentāri un Paraksti
    # -----------------------------------------------------------------------

    st.markdown("---")
    st.header("Komentāri un Paraksti")

    comments = st.text_area(
        "Papildus komentāri / piezīmes (tiks iekļauti dokumentā)",
        value=st.session_state.get('loaded_comments', '')
    )

    signatory_options = ["Adrians Stankevičs", "Rihards Ozoliņš", "Ēriks Ušackis", "Aleks Kristiāns Grīnbergs"]
    col_sig1, col_sig2 = st.columns(2)
    with col_sig1:
        selected_signatory = st.selectbox("Dokumentu sagatavoja", signatory_options, key="sig_select")
    with col_sig2:
        signatory_title = st.text_input("Amats", "valdes loceklis", key="sig_title")
    full_signatory = f"SIA Bratus {signatory_title} {selected_signatory}"
    st.caption(f"Paraksta laukā būs: {full_signatory}")

    # -----------------------------------------------------------------------
    # invoice_data salikšana
    # -----------------------------------------------------------------------

    invoice_data = {
        'doc_type':               doc_type,
        'doc_id':                 doc_id,
        'date':                   doc_date.strftime("%d.%m.%Y"),
        'due_date':               due_date.strftime("%d.%m.%Y"),
        'client_name':            st.session_state.client_data['name'],
        'client_address':         st.session_state.client_data['address'],
        'client_reg_no':          st.session_state.client_data['reg_no'],
        'client_vat_no':          st.session_state.client_data['vat_no'],
        'items':                  [],
        'subtotal':               fmt_curr(subtotal),
        'vat':                    fmt_curr(vat),
        'total':                  fmt_curr(total),
        'raw_total':              total,
        'raw_advance':            advance_payment,
        'advance_percent':        advance_percent,
        'discount_eur':           fmt_curr(discount_eur),
        'raw_discount_eur':       discount_eur,
        'discount_percent':       discount_percent,
        'subtotal_after_discount': fmt_curr(subtotal_after_discount),
        'amount_words':           amount_words,
        'signatory':              full_signatory,
        'comments':               comments,
        'receiver_name':          st.session_state.get('e_invoice_data', {}).get('receiver_name', ''),
        'receiver_reg_no':        st.session_state.get('e_invoice_data', {}).get('receiver_reg_no', ''),
        'receiver_address':       st.session_state.get('e_invoice_data', {}).get('receiver_address', ''),
        'customer_name':          st.session_state.get('e_invoice_data', {}).get('customer_name', ''),
        'customer_reg_no':        st.session_state.get('e_invoice_data', {}).get('customer_reg_no', ''),
        'customer_address':       st.session_state.get('e_invoice_data', {}).get('customer_address', ''),
    }

    if not edited_df.empty:
        for _, row in calc_df.iterrows():
            invoice_data['items'].append({
                'seq':       len(invoice_data['items']) + 1,
                'name':      row.get('NOSAUKUMS', ''),
                'unit':      row.get('Mērvienība', ''),
                'qty':       str(row.get('DAUDZUMS', 0)),
                'price':     fmt_curr(row.get('CENA (EUR)', 0)),
                'total':     fmt_curr(row.get('KOPĀ (EUR)', 0)),
                'raw_qty':   float(row.get('DAUDZUMS', 0)),
                'raw_price': float(row.get('CENA (EUR)', 0))
            })

    # -----------------------------------------------------------------------
    # Lejupielāde
    # -----------------------------------------------------------------------

    st.markdown("---")
    st.markdown("### Lejupielāde un Arhivēšana")

    is_proforma = st.toggle(
        "📝 Ģenerēt kā Proformas (testa) dokumentu", value=False,
        help="Ja ieslēgts: dokuments sauksies 'Proformas...', saglabāsies testa vēsturē un NETIKS augšupielādēts Google Drive."
    )

    if is_proforma:
        type_map = {
            "Pavadzīme":    "Proformas pavadzīme",
            "Rēķins":       "Proformas rēķins",
            "Avansa rēķins":"Proformas avansa rēķins"
        }
        invoice_data['doc_type'] = type_map.get(doc_type, doc_type)

    d_col1, d_col2 = st.columns(2)

    try:
        pdf_file      = generate_pdf(invoice_data)
        file_name_pdf = f"{invoice_data['doc_type'].replace(' ', '_')}_{doc_id.replace(' ', '_')}.pdf"
        with d_col1:
            st.download_button(
                label="📄 Lejupielādēt PDF",
                data=pdf_file,
                file_name=file_name_pdf,
                mime="application/pdf",
                on_click=handle_download,
                args=(invoice_data, pdf_file, file_name_pdf, "application/pdf", is_proforma)
            )
    except Exception as e:
        st.error(f"Kļūda PDF: {e}")

    try:
        docx_file      = generate_docx(invoice_data)
        file_name_docx = f"{invoice_data['doc_type'].replace(' ', '_')}_{doc_id.replace(' ', '_')}.docx"
        with d_col2:
            st.download_button(
                label="📝 Lejupielādēt Word",
                data=docx_file,
                file_name=file_name_docx,
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                on_click=handle_download,
                args=(invoice_data, docx_file, file_name_docx,
                      "application/vnd.openxmlformats-officedocument.wordprocessingml.document", is_proforma)
            )
    except Exception as e:
        st.error(f"Kļūda Word: {e}")

    # -----------------------------------------------------------------------
    # Vēstures tabula
    # -----------------------------------------------------------------------

    st.markdown("---")
    with st.expander("🗄️ Rēķinu vēsture (Izrakstītie)", expanded=False):
        if history:
            def fmt_lv(val):
                return f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", " ")

            rows_html = ""
            for i, entry in enumerate(reversed(history), 1):
                items_list = entry.get('items', [])
                base_amount = 0.0
                descriptions = []
                for item in items_list:
                    try:
                        raw_qty   = float(item.get('raw_qty', 0) or 0)
                        raw_price = float(item.get('raw_price', 0) or 0)
                        base_amount += raw_qty * raw_price
                        name = item.get('name', '')
                        if name:
                            descriptions.append(name)
                    except Exception:
                        pass

                total_str = str(entry.get('total', '0'))
                try:
                    total_val = float(total_str.replace('\u00a0', '').replace(' ', '').replace(',', '.'))
                except Exception:
                    total_val = 0.0

                vat_amount   = round(total_val - base_amount, 2)
                description  = "; ".join(descriptions)
                client_vat   = entry.get('client_vat_no', entry.get('client_reg_no', ''))

                rows_html += f"""
                <tr>
                    <td style="text-align:center">{i}</td>
                    <td style="text-align:center">{entry.get('date', '')}</td>
                    <td>{entry.get('client_name', '')}</td>
                    <td style="text-align:center">{client_vat}</td>
                    <td style="text-align:center">{entry.get('date', '')}</td>
                    <td style="text-align:center">{entry.get('doc_id', '')}</td>
                    <td style="max-width:220px; white-space:normal; word-break:break-word">{description}</td>
                    <td style="text-align:right">{fmt_lv(base_amount)}</td>
                    <td style="text-align:center">—</td>
                    <td style="text-align:center">—</td>
                    <td style="text-align:right">{fmt_lv(vat_amount)}</td>
                    <td style="text-align:right; font-weight:bold">{entry.get('total', '')}</td>
                </tr>
                """

            table_html = f"""
            <style>
            .inv-hist {{
                border-collapse: collapse;
                font-size: 11px;
                width: 100%;
            }}
            .inv-hist th, .inv-hist td {{
                border: 1px solid #bbb;
                padding: 4px 7px;
                vertical-align: middle;
            }}
            .inv-hist thead th {{
                background-color: #e8ecf0;
                text-align: center;
                font-weight: bold;
                line-height: 1.3;
            }}
            .inv-hist tbody tr:nth-child(even) {{
                background-color: #f5f8fb;
            }}
            .inv-hist tbody tr:hover {{
                background-color: #dceeff;
            }}
            </style>
            <div style="overflow-x:auto; margin-top:10px">
            <table class="inv-hist">
                <thead>
                    <tr>
                        <th rowspan="2" style="min-width:50px">Kārtas<br>Nr.</th>
                        <th rowspan="2" style="min-width:80px">Datums</th>
                        <th rowspan="2" style="min-width:150px">PR norādītais<br>darījuma partneris</th>
                        <th rowspan="2" style="min-width:140px">PR norādītā darījuma<br>partnera reģistrācijas<br>vai PVN maksātāja Nr.</th>
                        <th colspan="2" style="min-width:170px">PR datums un numurs</th>
                        <th rowspan="2" style="min-width:180px">Darījuma apraksts</th>
                        <th rowspan="2" style="min-width:100px">PR norādītā<br>darījuma vērtība<br>(bez PVN)</th>
                        <th rowspan="2" style="min-width:100px">Dabas resursu<br>un akcīzes<br>nodokļi</th>
                        <th rowspan="2" style="min-width:90px">Piešķirtās<br>atlaides</th>
                        <th rowspan="2" style="min-width:90px">PVN summa</th>
                        <th rowspan="2" style="min-width:100px">Kopējā<br>summa</th>
                    </tr>
                    <tr>
                        <th style="min-width:80px">Datums</th>
                        <th style="min-width:90px">Numurs</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html}
                </tbody>
            </table>
            </div>
            """
            st.markdown(table_html, unsafe_allow_html=True)
        else:
            st.info("Vēsture ir tukša.")

# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    st.title("SIA BRATUS Rēķinu Ģenerators")
    tab_invoice, tab_presets = st.tabs(["📄 Rēķina izveide", "⚙️ Produktu sagataves"])
    with tab_invoice:
        render_invoice_app()
    with tab_presets:
        render_presets_app()

if __name__ == "__main__":
    main()
