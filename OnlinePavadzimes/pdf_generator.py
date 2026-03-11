from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage, Flowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_RIGHT, TA_LEFT, TA_CENTER
import urllib.request
import io
import os

# --- Krāsu definīcijas ---
THEME_COLOR = colors.HexColor("#CDBF96")
TEXT_COLOR = colors.black

# --- Fontu ielāde ---
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
FONTS_DIR = os.path.join(CURRENT_DIR, "fonts")

# Reģistrē Montserrat fontus (atbalsta visus latviešu burtus un garumzīmes)
try:
    pdfmetrics.registerFont(TTFont('Montserrat', os.path.join(FONTS_DIR, "Montserrat-Regular.ttf")))
    REGULAR_FONT = 'Montserrat'
except Exception as e:
    print(f"Neizdevās ielādēt Montserrat: {e}")
    REGULAR_FONT = 'Helvetica'

try:
    pdfmetrics.registerFont(TTFont('Montserrat-Bold', os.path.join(FONTS_DIR, "Montserrat-Bold.ttf")))
    BOLD_FONT = 'Montserrat-Bold'
except:
    BOLD_FONT = 'Helvetica-Bold'

try:
    pdfmetrics.registerFont(TTFont('Montserrat-Italic', os.path.join(FONTS_DIR, "Montserrat-Italic.ttf")))
    ITALIC_FONT = 'Montserrat-Italic'
except:
    ITALIC_FONT = 'Helvetica-Oblique'
    
try:
    pdfmetrics.registerFont(TTFont('Montserrat-BoldItalic', os.path.join(FONTS_DIR, "Montserrat-BoldItalic.ttf")))
    BOLD_ITALIC_FONT = 'Montserrat-BoldItalic'
except:
    BOLD_ITALIC_FONT = 'Helvetica-BoldOblique'
    
# Reģistrējam kopējo fontu ģimeni, lai style bold/italic strādātu kopā
try:
    from reportlab.pdfbase.pdfmetrics import registerFontFamily
    registerFontFamily('Montserrat', normal='Montserrat', bold='Montserrat-Bold', italic='Montserrat-Italic', boldItalic='Montserrat-BoldItalic')
except:
    pass

# --- Palīgklase horizontālajām līnijām ---
class HorizontalLine(Flowable):
    def __init__(self, width=170*mm, color=THEME_COLOR, thickness=0.5):
        Flowable.__init__(self)
        self.width = width
        self.color = color
        self.thickness = thickness

    def draw(self):
        self.canv.setStrokeColor(self.color)
        self.canv.setLineWidth(self.thickness)
        self.canv.line(0, 0, self.width, 0)

def fmt_curr(val):
    return f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", " ")

