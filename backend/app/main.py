import uuid
from io import BytesIO
from datetime import datetime, time, timezone

from fastapi import Cookie, Depends, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, StreamingResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import get_cors_origins, settings
from app.db.base import Base
from app.db.session import engine, get_db
from app.models.entities import (
    ApprovalStatus,
    AuthToken,
    ContractParticipant,
    ContractSession,
    ContractVersion,
    Message,
    MessageRole,
    ParticipantRole,
    SessionStatus,
    User,
    now_utc,
)
from app.services.auth import generate_raw_token, hash_token, make_session_cookie, read_session_cookie, token_expires_at
from app.services.email import send_contract_invite, send_magic_link, smtp_is_configured
from app.services.pdf import build_contract_pdf
from app.services.privacy import contains_passport_like_data
from app.services.prompts import CONTRACT_SYSTEM_PROMPT, build_dispute_prompt
from app.services.yandex_gpt import YandexGPTError, ask_yandex_gpt

Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI-Arbitr API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LoginRequest(BaseModel):
    email: EmailStr
    personal_data_accepted: bool


class MessageRequest(BaseModel):
    content: str


class VersionRequest(BaseModel):
    content: str


class ChangesRequest(BaseModel):
    content: str


class InviteRequest(BaseModel):
    party_name: str = ""
    email: EmailStr | None = None


DEMO_SESSION_TITLE = "Пример: договор на лендинг"
DEMO_USER_PROMPT = (
    "Сгенерируй простой договор оказания услуг: исполнитель делает лендинг, "
    "заказчик платит 50 000 рублей, срок 10 рабочих дней."
)
DEMO_CONTRACT_TEXT = """### Договор оказания услуг

**1. Преамбула**
[Сторона 1], именуемая далее "Заказчик", и [Сторона 2], именуемая далее "Исполнитель",
заключили настоящий договор о нижеследующем.

**2. Предмет договора**
Исполнитель обязуется оказать услуги по созданию лендинга для Заказчика, а Заказчик
обязуется принять результат услуг и оплатить его.

**3. Стоимость и порядок расчетов**
Стоимость услуг составляет 50 000 рублей. Оплата производится в безналичном порядке
на расчетный счет Исполнителя в сроки, согласованные сторонами.

**4. Срок оказания услуг**
Исполнитель обязуется подготовить лендинг в течение 10 рабочих дней с даты согласования
технического задания и получения необходимых материалов от Заказчика.

**5. Права и обязанности сторон**
Исполнитель обязуется выполнить услуги добросовестно и передать результат Заказчику.
Заказчик обязуется предоставить необходимые материалы, рассмотреть результат и направить
мотивированные замечания либо подтвердить приемку.

**6. Ответственность сторон**
Стороны несут ответственность за нарушение обязательств в соответствии с законодательством
Российской Федерации и условиями настоящего договора.

**7. Порядок разрешения споров**
Стороны согласовали, что при возникновении разногласий они вправе обратиться к AI-Арбитру
для получения экспертного заключения по существу спора. AI-Арбитр анализирует текст договора
и историю согласования, после чего формирует рекомендации.

AI-Арбитр не является третейским судом, арбитражным учреждением или органом государственной
власти. Заключение AI-Арбитра носит рекомендательный характер и не ограничивает право любой
из сторон обратиться в компетентный суд за защитой своих интересов.

**8. Реквизиты и подписи сторон**
Заказчик: [реквизиты]

Исполнитель: [реквизиты]
"""


@app.get("/health")
def health():
    return {"status": "ok"}


def set_auth_cookie(response: Response, user: User) -> None:
    response.set_cookie(
        settings.session_cookie_name,
        make_session_cookie(str(user.id)),
        max_age=60 * 60 * 24 * 30,
        httponly=True,
        secure=settings.app_env != "local",
        samesite="lax",
    )


def get_current_user(
    db: Session = Depends(get_db),
    session_cookie: str | None = Cookie(default=None, alias=settings.session_cookie_name),
) -> User:
    user_id = read_session_cookie(session_cookie)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Требуется вход")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Требуется вход")
    return user


@app.post("/auth/magic-link")
def request_magic_link(payload: LoginRequest, db: Session = Depends(get_db)):
    if not payload.personal_data_accepted:
        raise HTTPException(status_code=400, detail="Нужно согласие на обработку персональных данных")

    user = db.query(User).filter(User.email == payload.email).one_or_none()
    if user is None:
        user = User(email=payload.email)
        db.add(user)
        db.flush()

    raw_token = generate_raw_token()
    db.add(
        AuthToken(
            email=payload.email,
            token_hash=hash_token(raw_token),
            expires_at=token_expires_at(),
        )
    )
    db.commit()

    verify_link = f"{settings.api_base_url}/auth/verify?token={raw_token}"
    send_magic_link(payload.email, verify_link)

    response = {"message": "Ссылка для входа отправлена на вашу почту"}
    if settings.app_env == "local" and not smtp_is_configured():
        response["dev_link"] = verify_link
    return response


