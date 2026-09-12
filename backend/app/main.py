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


class RegisterRequest(BaseModel):
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


class ReviewApproveRequest(BaseModel):
    full_name: str
    passport: str
    email: EmailStr
    personal_data_accepted: bool


GUEST_EMAIL_SUFFIX = "@guest.ai-arbitr.local"
DEMO_SESSION_TITLE = "пример"
LEGACY_DEMO_SESSION_TITLE = "Пример: договор на лендинг"
DEMO_USER_PROMPT = "Составь договор найма"
DEMO_REASONING_NOTE = """Что делает Арби:
• Понятно, делаем договор найма жилого помещения.
• Проверяю применимые нормы ГК РФ о найме жилого помещения.
• Существенные условия:
- предмет договора: квартира или иное жилое помещение;
- стороны договора: наймодатель и наниматель;
- срок найма;
- размер платы за найм и порядок ее внесения;
- порядок пользования жилым помещением.
• Обычные условия для долгосрочного договора найма:
- порядок передачи квартиры по акту;
- передача ключей и фиксация их количества;
- оплата ЖКУ по счетчикам и по квитанциям;
- обязанность передавать Наймодателю всю корреспонденцию, которая приходит на адрес квартиры;
- право Наймодателя посещать квартиру один раз в месяц с предварительным уведомлением;
- обеспечительный платеж с рассрочкой на 2 месяца при договоре на длительный срок;
- порядок возврата обеспечительного платежа, включая срок возврата 5 дней;
- условия перерасчета при досрочном прекращении договора Нанимателем;
- автоматическая пролонгация без дополнительного соглашения;
- запрет субнайма, перепланировки и посуточной сдачи без согласия;
- порядок текущего ремонта, устранения аварий и возмещения ущерба;
- правила проживания, гости, животные, курение и тишина;
- порядок разрешения споров через AI-Арбитр как рекомендательный механизм.
• Генерирую первую версию договора."""
DEMO_CONTRACT_TEXT = """### Договор найма жилого помещения

**1. Стороны договора**
[ФИО наймодателя], именуемый далее "Наймодатель", и [ФИО нанимателя], именуемый далее
"Наниматель", заключили настоящий договор найма жилого помещения.

**2. Предмет договора**
Наймодатель передает Нанимателю во временное владение и пользование квартиру, расположенную
по адресу: [адрес квартиры], общей площадью [площадь] кв. м, кадастровый номер при наличии: [номер].

Квартира передается для проживания Нанимателя и согласованных с Наймодателем лиц. Субнайм,
посуточная сдача, размещение третьих лиц на постоянной основе, предпринимательская деятельность
и перепланировка допускаются только с письменного согласия Наймодателя.

**3. Срок найма и пролонгация**
Договор заключен на срок [срок, например 11 месяцев / 3 года]: с [дата начала] по [дата окончания].

Если ни одна из сторон не направит письменное уведомление о прекращении договора не позднее чем
за 30 календарных дней до окончания срока, договор автоматически продлевается на тот же срок
и на тех же условиях без подписания дополнительного соглашения.

**4. Плата за найм**
Плата за найм составляет [сумма] рублей в месяц и вносится Нанимателем не позднее [число]
числа каждого месяца переводом на счет Наймодателя либо иным согласованным способом.

**5. ЖКУ, счетчики и квитанции**
Наниматель оплачивает коммунальные услуги по индивидуальным приборам учета на основании
показаний счетчиков, а также платежи, прямо связанные с фактическим проживанием и указанные
в квитанциях: [перечень платежей].

Наймодатель оплачивает взносы на капитальный ремонт, налоговые платежи и иные расходы
собственника, если стороны отдельно не согласуют иной порядок.

Наниматель обязан ежемесячно передавать Наймодателю фотографии показаний счетчиков и копии
оплаченных квитанций не позднее [число] числа месяца, следующего за расчетным.

**6. Обеспечительный платеж и рассрочка**
Обеспечительный платеж составляет [сумма] рублей. С учетом длительного срока найма стороны
согласовали рассрочку обеспечительного платежа на 2 месяца: 50% вносится при подписании
договора, оставшиеся 50% — не позднее [дата].

Обеспечительный платеж обеспечивает оплату найма, коммунальных платежей, возмещение ущерба
квартире и имуществу, а также иные подтвержденные задолженности Нанимателя по договору.

**7. Возврат обеспечительного платежа**
Наймодатель возвращает обеспечительный платеж в течение 5 календарных дней после возврата
квартиры по акту, передачи всех ключей и проведения окончательных расчетов.

Наймодатель вправе удержать только подтвержденные суммы: задолженность по найму, неоплаченные
ЖКУ, стоимость утраченного имущества и стоимость устранения повреждений сверх нормального
износа. Удержание должно быть обосновано расчетом и документами или фотографиями.

**8. Передача квартиры и ключей**
Квартира передается по акту приема-передачи. В акте стороны фиксируют состояние квартиры,
перечень мебели и техники, показания счетчиков, количество комплектов ключей, электронных
пропусков и выявленные недостатки.

При прекращении договора Наниматель возвращает квартиру, все комплекты ключей, пропуска,
пульты и иное переданное имущество по акту возврата.

**9. Корреспонденция**
Наниматель обязан передавать Наймодателю всю корреспонденцию, уведомления, квитанции, судебные
и административные письма, поступающие по адресу квартиры на имя Наймодателя, собственника,
прежних жильцов или иных лиц.

**10. Посещение квартиры Наймодателем**
Наймодатель вправе посещать квартиру для проверки состояния не чаще одного раза в месяц,
предупредив Нанимателя не менее чем за 24 часа. Стороны согласуют дату и время визита
с учетом разумных интересов друг друга.

В аварийных случаях, при угрозе ущерба квартире, соседям или общему имуществу дома, доступ
может быть предоставлен незамедлительно.

**11. Права и обязанности Нанимателя**
Наниматель обязуется бережно пользоваться квартирой и имуществом, соблюдать правила проживания
в доме, режим тишины, правила пожарной безопасности, не менять замки без согласия Наймодателя,
не проводить перепланировку и не заводить животных без письменного согласования.

Наниматель обязан незамедлительно сообщать Наймодателю об авариях, протечках, неисправностях,
претензиях соседей, управляющей организации или государственных органов.

**12. Текущий ремонт и повреждения**
Мелкий текущий ремонт, вызванный обычным использованием квартиры, стороны распределяют так:
[например: расходные материалы и мелкий ремонт до определенной суммы оплачивает Наниматель,
крупный ремонт инженерных систем — Наймодатель].

Повреждения, возникшие по вине Нанимателя, членов его семьи, гостей или иных допущенных им лиц,
устраняются за счет Нанимателя. Естественный износ не считается ущербом.

**13. Досрочное прекращение и перерасчет**
Наниматель вправе досрочно прекратить договор, предупредив Наймодателя не менее чем за 30
календарных дней. Если Наниматель освобождает квартиру до окончания оплаченного периода,
плата за найм перерасчитывается пропорционально фактическому количеству дней пользования
квартирой после даты возврата квартиры по акту, если стороны не согласовали иной порядок.

Если Наниматель прекращает договор без соблюдения срока предупреждения, Наймодатель вправе
удержать из обеспечительного платежа сумму платы за период недостающего предупреждения,
но не более размера фактически причиненных и обоснованных потерь.

**14. Ответственность сторон**
За просрочку оплаты Наниматель уплачивает неустойку в размере [размер] за каждый день просрочки,
если стороны согласуют такую меру ответственности.

**15. Порядок разрешения споров**
Стороны согласовали, что при возникновении разногласий они вправе обратиться к AI-Арбитру
для получения экспертного заключения по существу спора. AI-Арбитр анализирует текст договора
и историю согласования, после чего формирует рекомендации.

AI-Арбитр не является третейским судом, арбитражным учреждением или органом государственной
власти. Заключение AI-Арбитра носит рекомендательный характер и не ограничивает право любой
из сторон обратиться в компетентный суд за защитой своих интересов.

**16. Реквизиты и подписи сторон**
Наймодатель: [ФИО, контактные данные, реквизиты]

Наниматель: [ФИО, контактные данные, реквизиты]

Наймодатель: ______________________

Наниматель: ______________________
"""

