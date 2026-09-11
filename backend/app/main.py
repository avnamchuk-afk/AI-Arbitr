from datetime import datetime, timezone

from fastapi import Cookie, Depends, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.base import Base
from app.db.session import engine, get_db
from app.models.entities import (
    ApprovalStatus,
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
from app.services.email import send_magic_link, smtp_is_configured
from app.services.privacy import contains_passport_like_data
from app.services.yandex_gpt import YandexGPTError, ask_yandex_gpt

Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI-Arbitr API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
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
    db.commit()

    response = RedirectResponse(f"{settings.app_base_url}/?login=success", status_code=303)
    set_auth_cookie(response, user)
    return response


@app.get("/auth/me")
def auth_me(user: User = Depends(get_current_user)):
    return {"id": user.id, "email": user.email}


@app.post("/auth/logout")
def logout(response: Response):
    response.delete_cookie(settings.session_cookie_name)
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
    return (
        db.query(ContractSession)
        .filter(ContractSession.owner_user_id == user.id)
        .order_by(ContractSession.updated_at.desc())
        .all()
    )


@app.post("/sessions/{session_id}/messages")
async def send_message(session_id: str, payload: MessageRequest, db: Session = Depends(get_db)):
    session = db.get(ContractSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Сессия не найдена")

    if session.status == SessionStatus.finalized and not payload.content.strip().upper().startswith("СПОР"):
        return {
            "content": (
                "⚠️ В этом чате договор уже финализирован.\n"
                "Изменение условий после финализации невозможно.\n\n"
                "Если у вас возник спор по условиям договора, напишите \"СПОР\" и опишите ситуацию.\n"
                "Для создания нового договора нажмите кнопку \"+ Новый договор\"."
            )
        }

    warning = ""
    if contains_passport_like_data(payload.content):
        warning = (
            "⚠️ Обнаружены данные, похожие на серию и номер паспорта. "
            "Для MVP лучше использовать условные обозначения.\n\n"
        )

    db.add(Message(session_id=session.id, role=MessageRole.user, content=payload.content))
    db.commit()

    try:
        answer = await ask_yandex_gpt(
            [
                {
                    "role": "system",
                    "text": "Ты AI-Арбитр. Помогаешь составлять договоры по праву РФ и разрешать споры по ним.",
                },
                {"role": "user", "text": payload.content},
            ]
        )
    except YandexGPTError:
        answer = "Сервис временно недоступен. Попробуйте через минуту."

    answer = warning + answer
    db.add(Message(session_id=session.id, role=MessageRole.assistant, content=answer))
    db.commit()
    return {"content": answer}


@app.post("/sessions/{session_id}/versions")
def create_version(session_id: str, payload: VersionRequest, db: Session = Depends(get_db)):
    session = db.get(ContractSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Сессия не найдена")

    version_count = db.query(ContractVersion).filter(ContractVersion.session_id == session.id).count()
    version = ContractVersion(
        session_id=session.id,
        version_number=version_count + 1,
        content=payload.content,
    )
    session.status = SessionStatus.in_review
    for participant in session.participants:
        participant.approval_status = ApprovalStatus.pending
        participant.approved_version_id = None
    db.add(version)
    db.commit()
    db.refresh(version)
    return version
    AuthToken,