@app.get("/auth/verify")
def verify_magic_link(token: str, db: Session = Depends(get_db)):
    token_hash = hash_token(token)
    auth_token = db.query(AuthToken).filter(AuthToken.token_hash == token_hash).one_or_none()
    if auth_token is None or auth_token.used or auth_token.expires_at < datetime.now(timezone.utc):
        return RedirectResponse(f"{settings.app_base_url}/login?error=expired", status_code=303)

    user = db.query(User).filter(User.email == auth_token.email).one_or_none()
    if user is None:
        user = User(email=auth_token.email)
        db.add(user)
        db.flush()

    user.last_login_at = now_utc()
    auth_token.used = True
    ensure_demo_session(db, user)
    db.commit()

    response = RedirectResponse(f"{settings.app_base_url}/?login=success", status_code=303)
    set_auth_cookie(response, user)
    return response


@app.get("/auth/me")
def auth_me(user: User = Depends(get_current_user)):
    return {"id": user.id, "email": user.email}


@app.post("/auth/logout")
def logout(response: Response):
    response.delete_cookie(
        settings.session_cookie_name,
        secure=settings.app_env != "local",
        httponly=True,
        samesite="lax",
    )
    return {"message": "ok"}


@app.post("/sessions")
def create_session(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    session = ContractSession(owner_user_id=user.id)
    db.add(session)
    db.flush()
    db.add(ContractParticipant(session_id=session.id, user_id=user.id, role=ParticipantRole.party_1))
    db.add(ContractParticipant(session_id=session.id, role=ParticipantRole.party_2))
    db.commit()
    db.refresh(session)
    return session


@app.get("/sessions")
def list_sessions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_demo_session(db, user)
    db.commit()
    return (
        db.query(ContractSession)
        .join(ContractParticipant, ContractParticipant.session_id == ContractSession.id)
        .filter(or_(ContractSession.owner_user_id == user.id, ContractParticipant.user_id == user.id))
        .distinct()
        .order_by(ContractSession.updated_at.desc())
        .all()
    )


@app.get("/sessions/{session_id}")
def get_session(session_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    session = get_accessible_session(db, session_id, user)
    latest_version = get_latest_version(db, session)
    return {
        "session": session,
        "participants": session.participants,
        "versions": session.versions,
        "latest_version": latest_version,
        "messages": session.messages,
    }


def get_accessible_session(db: Session, session_id: str, user: User) -> ContractSession:
    session = db.get(ContractSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Сессия не найдена")

    participant = (
        db.query(ContractParticipant)
        .filter(ContractParticipant.session_id == session.id, ContractParticipant.user_id == user.id)
        .one_or_none()
    )
    if session.owner_user_id != user.id and participant is None:
        raise HTTPException(status_code=403, detail="Нет доступа к договору")
    return session


def get_latest_version(db: Session, session: ContractSession) -> ContractVersion | None:
    return (
        db.query(ContractVersion)
        .filter(ContractVersion.session_id == session.id)
        .order_by(ContractVersion.version_number.desc())
        .first()
    )


def get_user_participant(db: Session, session: ContractSession, user: User) -> ContractParticipant:
    participant = (
        db.query(ContractParticipant)
        .filter(ContractParticipant.session_id == session.id, ContractParticipant.user_id == user.id)
        .one_or_none()
    )
    if participant is None:
        raise HTTPException(status_code=403, detail="Пользователь не является стороной договора")
    return participant


def get_final_version(db: Session, session: ContractSession) -> ContractVersion | None:
    return (
        db.query(ContractVersion)
        .filter(ContractVersion.session_id == session.id, ContractVersion.is_final.is_(True))
        .order_by(ContractVersion.version_number.desc())
        .first()
    )


def count_completed_today(db: Session, user: User) -> int:
    today = now_utc().date()
    day_start = datetime.combine(today, time.min, tzinfo=timezone.utc)
    day_end = datetime.combine(today, time.max, tzinfo=timezone.utc)
    return (
        db.query(ContractSession)
        .filter(
            ContractSession.owner_user_id == user.id,
            ContractSession.is_completed.is_(True),
            ContractSession.finalized_at >= day_start,
            ContractSession.finalized_at <= day_end,
        )
        .count()
    )


def format_history(messages: list[Message]) -> str:
    return "\n\n".join(
        f"{message.created_at.isoformat()} / {message.role.value}:\n{message.content}" for message in messages
    )


def ensure_demo_session(db: Session, user: User) -> None:
    existing = (
        db.query(ContractSession)
        .filter(ContractSession.owner_user_id == user.id, ContractSession.title == DEMO_SESSION_TITLE)
        .one_or_none()
    )
    if existing is not None:
        return

    session = ContractSession(
        owner_user_id=user.id,
        title=DEMO_SESSION_TITLE,
        status=SessionStatus.in_review,
    )
    db.add(session)
    db.flush()
    db.add(ContractParticipant(session_id=session.id, user_id=user.id, role=ParticipantRole.party_1))
    db.add(ContractParticipant(session_id=session.id, role=ParticipantRole.party_2))
    db.add(Message(session_id=session.id, role=MessageRole.user, content=DEMO_USER_PROMPT))
    db.add(Message(session_id=session.id, role=MessageRole.assistant, content=DEMO_CONTRACT_TEXT))
    db.add(
        ContractVersion(
            session_id=session.id,
            version_number=1,
            content=DEMO_CONTRACT_TEXT,
        )
    )


def save_contract_version(db: Session, session: ContractSession, content: str) -> ContractVersion:
    version_count = db.query(ContractVersion).filter(ContractVersion.session_id == session.id).count()
    version = ContractVersion(
        session_id=session.id,
        version_number=version_count + 1,
        content=content,
    )
    session.status = SessionStatus.in_review
    for participant in session.participants:
        participant.approval_status = ApprovalStatus.pending
        participant.approved_version_id = None
    db.add(version)
    return version


@app.post("/sessions/{session_id}/invite")
def create_invite(
    session_id: str,
    payload: InviteRequest | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = db.get(ContractSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    if session.owner_user_id != user.id:
        raise HTTPException(status_code=403, detail="Приглашение может создать только Сторона 1")
    if session.invite_token is None:
        session.invite_token = uuid.uuid4()
        db.commit()
        db.refresh(session)
    invite_link = f"{settings.app_base_url}/invite/{session.invite_token}"
    sent = False
    if payload and payload.email:
        send_contract_invite(payload.email, invite_link, session.title)
        sent = smtp_is_configured()
        party_label = payload.party_name.strip() or str(payload.email)
        db.add(
            Message(
                session_id=session.id,
                role=MessageRole.system,
                content=f"Ссылка на согласование подготовлена для {party_label}: {payload.email}",
            )
        )
        db.commit()
    return {"invite_link": invite_link, "sent": sent}


@app.post("/invites/{invite_token}/accept")
def accept_invite(invite_token: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    session = db.query(ContractSession).filter(ContractSession.invite_token == invite_token).one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Приглашение не найдено")
    if session.owner_user_id == user.id:
        raise HTTPException(status_code=400, detail="Сторона 1 уже привязана к договору")

    participant = (
        db.query(ContractParticipant)
        .filter(ContractParticipant.session_id == session.id, ContractParticipant.role == ParticipantRole.party_2)
        .one()
    )
    if participant.user_id is None:
        participant.user_id = user.id
        participant.joined_at = now_utc()
        db.commit()
    elif participant.user_id != user.id:
        raise HTTPException(status_code=403, detail="Приглашение уже принято другой стороной")

    return {"session_id": session.id}


@app.post("/sessions/{session_id}/messages")
async def send_message(
    session_id: str,
    payload: MessageRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = get_accessible_session(db, session_id, user)

    is_dispute = payload.content.strip().upper().startswith("СПОР")
    if session.status == SessionStatus.finalized and not is_dispute:
        answer = (
            "⚠️ В этом чате договор уже финализирован.\n"
            "Изменение условий после финализации невозможно.\n\n"
            "Если у вас возник спор по условиям договора, напишите \"СПОР\" и опишите ситуацию.\n"
            "Для создания нового договора нажмите кнопку \"+ Новый договор\"."
        )
        db.add(Message(session_id=session.id, role=MessageRole.user, content=payload.content))
        db.add(Message(session_id=session.id, role=MessageRole.assistant, content=answer))
        db.commit()
        return {"content": answer}

    warning = ""
    if contains_passport_like_data(payload.content):
        warning = (
            "⚠️ Обнаружены данные, похожие на серию и номер паспорта. "
            "Для MVP лучше использовать условные обозначения.\n\n"
        )

    db.add(Message(session_id=session.id, role=MessageRole.user, content=payload.content))
    db.commit()

    try:
        should_save_contract_version = session.status != SessionStatus.finalized
        if session.status == SessionStatus.finalized and is_dispute:
            final_version = get_final_version(db, session)
            if final_version is None:
                raise HTTPException(status_code=400, detail="Финальная версия договора не найдена")
            messages = (
                db.query(Message)
                .filter(Message.session_id == session.id)
                .order_by(Message.created_at.asc())
                .all()
            )
            prompt = build_dispute_prompt(final_version.content, format_history(messages), payload.content)
        else:
            prompt = [
                {"role": "system", "text": CONTRACT_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "text": (
                        "Сгенерируй полный проект договора по следующему запросу. "
                        "Ответ должен быть именно текстом договора, без предварительных пояснений.\n\n"
                        f"Запрос пользователя:\n{payload.content}"
                    ),
                },
            ]
        answer = await ask_yandex_gpt(
            prompt
        )
    except YandexGPTError:
        should_save_contract_version = False
        answer = (
            "YandexGPT пока не настроен. Добавьте YANDEX_GPT_API_KEY и "
            "YANDEX_GPT_FOLDER_ID в .env, чтобы генерировать проекты договоров."
        )

    answer = warning + answer
    db.add(Message(session_id=session.id, role=MessageRole.assistant, content=answer))
    if should_save_contract_version:
        save_contract_version(db, session, answer)
    db.commit()
    return {"content": answer, "contract_saved": should_save_contract_version}


@app.post("/sessions/{session_id}/versions")
def create_version(
    session_id: str,
    payload: VersionRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = get_accessible_session(db, session_id, user)
    if session.status == SessionStatus.finalized:
        raise HTTPException(status_code=400, detail="Финализированный договор нельзя изменить")

    version = save_contract_version(db, session, payload.content)
    db.commit()
    db.refresh(version)
    return version


@app.post("/sessions/{session_id}/approve")
def approve_version(session_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    session = get_accessible_session(db, session_id, user)
    latest_version = get_latest_version(db, session)
    if latest_version is None:
        raise HTTPException(status_code=400, detail="Нет версии договора для согласования")

    participant = get_user_participant(db, session, user)
    participant.approval_status = ApprovalStatus.approved
    participant.approved_version_id = latest_version.id

    participants = session.participants
    both_approved = all(
        item.user_id is not None
        and item.approval_status == ApprovalStatus.approved
        and item.approved_version_id == latest_version.id
        for item in participants
    )
    if both_approved:
        owner = db.get(User, session.owner_user_id)
        if owner is None:
            raise HTTPException(status_code=400, detail="Владелец договора не найден")
        if count_completed_today(db, owner) >= 10:
            raise HTTPException(
                status_code=429,
                detail="Достигнут лимит бета-версии: 10 завершенных договоров в день. Доступ будет восстановлен завтра",
            )
        session.status = SessionStatus.finalized
        session.finalized_at = now_utc()
        session.download_token = session.download_token or uuid.uuid4()
        session.is_completed = True
        latest_version.is_final = True

    db.commit()
    return {"finalized": both_approved, "status": session.status}


@app.post("/sessions/{session_id}/request-changes")
def request_changes(
    session_id: str,
    payload: ChangesRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = get_accessible_session(db, session_id, user)
    if session.status == SessionStatus.finalized:
        raise HTTPException(status_code=400, detail="Финализированный договор нельзя изменить")

    participant = get_user_participant(db, session, user)
    participant.approval_status = ApprovalStatus.changes_requested
    db.add(
        Message(
            session_id=session.id,
            role=MessageRole.user,
            content=f"Запрошены правки ({participant.role.value}): {payload.content}",
        )
    )
    for item in session.participants:
        item.approval_status = ApprovalStatus.pending
        item.approved_version_id = None
    db.commit()
    return {"message": "Правки зафиксированы. Следующим шагом AI сформирует новую версию договора."}


@app.get("/download/{download_token}.pdf")
def download_contract_pdf(download_token: str, db: Session = Depends(get_db)):
    session = db.query(ContractSession).filter(ContractSession.download_token == download_token).one_or_none()
    if session is None or session.status != SessionStatus.finalized:
        raise HTTPException(status_code=404, detail="Финализированный договор не найден")

    final_version = (
        db.query(ContractVersion)
        .filter(ContractVersion.session_id == session.id, ContractVersion.is_final.is_(True))
        .order_by(ContractVersion.version_number.desc())
        .first()
    )
    if final_version is None:
        raise HTTPException(status_code=404, detail="Финальная версия договора не найдена")

    messages = (
        db.query(Message)
        .filter(Message.session_id == session.id)
        .order_by(Message.created_at.asc())
        .all()
    )
    pdf_bytes = build_contract_pdf(session, final_version, session.participants, messages)
    filename = f"ai-arbitr-{session.id}.pdf"
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
