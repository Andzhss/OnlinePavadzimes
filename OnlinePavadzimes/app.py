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
HISTORY_FILE = "invoice_history.json"
TEST_HISTORY_FILE = "test_invoice_history.json"
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"

# !!! IELĪMĒ SAVU MAPES ID ŠEIT !!!
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

# --- Vēstures Funkcijas (Īstā un Testa) ---
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
        st.toast("✅ Proformas dokuments saglabāts lokālajā testa vēsturē", icon="💾")
    else:
        save_to_history_generic(invoice_data, HISTORY_FILE)
        if get_drive_service():
            with st.spinner("Augšupielādē Google Drive..."):
                success = upload_to_drive(file_buffer, filename, mime_type)
                if success:
                    st.toast(f"✅ Saglabāts Drive: {filename}", icon="☁️")
                else:
                    st.toast("⚠️ Kļūda saglabājot Drive", icon="❌")
        else:
            st.toast("Nav pieslēgts Google Drive (tikai lejupielādēts)", icon="⚠️")


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
        items_list.append({
            "Secība": i + 1,
            "NOSAUKUMS": item.get('name', ''),
            "Mērvienība": item.get('unit', ''),
            "DAUDZUMS": item.get('raw_qty', float(item.get('qty', 0))),
            "CENA (EUR)": item.get('raw_price', 0.0)
        })
    st.session_state.items_df = pd.DataFrame(items_list)
    
    # Atpazīstam proformas nosaukumus un ieliekam standarta
    loaded_type = selected_test.get('doc_type', 'Pavadzīme')
    if loaded_type == "Proformas pavadzīme": loaded_type = "Pavadzīme"
    elif loaded_type == "Proformas rēķins": loaded_type = "Rēķins"
    elif loaded_type == "Proformas avansa rēķins": loaded_type = "Avansa rēķins"
        
    st.session_state.loaded_doc_type = loaded_type
    st.session_state.loaded_comments = selected_test.get('comments', '')
    try:
        st.session_state.loaded_doc_date = datetime.datetime.strptime(selected_test.get('date', ''), "%d.%m.%Y").date()
        st.session_state.loaded_due_date = datetime.datetime.strptime(selected_test.get('due_date', ''), "%d.%m.%Y").date()
    except:
        pass



GITHUB_REPO = "Andzhss/OnlinePavadzimes"
GITHUB_FILE_PATH = "OnlinePavadzimes/presets.csv"

def load_presets():
    default_df = pd.DataFrame(columns=["NOSAUKUMS", "Mērvienība", "CENA (EUR)"])
    if os.path.exists("presets.csv"):
        try:
            df = pd.read_csv("presets.csv")
            if df.empty or "NOSAUKUMS" not in df.columns:
                return default_df
            return df
        except Exception:
            # Neļaut sabojātam CSV failam (vai HTML atbildei no Github) uzkārt aplikāciju
            return default_df
    return default_df

def save_presets(df):
    df.to_csv("presets.csv", index=False)

def save_presets_to_github(df, token):
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE_PATH}"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }

        # Vispirms iegūstam faila SHA (lai varētu to pārrakstītu)
        response = requests.get(url, headers=headers)
        sha = ""
        if response.status_code == 200:
            sha = response.json().get("sha", "")

        csv_content = df.to_csv(index=False)
        encoded_content = base64.b64encode(csv_content.encode("utf-8")).decode("utf-8")

        data = {
            "message": "Update presets.csv via App",
            "content": encoded_content,
            "branch": "main"
        }
        if sha:
            data["sha"] = sha

        put_response = requests.put(url, headers=headers, json=data)
        if put_response.status_code in [200, 201]:
            return True, "Veiksmīgi saglabāts GitHub repozitorijā!"
        else:
            return False, f"Kļūda GitHub saglabāšanā: {put_response.text}"
    except Exception as e:
        return False, str(e)

