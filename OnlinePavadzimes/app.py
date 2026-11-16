import streamlit as st
import datetime
import pandas as pd
import json
import os
import io
import requests
import base64
import hmac
import time

# --- Google Bibliotēkas ---
from google_auth_oauthlib.flow import InstalledAppFlow

from utils import scrape_lursoft, money_to_words_lv, money_to_words_en
from i18n import LANGUAGES, labels, doc_type_label
from pdf_generator import generate_pdf
from docx_generator import generate_docx

# --- Konfigurācija ---
st.set_page_config(page_title="SIA BRATUS Invoice Generator", layout="wide")

from invoice_core import (
    CREDENTIALS_FILE, TOKEN_FILE, SCOPES, GOOGLE_DRIVE_FOLDER_ID, LOCAL_MODE,
    LOCAL_PRESETS_PATH, LOCAL_HISTORY_PATH, LOCAL_TEST_HIST_PATH, LOCAL_CLIENTS_PATH,
    GITHUB_PRESETS_PATH, GITHUB_HISTORY_PATH, GITHUB_TEST_HIST_PATH,
    get_github_token, fetch_csv_from_github, push_csv_to_github,
    get_drive_service, upload_to_drive,
    load_history, _history_to_df, save_to_history, sync_history_from_github,
    get_next_invoice_number, _norm_client_name, clients_from_history, record_client,
    load_presets, save_presets, data_lock,
)

# ---------------------------------------------------------------------------
# Pavadzīmes ielāde formā
# ---------------------------------------------------------------------------

def load_invoice_into_form(entry):
    doc_id = str(entry.get('pr_numurs', entry.get('doc_id', '')))
    parts = doc_id.split()
    if len(parts) > 1 and parts[-1].isdigit():
        st.session_state.doc_number_input = int(parts[-1])
    st.session_state.client_data = {
        'name':    entry.get('pr_partneris', entry.get('client_name', '')),
        'address': entry.get('client_address', ''),
        'reg_no':  entry.get('client_reg_no', ''),
        'vat_no':  entry.get('pr_pvn_nr', entry.get('client_vat_no', ''))
    }
    st.session_state.client_select = entry.get('pr_partneris', entry.get('client_name', ''))
    st.session_state.last_client_select = st.session_state.client_select
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
    st.session_state.loaded_doc_type = loaded_type
    st.session_state.loaded_comments = entry.get('comments', '')
    # Vecajos ierakstos šo kolonnu nav (NaN) → LV ar PVN
    lang = entry.get('language', 'lv')
    st.session_state.loaded_lang = lang if lang in LANGUAGES.values() else 'lv'
    vat_rate = str(entry.get('vat_rate', '') or '').strip()
    st.session_state.loaded_vat_enabled = vat_rate not in ('0', '0.0')
    vat_note = entry.get('vat_note', '')
    st.session_state.loaded_vat_note = vat_note if isinstance(vat_note, str) else ''
    try:
        date_str = entry.get('datums', entry.get('date', ''))
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
        success, msg = save_to_history(invoice_data, LOCAL_TEST_HIST_PATH, GITHUB_TEST_HIST_PATH)
        if success:
            st.toast("✅ Proformas dokuments saglabāts vēsturē", icon="💾")
        else:
            st.error(f"⚠️ Kļūda saglabājot vēsturi: {msg}")
    else:
        success, msg = save_to_history(invoice_data, LOCAL_HISTORY_PATH, GITHUB_HISTORY_PATH)
        if success:
            st.toast("✅ Dokuments saglabāts vēsturē", icon="💾")
        else:
            st.error(f"⚠️ Kļūda saglabājot vēsturi: {msg}")

        added, cmsg = record_client(invoice_data)
        if added:
            st.toast("👤 Klients pievienots klientu sarakstam", icon="➕")
            
        if get_drive_service():
            success_drive = upload_to_drive(file_buffer, filename, mime_type)
            if success_drive:
                st.toast(f"✅ Saglabāts Drive: {filename}", icon="☁️")
            else:
                st.toast("⚠️ Kļūda saglabājot Drive", icon="❌")
        else:
            st.toast("Nav pieslēgts Google Drive (tikai lejupielādēts)", icon="⚠️")

