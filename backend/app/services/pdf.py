from io import BytesIO
import hashlib
import re
from datetime import timedelta, timezone
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Flowable, Paragraph, SimpleDocTemplate, Spacer

from app.models.entities import ContractSession, ContractVersion, Message, ContractParticipant


FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]
STAMP_BLUE = colors.HexColor("#2457A6")
MOSCOW_TZ = timezone(timedelta(hours=3))


def get_pdf_font_name() -> str:
    for font_path in FONT_CANDIDATES:
        if Path(font_path).exists():
            pdfmetrics.registerFont(TTFont("AIArbitrSans", font_path))
            return "AIArbitrSans"
    return "Helvetica"


def para(text: str, style: ParagraphStyle) -> Paragraph:
    safe = (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br/>")
    )
    return Paragraph(safe, style)


def hash_value(value: str) -> str:
    normalized = (value or "").strip().lower()
    if not normalized:
        return ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def hash_text(value: str) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def extract_party_name(contract_text: str, legal_role: str) -> str:
    for line in (contract_text or "").splitlines():
        if f"«{legal_role}»" not in line:
            continue
        match = re.search(r"Гражданин РФ\s+([^,]+)", line, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return "не указано"


def extract_contract_title(contract_text: str, fallback: str) -> str:
    first_line = next((line.strip() for line in (contract_text or "").splitlines() if line.strip()), "")
    if not first_line:
        return fallback or "Договор"
    return re.sub(r"\s*№\s*\S+.*$", "", first_line, count=1).title()


def format_document_time(value) -> str:
    if not value:
        return "дата не указана"
    aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return aware.astimezone(MOSCOW_TZ).strftime("%d.%m.%Y %H:%M МСК")


def draw_page_header(canvas, doc, session, final_version, font_name: str) -> None:
    canvas.saveState()
    width, height = A4
    canvas.setStrokeColor(colors.HexColor("#CBD5E1"))
    canvas.setLineWidth(0.5)
    canvas.line(doc.leftMargin, height - 13 * mm, width - doc.rightMargin, height - 13 * mm)
    canvas.setFillColor(colors.HexColor("#475569"))
    canvas.setFont(font_name, 7.5)
    canvas.drawString(doc.leftMargin, height - 10 * mm, f"AI-Arbitr · {format_document_time(session.finalized_at)}")
    canvas.drawRightString(
        width - doc.rightMargin,
        height - 10 * mm,
        f"Версия № {final_version.version_number} · стр. {doc.page}",
    )
    canvas.restoreState()


class VerificationStamp(Flowable):
    def __init__(self, session: ContractSession, font_name: str):
        super().__init__()
        self.width = 82 * mm
        self.height = 29 * mm
        self.session = session
        self.font_name = font_name
        self.hAlign = "CENTER"

    def draw(self):
        canvas = self.canv
        canvas.saveState()
        canvas.setStrokeColor(STAMP_BLUE)
        canvas.setFillColor(colors.white)
        canvas.setLineWidth(1.2)
        canvas.roundRect(0, 0, self.width, self.height, 3 * mm, stroke=1, fill=1)
        canvas.setLineWidth(0.45)
        canvas.roundRect(2 * mm, 2 * mm, self.width - 4 * mm, self.height - 4 * mm, 2 * mm, stroke=1, fill=0)
        canvas.setFillColor(STAMP_BLUE)
        canvas.setFont(self.font_name, 12)
        canvas.drawCentredString(self.width / 2, self.height - 8 * mm, "AI-ARBITR")
        canvas.setFont(self.font_name, 8)
        canvas.drawCentredString(self.width / 2, self.height - 13 * mm, "ДОКУМЕНТ ПОДПИСАН")
        canvas.drawCentredString(self.width / 2, self.height - 18 * mm, "ПРОСТАЯ ЭЛЕКТРОННАЯ ПОДПИСЬ")
        canvas.setFont(self.font_name, 6.5)
        canvas.drawCentredString(
            self.width / 2,
            4.2 * mm,
            f"{format_document_time(self.session.finalized_at)} · ID {str(self.session.id)[:8]}",
        )
        canvas.restoreState()


def mask_email(email: str) -> str:
    if not email or "@" not in email:
        return "не указан"
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        masked_local = local[:1] + "*"
    else:
        masked_local = f"{local[:2]}***{local[-1:]}"
    return f"{masked_local}@{domain}"


def safe_event_content(content: str) -> str:
    parts = (content or "").split("|")
    event = parts[0] if parts else ""
    if event in {"VERSION_SENT", "VERSION_APPROVED"}:
        version = parts[1] if len(parts) > 1 else ""
        email = parts[2] if len(parts) > 2 else ""
        extras = [part for part in parts[3:] if "@" not in part]
        safe = [
            event,
            f"version:{version}" if version else "version:не указана",
            f"email_mask:{mask_email(email)}",
        ]
        email_hash = hash_value(email)
        if email_hash:
            safe.append(f"email_sha256:{email_hash}")
        safe.extend(extras)
        return " | ".join(safe)
    return content


def build_contract_pdf(
    session: ContractSession,
    final_version: ContractVersion,
    participants: list[ContractParticipant],
    messages: list[Message],
) -> bytes:
    buffer = BytesIO()
    font_name = get_pdf_font_name()
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="AIBase",
            parent=styles["Normal"],
            fontName=font_name,
            fontSize=10,
            leading=14,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            name="AITitle",
            parent=styles["Title"],
            fontName=font_name,
            fontSize=18,
            leading=24,
            spaceAfter=12,
        )
    )
    styles.add(
        ParagraphStyle(
            name="AIHeading",
            parent=styles["Heading2"],
            fontName=font_name,
            fontSize=13,
            leading=18,
            spaceBefore=10,
            spaceAfter=8,
        )
    )

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=20 * mm,
        bottomMargin=18 * mm,
        title="AI-Arbitr - договор",
    )

    story = [
        para(final_version.content, styles["AIBase"]),
        Spacer(1, 12),
        para(
            "Договор подписан сторонами с помощью сервиса AI-Arbitr путем обмена электронными сообщениями "
            "с применением простой электронной подписи в соответствии с Федеральным законом "
            "от 06.04.2011 № 63-ФЗ «Об электронной подписи».",
            styles["AIBase"],
        ),
        Spacer(1, 8),
        VerificationStamp(session, font_name),
    ]

    header = lambda canvas, current_doc: draw_page_header(canvas, current_doc, session, final_version, font_name)
    doc.build(story, onFirstPage=header, onLaterPages=header)
    return buffer.getvalue()


