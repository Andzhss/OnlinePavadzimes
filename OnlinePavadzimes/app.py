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
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"  # Šeit glabāsies tava pieslēgšanās sesija

# !!! IELĪMĒ SAVU MAPES ID ŠEIT (no URL beigām) !!!
GOOGLE_DRIVE_FOLDER_ID = "1vqhkHGH9WAMaFnXtduyyjYdEzHMx0iX9" 

# Ja piekļuves līmenis (scopes) mainās, token.json būs jāizdzēš
SCOPES = ['https://www.googleapis.com/auth/drive.file']

# --- Google Drive Funkcija (OAuth) ---
def get_drive_service():
    """Autentifikācija un servisa izveide."""
    creds = None
    # 1. Mēģinām ielādēt saglabāto sesiju
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    
    # 2. Ja nav sesijas vai tā beigusies, prasām ielogoties
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                # Ja nevar atjaunot (piem., tokens anulēts), dzēšam un prasām no jauna
                os.remove(TOKEN_FILE)
                creds = None
        
        if not creds:
            if not os.path.exists(CREDENTIALS_FILE):
                st.error("⚠️ Trūkst `credentials.json` faila! (OAuth Client ID)")
                return None
                
            # Šis atvērs pārlūku uz servera (tava datora)
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0, open_browser=False)
            
        # 3. Saglabājam sesiju nākotnei
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())

    return build('drive', 'v3', credentials=creds)

def upload_to_drive(file_buffer, filename, mime_type):
    """Augšupielāde izmantojot OAuth."""
    try:
        service = get_drive_service()
        if not service:
            return False

        file_metadata = {
            'name': filename,
            'parents': [GOOGLE_DRIVE_FOLDER_ID]
        }

        # Reset buffer
        file_buffer.seek(0)
        media = MediaIoBaseUpload(file_buffer, mimetype=mime_type, resumable=True)

        # Izpilde
        service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        
        # Reset buffer again for download button
        file_buffer.seek(0)
        return True
        
    except Exception as e:
        st.error(f"❌ Kļūda augšupielādējot Google Drive: {e}")
        return False

# --- Vēstures Funkcijas ---
def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding='utf-8') as f:
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

