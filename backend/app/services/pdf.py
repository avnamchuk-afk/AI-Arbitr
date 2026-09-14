from io import BytesIO
import hashlib
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


def hash_value(value: str) -> str:
    normalized = (value or "").strip().lower()
    if not normalized:
        return ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def hash_text(value: str) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


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
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="AI-Арбитр - справка электронного взаимодействия",
    )

    content_hash = hash_text(final_version.content)
    story = [
        para("Справка о факте электронного взаимодействия", styles["AITitle"]),
        para(
            "Документ сформирован сервисом AI-arbitr и фиксирует технические сведения о согласовании договора. "
            "Полные паспортные данные, телефон и полный адрес электронной почты в справке не раскрываются.",
            styles["AIBase"],
        ),
        para("Договор", styles["AIHeading"]),
        para(f"Наименование: {session.title or 'Договор'}", styles["AIBase"]),
        para(f"ID сессии: {session.id}", styles["AIBase"]),
        para(f"Статус: {session.status.value}", styles["AIBase"]),
        para(f"Финальная версия: № {final_version.version_number}, ID {final_version.id}", styles["AIBase"]),
        para(f"Дата финализации: {session.finalized_at or 'не указана'}", styles["AIBase"]),
        para(f"SHA-256 текста финальной версии: {content_hash}", styles["AIBase"]),
        para("Стороны", styles["AIHeading"]),
    ]

    for participant in participants:
        user_email = participant.user.email if getattr(participant, "user", None) else ""
        email_hash = hash_value(user_email)
        story.append(
            para(
                " | ".join(
                    [
                        f"Роль: {participant.role.value}",
                        f"UID стороны: {participant.user_id or participant.id}",
                        f"Статус: {participant.approval_status.value}",
                        f"Версия согласия: {participant.approved_version_id or 'не указана'}",
                        f"Дата присоединения: {participant.joined_at or 'не указана'}",
                        f"Email: {mask_email(user_email)}",
                        f"Email SHA-256: {email_hash or 'не указан'}",
                    ]
                ),
                styles["AIBase"],
            )
        )

    story.append(para("Технические события", styles["AIHeading"]))
    for message in messages:
        if message.role.value != "system":
            continue
        content = safe_event_content(message.content)
        if not content:
            continue
        created_at = message.created_at.isoformat() if message.created_at else ""
        story.append(para(f"{created_at} / {message.role.value}: {content}", styles["AIBase"]))

    story.extend(
        [
            para("Назначение справки", styles["AIHeading"]),
            para(
                "Справка предназначена для подтверждения факта электронного взаимодействия, согласования версии договора "
                "и формирования простой электронной подписи в сервисе AI-arbitr.",
                styles["AIBase"],
            ),
        ]
    )

    doc.build(story)
    return buffer.getvalue()