DEMO_EXPLANATION = """Обеспечительный платеж — это сумма, которая страхует Наймодателя от долгов и ущерба.
Его лучше не называть "штрафом" или "невозвратным депозитом": так условие выглядит справедливее
и понятнее для обеих сторон.

Важно указать:
• размер платежа;
• что именно он обеспечивает;
• срок возврата;
• какие суммы можно удержать;
• что естественный износ не считается ущербом."""

CONTRACT_UPDATE_PREFIX = "ДОПОЛНИТЬ ДОГОВОР:"


def build_reasoning_note(content: str) -> str:
    normalized = content.lower()
    if "найм" in normalized or "квартир" in normalized or "жил" in normalized:
        steps = [
            "Понятно, делаем договор найма жилого помещения.",
            "Проверяю применимые нормы ГК РФ о найме жилого помещения.",
            "Выделяю существенные условия: жилое помещение, стороны, срок найма, размер и порядок оплаты.",
            "Добавляю обычные условия: порядок передачи квартиры, коммунальные платежи, ремонт, доступ в помещение, ответственность.",
            "Учитываю спорные места: депозит, просрочка оплаты, повреждение имущества, досрочное расторжение.",
            "Генерирую первую версию договора.",
        ]
    else:
        steps = [
            "Понятно, готовлю проект договора по вашему запросу.",
            "Проверяю применимые нормы ГК РФ и обязательные условия договора.",
            "Выделяю существенные условия, без которых договор может работать плохо.",
            "Добавляю обычные условия: порядок оплаты, сроки, приемка, ответственность, изменение и расторжение.",
            "Учитываю типовые спорные места и формулирую условия понятным языком.",
            "Генерирую первую версию договора.",
        ]
    return "Что делает Арби:\n" + "\n".join(f"• {step}" for step in steps)