def render_presets_app():
    st.header("Produktu un Pakalpojumu Sagataves")
    st.write("Šeit varat pievienot, labot un dzēst biežāk izmantotos produktus.")

    github_token = st.secrets.get("GITHUB_TOKEN", "")

    if not github_token:
        st.warning("⚠️ GitHub Token nav atrasts. Izmaiņas tiks saglabātas tikai lokāli un pēc servera pārstartēšanas pazudīs.")
        with st.expander("Kā pieslēgt GitHub Token?"):
            st.markdown("1. Dodieties uz Streamlit Cloud vadības paneli (Manage app -> Settings -> Secrets).")
            st.markdown("2. Ievadiet Jūsu GitHub atslēgu šādā formātā:")
            st.code('GITHUB_TOKEN = "ghp_Jusu_GitHub_Token"')

    # Importēt pogas kolonnas virs tabulas
    c1, c2 = st.columns([1, 1])
    with c1:
        if st.button("⬇️ Importēt no GitHub (Atjaunot)"):
            try:
                # Lai apietu kešatmiņu, varam pievienot headerus (īpaši noderīgi privātiem repozitorijiem, ja ir token)
                headers = {}
                if github_token:
                    headers["Authorization"] = f"token {github_token}"

                raw_url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{GITHUB_FILE_PATH}"
                response = requests.get(raw_url, headers=headers)
                if response.status_code == 200:
                    with open("presets.csv", "wb") as f:
                        f.write(response.content)
                    st.success("Sagataves veiksmīgi ielādētas no GitHub!")
                    st.rerun()
                else:
                    st.error("Neizdevās lejupielādēt failu no GitHub (iespējams tas ir privāts vai vēl nepastāv).")
            except Exception as e:
                st.error(f"Kļūda: {e}")

    presets_df = load_presets()
    edited_presets = st.data_editor(
        presets_df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "CENA (EUR)": st.column_config.NumberColumn(format="%.2f", step=0.01)
        }
    )

    if st.button("💾 Saglabāt izmaiņas sagatavēs"):
        save_presets(edited_presets)

        # Ja ievadīts token, saglabājam arī GitHub
        if github_token:
            with st.spinner("Saglabā GitHub repozitorijā..."):
                success, msg = save_presets_to_github(edited_presets, github_token)
                if success:
                    st.success(f"Lieliski! Dati saglabāti lokāli un {msg}")
                else:
                    st.warning(f"Lokāli saglabāts, bet GitHub saglabāšana neizdevās: {msg}")
        else:
            st.success("Sagataves veiksmīgi saglabātas tikai lokāli! (Pievienojiet Token augstāk, lai tās nepazustu)")

