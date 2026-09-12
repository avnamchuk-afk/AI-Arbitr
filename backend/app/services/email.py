import smtplib
from email.message import EmailMessage

from app.core.config import settings


def smtp_is_configured() -> bool:
    return bool(settings.smtp_host and settings.smtp_user and settings.smtp_password and settings.smtp_from)


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

    if settings.smtp_port == 465:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port) as smtp:
            smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(message)
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
            smtp.starttls()
            smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(message)


def send_contract_invite(email: str, link: str, title: str, pdf_link: str | None = None) -> None:
    if not smtp_is_configured():
        return

    message = EmailMessage()
    message["Subject"] = "Согласование договора в AI-Арбитр"
    message["From"] = settings.smtp_from
    message["To"] = email
    message.set_content(
        "Здравствуйте!\n\n"
        f"Вам направлен на согласование договор: {title}.\n\n"
        "Посмотреть договор и подтвердить согласие можно по ссылке:\n"
        f"{link}\n\n"
        + (f"PDF-версия договора:\n{pdf_link}\n\n" if pdf_link else "")
        + "Если условия подходят, нажмите кнопку согласия и укажите свои данные.\n"
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