def build_question_reasoning_note(question: str) -> str:
    return (
        "Что делает Арби:\n"
        "• Вопрос понятен.\n"
        "• Проверяю его по текущей редакции договора.\n"
        "• Сверяю ответ с обычной практикой и нормами ГК РФ.\n"
        "• Отвечаю коротко и простым языком, без генерации новой версии договора."
    )


def build_update_reasoning_note(change: str) -> str:
    return (
        "Что делает Арби:\n"
        "• Нужно добавить новое условие в договор.\n"
        "• Проверяю, не противоречит ли оно ГК РФ и логике договора.\n"
        "• Ищу раздел договора, куда его правильно включить.\n"
        "• Формулирую норму и готовлю новую редакцию договора."
    )


def infer_session_title(content: str) -> str:
    normalized = content.lower()
    title_rules = [
        (("найм", "квартир", "жил"), "Найм жилья"),
        (("аренд",), "Аренда"),
        (("лендинг", "сайт", "веб", "landing"), "Лендинг"),
        (("юруслуг", "юридическ", "консультац", "претензи"), "Юруслуги"),
        (("оказан", "услуг"), "Услуги"),
        (("подряд", "ремонт", "строитель"), "Подряд"),
        (("купл", "продаж", "поставк"), "Купля-продажа"),
        (("заем", "займ", "долг"), "Заем"),
        (("ндаш", "nda", "конфиденциаль"), "NDA"),
    ]
    for keywords, title in title_rules:
        if any(keyword in normalized for keyword in keywords):
            return title

    compact = " ".join(content.replace("\n", " ").split())
    if not compact:
        return "Новый договор"
    return compact[:36].rstrip(" .,;:") or "Новый договор"


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


def get_optional_current_user(
    db: Session = Depends(get_db),
    session_cookie: str | None = Cookie(default=None, alias=settings.session_cookie_name),
) -> User | None:
    user_id = read_session_cookie(session_cookie)
    if user_id is None:
        return None
    return db.get(User, user_id)


def is_guest_user(user: User) -> bool:
    return user.email.endswith(GUEST_EMAIL_SUFFIX)