def build_interaction_certificate_pdf(
    session: ContractSession,
    final_version: ContractVersion,
    participants: list[ContractParticipant],
    messages: list[Message],
) -> bytes:
    buffer = BytesIO()
    font_name = get_pdf_font_name()
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="AIBase",
            parent=styles["Normal"],
            fontName=font_name,
            fontSize=10,
            leading=14,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            name="AITitle",
            parent=styles["Title"],
            fontName=font_name,
            fontSize=18,
            leading=24,
            spaceAfter=12,
        )
    )
    styles.add(
        ParagraphStyle(
            name="AIHeading",
            parent=styles["Heading2"],
            fontName=font_name,
            fontSize=13,
            leading=18,
            spaceBefore=10,
            spaceAfter=8,
        )
    )

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=20 * mm,
        bottomMargin=18 * mm,
        title="AI-Арбитр - справка электронного взаимодействия",
    )

    content_hash = session.final_content_hash or hash_text(final_version.content)
    party_names = {
        "party_1": extract_party_name(final_version.content, "Наймодатель"),
        "party_2": extract_party_name(final_version.content, "Наниматель"),
    }
    story = [
        para("Справка о факте электронного взаимодействия", styles["AITitle"]),
        para(f"Наименование: {extract_contract_title(final_version.content, session.title)}", styles["AIBase"]),
        para(f"Финальная версия: № {final_version.version_number}", styles["AIBase"]),
        para(f"Дата финализации: {session.finalized_at or 'не указана'}", styles["AIBase"]),
        para("Стороны", styles["AIHeading"]),
    ]

    for participant in participants:
        user_email = participant.user.email if getattr(participant, "user", None) else ""
        story.append(
            para(
                f"{party_names.get(participant.role.value, 'не указано')} — {user_email}. "
                f"Подписано: {participant.signed_at or 'не указано'}.",
                styles["AIBase"],
            )
        )

    story.extend(
        [
            para("Служебные данные", styles["AIHeading"]),
            para(f"ID договора: {session.id}", styles["AIBase"]),
            para(f"SHA-256 финального текста: {content_hash}", styles["AIBase"]),
            para("Способ подписания: простая электронная подпись через подтвержденные адреса электронной почты.", styles["AIBase"]),
            Spacer(1, 10),
            VerificationStamp(session, font_name),
        ]
    )

    header = lambda canvas, current_doc: draw_page_header(canvas, current_doc, session, final_version, font_name)
    doc.build(story, onFirstPage=header, onLaterPages=header)
    return buffer.getvalue()
