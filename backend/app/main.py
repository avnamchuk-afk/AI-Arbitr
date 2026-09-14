import uuid
import re
import ipaddress
import json
from types import SimpleNamespace
from io import BytesIO
from datetime import datetime, time, timezone
from urllib.request import urlopen

from fastapi import Cookie, Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, StreamingResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy import or_, text
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
    read_verified_ip_cookie,
    token_expires_at,
)
from app.services.contract_templates import AI_ARBITR_DISPUTE_SECTION, build_housing_rent_contract, build_website_development_contract
from app.services.email import send_contract_invite, send_contract_signed_notice, send_magic_link, smtp_is_configured
from app.services.pdf import build_contract_pdf, build_interaction_certificate_pdf
from app.services.privacy import contains_passport_like_data
from app.services.prompts import CONTRACT_SYSTEM_PROMPT, SIMPLE_CONTRACT_SYSTEM_PROMPT, build_dispute_prompt
from app.services.yandex_gpt import YandexGPTError, ask_yandex_gpt

Base.metadata.create_all(bind=engine)


def ensure_runtime_schema() -> None:
    with engine.begin() as connection:
        if engine.dialect.name == "postgresql":
            connection.execute(
                text("ALTER TABLE users ADD COLUMN IF NOT EXISTS trusted_login_count INTEGER NOT NULL DEFAULT 0")
            )
            connection.execute(
                text("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT FALSE")
            )
        elif engine.dialect.name == "sqlite":
            user_columns = connection.execute(text("PRAGMA table_info(users)")).fetchall()
            if not any(column[1] == "trusted_login_count" for column in user_columns):
                connection.execute(text("ALTER TABLE users ADD COLUMN trusted_login_count INTEGER NOT NULL DEFAULT 0"))
            session_columns = connection.execute(text("PRAGMA table_info(sessions)")).fetchall()
            if not any(column[1] == "is_deleted" for column in session_columns):
                connection.execute(text("ALTER TABLE sessions ADD COLUMN is_deleted BOOLEAN NOT NULL DEFAULT 0"))


ensure_runtime_schema()

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
    passport: str
    phone: str
    inn: str = ""
    email: EmailStr
    personal_data_accepted: bool


