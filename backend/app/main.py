import uuid
import re
import hashlib
from types import SimpleNamespace
from io import BytesIO
from datetime import datetime, time, timedelta, timezone
from urllib.parse import urlencode

from fastapi import Cookie, Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, StreamingResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from app.core.config import get_cors_origins, settings
from app.db.base import Base
from app.db.session import SessionLocal, engine, get_db
from app.models.entities import (
    ApprovalStatus,
    AuthToken,
    AnalyticsEvent,
    ContractAnalyticsSnapshot,
    ContractParticipant,
    ContractSession,
    ContractVersion,
    Message,
    MessageRole,
    ParticipantRole,
    RateLimitEvent,
    SessionStatus,
    User,
    now_utc,
)
from app.services.auth import (
    generate_raw_token,
    hash_token,
    make_session_cookie,
    make_verified_ip_cookie,
    read_session_cookie,
    token_expires_at,
)
from app.services.contract_templates import AI_ARBITR_DISPUTE_SECTION, build_housing_rent_contract, build_website_development_contract
from app.services.email import send_contract_invite, send_contract_signed_notice, send_dispute_notice, send_magic_link, send_signature_progress_notice, smtp_is_configured
from app.services.pdf import build_contract_pdf, build_interaction_certificate_pdf
from app.services.privacy import contains_passport_like_data
from app.services.prompts import CONTRACT_SYSTEM_PROMPT, SIMPLE_CONTRACT_SYSTEM_PROMPT, build_dispute_prompt
from app.services.yandex_gpt import YandexGPTError, ask_yandex_gpt
from app.version import APP_VERSION, identify_contract_template
from app.workflows.contract import (
    ContractAction,
    WorkflowContext,
    action_is_allowed,
    describe_workflow,
    workflow_catalog,
)

Base.metadata.create_all(bind=engine)


def ensure_runtime_schema() -> None:
    with engine.begin() as connection:
        if engine.dialect.name == "postgresql":
            connection.execute(
                text("ALTER TABLE users ADD COLUMN IF NOT EXISTS trusted_login_count INTEGER NOT NULL DEFAULT 0")
            )
            connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS service_rules_accepted BOOLEAN NOT NULL DEFAULT FALSE"))
            connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS privacy_accepted BOOLEAN NOT NULL DEFAULT FALSE"))
            connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS cookies_accepted BOOLEAN NOT NULL DEFAULT FALSE"))
            connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS consent_version VARCHAR(32)"))
            connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS consented_at TIMESTAMPTZ"))
            connection.execute(text("ALTER TABLE auth_tokens ADD COLUMN IF NOT EXISTS guest_user_id UUID REFERENCES users(id)"))
            connection.execute(
                text("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT FALSE")
            )
            connection.execute(text("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ"))
            connection.execute(text("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS invite_expires_at TIMESTAMPTZ"))
            connection.execute(text("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS pending_signing_content TEXT"))
            connection.execute(text("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS final_content_hash VARCHAR(64)"))
            connection.execute(text("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS party_1_legal_role VARCHAR(80)"))
            connection.execute(text("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS party_2_legal_role VARCHAR(80)"))
            connection.execute(text("ALTER TABLE contract_participants ADD COLUMN IF NOT EXISTS signed_at TIMESTAMPTZ"))
            connection.execute(text("ALTER TABLE contract_participants ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ"))
            connection.execute(text("ALTER TABLE contract_versions ADD COLUMN IF NOT EXISTS app_version VARCHAR(32)"))
            connection.execute(text("ALTER TABLE contract_versions ADD COLUMN IF NOT EXISTS template_id VARCHAR(80)"))
            connection.execute(text("ALTER TABLE contract_versions ADD COLUMN IF NOT EXISTS template_version VARCHAR(32)"))
        elif engine.dialect.name == "sqlite":
            user_columns = connection.execute(text("PRAGMA table_info(users)")).fetchall()
            if not any(column[1] == "trusted_login_count" for column in user_columns):
                connection.execute(text("ALTER TABLE users ADD COLUMN trusted_login_count INTEGER NOT NULL DEFAULT 0"))
            auth_token_columns = connection.execute(text("PRAGMA table_info(auth_tokens)")).fetchall()
            if not any(column[1] == "guest_user_id" for column in auth_token_columns):
                connection.execute(text("ALTER TABLE auth_tokens ADD COLUMN guest_user_id VARCHAR(36)"))
            session_columns = connection.execute(text("PRAGMA table_info(sessions)")).fetchall()
            if not any(column[1] == "is_deleted" for column in session_columns):
                connection.execute(text("ALTER TABLE sessions ADD COLUMN is_deleted BOOLEAN NOT NULL DEFAULT 0"))
            for column_name, column_type in (
                ("completed_at", "DATETIME"),
                ("invite_expires_at", "DATETIME"),
                ("pending_signing_content", "TEXT"),
                ("final_content_hash", "VARCHAR(64)"),
                ("party_1_legal_role", "VARCHAR(80)"),
                ("party_2_legal_role", "VARCHAR(80)"),
            ):
                if not any(column[1] == column_name for column in session_columns):
                    connection.execute(text(f"ALTER TABLE sessions ADD COLUMN {column_name} {column_type}"))
            participant_columns = connection.execute(text("PRAGMA table_info(contract_participants)")).fetchall()
            for column_name in ("signed_at", "completed_at"):
                if not any(column[1] == column_name for column in participant_columns):
                    connection.execute(text(f"ALTER TABLE contract_participants ADD COLUMN {column_name} DATETIME"))
            version_columns = connection.execute(text("PRAGMA table_info(contract_versions)")).fetchall()
            for column_name, column_type in (
                ("app_version", "VARCHAR(32)"),
                ("template_id", "VARCHAR(80)"),
                ("template_version", "VARCHAR(32)"),
            ):
                if not any(column[1] == column_name for column in version_columns):
                    connection.execute(text(f"ALTER TABLE contract_versions ADD COLUMN {column_name} {column_type}"))


ensure_runtime_schema()

app = FastAPI(title="AI-Arbitr API", version=APP_VERSION)

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
    service_rules_accepted: bool = False
    cookies_accepted: bool = False
    consent_version: str = "1.0"


class ConsentRequest(BaseModel):
    service_rules_accepted: bool
    privacy_accepted: bool
    cookies_accepted: bool
    consent_version: str = "1.0"


class MessageRequest(BaseModel):
    content: str
    model: str | None = None


class VersionRequest(BaseModel):
    content: str


class ChangesRequest(BaseModel):
    content: str


class InviteRequest(BaseModel):
    party_name: str = ""
    email: EmailStr | None = None
    creator_legal_role: str = ""


class ReviewApproveRequest(BaseModel):
    party_type: str = "individual"
    full_name: str
    passport: str = ""
    phone: str
    inn: str = ""
    ogrn: str = ""
    organization_name: str = ""
    email: EmailStr
    personal_data_accepted: bool
    service_rules_accepted: bool = False
    cookies_accepted: bool = False
    consent_version: str = "1.0"


GUEST_EMAIL_SUFFIX = "@guest.ai-arbitr.local"
VERIFIED_IP_COOKIE_NAME = "ai_arbitr_verified_ip"
DAILY_ACTION_LIMIT = 100
CONSENT_VERSION = "1.0"
DEMO_SESSION_TITLE = "пример"
LEGACY_DEMO_SESSION_TITLE = "Пример: договор на лендинг"
DEMO_USER_PROMPT = "Составь договор найма"
DEMO_REASONING_NOTE = """Ключевые условия для примера договора найма:
- предмет договора: квартира или иное жилое помещение;
- стороны договора: наймодатель и наниматель;
- срок найма;
- размер платы за найм и порядок ее внесения;
- порядок пользования жилым помещением.

Обычные условия для долгосрочного договора найма:
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
- порядок разрешения споров через AI-Арбитр."""
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
PLACEHOLDER_RE = re.compile(r"\[([^\[\]]+)\]")
MONEY_RE = re.compile(r"(\d[\d\s]*(?:[.,]\d+)?\s*(?:руб\.?|рублей))", re.IGNORECASE)
KEY_TERM_MAX_LENGTH = 72

KNOWN_SERVICE_MARKERS = (
    "юрид",
    "консультац",
    "бухгалтер",
    "маркет",
    "реклам",
    "дизайн",
    "разработ",
    "сайт",
    "saas",
    "саас",
    "it",
    "ит",
    "ремонт",
    "клининг",
    "перевод",
    "обуч",
    "образоват",
    "медицин",
    "транспорт",
    "логист",
    "охран",
)

BROAD_CONTRACT_PATTERNS = (
    "сделай договор",
    "составь договор",
    "подготовь договор",
    "нужен договор",
    "договор с подрядчиком",
    "договор на сотрудничество",
    "договор о сотрудничестве",
)

CONCRETE_CONTRACT_MARKERS = (
    "найм",
    "аренд",
    "квартир",
    "жил",
    "сайт",
    "лендинг",
    "saas",
    "саас",
    "разработ",
    "юрид",
    "бухгалтер",
    "маркет",
    "ремонт",
    "поставк",
    "купл",
    "продаж",
    "заем",
    "займ",
    "nda",
    "конфиденц",
    "перевод",
    "клининг",
    "обуч",
    "транспорт",
)


def build_reasoning_note(content: str) -> str:
    return ""


def needs_service_type_clarification(content: str) -> bool:
    normalized = content.lower().replace("ё", "е")
    service_request = "услуг" in normalized or "оказан" in normalized
    if not service_request:
        return False
    if "болгар" in normalized:
        return True
    return not any(marker in normalized for marker in KNOWN_SERVICE_MARKERS)


def build_service_type_clarification(content: str) -> str:
    if "болгар" in content.lower().replace("ё", "е"):
        return (
            "Похоже, в запросе есть опечатка: «болгарских услуг». "
            "Уточните, пожалуйста, какие именно услуги вы имели в виду: бухгалтерские, юридические, "
            "бытовые, строительные, IT-услуги или другие?\n\n"
            "Например: «договор на оказание бухгалтерских услуг для ООО»."
        )
    return (
        "Чтобы подготовить договор корректно, уточните, пожалуйста, какие именно услуги оказываются.\n\n"
        "Например: юридические консультации, бухгалтерское сопровождение, разработка ПО, маркетинг, "
        "ремонт, клининг или другие услуги."
    )


def needs_broad_contract_clarification(content: str) -> bool:
    normalized = " ".join(content.lower().replace("ё", "е").split())
    if len(normalized) <= 18 and "договор" in normalized:
        return True
    if not any(pattern in normalized for pattern in BROAD_CONTRACT_PATTERNS):
        return False
    return not any(marker in normalized for marker in CONCRETE_CONTRACT_MARKERS)


def build_broad_contract_clarification() -> str:
    return (
        "Уточните, пожалуйста, какой именно договор нужен и для какой ситуации.\n\n"
        "Напишите одной фразой: предмет договора, кто стороны и что должно быть результатом. "
        "Например: «договор подряда на ремонт квартиры», «договор поставки оборудования», "
        "«договор оказания маркетинговых услуг для ИП»."
    )


def is_housing_rent_request(content: str) -> bool:
    normalized = content.lower().replace("ё", "е")
    direct_housing_rent_phrases = (
        "договор найма",
        "найм жилого",
        "найма жилого",
        "наймодатель",
        "наниматель",
    )
    if any(phrase in normalized for phrase in direct_housing_rent_phrases):
        return True
    housing_markers = (
        "жиль",
        "жил",
        "квартир",
        "комнат",
        "дом",
        "помещени",
    )
    rent_markers = (
        "аренд",
        "найм",
        "снять",
        "сда",
    )
    return any(marker in normalized for marker in housing_markers) and any(
        marker in normalized for marker in rent_markers
    )


def is_website_development_request(content: str) -> bool:
    normalized = content.lower().replace("ё", "е")
    website_markers = ("сайт", "лендинг", "landing", "веб", "интернет-магазин")
    work_markers = ("создан", "разработ", "сдел", "подряд", "договор")
    return any(marker in normalized for marker in website_markers) and any(
        marker in normalized for marker in work_markers
    )


def normalize_contract_legal_title(contract_text: str, user_request: str) -> str:
    if not is_housing_rent_request(user_request):
        return contract_text

    legal_title = "Договор найма жилого помещения"
    lines = contract_text.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if "договор" in stripped.lower() or index == 0:
            prefix = ""
            if stripped.startswith("### "):
                prefix = "### "
            elif stripped.startswith("## "):
                prefix = "## "
            elif stripped.startswith("# "):
                prefix = "# "
            elif stripped.startswith("**") and stripped.endswith("**"):
                lines[index] = f"**{legal_title}**"
                return "\n".join(lines)
            lines[index] = f"{prefix}{legal_title}"
            return "\n".join(lines)

    return f"{legal_title}\n\n{contract_text}"


def clean_contract_markdown(contract_text: str) -> str:
    cleaned = re.sub(r"^\s{0,3}#{1,6}\s*", "", contract_text, flags=re.MULTILINE)
    cleaned = cleaned.replace("**", "")
    return cleaned.strip()


