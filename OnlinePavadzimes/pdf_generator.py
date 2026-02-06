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

# --- Fontu iestatījumi ---
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
FONT_BOLD_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
FONT_ITALIC_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf"

if os.path.exists(FONT_PATH):
    pdfmetrics.registerFont(TTFont('DejaVuSerif', FONT_PATH))
    REGULAR_FONT = 'DejaVuSerif'
    
    if os.path.exists(FONT_BOLD_PATH):
        pdfmetrics.registerFont(TTFont('DejaVuSerif-Bold', FONT_BOLD_PATH))
        BOLD_FONT = 'DejaVuSerif-Bold'
    else:
        BOLD_FONT = 'DejaVuSerif'
        
    if os.path.exists(FONT_ITALIC_PATH):
        pdfmetrics.registerFont(TTFont('DejaVuSerif-Italic', FONT_ITALIC_PATH))
        ITALIC_FONT = 'DejaVuSerif-Italic'
    else:
        ITALIC_FONT = 'DejaVuSerif'
else:
    REGULAR_FONT = 'Helvetica'
    BOLD_FONT = 'Helvetica-Bold'
    ITALIC_FONT = 'Helvetica-Oblique'

def fmt_curr(val):
    return f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", " ")

def generate_pdf(data):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=20*mm, leftMargin=20*mm,
                            topMargin=20*mm, bottomMargin=20*mm)
    
    styles = getSampleStyleSheet()
    
    # Stilu definīcijas
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
    
    # JAUNS STILS: Tabulas virsrakstiem (mazāks fonts, centrēts, balts)
    style_table_header = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName=BOLD_FONT,
        fontSize=9,            # Samazināts fonts, lai ielīstu
        alignment=TA_CENTER,   # Centrēts teksts
        textColor=colors.white,# Balts teksts
        leading=10             # Mazāka atstarpe starp rindām
    )
    
    # Preču rindām - centrēts stils (mērvienībai un daudzumam)
    style_cell_center = ParagraphStyle(
        'CellCenter',
        parent=style_normal,
        alignment=TA_CENTER
    )
    # Preču rindām - labējais stils (cenām)
    style_cell_right = ParagraphStyle(
        'CellRight',
        parent=style_normal,
        alignment=TA_RIGHT
    )
    
    elements = []
    
    # --- Header Section ---
    current_dir = os.path.dirname(os.path.abspath(__file__))
    logo_filename = "BRATUS MELNS LOGO PNG.png"
    logo_path = os.path.join(current_dir, logo_filename)
    
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
        Paragraph("PIEGĀDĀTĀJS", style_bold),
        Spacer(1, 2*mm),
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
    # IZMAIŅA: Virsraksti tagad ir Paragraph objekti, lai tie varētu sadalīties rindās
    raw_headers = ["NOSAUKUMS", "Mērvienība", "DAUDZUMS", "CENA (EUR)", "KOPĀ (EUR)"]
    headers = [Paragraph(h, style_table_header) for h in raw_headers]
    
    table_data = [headers]
    items = data.get('items', [])
    for item in items:
        table_data.append([
            Paragraph(item['name'], style_normal),      # Nosaukums - pa kreisi
            Paragraph(item['unit'], style_cell_center), # Mērvienība - centrēta
            Paragraph(str(item['qty']), style_cell_center),  # Daudzums - centrēts
            Paragraph(item['price'], style_cell_right), # Cena - pa labi
            Paragraph(item['total'], style_cell_right)  # Kopā - pa labi
        ])
    
    # IZMAIŅA: Pielāgoti platumi. 
    # Nosaukums: 55mm (bija 60), Mērvienība: 25mm (bija 30), 
    # Daudzums: 30mm (bija 25), Cena: 30mm (bija 25), Kopā: 30mm.
    t = Table(table_data, colWidths=[55*mm, 25*mm, 30*mm, 30*mm, 30*mm])
    
    header_color = colors.HexColor("#CDBF96")
    
    t.setStyle(TableStyle([
        # Header (pirmā rinda)
        ('BACKGROUND', (0,0), (-1,0), header_color),
        # Mums vairs nevajag TEXTCOLOR vai FONTNAME šeit, jo to nosaka 'style_table_header'
        ('VALIGN', (0,0), (-1,0), 'MIDDLE'), # Virsraksti vertikāli pa vidu
        
        # Pārējās rindas (saturs)
        ('VALIGN', (0,1), (-1,-1), 'TOP'),
        
        # Polsterējums (Padding)
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('LEFTPADDING', (0,0), (-1,-1), 4),
        ('RIGHTPADDING', (0,0), (-1,-1), 4),
        
        # Grid līnijas
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 10*mm))
    
    # --- Totals ---
    subtotal = data.get('subtotal', '0.00')
    vat = data.get('vat', '0.00')
    total = data.get('total', '0.00')
    
    totals_data = [
        ["", "KOPĀ (bez PVN)", f"€ {subtotal}"],
        ["", "PVN (21%)", f"€ {vat}"],
        ["", "Kopējā pasūtījuma summa", f"€ {total}"]
    ]
    
    totals_table = Table(totals_data, colWidths=[90*mm, 50*mm, 30*mm])
    
    last_row_font = REGULAR_FONT if doc_type == "Avansa rēķins" else BOLD_FONT
    
    totals_table.setStyle(TableStyle([
        ('ALIGN', (1,0), (1,2), 'RIGHT'),
        ('ALIGN', (2,0), (2,2), 'RIGHT'),
        ('FONTNAME', (1,0), (-1,-1), REGULAR_FONT),
        ('FONTNAME', (1,2), (2,2), last_row_font),
    ]))
    elements.append(totals_table)
    
    # --- Avansa Rēķina Papildus Sadaļa ---
    if doc_type == "Avansa rēķins":
        elements.append(Spacer(1, 5*mm))
        raw_advance = data.get('raw_advance', 0.0)
        formatted_advance = fmt_curr(raw_advance)
        percent_val = int(round(data.get('advance_percent', 0)))
        
        advance_data = [
            ["", f"APMAKSĀJAMAIS AVANSS ({percent_val}% apmērā):", f"€ {formatted_advance}"]
        ]
        
        adv_table = Table(advance_data, colWidths=[60*mm, 80*mm, 30*mm])
        adv_table.setStyle(TableStyle([
            ('ALIGN', (1,0), (2,0), 'RIGHT'),
            ('FONTNAME', (1,0), (-1,-1), BOLD_FONT),
            ('FONTSIZE', (1,0), (-1,-1), 11),
            ('TEXTCOLOR', (1,0), (2,0), colors.black),
            ('TOPPADDING', (0,0), (-1,-1), 8),
        ]))
        elements.append(adv_table)

    elements.append(Spacer(1, 5*mm))
    
    # Amount words
    amount_words = data.get('amount_words', '')
    prefix = "Summa vārdiem (avanss): " if doc_type == "Avansa rēķins" else "Summa vārdiem: "
    elements.append(Paragraph(f"<i>{prefix}{amount_words}</i>", style_italic))
    elements.append(Spacer(1, 10*mm))
    
    # --- Footer / Signatures ---
    elements.append(Paragraph("<b>Papildus informācija:</b>", style_normal))
    elements.append(Spacer(1, 5*mm))
    
    signatory = data.get('signatory', 'SIA Bratus valdes loceklis Adrians Stankevičs')
    
    if doc_type == "Pavadzīme":
        prepared_text = f"Pavadzīmi sagatavoja: {signatory}"
        received_text = "Pavadzīmi saņēma:"
    elif doc_type == "Avansa rēķins":
        prepared_text = f"Avansa rēķinu sagatavoja: {signatory}"
        received_text = "Avansa rēķinu saņēma:"
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