def generate_pdf(data):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=20*mm, leftMargin=20*mm,
                            topMargin=15*mm, bottomMargin=15*mm)
    
    styles = getSampleStyleSheet()
    
    # --- Stilu definīcijas ---
    style_normal = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontName=REGULAR_FONT,
        fontSize=10,
        leading=13,
        textColor=TEXT_COLOR
    )
    style_bold = ParagraphStyle(
        'CustomBold',
        parent=styles['Normal'],
        fontName=BOLD_FONT,
        fontSize=10,
        leading=13,
        textColor=TEXT_COLOR
    )
    style_italic = ParagraphStyle(
        'CustomItalic',
        parent=styles['Normal'],
        fontName=ITALIC_FONT,
        fontSize=10,
        leading=13,
        textColor=TEXT_COLOR
    )
    
    style_header_title = ParagraphStyle(
        'HeaderTitle',
        parent=styles['Normal'],
        fontName=BOLD_FONT,
        fontSize=14,
        alignment=TA_RIGHT,
        leading=18,
        textColor=TEXT_COLOR
    )
    style_header_info = ParagraphStyle(
        'HeaderInfo',
        parent=styles['Normal'],
        fontName=REGULAR_FONT,
        fontSize=10,
        alignment=TA_RIGHT,
        leading=12,
        textColor=TEXT_COLOR
    )

    style_table_header = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName=BOLD_FONT,
        fontSize=10,
        alignment=TA_CENTER,
        textColor=colors.white,
        leading=11
    )
    
    style_cell_left = ParagraphStyle('CellLeft', parent=style_normal, alignment=TA_LEFT)
    style_cell_center = ParagraphStyle('CellCenter', parent=style_normal, alignment=TA_CENTER)
    style_cell_right = ParagraphStyle('CellRight', parent=style_normal, alignment=TA_RIGHT)

    elements = []
    
    # ==========================================
    # 1. LOGO UN DOKUMENTA INFO
    # ==========================================
    current_dir = os.path.dirname(os.path.abspath(__file__))
    logo_filename = "BRATUS MELNS LOGO PNG.png"
    logo_path = os.path.join(current_dir, logo_filename)
    
    if os.path.exists(logo_path):
        logo = RLImage(logo_path, width=35*mm, height=26*mm, kind='proportional') 
    else:
        logo = Paragraph("LOGO", style_bold)
    
    doc_type = data.get('doc_type', 'Pavadzīme')
    doc_id = data.get('doc_id', 'BR 0000')
    date = data.get('date', '')
    due_date = data.get('due_date', '')
    
    header_text = [
        Paragraph(f"{doc_type} Nr. {doc_id}", style_header_title),
        Spacer(1, 2*mm),
        Paragraph(f"Datums: {date}", style_header_info),
        Paragraph(f"Apmaksāt līdz: {due_date}", style_header_info),
    ]
    
    header_table = Table([[logo, header_text]], colWidths=[85*mm, 85*mm])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('ALIGN', (0,0), (0,0), 'LEFT'),
        ('ALIGN', (1,0), (1,0), 'RIGHT'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 3*mm))
    elements.append(HorizontalLine()) 
    elements.append(Spacer(1, 5*mm))
    
    # ==========================================
    # 2. KLIENTS
    # ==========================================
    elements.append(Paragraph("KLIENTS", style_bold))
    elements.append(Spacer(1, 2*mm))
    
    elements.append(Paragraph(f"<b>{data.get('client_name', '')}</b>", style_normal))
    elements.append(Paragraph(f"<i>Adrese: {data.get('client_address', '')}</i>", style_normal))
    elements.append(Paragraph(f"<i>Reģ. Nr.: {data.get('client_reg_no', '')}</i>", style_normal))
    elements.append(Paragraph(f"<i>PVN Nr.: {data.get('client_vat_no', '')}</i>", style_normal))
    
    elements.append(Spacer(1, 3*mm))
    elements.append(HorizontalLine(thickness=0.2))
    elements.append(Spacer(1, 5*mm))
    
    # ==========================================
    # 3. PIEGĀDĀTĀJS UN BANKA
    # ==========================================
    sender_data = [
        Paragraph("<b>SIA Bratus</b>", style_normal),
        Paragraph(f"<i>Adrese: Ķekavas nov., Ķekava,</i>", style_normal),
        Paragraph(f"<i>Dārzenieku iela 42, LV-2123</i>", style_normal),
        Paragraph(f"<i>Reģ. Nr.: 40203628316</i>", style_normal),
        Paragraph(f"<i>PVN Nr.: LV40203628316</i>", style_normal),
        Paragraph(f"<i>Tālrunis: +371 24424434</i>", style_normal),
    ]
    
    bank_data = [
        Paragraph("<b><i>AS Swedbank</i></b>", style_normal),
        Paragraph(f"<i>SWIFT/BIC: HABALV22</i>", style_normal),
        Paragraph(f"<i>Bankas konta numurs: <b>LV64HABA0551060367591</b></i>", style_normal),
    ]
    
    info_table = Table([[sender_data, bank_data]], colWidths=[85*mm, 85*mm])
    info_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
    ]))
    elements.append(info_table)
    
    elements.append(Spacer(1, 10*mm))
    
    # ==========================================
    # 4. PREČU TABULA
    # ==========================================
    headers = [
        Paragraph("NOSAUKUMS", style_table_header),
        Paragraph("Mērvienība", style_table_header),
        Paragraph("DAUDZUMS", style_table_header),
        Paragraph("CENA (EUR)", style_table_header),
        Paragraph("KOPĀ (EUR)", style_table_header)
    ]
    
    table_data = [headers]
    items = data.get('items', [])
    
    if not items:
        for _ in range(3):
            items.append({'name': '', 'unit': '', 'qty': '', 'price': '', 'total': ''})

    for item in items:
        seq_num = item.get('seq', '')
        name_str = f"{seq_num}. {item['name']}" if seq_num else item['name']
        table_data.append([
            Paragraph(name_str, style_cell_left),
            Paragraph(item['unit'], style_cell_center),
            Paragraph(str(item['qty']), style_cell_center),
            Paragraph(item['price'], style_cell_right),
            Paragraph(item['total'], style_cell_right)
        ])
        
    col_widths = [65*mm, 25*mm, 25*mm, 25*mm, 30*mm]
    
    t = Table(table_data, colWidths=col_widths)
    
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), THEME_COLOR),
        ('VALIGN', (0,0), (-1,0), 'MIDDLE'),
        ('LINEBEFORE', (1,0), (-1,0), 1, colors.white), 
        ('VALIGN', (0,1), (-1,-1), 'TOP'),
        ('GRID', (0,0), (-1,-1), 0.5, THEME_COLOR),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('LEFTPADDING', (0,0), (-1,-1), 5),
        ('RIGHTPADDING', (0,0), (-1,-1), 5),
    ]))
    elements.append(t)
    
    # ==========================================
    # 5. KOPSUMMAS
    # ==========================================
    elements.append(Spacer(1, 2*mm))
    
    subtotal = data.get('subtotal', '0.00')
    vat = data.get('vat', '0.00')
    total = data.get('total', '0.00')
    
    raw_discount_eur = data.get('raw_discount_eur', 0.0)

    totals_data = []

    if raw_discount_eur > 0:
        totals_data.append(["", "KOPĀ (bez PVN un atlaides)", f"{subtotal} €"])
        discount_str = f"Atlaides apjoms ({data.get('discount_percent', 0):g}%)"
        totals_data.append(["", discount_str, f"-{data.get('discount_eur', '0.00')} €"])
        totals_data.append(["", "Kopā ar atlaidi (bez PVN)", f"{data.get('subtotal_after_discount', '0.00')} €"])
        totals_data.append(["", "PVN", f"{vat} €"])
        totals_data.append(["", "KOPUMĀ APMAKSAI", f"{total} €"])
        last_row_idx = 4
    else:
        totals_data.append(["", "KOPĀ", f"{subtotal} €"])
        totals_data.append(["", "PVN", f"{vat} €"])
        totals_data.append(["", "Kopumā", f"{total} €"])
        last_row_idx = 2
    
    totals_table = Table(totals_data, colWidths=[80*mm, 60*mm, 30*mm])
    
    if "avansa" in doc_type.lower():
        totals_style_cmds = [
            ('ALIGN', (1,0), (-1,-1), 'RIGHT'),
            ('TEXTCOLOR', (0,0), (-1,-1), TEXT_COLOR),
            ('FONTNAME', (0,0), (-1,-1), REGULAR_FONT),
        ]
    else:
        totals_style_cmds = [
            ('ALIGN', (1,0), (-1,-1), 'RIGHT'),
            ('TEXTCOLOR', (0,0), (-1,-1), TEXT_COLOR),
            ('FONTNAME', (1,0), (1,last_row_idx), BOLD_FONT),
            ('FONTNAME', (2,0), (2,last_row_idx), REGULAR_FONT),
            ('FONTNAME', (1,last_row_idx), (2,last_row_idx), BOLD_FONT),
            ('FONTNAME', (2,last_row_idx), (2,last_row_idx), BOLD_FONT),
        ]
    
    totals_table.setStyle(TableStyle(totals_style_cmds))
    elements.append(totals_table)
    
    # ==========================================
    # 6. SUMMA VĀRDIEM UN AVANSS
    # ==========================================
    elements.append(Spacer(1, 5*mm))
    
    if "avansa" in doc_type.lower():
        raw_advance = data.get('raw_advance', 0.0)
        formatted_advance = fmt_curr(raw_advance)
        percent_val = int(round(data.get('advance_percent', 0)))
        
        bold_text = f'<font name="{BOLD_FONT}">APMAKSĀJAMAIS AVANSS ({percent_val}%): {formatted_advance} €</font>'
        elements.append(Paragraph(bold_text, style_cell_right))
        elements.append(Spacer(1, 2*mm))

    amount_words = data.get('amount_words', '')
    prefix = "Vārdiem: "
    elements.append(Paragraph(f"<i>{prefix}{amount_words}</i>", 
                              ParagraphStyle('Words', parent=style_italic, alignment=TA_RIGHT)))
    
    # ==========================================
    # 7. PARAKSTI UN PAPILDINFO (Ieskaitot komentārus)
    # ==========================================
    elements.append(Spacer(1, 5*mm))
    elements.append(HorizontalLine(thickness=0.2))
    elements.append(Spacer(1, 2*mm))
    
    comments = data.get('comments', '').strip()
    if comments:
        comments_html = comments.replace('\n', '<br/>')
        elements.append(Paragraph(f"<b>Papildus informācija:</b><br/>{comments_html}", style_normal))
    else:
        elements.append(Paragraph("<b>Papildus informācija:</b>", style_bold))
        
    elements.append(Spacer(1, 10*mm))
    
    signatory = data.get('signatory', 'SIA Bratus valdes loceklis Adrians Stankevičs')
    
    if "pavadzīme" in doc_type.lower():
        prepared_text = f"Pavadzīmi sagatavoja: <i>{signatory}</i>"
        received_text = "Pavadzīmi saņēma:"
    elif "avansa rēķins" in doc_type.lower():
        prepared_text = f"Avansa rēķinu sagatavoja: <i>{signatory}</i>"
        received_text = "Avansa rēķinu saņēma:"
    else:
        prepared_text = f"Rēķinu sagatavoja: <i>{signatory}</i>"
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
