import streamlit as st
import datetime
from utils import scrape_lursoft, money_to_words_lv
from pdf_generator import generate_pdf
from docx_generator import generate_docx
import pandas as pd
import io

st.set_page_config(page_title="SIA BRATUS Invoice Generator", layout="wide")

def main():
    st.title("SIA BRATUS Rēķinu Ģenerators")

    # --- Sidebar Configuration ---
    st.sidebar.header("Iestatījumi")
    
    # 1. Document ID
    doc_number_input = st.sidebar.number_input("Dokumenta Nr.", min_value=1, value=49, step=1)
    doc_id = f"BR {doc_number_input:04d}" 
    st.sidebar.markdown(f"**Dokumenta ID:** {doc_id}")
    
    # 2. Date
    doc_date = st.sidebar.date_input("Datums", datetime.date.today())
    due_date = st.sidebar.date_input("Apmaksāt līdz", doc_date + datetime.timedelta(days=14))
    
    # 3. Document Type
    doc_type = st.sidebar.selectbox("Dokumenta tips", ["Pavadzīme", "Rēķins", "Avansa rēķins"])
    
    # --- Client Data ---
    st.header("Klients")
    
    col1, col2 = st.columns([1, 1])
    
    # Session state for client data
    if 'client_data' not in st.session_state:
        st.session_state.client_data = {
            'name': '',
            'address': '',
            'reg_no': '',
            'vat_no': ''
        }
        
    with col1:
        lursoft_url = st.text_input("Lursoft saite (automātiskai datu ielasīšanai)")
        scrape_btn = st.button("Ielādēt datus no Lursoft")
        
        if scrape_btn and lursoft_url:
            with st.spinner("Datu ielasīšana..."):
                scraped = scrape_lursoft(lursoft_url)
                if scraped:
                    if scraped.get('name'):
                        st.session_state.client_data['name'] = scraped.get('name')
                    if scraped.get('address'):
                        st.session_state.client_data['address'] = scraped.get('address')
                    if scraped.get('reg_no'):
                        st.session_state.client_data['reg_no'] = scraped.get('reg_no')
                        st.session_state.client_data['vat_no'] = "LV" + scraped.get('reg_no')
                    
                    st.success("Dati veiksmīgi ielasīti! Lūdzu pārbaudiet.")
                    st.rerun()
                else:
                    st.error("Neizdevās ielasīt datus. Lūdzu ievadiet manuāli.")
    
    with col2:
        client_name = st.text_input("Nosaukums", value=st.session_state.client_data['name'])
        client_address = st.text_input("Adrese", value=st.session_state.client_data['address'])
        client_reg_no = st.text_input("Reģ. Nr.", value=st.session_state.client_data['reg_no'])
        client_vat_no = st.text_input("PVN Nr.", value=st.session_state.client_data['vat_no'])
        
        st.session_state.client_data['name'] = client_name
        st.session_state.client_data['address'] = client_address
        st.session_state.client_data['reg_no'] = client_reg_no
        st.session_state.client_data['vat_no'] = client_vat_no

    st.markdown("---")
    
    # --- Items Table ---
    st.header("Preces / Pakalpojumi")
    
    if 'items_df' not in st.session_state:
        initial_data = [
            {
                "NOSAUKUMS": "Lāzeriekārta; modeļa nr.: KH7050; 80W",
                "Mērvienība": "Gab.",
                "DAUDZUMS": 1,
                "CENA (EUR)": 4505.00
            }
        ]
        st.session_state.items_df = pd.DataFrame(initial_data)
        
    edited_df = st.data_editor(
        st.session_state.items_df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "CENA (EUR)": st.column_config.NumberColumn(format="%.2f"),
            "DAUDZUMS": st.column_config.NumberColumn(step=1),
        }
    )
    
    # Calculate totals
    subtotal = 0.0
    vat = 0.0
    total = 0.0
    amount_words = ""
    advance_payment = 0.0
    advance_percent = 0.0 # Initialize
    
    # Helper to format currency LV style
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
            
            # --- Avansa Invoice Logic ---
            if doc_type == "Avansa rēķins":
                st.markdown("### Avansa iestatījumi")
                
                # Switch implementation
                calc_method = st.radio(
                    "Aprēķina veids:",
                    ["Avansa rēķina apmaksājamā summa ciparos (EUR)", "Avansa rēķina apmaksājamā summa procentos (%)"],
                    horizontal=True
                )
                
                if calc_method == "Avansa rēķina apmaksājamā summa ciparos (EUR)":
                    advance_payment = st.number_input(
                        "Ievadiet summu (EUR)", 
                        min_value=0.0, 
                        max_value=total, 
                        value=total, 
                        step=10.0
                    )
                    # Aprēķinam procentus priekš PDF/DOCX
                    if total > 0:
                        advance_percent = (advance_payment / total) * 100
                    else:
                        advance_percent = 0
                else:
                    advance_percent_input = st.number_input(
                        "Ievadiet procentus (%)", 
                        min_value=0.0, 
                        max_value=100.0, 
                        value=50.0, 
                        step=5.0
                    )
                    advance_percent = advance_percent_input
                    # Calculate EUR from percentage of TOTAL
                    advance_payment = total * (advance_percent / 100)
                
                st.markdown("### Aprēķins")
                t_col1, t_col2 = st.columns([3, 1])
                with t_col2:
                    st.markdown(f"Kopējā pasūtījuma summa: € {fmt_curr(total)}")
                    st.markdown(f"**APMAKSĀJAMAIS AVANSS ({int(round(advance_percent))}%):** € {fmt_curr(advance_payment)}")
                
                amount_words = money_to_words_lv(advance_payment)
                st.info(f"**Summa vārdiem (Avanss):** {amount_words}")
                
            else:
                # Standard Invoice/Pavadzīme
                advance_payment = total
                
                st.markdown("### Aprēķins")
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

    # --- Signatory ---
    st.header("Paraksti")
    signatory_options = [
        "Adrians Stankevičs",
        "Rihards Ozoliņš",
        "Ēriks Ušackis",
        "Aleks Kristiāns Grīnbergs"
    ]
    
    col_sig1, col_sig2 = st.columns(2)
    with col_sig1:
        selected_signatory = st.selectbox("Dokumentu sagatavoja", signatory_options)
    with col_sig2:
        signatory_title = st.text_input("Amats", "valdes loceklis")
        
    full_signatory = f"SIA Bratus {signatory_title} {selected_signatory}"
    st.caption(f"Paraksta laukā būs: {full_signatory}")
    
    # Data collection for generation
    invoice_data = {
        'doc_type': doc_type,
        'doc_id': doc_id,
        'date': doc_date.strftime("%d.%m.%Y"),
        'due_date': due_date.strftime("%d.%m.%Y"),
        'client_name': st.session_state.client_data['name'],
        'client_address': st.session_state.client_data['address'],
        'client_reg_no': st.session_state.client_data['reg_no'],
        'client_vat_no': st.session_state.client_data['vat_no'],
        'items': [],
        'subtotal': fmt_curr(subtotal),
        'vat': fmt_curr(vat),
        'total': fmt_curr(total),
        'raw_total': total,
        'raw_advance': advance_payment,
        'advance_percent': advance_percent, # Nododam procentus tālāk
        'amount_words': amount_words,
        'signatory': full_signatory
    }
    
    if not edited_df.empty:
        for index, row in calc_df.iterrows():
            invoice_data['items'].append({
                'name': row.get('NOSAUKUMS', ''),
                'unit': row.get('Mērvienība', ''),
                'qty': str(row.get('DAUDZUMS', 0)),
                'price': fmt_curr(row.get('CENA (EUR)', 0)),
                'total': fmt_curr(row.get('KOPĀ (EUR)', 0))
            })

    st.markdown("### Lejupielāde")
    d_col1, d_col2 = st.columns(2)
    
    # PDF
    try:
        pdf_file = generate_pdf(invoice_data)
        with d_col1:
            st.download_button(
                label="📄 Lejupielādēt PDF",
                data=pdf_file,
                file_name=f"{doc_type.replace(' ', '_')}_{doc_id.replace(' ', '_')}.pdf",
                mime="application/pdf"
            )
    except Exception as e:
        st.error(f"Kļūda ģenerējot PDF: {e}")
        
    # Docx
    try:
        docx_file = generate_docx(invoice_data)
        with d_col2:
            st.download_button(
                label="📝 Lejupielādēt Word",
                data=docx_file,
                file_name=f"{doc_type.replace(' ', '_')}_{doc_id.replace(' ', '_')}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
    except Exception as e:
        st.error(f"Kļūda ģenerējot Word: {e}")

if __name__ == "__main__":
    main()
