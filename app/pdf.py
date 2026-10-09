from datetime import date
from io import BytesIO

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas

W, H = landscape(A4)
INK, ACCENT, MUTED = HexColor("#1f2937"), HexColor("#1d4ed8"), HexColor("#6b7280")

TITLES = {
    "winner": "Certificate of Achievement",
    "place": "Certificate of Merit",
    "participation": "Certificate of Participation",
}
LEAD = {
    None: "in recognition of successfully completing",
    "winner": "in recognition of outstanding performance as the winner of",
    "place": "in recognition of securing a place in",
    "participation": "in recognition of participating in",
}


def fit(value: str, font: str, size: int, max_width: float, floor: int = 10) -> int:
    while size > floor and stringWidth(value, font, size) > max_width:
        size -= 1
    return size


def line(c: Canvas, value: str, y: float, font: str, size: int, color=INK, max_width: float = W - 160):
    c.setFont(font, fit(value, font, size, max_width))
    c.setFillColor(color)
    c.drawCentredString(W / 2, y, value)


def render(
    *,
    cert_id: str,
    name: str,
    title: str,
    event_name: str,
    issuer: str,
    issued_on: date,
    category: str | None = None,
    logo: bytes | None = None,
) -> bytes:
    buf = BytesIO()
    c = Canvas(buf, pagesize=(W, H), pageCompression=1)
    c.setTitle(f"{title} - {name}")
    c.setAuthor(issuer)

    c.setStrokeColor(ACCENT)
    c.setLineWidth(4)
    c.rect(24, 24, W - 48, H - 48)
    c.setLineWidth(1)
    c.rect(36, 36, W - 72, H - 72)

    if logo:
        c.drawImage(
            ImageReader(BytesIO(logo)),
            W / 2 - 80,
            H - 96,
            160,
            50,
            preserveAspectRatio=True,
            anchor="c",
            mask="auto",
        )

    line(c, title.upper(), H - 140, "Helvetica-Bold", 36, ACCENT)
    line(c, "This certificate is proudly presented to", H - 200, "Helvetica", 16, MUTED)
    line(c, name, H - 270, "Helvetica-Bold", 44)

    c.setStrokeColor(MUTED)
    c.setLineWidth(0.5)
    c.line(W / 2 - 200, H - 285, W / 2 + 200, H - 285)

    line(c, LEAD[category], H - 330, "Helvetica", 16, MUTED)
    line(c, event_name, H - 370, "Helvetica-Bold", 24)

    c.setFillColor(INK)
    c.setFont("Helvetica", 12)
    c.drawString(90, 90, f"Issued on {issued_on:%d %B %Y}")
    c.drawRightString(W - 90, 90, f"Issued by {issuer}")
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 8)
    c.drawCentredString(W / 2, 55, f"Certificate ID: {cert_id}")

    c.showPage()
    c.save()
    return buf.getvalue()
