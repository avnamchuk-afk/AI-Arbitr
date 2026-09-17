import smtplib
from email.message import EmailMessage

from app.core.config import settings


def smtp_is_configured() -> bool:
    return bool(settings.smtp_host and settings.smtp_user and settings.smtp_password and settings.smtp_from)


def _send_message(message: EmailMessage) -> None:
    if settings.smtp_port == 465:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port) as smtp:
            smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(message)
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
            smtp.starttls()
            smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(message)


def send_magic_link(email: str, link: str) -> None:
    if not smtp_is_configured():
        return

    message = EmailMessage()
    message["Subject"] = "Вход в AI-Арбитр"
    message["From"] = settings.smtp_from
    message["To"] = email
    message.set_content(
        "Здравствуйте!\n\n"
        "Для входа в AI-Арбитр перейдите по ссылке:\n"
        f"{link}\n\n"
        "Ссылка действует 10 минут. Если вы не запрашивали вход, просто проигнорируйте письмо.\n"
    )

    _send_message(message)


def send_contract_invite(
    email: str,
    link: str,
    title: str,
    pdf_link: str | None = None,
    copy_to: str | None = None,
) -> None:
    if not smtp_is_configured():
        return

    message = EmailMessage()
    message["Subject"] = "Согласование договора в AI-Арбитр"
    message["From"] = settings.smtp_from
    message["To"] = email
    message.set_content(
        "Здравствуйте!\n\n"
        f"Вам направлен на согласование проект договора: {title}.\n\n"
        f"{link}\n\n"
        + (f"PDF-версия:\n{pdf_link}\n" if pdf_link else "")
    )
    _send_message(message)

    if copy_to and copy_to.lower() != email.lower():
        confirmation = EmailMessage()
        confirmation["Subject"] = "Проект договора направлен на согласование"
        confirmation["From"] = settings.smtp_from
        confirmation["To"] = copy_to
        confirmation.set_content(
            "Здравствуйте!\n\n"
            f"Вы направили проект договора на согласование: {title}.\n"
            f"Адрес второй стороны: {email}.\n\n"
            "Мы сообщим, когда вторая сторона подпишет договор.\n"
        )
        _send_message(confirmation)


def send_contract_signed_notice(
    email: str,
    title: str,
    pdf_bytes: bytes | None = None,
    certificate_bytes: bytes | None = None,
    calendar_link: str | None = None,
) -> None:
    if not smtp_is_configured():
        return

    message = EmailMessage()
    message["Subject"] = "Договор подписан в AI-Арбитр"
    message["From"] = settings.smtp_from
    message["To"] = email
    attachment_text = (
        "Финальная PDF-версия договора и справка о факте электронного взаимодействия приложены к этому письму."
        if certificate_bytes
        else "PDF-версия договора приложена к этому письму."
    )
    message.set_content(
        "Здравствуйте!\n\n"
        f"Договор подписан обеими сторонами: {title}.\n\n"
        f"{attachment_text}\n\n"
        + (f"Добавить договорное событие в календарь:\n{calendar_link}\n\n" if calendar_link else "")
        + "Если возникнет спор, откройте его через сервис AI-Арбитр.\n"
    )
    if pdf_bytes:
        message.add_attachment(
            pdf_bytes,
            maintype="application",
            subtype="pdf",
            filename="ai-arbitr-final.pdf",
        )
    if certificate_bytes:
        message.add_attachment(
            certificate_bytes,
            maintype="application",
            subtype="pdf",
            filename="ai-arbitr-certificate.pdf",
        )

    if settings.smtp_port == 465:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port) as smtp:
            smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(message)
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
            smtp.starttls()
            smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(message)


def send_dispute_notice(email: str, title: str, subject: str, body: str, app_link: str) -> None:
    if not smtp_is_configured():
        return

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.smtp_from
    message["To"] = email
    message.set_content(
        "Здравствуйте!\n\n"
        f"По договору «{title}» направлено уведомление:\n\n{body}\n\n"
        f"Открыть договор и ответить:\n{app_link}\n"
    )
    if settings.smtp_port == 465:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port) as smtp:
            smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(message)
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
            smtp.starttls()
            smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(message)


def send_signature_progress_notice(email: str, title: str, app_link: str) -> None:
    if not smtp_is_configured():
        return
    message = EmailMessage()
    message["Subject"] = "Вторая сторона подписала договор в AI-Арбитр"
    message["From"] = settings.smtp_from
    message["To"] = email
    message.set_content(
        "Здравствуйте!\n\n"
        f"Вторая сторона подписала договор: {title}.\n"
        "Откройте сервис, проверьте финальную редакцию и подпишите договор со своей стороны.\n\n"
        f"{app_link}\n"
    )
    if settings.smtp_port == 465:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port) as smtp:
            smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(message)
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
            smtp.starttls()
            smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(message)
