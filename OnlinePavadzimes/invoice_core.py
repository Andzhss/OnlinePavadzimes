"""Rēķinu dati bez Streamlit: vēsture, klienti, sagataves, numerācija, Google Drive.

Izmanto gan Streamlit forma (app.py), gan Claude MCP serveris (mcp_server.py).
"""
import datetime
import json
import os
import base64
import fcntl
from contextlib import contextmanager

import pandas as pd
import requests

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Ja PAVADZ_DATA_DIR ir uzstādīts (Thinkpad serveris), dati glabājas tikai tur
# un GitHub netiek aiztikts. Bez tā — vecā Streamlit Cloud uzvedība (CSV repo).
DATA_DIR   = os.environ.get("PAVADZ_DATA_DIR") or BASE_DIR
LOCAL_MODE = bool(os.environ.get("PAVADZ_DATA_DIR"))
DOCS_DIR   = os.path.join(DATA_DIR, "docs")

CREDENTIALS_FILE = os.path.join(DATA_DIR if LOCAL_MODE else BASE_DIR, "credentials.json")
TOKEN_FILE = os.path.join(DATA_DIR, "token.json")
LOCK_FILE  = os.path.join(DATA_DIR, ".lock")

# Lokālie CSV faili
LOCAL_PRESETS_PATH    = os.path.join(DATA_DIR, "presets.csv")
LOCAL_HISTORY_PATH    = os.path.join(DATA_DIR, "invoice_history.csv")
LOCAL_TEST_HIST_PATH  = os.path.join(DATA_DIR, "test_invoice_history.csv")
LOCAL_CLIENTS_PATH    = os.path.join(DATA_DIR, "clients.csv")

# GitHub ceļi (repozitorijā)
GITHUB_REPO            = "Andzhss/OnlinePavadzimes"
GITHUB_PRESETS_PATH    = "OnlinePavadzimes/presets.csv"
GITHUB_HISTORY_PATH    = "OnlinePavadzimes/invoice_history.csv"
GITHUB_TEST_HIST_PATH  = "OnlinePavadzimes/test_invoice_history.csv"
GITHUB_CLIENTS_PATH    = "OnlinePavadzimes/clients.csv"

# Google Drive
GOOGLE_DRIVE_FOLDER_ID = "1vqhkHGH9WAMaFnXtduyyjYdEzHMx0iX9"
SCOPES = ['https://www.googleapis.com/auth/drive.file']

# CSV kolonnas vēsturei — JAUNAIS FORMĀTS
HISTORY_COLS = [
    'kartas_nr', 'datums', 'pr_partneris', 'pr_pvn_nr',
    'pr_datums', 'pr_numurs', 'darijuma_apraksts',
    'vertiba_bez_pvn', 'dabas_resursi', 'atlaides', 'pvn_summa', 'kopeja_summa',
    'due_date', 'client_reg_no', 'client_address', 'doc_type', 'items_json', 'comments', 'created_at',
    'language', 'vat_rate', 'vat_note'
]

# CSV kolonnas klientu sarakstam
CLIENTS_COLS = ['name', 'address', 'reg_no', 'vat_no', 'created_at']

# ---------------------------------------------------------------------------
# GitHub palīgfunkcijas
# ---------------------------------------------------------------------------