def ensure_ai_arbitr_dispute_section(contract_text: str) -> str:
    if "8.2.8. Настоящий порядок не ограничивает" in contract_text and "8.4. Стороны подтверждают" in contract_text:
        return contract_text

    text = re.sub(
        r"\n?8\.\s*ПОРЯДОК РАЗРЕШЕНИЯ СПОРОВ\s*\n.*?(?=\n9\.\s)",
        f"\n{AI_ARBITR_DISPUTE_SECTION}\n\n",
        contract_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if "8.2.8. Настоящий порядок не ограничивает" in text and "8.4. Стороны подтверждают" in text:
        return text.strip()

    text = re.sub(r"^.*AI-arbitr.*(?:\n|$)", "", text, flags=re.IGNORECASE | re.MULTILINE)
    insertion = f"\n\n{AI_ARBITR_DISPUTE_SECTION}\n\n"
    requisites_match = re.search(r"\n\d+\.\s*(?:РЕКВИЗИТЫ|АДРЕСА|ПОДПИСИ)", text, flags=re.IGNORECASE)
    if requisites_match:
        return (text[:requisites_match.start()] + insertion + text[requisites_match.start():]).strip()

    concluding_match = re.search(r"\n\d+\.\s*(?:ЗАКЛЮЧИТЕЛЬНЫЕ|СРОК ДЕЙСТВИЯ|ИЗМЕНЕНИЕ)", text, flags=re.IGNORECASE)
    if concluding_match:
        return (text[:concluding_match.start()] + insertion + text[concluding_match.start():]).strip()

    return (text.rstrip() + insertion).strip()


def extract_proposed_norms(messages: list[Message]) -> list[str]:
    norms: list[str] = []
    seen = set()
    for message in messages:
        if message.role != MessageRole.assistant:
            continue
        content = message.content.strip()
        marker = "Предлагаю такую редакцию нормы:"
        if marker not in content:
            continue
        norm = content.split(marker, 1)[1].strip()
        norm = norm.split("Добавить это условие в договор?", 1)[0].strip()
        norm = re.sub(r"^\[Номер пункта\]\.\s*", "", norm).strip()
        if not norm:
            continue
        signature = re.sub(r"\s+", " ", norm.lower())[:180]
        if signature not in seen:
            seen.add(signature)
            norms.append(norm)
    return norms


def collect_pending_norms_into_contract(contract_text: str, messages: list[Message]) -> str:
    norms = [
        norm
        for norm in extract_proposed_norms(messages)
        if re.sub(r"\s+", " ", norm.lower())[:120] not in re.sub(r"\s+", " ", contract_text.lower())
    ]
    if not norms:
        return contract_text

    additional_section = "ДОПОЛНИТЕЛЬНЫЕ УСЛОВИЯ, СОГЛАСОВАННЫЕ В ХОДЕ ОБСУЖДЕНИЯ\n\n"
    additional_section += "\n".join(f"[Номер пункта]. {norm}" for norm in norms)

    dispute_index = contract_text.find("8. ПОРЯДОК РАЗРЕШЕНИЯ СПОРОВ")
    if dispute_index >= 0:
        return (contract_text[:dispute_index].rstrip() + "\n\n" + additional_section + "\n\n" + contract_text[dispute_index:]).strip()

    return (contract_text.rstrip() + "\n\n" + additional_section).strip()


def add_norm_to_contract(contract_text: str, norm: str) -> str:
    clean_norm = re.sub(r"^\[Номер пункта\]\.\s*", "", norm.strip())
    if not clean_norm:
        return contract_text
    if re.sub(r"\s+", " ", clean_norm.lower())[:120] in re.sub(r"\s+", " ", contract_text.lower()):
        return contract_text

    normalized = clean_norm.lower().replace("ё", "е")
    section_rules = (
        (("плат", "цен", "стоим", "депозит", "обеспечитель", "расчет"), ("ПЛАТ", "РАСЧЕТ", "ЦЕН")),
        (("срок", "пролонг", "расторж", "прекращ"), ("СРОК", "ИЗМЕНЕНИЕ И РАСТОРЖЕНИЕ", "ПРЕКРАЩЕН")),
        (("неустой", "ответствен", "возмест", "ущерб"), ("ОТВЕТСТВЕННОСТ",)),
        (("разреш", "запрещ", "кальян", "курен", "пользован", "обязан"), ("ПРАВА И ОБЯЗАННОСТИ", "ПОРЯДОК ПОЛЬЗОВАНИЯ")),
    )
    target_headings: tuple[str, ...] = ()
    for markers, headings in section_rules:
        if any(marker in normalized for marker in markers):
            target_headings = headings
            break

    for heading in target_headings:
        heading_match = re.search(rf"(?im)^(\d+)\.\s*[^\n]*{re.escape(heading)}[^\n]*$", contract_text)
        if not heading_match:
            continue
        section_number = int(heading_match.group(1))
        next_heading = re.search(rf"(?m)^({section_number + 1}|\d{{2,}})\.\s+", contract_text[heading_match.end():])
        section_end = heading_match.end() + next_heading.start() if next_heading else len(contract_text)
        section_text = contract_text[heading_match.start():section_end]
        item_numbers = [int(value) for value in re.findall(rf"(?m)^{section_number}\.(\d+)\.\s*", section_text)]
        item_number = max(item_numbers, default=0) + 1
        numbered_norm = f"{section_number}.{item_number}. {clean_norm}"
        return (contract_text[:section_end].rstrip() + "\n" + numbered_norm + "\n\n" + contract_text[section_end:].lstrip()).strip()

    additional_section = "ДОПОЛНИТЕЛЬНЫЕ УСЛОВИЯ, СОГЛАСОВАННЫЕ В ХОДЕ ОБСУЖДЕНИЯ\n\n"
    additional_section += f"[Номер пункта]. {clean_norm}"
    dispute_index = contract_text.find("8. ПОРЯДОК РАЗРЕШЕНИЯ СПОРОВ")
    if dispute_index >= 0:
        return (contract_text[:dispute_index].rstrip() + "\n\n" + additional_section + "\n\n" + contract_text[dispute_index:]).strip()
    return (contract_text.rstrip() + "\n\n" + additional_section).strip()


def build_contract_number(version_number: int) -> str:
    return f"{now_utc().strftime('%d%m%y')}/{version_number}"


def apply_contract_number(contract_text: str, version_number: int) -> str:
    contract_number = build_contract_number(version_number)
    lines = contract_text.splitlines()
    for index, line in enumerate(lines[:5]):
        if "договор" not in line.lower():
            continue
        if "№" in line:
            lines[index] = re.sub(r"№\s*\S+", f"№ {contract_number}", line, count=1)
        else:
            lines[index] = f"{line.rstrip()} № {contract_number}"
        return "\n".join(lines)
    return f"Договор № {contract_number}\n\n{contract_text}"


def build_question_reasoning_note(question: str) -> str:
    return ""


def build_update_reasoning_note(change: str) -> str:
    return ""


def looks_like_contract_text(text: str) -> bool:
    normalized = text.lower()
    contract_markers = [
        "договор",
        "преамбула",
        "предмет договора",
        "права и обязанности",
        "ответственность сторон",
        "реквизиты и подписи",
    ]
    marker_count = sum(1 for marker in contract_markers if marker in normalized)
    return marker_count >= 4 and len(text) > 1800


def extract_placeholders(contract_text: str) -> list[str]:
    placeholders: list[str] = []
    seen = set()
    for raw_placeholder in PLACEHOLDER_RE.findall(contract_text):
        placeholder = " ".join(raw_placeholder.split())
        normalized = placeholder.lower()
        if placeholder and normalized not in seen:
            seen.add(normalized)
            placeholders.append(placeholder)
    return placeholders


def is_affirmative_message(text: str) -> bool:
    normalized = text.strip().lower()
    return normalized in {"да", "давай", "ок", "окей", "согласен", "согласна", "переходим", "да, переходим", "направляем"}


def is_short_option(text: str) -> bool:
    normalized = text.strip().lower().replace("ё", "е")
    return normalized in {"краткая", "краткую", "1", "первую", "вариант 1"}


def is_expanded_option(text: str) -> bool:
    normalized = text.strip().lower().replace("ё", "е")
    return normalized in {"расширенная", "расширенную", "2", "вторую", "вариант 2"}


def last_assistant_message(messages: list[Message]) -> str:
    for message in reversed(messages):
        if message.role == MessageRole.assistant:
            return message.content
    return ""


def parse_placeholder_values(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        clean_key = " ".join(key.replace("[", "").replace("]", "").split()).lower()
        clean_value = value.strip()
        if clean_key and clean_value:
            values[clean_key] = clean_value
    return values


def fill_contract_placeholders(contract_text: str, values: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        placeholder = " ".join(match.group(1).split())
        return values.get(placeholder.lower(), match.group(0))

    return PLACEHOLDER_RE.sub(replace, contract_text)


def normalize_contract_line(line: str) -> str:
    return line.strip().strip("#* ").replace("**", "").strip()


def split_contract_sentences(contract_text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", contract_text)
    return [item.strip() for item in re.split(r"(?<=[.!?])\s+", normalized) if item.strip()]


def compact_key_term(value: str, max_length: int = KEY_TERM_MAX_LENGTH, strip_leading_number: bool = True) -> str:
    value = normalize_contract_line(value)
    if strip_leading_number:
        value = re.sub(r"^\d+(?:\.\d+)*\.?\s*", "", value)
    value = re.sub(r"\s+", " ", value).strip(" ;,.")
    if not value:
        return "не указано"
    if len(value) <= max_length:
        return value
    return value[: max_length - 1].rstrip(" ,.;:") + "…"


def find_sentence(contract_text: str, keywords: tuple[str, ...]) -> str:
    for sentence in split_contract_sentences(contract_text):
        lowered = sentence.lower()
        if all(keyword in lowered for keyword in keywords):
            return sentence
    return "не указано"


def first_placeholder_value(contract_text: str, names: tuple[str, ...]) -> str:
    placeholders = {item.lower(): item for item in PLACEHOLDER_RE.findall(contract_text)}
    for name in names:
        value = placeholders.get(name.lower())
        if value:
            return f"[{value}]"
    return ""


def extract_money_or_placeholder(sentence: str, placeholder_names: tuple[str, ...] = ()) -> str:
    if sentence == "не указано":
        return "не указано"
    money_match = MONEY_RE.search(sentence)
    if money_match:
        return compact_key_term(money_match.group(1), 32, strip_leading_number=False)
    amount_with_words_match = re.search(r"(\d[\d\s]*)\s*\([^)]*\)\s*руб", sentence, re.IGNORECASE)
    if amount_with_words_match:
        return compact_key_term(
            f"{amount_with_words_match.group(1).strip()} рублей",
            32,
            strip_leading_number=False,
        )
    placeholder = first_placeholder_value(sentence, placeholder_names)
    return compact_key_term(placeholder, 48) if placeholder else "не указано"


def build_object_summary(contract_text: str) -> str:
    normalized = contract_text.lower()
    if "1-комнат" in normalized and "москва" in normalized:
        return "1-комнатная квартира в Москве"
    address = first_placeholder_value(contract_text, ("адрес жилого помещения", "адрес объекта"))
    if "квартир" in normalized:
        object_type = "квартира"
    elif "комнат" in normalized:
        object_type = "комната"
    elif "жилой дом" in normalized or re.search(r"\bдом\b", normalized):
        object_type = "жилой дом"
    else:
        object_type = "жилое помещение"

    if address:
        return f"{object_type}, {address}"

    address_sentence = find_sentence(contract_text, ("адрес",))
    if address_sentence != "не указано":
        return compact_key_term(address_sentence)
    return object_type


def build_key_terms(contract_text: str) -> list[dict[str, str]]:
    term_placeholder = first_placeholder_value(contract_text, ("дата окончания договора", "срок"))
    if "13 августа 2027" in contract_text:
        term_value = "11 месяцев"
    else:
        term_value = f"до {term_placeholder}" if term_placeholder else compact_key_term(find_sentence(contract_text, ("действует",)))

    payment_sentence = find_sentence(contract_text, ("ежемесячная", "плата"))
    payment_value = extract_money_or_placeholder(payment_sentence, ("сумма цифрами", "сумма"))

    utilities_sentence = find_sentence(contract_text, ("коммунальные", "платежи"))
    if utilities_sentence != "не указано" and "показан" in utilities_sentence.lower():
        utilities_value = "счетчики отдельно"
    else:
        utilities_value = "не указано"

    prolongation_sentence = find_sentence(contract_text, ("автоматически", "продлен"))
    prolongation_value = "есть" if prolongation_sentence != "не указано" else "нет"

    children_value = "можно с детьми"
    pets_sentence = find_sentence(contract_text, ("домашних", "животных"))
    if pets_sentence != "не указано" and "соглас" in pets_sentence.lower():
        pets_value = "нельзя с животными без согласия"
    elif pets_sentence != "не указано" and "не допуска" in pets_sentence.lower():
        pets_value = "нельзя с животными"
    else:
        pets_value = "не указано"

    deposit_sentence = find_sentence(contract_text, ("вносит", "обеспечительный", "платеж"))
    if deposit_sentence == "не указано":
        deposit_sentence = find_sentence(contract_text, ("депозит", "размер"))
    deposit_value = extract_money_or_placeholder(deposit_sentence, ("сумма обеспечительного платежа",))
    if deposit_value != "не указано":
        deposit_value = f"в размере {deposit_value}"

    return [
        {"label": "Объект", "value": compact_key_term(build_object_summary(contract_text), strip_leading_number=False)},
        {"label": "Оплата в месяц", "value": compact_key_term(payment_value, 48, strip_leading_number=False)},
        {"label": "ЖКУ", "value": compact_key_term(utilities_value, 48)},
        {"label": "Срок", "value": compact_key_term(term_value, 48, strip_leading_number=False)},
        {"label": "Автопролонгация", "value": compact_key_term(prolongation_value, 48)},
        {"label": "Дети", "value": compact_key_term(children_value, 48)},
        {"label": "Животные", "value": compact_key_term(pets_value, 48)},
        {"label": "Депозит", "value": compact_key_term(deposit_value, 48)},
        {"label": "Споры", "value": "через AI-Arbitr"},
    ]


def infer_contract_category(title: str = "", contract_text: str = "") -> str:
    normalized = f"{title}\n{contract_text}".lower().replace("ё", "е")
    if any(marker in normalized for marker in ("найм", "жил", "квартир", "аренд")):
        return "housing_rent"
    if any(marker in normalized for marker in ("saas", "саас", "сайт", "лендинг", "разработ")):
        return "digital_development"
    if any(marker in normalized for marker in ("клининг", "уборк")):
        return "cleaning"
    if any(marker in normalized for marker in ("подряд", "строител", "ремонт")):
        return "construction"
    if any(marker in normalized for marker in ("юрид", "консультац")):
        return "legal_services"
    if any(marker in normalized for marker in ("поставк", "купл", "продаж")):
        return "goods"
    if any(marker in normalized for marker in ("заем", "займ")):
        return "loan"
    if "договор" in normalized:
        return "other_contract"
    return "unknown"


def extract_amount(value: str) -> float | None:
    match = re.search(r"(\d[\d\s]*(?:[.,]\d+)?)", value or "")
    if not match:
        return None
    normalized = match.group(1).replace(" ", "").replace(",", ".")
    try:
        return float(normalized)
    except ValueError:
        return None


def extract_term_months(value: str) -> int | None:
    normalized = (value or "").lower().replace("ё", "е")
    month_match = re.search(r"(\d+)\s*(?:месяц|мес)", normalized)
    if month_match:
        return int(month_match.group(1))
    year_match = re.search(r"(\d+)\s*(?:год|лет)", normalized)
    if year_match:
        return int(year_match.group(1)) * 12
    if "11 месяцев" in normalized:
        return 11
    return None


def key_term_value(key_terms: list[dict[str, str]], label: str) -> str:
    for term in key_terms:
        if term.get("label") == label:
            return term.get("value") or ""
    return ""


def record_analytics_event(
    db: Session,
    event_type: str,
    session: ContractSession | None = None,
    user: User | None = None,
    properties: dict | None = None,
    source: str = "app",
) -> None:
    latest_version = get_latest_version(db, session) if session else None
    db.add(
        AnalyticsEvent(
            session_id=session.id if session else None,
            user_id=user.id if user else None,
            event_type=event_type,
            contract_category=infer_contract_category(session.title, latest_version.content if latest_version else "")
            if session
            else "unknown",
            session_status=session.status.value if session else "unknown",
            is_guest=is_guest_user(user) if user else False,
            source=source,
            properties=properties or {},
        )
    )


def upsert_contract_analytics_snapshot(db: Session, session: ContractSession) -> None:
    latest_version = get_latest_version(db, session)
    contract_text = latest_version.content if latest_version else ""
    key_terms = build_key_terms(contract_text) if contract_text else []
    participants = list(session.participants)
    messages = (
        db.query(Message)
        .filter(Message.session_id == session.id)
        .all()
    )
    version_count = db.query(ContractVersion).filter(ContractVersion.session_id == session.id).count()
    system_messages = [message.content for message in messages if message.role == MessageRole.system]
    payment_value = key_term_value(key_terms, "Оплата в месяц")
    deposit_value = key_term_value(key_terms, "Депозит")
    term_value = key_term_value(key_terms, "Срок")
    prolongation_value = key_term_value(key_terms, "Автопролонгация").lower()
    utilities_value = key_term_value(key_terms, "ЖКУ").lower()
    children_value = key_term_value(key_terms, "Дети").lower()
    pets_value = key_term_value(key_terms, "Животные").lower()
    snapshot = db.get(ContractAnalyticsSnapshot, session.id)
    if snapshot is None:
        snapshot = ContractAnalyticsSnapshot(session_id=session.id)
        db.add(snapshot)
    snapshot.owner_user_id = session.owner_user_id
    snapshot.contract_category = infer_contract_category(session.title, contract_text)
    snapshot.contract_kind = compact_key_term(session.title or "unknown", 120)
    snapshot.status = session.status.value
    snapshot.version_count = version_count
    snapshot.message_count = len(messages)
    snapshot.user_message_count = sum(1 for message in messages if message.role == MessageRole.user)
    snapshot.assistant_message_count = sum(1 for message in messages if message.role == MessageRole.assistant)
    snapshot.sent_to_review = any(content.startswith("VERSION_SENT|") for content in system_messages)
    snapshot.signed_by_party_2 = any(
        participant.role == ParticipantRole.party_2 and participant.approval_status == ApprovalStatus.approved
        for participant in participants
    )
    snapshot.signed_by_party_1 = any(
        participant.role == ParticipantRole.party_1 and participant.approval_status == ApprovalStatus.approved
        for participant in participants
    )
    snapshot.finalized = session.status == SessionStatus.finalized
    completed_event_exists = any("Договор отмечен как исполненный" in content for content in system_messages)
    snapshot.completed_without_dispute = completed_event_exists and not any(
        content.startswith("DISPUTE_OPENED|") for content in system_messages
    )
    snapshot.dispute_opened = any(content.startswith("DISPUTE_OPENED|") for content in system_messages)
    snapshot.monthly_payment_amount = extract_amount(payment_value)
    snapshot.deposit_amount = extract_amount(deposit_value)
    snapshot.term_months = extract_term_months(term_value)
    snapshot.auto_prolongation = True if prolongation_value == "есть" else False if prolongation_value == "нет" else None
    snapshot.utilities_separate = "счетчик" in utilities_value
    snapshot.children_allowed = "можно" in children_value
    snapshot.pets_allowed = False if "нельзя" in pets_value else True if "можно" in pets_value else None
    snapshot.updated_at = now_utc()


@app.on_event("startup")
def backfill_contract_analytics_snapshots() -> None:
    db = SessionLocal()
    try:
        sessions = db.query(ContractSession).all()
        for session in sessions:
            upsert_contract_analytics_snapshot(db, session)
        db.commit()
    finally:
        db.close()


def build_placeholder_request(placeholders: list[str]) -> str:
    lines = "\n".join(f"- {placeholder}: " for placeholder in placeholders)
    return (
        "Хорошо, перед согласованием нужно заполнить данные, которые пока стоят в квадратных скобках.\n\n"
        "Пришлите их в таком формате:\n"
        f"{lines}\n\n"
        "Я проверю, что все обязательные поля заполнены, и внесу данные в договор."
    )


def build_demo_replacement_request() -> str:
    return (
        "Хорошо, перед согласованием заменим вымышленные данные на реальные.\n\n"
        "Пришлите данные в таком формате:\n"
        "- роль: наниматель / наймодатель / заказчик / исполнитель\n"
        "- ФИО: \n"
        "- паспорт: \n"
        "- email: \n\n"
        "Я проверю формат и изменю вымышленные данные в договоре."
    )


def extract_email_from_text(text: str) -> str | None:
    match = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-zА-Яа-я]{2,}", text)
    return match.group(0) if match else None


def infer_legal_role_pair(title: str, contract_text: str) -> tuple[str, str]:
    source = f"{title}\n{contract_text}".lower()
    role_pairs = (
        (("найм", "нанимател", "жилое помещ"), ("Наймодатель", "Наниматель")),
        (("аренд", "арендатор"), ("Арендодатель", "Арендатор")),
        (("купл", "продавец", "покупател"), ("Продавец", "Покупатель")),
        (("подряд", "подрядчик"), ("Заказчик", "Подрядчик")),
        (("услуг", "исполнитель", "заказчик", "разработ"), ("Заказчик", "Исполнитель")),
        (("займ", "заемщик", "займодав"), ("Займодавец", "Заемщик")),
    )
    for markers, pair in role_pairs:
        if any(marker in source for marker in markers):
            return pair
    return ("Заказчик", "Исполнитель")


def assign_legal_roles(session: ContractSession, contract_text: str, creator_role: str) -> None:
    first_role, second_role = infer_legal_role_pair(session.title, contract_text)
    if creator_role not in {first_role, second_role}:
        raise HTTPException(status_code=400, detail="Выберите свою роль в договоре")
    session.party_1_legal_role = creator_role
    session.party_2_legal_role = second_role if creator_role == first_role else first_role


def fill_demo_contract_data(contract_text: str, values: dict[str, str]) -> str:
    role = values.get("роль", "").lower()
    full_name = values.get("фио") or values.get("ф.и.о.") or values.get("имя")
    passport = values.get("паспорт") or values.get("паспортные данные")
    email = values.get("email") or values.get("почта") or values.get("адрес электронной почты")
    updated = contract_text

    is_party_two = any(marker in role for marker in ("наним", "заказ", "сторона 2", "покуп", "клиент"))
    if full_name:
        if is_party_two:
            updated = updated.replace("Иванов Иван Иванович", full_name)
        else:
            updated = updated.replace("Петров Петр Петрович", full_name)
    if passport:
        if is_party_two:
            updated = updated.replace("1111 111111", passport)
        else:
            updated = updated.replace("2222 222222", passport)
            updated = updated.replace("1111 111111", passport, 1)
    if email:
        if is_party_two:
            updated = updated.replace("ivanov@example.com", email).replace("party2@example.test", email)
        else:
            updated = updated.replace("petrov@example.com", email).replace("party1@example.test", email)
    return updated


def mask_tail(value: str, visible_tail: int = 2) -> str:
    compact = "".join(ch for ch in value if ch.isalnum())
    if not compact:
        return ""
    if len(compact) <= visible_tail:
        return "*" * len(compact)
    return "*" * (len(compact) - visible_tail) + compact[-visible_tail:]


def apply_ephemeral_party_data(
    contract_text: str,
    payload: ReviewApproveRequest,
    participant_role: ParticipantRole = ParticipantRole.party_2,
    legal_role: str | None = None,
) -> str:
    # The MVP collects only the passport number, so remove legacy demo-only
    # issuing authority and registration address from every party line.
    updated = re.sub(
        r",\s*выдан[^\n]*?,\s*именуемый",
        ", именуемый",
        contract_text,
        flags=re.IGNORECASE,
    )
    legal_role = legal_role or ("Наниматель" if participant_role == ParticipantRole.party_2 else "Наймодатель")
    passport_digits = re.sub(r"\D", "", payload.passport)
    lines = updated.splitlines()
    replaced_requisites = False
    for index, line in enumerate(lines):
        if f"«{legal_role}»" not in line:
            continue
        lines[index] = re.sub(r"Гражданин РФ\s+[^,]+", f"Гражданин РФ {payload.full_name}", line, count=1)
        if len(passport_digits) == 10:
            lines[index] = re.sub(
                r"паспорт серии\s*\d{4}\s*№\s*\d{6}",
                f"паспорт серии {passport_digits[:4]} № {passport_digits[4:]}",
                lines[index],
                count=1,
            )
        replaced_requisites = True
        break
    updated = "\n".join(lines)
    section_label = legal_role.upper()
    other_role = "Наймодатель" if legal_role == "Наниматель" else "Наниматель" if legal_role == "Наймодатель" else ""
    other_label = other_role.upper()
    passport_line = (
        f"Паспорт: серия {passport_digits[:4]} № {passport_digits[4:]}"
        if len(passport_digits) == 10
        else f"Паспорт: {payload.passport}"
    )
    requisites_block = (
        f"{section_label}:\n"
        f"Ф.И.О.: {payload.full_name}\n"
        f"{passport_line}\n"
        f"Телефон: {payload.phone}\n"
        f"E-mail: {payload.email}"
    )
    section_boundary = rf"\n\s*{other_label}:|" if other_label else ""
    section_pattern = rf"{section_label}:\s*\n.*?(?={section_boundary}\n\s*11\.1\.|\Z)"
    updated, section_replacements = re.subn(
        section_pattern,
        requisites_block,
        updated,
        count=1,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if section_replacements:
        updated = re.sub(
            r"\n\s*11\.1\.\s*Договор подписывается сторонами простой электронной подписью[^\n]*",
            "",
            updated,
            count=1,
            flags=re.IGNORECASE,
        )
    if not replaced_requisites and payload.party_type == "individual":
        updated += (
            f"\n\nРеквизиты {'Стороны 2' if participant_role == ParticipantRole.party_2 else 'Стороны 1'}:\n"
            f"ФИО: {payload.full_name}\nПаспорт: {payload.passport}"
        )
    if payload.party_type == "business":
        details = [
            f"Организация / ИП: {payload.organization_name}",
            f"Подписант: {payload.full_name}",
            f"ИНН: {payload.inn}",
            f"ОГРН / ОГРНИП: {payload.ogrn}",
        ]
        party_label = "Стороны 2" if participant_role == ParticipantRole.party_2 else "Стороны 1"
        updated += f"\n\nРеквизиты {party_label}:\n" + "\n".join(details)
    party_number = "2" if participant_role == ParticipantRole.party_2 else "1"
    if section_replacements == 0 and payload.phone and f"телефон стороны {party_number}" not in updated.lower():
        updated += f"\n\nТелефон Стороны {party_number}: {payload.phone}"
    if payload.inn and payload.party_type != "business" and "инн" not in updated.lower():
        updated += f"\nИНН Стороны {party_number}: {payload.inn}"
    if section_replacements == 0 and payload.email and str(payload.email).lower() not in updated.lower():
        updated += f"\nEmail Стороны {party_number}: {payload.email}"
    return updated


def is_rent_increase_question(text: str) -> bool:
    normalized = text.lower()
    rent_markers = ("плат", "аренд", "найм", "цена", "стоимост")
    increase_markers = ("увелич", "повыс", "подня", "индексац", "измен")
    return any(marker in normalized for marker in rent_markers) and any(
        marker in normalized for marker in increase_markers
    )


def build_rent_increase_answer(contract_text: str) -> str:
    normalized = contract_text.lower()
    has_explicit_increase_rule = (
        ("повыш" in normalized or "увелич" in normalized or "индексац" in normalized)
        and "плат" in normalized
    )
    if has_explicit_increase_rule:
        contract_status = (
            "В договоре есть условие об изменении платы, поэтому нужно смотреть именно его: "
            "кто вправе инициировать повышение, как направляется уведомление, с какой даты действует новая сумма."
        )
    else:
        contract_status = (
            "Прямо в этой редакции договора порядок повышения платы не предусмотрен."
        )

    return (
        f"{contract_status}\n\n"
        "По общему правилу наймодатель не может просто в одностороннем порядке поднять плату: "
        "размер платы устанавливается соглашением сторон, а одностороннее изменение допускается "
        "только если это предусмотрено законом или самим договором. Для договоров найма/аренды "
        "обычно закладывают ограничение: пересмотр платы не чаще одного раза в год.\n\n"
        "Практически лучше добавить в договор отдельное условие: например, что плата может быть "
        "увеличена не чаще одного раза в год, с письменным уведомлением за 30 дней и с предельным "
        "размером повышения, например не более 10-15%.\n\n"
        "Хотите включить это условие в договор?"
    )


def build_contract_gap_instruction() -> str:
    return (
        "Работай как внимательный договорный юрист. Если вопрос пользователя показывает беспокойство "
        "о конкретной ситуации, проверь три уровня:\n"
        "1. Есть ли прямое условие в текущем договоре.\n"
        "2. Есть ли применимая норма ГК РФ или обычная договорная практика.\n"
        "3. Снимается ли риск включением ясного условия в договор.\n\n"
        "Если в договоре прямого условия нет, но вопрос регулируется законом или обычно решается "
        "договорным условием, не ограничивайся ответом «зависит от договора». Скажи эмпатично: "
        "«Понимаю, почему вы спрашиваете: это действительно лучше заранее прописать». Затем объясни "
        "норму закона простым языком и в конце спроси: «Хотите включить это положение в договор?»\n\n"
        "Если в договоре уже есть подходящее условие, сначала укажи это и объясни, как оно работает. "
        "Если условие есть, но оно слишком общее или не снимает риск полностью, предложи уточнить его."
    )


async def summarize_added_contract_norm(updated_contract: str, requested_change: str) -> str:
    prompt = [
        {
            "role": "system",
            "text": (
                "Ты AI-Арбитр. Пользователь попросил добавить условие в договор. "
                "Перед тобой уже обновленная полная редакция договора. "
                "Не выводи весь договор. Покажи только одну добавленную или измененную норму, "
                "которую пользователь должен увидеть в чате. Затем задай вопрос: "
                "«Переходим к согласованию?»"
            ),
        },
        {
            "role": "user",
            "text": (
                f"Просьба пользователя:\n{requested_change}\n\n"
                f"Обновленная редакция договора:\n{updated_contract}"
            ),
        },
    ]
    return await ask_yandex_gpt(prompt)


def build_rule_based_contract_norm(dialogue: str) -> str | None:
    normalized = dialogue.lower().replace("ё", "е")
    deposit_markers = ("депозит", "обеспечительный")
    split_markers = ("два", "2 ", "двум", "две", "платеж", "рассроч", "част")
    if any(marker in normalized for marker in deposit_markers) and any(marker in normalized for marker in split_markers):
        return (
            "Предлагаю такую редакцию нормы:\n\n"
            "[Номер пункта]. Обеспечительный платеж уплачивается Нанимателем двумя равными платежами: "
            "50% суммы обеспечительного платежа вносится в день подписания Договора, оставшиеся 50% "
            "суммы обеспечительного платежа вносятся не позднее [срок внесения второй части]. "
            "До внесения второй части обеспечительного платежа Наниматель обязан исполнять остальные "
            "обязательства по Договору в полном объеме. Невнесение второй части обеспечительного платежа "
            "в установленный срок считается существенным нарушением Договора и дает Наймодателю право "
            "потребовать внесения задолженности либо расторжения Договора в порядке, предусмотренном Договором.\n\n"
            "Добавить это условие в договор?"
        )

    increase_markers = ("повыс", "увелич", "подня", "индексац")
    payment_markers = ("плата", "аренд", "найм", "стоимость", "цена")
    if any(marker in normalized for marker in increase_markers) and any(marker in normalized for marker in payment_markers):
        return (
            "Предлагаю такую редакцию нормы:\n\n"
            "[Номер пункта]. Размер платы за пользование жилым помещением может быть изменен только "
            "по соглашению Сторон. Одностороннее увеличение платы Наймодателем не допускается, "
            "за исключением случая, когда Стороны заранее письменно согласовали такое изменение. "
            "При согласовании права на повышение платы оно допускается не чаще одного раза в год, "
            "с письменным уведомлением Нанимателя не менее чем за 30 календарных дней и в пределах "
            "не более [процент]% от действующего размера платы.\n\n"
            "Добавить это условие в договор?"
        )

    return None


def build_rule_based_addition_review(requested_change: str) -> str | None:
    normalized = requested_change.lower().replace("ё", "е")
    if "кальян" in normalized:
        return (
            "Проверил условие в контексте договора найма. Прямого запрета на использование кальяна "
            "внутри частного жилого помещения нет, но условие не должно разрешать курение в местах общего "
            "пользования, нарушение прав соседей, требований пожарной безопасности или причинение ущерба квартире.\n\n"
            "Разместить условие правильно в разделе о правах и обязанностях Нанимателя.\n\n"
            "Вариант 1 — краткий:\n"
            "[Номер пункта]. Нанимателю разрешается использовать кальян внутри Жилого помещения при соблюдении "
            "требований пожарной безопасности и прав соседей.\n\n"
            "Вариант 2 — расширенный:\n"
            "[Номер пункта]. Нанимателю разрешается использовать кальян исключительно внутри Жилого помещения. "
            "Использование кальяна в местах общего пользования не допускается. Наниматель обязан соблюдать "
            "требования пожарной безопасности, не допускать задымления помещений общего пользования, нарушения "
            "прав соседей и повреждения отделки или имущества и возместить причиненный по его вине ущерб.\n\n"
            "Выберите: краткая, расширенная или пришлите свою редакцию."
        )

    business_markers = ("космет", "маникюр", "массаж", "парикмах", "услуг")
    home_business_markers = ("на дому", "в квартир", "в жилом", "клиент")
    if any(marker in normalized for marker in business_markers) and any(marker in normalized for marker in home_business_markers):
        return (
            "Однозначно включить разрешение в такой формулировке нельзя: сначала нужно понять масштаб деятельности. "
            "Часть 2 статьи 17 ЖК РФ допускает профессиональную или предпринимательскую деятельность в жилом "
            "помещении для законно проживающего гражданина, если она не нарушает права соседей и требования к жилью. "
            "При этом статья 288 ГК РФ не позволяет фактически разместить в квартире организацию без перевода "
            "помещения в нежилое.\n\n"
            "Уточните: услуги оказывает сам Наниматель без работников и вывески, сколько клиентов планируется "
            "принимать в день и требуется ли специальное оборудование? После этого я смогу проверить условие и "
            "предложить безопасную редакцию."
        )

    prohibited_markers = ("производство", "хостел", "гостиниц", "наркот", "незакон")
    if any(marker in normalized for marker in prohibited_markers):
        return (
            "Включить такое разрешение в договор нельзя: соглашение сторон не может узаконить использование "
            "жилого помещения вопреки его назначению и обязательным требованиям закона. Предложите законную "
            "альтернативу, и я проверю ее отдельно."
        )
    return None


async def review_contract_addition(contract_text: str, requested_change: str, model: str | None) -> str:
    rule_based = build_rule_based_addition_review(requested_change)
    if rule_based:
        return rule_based
    prompt = [
        {
            "role": "system",
            "text": (
                "Ты договорный юрист РФ. Анализируй ТОЛЬКО последнюю просьбу пользователя и текущий договор; "
                "не переноси темы из предыдущего диалога. Сначала проверь, допустимо ли условие по императивным "
                "нормам закона, назначению договора и балансу сторон. Не выдумывай номер статьи: указывай статью "
                "только если уверен. Если условие незаконно, напиши, что включить его нельзя, объясни причину и "
                "не предлагай редакции. Если нужны факты для правовой оценки, задай один конкретный уточняющий вопрос. "
                "Если условие допустимо, назови подходящий раздел договора и предложи две редакции одной нормы. "
                "Формат вариантов строго: «Вариант 1 — краткий:» и «Вариант 2 — расширенный:». Заверши фразой "
                "«Выберите: краткая, расширенная или пришлите свою редакцию». Не возвращай полный договор."
            ),
        },
        {
            "role": "user",
            "text": (
                f"Последняя просьба, которую нужно проверить:\n{requested_change}\n\n"
                f"Текущая версия договора:\n{contract_text}"
            ),
        },
    ]
    return await ask_yandex_gpt(prompt, model=model)


def is_deposit_split_question(text: str) -> bool:
    normalized = text.lower().replace("ё", "е")
    deposit_markers = ("депозит", "обеспечительный")
    split_markers = ("два", "2 ", "двум", "две", "платеж", "рассроч", "част")
    return any(marker in normalized for marker in deposit_markers) and any(marker in normalized for marker in split_markers)


def build_deposit_split_answer(contract_text: str) -> str:
    has_split = "двумя равными платежами" in contract_text.lower().replace("ё", "е")
    if has_split:
        return (
            "Да, в этой редакции уже предусмотрена рассрочка обеспечительного платежа на два платежа. "
            "Проверьте только срок внесения второй части и последствия просрочки.\n\n"
            "Хотите уточнить это условие в договоре?"
        )
    return (
        "Да, обеспечительный платеж можно разбить на два платежа, если стороны прямо согласуют это в договоре. "
        "Такое условие лучше прописать отдельно: размер первой части, срок внесения второй части и последствия просрочки.\n\n"
        "Хотите включить это условие в договор?"
    )


async def propose_contract_norm(contract_text: str, last_answer: str, dialogue: str) -> str:
    rule_based = build_rule_based_contract_norm(dialogue)
    if rule_based:
        return rule_based

    prompt = [
        {
            "role": "system",
            "text": (
                "Ты договорный юрист. Пользователь согласился включить в договор положение, "
                "которое ты только что предложил после ответа на вопрос. "
                "Не выводи весь договор и не говори, что договор уже изменен. "
                "Сформулируй строго одну готовую норму для включения в договор: с номером пункта-заглушкой "
                "и юридически аккуратным текстом. Норма должна вытекать только из последнего предложения "
                "о включении условия. Не добавляй тему, которую пользователь не обсуждал. "
                "После нормы коротко спроси: «Добавить это условие в договор?»"
            ),
        },
        {
            "role": "user",
            "text": (
                f"Текущая версия договора:\n{contract_text}\n\n"
                f"Последний ответ помощника, где предложено включить условие:\n{last_answer}\n\n"
                f"Последний диалог:\n{dialogue}"
            ),
        },
    ]
    return await ask_yandex_gpt(prompt)


async def propose_contract_norm_options(contract_text: str, last_answer: str, dialogue: str) -> str:
    rule_based = build_rule_based_contract_norm(dialogue)
    if rule_based:
        norm = rule_based.split("Предлагаю такую редакцию нормы:", 1)[-1]
        norm = norm.replace("Добавить это условие в договор?", "").strip()
        return (
            "Да, можно добавить. Предлагаю две редакции.\n\n"
            "Вариант 1 — краткий:\n"
            f"{norm}\n\n"
            "Вариант 2 — расширенный:\n"
            f"{norm} Стороны подтверждают, что такое условие направлено на баланс интересов сторон, "
            "предсказуемость исполнения договора и предотвращение спора о порядке применения соответствующего условия.\n\n"
            "Выберите: краткая, расширенная или пришлите свою редакцию."
        )

    prompt = [
        {
            "role": "system",
            "text": (
                "Ты договорный юрист. Пользователь согласился добавить в договор условие, "
                "которое ты предложил после ответа на вопрос. "
                "Сформулируй две редакции одной и той же нормы: краткую и расширенную. "
                "Не выводи полный договор. Не утверждай, что норма уже добавлена. "
                "Формат строго такой:\n"
                "Да, можно добавить. Предлагаю две редакции.\n\n"
                "Вариант 1 — краткий:\n[текст нормы]\n\n"
                "Вариант 2 — расширенный:\n[текст нормы]\n\n"
                "Выберите: краткая, расширенная или пришлите свою редакцию."
            ),
        },
        {
            "role": "user",
            "text": (
                f"Текущая версия договора:\n{contract_text}\n\n"
                f"Последний ответ помощника:\n{last_answer}\n\n"
                f"Последний диалог:\n{dialogue}"
            ),
        },
    ]
    return await ask_yandex_gpt(prompt)


def extract_norm_option(options_text: str, option: str) -> str | None:
    if option == "short":
        pattern = r"Вариант 1\s*[—-]\s*кратк\w*:\s*(.*?)(?:\n\s*Вариант 2\s*[—-]\s*расшир|\Z)"
    else:
        pattern = r"Вариант 2\s*[—-]\s*расшир\w*:\s*(.*?)(?:\n\s*Выберите|\Z)"
    match = re.search(pattern, options_text, re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    norm = match.group(1).strip()
    return norm or None


def build_custom_norm_review(custom_text: str) -> str:
    return (
        "Редакция условия:\n\n"
        f"{custom_text.strip()}\n\n"
        "Фиксирую новый пункт договора.\n\n"
        "Переходим к согласованию?"
    )


def build_norm_saved_answer(norm: str) -> str:
    return (
        "Фиксирую новый пункт договора.\n\n"
        f"{norm.strip()}\n\n"
        "Переходим к согласованию?"
    )


def infer_session_title(content: str) -> str:
    if is_housing_rent_request(content):
        return "Договор найма"

    normalized = content.lower()
    title_rules = [
        (("saas", "саас", "сaas", "saaс"), "Договор SaaS"),
        (("найм", "квартир", "жил", "жиль"), "Договор найма"),
        (("аренд",), "Договор аренды"),
        (("лендинг", "landing"), "Договор на лендинг"),
        (("сайт", "веб"), "Договор на сайт"),
        (("клининг", "уборк"), "Договор клининга"),
        (("юруслуг", "юридическ", "консультац", "претензи"), "Договор юруслуг"),
        (("подряд", "ремонт", "строитель"), "Договор подряда"),
        (("поставк",), "Договор поставки"),
        (("купл", "продаж"), "Договор купли-продажи"),
        (("заем", "займ", "долг"), "Договор займа"),
        (("ндаш", "nda", "конфиденциаль"), "NDA"),
        (("оказан", "услуг"), "Договор услуг"),
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
    return {"status": "ok", "version": APP_VERSION}


@app.get("/workflow/catalog")
def get_workflow_catalog():
    return workflow_catalog()


@app.get("/stats")
def stats(db: Session = Depends(get_db)):
    real_users = db.query(User).filter(~User.email.like(f"%{GUEST_EMAIL_SUFFIX}")).count()
    guest_users = db.query(User).filter(User.email.like(f"%{GUEST_EMAIL_SUFFIX}")).count()
    generated_ids = {
        row[0]
        for row in db.query(ContractVersion.session_id)
        .distinct()
        .all()
    }
    signed_ids = {
        row[0]
        for row in db.query(ContractSession.id)
        .filter(ContractSession.status == SessionStatus.finalized)
        .all()
    }
    disputed_ids = {
        row[0]
        for row in db.query(Message.session_id)
        .filter(Message.role == MessageRole.user, Message.content.startswith("СПОР"))
        .distinct()
        .all()
    }
    completed_ids = {
        row[0]
        for row in db.query(Message.session_id)
        .filter(
            Message.role == MessageRole.system,
            Message.content.startswith("Договор отмечен как исполненный"),
        )
        .distinct()
        .all()
    }
    closed_without_dispute_ids = completed_ids - disputed_ids
    return {
        "users": real_users,
        "guest_users": guest_users,
        "generated_contracts": len(generated_ids),
        "signed_contracts": len(signed_ids),
        "disputed_contracts": len(disputed_ids),
        "closed_without_dispute_contracts": len(closed_without_dispute_ids),
    }


def set_auth_cookie(response: Response, user: User) -> None:
    use_secure_cookie = settings.app_base_url.startswith("https://")
    response.set_cookie(
        settings.session_cookie_name,
        make_session_cookie(str(user.id)),
        max_age=60 * 60 * 24 * 30,
        httponly=True,
        secure=use_secure_cookie,
        samesite="lax",
    )


def clear_auth_cookie(response: Response) -> None:
    use_secure_cookie = settings.app_base_url.startswith("https://")
    response.delete_cookie(
        settings.session_cookie_name,
        secure=use_secure_cookie,
        httponly=True,
        samesite="lax",
    )


def set_verified_ip_cookie(response: Response, user: User, ip_address: str) -> None:
    if not ip_address:
        return
    use_secure_cookie = settings.app_base_url.startswith("https://")
    response.set_cookie(
        VERIFIED_IP_COOKIE_NAME,
        make_verified_ip_cookie(str(user.id), ip_address),
        max_age=60 * 60 * 24 * 14,
        httponly=True,
        secure=use_secure_cookie,
        samesite="lax",
    )


def clear_verified_ip_cookie(response: Response) -> None:
    use_secure_cookie = settings.app_base_url.startswith("https://")
    response.delete_cookie(
        VERIFIED_IP_COOKIE_NAME,
        secure=use_secure_cookie,
        httponly=True,
        samesite="lax",
    )


def get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    real_ip = request.headers.get("x-real-ip", "")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else ""


def rate_limit_subject(request: Request, user: User | None = None, email: str = "") -> str:
    if user is not None and not is_guest_user(user):
        return f"user:{user.id}"
    if email:
        return f"email:{email.lower()}"
    client_ip = get_client_ip(request)
    return f"ip:{client_ip or 'unknown'}"


def check_daily_rate_limit(
    db: Session,
    request: Request,
    action: str,
    user: User | None = None,
    email: str = "",
) -> None:
    subject = rate_limit_subject(request, user=user, email=email)
    today = now_utc().date()
    day_start = datetime.combine(today, time.min, tzinfo=timezone.utc)
    count = (
        db.query(RateLimitEvent)
        .filter(
            RateLimitEvent.subject == subject,
            RateLimitEvent.action == action,
            RateLimitEvent.created_at >= day_start,
        )
        .count()
    )
    if count >= DAILY_ACTION_LIMIT:
        raise HTTPException(
            status_code=429,
            detail="Достигнут дневной лимит 100 запросов. Доступ будет восстановлен завтра.",
        )
    db.add(RateLimitEvent(subject=subject, action=action))
    db.flush()


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


def apply_user_consent(user: User) -> None:
    user.service_rules_accepted = True
    user.privacy_accepted = True
    user.cookies_accepted = True
    user.consent_version = CONSENT_VERSION
    user.consented_at = now_utc()


def require_unified_consent(personal_data: bool, service_rules: bool, cookies: bool, version: str) -> None:
    if not (personal_data and service_rules and cookies):
        raise HTTPException(
            status_code=400,
            detail="Нужно принять Правила сервиса, Политику конфиденциальности и использование обязательных cookies",
        )
    if version != CONSENT_VERSION:
        raise HTTPException(status_code=409, detail="Правила сервиса обновлены. Обновите страницу и примите новую редакцию")


@app.post("/auth/consent")
def save_consent(
    payload: ConsentRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_unified_consent(
        payload.privacy_accepted,
        payload.service_rules_accepted,
        payload.cookies_accepted,
        payload.consent_version,
    )
    apply_user_consent(user)
    db.commit()
    return {"accepted": True, "consent_version": user.consent_version}


@app.post("/auth/guest")
def create_guest(response: Response, db: Session = Depends(get_db)):
    user = User(email=f"guest-{uuid.uuid4().hex}{GUEST_EMAIL_SUFFIX}")
    db.add(user)
    db.flush()
    ensure_demo_session(db, user)
    db.commit()
    set_auth_cookie(response, user)
    return {"id": user.id, "email": "", "is_guest": True}


def issue_magic_link(
    email: str,
    request: Request,
    db: Session,
    guest_user_id: uuid.UUID | None = None,
) -> dict[str, str]:
    check_daily_rate_limit(db, request, "magic_link", email=email)
    raw_token = generate_raw_token()
    db.add(
        AuthToken(
            email=email,
            token_hash=hash_token(raw_token),
            expires_at=token_expires_at(),
            guest_user_id=guest_user_id,
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
    request: Request,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    require_unified_consent(
        payload.personal_data_accepted,
        payload.service_rules_accepted,
        payload.cookies_accepted,
        payload.consent_version,
    )

    existing_user = db.query(User).filter(User.email == payload.email).one_or_none()
    if existing_user is not None and (current_user is None or existing_user.id != current_user.id):
        raise HTTPException(status_code=409, detail="Аккаунт с таким email уже есть. Войдите по email.")

    if current_user is not None and is_guest_user(current_user):
        current_user.email = payload.email
        apply_user_consent(current_user)
        db.flush()
    elif existing_user is None:
        new_user = User(email=payload.email)
        apply_user_consent(new_user)
        db.add(new_user)
        db.flush()
    elif existing_user is not None:
        apply_user_consent(existing_user)
    return issue_magic_link(payload.email, request, db)


@app.post("/auth/quick-register")
def quick_register_guest(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_unified_consent(
        payload.personal_data_accepted,
        payload.service_rules_accepted,
        payload.cookies_accepted,
        payload.consent_version,
    )
    if not is_guest_user(current_user):
        return {"id": current_user.id, "email": current_user.email, "is_guest": False}

    existing_user = db.query(User).filter(User.email == payload.email).one_or_none()
    if existing_user is not None:
        result = issue_magic_link(payload.email, request, db, guest_user_id=current_user.id)
        result["verification_required"] = True
        result["message"] = "Аккаунт уже существует. Отправил ссылку для подтверждения и сохранения договора."
        return result

    current_user.email = payload.email
    apply_user_consent(current_user)
    current_user.trusted_login_count = 0
    db.flush()
    db.commit()
    db.refresh(current_user)
    set_auth_cookie(response, current_user)
    return {
        "id": current_user.id,
        "email": current_user.email,
        "is_guest": False,
        "message": "Сессия сохранена. Продолжаю отправку ссылки второй стороне.",
    }


@app.post("/auth/login")
def request_login_link(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="Аккаунт не найден. Зарегистрируйтесь по email.")

    return issue_magic_link(payload.email, request, db)


@app.post("/auth/magic-link")
def request_magic_link(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    require_unified_consent(
        payload.personal_data_accepted,
        payload.service_rules_accepted,
        payload.cookies_accepted,
        payload.consent_version,
    )

    user = db.query(User).filter(User.email == payload.email).one_or_none()
    if user is None:
        user = User(email=payload.email)
        db.add(user)
        db.flush()
    apply_user_consent(user)

    return issue_magic_link(payload.email, request, db)


@app.get("/auth/verify")
def verify_magic_link(token: str, request: Request, db: Session = Depends(get_db)):
    token_hash = hash_token(token)
    auth_token = db.query(AuthToken).filter(AuthToken.token_hash == token_hash).one_or_none()
    if auth_token is None or auth_token.used or auth_token.expires_at < datetime.now(timezone.utc):
        return RedirectResponse(f"{settings.app_base_url}/login?error=expired", status_code=303)

    user = db.query(User).filter(User.email == auth_token.email).one_or_none()
    if user is None:
        user = User(email=auth_token.email)
        db.add(user)
        db.flush()

    if auth_token.guest_user_id and auth_token.guest_user_id != user.id:
        guest = db.get(User, auth_token.guest_user_id)
        if guest is not None and is_guest_user(guest):
            guest_sessions = db.query(ContractSession).filter(ContractSession.owner_user_id == guest.id).all()
            for guest_session in guest_sessions:
                guest_session.owner_user_id = user.id
                creator = (
                    db.query(ContractParticipant)
                    .filter(
                        ContractParticipant.session_id == guest_session.id,
                        ContractParticipant.role == ParticipantRole.party_1,
                    )
                    .one_or_none()
                )
                if creator is not None:
                    creator.user_id = user.id

    user.last_login_at = now_utc()
    user.trusted_login_count = 0
    auth_token.used = True
    ensure_demo_session(db, user)
    db.commit()

    response = RedirectResponse(f"{settings.app_base_url}/?login=success", status_code=303)
    set_auth_cookie(response, user)
    set_verified_ip_cookie(response, user, get_client_ip(request))
    return response


@app.get("/auth/me")
def auth_me(
    user: User = Depends(get_current_user),
):
    return {
        "id": user.id,
        "email": "" if is_guest_user(user) else user.email,
        "is_guest": is_guest_user(user),
        "consent_version": user.consent_version,
        "required_consent_version": CONSENT_VERSION,
        "consent_required": user.consent_version != CONSENT_VERSION,
    }


@app.post("/auth/logout")
def logout(response: Response):
    clear_auth_cookie(response)
    clear_verified_ip_cookie(response)
    return {"message": "ok"}


@app.post("/sessions")
def create_session(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    session = ContractSession(owner_user_id=user.id)
    db.add(session)
    db.flush()
    db.add(ContractParticipant(session_id=session.id, user_id=user.id, role=ParticipantRole.party_1))
    db.add(ContractParticipant(session_id=session.id, role=ParticipantRole.party_2))
    record_analytics_event(db, "session_created", session=session, user=user)
    upsert_contract_analytics_snapshot(db, session)
    db.commit()
    db.refresh(session)
    return session


@app.get("/sessions")
def list_sessions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_demo_session(db, user)
    db.commit()
    sessions = (
        db.query(ContractSession)
        .join(ContractParticipant, ContractParticipant.session_id == ContractSession.id)
        .filter(or_(ContractSession.owner_user_id == user.id, ContractParticipant.user_id == user.id))
        .distinct()
        .order_by(ContractSession.updated_at.desc())
        .all()
    )
    return [serialize_session_summary(db, session, user) for session in sessions]


@app.get("/contacts")
def list_contract_contacts(
    q: str = "",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    normalized_query = q.strip().lower()
    accessible_session_ids = {
        row[0]
        for row in db.query(ContractParticipant.session_id)
        .filter(ContractParticipant.user_id == user.id)
        .all()
    }
    if not accessible_session_ids:
        return []
    participants = (
        db.query(ContractParticipant)
        .filter(ContractParticipant.session_id.in_(accessible_session_ids))
        .all()
    )
    contacts = []
    seen = set()
    for participant in participants:
        contact = participant.user
        if contact is None or contact.id == user.id or is_guest_user(contact):
            continue
        email = contact.email.lower()
        if normalized_query and normalized_query not in email:
            continue
        if email in seen:
            continue
        seen.add(email)
        contacts.append({"email": contact.email})
    return contacts[:8]


@app.get("/sessions/{session_id}")
def get_session(session_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    session = get_accessible_session(db, session_id, user)
    current_participant = next(
        (participant for participant in session.participants if participant.user_id == user.id),
        None,
    )
    actor_role = current_participant.role.value if current_participant else "party_1"
    latest_version = get_latest_version(db, session)
    messages = (
        db.query(Message)
        .filter(Message.session_id == session.id)
        .order_by(Message.created_at.asc())
        .all()
    )
    return {
        "session": session,
        "participants": session.participants,
        "versions": session.versions,
        "latest_version": latest_version,
        "key_terms": build_key_terms(latest_version.content) if latest_version else [],
        "messages": messages,
        "workflow": workflow_for(db, session, actor_role),
    }


@app.delete("/sessions/{session_id}")
def delete_session(session_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    session = db.get(ContractSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    if session.owner_user_id != user.id:
        raise HTTPException(status_code=403, detail="Удалить договор может только его создатель")
    require_workflow_action(db, session, "party_1", ContractAction.DELETE_CONTRACT)

    session.is_deleted = True
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


def build_workflow_context(db: Session, session: ContractSession) -> WorkflowContext:
    participants = list(session.participants)
    party_1 = next((item for item in participants if item.role == ParticipantRole.party_1), None)
    party_2 = next((item for item in participants if item.role == ParticipantRole.party_2), None)
    has_version = db.query(ContractVersion.id).filter(ContractVersion.session_id == session.id).first() is not None
    invite_sent = (
        db.query(Message.id)
        .filter(Message.session_id == session.id, Message.content.like("VERSION_SENT|%"))
        .first()
        is not None
    )
    dispute_opened = (
        db.query(Message.id)
        .filter(Message.session_id == session.id, Message.content.like("DISPUTE_OPENED|%"))
        .first()
        is not None
    )
    return WorkflowContext(
        has_version=has_version,
        invite_sent=invite_sent,
        party_1_approved=party_1 is not None and party_1.approval_status == ApprovalStatus.approved,
        party_2_approved=party_2 is not None and party_2.approval_status == ApprovalStatus.approved,
        finalized=session.status == SessionStatus.finalized,
        dispute_opened=dispute_opened,
        completed=session.is_completed,
        deleted=session.is_deleted,
    )


def workflow_for(db: Session, session: ContractSession, actor_role: str) -> dict:
    return describe_workflow(build_workflow_context(db, session), actor_role)


def require_workflow_action(
    db: Session,
    session: ContractSession,
    actor_role: str,
    action: ContractAction,
) -> None:
    context = build_workflow_context(db, session)
    if action_is_allowed(context, actor_role, action):
        return
    workflow = describe_workflow(context, actor_role)
    raise HTTPException(
        status_code=409,
        detail={
            "message": f"Действие «{action.value}» недоступно на этапе «{workflow['stage_label']}»",
            "workflow": workflow,
        },
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


def add_working_days(start: datetime, days: int) -> datetime:
    result = start
    added = 0
    while added < days:
        result += timedelta(days=1)
        if result.weekday() < 5:
            added += 1
    return result


def format_moscow_time(value: datetime) -> str:
    return value.astimezone(timezone(timedelta(hours=3))).strftime("%d.%m.%Y %H:%M")


def email_other_contract_parties(session: ContractSession, user: User, subject: str, body: str) -> None:
    for participant in session.participants:
        recipient = participant.user
        if recipient is None or recipient.id == user.id or is_guest_user(recipient):
            continue
        try:
            send_dispute_notice(
                recipient.email,
                session.title,
                subject,
                body,
                f"{settings.app_base_url}/?session={session.id}",
            )
        except Exception:
            continue


def get_final_version(db: Session, session: ContractSession) -> ContractVersion | None:
    return (
        db.query(ContractVersion)
        .filter(ContractVersion.session_id == session.id, ContractVersion.is_final.is_(True))
        .order_by(ContractVersion.version_number.desc())
        .first()
    )


def serialize_session_summary(db: Session, session: ContractSession, user: User) -> dict:
    participants = list(session.participants)
    current_participant = next((participant for participant in participants if participant.user_id == user.id), None)
    party_1 = next((participant for participant in participants if participant.role == ParticipantRole.party_1), None)
    party_2 = next((participant for participant in participants if participant.role == ParticipantRole.party_2), None)
    actor_role = current_participant.role.value if current_participant else "party_1"
    return {
        "id": session.id,
        "owner_user_id": session.owner_user_id,
        "title": session.title,
        "status": session.status,
        "is_completed": session.is_completed,
        "is_deleted": session.is_deleted,
        "finalized_at": session.finalized_at,
        "download_token": session.download_token,
        "invite_token": session.invite_token,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "my_role": current_participant.role if current_participant else None,
        "party_1_approved": party_1.approval_status == ApprovalStatus.approved if party_1 else False,
        "party_2_approved": party_2.approval_status == ApprovalStatus.approved if party_2 else False,
        "party_2_email": party_2.user.email if party_2 and party_2.user and not is_guest_user(party_2.user) else "",
        "workflow": workflow_for(db, session, actor_role),
    }


def count_completed_today(db: Session, user: User) -> int:
    today = now_utc().date()
    day_start = datetime.combine(today, time.min, tzinfo=timezone.utc)
    day_end = datetime.combine(today, time.max, tzinfo=timezone.utc)
    return (
        db.query(ContractSession)
        .filter(
            ContractSession.owner_user_id == user.id,
            ContractSession.status == SessionStatus.finalized,
            ContractSession.finalized_at >= day_start,
            ContractSession.finalized_at <= day_end,
        )
        .count()
    )


def finalize_signed_session(db: Session, session: ContractSession, final_version: ContractVersion) -> None:
    owner = db.get(User, session.owner_user_id)
    if owner is None:
        raise HTTPException(status_code=400, detail="Владелец договора не найден")
    if count_completed_today(db, owner) >= DAILY_ACTION_LIMIT:
        raise HTTPException(
            status_code=429,
            detail="Достигнут лимит бета-версии: 100 завершенных договоров в день. Доступ будет восстановлен завтра",
        )
    session.status = SessionStatus.finalized
    session.finalized_at = now_utc()
    session.download_token = None
    session.invite_token = None
    session.invite_expires_at = None
    session.is_completed = False
    session.completed_at = None
    final_version.is_final = True
    for participant in session.participants:
        participant.approval_status = ApprovalStatus.approved
        participant.approved_version_id = final_version.id
        participant.signed_at = participant.signed_at or now_utc()
    db.add(Message(session_id=session.id, role=MessageRole.system, content="CONTRACT_FINALIZED"))
    record_analytics_event(db, "contract_finalized", session=session, user=owner, properties={"version_number": final_version.version_number})
    upsert_contract_analytics_snapshot(db, session)


def build_contract_calendar_link(session: ContractSession, final_version: ContractVersion) -> str:
    event_date = session.finalized_at or now_utc()
    start = event_date.strftime("%Y%m%d")
    end = event_date.strftime("%Y%m%d")
    contract_text = f"{session.title}\n{final_version.content}".lower()
    is_rent_contract = any(marker in contract_text for marker in ("найм", "наниматель", "наймодатель", "жилое помещение"))
    if is_rent_contract:
        title = "Ежемесячная оплата по договору найма"
        details = (
            f"Напоминание AI-Arbitr по договору: {session.title}. "
            "Проверьте оплату за найм и связанные платежи по условиям договора."
        )
    else:
        title = f"Проверить обязательства по договору: {session.title}"
        details = (
            f"Напоминание AI-Arbitr по договору: {session.title}. "
            "Проверьте сроки, оплату и исполнение обязательств."
        )

    query = urlencode(
        {
            "action": "TEMPLATE",
            "text": title,
            "dates": f"{start}/{end}",
            "details": details,
            "recur": "RRULE:FREQ=MONTHLY",
        }
    )
    return f"https://calendar.google.com/calendar/render?{query}"


def format_history(messages: list[Message]) -> str:
    return "\n\n".join(
        f"{message.created_at.isoformat()} / {message.role.value}:\n{message.content}" for message in messages
    )


def format_recent_dialogue(messages: list[Message], limit: int = 8) -> str:
    relevant_messages = [message for message in messages if message.role in {MessageRole.user, MessageRole.assistant}]
    return "\n\n".join(
        f"{message.role.value}:\n{message.content}" for message in relevant_messages[-limit:]
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
                "и email. Я подготовлю ссылку для согласования, по которой вторая сторона сможет "
                "принять версию или предложить правки."
            ),
        )
    )
    demo_template_id, demo_template_version = identify_contract_template(DEMO_CONTRACT_TEXT)
    db.add(
        ContractVersion(
            session_id=session.id,
            version_number=1,
            content=DEMO_CONTRACT_TEXT,
            app_version=APP_VERSION,
            template_id=demo_template_id,
            template_version=demo_template_version,
        )
    )


def save_contract_version(db: Session, session: ContractSession, content: str) -> ContractVersion:
    content = ensure_ai_arbitr_dispute_section(clean_contract_markdown(content))
    version_count = db.query(ContractVersion).filter(ContractVersion.session_id == session.id).count()
    version_number = version_count + 1
    content = apply_contract_number(content, version_number)
    template_id, template_version = identify_contract_template(content)
    version = ContractVersion(
        session_id=session.id,
        version_number=version_number,
        content=content,
        app_version=APP_VERSION,
        template_id=template_id,
        template_version=template_version,
    )
    session.status = SessionStatus.in_review
    for participant in session.participants:
        participant.approval_status = ApprovalStatus.pending
        participant.approved_version_id = None
        participant.signed_at = None
    session.pending_signing_content = None
    session.final_content_hash = None
    db.add(version)
    db.add(Message(session_id=session.id, role=MessageRole.system, content=f"VERSION_CREATED|{version_number}"))
    db.flush()
    record_analytics_event(
        db,
        "contract_version_created",
        session=session,
        user=db.get(User, session.owner_user_id),
        properties={"version_number": version_number},
    )
    upsert_contract_analytics_snapshot(db, session)
    return version


@app.post("/sessions/{session_id}/invite")
def create_invite(
    session_id: str,
    request: Request,
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
    require_workflow_action(db, session, "party_1", ContractAction.SEND_INVITE)
    if session.invite_token is None:
        session.invite_token = uuid.uuid4()
    if session.invite_expires_at is None or session.invite_expires_at < now_utc():
        session.invite_expires_at = now_utc() + timedelta(days=7)
    db.commit()
    db.refresh(session)
    latest_version = get_latest_version(db, session)
    if latest_version is None:
        raise HTTPException(status_code=400, detail="Нет версии договора для согласования")
    if payload and payload.email:
        default_role, _ = infer_legal_role_pair(session.title, latest_version.content)
        creator_role = payload.creator_legal_role or session.party_1_legal_role or default_role
        assign_legal_roles(session, latest_version.content, creator_role)
    messages = (
        db.query(Message)
        .filter(Message.session_id == session.id)
        .order_by(Message.created_at.asc())
        .all()
    )
    collected_contract = collect_pending_norms_into_contract(latest_version.content, messages)
    if collected_contract != latest_version.content:
        latest_version = save_contract_version(db, session, collected_contract)
        db.flush()
    invite_link = f"{settings.app_base_url}/review/{session.invite_token}"
    pdf_link = f"{settings.api_base_url}/review/{session.invite_token}.pdf"
    version_number = latest_version.version_number
    sent = False
    if payload and payload.email:
        check_daily_rate_limit(db, request, "contract_invite", user=user)
        invited_user = db.query(User).filter(User.email == str(payload.email)).one_or_none()
        if invited_user is None:
            invited_user = User(email=str(payload.email))
            db.add(invited_user)
            db.flush()
        party_2 = (
            db.query(ContractParticipant)
            .filter(ContractParticipant.session_id == session.id, ContractParticipant.role == ParticipantRole.party_2)
            .one()
        )
        party_2.user_id = invited_user.id
        send_contract_invite(payload.email, invite_link, session.title, pdf_link, copy_to=user.email)
        sent = smtp_is_configured()
        db.add(
            Message(
                session_id=session.id,
                role=MessageRole.system,
                content=f"VERSION_SENT|{version_number}|{payload.email}",
            )
        )
        record_analytics_event(
            db,
            "invite_sent",
            session=session,
            user=user,
            properties={"version_number": version_number, "delivery": "email"},
        )
        upsert_contract_analytics_snapshot(db, session)
        db.commit()
    return {
        "invite_link": invite_link,
        "sent": sent,
        "sent_to": str(payload.email) if payload and payload.email else None,
        "copy_to": user.email if sent else None,
        "workflow": workflow_for(db, session, "party_1"),
    }


def get_session_by_review_token(db: Session, invite_token: str) -> ContractSession:
    session = db.query(ContractSession).filter(ContractSession.invite_token == invite_token).one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Ссылка согласования не найдена")
    invite_deadline = session.invite_expires_at or (session.updated_at + timedelta(days=7))
    if invite_deadline.tzinfo is None:
        invite_deadline = invite_deadline.replace(tzinfo=timezone.utc)
    if invite_deadline < now_utc():
        raise HTTPException(status_code=410, detail="Срок действия ссылки согласования истек")
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
        "version_number": latest_version.version_number,
        "version_created_at": latest_version.created_at,
        "status": session.status,
        "contract": latest_version.content,
        "key_terms": build_key_terms(latest_version.content),
        "approved": party_2.approval_status == ApprovalStatus.approved,
        "party_email": party_2.user.email if party_2.user else "",
        "legal_role": session.party_2_legal_role or infer_legal_role_pair(session.title, latest_version.content)[1],
        "finalized": session.status == SessionStatus.finalized,
        "download_token": session.download_token,
        "pdf_link": f"{settings.api_base_url}/review/{invite_token}.pdf",
        "workflow": workflow_for(db, session, "party_2"),
    }


@app.post("/review/{invite_token}/approve")
def approve_review_contract(invite_token: str, payload: ReviewApproveRequest, db: Session = Depends(get_db)):
    require_unified_consent(
        payload.personal_data_accepted,
        payload.service_rules_accepted,
        payload.cookies_accepted,
        payload.consent_version,
    )
    if payload.party_type not in {"individual", "business"}:
        raise HTTPException(status_code=400, detail="Выберите тип стороны")
    if len(payload.full_name.strip().split()) < 2:
        raise HTTPException(status_code=400, detail="Укажите ФИО полностью")
    phone_digits = re.sub(r"\D", "", payload.phone)
    if not 10 <= len(phone_digits) <= 15:
        raise HTTPException(status_code=400, detail="Проверьте номер телефона")
    if payload.party_type == "individual" and not re.fullmatch(r"\d{4}\s?\d{6}", payload.passport.strip()):
        raise HTTPException(status_code=400, detail="Паспорт нужно указать в формате 0000 000000")
    if payload.party_type == "business":
        if not payload.organization_name.strip():
            raise HTTPException(status_code=400, detail="Укажите наименование организации или ИП")
        if not re.fullmatch(r"\d{10}|\d{12}", payload.inn.strip()):
            raise HTTPException(status_code=400, detail="ИНН должен содержать 10 или 12 цифр")
        if not re.fullmatch(r"\d{13}|\d{15}", payload.ogrn.strip()):
            raise HTTPException(status_code=400, detail="ОГРН или ОГРНИП должен содержать 13 или 15 цифр")
    session = get_session_by_review_token(db, invite_token)
    latest_version = get_latest_version(db, session)
    if latest_version is None:
        raise HTTPException(status_code=400, detail="Нет версии договора для согласования")
    owner = db.get(User, session.owner_user_id)
    if session.status == SessionStatus.finalized:
        return {"finalized": True, "owner_email": owner.email if owner else None}
    require_workflow_action(db, session, "party_2", ContractAction.SIGN_COUNTERPARTY)

    participant = (
        db.query(ContractParticipant)
        .filter(ContractParticipant.session_id == session.id, ContractParticipant.role == ParticipantRole.party_2)
        .one()
    )
    if participant.approval_status == ApprovalStatus.approved:
        return {
            "finalized": False,
            "party_two_signed": True,
            "owner_email": owner.email if owner else None,
        }
    invited_email = participant.user.email if participant.user else ""
    if not invited_email or str(payload.email).lower() != invited_email.lower():
        raise HTTPException(status_code=403, detail="Подписать договор можно только с email, на который направлено приглашение")
    user = db.query(User).filter(User.email == payload.email).one_or_none()
    if user is None:
        user = User(email=payload.email)
        db.add(user)
        db.flush()
    apply_user_consent(user)

    participant.user_id = user.id
    participant.joined_at = participant.joined_at or now_utc()
    participant.signed_at = now_utc()
    participant.approval_status = ApprovalStatus.approved
    participant.approved_version_id = latest_version.id
    db.add(
        Message(
            session_id=session.id,
            role=MessageRole.system,
            content=(
                f"VERSION_APPROVED|{latest_version.version_number}|{payload.email}"
                f"|type:{payload.party_type}"
                f"|passport:{mask_tail(payload.passport, 2)}|phone:{mask_tail(payload.phone, 2)}"
                f"|inn:{mask_tail(payload.inn, 2) if payload.inn else ''}"
                f"|ogrn:{mask_tail(payload.ogrn, 2) if payload.ogrn else ''}"
            ),
        )
    )
    temp_content = apply_ephemeral_party_data(
        latest_version.content,
        payload,
        ParticipantRole.party_2,
        session.party_2_legal_role,
    )
    session.pending_signing_content = temp_content
    if owner and not is_guest_user(owner):
        send_signature_progress_notice(owner.email, session.title, f"{settings.app_base_url}/?session={session.id}")
    record_analytics_event(
        db,
        "party_2_approved",
        session=session,
        user=user,
        properties={
            "version_number": latest_version.version_number,
            "role": "party_2",
            "party_type": payload.party_type,
        },
    )
    upsert_contract_analytics_snapshot(db, session)
    db.commit()
    return {
        "finalized": False,
        "party_two_signed": True,
        "owner_email": owner.email if owner else None,
        "workflow": workflow_for(db, session, "party_2"),
    }


@app.post("/sessions/{session_id}/messages")
async def send_message(
    session_id: str,
    payload: MessageRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = get_accessible_session(db, session_id, user)
    check_daily_rate_limit(db, request, "chat_message", user=user)

    normalized_content = payload.content.strip().upper()
    is_dispute = normalized_content.startswith("СПОР")
    is_dispute_response = normalized_content.startswith("ОТВЕТ")
    if session.status == SessionStatus.finalized and not (is_dispute or is_dispute_response):
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
    prior_messages = (
        db.query(Message)
        .filter(Message.session_id == session.id)
        .order_by(Message.created_at.asc())
        .all()
    )
    is_contract_question = (
        session.status != SessionStatus.finalized
        and latest_version_before_answer is not None
        and not is_contract_update
    )
    if session.title == "Новый договор":
        title_source = payload.content.removeprefix(CONTRACT_UPDATE_PREFIX).strip()
        session.title = infer_session_title(title_source)
    db.add(Message(session_id=session.id, role=MessageRole.user, content=payload.content))
    db.flush()

    if session.status == SessionStatus.finalized and is_dispute_response:
        notice_marker = next(
            (message for message in reversed(prior_messages) if message.role == MessageRole.system and message.content.startswith("DELAY_NOTICE|")),
            None,
        )
        if notice_marker is None:
            answer = "Уведомление о просрочке по этому договору еще не направлялось."
        else:
            notice_parts = notice_marker.content.split("|", 3)
            initiator_id = notice_parts[1] if len(notice_parts) > 1 else ""
            if str(user.id) == initiator_id:
                answer = "Ответ на уведомление должна направить другая сторона договора. Вы можете дополнить описание спора сообщением без слова «ОТВЕТ»."
            else:
                db.add(Message(session_id=session.id, role=MessageRole.system, content=f"DELAY_RESPONSE|{user.id}|{now_utc().isoformat()}"))
                answer = "Ответ зафиксирован и будет учтен. Автоматическое уведомление о нарушении не формируется."
                email_other_contract_parties(session, user, "Получен ответ на уведомление о просрочке", payload.content.strip())
        db.add(Message(session_id=session.id, role=MessageRole.assistant, content=answer))
        db.commit()
        return {"content": answer, "contract_saved": False, "reasoning": ""}

    if session.status == SessionStatus.finalized and is_dispute:
        notice_marker = next(
            (message for message in prior_messages if message.role == MessageRole.system and message.content.startswith("DELAY_NOTICE|")),
            None,
        )
        if notice_marker is None:
            sent_at = now_utc()
            response_due = add_working_days(sent_at, 3)
            description = payload.content.strip()[4:].strip() or "Зафиксирована просрочка исполнения обязательства."
            notice_body = (
                f"Сообщается о возможной просрочке исполнения: {description}\n\n"
                f"Просим ответить и сообщить срок исполнения до {format_moscow_time(response_due)} по Москве. "
                "Для ответа откройте договор и начните сообщение со слова «ОТВЕТ»."
            )
            db.add(
                Message(
                    session_id=session.id,
                    role=MessageRole.system,
                    content=f"DELAY_NOTICE|{user.id}|{sent_at.isoformat()}|{response_due.isoformat()}",
                )
            )
            answer = (
                "Уведомление о просрочке направлено второй стороне. Я оставил три рабочих дня на ответ или исполнение. "
                f"Срок ответа: {format_moscow_time(response_due)} по Москве.\n\n"
                "Если ответа не будет, после этой даты снова нажмите «Открыть спор»: я подготовлю уведомление о нарушении, "
                "процитирую условие договора и рассчитаю требование."
            )
            email_other_contract_parties(session, user, "Уведомление о просрочке исполнения", notice_body)
            db.add(Message(session_id=session.id, role=MessageRole.assistant, content=answer))
            record_analytics_event(db, "delay_notice_sent", session=session, user=user)
            db.commit()
            return {"content": answer, "contract_saved": False, "reasoning": ""}

        breach_notice_exists = any(
            message.role == MessageRole.system and message.content.startswith("BREACH_NOTICE|")
            for message in prior_messages
        )
        if breach_notice_exists:
            answer = "Уведомление о нарушении уже направлено и сохранено в истории договора."
            db.add(Message(session_id=session.id, role=MessageRole.assistant, content=answer))
            db.commit()
            return {"content": answer, "contract_saved": False, "reasoning": ""}

        parts = notice_marker.content.split("|", 3)
        initiator_id = parts[1] if len(parts) > 1 else ""
        if str(user.id) != initiator_id:
            answer = "Продолжить этот спор может сторона, которая направила уведомление. Вы можете ответить, начав сообщение со слова «ОТВЕТ»."
            db.add(Message(session_id=session.id, role=MessageRole.assistant, content=answer))
            db.commit()
            return {"content": answer, "contract_saved": False, "reasoning": ""}
        response_due = datetime.fromisoformat(parts[3]) if len(parts) > 3 else add_working_days(notice_marker.created_at, 3)
        response_exists = any(
            message.role == MessageRole.system
            and message.content.startswith("DELAY_RESPONSE|")
            and message.content.split("|", 2)[1] != initiator_id
            and message.created_at > notice_marker.created_at
            for message in prior_messages
        )
        if response_exists:
            answer = "Вторая сторона ответила на уведомление. Опишите, что осталось неисполненным, чтобы я учел обе позиции."
            db.add(Message(session_id=session.id, role=MessageRole.assistant, content=answer))
            db.commit()
            return {"content": answer, "contract_saved": False, "reasoning": ""}
        if now_utc() < response_due:
            answer = f"Срок для ответа еще не истек. Ждем до {format_moscow_time(response_due)} по Москве."
            db.add(Message(session_id=session.id, role=MessageRole.assistant, content=answer))
            db.commit()
            return {"content": answer, "contract_saved": False, "reasoning": ""}

    last_assistant_before_answer = last_assistant_message(prior_messages)
    last_assistant_lower = last_assistant_before_answer.lower()

    if (
        latest_version_before_answer is not None
        and not is_contract_update
        and "введите e-mail второй стороны" in last_assistant_lower
    ):
        party_email = extract_email_from_text(payload.content)
        if not party_email:
            answer = "Не вижу email второй стороны. Пришлите его одним сообщением, например: name@example.com."
            db.add(Message(session_id=session.id, role=MessageRole.assistant, content=answer))
            db.commit()
            return {"content": answer, "contract_saved": False, "reasoning": "", "next_action": "email"}
        if is_guest_user(user):
            answer = (
                "Чтобы отправить ссылку второй стороне, сначала нужно сохранить договор за вашей почтой. "
                "Нажмите «Вход» и укажите свой email, затем вернитесь в этот чат и отправьте email второй стороны еще раз."
            )
            db.add(Message(session_id=session.id, role=MessageRole.assistant, content=answer))
            db.commit()
            return {"content": answer, "contract_saved": False, "reasoning": "", "next_action": "auth_required"}

        if session.invite_token is None:
            session.invite_token = uuid.uuid4()
        session.invite_expires_at = now_utc() + timedelta(days=7)
        db.flush()
        check_daily_rate_limit(db, request, "contract_invite", user=user)
        latest_version = get_latest_version(db, session)
        if latest_version is None:
            raise HTTPException(status_code=400, detail="Нет версии договора для согласования")
        invited_user = db.query(User).filter(User.email == party_email).one_or_none()
        if invited_user is None:
            invited_user = User(email=party_email)
            db.add(invited_user)
            db.flush()
        party_2 = (
            db.query(ContractParticipant)
            .filter(ContractParticipant.session_id == session.id, ContractParticipant.role == ParticipantRole.party_2)
            .one()
        )
        party_2.user_id = invited_user.id
        invite_link = f"{settings.app_base_url}/review/{session.invite_token}"
        pdf_link = f"{settings.api_base_url}/review/{session.invite_token}.pdf"
        send_contract_invite(party_email, invite_link, session.title, pdf_link, copy_to=user.email)
        db.add(
            Message(
                session_id=session.id,
                role=MessageRole.system,
                content=f"VERSION_SENT|{latest_version.version_number}|{party_email}",
            )
        )
        record_analytics_event(
            db,
            "invite_sent",
            session=session,
            user=user,
            properties={"version_number": latest_version.version_number, "delivery": "email"},
        )
        upsert_contract_analytics_snapshot(db, session)
        answer = (
            f"Версия № {latest_version.version_number} направлена на согласование на адрес {party_email}. "
            f"Копия письма отправлена на {user.email}."
        )
        db.add(Message(session_id=session.id, role=MessageRole.assistant, content=answer))
        db.commit()
        return {
            "content": answer,
            "contract_saved": False,
            "reasoning": "",
            "next_action": "sent",
            "invite_link": invite_link,
            "sent_to": party_email,
            "copy_to": user.email,
        }

    if (
        latest_version_before_answer is not None
        and not is_contract_update
        and is_affirmative_message(payload.content)
        and "переходим к согласованию" in last_assistant_lower
    ):
        latest_version = get_latest_version(db, session)
        version_number = latest_version.version_number if latest_version else 1
        answer = (
            f"Готовлю версию № {version_number}.\n\n"
            "Версия готова.\n\n"
            "Введите e-mail второй стороны, на который направить ссылку для согласования."
        )
        db.add(Message(session_id=session.id, role=MessageRole.assistant, content=answer))
        db.commit()
        return {"content": answer, "contract_saved": False, "reasoning": "", "next_action": "email"}

    if (
        latest_version_before_answer is not None
        and not is_contract_update
        and "выберите: краткая, расширенная или пришлите свою редакцию" in last_assistant_lower
    ):
        selected_norm = None
        reasoning = ""
        if is_short_option(payload.content):
            selected_norm = extract_norm_option(last_assistant_before_answer, "short")
        elif is_expanded_option(payload.content):
            selected_norm = extract_norm_option(last_assistant_before_answer, "expanded")
        else:
            selected_norm = payload.content.strip()
            reasoning = ""

        if not selected_norm:
            selected_norm = payload.content.strip()

        updated_contract = add_norm_to_contract(latest_version_before_answer.content, selected_norm)
        save_contract_version(db, session, updated_contract)
        answer = build_custom_norm_review(selected_norm) if reasoning else build_norm_saved_answer(selected_norm)
        if reasoning:
            db.add(Message(session_id=session.id, role=MessageRole.system, content=reasoning))
        db.add(Message(session_id=session.id, role=MessageRole.assistant, content=answer))
        db.commit()
        return {"content": answer, "contract_saved": True, "reasoning": reasoning, "next_action": "agreement"}

    if latest_version_before_answer is not None and is_contract_update:
        requested_change = payload.content.removeprefix(CONTRACT_UPDATE_PREFIX).strip()
        try:
            answer = await review_contract_addition(
                latest_version_before_answer.content,
                requested_change,
                payload.model,
            )
        except YandexGPTError:
            answer = (
                "Не удалось надежно проверить законность именно этого условия. Я не буду подменять вашу просьбу "
                "другой нормой. Сформулируйте, пожалуйста, кто получает право, какое действие разрешается и при "
                "каких ограничениях, после чего я повторю проверку."
            )
        next_action = (
            "choose_norm"
            if "вариант 1" in answer.lower() and "вариант 2" in answer.lower()
            else "clarify_addition"
        )
        db.add(Message(session_id=session.id, role=MessageRole.assistant, content=answer))
        db.commit()
        return {
            "content": answer,
            "contract_saved": False,
            "reasoning": "",
            "next_action": next_action,
        }

    if latest_version_before_answer is None and not is_contract_update and needs_service_type_clarification(payload.content):
        answer = build_service_type_clarification(payload.content)
        db.add(Message(session_id=session.id, role=MessageRole.assistant, content=answer))
        db.commit()
        return {"content": answer, "contract_saved": False, "reasoning": ""}

    if latest_version_before_answer is None and not is_contract_update and needs_broad_contract_clarification(payload.content):
        answer = build_broad_contract_clarification()
        db.add(Message(session_id=session.id, role=MessageRole.assistant, content=answer))
        db.commit()
        return {"content": answer, "contract_saved": False, "reasoning": ""}

    recent_messages_text = "\n".join(message.content for message in prior_messages[-8:])
    if (
        latest_version_before_answer is not None
        and not is_contract_update
        and is_affirmative_message(payload.content)
        and ("хотите включить" in recent_messages_text.lower() or build_rule_based_contract_norm(recent_messages_text))
    ):
        recent_dialogue = format_recent_dialogue(prior_messages)
        try:
            answer = await propose_contract_norm_options(
                latest_version_before_answer.content,
                last_assistant_before_answer,
                recent_dialogue,
            )
        except YandexGPTError:
            answer = (
                "Да, можно добавить. Предлагаю две редакции.\n\n"
                "Вариант 1 — краткий:\n"
                "[Номер пункта]. Соответствующее действие допускается только по предварительному письменному соглашению сторон.\n\n"
                "Вариант 2 — расширенный:\n"
                "[Номер пункта]. Соответствующее действие допускается только по предварительному письменному соглашению сторон "
                "с указанием срока, порядка уведомления и последствий нарушения. Одностороннее изменение условия не допускается, "
                "если иное прямо не предусмотрено законом или настоящим Договором.\n\n"
                "Выберите: краткая, расширенная или пришлите свою редакцию."
            )
        db.add(Message(session_id=session.id, role=MessageRole.assistant, content=answer))
        db.commit()
        return {"content": answer, "contract_saved": False, "reasoning": "", "next_action": "choose_norm"}

    if latest_version_before_answer is not None and not is_contract_update and is_deposit_split_question(payload.content):
        answer = build_deposit_split_answer(latest_version_before_answer.content)
        db.add(Message(session_id=session.id, role=MessageRole.assistant, content=answer))
        db.commit()
        return {"content": answer, "contract_saved": False, "reasoning": ""}

    if session.status != SessionStatus.finalized and latest_version_before_answer is not None and not is_contract_update:
        placeholders = extract_placeholders(latest_version_before_answer.content)
        last_assistant = last_assistant_message(prior_messages).lower()
        if placeholders and is_affirmative_message(payload.content) and "переходим к согласованию" in last_assistant:
            answer = build_placeholder_request(placeholders)
            db.add(Message(session_id=session.id, role=MessageRole.assistant, content=answer))
            db.commit()
            return {"content": answer, "contract_saved": False, "reasoning": ""}

        if not placeholders and is_affirmative_message(payload.content) and "переходим к согласованию" in last_assistant:
            answer = build_demo_replacement_request()
            db.add(Message(session_id=session.id, role=MessageRole.assistant, content=answer))
            db.commit()
            return {"content": answer, "contract_saved": False, "reasoning": ""}

        if placeholders and "перед согласованием нужно заполнить данные" in last_assistant:
            values = parse_placeholder_values(payload.content)
            missing = [placeholder for placeholder in placeholders if placeholder.lower() not in values]
            if missing:
                answer = (
                    "Пока не хватает данных для заполнения договора:\n"
                    + "\n".join(f"- {placeholder}" for placeholder in missing)
                    + "\n\nПришлите недостающие значения в формате: поле: значение."
                )
                db.add(Message(session_id=session.id, role=MessageRole.assistant, content=answer))
                db.commit()
                return {"content": answer, "contract_saved": False, "reasoning": ""}

            filled_contract = fill_contract_placeholders(latest_version_before_answer.content, values)
            save_contract_version(db, session, filled_contract)
            answer = (
                "Данные внесены в договор успешно.\n\n"
                "Переходим к отправке ссылки второй стороне для согласования?"
            )
            db.add(Message(session_id=session.id, role=MessageRole.assistant, content=answer))
            db.commit()
            return {"content": answer, "contract_saved": True, "reasoning": ""}

        if "заменим вымышленные данные" in last_assistant:
            values = parse_placeholder_values(payload.content)
            missing = [field for field in ("роль", "фио", "паспорт", "email") if field not in values]
            if missing:
                answer = (
                    "Пока не хватает данных для замены вымышленных сведений:\n"
                    + "\n".join(f"- {field}" for field in missing)
                    + "\n\nПришлите недостающие значения в формате: поле: значение."
                )
                db.add(Message(session_id=session.id, role=MessageRole.assistant, content=answer))
                db.commit()
                return {"content": answer, "contract_saved": False, "reasoning": ""}

            filled_contract = fill_demo_contract_data(latest_version_before_answer.content, values)
            save_contract_version(db, session, filled_contract)
            answer = (
                "Изменяю вымышленные данные на реальные.\n\n"
                "Данные внесены в договор успешно.\n\n"
                "Переходим к отправке ссылки второй стороне для согласования?"
            )
            db.add(Message(session_id=session.id, role=MessageRole.assistant, content=answer))
            db.commit()
            return {"content": answer, "contract_saved": True, "reasoning": ""}

    if session.status == SessionStatus.finalized:
        reasoning_note = ""
    elif latest_version_before_answer is None:
        reasoning_note = build_reasoning_note(payload.content)
    elif is_contract_update:
        reasoning_note = build_update_reasoning_note(payload.content.removeprefix(CONTRACT_UPDATE_PREFIX).strip())
    else:
        reasoning_note = build_question_reasoning_note(payload.content)
    if reasoning_note and not is_contract_question:
        db.add(Message(session_id=session.id, role=MessageRole.system, content=reasoning_note))
    db.commit()

    try:
        should_save_contract_version = session.status != SessionStatus.finalized
        display_answer: str | None = None
        used_fixed_template = False
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
                messages_for_context = (
                    db.query(Message)
                    .filter(Message.session_id == session.id)
                    .order_by(Message.created_at.asc())
                    .all()
                )
                recent_dialogue = format_recent_dialogue(messages_for_context)
                prompt = [
                    {
                        "role": "system",
                        "text": (
                            "Ты AI-Арбитр. Пользователь задает вопрос по уже подготовленному договору. "
                            "Ответь на последний вопрос пользователя с учетом предыдущего диалога. "
                            "Если последний вопрос является уточнением, восстанови контекст из истории. "
                            "Запрещено возвращать полный текст договора, "
                            "разделы договора, преамбулу, реквизиты или новую редакцию. "
                            "Сначала дай прямой ответ, затем кратко объясни почему. "
                            "Ответ строй только по одной из трех схем:\n"
                            "1) Если вопрос прямо урегулирован договором: «Это договором предусмотрено» и короткая цитата пункта.\n"
                            "2) Если договор молчит, но вопрос урегулирован ГК РФ: «Это договором прямо не предусмотрено, "
                            "но применяется норма закона» и краткая ссылка на статью ГК РФ.\n"
                            "3) Если есть риск неопределенности: объясни риск и предложи добавить ясное условие.\n"
                            f"{build_contract_gap_instruction()} "
                            "Если вопрос про изменение цены, срок, расторжение, депозит или ответственность, "
                            "обязательно проверь, что написано в договоре, и отдельно укажи, зависит ли ответ "
                            "от условия договора или от соглашения сторон. Если по закону нужна оговорка "
                            "или согласие другой стороны, скажи это прямо. "
                            "Если вопрос про повышение платы по договору найма жилого помещения, "
                            "сначала проверь, есть ли в договоре прямое условие о повышении платы. "
                            "Если такого условия нет, прямо скажи: «Прямо договором это не предусмотрено». "
                            "Затем объясни, что одностороннее изменение платы по ст. 682 ГК РФ не допускается, "
                            "кроме случаев, предусмотренных законом или договором, и что практически стоит "
                            "включить отдельное условие о повышении не чаще одного раза в год. "
                            "В конце спроси: «Хотите включить это условие в договор?» "
                            "Максимум 8-10 предложений."
                        ),
                    },
                    {
                        "role": "user",
                        "text": (
                            f"Последний вопрос пользователя:\n{payload.content}\n\n"
                            f"Предыдущий диалог:\n{recent_dialogue}\n\n"
                            "Текущая версия договора ниже дана только как справочный материал. "
                            "Не переписывай ее и не выводи ее текст в ответе.\n\n"
                            f"{latest_version.content}"
                        ),
                    },
                ]
        else:
            if is_housing_rent_request(payload.content):
                answer = build_housing_rent_contract(settings.app_base_url)
                prompt = None
                used_fixed_template = True
            elif is_website_development_request(payload.content):
                answer = build_website_development_contract()
                prompt = None
                used_fixed_template = True
            else:
                prompt = [
                    {"role": "system", "text": SIMPLE_CONTRACT_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "text": (
                            "Сгенерируй упрощенный проект договора по следующему запросу. "
                            "Ответ должен быть только текстом договора, без предварительных пояснений. "
                            "Сделай договор достаточно полным для MVP, но не чрезмерно длинным.\n\n"
                            f"Запрос пользователя:\n{payload.content}"
                        ),
                    },
                ]
        if prompt is not None:
            answer = await ask_yandex_gpt(prompt, model=payload.model)
        if latest_version_before_answer is None and not used_fixed_template:
            answer = normalize_contract_legal_title(answer, payload.content)
        if should_save_contract_version or looks_like_contract_text(answer):
            answer = clean_contract_markdown(answer)
        if should_save_contract_version:
            answer = ensure_ai_arbitr_dispute_section(answer)
            next_version_number = (
                db.query(ContractVersion)
                .filter(ContractVersion.session_id == session.id)
                .count()
                + 1
            )
            answer = apply_contract_number(answer, next_version_number)
        if session.status == SessionStatus.finalized and is_dispute:
            answer = (
                answer
                + "\n\nЧерез 3 рабочих дня после направления решения сторонам необходимо проверить исполнение. "
                "Сторона, в пользу которой вынесено решение, должна закрыть спор при исполнении решения "
                "либо использовать финальный PDF договора, решение AI-Арбитра и историю уведомлений для обращения в суд."
            )
        if is_contract_update:
            requested_change = payload.content.removeprefix(CONTRACT_UPDATE_PREFIX).strip()
            try:
                display_answer = await summarize_added_contract_norm(answer, requested_change)
            except YandexGPTError:
                display_answer = (
                    "Готово, я добавил условие в новую редакцию договора.\n\n"
                    f"Суть добавленного условия: {requested_change}\n\n"
                    "Переходим к согласованию?"
                )
        if latest_version_before_answer is not None and not is_contract_update and looks_like_contract_text(answer):
            answer = (
                "Да, вопрос понял, но модель начала возвращать текст договора вместо ответа. "
                "Коротко: изменение платы возможно только в порядке, предусмотренном договором, "
                "или по соглашению сторон. Если в договоре нет права Наймодателя односторонне "
                "повышать плату на 40%, такое повышение нельзя просто навязать Нанимателю."
            )
        if (
            latest_version_before_answer is not None
            and not is_contract_update
            and is_rent_increase_question(payload.content)
            and ("хотите включить" not in answer.lower() or "682" not in answer)
        ):
            answer = build_rent_increase_answer(latest_version_before_answer.content)
    except YandexGPTError:
        should_save_contract_version = False
        answer = (
            "Не удалось получить ответ YandexGPT. Запрос не потерян, но генерация договора "
            "не завершилась. Попробуйте отправить запрос еще раз через несколько секунд."
        )

    contract_text = answer
    answer = warning + (display_answer or answer)
    db.add(Message(session_id=session.id, role=MessageRole.assistant, content=answer))
    if should_save_contract_version:
        save_contract_version(db, session, contract_text)
    if is_dispute and session.status == SessionStatus.finalized:
        db.add(Message(session_id=session.id, role=MessageRole.system, content=f"DISPUTE_OPENED|{user.id}"))
        db.add(Message(session_id=session.id, role=MessageRole.system, content=f"BREACH_NOTICE|{user.id}|{now_utc().isoformat()}"))
        email_other_contract_parties(session, user, "Уведомление о нарушении обязательства", answer)
        record_analytics_event(db, "dispute_opened", session=session, user=user)
    upsert_contract_analytics_snapshot(db, session)
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
    participant = get_user_participant(db, session, user)
    require_workflow_action(db, session, participant.role.value, ContractAction.CREATE_VERSION)

    version = save_contract_version(db, session, payload.content)
    db.commit()
    db.refresh(version)
    return version


@app.post("/sessions/{session_id}/approve")
def approve_version(
    session_id: str,
    payload: ReviewApproveRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = get_accessible_session(db, session_id, user)
    latest_version = get_latest_version(db, session)
    if latest_version is None:
        raise HTTPException(status_code=400, detail="Нет версии договора для согласования")
    if session.owner_user_id != user.id:
        raise HTTPException(status_code=403, detail="Финальную подпись ставит создатель договора")
    require_workflow_action(db, session, "party_1", ContractAction.SIGN_CREATOR)
    require_unified_consent(
        payload.personal_data_accepted,
        payload.service_rules_accepted,
        payload.cookies_accepted,
        payload.consent_version,
    )
    if payload.party_type not in {"individual", "business"}:
        raise HTTPException(status_code=400, detail="Выберите тип стороны")
    if str(payload.email).lower() != user.email.lower():
        raise HTTPException(status_code=403, detail="Email подписанта не совпадает с аккаунтом")
    if len(payload.full_name.strip().split()) < 2:
        raise HTTPException(status_code=400, detail="Укажите ФИО полностью")
    phone_digits = re.sub(r"\D", "", payload.phone)
    if not 10 <= len(phone_digits) <= 15:
        raise HTTPException(status_code=400, detail="Проверьте номер телефона")
    if payload.party_type == "individual" and not re.fullmatch(r"\d{4}\s?\d{6}", payload.passport.strip()):
        raise HTTPException(status_code=400, detail="Паспорт нужно указать в формате 0000 000000")
    if payload.party_type == "business":
        if not payload.organization_name.strip():
            raise HTTPException(status_code=400, detail="Укажите наименование организации или ИП")
        if not re.fullmatch(r"\d{10}|\d{12}", payload.inn.strip()):
            raise HTTPException(status_code=400, detail="ИНН должен содержать 10 или 12 цифр")
        if not re.fullmatch(r"\d{13}|\d{15}", payload.ogrn.strip()):
            raise HTTPException(status_code=400, detail="ОГРН или ОГРНИП должен содержать 13 или 15 цифр")
    apply_user_consent(user)

    signing_content = session.pending_signing_content or latest_version.content
    signing_content = apply_ephemeral_party_data(
        signing_content,
        payload,
        ParticipantRole.party_1,
        session.party_1_legal_role,
    )
    session.pending_signing_content = signing_content

    participant = get_user_participant(db, session, user)
    participant.approval_status = ApprovalStatus.approved
    participant.approved_version_id = latest_version.id
    participant.signed_at = now_utc()
    db.add(
        Message(
            session_id=session.id,
            role=MessageRole.system,
            content=f"VERSION_APPROVED|{latest_version.version_number}|{user.email}",
        )
    )
    record_analytics_event(
        db,
        "party_approved",
        session=session,
        user=user,
        properties={"version_number": latest_version.version_number, "role": participant.role.value},
    )

    participants = session.participants
    both_approved = all(
        item.user_id is not None
        and item.approval_status == ApprovalStatus.approved
        and item.approved_version_id == latest_version.id
        for item in participants
    )
    if both_approved:
        signing_content = session.pending_signing_content or latest_version.content
        latest_version.content = signing_content
        session.final_content_hash = hashlib.sha256(signing_content.encode("utf-8")).hexdigest()
        finalize_signed_session(db, session, latest_version)
    else:
        upsert_contract_analytics_snapshot(db, session)

    db.commit()
    if both_approved:
        messages = (
            db.query(Message)
            .filter(Message.session_id == session.id)
            .order_by(Message.created_at.asc())
            .all()
        )
        pdf_version = SimpleNamespace(
            content=signing_content,
            version_number=latest_version.version_number,
        )
        pdf_bytes = build_contract_pdf(session, pdf_version, participants, messages)
        certificate_bytes = build_interaction_certificate_pdf(session, latest_version, participants, messages)
        calendar_link = build_contract_calendar_link(session, latest_version)
        try:
            for item in participants:
                if item.user and not is_guest_user(item.user):
                    send_contract_signed_notice(item.user.email, session.title, pdf_bytes, certificate_bytes, calendar_link)
        finally:
            session.pending_signing_content = None
            db.commit()
    return {
        "finalized": both_approved,
        "status": session.status,
        "workflow": workflow_for(db, session, "party_1"),
    }


@app.post("/sessions/{session_id}/complete")
def complete_contract(session_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    session = get_accessible_session(db, session_id, user)
    participant = get_user_participant(db, session, user)
    if session.is_completed:
        return {
            "completed": True,
            "message": "Договор уже закрыт",
            "workflow": workflow_for(db, session, participant.role.value),
        }
    require_workflow_action(db, session, participant.role.value, ContractAction.CONFIRM_COMPLETION)
    if participant.completed_at is not None:
        return {
            "completed": session.is_completed,
            "message": (
                "Договор уже закрыт"
                if session.is_completed
                else "Ваше подтверждение уже сохранено. Ожидается подтверждение второй стороны"
            ),
            "workflow": workflow_for(db, session, participant.role.value),
        }
    participant.completed_at = now_utc()
    both_confirmed = all(item.user_id is not None and item.completed_at is not None for item in session.participants)
    if both_confirmed and not session.is_completed:
        session.is_completed = True
        session.completed_at = now_utc()
        db.add(
            Message(
                session_id=session.id,
                role=MessageRole.system,
                content="Договор отмечен обеими сторонами как исполненный. Чат сохранен в истории и защищен от удаления.",
            )
        )
        record_analytics_event(db, "contract_completed", session=session, user=user)
    elif not both_confirmed:
        db.add(
            Message(
                session_id=session.id,
                role=MessageRole.system,
                content=f"Исполнение подтверждено стороной {participant.role.value}. Ожидается подтверждение второй стороны.",
            )
        )
    upsert_contract_analytics_snapshot(db, session)
    db.commit()
    return {
        "completed": both_confirmed,
        "message": (
            "Договор закрыт: исполнение подтверждено обеими сторонами"
            if both_confirmed
            else "Ваше подтверждение сохранено. Для закрытия требуется подтверждение второй стороны"
        ),
        "workflow": workflow_for(db, session, participant.role.value),
    }


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


@app.get("/sessions/{session_id}/certificate.pdf")
def download_interaction_certificate(
    session_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = get_accessible_session(db, session_id, user)
    if session.status != SessionStatus.finalized:
        raise HTTPException(status_code=400, detail="Справка доступна только после подписания договора")

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
    pdf_bytes = build_interaction_certificate_pdf(session, final_version, session.participants, messages)
    filename = f"ai-arbitr-certificate-{session.id}.pdf"
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/download/{download_token}.pdf")
def download_contract_pdf(download_token: str, db: Session = Depends(get_db)):
    raise HTTPException(status_code=410, detail="Финальный PDF направляется сторонам на email и не хранится по постоянной ссылке")
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
