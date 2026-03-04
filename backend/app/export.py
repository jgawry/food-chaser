"""Generate a PDF report of deals."""
import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, HRFlowable,
)

# Register a Unicode-capable font so Polish characters render correctly.
# Try Calibri (Windows) → Arial (Windows) → fall back to Helvetica.
def _try_register(name, bold_name, path, bold_path):
    try:
        pdfmetrics.registerFont(TTFont(name,      path))
        pdfmetrics.registerFont(TTFont(bold_name, bold_path))
        return name, bold_name
    except Exception:
        return None, None

_FONT_NORMAL, _FONT_BOLD = (
    _try_register('Calibri', 'Calibri-Bold',
                  r'C:\Windows\Fonts\calibri.ttf',
                  r'C:\Windows\Fonts\calibrib.ttf')
    or _try_register('Arial', 'Arial-Bold',
                     r'C:\Windows\Fonts\arial.ttf',
                     r'C:\Windows\Fonts\arialbd.ttf')
    or ('Helvetica', 'Helvetica-Bold')
)

_RED   = colors.HexColor('#e63946')
_GRAY  = colors.HexColor('#888888')
_LIGHT = colors.HexColor('#f5f5f5')
_WHITE = colors.white

PAGE_W, PAGE_H = A4
MARGIN = 1.5 * cm


def generate_deals_pdf(deals: list) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=MARGIN,
        title='Food Chaser — Deals Report',
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'Title', parent=styles['Normal'],
        fontSize=20, fontName=_FONT_BOLD,
        textColor=_RED, spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        'Subtitle', parent=styles['Normal'],
        fontSize=9, fontName=_FONT_NORMAL,
        textColor=_GRAY, spaceAfter=12,
    )
    cat_style = ParagraphStyle(
        'Cat', parent=styles['Normal'],
        fontSize=11, fontName=_FONT_BOLD,
        textColor=_RED, spaceBefore=14, spaceAfter=4,
    )
    cell_style = ParagraphStyle(
        'Cell', parent=styles['Normal'],
        fontSize=8, fontName=_FONT_NORMAL, leading=10,
    )
    cell_bold = ParagraphStyle(
        'CellBold', parent=cell_style,
        fontName=_FONT_BOLD,
    )

    # ── Helpers ──────────────────────────────────────────────────────────────

    def p(text, style=None):
        return Paragraph(str(text) if text else '—', style or cell_style)

    def price_str(val):
        return f'{val:.2f} zł' if val is not None else '—'

    def disc_str(val):
        return f'-{val}%' if val is not None else '—'

    # ── Group deals by category ───────────────────────────────────────────────

    from itertools import groupby
    sorted_deals = sorted(deals, key=lambda d: (d.get('category') or '', (d.get('name') or '').lower()))
    groups = {k: list(v) for k, v in groupby(sorted_deals, key=lambda d: d.get('category') or 'Inne')}

    # ── Build document elements ───────────────────────────────────────────────

    elements = []

    elements.append(Paragraph('Food Chaser', title_style))
    elements.append(Paragraph(
        f'Deals report · Generated {datetime.now().strftime("%d %b %Y, %H:%M")} · {len(deals)} products',
        subtitle_style,
    ))
    elements.append(HRFlowable(width='100%', thickness=1, color=_RED, spaceAfter=12))

    col_widths = [3.5*cm, 7.0*cm, 2.0*cm, 2.2*cm, 2.2*cm, 1.6*cm]

    header_row = [
        p('Brand', cell_bold), p('Name', cell_bold), p('Qty', cell_bold),
        p('Price', cell_bold), p('Was', cell_bold), p('Disc.', cell_bold),
    ]
    header_style = TableStyle([
        ('BACKGROUND',  (0, 0), (-1, 0), _RED),
        ('TEXTCOLOR',   (0, 0), (-1, 0), _WHITE),
        ('FONTNAME',    (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',    (0, 0), (-1, 0), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 5),
        ('TOPPADDING',    (0, 0), (-1, 0), 5),
    ])
    row_style = TableStyle([
        ('FONTSIZE',      (0, 0), (-1, -1), 8),
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [_WHITE, _LIGHT]),
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING',    (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING',   (0, 0), (-1, -1), 4),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 4),
        ('GRID',          (0, 0), (-1, -1), 0.25, colors.HexColor('#dddddd')),
    ])

    for category, items in groups.items():
        elements.append(Paragraph(f'{category}  ({len(items)} products)', cat_style))

        rows = [header_row]
        for d in items:
            rows.append([
                p(d.get('brand') or '—'),
                p(d.get('name') or '—'),
                p(d.get('qty') or '—'),
                p(price_str(d.get('price'))),
                p(price_str(d.get('old_price'))),
                p(disc_str(d.get('discount_pct'))),
            ])

        tbl = Table(rows, colWidths=col_widths, repeatRows=1)
        tbl.setStyle(header_style)
        tbl.setStyle(row_style)
        elements.append(tbl)
        elements.append(Spacer(1, 0.3*cm))

    doc.build(elements)
    return buf.getvalue()
