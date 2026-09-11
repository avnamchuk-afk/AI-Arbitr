from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

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
)
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


class SessionCreateRequest(BaseModel):
    email: EmailStr


class MessageRequest(BaseModel):
    content: str


class VersionRequest(BaseModel):
    content: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/auth/magic-link")
def request_magic_link(payload: LoginRequest, db: Session = Depends(get_db)):
    if not payload.personal_data_accepted:
        raise HTTPException(status_code=400, detail="Нужно согласие на обработку персональных данных")

    user = db.query(User).filter(User.email == payload.email).one_or_none()
    if user is None:
        user = User(email=payload.email)
        db.add(user)
        db.commit()

    return {"message": "MVP: пользователь создан. Отправку email подключим после настройки SMTP."}


@app.post("/sessions")
def create_session(payload: SessionCreateRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).one_or_none()
    if user is None:
        user = User(email=payload.email)
        db.add(user)
        db.flush()

    session = ContractSession(owner_user_id=user.id)
    db.add(session)
    db.flush()
    db.add(ContractParticipant(session_id=session.id, user_id=user.id, role=ParticipantRole.party_1))
    db.add(ContractParticipant(session_id=session.id, role=ParticipantRole.party_2))
    db.commit()
    db.refresh(session)
    return session


@app.get("/sessions")
def list_sessions(email: EmailStr, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email).one_or_none()
    if user is None:
        return []
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