@contextmanager
def data_lock():
    """Viens rakstītājs vienlaikus — forma un Claude (MCP) raksta tos pašus CSV."""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(LOCK_FILE, "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)

def get_github_token():
    if LOCAL_MODE:
        return ""
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        try:
            import streamlit as st
            token = st.secrets.get("GITHUB_TOKEN", "")
        except Exception:
            token = ""
    return token.strip().strip('"').strip("'") if token else ""

def fetch_csv_from_github(github_path):
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
        print(f"Google Drive kļūda: {e}")
        return False

# ---------------------------------------------------------------------------
# Vēstures funkcijas (CSV bāzētas)
# ---------------------------------------------------------------------------

def _fmt(val):
    try:
        return f"{float(val):,.2f}".replace(",", "X").replace(".", ",").replace("X", " ")
    except Exception:
        return str(val)

def _migrate_old_history(df):
    records = []
    for i, (_, row) in enumerate(df.iterrows(), 1):
        items_str = row.get('items', '[]')
        try:
            items_list = json.loads(items_str) if pd.notna(items_str) and items_str else []
        except Exception:
            items_list = []
        base = sum(
            float(it.get('raw_qty', 0) or 0) * float(it.get('raw_price', 0) or 0)
            for it in items_list
        )
        try:
            total_val = float(str(row.get('total', '0')).replace('\u00a0', '').replace(' ', '').replace(',', '.'))
        except Exception:
            total_val = 0.0
        vat = round(total_val - base, 2)
        descriptions = [it.get('name', '') for it in items_list if it.get('name')]
        rec = {
            'kartas_nr':         i,
            'datums':            row.get('date', ''),
            'pr_partneris':      row.get('client_name', ''),
            'pr_pvn_nr':         row.get('client_vat_no', row.get('client_reg_no', '')),
            'pr_datums':         row.get('date', ''),
            'pr_numurs':         row.get('doc_id', ''),
            'darijuma_apraksts': '; '.join(descriptions),
            'vertiba_bez_pvn':   _fmt(base),
            'dabas_resursi':     '',
            'atlaides':          _fmt(0),
            'pvn_summa':         _fmt(vat),
            'kopeja_summa':      row.get('total', ''),
            'due_date':          row.get('due_date', ''),
            'client_reg_no':     row.get('client_reg_no', ''),
            'client_address':    row.get('client_address', ''),
            'doc_type':          row.get('doc_type', ''),
            'items_json':        items_str if pd.notna(items_str) else '[]',
            'comments':          row.get('comments', ''),
            'created_at':        row.get('created_at', ''),
            'items':             items_list,
            'doc_id':            row.get('doc_id', ''),
            'client_name':       row.get('client_name', ''),
            'client_vat_no':     row.get('client_vat_no', ''),
            'date':              row.get('date', ''),
            'total':             row.get('total', ''),
        }
        records.append(rec)
    return records

def load_history(local_path):
    if not os.path.exists(local_path):
        return []
    try:
        df = pd.read_csv(local_path, dtype=str)
        if df.empty:
            return []
        if 'doc_id' in df.columns and 'kartas_nr' not in df.columns:
            return _migrate_old_history(df)
        records = []
        for _, row in df.iterrows():
            rec = row.to_dict()
            items_str = rec.get('items_json', '[]')
            try:
                rec['items'] = json.loads(items_str) if pd.notna(items_str) and items_str else []
            except Exception:
                rec['items'] = []
            rec['doc_id']        = rec.get('pr_numurs', '')
            rec['client_name']   = rec.get('pr_partneris', '')
            rec['client_vat_no'] = rec.get('pr_pvn_nr', '')
            rec['date']          = rec.get('datums', '')
            rec['total']         = rec.get('kopeja_summa', '')
            records.append(rec)
        return records
    except Exception:
        return []

def _history_to_df(history):
    rows = []
    for entry in history:
        row = {col: entry.get(col, '') for col in HISTORY_COLS}
        items_val = entry.get('items_json', entry.get('items', []))
        if isinstance(items_val, list):
            row['items_json'] = json.dumps(items_val, ensure_ascii=False)
        else:
            row['items_json'] = items_val if items_val else '[]'
        rows.append(row)
    return pd.DataFrame(rows, columns=HISTORY_COLS) if rows else pd.DataFrame(columns=HISTORY_COLS)

def save_to_history(invoice_data, local_path, github_path):
    with data_lock():
        return _save_to_history(invoice_data, local_path, github_path)

def _save_to_history(invoice_data, local_path, github_path):
    history = load_history(local_path)
    items        = invoice_data.get('items', [])
    raw_total    = float(invoice_data.get('raw_total', 0) or 0)
    raw_discount = float(invoice_data.get('raw_discount_eur', 0) or 0)
    vat_amount   = round(float(invoice_data.get('raw_vat', 0) or 0), 2)
    base_amount  = round(raw_total - vat_amount, 2)
    descriptions = [it.get('name', '') for it in items if it.get('name')]
    pr_numurs    = invoice_data.get('doc_id', '')
    existing_nums = [int(str(e.get('kartas_nr', 0)).strip() or 0) for e in history]
    next_kartas   = max(existing_nums, default=0) + 1
    new_entry = {
        'kartas_nr':         next_kartas,
        'datums':            invoice_data.get('date', ''),
        'pr_partneris':      invoice_data.get('client_name', ''),
        'pr_pvn_nr':         invoice_data.get('client_vat_no', ''),
        'pr_datums':         invoice_data.get('date', ''),
        'pr_numurs':         pr_numurs,
        'darijuma_apraksts': '; '.join(descriptions),
        'vertiba_bez_pvn':   _fmt(base_amount),
        'dabas_resursi':     '',
        'atlaides':          _fmt(raw_discount),
        'pvn_summa':         _fmt(vat_amount),
        'kopeja_summa':      invoice_data.get('total', ''),
        'due_date':          invoice_data.get('due_date', ''),
        'client_reg_no':     invoice_data.get('client_reg_no', ''),
        'client_address':    invoice_data.get('client_address', ''),
        'doc_type':          invoice_data.get('doc_type', ''),
        'items_json':        json.dumps(items, ensure_ascii=False),
        'comments':          invoice_data.get('comments', ''),
        'created_at':        datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'language':          invoice_data.get('lang', 'lv'),
        'vat_rate':          invoice_data.get('vat_rate', 21) if invoice_data.get('vat_enabled', True) else 0,
        'vat_note':          invoice_data.get('vat_note', ''),
        'items':             items,
        'doc_id':            pr_numurs,
        'client_name':       invoice_data.get('client_name', ''),
        'client_vat_no':     invoice_data.get('client_vat_no', ''),
        'date':              invoice_data.get('date', ''),
        'total':             invoice_data.get('total', ''),
    }
    updated = False
    for i, entry in enumerate(history):
        if entry.get('pr_numurs') == pr_numurs or entry.get('doc_id') == pr_numurs:
            new_entry['kartas_nr'] = entry.get('kartas_nr', next_kartas)
            history[i] = new_entry
            updated = True
            break
    if not updated:
        history.append(new_entry)
    df = _history_to_df(history)
    # Šīs ir save_to_history beigas
    df.to_csv(local_path, index=False, encoding='utf-8')
    if LOCAL_MODE:
        return True, "Saglabāts serverī"
    if get_github_token():
        success, msg = push_csv_to_github(df, github_path, f"Pievieno {pr_numurs}")
        return success, msg
    else:
        return False, "Sistēmā nav ievadīts GITHUB_TOKEN"

def sync_history_from_github(local_path, github_path):
    content = fetch_csv_from_github(github_path)
    if content and ('doc_id' in content or 'kartas_nr' in content):
        with open(local_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False

def get_next_invoice_number(history):
    if not history:
        return 49
    max_num = 0
    for entry in history:
        doc = str(entry.get('pr_numurs', entry.get('doc_id', '')))
        parts = doc.split()
        if len(parts) > 1 and parts[-1].isdigit():
            num = int(parts[-1])
            if num > max_num:
                max_num = num
    return max_num + 1

# ---------------------------------------------------------------------------
# Klientu saraksta funkcijas (CSV bāzētas)
# ---------------------------------------------------------------------------

def _norm_client_name(name):
    """Normalizē klienta nosaukumu dedublikācijai."""
    return " ".join(str(name).strip().split()).lower()

def load_clients():
    if not LOCAL_MODE and not os.path.exists(LOCAL_CLIENTS_PATH):
        content = fetch_csv_from_github(GITHUB_CLIENTS_PATH)
        if content and 'name' in content:
            try:
                with open(LOCAL_CLIENTS_PATH, 'w', encoding='utf-8') as f:
                    f.write(content)
            except Exception:
                pass
    if not os.path.exists(LOCAL_CLIENTS_PATH):
        return []
    try:
        df = pd.read_csv(LOCAL_CLIENTS_PATH, dtype=str)
        if df.empty:
            return []
        return df.to_dict('records')
    except Exception:
        return []

def _clients_to_df(clients):
    rows = []
    for c in clients:
        row = {col: c.get(col, '') for col in CLIENTS_COLS}
        rows.append(row)
    return pd.DataFrame(rows, columns=CLIENTS_COLS) if rows else pd.DataFrame(columns=CLIENTS_COLS)

def save_clients(clients):
    df = _clients_to_df(clients)
    df.to_csv(LOCAL_CLIENTS_PATH, index=False, encoding='utf-8')

def push_clients_to_github(clients):
    df = _clients_to_df(clients)
    return push_csv_to_github(df, GITHUB_CLIENTS_PATH, "Update clients.csv via App")

def upsert_client(clients, name, address='', reg_no='', vat_no=''):
    """Pievieno vai atjauno klientu. Atgriež (clients, added). Bez duplikātiem.

    Duplikātu nosaka pēc normalizēta nosaukuma VAI pēc sakrītoša reģ. nr. /
    PVN nr. (lai viena firma ar atšķirīgu nosaukuma pierakstu neparādītos 2x).
    """
    name = str(name or '').strip()
    if not name:
        return clients, False
    key = _norm_client_name(name)
    reg = str(reg_no or '').strip()
    vat = str(vat_no or '').strip()
    for c in clients:
        c_name = _norm_client_name(c.get('name', ''))
        c_reg  = str(c.get('reg_no', '') or '').strip()
        c_vat  = str(c.get('vat_no', '') or '').strip()
        same_reg = bool(reg and c_reg and reg == c_reg)
        same_vat = bool(vat and c_vat and vat == c_vat)
        if c_name == key or same_reg or same_vat:
            if address: c['address'] = address
            if reg_no:  c['reg_no']  = reg_no
            if vat_no:  c['vat_no']  = vat_no
            return clients, False
    clients.append({
        'name':       name,
        'address':    str(address or ''),
        'reg_no':     str(reg_no or ''),
        'vat_no':     str(vat_no or ''),
        'created_at': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    return clients, True

def clients_from_history(history):
    """Apvieno klientu CSV ar vēsturi, deduplicē un saglabā atpakaļ."""
    clients = load_clients()
    changed = False
    for e in history:
        name = e.get('pr_partneris', e.get('client_name', ''))
        if not name:
            continue
        clients, added = upsert_client(
            clients,
            name,
            e.get('client_address', ''),
            e.get('client_reg_no', ''),
            e.get('pr_pvn_nr', e.get('client_vat_no', '')),
        )
        if added:
            changed = True
    if changed:
        with data_lock():
            save_clients(clients)
        if get_github_token():
            push_clients_to_github(clients)
    return clients

def record_client(invoice_data):
    """Pēc dokumenta izveides ieraksta klientu sarakstā (bez duplikātiem)."""
    name = str(invoice_data.get('client_name') or '').strip()
    if not name:
        return False, ""
    with data_lock():
        clients = load_clients()
        clients, added = upsert_client(
            clients,
            name,
            invoice_data.get('client_address', ''),
            invoice_data.get('client_reg_no', ''),
            invoice_data.get('client_vat_no', ''),
        )
        save_clients(clients)
    if added and get_github_token():
        success, msg = push_clients_to_github(clients)
        return added, (msg if success else "")
    return added, ""

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
# Rēķina aprēķins bez formas (Claude/MCP). Formulas tādas pašas kā app.py.
# ---------------------------------------------------------------------------

SIGNATORIES = ["Adrians Stankevičs", "Rihards Ozoliņš", "Ēriks Ušackis", "Aleks Kristiāns Grīnbergs"]
DOC_TYPES = ["Pavadzīme", "Rēķins", "Avansa rēķins"]
PROFORMA_TYPES = {
    "Pavadzīme":     "Proformas pavadzīme",
    "Rēķins":        "Proformas rēķins",
    "Avansa rēķins": "Proformas avansa rēķins",
}
VAT_RATE = 21


def fmt_curr(val):
    return f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", " ")


def build_invoice_data(*, doc_type, doc_id, client, items, lang='lv', vat_enabled=True, vat_note='',
                       discount_percent=0.0, advance_percent=50.0, date=None, due_days=7,
                       comments='', signatory='Adrians Stankevičs', signatory_title='', proforma=False):
    """Saliek invoice_data tādā pašā formā kā app.py, lai der pdf/docx ģeneratoriem un vēsturei."""
    from utils import money_to_words_lv, money_to_words_en
    from i18n import labels

    date = date or datetime.date.today()
    due_date = date + datetime.timedelta(days=int(due_days))

    rows = []
    for it in items:
        qty, price = float(it['qty']), float(it['price'])
        rows.append({
            'seq':       len(rows) + 1,
            'name':      it['name'],
            'unit':      it.get('unit') or 'Gab.',
            'qty':       str(qty),
            'price':     fmt_curr(price),
            'total':     fmt_curr(qty * price),
            'raw_qty':   qty,
            'raw_price': price,
        })

    subtotal = sum(r['raw_qty'] * r['raw_price'] for r in rows)
    discount_percent = float(discount_percent or 0)
    discount_eur = subtotal * discount_percent / 100
    after_discount = subtotal - discount_eur
    vat = after_discount * VAT_RATE / 100 if vat_enabled else 0.0
    total = after_discount + vat

    if doc_type == "Avansa rēķins":
        advance_payment = total * float(advance_percent) / 100
        words_amount = advance_payment
    else:
        advance_percent = 0.0
        advance_payment = total
        words_amount = total
    words = (money_to_words_en if lang == 'en' else money_to_words_lv)(words_amount)

    title = signatory_title or labels(lang)['default_title']
    if lang == 'en':
        full_signatory = f"{signatory}, {title}, SIA Bratus"
    else:
        full_signatory = f"SIA Bratus {title} {signatory}"

    return {
        'doc_type':                PROFORMA_TYPES.get(doc_type, doc_type) if proforma else doc_type,
        'doc_id':                  doc_id,
        'lang':                    lang,
        'vat_enabled':             vat_enabled,
        'vat_rate':                VAT_RATE,
        'vat_note':                vat_note if not vat_enabled else '',
        'raw_vat':                 vat,
        'date':                    date.strftime("%d.%m.%Y"),
        'due_date':                due_date.strftime("%d.%m.%Y"),
        'client_name':             client.get('name', ''),
        'client_address':          client.get('address', ''),
        'client_reg_no':           client.get('reg_no', ''),
        'client_vat_no':           client.get('vat_no', ''),
        'items':                   rows,
        'subtotal':                fmt_curr(subtotal),
        'vat':                     fmt_curr(vat),
        'total':                   fmt_curr(total),
        'raw_total':               total,
        'raw_advance':             advance_payment,
        'advance_percent':         advance_percent,
        'discount_eur':            fmt_curr(discount_eur),
        'raw_discount_eur':        discount_eur,
        'discount_percent':        discount_percent,
        'subtotal_after_discount': fmt_curr(after_discount),
        'amount_words':            words,
        'signatory':               full_signatory,
        'comments':                comments or '',
    }


def doc_filename(invoice_data, ext):
    from i18n import doc_type_label
    base = doc_type_label(invoice_data['doc_type'], invoice_data.get('lang', 'lv'))
    return f"{base.replace(' ', '_')}_{invoice_data['doc_id'].replace(' ', '_')}.{ext}"


def write_documents(invoice_data, upload=True):
    """Uzģenerē PDF un Word, saglabā DOCS_DIR un (ja pieslēgts) augšupielādē Google Drive."""
    from pdf_generator import generate_pdf
    from docx_generator import generate_docx

    os.makedirs(DOCS_DIR, exist_ok=True)
    out = {}
    for ext, gen, mime in [
        ('pdf', generate_pdf, 'application/pdf'),
        ('docx', generate_docx, 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'),
    ]:
        buf = gen(dict(invoice_data, items=[dict(i) for i in invoice_data['items']]))
        name = doc_filename(invoice_data, ext)
        with open(os.path.join(DOCS_DIR, name), 'wb') as f:
            f.write(buf.getvalue())
        drive_ok = upload_to_drive(buf, name, mime) if upload and get_drive_service() else False
        out[ext] = {'file': name, 'drive': drive_ok}
    return out