@app.post("/auth/guest")
def create_guest(response: Response, db: Session = Depends(get_db)):
    user = User(email=f"guest-{uuid.uuid4().hex}{GUEST_EMAIL_SUFFIX}")
    db.add(user)
    db.flush()
    ensure_demo_session(db, user)
    db.commit()
    set_auth_cookie(response, user)
    return {"id": user.id, "email": "", "is_guest": True}


def issue_magic_link(email: str, db: Session) -> dict[str, str]:
    raw_token = generate_raw_token()
    db.add(
        AuthToken(
            email=email,
            token_hash=hash_token(raw_token),
            expires_at=token_expires_at(),
        )
    )
    db.commit()

    verify_link = f"{settings.api_base_url}/auth/verify?token={raw_token}"
    send_magic_link(email, verify_link)

    response = {"message": "Ссылка для входа отправлена на вашу почту"}
    if settings.app_env == "local" and not smtp_is_configured():
        response["dev_link"] = verify_link
    return response


@app.post("/auth/register")
def register(
    payload: RegisterRequest,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    if not payload.personal_data_accepted:
        raise HTTPException(status_code=400, detail="Нужно согласие на обработку персональных данных")

    existing_user = db.query(User).filter(User.email == payload.email).one_or_none()
    if existing_user is not None and (current_user is None or existing_user.id != current_user.id):
        raise HTTPException(status_code=409, detail="Аккаунт с таким email уже есть. Войдите по email.")

    if current_user is not None and is_guest_user(current_user):
        current_user.email = payload.email
        db.flush()
    elif existing_user is None:
        db.add(User(email=payload.email))
        db.flush()
    return issue_magic_link(payload.email, db)


@app.post("/auth/login")
def request_login_link(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="Аккаунт не найден. Зарегистрируйтесь по email.")

    return issue_magic_link(payload.email, db)


@app.post("/auth/magic-link")
def request_magic_link(payload: RegisterRequest, db: Session = Depends(get_db)):
    if not payload.personal_data_accepted:
        raise HTTPException(status_code=400, detail="Нужно согласие на обработку персональных данных")

    user = db.query(User).filter(User.email == payload.email).one_or_none()
    if user is None:
        db.add(User(email=payload.email))
        db.flush()

    return issue_magic_link(payload.email, db)


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
    return {"id": user.id, "email": "" if is_guest_user(user) else user.email, "is_guest": is_guest_user(user)}


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


@app.delete("/sessions/{session_id}")
def delete_session(session_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    session = db.get(ContractSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    if session.owner_user_id != user.id:
        raise HTTPException(status_code=403, detail="Удалить договор может только его создатель")

    db.query(Message).filter(Message.session_id == session.id).delete(synchronize_session=False)
    db.query(ContractVersion).filter(ContractVersion.session_id == session.id).delete(synchronize_session=False)
    db.query(ContractParticipant).filter(ContractParticipant.session_id == session.id).delete(synchronize_session=False)
    db.delete(session)
    db.commit()
    return {"message": "deleted"}


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
        .filter(
            ContractSession.owner_user_id == user.id,
            ContractSession.title.in_([DEMO_SESSION_TITLE, LEGACY_DEMO_SESSION_TITLE]),
        )
        .one_or_none()
    )
    if existing is not None:
        existing.title = DEMO_SESSION_TITLE
        db.query(Message).filter(Message.session_id == existing.id).delete(synchronize_session=False)
        db.query(ContractVersion).filter(ContractVersion.session_id == existing.id).delete(synchronize_session=False)
        session = existing
    else:
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
    db.add(Message(session_id=session.id, role=MessageRole.system, content=DEMO_REASONING_NOTE))
    db.add(Message(session_id=session.id, role=MessageRole.assistant, content=DEMO_CONTRACT_TEXT))
    db.add(Message(session_id=session.id, role=MessageRole.user, content="Что такое обеспечительный платеж и почему он возвращается не всегда?"))
    db.add(Message(session_id=session.id, role=MessageRole.assistant, content=DEMO_EXPLANATION))
    db.add(
        Message(
            session_id=session.id,
            role=MessageRole.assistant,
            content=(
                "Если по примеру все понятно, следующий шаг в реальном договоре — указать имя второй стороны "
                "и email. AI-Арбитр подготовит ссылку для согласования, по которой вторая сторона сможет "
                "принять версию или предложить правки."
            ),
        )
    )
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
    if is_guest_user(user):
        raise HTTPException(status_code=403, detail="Зарегистрируйтесь по email, чтобы отправить ссылку согласования")
    if session.invite_token is None:
        session.invite_token = uuid.uuid4()
        db.commit()
        db.refresh(session)
    invite_link = f"{settings.app_base_url}/review/{session.invite_token}"
    pdf_link = f"{settings.api_base_url}/review/{session.invite_token}.pdf"
    sent = False
    if payload and payload.email:
        send_contract_invite(payload.email, invite_link, session.title, pdf_link)
        sent = smtp_is_configured()
        party_label = payload.party_name.strip() or str(payload.email)
        db.add(
            Message(
                session_id=session.id,
                role=MessageRole.system,
                content=f"Ссылка на просмотр и согласие отправлена для {party_label}: {payload.email}",
            )
        )
        db.commit()
    return {"invite_link": invite_link, "sent": sent}


def get_session_by_review_token(db: Session, invite_token: str) -> ContractSession:
    session = db.query(ContractSession).filter(ContractSession.invite_token == invite_token).one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Ссылка согласования не найдена")
    return session


@app.get("/review/{invite_token}.pdf")
def download_review_pdf(invite_token: str, db: Session = Depends(get_db)):
    session = get_session_by_review_token(db, invite_token)
    latest_version = get_latest_version(db, session)
    if latest_version is None:
        raise HTTPException(status_code=404, detail="Версия договора не найдена")
    messages = (
        db.query(Message)
        .filter(Message.session_id == session.id)
        .order_by(Message.created_at.asc())
        .all()
    )
    pdf_bytes = build_contract_pdf(session, latest_version, session.participants, messages)
    filename = f"ai-arbitr-review-{session.id}.pdf"
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@app.get("/review/{invite_token}")
def get_review_contract(invite_token: str, db: Session = Depends(get_db)):
    session = get_session_by_review_token(db, invite_token)
    latest_version = get_latest_version(db, session)
    if latest_version is None:
        raise HTTPException(status_code=404, detail="Версия договора не найдена")
    party_2 = (
        db.query(ContractParticipant)
        .filter(ContractParticipant.session_id == session.id, ContractParticipant.role == ParticipantRole.party_2)
        .one()
    )
    return {
        "session_id": session.id,
        "title": session.title,
        "status": session.status,
        "contract": latest_version.content,
        "approved": party_2.approval_status == ApprovalStatus.approved,
        "finalized": session.status == SessionStatus.finalized,
        "download_token": session.download_token,
        "pdf_link": f"{settings.api_base_url}/review/{invite_token}.pdf",
    }


@app.post("/review/{invite_token}/approve")
def approve_review_contract(invite_token: str, payload: ReviewApproveRequest, db: Session = Depends(get_db)):
    if not payload.personal_data_accepted:
        raise HTTPException(status_code=400, detail="Нужно согласие на обработку персональных данных")

    session = get_session_by_review_token(db, invite_token)
    latest_version = get_latest_version(db, session)
    if latest_version is None:
        raise HTTPException(status_code=400, detail="Нет версии договора для согласования")
    if session.status == SessionStatus.finalized:
        return {"finalized": True, "download_token": session.download_token}

    participant = (
        db.query(ContractParticipant)
        .filter(ContractParticipant.session_id == session.id, ContractParticipant.role == ParticipantRole.party_2)
        .one()
    )
    user = db.query(User).filter(User.email == payload.email).one_or_none()
    if user is None:
        user = User(email=payload.email)
        db.add(user)
        db.flush()

    owner = db.get(User, session.owner_user_id)
    if owner is None:
        raise HTTPException(status_code=400, detail="Владелец договора не найден")
    if count_completed_today(db, owner) >= 10:
        raise HTTPException(
            status_code=429,
            detail="Достигнут лимит бета-версии: 10 завершенных договоров в день. Доступ будет восстановлен завтра",
        )

    participant.user_id = user.id
    participant.joined_at = participant.joined_at or now_utc()
    participant.approval_status = ApprovalStatus.approved
    participant.approved_version_id = latest_version.id
    session.status = SessionStatus.finalized
    session.finalized_at = now_utc()
    session.download_token = session.download_token or uuid.uuid4()
    session.is_completed = True
    latest_version.is_final = True
    db.add(
        Message(
            session_id=session.id,
            role=MessageRole.system,
            content=(
                "Вторая сторона согласовала договор.\n"
                f"ФИО: {payload.full_name.strip()}\n"
                f"Паспортные данные: {payload.passport.strip()}\n"
                f"Email: {payload.email}"
            ),
        )
    )
    db.add(
        Message(
            session_id=session.id,
            role=MessageRole.assistant,
            content=(
                "Вторая сторона согласовала договор. Финальная PDF-версия сформирована "
                f"и доступна по ссылке: {settings.api_base_url}/download/{session.download_token}.pdf"
            ),
        )
    )
    db.commit()
    return {"finalized": True, "download_token": session.download_token}


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

    latest_version_before_answer = get_latest_version(db, session)
    is_contract_update = payload.content.startswith(CONTRACT_UPDATE_PREFIX)
    if session.title == "Новый договор":
        title_source = payload.content.removeprefix(CONTRACT_UPDATE_PREFIX).strip()
        session.title = infer_session_title(title_source)
    db.add(Message(session_id=session.id, role=MessageRole.user, content=payload.content))
    if session.status == SessionStatus.finalized:
        reasoning_note = ""
    elif latest_version_before_answer is None:
        reasoning_note = build_reasoning_note(payload.content)
    elif is_contract_update:
        reasoning_note = build_update_reasoning_note(payload.content.removeprefix(CONTRACT_UPDATE_PREFIX).strip())
    else:
        reasoning_note = build_question_reasoning_note(payload.content)
    if reasoning_note:
        db.add(Message(session_id=session.id, role=MessageRole.system, content=reasoning_note))
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
        elif session.status != SessionStatus.finalized and latest_version_before_answer is not None:
            latest_version = latest_version_before_answer
            if is_contract_update:
                requested_change = payload.content.removeprefix(CONTRACT_UPDATE_PREFIX).strip()
                prompt = [
                    {"role": "system", "text": CONTRACT_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "text": (
                            "Перед тобой текущая версия договора. Внеси в нее новое условие или уточнение "
                            "по просьбе пользователя. Верни полный обновленный текст договора без пояснений.\n\n"
                            f"Текущая версия договора:\n{latest_version.content}\n\n"
                            f"Просьба пользователя:\n{requested_change}"
                        ),
                    },
                ]
            else:
                should_save_contract_version = False
                prompt = [
                    {
                        "role": "system",
                        "text": (
                            "Ты AI-Арбитр. Пользователь задает вопрос по уже подготовленному договору. "
                            "Ответь простым языком, конкретно и практически. Не генерируй договор заново. "
                            "Сначала дай прямой ответ на вопрос, затем кратко объясни почему. "
                            "Если вопрос про изменение цены, срок, расторжение, депозит или ответственность, "
                            "обязательно проверь, что написано в договоре, и отдельно укажи, зависит ли ответ "
                            "от условия договора или от соглашения сторон. Если по закону нужна оговорка "
                            "или согласие другой стороны, скажи это прямо."
                        ),
                    },
                    {
                        "role": "user",
                        "text": (
                            f"Текущая версия договора:\n{latest_version.content}\n\n"
                            f"Вопрос пользователя:\n{payload.content}"
                        ),
                    },
                ]
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

    contract_text = answer
    answer = warning + answer
    db.add(Message(session_id=session.id, role=MessageRole.assistant, content=answer))
    if should_save_contract_version:
        save_contract_version(db, session, contract_text)
    db.commit()
    return {"content": answer, "contract_saved": should_save_contract_version, "reasoning": reasoning_note}


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
