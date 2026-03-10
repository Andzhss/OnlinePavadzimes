import streamlit as st
import datetime
import pandas as pd
import json
import os
import io

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
HISTORY_FILE = "invoice_history.json"
TEST_HISTORY_FILE = "test_invoice_history.json"
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"

GOOGLE_DRIVE_FOLDER_ID = "1vqhkHGH9WAMaFnXtduyyjYdEzHMx0iX9" 
SCOPES = ['https://www.googleapis.com/auth/drive.file']

# --- Google Drive Funkcijas ---
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
            with open(TOKEN_FILE, 'w') as token:
                token.write(creds.to_json())
        except Exception:
            if os.path.exists(TOKEN_FILE): os.remove(TOKEN_FILE)
            creds = None

    if creds and creds.valid:
        return build('drive', 'v3', credentials=creds)
    return None

def upload_to_drive(file_buffer, filename, mime_type):
    try:
        service = get_drive_service()
        if not service:
            return False

        file_metadata = {
            'name': filename,
            'parents': [GOOGLE_DRIVE_FOLDER_ID]
        }
        file_buffer.seek(0)
        media = MediaIoBaseUpload(file_buffer, mimetype=mime_type, resumable=True)
        service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        file_buffer.seek(0)
        return True
    except Exception as e:
        st.error(f"❌ Kļūda Google Drive: {e}")
        return False

def load_history(filepath=HISTORY_FILE):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return []
    return []

def get_next_invoice_number(history):
    if not history:
        return 49
    max_num = 0
    for entry in history:
        doc_id = entry.get('doc_id', '')
        parts = doc_id.split()
        if len(parts) > 1 and parts[-1].isdigit():
            num = int(parts[-1])
            if num > max_num:
                max_num = num
    return max_num + 1