def render_invoice_app():
    history = load_history(HISTORY_FILE)
    next_number = get_next_invoice_number(history)

    # --- SĀNA JOSLA: 1. Dokumenta Dati ---
    st.sidebar.header("Rēķina iestatījumi")

    if 'doc_number_input' not in st.session_state:
        st.session_state.doc_number_input = next_number

    doc_number_input = st.sidebar.number_input(
        "Dokumenta Nr.", min_value=1, value=st.session_state.doc_number_input, step=1
    )
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

    # --- SĀNA JOSLA: 2. Testa Pavadzīmju Ielāde ---
    st.sidebar.subheader("🔄 Testa pavadzīmju ielāde")
    test_history = load_history(TEST_HISTORY_FILE)
    if test_history:
        test_options = { f"{t['doc_id']} - {t.get('client_name','')} ({t.get('date','')})": t for t in reversed(test_history) }
        selected_test_label = st.sidebar.selectbox("Izvēlies testa dokumentu", list(test_options.keys()))
        if st.sidebar.button("Ielādēt izvēlēto"):
            load_test_invoice(test_options[selected_test_label])
            st.rerun()
    else:
        st.sidebar.info("Nav saglabātu testa pavadzīmju.")

    st.sidebar.markdown("---")

    # --- SĀNA JOSLA: 3. Google Drive ---
    st.sidebar.subheader("Google Drive")
    if GOOGLE_DRIVE_FOLDER_ID:
        drive_url = f"https://drive.google.com/drive/folders/{GOOGLE_DRIVE_FOLDER_ID}"
        st.sidebar.link_button("📂 Atvērt Google Drive mapi", drive_url)

    service = get_drive_service()
    if service:
        st.sidebar.success("✅ Pieslēgts")
        if st.sidebar.button("Atslēgties"):
            if os.path.exists(TOKEN_FILE): os.remove(TOKEN_FILE)
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
                        with open(TOKEN_FILE, 'w') as token:
                            token.write(creds.to_json())
                        st.success("Veiksmīgi pieslēgts!")
                        st.rerun()
                    except Exception as e:
                        st.sidebar.error(f"Kļūda: {e}")
                else:
                    st.sidebar.error("Lūdzu ievadi kodu!")
        else:
            st.sidebar.error("Trūkst credentials.json faila!")

    st.sidebar.markdown("---")
    
    # --- SĀNA JOSLA: 4. Datu Pārvaldība ---
    st.sidebar.subheader("Datu pārvaldība")
    if 'confirm_delete_history' not in st.session_state:
        st.session_state.confirm_delete_history = False

    if st.sidebar.button("🗑️ Dzēst visu rēķinu vēsturi"):
        st.session_state.confirm_delete_history = True

    if st.session_state.confirm_delete_history:
        st.sidebar.error("Vai tiešām dzēst visu vēsturi? Nevar atsaukt.")
        col_del_1, col_del_2 = st.sidebar.columns(2)
        if col_del_1.button("Jā, dzēst"):
            if os.path.exists(HISTORY_FILE): os.remove(HISTORY_FILE)
            if os.path.exists(TEST_HISTORY_FILE): os.remove(TEST_HISTORY_FILE)
            st.session_state.confirm_delete_history = False
            st.rerun()
        if col_del_2.button("Atcelt"):
            st.session_state.confirm_delete_history = False
            st.rerun()
    
    # --- GALVENAIS SATURS ---
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
    st.header("Preces / Pakalpojumi")
    
    if 'items_df' not in st.session_state:
        initial_data = [{"NOSAUKUMS": "Lāzeriekārta; modeļa nr.: KH7050; 80W", "Mērvienība": "Gab.", "DAUDZUMS": 1.00, "CENA (EUR)": 4505.00}]
        # Secības kolonnu vairs nelietosim tabulā
        st.session_state.items_df = pd.DataFrame(initial_data)
        
        # Jau ielādētās vecās sesijas var saturēt "Secība" kolonnu - izdzēšam to, lai nerādītos.
        if "Secība" in st.session_state.items_df.columns:
            st.session_state.items_df = st.session_state.items_df.drop(columns=["Secība"])

    # --- SAGATAVJU PIEVIENOŠANA ---
    st.subheader("Pievienot no sagatavēm")
    presets_df = load_presets()
    if not presets_df.empty:
        p_col1, p_col2, p_col3 = st.columns([3, 1, 1])
        with p_col1:
            preset_options = presets_df['NOSAUKUMS'].tolist()
            selected_preset_name = st.selectbox("Izvēlieties produktu", preset_options)
        with p_col2:
            preset_qty = st.number_input("Daudzums", min_value=0.01, value=1.00, step=0.01)
        with p_col3:
            st.write("") # Spacer for vertical alignment
            st.write("")
            if st.button("➕ Pievienot tabulai"):
                selected_row = presets_df[presets_df['NOSAUKUMS'] == selected_preset_name].iloc[0]
                new_item = {
                    "NOSAUKUMS": selected_row['NOSAUKUMS'],
                    "Mērvienība": selected_row['Mērvienība'],
                    "DAUDZUMS": preset_qty,
                    "CENA (EUR)": selected_row['CENA (EUR)']
                }
                st.session_state.items_df = pd.concat([st.session_state.items_df, pd.DataFrame([new_item])], ignore_index=True)
                st.rerun()
    else:
        st.info("Sagatavju saraksts ir tukšs. Pievienojiet tos sānu izvēlnes sadaļā 'Produktu sagataves'.")

    # Aprēķinām "Cena kopā (EUR)", lai tā parādītos tabulā katru reizi, kad lapa tiek pārzīmēta
    display_df = st.session_state.items_df.copy()
    display_df['DAUDZUMS'] = pd.to_numeric(display_df['DAUDZUMS'], errors='coerce').fillna(0)
    display_df['CENA (EUR)'] = pd.to_numeric(display_df['CENA (EUR)'], errors='coerce').fillna(0)
    display_df['Cena kopā (EUR)'] = display_df['DAUDZUMS'] * display_df['CENA (EUR)']

    # Atļaujam rindu pārkārtošanu (Drag & Drop), izmantojot Streamlit noklusēto indeksu
    edited_df = st.data_editor(
        display_df, num_rows="dynamic", use_container_width=True, hide_index=False,
        column_config={
            "CENA (EUR)": st.column_config.NumberColumn(format="%.2f"), 
            "DAUDZUMS": st.column_config.NumberColumn(format="%.2f", step=0.01),
            "Cena kopā (EUR)": st.column_config.NumberColumn("Cena kopā (EUR)", disabled=True, format="%.2f")
        }
    )
    
    # Atjauninām st.session_state.items_df bez "Cena kopā (EUR)", lai piefiksētu lietotāja veiktās izmaiņas.
    # Tas ļaus st.data_editor() automātiski atjaunoties pēc šūnas rediģēšanas, jo streamlit
    # pārzīmēs lapu un 'Cena kopā (EUR)' tiks pārrēķināta sākumā, ja vērtības atšķiras.
    updated_items_df = edited_df.drop(columns=['Cena kopā (EUR)'], errors='ignore')

    # Poga lapas pārzīmēšanai un jaunās summas atjaunošanai
    if st.button("🔄 Pārrēķināt summas"):
        st.session_state.items_df = updated_items_df
        st.rerun()

    subtotal, vat, total = 0.0, 0.0, 0.0
    amount_words = ""
    advance_payment, advance_percent = 0.0, 0.0
    discount_eur, discount_percent = 0.0, 0.0
    
    def fmt_curr(val):
        return f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", " ")

    try:
        if not edited_df.empty:
            calc_df = edited_df.copy()
            # Mēs vairs nesakārtojam pēc vecās 'Secība' kolonnas, jo tagad to nosaka rindas secība (Drag & Drop) un indekss
            # Tāpēc 'Secība' šeit vairs nav vajadzīga
                
            calc_df['DAUDZUMS'] = pd.to_numeric(calc_df['DAUDZUMS'], errors='coerce').fillna(0)
            calc_df['CENA (EUR)'] = pd.to_numeric(calc_df['CENA (EUR)'], errors='coerce').fillna(0)
            calc_df['KOPĀ (EUR)'] = calc_df['DAUDZUMS'] * calc_df['CENA (EUR)']
            
            subtotal = calc_df['KOPĀ (EUR)'].sum()

            st.markdown("### Atlaide")
            discount_type = st.radio("Atlaides veids:", ["Nav atlaides", "Procentos (%)", "Ciparos (EUR)"], horizontal=True)
            if discount_type == "Procentos (%)":
                discount_percent = st.number_input("Atlaides procenti (%)", 0.0, 100.0, 0.0, 5.0)
                discount_eur = subtotal * (discount_percent / 100)
            elif discount_type == "Ciparos (EUR)":
                discount_eur = st.number_input("Atlaides summa (EUR)", 0.0, subtotal, 0.0, 10.0)
                discount_percent = (discount_eur / subtotal) * 100 if subtotal > 0 else 0

            subtotal_after_discount = subtotal - discount_eur
            vat = subtotal_after_discount * 0.21
            total = subtotal_after_discount + vat
            
            if doc_type == "Avansa rēķins":
                st.markdown("### Avansa iestatījumi")
                calc_method = st.radio("Aprēķina veids:", ["Ciparos (EUR)", "Procentos (%)"], horizontal=True)
                
                if calc_method == "Ciparos (EUR)":
                    advance_payment = st.number_input("Summa (EUR)", 0.0, total, total, 10.0)
                    advance_percent = (advance_payment / total) * 100 if total > 0 else 0
                else:
                    advance_percent = st.number_input("Procenti (%)", 0.0, 100.0, 50.0, 5.0)
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

    st.markdown("---")
    st.header("Komentāri un Paraksti")
    
    default_comments = st.session_state.get('loaded_comments', '')
    comments = st.text_area("Papildus komentāri / piezīmes (tiks iekļauti dokumentā)", value=default_comments)
    
    signatory_options = ["Adrians Stankevičs", "Rihards Ozoliņš", "Ēriks Ušackis", "Aleks Kristiāns Grīnbergs"]
    col_sig1, col_sig2 = st.columns(2)
    with col_sig1:
        selected_signatory = st.selectbox("Dokumentu sagatavoja", signatory_options, key="sig_select")
    with col_sig2:
        signatory_title = st.text_input("Amats", "valdes loceklis", key="sig_title")
    full_signatory = f"SIA Bratus {signatory_title} {selected_signatory}"
    st.caption(f"Paraksta laukā būs: {full_signatory}")
    
    # Nodrošinām, ka discount vērtības ir aprēķinātas un pieejamas arī ja DataFrame ir tukšs (piemēram 0)
    try:
        subtotal_val = subtotal
        subtotal_after_discount_val = subtotal_after_discount
        discount_eur_val = discount_eur
        discount_percent_val = discount_percent
    except NameError:
        subtotal_val, subtotal_after_discount_val, discount_eur_val, discount_percent_val = 0.0, 0.0, 0.0, 0.0

    invoice_data = {
        'doc_type': doc_type, 'doc_id': doc_id, 'date': doc_date.strftime("%d.%m.%Y"),
        'due_date': due_date.strftime("%d.%m.%Y"), 'client_name': st.session_state.client_data['name'],
        'client_address': st.session_state.client_data['address'], 'client_reg_no': st.session_state.client_data['reg_no'],
        'client_vat_no': st.session_state.client_data['vat_no'], 'items': [],
        'subtotal': fmt_curr(subtotal_val), 'vat': fmt_curr(vat), 'total': fmt_curr(total),
        'raw_total': total, 'raw_advance': advance_payment, 'advance_percent': advance_percent,
        'discount_eur': fmt_curr(discount_eur_val), 'raw_discount_eur': discount_eur_val,
        'discount_percent': discount_percent_val, 'subtotal_after_discount': fmt_curr(subtotal_after_discount_val),
        'amount_words': amount_words, 'signatory': full_signatory,
        'comments': comments
    }
    
    if not edited_df.empty:
        # iterrows saglabā rindu kārtību, tādēļ mēs varam veidot "Secība" numuru pievienošanas brīdī.
        for index, row in calc_df.iterrows():
            # Ievietojam seq, lai ģeneratori zinātu rindas numuru (piemēram Word dokumentā/PDF), ja tas joprojām ir vajadzīgs tabulā
            invoice_data['items'].append({
                'seq': len(invoice_data['items']) + 1,
                'name': row.get('NOSAUKUMS', ''), 'unit': row.get('Mērvienība', ''),
                'qty': str(row.get('DAUDZUMS', 0)), 'price': fmt_curr(row.get('CENA (EUR)', 0)),
                'total': fmt_curr(row.get('KOPĀ (EUR)', 0)),
                'raw_qty': float(row.get('DAUDZUMS', 0)),
                'raw_price': float(row.get('CENA (EUR)', 0))
            })

    st.markdown("---")
    
    # === POGU UN LEJUPIELĀDES SADAĻA ===
    st.markdown("### Lejupielāde un Arhivēšana")
    
    is_proforma = st.toggle("📝 Ģenerēt kā Proformas (testa) dokumentu", value=False, help="Ja ieslēgts: Dokuments sauksies 'Proformas...', saglabāsies TIKAI testa vēsturē un NETIKS augšupielādēts Google Drive.")

    # Ja toggle ir aktīvs, nomainām nosaukumu pirms ģenerēšanas
    if is_proforma:
        if doc_type == "Pavadzīme":
            invoice_data['doc_type'] = "Proformas pavadzīme"
        elif doc_type == "Rēķins":
            invoice_data['doc_type'] = "Proformas rēķins"
        elif doc_type == "Avansa rēķins":
            invoice_data['doc_type'] = "Proformas avansa rēķins"
            
    d_col1, d_col2 = st.columns(2)
    
    # 1. PDF poga
    try:
        pdf_file = generate_pdf(invoice_data)
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
        
    # 2. WORD poga
    try:
        docx_file = generate_docx(invoice_data)
        file_name_docx = f"{invoice_data['doc_type'].replace(' ', '_')}_{doc_id.replace(' ', '_')}.docx"
        
        with d_col2:
            st.download_button(
                label="📝 Lejupielādēt Word",
                data=docx_file,
                file_name=file_name_docx,
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                on_click=handle_download,
                args=(invoice_data, docx_file, file_name_docx, "application/vnd.openxmlformats-officedocument.wordprocessingml.document", is_proforma)
            )
    except Exception as e:
        st.error(f"Kļūda Word: {e}")

    st.markdown("---")
    with st.expander("🗄️ Rēķinu vēsture (Izrakstītie)", expanded=False):
        if history:
            hist_df = pd.DataFrame(history)
            display_cols = ['doc_id', 'date', 'client_name', 'doc_type', 'total', 'created_at']
            rename_map = {'doc_id': 'Nr.', 'date': 'Datums', 'client_name': 'Klients', 
                          'doc_type': 'Tips', 'total': 'Summa (EUR)', 'created_at': 'Izveidots'}
            valid_cols = [c for c in display_cols if c in hist_df.columns]
            st.dataframe(hist_df[valid_cols].rename(columns=rename_map).sort_index(ascending=False), use_container_width=True)
        else:
            st.info("Vēsture ir tukša.")


def main():
    st.title("SIA BRATUS Rēķinu Ģenerators")
    tab_invoice, tab_presets = st.tabs(["📄 Rēķina izveide", "⚙️ Produktu sagataves"])

    with tab_invoice:
        render_invoice_app()

    with tab_presets:
        render_presets_app()

if __name__ == "__main__":
    main()