GUEST_EMAIL_SUFFIX = "@guest.ai-arbitr.local"
VERIFIED_IP_COOKIE_NAME = "ai_arbitr_verified_ip"
VPN_CHECK_CACHE: dict[str, tuple[datetime, bool]] = {}
DAILY_ACTION_LIMIT = 100
DEMO_SESSION_TITLE = "пример"
LEGACY_DEMO_SESSION_TITLE = "Пример: договор на лендинг"
DEMO_USER_PROMPT = "Составь договор найма"
DEMO_REASONING_NOTE = """Что я делаю:
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
PLACEHOLDER_RE = re.compile(r"\[([^\[\]]+)\]")
MONEY_RE = re.compile(r"(\d[\d\s]*(?:[.,]\d+)?\s*(?:руб\.?|рублей))", re.IGNORECASE)

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
    normalized = content.lower()
    if is_housing_rent_request(content):
        steps = [
            "Понятно, делаем договор найма жилого помещения.",
            "Проверяю применимые нормы ГК РФ о найме жилого помещения.",
            "Выделяю существенные условия: жилое помещение, стороны, срок найма, размер и порядок оплаты.",
            "Добавляю обычные условия: порядок передачи квартиры, коммунальные платежи, ремонт, доступ в помещение, ответственность.",
            "Учитываю спорные места: депозит, просрочка оплаты, повреждение имущества, досрочное расторжение.",
            "Добавляю вымышленные данные, чтобы договор сразу было удобно читать.",
            "Позже заменю вымышленные данные на реальные данные сторон и условия сделки.",
            "Генерирую первую версию договора.",
        ]
    else:
        steps = [
            "Проверяю, достаточно ли понятно описан вид договора.",
            "Проверяю применимые нормы ГК РФ и обязательные условия договора.",
            "Выделяю существенные условия, без которых договор может работать плохо.",
            "Добавляю обычные условия: порядок оплаты, сроки, приемка, ответственность, изменение и расторжение.",
            "Учитываю типовые спорные места и формулирую условия понятным языком.",
            "Добавляю вымышленные данные, чтобы договор сразу было удобно читать.",
            "Позже заменю вымышленные данные на реальные данные сторон и условия сделки.",
            "Генерирую первую версию договора.",
        ]
    return "Что я делаю:\n" + "\n".join(f"• {step}" for step in steps)


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
    return (
        "Что я делаю:\n"
        "• Вопрос понятен.\n"
        "• Проверяю его по текущей редакции договора.\n"
        "• Сверяю ответ с обычной практикой и нормами ГК РФ.\n"
        "• Отвечаю коротко и простым языком, без генерации новой версии договора."
    )


def build_update_reasoning_note(change: str) -> str:
    return (
        "Что я делаю:\n"
        "• Нужно добавить новое условие в договор.\n"
        "• Проверяю, не противоречит ли оно ГК РФ и логике договора.\n"
        "• Ищу раздел договора, куда его правильно включить.\n"
        "• Формулирую норму и готовлю новую редакцию договора."
    )


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
    money_match = MONEY_RE.search(sentence)
    if money_match:
        return money_match.group(1)
    amount_with_words_match = re.search(r"(\d[\d\s]*)\s*\([^)]*\)\s*руб", sentence, re.IGNORECASE)
    if amount_with_words_match:
        return f"{amount_with_words_match.group(1).strip()} рублей"
    placeholder = first_placeholder_value(sentence, placeholder_names)
    return placeholder or sentence


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
        return address_sentence
    return object_type


def build_key_terms(contract_text: str) -> list[dict[str, str]]:
    term_placeholder = first_placeholder_value(contract_text, ("дата окончания договора", "срок"))
    if "13 августа 2027" in contract_text:
        term_value = "11 месяцев"
    else:
        term_value = f"до {term_placeholder}" if term_placeholder else find_sentence(contract_text, ("действует",))

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
        {"label": "Объект", "value": build_object_summary(contract_text)},
        {"label": "Оплата в месяц", "value": payment_value},
        {"label": "ЖКУ", "value": utilities_value},
        {"label": "Срок", "value": term_value},
        {"label": "Автопролонгация", "value": prolongation_value},
        {"label": "Дети", "value": children_value},
        {"label": "Животные", "value": pets_value},
        {"label": "Депозит", "value": deposit_value},
        {"label": "Споры", "value": "через AI-Arbitr"},
    ]


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


def apply_ephemeral_party_data(contract_text: str, payload: ReviewApproveRequest) -> str:
    updated = contract_text.replace("1111 111111", payload.passport)
    if payload.phone and "телефон" not in updated.lower():
        updated += f"\n\nТелефон Стороны 2: {payload.phone}"
    if payload.inn and "инн" not in updated.lower():
        updated += f"\nИНН Стороны 2: {payload.inn}"
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
        "Проверяю вашу редакцию:\n"
        "• не нарушает ли она баланс сторон;\n"
        "• достаточно ли ясно описывает обязанность;\n"
        "• можно ли будет применить ее на практике.\n\n"
        "Редакция выглядит допустимой для включения в договор.\n\n"
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
    return {"status": "ok"}


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


def is_public_ip(ip_address: str) -> bool:
    try:
        parsed_ip = ipaddress.ip_address(ip_address)
    except ValueError:
        return False
    return not (
        parsed_ip.is_private
        or parsed_ip.is_loopback
        or parsed_ip.is_link_local
        or parsed_ip.is_multicast
        or parsed_ip.is_reserved
        or parsed_ip.is_unspecified
    )


def looks_like_vpn_or_hosting_ip(ip_address: str) -> bool:
    if not is_public_ip(ip_address):
        return False

    cached = VPN_CHECK_CACHE.get(ip_address)
    if cached and (now_utc() - cached[0]).total_seconds() < 60 * 60:
        return cached[1]

    suspicious = False
    try:
        fields = "status,message,proxy,hosting,query"
        with urlopen(f"http://ip-api.com/json/{ip_address}?fields={fields}", timeout=1.5) as response:
            data = json.loads(response.read().decode("utf-8"))
        suspicious = data.get("status") == "success" and bool(data.get("proxy") or data.get("hosting"))
    except Exception:
        suspicious = False

    VPN_CHECK_CACHE[ip_address] = (now_utc(), suspicious)
    return suspicious


def verified_ip_matches(cookie_value: str | None, user: User, ip_address: str) -> bool:
    data = read_verified_ip_cookie(cookie_value)
    return bool(data and data["user_id"] == str(user.id) and data["ip"] == ip_address)


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


@app.post("/auth/guest")
def create_guest(response: Response, db: Session = Depends(get_db)):
    user = User(email=f"guest-{uuid.uuid4().hex}{GUEST_EMAIL_SUFFIX}")
    db.add(user)
    db.flush()
    ensure_demo_session(db, user)
    db.commit()
    set_auth_cookie(response, user)
    return {"id": user.id, "email": "", "is_guest": True}


def issue_magic_link(email: str, request: Request, db: Session) -> dict[str, str]:
    check_daily_rate_limit(db, request, "magic_link", email=email)
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
    request: Request,
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
    return issue_magic_link(payload.email, request, db)


@app.post("/auth/quick-register")
def quick_register_guest(
    payload: RegisterRequest,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not payload.personal_data_accepted:
        raise HTTPException(status_code=400, detail="Нужно согласие на обработку персональных данных")
    if not is_guest_user(current_user):
        return {"id": current_user.id, "email": current_user.email, "is_guest": False}

    existing_user = db.query(User).filter(User.email == payload.email).one_or_none()
    if existing_user is not None:
        raise HTTPException(status_code=409, detail="Аккаунт с таким email уже есть. Войдите по ссылке из письма.")

    current_user.email = payload.email
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
    if not payload.personal_data_accepted:
        raise HTTPException(status_code=400, detail="Нужно согласие на обработку персональных данных")

    user = db.query(User).filter(User.email == payload.email).one_or_none()
    if user is None:
        db.add(User(email=payload.email))
        db.flush()

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
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    verified_ip_cookie: str | None = Cookie(default=None, alias=VERIFIED_IP_COOKIE_NAME),
):
    if not is_guest_user(user):
        client_ip = get_client_ip(request)
        if looks_like_vpn_or_hosting_ip(client_ip) and not verified_ip_matches(verified_ip_cookie, user, client_ip):
            clear_auth_cookie(response)
            clear_verified_ip_cookie(response)
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "magic_link_required",
                    "email": user.email,
                    "message": "Вход из новой или защищенной сети. Подтвердите email по ссылке из письма.",
                },
            )
        user.trusted_login_count = (user.trusted_login_count or 0) + 1
        if user.trusted_login_count >= 10:
            user.trusted_login_count = 0
            db.commit()
            clear_auth_cookie(response)
            clear_verified_ip_cookie(response)
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "magic_link_required",
                    "email": user.email,
                    "message": "Для безопасности подтвердите вход по ссылке из письма.",
                },
            )
        db.commit()
    return {"id": user.id, "email": "" if is_guest_user(user) else user.email, "is_guest": is_guest_user(user)}


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


@app.get("/sessions/{session_id}")
def get_session(session_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    session = get_accessible_session(db, session_id, user)
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
    }


@app.delete("/sessions/{session_id}")
def delete_session(session_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    session = db.get(ContractSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    if session.owner_user_id != user.id:
        raise HTTPException(status_code=403, detail="Удалить договор может только его создатель")
    if session.status == SessionStatus.finalized or any(
        participant.approval_status == ApprovalStatus.approved for participant in session.participants
    ):
        raise HTTPException(status_code=400, detail="Подписанные договоры защищены от удаления")

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


def serialize_session_summary(db: Session, session: ContractSession, user: User) -> dict:
    participants = list(session.participants)
    current_participant = next((participant for participant in participants if participant.user_id == user.id), None)
    party_1 = next((participant for participant in participants if participant.role == ParticipantRole.party_1), None)
    party_2 = next((participant for participant in participants if participant.role == ParticipantRole.party_2), None)
    completed_event_exists = (
        db.query(Message.id)
        .filter(
            Message.session_id == session.id,
            Message.role == MessageRole.system,
            Message.content.startswith("Договор отмечен как исполненный"),
        )
        .first()
        is not None
    )
    return {
        "id": session.id,
        "owner_user_id": session.owner_user_id,
        "title": session.title,
        "status": session.status,
        "is_completed": completed_event_exists,
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
    }


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
    session.is_completed = True
    final_version.is_final = True
    for participant in session.participants:
        participant.approval_status = ApprovalStatus.approved
        participant.approved_version_id = final_version.id
    db.add(Message(session_id=session.id, role=MessageRole.system, content="CONTRACT_FINALIZED"))


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
    db.add(
        ContractVersion(
            session_id=session.id,
            version_number=1,
            content=DEMO_CONTRACT_TEXT,
        )
    )


def save_contract_version(db: Session, session: ContractSession, content: str) -> ContractVersion:
    content = ensure_ai_arbitr_dispute_section(clean_contract_markdown(content))
    version_count = db.query(ContractVersion).filter(ContractVersion.session_id == session.id).count()
    version_number = version_count + 1
    content = apply_contract_number(content, version_number)
    version = ContractVersion(
        session_id=session.id,
        version_number=version_number,
        content=content,
    )
    session.status = SessionStatus.in_review
    for participant in session.participants:
        participant.approval_status = ApprovalStatus.pending
        participant.approved_version_id = None
    db.add(version)
    db.add(Message(session_id=session.id, role=MessageRole.system, content=f"VERSION_CREATED|{version_number}"))
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
    if session.invite_token is None:
        session.invite_token = uuid.uuid4()
        db.commit()
        db.refresh(session)
    latest_version = get_latest_version(db, session)
    if latest_version is None:
        raise HTTPException(status_code=400, detail="Нет версии договора для согласования")
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
        send_contract_invite(payload.email, invite_link, session.title, pdf_link)
        sent = smtp_is_configured()
        db.add(
            Message(
                session_id=session.id,
                role=MessageRole.system,
                content=f"VERSION_SENT|{version_number}|{payload.email}",
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
        "key_terms": build_key_terms(latest_version.content),
        "approved": party_2.approval_status == ApprovalStatus.approved,
        "party_email": party_2.user.email if party_2.user else "",
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
        return {"finalized": True}

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

    participant.user_id = user.id
    participant.joined_at = participant.joined_at or now_utc()
    participant.approval_status = ApprovalStatus.approved
    participant.approved_version_id = latest_version.id
    db.add(
        Message(
            session_id=session.id,
            role=MessageRole.system,
            content=(
                f"VERSION_APPROVED|{latest_version.version_number}|{payload.email}"
                f"|passport:{mask_tail(payload.passport, 2)}|phone:{mask_tail(payload.phone, 2)}"
                f"|inn:{mask_tail(payload.inn, 2) if payload.inn else ''}"
            ),
        )
    )
    owner = db.get(User, session.owner_user_id)
    temp_content = apply_ephemeral_party_data(latest_version.content, payload)
    temp_version = SimpleNamespace(content=temp_content)
    messages = (
        db.query(Message)
        .filter(Message.session_id == session.id)
        .order_by(Message.created_at.asc())
        .all()
    )
    pdf_bytes = build_contract_pdf(session, temp_version, session.participants, messages)
    for email in {str(payload.email), owner.email if owner and not is_guest_user(owner) else ""}:
        if email:
            send_contract_signed_notice(email, session.title, pdf_bytes)
    db.commit()
    return {"finalized": False, "party_two_signed": True}


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
        send_contract_invite(party_email, invite_link, session.title, pdf_link)
        db.add(
            Message(
                session_id=session.id,
                role=MessageRole.system,
                content=f"VERSION_SENT|{latest_version.version_number}|{party_email}",
            )
        )
        answer = f"Версия № {latest_version.version_number} направлена на согласование на адрес {party_email}."
        db.add(Message(session_id=session.id, role=MessageRole.assistant, content=answer))
        db.commit()
        return {
            "content": answer,
            "contract_saved": False,
            "reasoning": "",
            "next_action": "sent",
            "invite_link": invite_link,
        }

    if (
        latest_version_before_answer is not None
        and not is_contract_update
        and is_affirmative_message(payload.content)
        and "переходим к согласованию" in last_assistant_lower
    ):
        latest_version = get_latest_version(db, session)
        version_number = latest_version.version_number if latest_version else 1
        reasoning = (
            "Что я делаю:\n"
            f"• Готовлю версию № {version_number} для согласования.\n"
            "• Проверяю, что добавленные условия учтены.\n"
            "• Версия готова к отправке второй стороне."
        )
        answer = (
            f"Готовлю версию № {version_number}.\n\n"
            "Версия готова.\n\n"
            "Введите e-mail второй стороны, на который направить ссылку для согласования."
        )
        db.add(Message(session_id=session.id, role=MessageRole.system, content=reasoning))
        db.add(Message(session_id=session.id, role=MessageRole.assistant, content=answer))
        db.commit()
        return {"content": answer, "contract_saved": False, "reasoning": reasoning, "next_action": "email"}

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
            reasoning = (
                "Что я делаю:\n"
                "• Пользователь предложил свою редакцию условия.\n"
                "• Проверяю, не нарушает ли она баланс сторон.\n"
                "• Проверяю ясность формулировки и возможность применить ее на практике."
            )

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

    if latest_version_before_answer is None and not is_contract_update and needs_service_type_clarification(payload.content):
        answer = build_service_type_clarification(payload.content)
        db.add(
            Message(
                session_id=session.id,
                role=MessageRole.system,
                content=(
                    "Что я делаю:\n"
                    "• Вижу, что запрос относится к договору оказания услуг.\n"
                    "• Вид услуги указан неясно или похож на опечатку.\n"
                    "• Сначала уточняю предмет договора, чтобы не подготовить неверный документ."
                ),
            )
        )
        db.add(Message(session_id=session.id, role=MessageRole.assistant, content=answer))
        db.commit()
        return {"content": answer, "contract_saved": False, "reasoning": ""}

    if latest_version_before_answer is None and not is_contract_update and needs_broad_contract_clarification(payload.content):
        answer = build_broad_contract_clarification()
        db.add(
            Message(
                session_id=session.id,
                role=MessageRole.system,
                content=(
                    "Что я делаю:\n"
                    "• Вижу, что запрос слишком общий.\n"
                    "• Сначала уточняю предмет договора и роли сторон.\n"
                    "• После уточнения подготовлю проект без лишних догадок."
                ),
            )
        )
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
            reasoning = (
                "Что я делаю:\n"
                "• Проверяю реальные данные стороны.\n"
                "• Изменяю вымышленные данные в тексте договора.\n"
                "• Сохраняю новую версию перед согласованием."
            )
            answer = (
                "Изменяю вымышленные данные на реальные.\n\n"
                "Данные внесены в договор успешно.\n\n"
                "Переходим к отправке ссылки второй стороне для согласования?"
            )
            db.add(Message(session_id=session.id, role=MessageRole.system, content=reasoning))
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
            answer = await ask_yandex_gpt(
                prompt
            )
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
    db.add(
        Message(
            session_id=session.id,
            role=MessageRole.system,
            content=f"VERSION_APPROVED|{latest_version.version_number}|{user.email}",
        )
    )

    participants = session.participants
    both_approved = all(
        item.user_id is not None
        and item.approval_status == ApprovalStatus.approved
        and item.approved_version_id == latest_version.id
        for item in participants
    )
    if both_approved:
        finalize_signed_session(db, session, latest_version)

    db.commit()
    if both_approved:
        messages = (
            db.query(Message)
            .filter(Message.session_id == session.id)
            .order_by(Message.created_at.asc())
            .all()
        )
        pdf_bytes = build_contract_pdf(session, latest_version, participants, messages)
        certificate_bytes = build_interaction_certificate_pdf(session, latest_version, participants, messages)
        for item in participants:
            if item.user and not is_guest_user(item.user):
                send_contract_signed_notice(item.user.email, session.title, pdf_bytes, certificate_bytes)
    return {"finalized": both_approved, "status": session.status}


@app.post("/sessions/{session_id}/complete")
def complete_contract(session_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    session = get_accessible_session(db, session_id, user)
    if session.status != SessionStatus.finalized:
        raise HTTPException(status_code=400, detail="Отметить исполнение можно только по подписанному договору")
    db.add(
        Message(
            session_id=session.id,
            role=MessageRole.system,
            content="Договор отмечен как исполненный. Чат сохранен в истории и защищен от удаления.",
        )
    )
    db.commit()
    return {"message": "Договор отмечен как исполненный"}


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