def save_to_history(invoice_data):
    history = load_history()
    new_entry = {
        'doc_id': invoice_data['doc_id'],
        'date': invoice_data['date'],
        'client_name': invoice_data['client_name'],
        'doc_type': invoice_data['doc_type'],
        'total': invoice_data.get('total', '0.00'),
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
    with open(HISTORY_FILE, "w", encoding='utf-8') as f:
        json.dump(history, f, indent=4, ensure_ascii=False)

def handle_download(invoice_data, file_buffer, filename, mime_type):
    # 1. Saglabājam vietējā vēsturē
    save_to_history(invoice_data)
    
    # 2. Augšupielādējam uz Google Drive
    # Mēs izmantojam st.spinner, lai parādītu procesu
    # Piezīme: Streamlit callbacks nevar viegli izmantot UI elementus, 
    # bet spinner un toast parasti strādā.
    print(f"Sāku augšupielādi: {filename}") # Redzēsi terminālī
    success = upload_to_drive(file_buffer, filename, mime_type)
    
    if success:
        st.toast(f"✅ Saglabāts Google Drive: {filename}", icon="☁️")
    else:
        st.toast("⚠️ Neizdevās saglabāt Google Drive", icon="❌")

def main():
    st.title("SIA BRATUS Rēķinu Ģenerators")

    history = load_history()
    next_number = get_next_invoice_number(history)

    # --- Sāna josla ---
    st.sidebar.header("Iestatījumi")
    
    if 'doc_number_input' not in st.session_state:
        st.session_state.doc_number_input = next_number

    doc_number_input = st.sidebar.number_input(
        "Dokumenta Nr.", min_value=1, value=st.session_state.doc_number_input, step=1
    )
    doc_id = f"BR {doc_number_input:04d}" 
    st.sidebar.markdown(f"**Dokumenta ID:** {doc_id}")
    
    doc_date = st.sidebar.date_input("Datums", datetime.date.today())
    due_date = st.sidebar.date_input("Apmaksāt līdz", doc_date + datetime.timedelta(days=14))
    doc_type = st.sidebar.selectbox("Dokumenta tips", ["Pavadzīme", "Rēķins", "Avansa rēķins"])
    
    # --- Klienta dati ---
    st.header("Klients")
    col1, col2 = st.columns([1, 1])
    
    if 'client_data' not in st.session_state:
        st.session_state.client_data = {'name': '', 'address': '', 'reg_no': '', 'vat_no': ''}
        
    with col1:
        lursoft_url = st.text_input("Lursoft saite")
        scrape_btn = st.button("Ielādēt datus no Lursoft")
        if scrape_btn and lursoft_url:
            with st.spinner("Datu ielasīšana..."):
                scraped = scrape_lursoft(lursoft_url)
                if scraped:
                    if scraped.get('name'): st.session_state.client_data['name'] = scraped.get('name')
                    if scraped.get('address'): st.session_state.client_data['address'] = scraped.get('address')
                    if scraped.get('reg_no'): st.session_state.client_data['reg_no'] = scraped.get('reg_no')
                    st.session_state.client_data['vat_no'] = "LV" + scraped.get('reg_no')
                    st.success("Dati veiksmīgi ielasīti!")
                    st.rerun()
                else:
                    st.error("Neizdevās ielasīt datus.")
    
    with col2:
        st.session_state.client_data['name'] = st.text_input("Nosaukums", value=st.session_state.client_data['name'])
        st.session_state.client_data['address'] = st.text_input("Adrese", value=st.session_state.client_data['address'])
        st.session_state.client_data['reg_no'] = st.text_input("Reģ. Nr.", value=st.session_state.client_data['reg_no'])
        st.session_state.client_data['vat_no'] = st.text_input("PVN Nr.", value=st.session_state.client_data['vat_no'])

    st.markdown("---")
    
    # --- Preces ---
    st.header("Preces / Pakalpojumi")
    
    if 'items_df' not in st.session_state:
        initial_data = [{"NOSAUKUMS": "Lāzeriekārta; modeļa nr.: KH7050; 80W", "Mērvienība": "Gab.", "DAUDZUMS": 1, "CENA (EUR)": 4505.00}]
        st.session_state.items_df = pd.DataFrame(initial_data)
        
    edited_df = st.data_editor(
        st.session_state.items_df, num_rows="dynamic", use_container_width=True,
        column_config={"CENA (EUR)": st.column_config.NumberColumn(format="%.2f"), "DAUDZUMS": st.column_config.NumberColumn(step=1)}
    )
    
    # Aprēķini
    subtotal = 0.0
    vat = 0.0
    total = 0.0
    amount_words = ""
    advance_payment = 0.0
    advance_percent = 0.0
    
    def fmt_curr(val):
        return f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", " ")

    try:
        if not edited_df.empty:
            calc_df = edited_df.copy()
            calc_df['DAUDZUMS'] = pd.to_numeric(calc_df['DAUDZUMS'], errors='coerce').fillna(0)
            calc_df['CENA (EUR)'] = pd.to_numeric(calc_df['CENA (EUR)'], errors='coerce').fillna(0)
            calc_df['KOPĀ (EUR)'] = calc_df['DAUDZUMS'] * calc_df['CENA (EUR)']
            
            subtotal = calc_df['KOPĀ (EUR)'].sum()
            vat = subtotal * 0.21
            total = subtotal + vat
            
            if doc_type == "Avansa rēķins":
                st.markdown("### Avansa iestatījumi")
                calc_method = st.radio("Aprēķina veids:", ["Avansa rēķina apmaksājamā summa ciparos (EUR)", "Avansa rēķina apmaksājamā summa procentos (%)"], horizontal=True)
                
                if calc_method == "Avansa rēķina apmaksājamā summa ciparos (EUR)":
                    advance_payment = st.number_input("Summa (EUR)", 0.0, total, total, 10.0)
                    if total > 0:
                        advance_percent = (advance_payment / total) * 100
                    else:
                        advance_percent = 0
                else:
                    advance_percent_input = st.number_input("Procenti (%)", 0.0, 100.0, 50.0, 5.0)
                    advance_percent = advance_percent_input
                    advance_payment = total * (advance_percent / 100)
                
                t_col1, t_col2 = st.columns([3, 1])
                with t_col2:
                    st.markdown(f"Kopējā pasūtījuma summa: € {fmt_curr(total)}")
                    st.markdown(f"**APMAKSĀJAMAIS AVANSS ({int(round(advance_percent))}%):** € {fmt_curr(advance_payment)}")
                amount_words = money_to_words_lv(advance_payment)
                st.info(f"**Summa vārdiem (Avanss):** {amount_words}")
            else:
                advance_payment = total
                t_col1, t_col2 = st.columns([3, 1])
                with t_col2:
                    st.markdown(f"**KOPĀ:** € {fmt_curr(subtotal)}")
                    st.markdown(f"**PVN (21%):** € {fmt_curr(vat)}")
                    st.markdown(f"**Kopā ar PVN:** € {fmt_curr(total)}")
                amount_words = money_to_words_lv(total)
                st.info(f"**Summa vārdiem:** {amount_words}")
            
    except Exception as e:
        st.error(f"Kļūda aprēķinos: {e}")

    st.markdown("---")
    
    # --- Paraksti ---
    st.header("Paraksti")
    signatory_options = ["Adrians Stankevičs", "Rihards Ozoliņš", "Ēriks Ušackis", "Aleks Kristiāns Grīnbergs"]
    col_sig1, col_sig2 = st.columns(2)
    with col_sig1:
        selected_signatory = st.selectbox("Dokumentu sagatavoja", signatory_options, key="sig_select")
    with col_sig2:
        signatory_title = st.text_input("Amats", "valdes loceklis", key="sig_title")
    full_signatory = f"SIA Bratus {signatory_title} {selected_signatory}"
    st.caption(f"Paraksta laukā būs: {full_signatory}")
    
    # Datu sagatavošana
    invoice_data = {
        'doc_type': doc_type, 'doc_id': doc_id, 'date': doc_date.strftime("%d.%m.%Y"),
        'due_date': due_date.strftime("%d.%m.%Y"), 'client_name': st.session_state.client_data['name'],
        'client_address': st.session_state.client_data['address'], 'client_reg_no': st.session_state.client_data['reg_no'],
        'client_vat_no': st.session_state.client_data['vat_no'], 'items': [],
        'subtotal': fmt_curr(subtotal), 'vat': fmt_curr(vat), 'total': fmt_curr(total),
        'raw_total': total, 'raw_advance': advance_payment, 'advance_percent': advance_percent,
        'amount_words': amount_words, 'signatory': full_signatory
    }
    
    if not edited_df.empty:
        for index, row in calc_df.iterrows():
            invoice_data['items'].append({
                'name': row.get('NOSAUKUMS', ''), 'unit': row.get('Mērvienība', ''),
                'qty': str(row.get('DAUDZUMS', 0)), 'price': fmt_curr(row.get('CENA (EUR)', 0)),
                'total': fmt_curr(row.get('KOPĀ (EUR)', 0))
            })

    # --- LEJUPIELĀDE ---
    st.markdown("### Lejupielāde un Arhivēšana")
    st.caption("Pirmajā reizē atvērsies pārlūks, lai apstiprinātu piekļuvi Google Drive.")
    
    d_col1, d_col2 = st.columns(2)
    
    # PDF
    try:
        pdf_file = generate_pdf(invoice_data)
        file_name_pdf = f"{doc_type.replace(' ', '_')}_{doc_id.replace(' ', '_')}.pdf"
        
        with d_col1:
            st.download_button(
                label="📄 Lejupielādēt PDF",
                data=pdf_file,
                file_name=file_name_pdf,
                mime="application/pdf",
                on_click=handle_download,
                args=(invoice_data, pdf_file, file_name_pdf, "application/pdf")
            )
    except Exception as e:
        st.error(f"Kļūda PDF: {e}")
        
    # Docx
    try:
        docx_file = generate_docx(invoice_data)
        file_name_docx = f"{doc_type.replace(' ', '_')}_{doc_id.replace(' ', '_')}.docx"
        
        with d_col2:
            st.download_button(
                label="📝 Lejupielādēt Word",
                data=docx_file,
                file_name=file_name_docx,
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                on_click=handle_download,
                args=(invoice_data, docx_file, file_name_docx, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            )
    except Exception as e:
        st.error(f"Kļūda Word: {e}")

    # --- Vēsture ---
    st.markdown("---")
    with st.expander("🗄️ Rēķinu vēsture", expanded=False):
        if history:
            hist_df = pd.DataFrame(history)
            display_cols = ['doc_id', 'date', 'client_name', 'doc_type', 'total', 'created_at']
            rename_map = {'doc_id': 'Nr.', 'date': 'Datums', 'client_name': 'Klients', 
                          'doc_type': 'Tips', 'total': 'Summa (EUR)', 'created_at': 'Izveidots'}
            valid_cols = [c for c in display_cols if c in hist_df.columns]
            st.dataframe(hist_df[valid_cols].rename(columns=rename_map).sort_index(ascending=False), use_container_width=True)
        else:
            st.info("Vēsture ir tukša.")

if __name__ == "__main__":
    main()