def save_to_history_generic(invoice_data, filepath):
    history = load_history(filepath)
    new_entry = {
        'doc_id': invoice_data['doc_id'],
        'date': invoice_data['date'],
        'due_date': invoice_data.get('due_date', ''),
        'client_name': invoice_data['client_name'],
        'client_address': invoice_data.get('client_address', ''),
        'client_reg_no': invoice_data.get('client_reg_no', ''),
        'client_vat_no': invoice_data.get('client_vat_no', ''),
        'doc_type': invoice_data['doc_type'],
        'total': invoice_data.get('total', '0.00'),
        'items': invoice_data.get('items', []),
        'comments': invoice_data.get('comments', ''),
        'created_at': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    updated = False
    for i, entry in enumerate(history):
        if entry['doc_id'] == new_entry['doc_id']:
            history[i] = new_entry
            updated = True
            break
    if not updated:
        history.append(new_entry)
    with open(filepath, "w", encoding='utf-8') as f:
        json.dump(history, f, indent=4, ensure_ascii=False)

def handle_download(invoice_data, file_buffer, filename, mime_type, is_proforma):
    if is_proforma:
        save_to_history_generic(invoice_data, TEST_HISTORY_FILE)
        st.toast("✅ Proformas dokuments saglabāts testa vēsturē", icon="💾")
    else:
        save_to_history_generic(invoice_data, HISTORY_FILE)
        if get_drive_service():
            with st.spinner("Augšupielādē Google Drive..."):
                success = upload_to_drive(file_buffer, filename, mime_type)
                if success:
                    st.toast(f"✅ Saglabāts Drive: {filename}", icon="☁️")
        else:
            st.toast("Nav pieslēgts Google Drive", icon="⚠️")

def load_test_invoice(selected_test):
    doc_num_str = selected_test.get('doc_id', '').split()[-1]
    if doc_num_str.isdigit():
        st.session_state.doc_number_input = int(doc_num_str)
        
    st.session_state.client_data = {
        'name': selected_test.get('client_name', ''),
        'address': selected_test.get('client_address', ''),
        'reg_no': selected_test.get('client_reg_no', ''),
        'vat_no': selected_test.get('client_vat_no', '')
    }
    
    items_list = []
    for i, item in enumerate(selected_test.get('items', [])):
        qty = item.get('raw_qty', float(item.get('qty', 0)))
        price = item.get('raw_price', 0.0)
        items_list.append({
            "Secība": i + 1,
            "NOSAUKUMS": item.get('name', ''),
            "Mērvienība": item.get('unit', ''),
            "DAUDZUMS": qty,
            "CENA (EUR)": price,
            "Cena kopā (EUR)": qty * price
        })
    st.session_state.items_df = pd.DataFrame(items_list)
    
    loaded_type = selected_test.get('doc_type', 'Pavadzīme')
    if "Proformas" in loaded_type:
        loaded_type = loaded_type.replace("Proformas ", "")
        
    st.session_state.loaded_doc_type = loaded_type
    st.session_state.loaded_comments = selected_test.get('comments', '')
    try:
        st.session_state.loaded_doc_date = datetime.datetime.strptime(selected_test.get('date', ''), "%d.%m.%Y").date()
        st.session_state.loaded_due_date = datetime.datetime.strptime(selected_test.get('due_date', ''), "%d.%m.%Y").date()
    except:
        pass

def main():
    st.title("SIA BRATUS Rēķinu Ģenerators")
    history = load_history(HISTORY_FILE)
    next_number = get_next_invoice_number(history)

    st.sidebar.header("Rēķina iestatījumi")
    if 'doc_number_input' not in st.session_state:
        st.session_state.doc_number_input = next_number

    doc_number_input = st.sidebar.number_input("Dokumenta Nr.", min_value=1, value=st.session_state.doc_number_input, step=1)
    doc_id = f"BR {doc_number_input:04d}" 
    st.sidebar.markdown(f"**Dokumenta ID:** {doc_id}")
    
    default_doc_date = st.session_state.get('loaded_doc_date', datetime.date.today())
    doc_date = st.sidebar.date_input("Datums", default_doc_date)
    default_due_date = st.session_state.get('loaded_due_date', doc_date + datetime.timedelta(days=14))
    due_date = st.sidebar.date_input("Apmaksāt līdz", default_due_date)
    
    doc_types = ["Pavadzīme", "Rēķins", "Avansa rēķins"]
    dt_index = 0
    if 'loaded_doc_type' in st.session_state and st.session_state.loaded_doc_type in doc_types:
        dt_index = doc_types.index(st.session_state.loaded_doc_type)
    doc_type = st.sidebar.selectbox("Dokumenta tips", doc_types, index=dt_index)
    
    st.sidebar.markdown("---")
    st.sidebar.subheader("🔄 Testa ielāde")
    test_history = load_history(TEST_HISTORY_FILE)
    if test_history:
        test_options = { f"{t['doc_id']} - {t.get('client_name','')}": t for t in reversed(test_history) }
        selected_test_label = st.sidebar.selectbox("Izvēlies testa dokumentu", list(test_options.keys()))
        if st.sidebar.button("Ielādēt izvēlēto"):
            load_test_invoice(test_options[selected_test_label])
            st.rerun()

    st.header("Klients")
    col1, col2 = st.columns([1, 1])
    if 'client_data' not in st.session_state:
        st.session_state.client_data = {'name': '', 'address': '', 'reg_no': '', 'vat_no': ''}
        
    with col1:
        lursoft_url = st.text_input("Lursoft saite")
        if st.button("Ielādēt datus no Lursoft") and lursoft_url:
            scraped = scrape_lursoft(lursoft_url)
            if scraped:
                st.session_state.client_data.update(scraped)
                st.session_state.client_data['vat_no'] = "LV" + scraped.get('reg_no', '')
                st.rerun()
    
    with col2:
        st.session_state.client_data['name'] = st.text_input("Nosaukums", st.session_state.client_data['name'])
        st.session_state.client_data['address'] = st.text_input("Adrese", st.session_state.client_data['address'])
        st.session_state.client_data['reg_no'] = st.text_input("Reģ. Nr.", st.session_state.client_data['reg_no'])
        st.session_state.client_data['vat_no'] = st.text_input("PVN Nr.", st.session_state.client_data['vat_no'])

    st.markdown("---")
    st.header("Preces / Pakalpojumi")
    
    if 'items_df' not in st.session_state:
        initial_data = [{"Secība": 1, "NOSAUKUMS": "Lāzeriekārta", "Mērvienība": "Gab.", "DAUDZUMS": 1.0, "CENA (EUR)": 4505.00, "Cena kopā (EUR)": 4505.00}]
        st.session_state.items_df = pd.DataFrame(initial_data)
        
    edited_df = st.data_editor(
        st.session_state.items_df, num_rows="dynamic", use_container_width=True,
        column_config={
            "Secība": st.column_config.NumberColumn("Secība", step=1),
            "CENA (EUR)": st.column_config.NumberColumn(format="%.2f"), 
            "DAUDZUMS": st.column_config.NumberColumn(format="%.2f", step=0.01),
            "Cena kopā (EUR)": st.column_config.NumberColumn(format="%.2f", disabled=True)
        }
    )
    
    def fmt_curr(val):
        return f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", " ")

    subtotal, vat, total = 0.0, 0.0, 0.0
    if not edited_df.empty:
        calc_df = edited_df.copy()
        calc_df['DAUDZUMS'] = pd.to_numeric(calc_df['DAUDZUMS'], errors='coerce').fillna(0)
        calc_df['CENA (EUR)'] = pd.to_numeric(calc_df['CENA (EUR)'], errors='coerce').fillna(0)
        calc_df['Cena kopā (EUR)'] = calc_df['DAUDZUMS'] * calc_df['CENA (EUR)']
        
        subtotal = calc_df['Cena kopā (EUR)'].sum()
        vat = subtotal * 0.21
        total = subtotal + vat
        
        t_col1, t_col2 = st.columns([3, 1])
        with t_col2:
            st.markdown(f"**KOPĀ:** € {fmt_curr(subtotal)}")
            st.markdown(f"**PVN (21%):** € {fmt_curr(vat)}")
            st.markdown(f"**Kopā ar PVN:** € {fmt_curr(total)}")
        amount_words = money_to_words_lv(total)
        st.info(f"**Summa vārdiem:** {amount_words}")

    st.markdown("---")
    comments = st.text_area("Papildus komentāri", st.session_state.get('loaded_comments', ''))
    
    signatory_options = ["Adrians Stankevičs", "Rihards Ozoliņš", "Ēriks Ušackis", "Aleks Kristiāns Grīnbergs"]
    selected_signatory = st.selectbox("Dokumentu sagatavoja", signatory_options)
    full_signatory = f"SIA Bratus valdes loceklis {selected_signatory}"
    
    invoice_data = {
        'doc_type': doc_type, 'doc_id': doc_id, 'date': doc_date.strftime("%d.%m.%Y"),
        'due_date': due_date.strftime("%d.%m.%Y"), 'client_name': st.session_state.client_data['name'],
        'client_address': st.session_state.client_data['address'], 'client_reg_no': st.session_state.client_data['reg_no'],
        'client_vat_no': st.session_state.client_data['vat_no'], 'items': [],
        'subtotal': fmt_curr(subtotal), 'vat': fmt_curr(vat), 'total': fmt_curr(total),
        'amount_words': amount_words, 'signatory': full_signatory, 'comments': comments
    }
    
    for _, row in calc_df.iterrows():
        invoice_data['items'].append({
            'name': row['NOSAUKUMS'], 'unit': row['Mērvienība'],
            'qty': f"{row['DAUDZUMS']:.2f}", 'price': fmt_curr(row['CENA (EUR)']),
            'total': fmt_curr(row['Cena kopā (EUR)']),
            'raw_qty': float(row['DAUDZUMS']), 'raw_price': float(row['CENA (EUR)'])
        })

    is_proforma = st.toggle("📝 Ģenerēt kā Proformas dokumentu")
    if is_proforma: invoice_data['doc_type'] = f"Proformas {doc_type}"
            
    d_col1, d_col2 = st.columns(2)
    with d_col1:
        pdf_file = generate_pdf(invoice_data)
        st.download_button("📄 Lejupielādēt PDF", pdf_file, f"{doc_id}.pdf", "application/pdf", on_click=handle_download, args=(invoice_data, pdf_file, f"{doc_id}.pdf", "application/pdf", is_proforma))
    with d_col2:
        docx_file = generate_docx(invoice_data)
        st.download_button("📝 Lejupielādēt Word", docx_file, f"{doc_id}.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", on_click=handle_download, args=(invoice_data, docx_file, f"{doc_id}.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", is_proforma))

if __name__ == "__main__":
    main()
