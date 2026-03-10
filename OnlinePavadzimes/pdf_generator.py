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

THEME_COLOR = colors.HexColor("#CDBF96")
TEXT_COLOR = colors.black
REGULAR_FONT = 'Helvetica'
BOLD_FONT = 'Helvetica-Bold'
ITALIC_FONT = 'Helvetica-Oblique'

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

def generate_pdf(data):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=20*mm, leftMargin=20*mm, topMargin=15*mm, bottomMargin=15*mm)
    styles = getSampleStyleSheet()
    
    style_normal = ParagraphStyle('CustomNormal', parent=styles['Normal'], fontName=REGULAR_FONT, fontSize=10, leading=13)
    style_bold = ParagraphStyle('CustomBold', parent=styles['Normal'], fontName=BOLD_FONT, fontSize=10, leading=13)
    style_italic = ParagraphStyle('CustomItalic', parent=styles['Normal'], fontName=ITALIC_FONT, fontSize=10, leading=13)
    style_header_title = ParagraphStyle('HeaderTitle', parent=styles['Normal'], fontName=BOLD_FONT, fontSize=14, alignment=TA_RIGHT)
    style_table_header = ParagraphStyle('TableHeader', parent=styles['Normal'], fontName=BOLD_FONT, fontSize=10, alignment=TA_CENTER, textColor=colors.white)

    elements = []
    
    # Header & Logo
    doc_type = data.get('doc_type', 'Pavadzīme')
    doc_id = data.get('doc_id', 'BR 0000')
    header_text = [Paragraph(f"{doc_type} Nr. {doc_id}", style_header_title), Paragraph(f"Datums: {data.get('date', '')}", style_normal), Paragraph(f"Apmaksāt līdz: {data.get('due_date', '')}", style_normal)]
    elements.append(Table([[Paragraph("<b>SIA BRATUS</b>", style_bold), header_text]], colWidths=[85*mm, 85*mm]))
    elements.append(HorizontalLine())
    elements.append(Spacer(1, 5*mm))

    # Client Info
    elements.append(Paragraph(f"<b>KLIENTS: {data.get('client_name', '')}</b>", style_normal))
    elements.append(Paragraph(f"Adrese: {data.get('client_address', '')}", style_italic))
    elements.append(Spacer(1, 5*mm))

    # Items Table
    headers = [Paragraph("NOSAUKUMS", style_table_header), Paragraph("Mērv.", style_table_header), Paragraph("DAUDZUMS", style_table_header), Paragraph("CENA (EUR)", style_table_header), Paragraph("Cena kopā (EUR)", style_table_header)]
    table_data = [headers]
    for item in data.get('items', []):
        table_data.append([item['name'], item['unit'], item['qty'], item['price'], item['total']])
    
    t = Table(table_data, colWidths=[65*mm, 20*mm, 25*mm, 25*mm, 35*mm])
    t.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,0), THEME_COLOR), ('GRID', (0,0), (-1,-1), 0.5, THEME_COLOR), ('VALIGN', (0,0), (-1,-1), 'MIDDLE')]))
    elements.append(t)
    
    # Totals
    elements.append(Spacer(1, 5*mm))
    elements.append(Paragraph(f"<b>KOPĀ: {data.get('total', '0.00')} €</b>", style_header_title))
    elements.append(Paragraph(f"<i>Vārdiem: {data.get('amount_words', '')}</i>", style_italic))
    
    doc.build(elements)
    buffer.seek(0)
    return buffer
