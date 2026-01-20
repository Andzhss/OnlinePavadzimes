from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.oxml.ns import nsdecls
from docx.oxml import parse_xml
import io

def generate_docx(data):
    doc = Document()
    
    # Set margins
    sections = doc.sections
    for section in sections:
        section.top_margin = Cm(2)
        section.bottom_margin = Cm(2)
        section.left_margin = Cm(2)
        section.right_margin = Cm(2)
        
    # Styles
    style = doc.styles['Normal']
    font = style.font
    # 1. IZMAIŅA: Nomainīts fonts uz DejaVu Serif
    font.name = 'DejaVu Serif'
    font.size = Pt(10)
    
    # --- Header ---
    # 2 columns table: Logo | Doc Info
    table = doc.add_table(rows=1, cols=2)
    table.autofit = False
    table.columns[0].width = Cm(10)
    table.columns[1].width = Cm(7)
    
    # Logo
    cell_logo = table.cell(0, 0)
    paragraph = cell_logo.paragraphs[0]
    # Add logo if exists
    try:
        # 2. IZMAIŅA: Nomainīts logo faila nosaukums
        paragraph.add_run().add_picture('BRATUS MELNS LOGO PNG.png', width=Cm(4))
    except:
        paragraph.add_run("LOGO")
        
    # Info
    cell_info = table.cell(0, 1)
    p = cell_info.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    
    doc_type = data.get('doc_type', 'Pavadzīme')
    doc_id = data.get('doc_id', 'BR 0000')
    date = data.get('date', '')
    due_date = data.get('due_date', '')
    
    run = p.add_run(f"{doc_type} Nr. {doc_id}\n")
    run.bold = True
    run.font.size = Pt(12)
    
    p.add_run(f"Datums: {date}\n")
    p.add_run(f"Apmaksāt līdz: {due_date}")
    
    doc.add_paragraph() # Spacer
    
    # --- Client ---
    p = doc.add_paragraph()
    p.add_run("KLIENTS").bold = True
    
    p = doc.add_paragraph()
    p.add_run(data.get('client_name', '')).bold = True
    p.add_run(f"\nAdrese: {data.get('client_address', '')}")
    p.add_run(f"\nReģ. Nr.: {data.get('client_reg_no', '')}")
    p.add_run(f"\nPVN Nr.: {data.get('client_vat_no', '')}")
    
    doc.add_paragraph()
    
    # --- Sender & Bank ---
    table = doc.add_table(rows=1, cols=2)
    table.autofit = False
    table.columns[0].width = Cm(8.5)
    table.columns[1].width = Cm(8.5)
    
    # Sender
    cell = table.cell(0, 0)
    p = cell.paragraphs[0]
    p.add_run("SIA Bratus").bold = True
    p.add_run("\nAdrese: Ķekavas nov., Ķekava,")
    p.add_run("\nDārzenieku iela 42, LV-2123")
    p.add_run("\nReģ. Nr.: 40203628316")
    p.add_run("\nPVN Nr.: LV40203628316")
    p.add_run("\nTālrunis: +371 24424434")
    
    # Bank
    cell = table.cell(0, 1)
    p = cell.paragraphs[0]
    p.add_run("AS Swedbank").bold = True
    p.add_run("\nSWIFT/BIC: HABALV22")
    p.add_run("\nBankas konta numurs: LV64HABA0551060367591")
    
    doc.add_paragraph()
    
    # --- Items Table ---
    headers = ["NOSAUKUMS", "Mērvienība", "DAUDZUMS", "CENA (EUR)", "KOPĀ (EUR)"]
    items = data.get('items', [])
    
    table = doc.add_table(rows=1, cols=5)
    table.style = 'Table Grid' # Or None
    
    hdr_cells = table.rows[0].cells
    for i, h in enumerate(headers):
        hdr_cells[i].text = h
        # Style header background
        tcPr = hdr_cells[i]._element.tcPr
        shd = parse_xml(r'<w:shd {} w:fill="CDBF96"/>'.format(nsdecls('w')))
        tcPr.append(shd)
        # Bold and White text?
        p = hdr_cells[i].paragraphs[0]
        run = p.runs[0]
        run.bold = True
        run.font.color.rgb = RGBColor(255, 255, 255)
        # Alignment
        if i >= 2:
            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            
    for item in items:
        row_cells = table.add_row().cells
        row_cells[0].text = item['name']
        row_cells[1].text = item['unit']
        row_cells[2].text = str(item['qty'])
        row_cells[3].text = str(item['price'])
        row_cells[4].text = str(item['total'])
        
        # Alignment
        row_cells[2].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
        row_cells[3].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
        row_cells[4].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
        
    doc.add_paragraph()
    
    # --- Totals ---
    # Create a table for alignment
    table = doc.add_table(rows=3, cols=3)
    table.autofit = False
    table.columns[0].width = Cm(11)
    table.columns[1].width = Cm(3)
    table.columns[2].width = Cm(3)
    
    subtotal = data.get('subtotal', '0.00')
    vat = data.get('vat', '0.00')
    total = data.get('total', '0.00')
    
    def set_total_row(row_idx, label, value, bold=False):
        cell_lbl = table.cell(row_idx, 1)
        cell_val = table.cell(row_idx, 2)
        p = cell_lbl.paragraphs[0]
        p.add_run(label).bold = True
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        
        p = cell_val.paragraphs[0]
        p.add_run(f"€ {value}").bold = bold
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT

    set_total_row(0, "KOPĀ", subtotal, True)
    set_total_row(1, "PVN", vat, True)
    set_total_row(2, "Kopumā", total, True)
    
    doc.add_paragraph()
    
    # Amount words
    p = doc.add_paragraph()
    p.add_run(f"Summa vārdiem: {data.get('amount_words', '')}").italic = True
    
    doc.add_paragraph()
    doc.add_paragraph().add_run("Papildus informācija:").bold = True
    doc.add_paragraph()
    
    # --- Signatures ---
    signatory = data.get('signatory', 'SIA Bratus valdes loceklis Adrians Stankevičs')
    
    if doc_type == "Pavadzīme":
        prepared_text = f"Pavadzīmi sagatavoja: {signatory}"
        received_text = "Pavadzīmi saņēma:"
    else:
        prepared_text = f"Rēķinu sagatavoja: {signatory}"
        received_text = "Rēķinu saņēma:"
        
    table = doc.add_table(rows=2, cols=2)
    table.autofit = False
    table.columns[0].width = Cm(10)
    table.columns[1].width = Cm(7)
    
    cell = table.cell(0, 0)
    p = cell.paragraphs[0]
    p.add_run(prepared_text).italic = True
    
    cell = table.cell(0, 1)
    cell.paragraphs[0].add_run("__________________________")
    cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
    
    cell = table.cell(1, 0)
    p = cell.paragraphs[0]
    p.add_run(received_text).italic = True
    
    cell = table.cell(1, 1)
    cell.paragraphs[0].add_run("__________________________")
    cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
    
    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer

if __name__ == "__main__":
    # Test
    data = {
        'doc_type': 'Pavadzīme',
        'doc_id': 'BR 0049',
        'date': '09.01.2026',
        'due_date': '23.01.2026',
        'client_name': 'ARĀJIŅI, Rēzeknes rajona Nautrēnu pagasta zemnieku saimniecība',
        'client_address': 'Rēzeknes nov., Nautrēnu pag., Rogovka, LV-4652',
        'client_reg_no': '42401017811',
        'client_vat_no': 'LV42401017811',
        'items': [
            {'name': 'Lāzeriekārta; modeļa nr.: KH7050; 80W', 'unit': 'Gab.', 'qty': '1', 'price': '4 505,00', 'total': '4 505,00'}
        ],
        'subtotal': '4 505,00',
        'vat': '946,05',
        'total': '5 451,05',
        'amount_words': 'Pieci tūkstoši četri simti piecdesmit viens eiro 05 centi',
        'signatory': 'SIA Bratus valdes loceklis Adrians Stankevičs'
    }
    docx_file = generate_docx(data)
    with open("test_output.docx", "wb") as f:
        f.write(docx_file.read())
    print("DOCX generated.")
