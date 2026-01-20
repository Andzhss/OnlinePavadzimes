from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_RIGHT, TA_LEFT, TA_CENTER
import io
import os

# Register Fonts
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_ITALIC_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf" # This might not exist

if os.path.exists(FONT_PATH):
    pdfmetrics.registerFont(TTFont('DejaVuSans', FONT_PATH))
    REGULAR_FONT = 'DejaVuSans'
    
    if os.path.exists(FONT_BOLD_PATH):
        pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', FONT_BOLD_PATH))
        BOLD_FONT = 'DejaVuSans-Bold'
    else:
        BOLD_FONT = 'DejaVuSans' # Fallback
        
    if os.path.exists(FONT_ITALIC_PATH):
        pdfmetrics.registerFont(TTFont('DejaVuSans-Oblique', FONT_ITALIC_PATH))
        ITALIC_FONT = 'DejaVuSans-Oblique'
    else:
        ITALIC_FONT = 'DejaVuSans' # Fallback to regular if italic missing
else:
    REGULAR_FONT = 'Helvetica'
    BOLD_FONT = 'Helvetica-Bold'
    ITALIC_FONT = 'Helvetica-Oblique'

def generate_pdf(data):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=20*mm, leftMargin=20*mm,
                            topMargin=20*mm, bottomMargin=20*mm)
    
    styles = getSampleStyleSheet()
    # Define custom styles
    style_normal = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontName=REGULAR_FONT,
        fontSize=10,
        leading=14
    )
    style_bold = ParagraphStyle(
        'CustomBold',
        parent=styles['Normal'],
        fontName=BOLD_FONT,
        fontSize=10,
        leading=14
    )
    style_italic = ParagraphStyle(
        'CustomItalic',
        parent=styles['Normal'],
        fontName=ITALIC_FONT,
        fontSize=10,
        leading=14
    )
    style_header_right = ParagraphStyle(
        'HeaderRight',
        parent=styles['Normal'],
        fontName=BOLD_FONT,
        fontSize=12,
        alignment=TA_RIGHT,
        leading=16
    )
    style_header_right_small = ParagraphStyle(
        'HeaderRightSmall',
        parent=styles['Normal'],
        fontName=REGULAR_FONT,
        fontSize=10,
        alignment=TA_RIGHT,
        leading=12
    )
    
    elements = []
    
    # --- Header Section ---
    logo_path = "logo.png"
    if os.path.exists(logo_path):
        logo = RLImage(logo_path, width=40*mm, height=30*mm, kind='proportional') 
    else:
        logo = Paragraph("LOGO", style_bold)
    
    doc_type = data.get('doc_type', 'Pavadzīme')
    doc_id = data.get('doc_id', 'BR 0000')
    date = data.get('date', '')
    due_date = data.get('due_date', '')
    
    header_text = [
        Paragraph(f"{doc_type} Nr. {doc_id}", style_header_right),
        Paragraph(f"Datums: {date}", style_header_right_small),
        Paragraph(f"Apmaksāt līdz: {due_date}", style_header_right_small),
    ]
    
    # Right column needs to be a list of flowables or a single flowable
    # We can use a nested table or just pass the list
    
    header_table = Table([[logo, header_text]], colWidths=[100*mm, 70*mm])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('ALIGN', (1,0), (1,0), 'RIGHT'),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 10*mm))
    
    # --- Client Section ---
    elements.append(Paragraph("KLIENTS", style_bold))
    elements.append(Spacer(1, 2*mm))
    elements.append(Paragraph(f"<b>{data.get('client_name', '')}</b>", style_normal))
    elements.append(Paragraph(f"Adrese: {data.get('client_address', '')}", style_normal))
    elements.append(Paragraph(f"Reģ. Nr.: {data.get('client_reg_no', '')}", style_normal))
    elements.append(Paragraph(f"PVN Nr.: {data.get('client_vat_no', '')}", style_normal))
    
    elements.append(Spacer(1, 10*mm))
    
    # --- Sender & Bank Section ---
    sender_info = [
        Paragraph("<b>SIA Bratus</b>", style_normal),
        Paragraph("Adrese: Ķekavas nov., Ķekava,", style_normal),
        Paragraph("Dārzenieku iela 42, LV-2123", style_normal),
        Paragraph("Reģ. Nr.: 40203628316", style_normal),
        Paragraph("PVN Nr.: LV40203628316", style_normal),
        Paragraph("Tālrunis: +371 24424434", style_normal),
    ]
    
    bank_info = [
        Paragraph("<b>AS Swedbank</b>", style_normal),
        Paragraph("SWIFT/BIC: HABALV22", style_normal),
        Paragraph("Bankas konta numurs: LV64HABA0551060367591", style_normal),
    ]
    
    sender_table = Table([[sender_info, bank_info]], colWidths=[85*mm, 85*mm])
    sender_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]))
    elements.append(sender_table)
    elements.append(Spacer(1, 10*mm))
    
    # --- Items Table ---
    headers = ["NOSAUKUMS", "Mērvienība", "DAUDZUMS", "CENA (EUR)", "KOPĀ (EUR)"]
    
    # Style for headers
    header_style = ParagraphStyle(
        'HeaderStyle',
        parent=styles['Normal'],
        fontName=BOLD_FONT,
        fontSize=10,
        textColor=colors.white,
        alignment=TA_CENTER
    )
    
    # Data Rows
    # Convert headers to Paragraphs for white color? Or use table style for text color
    # Using TableStyle TEXTCOLOR is easier if simple strings.
    # But we want bold headers.
    
    table_data = [headers]
    items = data.get('items', [])
    for item in items:
        table_data.append([
            Paragraph(item['name'], style_normal),
            item['unit'],
            item['qty'],
            item['price'],
            item['total']
        ])
        
    t = Table(table_data, colWidths=[60*mm, 30*mm, 25*mm, 25*mm, 30*mm])
    
    header_color = colors.HexColor("#CDBF96")
    
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), header_color),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), BOLD_FONT),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'), 
        ('ALIGN', (2,0), (-1,-1), 'RIGHT'), # Qty right
        ('ALIGN', (3,0), (-1,-1), 'RIGHT'), # Price right
        ('ALIGN', (4,0), (-1,-1), 'RIGHT'), # Total right
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('FONTNAME', (0,1), (-1,-1), REGULAR_FONT),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('TOPPADDING', (0,0), (-1,-1), 6),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 10*mm))
    
    # --- Totals ---
    subtotal = data.get('subtotal', '0.00')
    vat = data.get('vat', '0.00')
    total = data.get('total', '0.00')
    
    totals_data = [
        ["", "KOPĀ", f"€ {subtotal}"],
        ["", "PVN", f"€ {vat}"],
        ["", "Kopumā", f"€ {total}"]
    ]
    
    totals_table = Table(totals_data, colWidths=[110*mm, 30*mm, 30*mm])
    totals_table.setStyle(TableStyle([
        ('ALIGN', (1,0), (1,2), 'RIGHT'),
        ('ALIGN', (2,0), (2,2), 'RIGHT'),
        ('FONTNAME', (1,0), (-1,-1), BOLD_FONT),
        ('FONTNAME', (2,0), (-1,-1), BOLD_FONT),
    ]))
    elements.append(totals_table)
    elements.append(Spacer(1, 5*mm))
    
    # Amount in words
    amount_words = data.get('amount_words', '')
    elements.append(Paragraph(f"<i>Summa vārdiem: {amount_words}</i>", style_italic))
    elements.append(Spacer(1, 10*mm))
    
    # --- Footer / Signatures ---
    elements.append(Paragraph("<b>Papildus informācija:</b>", style_normal))
    elements.append(Spacer(1, 5*mm))
    
    signatory = data.get('signatory', 'SIA Bratus valdes loceklis Adrians Stankevičs')
    
    # Handle grammar
    if doc_type == "Pavadzīme":
        prepared_text = f"Pavadzīmi sagatavoja: {signatory}"
        received_text = "Pavadzīmi saņēma:"
    else: # Rēķins
        prepared_text = f"Rēķinu sagatavoja: {signatory}"
        received_text = "Rēķinu saņēma:"
    
    sig_table_data = [
        [Paragraph(prepared_text, style_italic), "__________________________"],
        [Paragraph(received_text, style_italic), "__________________________"]
    ]
    
    sig_table = Table(sig_table_data, colWidths=[100*mm, 70*mm])
    sig_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'BOTTOM'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 10),
        ('ALIGN', (1,0), (1,1), 'RIGHT'),
    ]))
    elements.append(sig_table)
    
    doc.build(elements)
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
    pdf = generate_pdf(data)
    with open("test_output.pdf", "wb") as f:
        f.write(pdf.read())
    print("PDF generated.")
