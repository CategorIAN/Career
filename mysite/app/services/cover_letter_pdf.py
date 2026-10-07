from html import escape
from io import BytesIO
from pathlib import Path
import re

from django.conf import settings
from django.utils import timezone
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer

from app.models import Application


SIGNATURE_IMAGE_PATH = Path(settings.BASE_DIR) / "app" / "static" / "app" / "images" / "signature.jpg"


class CoverLetterPDFError(Exception):
    """The cover-letter PDF could not be generated."""


def cover_letter_filename(application: Application) -> str:
    company_name = (
        application.company.name
        if application.company_id is not None
        else application.job_posting.company_name
    )
    posting_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", application.job_posting.title)
    safe_company_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", company_name)
    posting_name = posting_name.strip().rstrip(".") or "Job Posting"
    safe_company_name = safe_company_name.strip().rstrip(".") or "Company"
    document_date = timezone.localdate().strftime("%y.%m.%d")
    return f"{document_date} {posting_name} @ {safe_company_name} Cover Letter.pdf"


def _signature_image():
    if not SIGNATURE_IMAGE_PATH.is_file():
        raise CoverLetterPDFError(
            f"Signature image is missing: {SIGNATURE_IMAGE_PATH}"
        )

    signature = Image(str(SIGNATURE_IMAGE_PATH))
    signature._restrictSize(1.6 * inch, 0.55 * inch)
    signature.hAlign = "LEFT"
    return signature


def _body_paragraphs(cover_letter, style):
    paragraphs = []
    for paragraph in re.split(r"\n\s*\n", cover_letter.strip()):
        lines = [escape(line) for line in paragraph.splitlines()]
        paragraphs.append(Paragraph("<br/>".join(lines), style))
        paragraphs.append(Spacer(1, 0.16 * inch))
    return paragraphs


def build_cover_letter_pdf(application: Application) -> bytes:
    """Build a polished PDF from an Application's saved cover-letter body."""
    cover_letter = application.cover_letter.strip()
    if not cover_letter:
        raise CoverLetterPDFError("This application does not have a cover letter.")

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        leftMargin=0.9 * inch,
        rightMargin=0.9 * inch,
        topMargin=0.85 * inch,
        bottomMargin=0.85 * inch,
        title=cover_letter_filename(application).removesuffix(".pdf"),
        author="Ian Kessler",
    )
    styles = getSampleStyleSheet()
    body_style = ParagraphStyle(
        "CoverLetterBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=11,
        leading=15,
        alignment=TA_LEFT,
        spaceAfter=0,
    )
    closing_style = ParagraphStyle(
        "CoverLetterClosing",
        parent=body_style,
        spaceAfter=0,
    )

    story = _body_paragraphs(cover_letter, body_style)
    story.extend(
        [
            Spacer(1, 0.12 * inch),
            Paragraph("Sincerely,", closing_style),
            Spacer(1, 0.06 * inch),
            _signature_image(),
            Spacer(1, 0.04 * inch),
            Paragraph("Ian Kessler", closing_style),
        ]
    )
    try:
        document.build(story)
    except Exception as error:
        raise CoverLetterPDFError("Unable to build the cover-letter PDF.") from error
    return buffer.getvalue()
