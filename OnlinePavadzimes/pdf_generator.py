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

from i18n import labels, doc_type_label, signature_texts, totals_rows

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
    
    lang = data.get('lang', 'lv')
    L = labels(lang)
    doc_type = data.get('doc_type', 'Pavadzīme')
    display_doc_type = doc_type_label("Pavadzīme" if "e-rēķins" in doc_type.lower() else doc_type, lang)

    doc_id = data.get('doc_id', 'BR 0000')
    date = data.get('date', '')
    due_date = data.get('due_date', '')
    
    header_text = [
        Paragraph(f"{display_doc_type} {L['nr']} {doc_id}", style_header_title),
        Spacer(1, 2*mm),
        Paragraph(f"{L['date']}: {date}", style_header_info),
        Paragraph(f"{L['due_date']}: {due_date}", style_header_info),
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
    # 2. KLIENTS VAI E-RĒĶINA INFO
    # ==========================================
    if "e-rēķins" in doc_type.lower():
        rec_name = data.get('receiver_name', '')
        rec_reg = data.get('receiver_reg_no', '')
        rec_addr = data.get('receiver_address', '')
        
        cus_name = data.get('customer_name', '')
        cus_reg = data.get('customer_reg_no', '')
        cus_addr = data.get('customer_address', '')

        # Izmantojam vienu HTML stila Paragraph katram, lai garantētu lauku neizzušanu
        rec_text = f"<b>{L['receiver']}</b><br/><br/><b>{rec_name}</b><br/><b>{L['reg_no']}:</b> {rec_reg}<br/><b>{L['legal_address']}:</b> {rec_addr}"
        cus_text = f"<b>{L['customer']}</b><br/><br/><b>{cus_name}</b><br/><b>{L['reg_no']}:</b> {cus_reg}<br/><b>{L['legal_address']}:</b> {cus_addr}"

        receiver_para = Paragraph(rec_text, style_normal)
        customer_para = Paragraph(cus_text, style_normal)

        e_invoice_table = Table([[receiver_para, customer_para]], colWidths=[85*mm, 85*mm])
        e_invoice_table.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('LEFTPADDING', (0,0), (-1,-1), 0),
            ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ]))
        elements.append(e_invoice_table)
        elements.append(Spacer(1, 5*mm))
        elements.append(HorizontalLine(thickness=0.2))
        elements.append(Spacer(1, 5*mm))

        elements.append(Paragraph(f"<b>{L['sender']}</b>", style_normal))
        elements.append(Spacer(1, 3*mm))
    else:
        elements.append(Paragraph(L['client'], style_bold))
        elements.append(Spacer(1, 2*mm))

        elements.append(Paragraph(f"<b>{data.get('client_name', '')}</b>", style_normal))
        elements.append(Paragraph(f"<i>{L['address']}: {data.get('client_address', '')}</i>", style_normal))
        elements.append(Paragraph(f"<i>{L['reg_no']}: {data.get('client_reg_no', '')}</i>", style_normal))
        elements.append(Paragraph(f"<i>{L['vat_no']}: {data.get('client_vat_no', '')}</i>", style_normal))

        elements.append(Spacer(1, 3*mm))
        elements.append(HorizontalLine(thickness=0.2))
        elements.append(Spacer(1, 5*mm))
    
    # ==========================================
    # 3. PIEGĀDĀTĀJS UN BANKA
    # ==========================================
    sender_data = [
        Paragraph("<b>SIA Bratus</b>", style_normal),
        Paragraph(f"<i>{L['address']}: {L['seller_address'][0]}</i>", style_normal),
        Paragraph(f"<i>{L['seller_address'][1]}</i>", style_normal),
        Paragraph(f"<i>{L['reg_no']}: 40203628316</i>", style_normal),
        Paragraph(f"<i>{L['vat_no']}: LV40203628316</i>", style_normal),
        Paragraph(f"<i>{L['phone']}: +371 24424434</i>", style_normal),
    ]
    
    bank_data = [
        Paragraph("<b><i>AS Swedbank</i></b>", style_normal),
        Paragraph(f"<i>SWIFT/BIC: HABALV22</i>", style_normal),
        Paragraph(f"<i>{L['bank_account']}: <b>LV64HABA0551060367591</b></i>", style_normal),
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
        Paragraph(L['col_name'], style_table_header),
        Paragraph(L['col_unit'], style_table_header),
        Paragraph(L['col_qty'], style_table_header),
        Paragraph(L['col_price'], style_table_header),
        Paragraph(L['col_total'], style_table_header)
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
    
    totals_data = [["", label, value] for label, value in totals_rows(data)]
    last_row_idx = len(totals_data) - 1

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
        
        bold_text = f'<font name="{BOLD_FONT}">{L['advance_due']} ({percent_val}%): {formatted_advance} €</font>'
        elements.append(Paragraph(bold_text, style_cell_right))
        elements.append(Spacer(1, 2*mm))

    amount_words = data.get('amount_words', '')
    prefix = L['in_words']
    elements.append(Paragraph(f"<i>{prefix}{amount_words}</i>", 
                              ParagraphStyle('Words', parent=style_italic, alignment=TA_RIGHT)))

    vat_note = data.get('vat_note', '').strip()
    if not data.get('vat_enabled', True) and vat_note:
        elements.append(Spacer(1, 2*mm))
        elements.append(Paragraph(vat_note, ParagraphStyle('VatNote', parent=style_italic, alignment=TA_RIGHT)))
    
    # ==========================================
    # 7. PAPILDINFO (Komentāri)
    # ==========================================
    comments = data.get('comments', '').strip()
    if comments:
        elements.append(Spacer(1, 10*mm))
        elements.append(Paragraph(f"<font name='{BOLD_FONT}'>{L['comments']}</font>", style_bold))
        comments_html = comments.replace('\n', '<br/>')
        elements.append(Paragraph(comments_html, style_normal))

    # ==========================================
    # 8. PARAKSTI
    # ==========================================
    elements.append(Spacer(1, 5*mm))
    elements.append(HorizontalLine(thickness=0.2))
    elements.append(Spacer(1, 2*mm))
    
    signatory = data.get('signatory', 'SIA Bratus valdes loceklis Adrians Stankevičs')
    
    prepared_label, received_text = signature_texts(doc_type, lang)
    prepared_text = f"{prepared_label} <i>{signatory}</i>"
    
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
