from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage, Flowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_RIGHT, TA_LEFT, TA_CENTER
import io
import os

# --- Krāsu definīcijas (no attēla) ---
THEME_COLOR = colors.HexColor("#CDBF96") # Bēšs/Zelts tonis
TEXT_COLOR = colors.black

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
    # A4 platums ir 210mm. Ar 20mm malām paliek 170mm darba zona.
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
    
    # Galvene (Header) labajā pusē
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

    # Tabulas virsraksti (balti, centrēti)
    style_table_header = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName=BOLD_FONT,
        fontSize=10,
        alignment=TA_CENTER,
        textColor=colors.white,
        leading=11
    )
    
    # Šūnu stili
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
    
    # Labā puse
    header_text = [
        Paragraph(f"{doc_type} Nr. {doc_id}", style_header_title),
        Spacer(1, 2*mm),
        Paragraph(f"Datums: {date}", style_header_info),
        Paragraph(f"Apmaksāt līdz: {due_date}", style_header_info),
    ]
    
    # Tabula: Logo pa kreisi, Info pa labi
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
    elements.append(HorizontalLine()) # Līnija
    elements.append(Spacer(1, 5*mm))
    
    # ==========================================
    # 2. KLIENTS
    # ==========================================
    elements.append(Paragraph("KLIENTS", style_bold))
    elements.append(Spacer(1, 2*mm))
    
    # Klients bold, adrese italic (kā paraugā)
    elements.append(Paragraph(f"<b>{data.get('client_name', '')}</b>", style_normal))
    elements.append(Paragraph(f"<i>Adrese: {data.get('client_address', '')}</i>", style_normal))
    elements.append(Paragraph(f"<i>Reģ. Nr.: {data.get('client_reg_no', '')}</i>", style_normal))
    elements.append(Paragraph(f"<i>PVN Nr.: {data.get('client_vat_no', '')}</i>", style_normal))
    
    elements.append(Spacer(1, 3*mm))
    elements.append(HorizontalLine(thickness=0.2)) # Plānāka līnija
    elements.append(Spacer(1, 5*mm))
    
    # ==========================================
    # 3. PIEGĀDĀTĀJS UN BANKA
    # ==========================================
    # Veidojam kā tabulu divās kolonnās
    
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
    
    # Virsraksti (Paragraph, lai ietilptu un centrētos)
    headers = [
        Paragraph("NOSAUKUMS", style_table_header),
        Paragraph("Mērvienība", style_table_header),
        Paragraph("DAUDZUMS", style_table_header),
        Paragraph("CENA (EUR)", style_table_header),
        Paragraph("KOPĀ (EUR)", style_table_header)
    ]
    
    table_data = [headers]
    items = data.get('items', [])
    
    # Ja nav preču, pievienojam tukšas rindas vizuālajam izskatam (kā paraugā)
    if not items:
        for _ in range(3):
            items.append({'name': '', 'unit': '', 'qty': '', 'price': '', 'total': ''})

    for item in items:
        table_data.append([
            Paragraph(item['name'], style_cell_left),
            Paragraph(item['unit'], style_cell_center),
            Paragraph(str(item['qty']), style_cell_center),
            Paragraph(item['price'], style_cell_right),
            Paragraph(item['total'], style_cell_right)
        ])
        
    # Kolonnu platumi (pielāgoti lai kopā ~170mm)
    col_widths = [65*mm, 25*mm, 25*mm, 25*mm, 30*mm]
    
    t = Table(table_data, colWidths=col_widths)
    
    t.setStyle(TableStyle([
        # --- GALVENES STILS ---
        ('BACKGROUND', (0,0), (-1,0), THEME_COLOR), # Bēšs fons
        ('VALIGN', (0,0), (-1,0), 'MIDDLE'),        # Centrēts vertikāli
        
        # Baltas vertikālās līnijas galvenē
        ('LINEBEFORE', (1,0), (-1,0), 1, colors.white), 
        
        # --- SATURA STILS ---
        ('VALIGN', (0,1), (-1,-1), 'TOP'), # Saturs pie augšas
        
        # Bēšas līnijas visam saturam (režģis)
        ('GRID', (0,0), (-1,-1), 0.5, THEME_COLOR),
        
        # Polsterējums
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
    
    totals_data = [
        ["", "KOPĀ", f"{subtotal} €"],
        ["", "PVN", f"{vat} €"],
        ["", "Kopumā", f"{total} €"]
    ]
    
    # Pielāgojam platumus, lai sakristu ar augšējo tabulu
    # Pēdējās 3 kolonnas augšā bija: 25 + 25 + 30 = 80mm
    # Te mums vajag 2 kolonnas beigās.
    totals_table = Table(totals_data, colWidths=[90*mm, 50*mm, 30*mm])
    
    totals_table.setStyle(TableStyle([
        ('ALIGN', (1,0), (-1,-1), 'RIGHT'), # Visu centrēt pa labi
        ('FONTNAME', (1,0), (1,2), BOLD_FONT), # Nosaukumi Bold
        ('FONTNAME', (2,0), (2,2), REGULAR_FONT), # Skaitļi Regular
        ('FONTNAME', (1,2), (2,2), BOLD_FONT), # Pēdējā rinda (Kopumā) Bold
        ('TEXTCOLOR', (0,0), (-1,-1), TEXT_COLOR),
    ]))
    elements.append(totals_table)
    
    # ==========================================
    # 6. SUMMA VĀRDIEM UN AVANSS
    # ==========================================
    elements.append(Spacer(1, 5*mm))
    
    # Avansa tabula (ja ir)
    if doc_type == "Avansa rēķins":
        raw_advance = data.get('raw_advance', 0.0)
        formatted_advance = fmt_curr(raw_advance)
        percent_val = int(round(data.get('advance_percent', 0)))
        
        elements.append(Paragraph(f"<b>APMAKSĀJAMAIS AVANSS ({percent_val}%): {formatted_advance} €</b>", style_cell_right))
        elements.append(Spacer(1, 2*mm))

    amount_words = data.get('amount_words', '')
    prefix = "Vārdiem: "
    # Kursīvā, pa labi
    elements.append(Paragraph(f"<i>{prefix}{amount_words}</i>", 
                              ParagraphStyle('Words', parent=style_italic, alignment=TA_RIGHT)))
    
    # ==========================================
    # 7. PARAKSTI UN PAPILDINFO
    # ==========================================
    elements.append(Spacer(1, 5*mm))
    elements.append(HorizontalLine(thickness=0.2))
    elements.append(Spacer(1, 2*mm))
    
    elements.append(Paragraph("<b>Papildus informācija:</b>", style_bold))
    elements.append(Spacer(1, 10*mm))
    
    signatory = data.get('signatory', 'SIA Bratus valdes loceklis Adrians Stankevičs')
    
    if doc_type == "Pavadzīme":
        prepared_text = f"Pavadzīmi sagatavoja: <i>{signatory}</i>"
        received_text = "Pavadzīmi saņēma:"
    else:
        prepared_text = f"Rēķinu sagatavoja: <i>{signatory}</i>"
        received_text = "Rēķinu saņēma:"
    
    # Parakstu līnijas
    sig_table_data = [
        [Paragraph(prepared_text, style_italic), "__________________________"],
        [Paragraph(received_text, style_italic), "__________________________"]
    ]
    
    sig_table = Table(sig_table_data, colWidths=[100*mm, 70*mm])
    sig_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'BOTTOM'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 10),
        ('ALIGN', (1,0), (1,1), 'RIGHT'), # Līnijas pa labi
    ]))
    elements.append(sig_table)
    
    doc.build(elements)
    buffer.seek(0)
    return buffer