# ---------------------------------------------------------------------------
# Sagataves
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Excel ģenerators vēsturei
# ---------------------------------------------------------------------------

def generate_history_excel(history):
    from openpyxl import Workbook
    from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "Rēķinu vēsture"

    header_fill  = PatternFill("solid", fgColor="D9E1F2")
    subhead_fill = PatternFill("solid", fgColor="E9EEF8")
    even_fill    = PatternFill("solid", fgColor="F2F5FC")
    odd_fill     = PatternFill("solid", fgColor="FFFFFF")
    header_font  = Font(name="Calibri", bold=True, size=9)
    data_font    = Font(name="Calibri", size=9)
    thin         = Side(style="thin", color="AAAAAA")
    border       = Border(left=thin, right=thin, top=thin, bottom=thin)

    headers_row1 = [
        ("Kārtas\nNr.",                                                           1, "center"),
        ("Datums",                                                                1, "center"),
        ("PR norādītais\ndarījuma partneris",                                     1, "left"),
        ("PR norādītā darījuma partnera\nreģistrācijas vai PVN maksātāja Nr.",    1, "center"),
        ("PR datums un numurs",                                                   2, "center"),
        ("Darījuma apraksts",                                                     1, "left"),
        ("PR norādītā\ndarījuma vērtība\n(bez PVN)",                              1, "right"),
        ("Dabas resursu\nun akcīzes\nnodokļi",                                    1, "right"),
        ("Piešķirtās\natlaides",                                                  1, "right"),
        ("PVN\nsumma",                                                            1, "right"),
        ("Kopējā\nsumma",                                                         1, "right"),
    ]

    col = 1
    for text, span, align in headers_row1:
        cell = ws.cell(row=1, column=col, value=text)
        cell.fill      = header_fill
        cell.font      = header_font
        cell.border    = border
        cell.alignment = Alignment(horizontal=align, vertical="center", wrap_text=True)
        if span == 2:
            ws.merge_cells(start_row=1, start_column=col, end_row=1, end_column=col + 1)
            ws.cell(row=1, column=col + 1).fill   = header_fill
            ws.cell(row=1, column=col + 1).border = border
        else:
            ws.merge_cells(start_row=1, start_column=col, end_row=2, end_column=col)
        col += span

    pr_col = 5
    for sub_col, sub_text in [(pr_col, "Datums"), (pr_col + 1, "Numurs")]:
        cell = ws.cell(row=2, column=sub_col, value=sub_text)
        cell.fill      = subhead_fill
        cell.font      = header_font
        cell.border    = border
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    ws.row_dimensions[1].height = 40
    ws.row_dimensions[2].height = 18

    for r_idx, entry in enumerate(history, start=3):
        row_fill = even_fill if r_idx % 2 == 0 else odd_fill
        values = [
            (entry.get('kartas_nr', ''),                                        "center"),
            (entry.get('datums', entry.get('date', '')),                        "center"),
            (entry.get('pr_partneris', entry.get('client_name', '')),           "left"),
            (entry.get('pr_pvn_nr', entry.get('client_vat_no', '')),            "center"),
            (entry.get('pr_datums', entry.get('date', '')),                     "center"),
            (entry.get('pr_numurs', entry.get('doc_id', '')),                   "center"),
            (entry.get('darijuma_apraksts', ''),                                "left"),
            (entry.get('vertiba_bez_pvn', ''),                                  "right"),
            (entry.get('dabas_resursi', '') or '—',                             "right"),
            (entry.get('atlaides', '') or '—',                                  "right"),
            (entry.get('pvn_summa', ''),                                        "right"),
            (entry.get('kopeja_summa', entry.get('total', '')),                 "right"),
        ]
        for c_idx, (val, align) in enumerate(values, start=1):
            cell = ws.cell(row=r_idx, column=c_idx, value=str(val) if val else '')
            cell.fill      = row_fill
            cell.font      = data_font
            cell.border    = border
            cell.alignment = Alignment(
                horizontal=align, vertical="center", wrap_text=(align == "left")
            )
        ws.row_dimensions[r_idx].height = 15

    col_widths = [8, 11, 28, 22, 11, 11, 40, 14, 12, 12, 12, 13]
    for i, w in enumerate(col_widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

    ws.freeze_panes = "A3"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()

# ---------------------------------------------------------------------------
# render_presets_app
# ---------------------------------------------------------------------------

def render_presets_app():
    st.header("Produktu un Pakalpojumu Sagataves")
    st.write("Šeit varat pievienot, labot un dzēst biežāk izmantotos produktus.")

    github_token = get_github_token()
    if not github_token and not LOCAL_MODE:
        st.warning("⚠️ GitHub Token nav atrasts. Izmaiņas tiks saglabātas tikai lokāli un pēc servera restartēšanas pazudīs.")
        with st.expander("Kā pieslēgt GitHub Token?"):
            st.markdown("1. Dodieties uz Streamlit Cloud → Manage app → Settings → Secrets.")
            st.markdown("2. Ievadiet:")
            st.code('GITHUB_TOKEN = "ghp_Jusu_GitHub_Token"')

    if "preset_editor_key" not in st.session_state:
        st.session_state.preset_editor_key = 0

    if not LOCAL_MODE and st.button("⬇️ Importēt no GitHub (Atjaunot)"):
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
            st.success("Saglabāts!" if LOCAL_MODE else "Saglabāts lokāli! (Nav GitHub Token)")

# ---------------------------------------------------------------------------
# render_invoice_app
# ---------------------------------------------------------------------------

def render_invoice_app():
    history      = load_history(LOCAL_HISTORY_PATH)
    test_history = load_history(LOCAL_TEST_HIST_PATH)
    next_number  = get_next_invoice_number(history)

    st.sidebar.header("Rēķina iestatījumi")

    if not LOCAL_MODE and st.sidebar.button("☁️ Ielādēt vēsturi no GitHub"):
        ok1 = sync_history_from_github(LOCAL_HISTORY_PATH, GITHUB_HISTORY_PATH)
        ok2 = sync_history_from_github(LOCAL_TEST_HIST_PATH, GITHUB_TEST_HIST_PATH)
        # Atjaunojam arī klientu sarakstu no GitHub
        if os.path.exists(LOCAL_CLIENTS_PATH):
            os.remove(LOCAL_CLIENTS_PATH)
        if ok1 or ok2:
            st.sidebar.success("Vēsture atjaunota!")
            st.rerun()
        else:
            st.sidebar.warning("Neizdevās sinhronizēt (tukša vēsture vai nav Token)")

    if 'doc_number_input' not in st.session_state:
        st.session_state.doc_number_input = next_number

    doc_number_input = st.sidebar.number_input(
        "Dokumenta Nr.", min_value=1, value=st.session_state.doc_number_input, step=1
    )
    doc_id = f"BR {doc_number_input:04d}"
    st.sidebar.markdown(f"**Dokumenta ID:** {doc_id}")
    if any(e.get('pr_numurs') == doc_id for e in history):
        st.sidebar.warning(f"{doc_id} jau ir vēsturē (iespējams, izveidots caur Claude). "
                           "Saglabājot tas tiks pārrakstīts — ja veido jaunu, nomaini numuru.")

    if history:
        last_num = get_next_invoice_number(history) - 1
        st.sidebar.info(f"📋 Pēdējā pavadzīme: **BR {last_num:04d}**")

    default_doc_date = st.session_state.get('loaded_doc_date', datetime.date.today())
    doc_date = st.sidebar.date_input("Datums", default_doc_date)

    default_due_date = st.session_state.get('loaded_due_date', doc_date + datetime.timedelta(days=7))
    due_date = st.sidebar.date_input("Apmaksāt līdz", default_due_date)

    st.sidebar.markdown("---")

    st.sidebar.subheader("📂 Atvērt iepriekšējo pavadzīmi")
    if history:
        hist_options = {
            f"{e.get('pr_numurs', e.get('doc_id',''))} — {e.get('pr_partneris', e.get('client_name',''))} ({e.get('datums', e.get('date',''))})": e
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

    st.sidebar.subheader("🔄 Testa pavadzīmju ielāde")
    if test_history:
        test_options = {
            f"{t.get('pr_numurs', t.get('doc_id',''))} — {t.get('pr_partneris', t.get('client_name',''))} ({t.get('datums', t.get('date',''))})": t
            for t in reversed(test_history)
        }
        selected_test_label = st.sidebar.selectbox("Izvēlies testa dokumentu", list(test_options.keys()))
        if st.sidebar.button("Ielādēt izvēlēto", key="load_test_btn"):
            load_invoice_into_form(test_options[selected_test_label])
            st.rerun()
    else:
        st.sidebar.info("Nav saglabātu testa pavadzīmju.")

    st.sidebar.markdown("---")

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
    # Klienta izvēle (dropdown) — augšā
    # -----------------------------------------------------------------------

    clients = clients_from_history(history)

    if 'client_data' not in st.session_state:
        st.session_state.client_data = {'name': '', 'address': '', 'reg_no': '', 'vat_no': ''}
    if 'client_select' not in st.session_state:
        st.session_state.client_select = "— Jauns klients —"
    if 'last_client_select' not in st.session_state:
        st.session_state.last_client_select = st.session_state.client_select

    client_names = ["— Jauns klients —"] + sorted(
        [str(c.get('name', '')).strip() for c in clients if str(c.get('name', '')).strip()],
        key=lambda x: x.lower()
    )

    if st.session_state.client_select not in client_names:
        st.session_state.client_select = "— Jauns klients —"
        st.session_state.last_client_select = "— Jauns klients —"

    default_client_index = (
        client_names.index(st.session_state.client_select)
        if st.session_state.client_select in client_names else 0
    )

    st.markdown("### 👤 Izvēlies klientu")
    col_client_dd, col_client_hint = st.columns([2, 1])
    with col_client_dd:
        selected_client = st.selectbox(
            "Klients no saraksta",
            client_names,
            index=default_client_index,
            key="client_select",
        )
    with col_client_hint:
        st.caption(
            "Ja klienta nav sarakstā, izvēlies „— Jauns klients —” un aizpildi datus zemāk. "
            "Pēc dokumenta saglabāšanas klients automātiski tiks pievienots sarakstam."
        )

    if selected_client != st.session_state.last_client_select:
        st.session_state.last_client_select = selected_client
        if selected_client != "— Jauns klients —":
            for c in clients:
                if str(c.get('name', '')).strip() == selected_client:
                    st.session_state.client_data = {
                        'name':    c.get('name', ''),
                        'address': c.get('address', ''),
                        'reg_no':  c.get('reg_no', ''),
                        'vat_no':  c.get('vat_no', ''),
                    }
                    break
            else:
                st.session_state.client_data = {
                    'name': selected_client, 'address': '', 'reg_no': '', 'vat_no': ''
                }

    st.markdown("---")

    # -----------------------------------------------------------------------
    # Klienta dati
    # -----------------------------------------------------------------------

    doc_types = ["Pavadzīme", "Rēķins", "Avansa rēķins", "E-rēķins"]
    dt_index = 0
    if 'loaded_doc_type' in st.session_state and st.session_state.loaded_doc_type in doc_types:
        dt_index = doc_types.index(st.session_state.loaded_doc_type)
    col_dt, col_lang, col_vat = st.columns([2, 1, 1])
    with col_dt:
        doc_type = st.selectbox("Dokumenta tips", doc_types, index=dt_index)
    with col_lang:
        lang_names = list(LANGUAGES.keys())
        loaded_lang = st.session_state.get('loaded_lang', 'lv')
        lang_index = list(LANGUAGES.values()).index(loaded_lang) if loaded_lang in LANGUAGES.values() else 0
        lang = LANGUAGES[st.selectbox("Dokumenta valoda", lang_names, index=lang_index)]
    with col_vat:
        st.write("")
        st.write("")
        vat_enabled = st.toggle("Piemērot PVN 21%", value=st.session_state.get('loaded_vat_enabled', True))
    vat_note = ""
    if not vat_enabled:
        vat_note = st.text_input(
            "PVN nepiemērošanas pamatojums (neobligāts, tiks parādīts dokumentā)",
            value=st.session_state.get('loaded_vat_note', ''),
            placeholder=("Reverse charge – Article 196 of Council Directive 2006/112/EC" if lang == 'en'
                         else "Nodokļa apgrieztā maksāšana – PVN likuma 143. pants"),
        )

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
                        # PVN: izmantojam scraped vērtību ja ir, citādi "LV"+reģ.nr., citādi "-"
                        if scraped.get('vat_no'):
                            st.session_state.client_data['vat_no'] = scraped['vat_no']
                        elif scraped.get('reg_no'):
                            st.session_state.client_data['vat_no'] = "LV" + scraped['reg_no']
                        else:
                            st.session_state.client_data['vat_no'] = "-"
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
            preset_options  = presets_df['NOSAUKUMS'].tolist()
            selected_preset = st.selectbox("Izvēlieties produktu", preset_options)
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
    display_df['DAUDZUMS']        = pd.to_numeric(display_df['DAUDZUMS'],        errors='coerce').fillna(0)
    display_df['CENA (EUR)']      = pd.to_numeric(display_df['CENA (EUR)'],      errors='coerce').fillna(0)
    display_df['Cena kopā (EUR)'] = display_df['DAUDZUMS'] * display_df['CENA (EUR)']

    edited_df = st.data_editor(
        display_df, num_rows="dynamic", width="stretch", hide_index=False,
        column_config={
            "CENA (EUR)":      st.column_config.NumberColumn(format="%.2f"),
            "DAUDZUMS":        st.column_config.NumberColumn(format="%.2f", step=0.01),
            "Cena kopā (EUR)": st.column_config.NumberColumn("Cena kopā (EUR)", disabled=True, format="%.2f")
        }
    )

    # Aizpildām noklusējuma vērtības jaunām rindām
    edited_df['Mērvienība'] = edited_df['Mērvienība'].fillna('Gab.').replace('', 'Gab.')
    edited_df['DAUDZUMS']   = edited_df['DAUDZUMS'].fillna(1.0).replace(0, 1.0)

    if st.button("🔄 Pārrēķināt summas"):
        st.session_state.items_df = edited_df.drop(columns=['Cena kopā (EUR)'], errors='ignore')
        st.rerun()

    # -----------------------------------------------------------------------
    # Aprēķini
    # -----------------------------------------------------------------------

    subtotal, vat, total             = 0.0, 0.0, 0.0
    advance_payment, advance_percent = 0.0, 0.0
    discount_eur, discount_percent   = 0.0, 0.0
    subtotal_after_discount          = 0.0
    amount_words                     = ""
    calc_df                          = edited_df.copy()

    def fmt_curr(val):
        return f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", " ")

    money_to_words = money_to_words_en if lang == 'en' else money_to_words_lv

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
            vat   = subtotal_after_discount * 0.21 if vat_enabled else 0.0
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
                amount_words = money_to_words(advance_payment)
                st.info(f"**Summa vārdiem (Avanss):** {amount_words}")
            else:
                advance_payment = total
                _, t_col2 = st.columns([3, 1])
                with t_col2:
                    st.markdown(f"**KOPĀ (bez PVN un atlaides):** € {fmt_curr(subtotal)}")
                    if discount_eur > 0:
                        st.markdown(f"**Atlaides apjoms ({discount_percent:g}%):** € -{fmt_curr(discount_eur)}")
                        st.markdown(f"**Kopā ar atlaidi (bez PVN):** € {fmt_curr(subtotal_after_discount)}")
                    st.markdown(f"**PVN ({21 if vat_enabled else 0}%):** € {fmt_curr(vat)}")
                    st.markdown(f"**KOPUMĀ APMAKSAI:** € {fmt_curr(total)}")
                amount_words = money_to_words(total)
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
        selected_signatory = st.selectbox("Dokumentu sagatavoja", signatory_options, index=1, key="sig_select")
    with col_sig2:
        signatory_title = st.text_input("Amats", labels(lang)['default_title'], key=f"sig_title_{lang}")
    if lang == 'en':
        full_signatory = f"{selected_signatory}, {signatory_title}, SIA Bratus"
    else:
        full_signatory = f"SIA Bratus {signatory_title} {selected_signatory}"
    st.caption(f"Paraksta laukā būs: {full_signatory}")

    # -----------------------------------------------------------------------
    # invoice_data salikšana
    # -----------------------------------------------------------------------

    invoice_data = {
        'doc_type':                doc_type,
        'doc_id':                  doc_id,
        'lang':                    lang,
        'vat_enabled':             vat_enabled,
        'vat_rate':                21,
        'vat_note':                vat_note,
        'raw_vat':                 vat,
        'date':                    doc_date.strftime("%d.%m.%Y"),
        'due_date':                due_date.strftime("%d.%m.%Y"),
        'client_name':             st.session_state.client_data['name'],
        'client_address':          st.session_state.client_data['address'],
        'client_reg_no':           st.session_state.client_data['reg_no'],
        'client_vat_no':           st.session_state.client_data['vat_no'],
        'items':                   [],
        'subtotal':                fmt_curr(subtotal),
        'vat':                     fmt_curr(vat),
        'total':                   fmt_curr(total),
        'raw_total':               total,
        'raw_advance':             advance_payment,
        'advance_percent':         advance_percent,
        'discount_eur':            fmt_curr(discount_eur),
        'raw_discount_eur':        discount_eur,
        'discount_percent':        discount_percent,
        'subtotal_after_discount': fmt_curr(subtotal_after_discount),
        'amount_words':            amount_words,
        'signatory':               full_signatory,
        'comments':                comments,
        'receiver_name':           st.session_state.get('e_invoice_data', {}).get('receiver_name', ''),
        'receiver_reg_no':         st.session_state.get('e_invoice_data', {}).get('receiver_reg_no', ''),
        'receiver_address':        st.session_state.get('e_invoice_data', {}).get('receiver_address', ''),
        'customer_name':           st.session_state.get('e_invoice_data', {}).get('customer_name', ''),
        'customer_reg_no':         st.session_state.get('e_invoice_data', {}).get('customer_reg_no', ''),
        'customer_address':        st.session_state.get('e_invoice_data', {}).get('customer_address', ''),
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
            "Pavadzīme":     "Proformas pavadzīme",
            "Rēķins":        "Proformas rēķins",
            "Avansa rēķins": "Proformas avansa rēķins"
        }
        invoice_data['doc_type'] = type_map.get(doc_type, doc_type)

    d_col1, d_col2 = st.columns(2)
    file_base = f"{doc_type_label(invoice_data['doc_type'], lang).replace(' ', '_')}_{doc_id.replace(' ', '_')}"

    try:
        pdf_file      = generate_pdf(invoice_data)
        file_name_pdf = f"{file_base}.pdf"
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
        file_name_docx = f"{file_base}.docx"
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
            excel_bytes = generate_history_excel(history)
            st.download_button(
                label="📥 Lejupielādēt kā Excel",
                data=excel_bytes,
                file_name=f"rekinu_vesture_{datetime.date.today().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            st.markdown("---")

            # Veidojam DataFrame no vēstures datiem
            hist_data = []
            for entry in history:
                hist_data.append({
                    "Kārtas Nr.": entry.get('kartas_nr', ''),
                    "Datums": entry.get('datums', entry.get('date', '')),
                    "Darījuma partneris": entry.get('pr_partneris', entry.get('client_name', '')),
                    "Reģ./PVN Nr.": entry.get('pr_pvn_nr', entry.get('client_vat_no', '')),
                    "PR datums": entry.get('pr_datums', entry.get('date', '')),
                    "PR numurs": entry.get('pr_numurs', entry.get('doc_id', '')),
                    "Darījuma apraksts": entry.get('darijuma_apraksts', ''),
                    "Vērtība (bez PVN)": entry.get('vertiba_bez_pvn', ''),
                    "Dabas resursi": entry.get('dabas_resursi', '') or '—',
                    "Atlaides": entry.get('atlaides', '') or '—',
                    "PVN summa": entry.get('pvn_summa', ''),
                    "Kopējā summa": entry.get('kopeja_summa', entry.get('total', '')),
                })
            hist_df = pd.DataFrame(hist_data)

            edited_hist_df = st.data_editor(
                hist_df,
                num_rows="fixed",
                use_container_width=True,
                hide_index=True,
                key="history_editor",
                disabled=hist_df.columns.tolist()
            )

            # Ja rindas tika dzēstas, parādām pogu saglabāšanai
            if len(edited_hist_df) < len(hist_df):
                deleted_count = len(hist_df) - len(edited_hist_df)
                st.warning(f"⚠️ {deleted_count} rinda(s) atzīmēta(s) dzēšanai.")
                if st.button("💾 Apstiprināt dzēšanu", type="primary"):
                    kept_nums = set(edited_hist_df["PR numurs"].tolist())
                    new_history = [e for e in history
                                   if e.get('pr_numurs', e.get('doc_id', '')) in kept_nums]
                    df = _history_to_df(new_history)
                    df.to_csv(LOCAL_HISTORY_PATH, index=False, encoding='utf-8')
                    if get_github_token():
                        success, msg = push_csv_to_github(df, GITHUB_HISTORY_PATH,
                                                          f"Dzēsti {deleted_count} ieraksti no vēstures")
                        if success:
                            st.success("✅ Vēsture atjaunināta un saglabāta GitHub!")
                        else:
                            st.warning(f"Lokāli saglabāts, bet GitHub kļūda: {msg}")
                    else:
                        st.success("✅ Vēsture atjaunināta lokāli!")
                    st.rerun()
        else:
            st.info("Vēsture ir tukša.")

# ---------------------------------------------------------------------------
# render_clients_app
# ---------------------------------------------------------------------------

def render_clients_app():
    st.header("📊 Klientu pārskats un statistika")
    st.write("Pārskats par visiem klientiem, dokumentu skaitu un kopējām summām.")

    if st.button("🔄 Atjaunot klientus no vēstures"):
        _history = load_history(LOCAL_HISTORY_PATH)
        _clients = clients_from_history(_history)
        st.success(f"Klientu sarakstā: {len(_clients)} ieraksti.")
        st.rerun()

    history = load_history(LOCAL_HISTORY_PATH)
    clients = clients_from_history(history)

    if not history and not clients:
        st.info("Nav datu — vispirms izveido dokumentus cilnē „Rēķina izveide”.")
        return

    # Agregējam datus pēc klienta
    agg = {}
    for e in history:
        name = str(e.get('pr_partneris', e.get('client_name', '')) or '').strip()
        if not name:
            continue
        key = _norm_client_name(name)
        try:
            total = float(
                str(e.get('kopeja_summa', e.get('total', '0')) or '0')
                .replace('\u00a0', '').replace(' ', '').replace(',', '.')
            )
        except Exception:
            total = 0.0
        a = agg.setdefault(key, {
            'name': name,
            'address': e.get('client_address', ''),
            'reg_no': e.get('client_reg_no', ''),
            'vat_no': e.get('pr_pvn_nr', e.get('client_vat_no', '')),
            'count': 0,
            'total': 0.0,
            'last_date': '',
        })
        a['count'] += 1
        a['total'] += total
        d = str(e.get('datums', e.get('date', '')) or '')
        if d and d > a['last_date']:
            a['last_date'] = d

    # Pievienojam klientus, kuriem vēl nav dokumentu
    for c in clients:
        name = str(c.get('name', '') or '').strip()
        if not name:
            continue
        key = _norm_client_name(name)
        if key not in agg:
            agg[key] = {
                'name': name,
                'address': c.get('address', ''),
                'reg_no': c.get('reg_no', ''),
                'vat_no': c.get('vat_no', ''),
                'count': 0,
                'total': 0.0,
                'last_date': '',
            }

    rows = sorted(agg.values(), key=lambda r: r['total'], reverse=True)
    stats_df = pd.DataFrame(rows)

    total_clients = len(rows)
    total_docs = int(sum(r['count'] for r in rows))
    total_sum = float(sum(r['total'] for r in rows))

    m1, m2, m3 = st.columns(3)
    with m1:
        st.metric("👥 Klientu skaits", total_clients)
    with m2:
        st.metric("📄 Dokumentu skaits", total_docs)
    with m3:
        st.metric("💶 Kopējā summa", f"€ {total_sum:,.2f}".replace(",", " "))

    st.markdown("---")

    # Top klientu diagramma
    if not stats_df.empty and float(stats_df['total'].sum()) > 0:
        st.subheader("🔝 Top klienti pēc apgrozījuma")
        top_df = stats_df.nlargest(10, 'total')[['name', 'total']].copy()
        top_df = top_df.rename(columns={'name': 'Klients', 'total': 'Summa (EUR)'})
        st.bar_chart(top_df.set_index('Klients'))

    st.markdown("---")
    st.subheader("📋 Klientu tabula")

    display = stats_df[['name', 'address', 'reg_no', 'vat_no', 'count', 'total', 'last_date']].copy()
    display = display.rename(columns={
        'name':      'Klients',
        'address':   'Adrese',
        'reg_no':    'Reģ. Nr.',
        'vat_no':    'PVN Nr.',
        'count':     'Dokumenti',
        'total':     'Kopējā summa (EUR)',
        'last_date': 'Pēdējais datums',
    })
    display['Kopējā summa (EUR)'] = pd.to_numeric(display['Kopējā summa (EUR)'], errors='coerce').fillna(0).round(2)

    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Kopējā summa (EUR)": st.column_config.NumberColumn(format="%.2f"),
            "Dokumenti": st.column_config.NumberColumn(format="%d"),
        },
    )

    # CSV lejupielāde
    csv_bytes = display.to_csv(index=False).encode('utf-8-sig')
    st.download_button(
        "📥 Lejupielādēt klientu pārskatu (CSV)",
        data=csv_bytes,
        file_name=f"klientu_parskats_{datetime.date.today().strftime('%Y%m%d')}.csv",
        mime="text/csv",
    )

# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def require_password():
    """Caur Cloudflare tuneli (publiski) prasa paroli; Tailscale tīklā — nē.
    Cloudflare vienmēr pieliek Cf-Connecting-Ip, tailscale serve to nedara."""
    if not LOCAL_MODE or 'cf-connecting-ip' not in {k.lower() for k in st.context.headers.keys()}:
        return True
    if st.session_state.get('authed'):
        return True
    password = os.environ.get("PAVADZ_PASSWORD", "")
    st.title("SIA BRATUS Rēķinu Ģenerators")
    with st.form("login"):
        pw = st.text_input("Parole", type="password")
        if st.form_submit_button("Ieiet"):
            if password and hmac.compare_digest(pw.encode(), password.encode()):
                st.session_state.authed = True
                st.rerun()
            time.sleep(2)
            st.error("Nepareiza parole")
    return False

def main():
    if not require_password():
        return
    st.title("SIA BRATUS Rēķinu Ģenerators")
    tab_invoice, tab_presets, tab_clients = st.tabs([
        "📄 Rēķina izveide", "⚙️ Produktu sagataves", "📊 Klientu pārskats"
    ])
    with tab_invoice:
        render_invoice_app()
    with tab_presets:
        render_presets_app()
    with tab_clients:
        render_clients_app()

if __name__ == "__main__":
    main()
