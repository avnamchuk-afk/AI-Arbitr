from io import BytesIO
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

from app.models.entities import ContractSession, ContractVersion, Message, ContractParticipant


FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]


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
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="AI-Арбитр - договор и история",
    )

    story = [
        para(session.title or "Договор", styles["AITitle"]),
        para(final_version.content, styles["AIBase"]),
        Spacer(1, 10),
        para("Отметки простой электронной подписи", styles["AIHeading"]),
    ]
    for participant in participants:
        user_email = participant.user.email if getattr(participant, "user", None) else "не привязан"
        signed_at = session.finalized_at if participant.role.value == "party_1" else participant.joined_at
        if participant.approval_status.value == "approved":
            story.append(
                para(
                    "Подписано простой электронной подписью через сервис AI-arbitr. "
                    f"Сторона: {participant.role.value}. Email/идентификатор: {user_email}. "
                    f"Дата и время подписания: {signed_at or 'не указано'}. "
                    f"ID договора: {session.id}.",
                    styles["AIBase"],
                )
            )

    story.extend(
        [
            para(f"ID сессии: {session.id}", styles["AIBase"]),
            para(f"Дата финализации: {session.finalized_at or 'не указана'}", styles["AIBase"]),
            PageBreak(),
            para("История обсуждения", styles["AIHeading"]),
        ]
    )

    for message in messages:
        created_at = message.created_at.isoformat() if message.created_at else ""
        story.append(para(f"{created_at} / {message.role.value}", styles["AIHeading"]))
        story.append(para(message.content, styles["AIBase"]))

    doc.build(story)
    return buffer.getvalue()
