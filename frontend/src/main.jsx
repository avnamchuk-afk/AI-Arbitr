import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  BriefcaseBusiness,
  Building2,
  Check,
  ChevronDown,
  ChevronRight,
  Copy,
  Download,
  FileText,
  BarChart3,
  Globe2,
  Hammer,
  HardHat,
  Home,
  LogOut,
  Menu,
  Plus,
  RefreshCw,
  Scale,
  Search,
  Send,
  ShieldCheck,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  Trash2,
} from "lucide-react";
import LandingPage from "./LandingPage.jsx";
import KnowledgeBase from "./KnowledgeBase.jsx";
import { FORM_HINTS, getChatSuggestions, getSessionSearchSuggestions } from "./catalogs/suggestions.js";
import { APP_VERSION, APP_VERSION_SHORT } from "./version.js";
import "./styles.css";

const API_URL = window.__AI_ARBITR_CONFIG__?.apiUrl || "http://localhost:8000";
const SUPPORT_EMAIL = "ai-arbitr@ya.ru";
const SUPPORT_MAILTO = `mailto:${SUPPORT_EMAIL}?subject=${encodeURIComponent("Обратная связь AI-Arbitr")}`;
const TYPEWRITER_DELAY_MS = 10;
const TYPEWRITER_CHUNK_SIZE = 4;
const TYPEWRITER_MAX_STEPS = 90;
const MIN_INITIAL_THINKING_MS = 3200;
const MIN_REGULAR_THINKING_MS = 1500;
const DEMO_REVIEW_PASSPORT = "1111 111111";
const DEFAULT_AI_MODEL = "qwen";
const LAST_SESSION_KEY = "ai-arbitr-current-session";
const PENDING_INVITE_KEY = "ai-arbitr-pending-invite";
const CONSENT_VERSION = "1.0";

function apiErrorMessage(detail, fallback) {
  if (typeof detail === "string" && detail.trim()) return detail;
  if (detail && typeof detail.message === "string") return detail.message;
  return fallback;
}
const sessionModeKey = (sessionId) => `ai-arbitr-chat-mode:${sessionId}`;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const PRIVACY_SECTIONS = [
  {
    title: "1. Общие положения",
    items: [
      "1.1. Настоящая Политика конфиденциальности определяет порядок обработки и защиты персональных данных пользователей сервиса Ai-arbitr, предоставляемого на сайте https://ai-arbitr.ru.",
      "1.2. Ai-arbitr уважает конфиденциальность пользователей и придерживается принципа минимизации обработки персональных данных в соответствии с Федеральным законом от 27.07.2006 № 152-ФЗ «О персональных данных».",
      "1.3. Ключевой принцип Сервиса: мы намеренно не храним пакет данных, позволяющий однозначно идентифицировать пользователя после заключения договора. Обработка полных персональных данных носит строго эфемерный характер и ограничивается моментом формирования документа и его однократной передачи сторонам.",
      "1.4. Используя Сервис, вы выражаете согласие с настоящей Политикой и условиями обработки персональных данных, указанными в Пользовательском соглашении.",
    ],
  },
  {
    title: "2. Состав собираемых персональных данных",
    items: [
      "2.1. Данные, собираемые автоматически: IP-адрес устройства; информация о браузере; отпечаток браузера; дата и время доступа к Сервису; Session ID; хэш-суммы документов; логи действий пользователя.",
      "2.2. Данные, предоставляемые пользователем добровольно (эфемерная обработка): адрес электронной почты; номер телефона; серия, номер паспорта; ИНН (для ИП, МСП).",
      "2.3. Данные, сохраняемые в системе после заключения договора: UID сторон; хэш адреса электронной почты; маскированные данные; технические логи.",
      "2.4. Сервис использует строго необходимые cookies для сессии, авторизации, безопасности и восстановления открытого договора. Рекламные cookies не используются.",
      "Важно: указанный объем данных сам по себе не образует пакет данных, позволяющий однозначно идентифицировать личность пользователя без сопоставления с информацией, которой стороны обменялись самостоятельно.",
    ],
  },
  {
    title: "3. Цели обработки персональных данных",
    items: [
      "3.1. Персональные данные обрабатываются для формирования проекта договора, включения реквизитов сторон, однократной отправки финального PDF-документа, фиксации конклюдентных действий как простой электронной подписи и логирования действий для доказательственной базы.",
      "3.1.1. Указанный пользователем email используется для юридически значимых уведомлений о согласовании, подписании, исполнении договора и споре в соответствии с Правилами сервиса.",
      "3.2. Мы не используем персональные данные для маркетинга, профилирования или внешних проверок через государственные реестры.",
    ],
  },
  {
    title: "4. Правовые основания обработки",
    items: [
      "4.1. Обработка осуществляется на основании согласия субъекта, необходимости для заключения и исполнения договора, а также осуществления правосудия.",
      "4.2. Пользователь, проставляя чекбокс, дает заверение об обстоятельствах, принимая на себя ответственность за достоверность предоставленных сведений.",
    ],
  },
  {
    title: "5. Порядок и сроки обработки. Эфемерное хранение",
    items: [
      "5.1. Персональные данные, включая серию и номер паспорта, номер телефона и ИНН, используются системой только для генерации финального PDF-документа и его рассылки сторонам.",
      "5.2. Сразу после успешной отправки финального PDF-документа сторонам полные персональные данные безвозвратно удаляются из оперативной памяти и базы данных Сервиса.",
      "5.3. После заключения договора Сервис не хранит пакет данных, позволяющий идентифицировать пользователя. Сохраняются только обезличенные технические логи и маскированные значения.",
      "5.4. UID, хэши email, маскированные реквизиты и технические логи хранятся 5 лет с момента заключения договора в архивных и доказательственных целях.",
    ],
  },
  {
    title: "6. Передача персональных данных",
    items: [
      "6.1. Полные персональные данные передаются сторонам друг друга однократно в составе финального PDF-документа и текстового уведомления на email.",
      "6.2. При возникновении спора стороны вправе самостоятельно обмениваться полными персональными данными, включая сохраненный PDF-файл, для защиты своих прав за пределами Сервиса.",
      "6.3. По официальному мотивированному запросу суда или правоохранительных органов Сервис предоставляет справку о факте электронного взаимодействия: хэш документа, IP-адрес, User-Agent, timestamp и лог отправки письма.",
      "6.4. Мы не передаем данные коммерческим организациям, рекламным сетям или иным третьим лицам без согласия пользователя или прямого требования закона.",
    ],
  },
  {
    title: "7. Права субъекта персональных данных",
    items: [
      "7.1. Пользователь имеет право на доступ, уточнение, блокирование или уничтожение персональных данных, хранящихся в Сервисе.",
      "7.2. В отношении полных данных, введенных при подписании, право на доступ или удаление может быть реализовано только до момента их эфемерного удаления после отправки документа.",
      "7.3. После удаления полных данных Сервис может подтвердить только факт обработки, но не их содержание.",
      "7.4. Отзыв согласия не влечет автоматического удаления данных, если обработка необходима для исполнения договора или осуществления правосудия.",
    ],
  },
  {
    title: "8. Меры по защите персональных данных",
    items: [
      "8.1. Использование защищенного протокола HTTPS (SSL/TLS).",
      "8.2. Хранение идентификаторов и токенов в хэшированном виде.",
      "8.3. Использование временного хранения для полных персональных данных с автоматическим принудительным удалением после триггера отправки email.",
      "8.4. Логирование факта выполнения команды удаления для целей внутреннего аудита безопасности.",
    ],
  },
  {
    title: "9. Заключительные положения",
    items: [
      "9.1. Мы оставляем за собой право вносить изменения в настоящую Политику. Актуальная версия размещается на Сайте.",
      `9.2. Контактная информация по вопросам обработки персональных данных: ${SUPPORT_EMAIL}.`,
      "9.3. Политика регулируется законодательством Российской Федерации.",
    ],
  },
];

const TERMS_SECTIONS = [
  {
    title: "1. Электронное взаимодействие",
    items: [
      "1.1. Пользователь указывает принадлежащий ему адрес электронной почты и признает сообщения AI-Arbitr, направленные на этот адрес, юридически значимыми уведомлениями в рамках работы с договором.",
      "1.2. Переход по персональной ссылке, согласование версии и нажатие кнопки «Подписать» фиксируются Сервисом как действия пользователя и могут использоваться как простая электронная подпись в согласованном сторонами порядке.",
      "1.3. Пользователь обязан сохранять доступ к своей почте, не передавать персональные ссылки третьим лицам и своевременно сообщать о компрометации доступа.",
    ],
  },
  {
    title: "2. Документы и уведомления",
    items: [
      "2.1. Проекты, уведомления о подписании, финальный PDF и справка об электронном взаимодействии направляются на указанные сторонами адреса электронной почты.",
      "2.2. Сообщение считается доставленным после успешной передачи почтовому серверу адресата. Пользователь самостоятельно проверяет папки «Входящие» и «Спам».",
    ],
  },
  {
    title: "3. Cookies",
    items: [
      "3.1. Сервис использует строго необходимые cookies для сохранения сессии, авторизации, безопасности и восстановления открытого договора.",
      "3.2. Обязательные cookies не используются для рекламного отслеживания. При появлении аналитических или маркетинговых cookies Сервис запросит отдельное согласие.",
    ],
  },
];

function needsServiceClarification(content) {
  const normalized = content.toLowerCase().replaceAll("ё", "е");
  const serviceRequest = normalized.includes("услуг") || normalized.includes("оказан");
  if (!serviceRequest) return false;
  if (normalized.includes("болгар")) return true;
  const knownMarkers = [
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
    "медицин",
    "транспорт",
    "логист",
    "охран",
  ];
  return !knownMarkers.some((marker) => normalized.includes(marker));
}

function needsBroadContractClarification(content) {
  const normalized = content.toLowerCase().replaceAll("ё", "е").trim().replace(/\s+/g, " ");
  if (normalized.length <= 18 && normalized.includes("договор")) return true;
  const broadPatterns = [
    "сделай договор",
    "составь договор",
    "подготовь договор",
    "нужен договор",
    "договор с подрядчиком",
    "договор на сотрудничество",
    "договор о сотрудничестве",
  ];
  if (!broadPatterns.some((pattern) => normalized.includes(pattern))) return false;
  const concreteMarkers = [
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
  ];
  return !concreteMarkers.some((marker) => normalized.includes(marker));
}

function getThinkingSteps(content) {
  if (needsServiceClarification(content)) {
    return ["Нужно уточнение", "Готовлю короткий вопрос"];
  }
  if (needsBroadContractClarification(content)) {
    return ["Нужно уточнение", "Готовлю короткий вопрос"];
  }
  return ["Генерация ответа", "Подготовка текста", "Завершение"];
}

function buildReasoningNote(steps) {
  return "";
}

function formatSessionTimestamp(session) {
  const timestamp = session.updated_at || session.created_at;
  return new Date(timestamp).toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatFinalizedDate(session) {
  const timestamp = session?.finalized_at || session?.updated_at || session?.created_at;
  if (!timestamp) return "не указана";
  return new Date(timestamp).toLocaleDateString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

function formatEventTimestamp(timestamp) {
  if (!timestamp) return "";
  return new Date(timestamp).toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function getHistoryEvent(message) {
  if (message.role !== "system") return null;
  const parts = message.content.split("|");
  if (parts[0] === "VERSION_CREATED") {
    return {
      title: `Версия №${parts[1] || "1"} создана`,
      meta: formatEventTimestamp(message.created_at),
    };
  }
  if (parts[0] === "VERSION_SENT") {
    return {
      title: `Версия №${parts[1] || "1"} направлена на согласование`,
      meta: [parts[2], formatEventTimestamp(message.created_at)].filter(Boolean).join(" · "),
    };
  }
  if (parts[0] === "VERSION_APPROVED") {
    return {
      title: `Версия №${parts[1] || "1"} согласована`,
      meta: [parts[2], formatEventTimestamp(message.created_at)].filter(Boolean).join(" · "),
    };
  }
  if (parts[0] === "CONTRACT_FINALIZED") {
    return {
      title: "Договор подписан сторонами",
      meta: formatEventTimestamp(message.created_at),
    };
  }
  return null;
}

const SESSION_FILTERS = [
  { id: "draft", label: "Черновики" },
  { id: "sent", label: "Исходящие" },
  { id: "incoming", label: "Входящие" },
  { id: "my-signature", label: "На подпись" },
  { id: "active", label: "Действующие" },
  { id: "closed", label: "Архив" },
  { id: "deleted", label: "Удаленные" },
];

function getSessionBucket(session) {
  const stage = session.workflow?.stage;
  if (stage === "deleted") return "deleted";
  if (stage === "completed") return "closed";
  if (stage === "active" || stage === "dispute") return "active";
  if (stage === "awaiting_creator") return "my-signature";
  if (stage === "awaiting_counterparty") return session.my_role === "party_2" ? "incoming" : "sent";
  if (session.my_role === "party_2") return "incoming";
  return "draft";
}

function getSessionStatusLabel(session) {
  if (session.workflow?.stage_label) return session.workflow.stage_label;
  const bucket = getSessionBucket(session);
  if (bucket === "draft") return "Черновик";
  if (bucket === "sent") return "На согласовании";
  if (bucket === "incoming") return "Входящий";
  if (bucket === "my-signature") return "Ждет моей подписи";
  if (bucket === "active") return "Действует";
  if (bucket === "deleted") return "Удален";
  return "В архиве";
}

function getSessionIcon(session) {
  const title = (session.title || "").toLowerCase();
  if (title.includes("подряд") || title.includes("строит") || title.includes("ремонт")) return HardHat;
  if (title.includes("найм") || title.includes("аренд")) return Home;
  if (title.includes("saas") || title.includes("сайт") || title.includes("лендинг")) return Globe2;
  if (title.includes("клининг")) return Sparkles;
  if (title.includes("юруслуг") || title.includes("юрид")) return Scale;
  if (title.includes("поставк") || title.includes("купли")) return BriefcaseBusiness;
  if (title.includes("nda")) return ShieldCheck;
  if (title.includes("займ")) return Building2;
  if (title.includes("услуг")) return Hammer;
  return FileText;
}

function getSessionCounterparty(session) {
  if (session.party_2_email) return session.party_2_email;
  if (session.my_role === "party_2") return "Сторона 1";
  if (session.invite_token || session.status === "in_review") return "Сторона 2";
  return "Без контрагента";
}

function getContractContext(session, detail) {
  return `${session?.title || ""}\n${detail?.latest_version?.content || ""}`.toLowerCase();
}

function getLegalRoleOptions(session, detail) {
  const catalogRoles = detail?.contract_type?.roles;
  if (Array.isArray(catalogRoles) && catalogRoles.length === 2) return catalogRoles;
  const context = getContractContext(session, detail);
  if (context.includes("найм") || context.includes("нанимател") || context.includes("жилое помещ")) return ["Наймодатель", "Наниматель"];
  if (context.includes("аренд")) return ["Арендодатель", "Арендатор"];
  if (context.includes("купл") || context.includes("продавец") || context.includes("покупател")) return ["Продавец", "Покупатель"];
  if (context.includes("подряд") || context.includes("подрядчик")) return ["Заказчик", "Подрядчик"];
  if (context.includes("займ")) return ["Займодавец", "Заемщик"];
  return ["Заказчик", "Исполнитель"];
}

function getQuestionPlaceholder(session, detail) {
  const context = getContractContext(session, detail);
  if (context.includes("найм") || context.includes("квартир") || context.includes("жил")) {
    return "Например: что означает обеспечительный платеж и когда его вернут?";
  }
  if (context.includes("подряд") || context.includes("строител") || context.includes("ремонт")) {
    return "Например: что будет, если подрядчик нарушит срок работ?";
  }
  if (context.includes("услуг") || context.includes("оказан")) {
    return "Например: как понять, какие услуги считаются оказанными?";
  }
  if (context.includes("сайт") || context.includes("saas") || context.includes("саас") || context.includes("разработ")) {
    return "Например: когда результат считается принятым заказчиком?";
  }
  if (context.includes("поставк") || context.includes("купл") || context.includes("продаж")) {
    return "Например: что будет при просрочке поставки или оплаты?";
  }
  return "Например: какие риски есть в этом условии?";
}

function getAdditionPlaceholder(session, detail) {
  const context = getContractContext(session, detail);
  if (context.includes("найм") || context.includes("квартир") || context.includes("жил")) {
    return "Например: добавить запрет проживания с животными без согласия";
  }
  if (context.includes("подряд") || context.includes("строител") || context.includes("ремонт")) {
    return "Например: добавить пеню за просрочку выполнения работ";
  }
  if (context.includes("услуг") || context.includes("оказан")) {
    return "Например: добавить порядок подтверждения оказанных услуг";
  }
  if (context.includes("сайт") || context.includes("saas") || context.includes("саас") || context.includes("разработ")) {
    return "Например: добавить этап приемки и исправления замечаний";
  }
  if (context.includes("поставк") || context.includes("купл") || context.includes("продаж")) {
    return "Например: добавить ответственность за просрочку поставки";
  }
  return "Например: добавить условие о сроках, оплате или ответственности";
}

const PROJECT_TEAM = [
  {
    name: "Alex",
    role: "Architecture & Legal Methodology",
    text: "Системная логика, legal tech и промпт-инжиниринг.",
  },
  {
    name: "Артур",
    role: "Legal Counsel",
    text: "Договорное право, юридическая валидность и LegalTech-коммуникация.",
  },
  {
    name: "Лена",
    role: "Finance & Unit Economics",
    text: "Финансовая модель, устойчивость и unit-экономика SaaS.",
  },
  {
    name: "Ника",
    role: "Lead IT & AI Development",
    text: "AI-интеграции, безопасность, iOS/Android и инфраструктура.",
  },
  {
    name: "Николай",
    role: "Growth & Marketing",
    text: "Рост, digital-коммуникации и развитие сообщества.",
  },
  {
    name: "София",
    role: "Behavioral Psychology",
    text: "Поведенческая психология, медиация и разрешение конфликтов.",
  },
];

function ModelSelector({ selectedModel, onChange }) {
  return (
    <label className="model-selector" aria-label="Выбор нейросети">
      <span className="model-status" aria-hidden="true" />
      <span className="model-copy">
        <select
          value={selectedModel}
          onChange={(event) => {
            onChange?.(event.target.value);
          }}
        >
          <option value="yandexgpt">YandexGPT 5.1 Pro</option>
          <option value="qwen">Qwen 2.5 7B Instruct</option>
          <option value="gigachat" disabled>GigaChat скоро</option>
          <option value="chatgpt" disabled>ChatGPT скоро</option>
          <option value="claude" disabled>Claude скоро</option>
          <option value="deepseek" disabled>DeepSeek скоро</option>
        </select>
        <small>Foundation Models API</small>
      </span>
    </label>
  );
}

function LogoMark({ compact = false, onClick }) {
  const content = (
    <>
      <span className="brand-icon" aria-hidden="true">
        <i />
      </span>
      <span className="brand-word">AI-Arbitr</span>
      <span className="brand-beta">β {APP_VERSION_SHORT}</span>
    </>
  );
  if (onClick) {
    return (
      <button
        className={compact ? "brand-mark compact interactive" : "brand-mark interactive"}
        type="button"
        onClick={onClick}
        aria-label="О сервисе AI-Arbitr"
      >
        {content}
      </button>
    );
  }
  return (
    <div className={compact ? "brand-mark compact" : "brand-mark"} aria-label={`AI-Arbitr beta ${APP_VERSION_SHORT}`}>
      {content}
    </div>
  );
}

function KeyTermsCard({ terms, onTermClick }) {
  const compactValue = (value) => {
    const normalized = String(value || "").replace(/\s+/g, " ").trim();
    return normalized.length > 72 ? `${normalized.slice(0, 71).trim()}…` : normalized;
  };
  const visibleTerms = (terms || [])
    .map((term) => ({ ...term, value: compactValue(term.value) }))
    .filter((term) => term.value && term.value !== "не указано");
  if (!visibleTerms.length) return null;
  return (
    <section className="key-terms-card">
      <strong>Ключевые условия</strong>
      <div className="key-terms-list">
        {visibleTerms.map((term, index) => (
          <button
            className="key-term"
            key={`${term.label}-${index}`}
            type="button"
            onClick={() => onTermClick?.(term)}
          >
            <span className="key-check">
              <Check size={14} />
            </span>
            <div>
              <small>{term.label}</small>
              <p>{term.value}</p>
            </div>
          </button>
        ))}
      </div>
    </section>
  );
}

function PrivacyPage() {
  return (
    <main className="privacy-page">
      <article className="privacy-shell">
        <header className="privacy-header">
          <LogoMark compact />
          <p>Версия 1.3 от 18 сентября 2026 г.</p>
          <h1>Политика конфиденциальности сервиса Ai-arbitr</h1>
        </header>
        {PRIVACY_SECTIONS.map((section) => (
          <section key={section.title} className="privacy-section">
            <h2>{section.title}</h2>
            {section.items.map((item) => (
              <p key={item}>{item}</p>
            ))}
          </section>
        ))}
        <footer className="privacy-footer">
          <p>Дата последнего обновления: 18 сентября 2026 г.</p>
          <strong>Ai-arbitr — конфиденциальность по дизайну.</strong>
          <a href={SUPPORT_MAILTO}>{SUPPORT_EMAIL}</a>
          <a href="/">Вернуться в сервис</a>
        </footer>
      </article>
    </main>
  );
}

function TermsPage() {
  return (
    <main className="privacy-page">
      <article className="privacy-shell">
        <header className="privacy-header">
          <LogoMark compact />
          <p>Версия 1.0 от 18 сентября 2026 г.</p>
          <h1>Правила сервиса AI-Arbitr</h1>
        </header>
        {TERMS_SECTIONS.map((section) => (
          <section key={section.title} className="privacy-section">
            <h2>{section.title}</h2>
            {section.items.map((item) => <p key={item}>{item}</p>)}
          </section>
        ))}
        <footer className="privacy-footer">
          <a href="/privacy">Политика конфиденциальности</a>
          <a href={SUPPORT_MAILTO}>Обратная связь · {SUPPORT_EMAIL}</a>
          <a href="/">Вернуться в сервис</a>
        </footer>
      </article>
    </main>
  );
}

function ConsentText() {
  return (
    <span>
      Принимаю <a href="/terms" target="_blank" rel="noreferrer">Правила сервиса</a>, включая юридически значимые
      уведомления по email, <a href="/privacy" target="_blank" rel="noreferrer">Политику конфиденциальности</a> и
      использование обязательных cookies
    </span>
  );
}

function MessageActions({ message, onToast }) {
  if (!["assistant", "user"].includes(message.role)) return null;
  const copyMessage = () => {
    navigator.clipboard?.writeText(message.content || "");
    onToast?.("Сообщение скопировано");
  };
  return (
    <div className="message-actions" aria-label="Действия с сообщением">
      <button onClick={copyMessage} title="Копировать" aria-label="Копировать сообщение">
        <Copy size={14} />
      </button>
      <button title="Хороший ответ" aria-label="Хороший ответ" onClick={() => onToast?.("Спасибо, учту оценку")}>
        <ThumbsUp size={14} />
      </button>
      <button title="Плохой ответ" aria-label="Плохой ответ" onClick={() => onToast?.("Понял, этот ответ можно улучшить")}>
        <ThumbsDown size={14} />
      </button>
      {message.role === "assistant" && (
        <button title="Обновить ответ" aria-label="Обновить ответ" onClick={() => onToast?.("Перегенерацию ответа добавим следующим шагом")}>
          <RefreshCw size={14} />
        </button>
      )}
    </div>
  );
}

function SuggestionList({ items, activeIndex = -1, onSelect, label }) {
  if (!items.length) return null;
  return (
    <div className="suggestion-list" role="listbox" aria-label={label}>
      <small>{label}</small>
      {items.map((item, index) => {
        const value = typeof item === "string" ? item : item.title;
        const meta = typeof item === "string" ? "" : getSessionStatusLabel(item);
        return (
          <button
            key={typeof item === "string" ? item : item.id}
            type="button"
            role="option"
            aria-selected={index === activeIndex}
            className={index === activeIndex ? "active" : ""}
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => onSelect(item)}
          >
            <Search size={14} />
            <span>{value}</span>
            {meta && <em>{meta}</em>}
          </button>
        );
      })}
    </div>
  );
}

function App() {
  const [email, setEmail] = useState("");
  const [authMode, setAuthMode] = useState("register");
  const [userId, setUserId] = useState("");
  const [authReady, setAuthReady] = useState(false);
  const [isGuest, setIsGuest] = useState(false);
  const [authPromptOpen, setAuthPromptOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [aboutOpen, setAboutOpen] = useState(false);
  const [statsOpen, setStatsOpen] = useState(false);
  const [stats, setStats] = useState(null);
  const [statsLoading, setStatsLoading] = useState(false);
  const [contractPreviewOpen, setContractPreviewOpen] = useState(false);
  const [toast, setToast] = useState("");
  const [inviteConfirmation, setInviteConfirmation] = useState("");
  const storedConsentVersion = localStorage.getItem("ai-arbitr-consent-version");
  const [accepted, setAccepted] = useState(storedConsentVersion === CONSENT_VERSION);
  const [cookieConsentVisible, setCookieConsentVisible] = useState(
    storedConsentVersion !== CONSENT_VERSION
  );
  const [authed, setAuthed] = useState(false);
  const [sessions, setSessions] = useState([]);
  const [currentSession, setCurrentSession] = useState(null);
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState(localStorage.getItem("ai-arbitr-draft") || "");
  const [selectedModel, setSelectedModel] = useState(localStorage.getItem("ai-arbitr-model") || DEFAULT_AI_MODEL);
  const [thinking, setThinking] = useState(false);
  const [thinkingStep, setThinkingStep] = useState("");
  const [thinkingProgress, setThinkingProgress] = useState(0);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [loginNotice, setLoginNotice] = useState("");
  const [devLink, setDevLink] = useState("");
  const [sessionDetail, setSessionDetail] = useState(null);
  const [inviteLink, setInviteLink] = useState("");
  const [appNotice, setAppNotice] = useState("");
  const [partyEmail, setPartyEmail] = useState("");
  const [emailSuggestions, setEmailSuggestions] = useState([]);
  const [creatorLegalRole, setCreatorLegalRole] = useState("");
  const [deleteCandidateId, setDeleteCandidateId] = useState("");
  const [chatMode, setChatMode] = useState("idle");
  const [expandedSessionGroups, setExpandedSessionGroups] = useState(["draft"]);
  const [sessionSearch, setSessionSearch] = useState("");
  const [sessionSearchFocused, setSessionSearchFocused] = useState(false);
  const [composerFocused, setComposerFocused] = useState(false);
  const [activeSuggestionIndex, setActiveSuggestionIndex] = useState(-1);
  const [questionResolved, setQuestionResolved] = useState(false);
  const [authPromptTitle, setAuthPromptTitle] = useState("Сохранить историю");
  const [authPromptCopy, setAuthPromptCopy] = useState(
    "Укажите email, чтобы сохранить этот договор, получить ссылку для входа и отправить договор второй стороне."
  );
  const [afterAuthAction, setAfterAuthAction] = useState("");
  const [reviewData, setReviewData] = useState(null);
  const [reviewForm, setReviewForm] = useState({
    partyType: "individual",
    fullName: "Иванов Иван Иванович",
    passport: DEMO_REVIEW_PASSPORT,
    phone: "+7 900 000-00-00",
    inn: "",
    ogrn: "",
    organizationName: "",
    email: "",
    accepted: storedConsentVersion === CONSENT_VERSION,
  });
  const [reviewNotice, setReviewNotice] = useState("");
  const [reviewLoading, setReviewLoading] = useState(false);
  const [reviewFormOpen, setReviewFormOpen] = useState(false);
  const [reviewConfirmation, setReviewConfirmation] = useState(null);
  const [reviewSubmitting, setReviewSubmitting] = useState(false);
  const [ownerSigningOpen, setOwnerSigningOpen] = useState(false);
  const [ownerSubmitting, setOwnerSubmitting] = useState(false);
  const [ownerForm, setOwnerForm] = useState({
    partyType: "individual",
    fullName: "Петров Петр Петрович",
    passport: DEMO_REVIEW_PASSPORT,
    phone: "+7 900 000-00-00",
    inn: "",
    ogrn: "",
    organizationName: "",
    accepted: storedConsentVersion === CONSENT_VERSION,
  });
  const [inviteSending, setInviteSending] = useState(false);
  const [authSubmitting, setAuthSubmitting] = useState(false);
  const messagesEndRef = useRef(null);
  const reviewFormRef = useRef(null);
  const ownerFormRef = useRef(null);
  const agreementRef = useRef(null);
  const pendingInviteResumeRef = useRef(false);
  const sessionRestoreDoneRef = useRef(false);
  const sessionLoadRequestRef = useRef(0);
  const gestureRef = useRef({ x: 0, y: 0 });

  const reviewToken = getReviewTokenFromPath();
  const isPrivacyPath = window.location.pathname === "/privacy";
  const isTermsPath = window.location.pathname === "/terms";
  const isLandingPath = window.location.pathname === "/landing";
  const isKnowledgePath = window.location.pathname === "/knowledge" || window.location.pathname.startsWith("/knowledge/");

  useEffect(() => {
    if (reviewToken || isPrivacyPath || isTermsPath || isLandingPath || isKnowledgePath) {
      setAuthReady(true);
      return;
    }
    async function bootstrapAuth() {
      try {
        const response = await fetch(`${API_URL}/auth/me`, { credentials: "include" });
        const data = await response.json().catch(() => ({}));
        if (response.ok) {
          if (data.consent_required || data.consent_version !== CONSENT_VERSION) {
            setAccepted(false);
            setCookieConsentVisible(true);
          }
          setEmail(data.email);
          setUserId(data.id);
          setIsGuest(Boolean(data.is_guest));
          setAuthed(true);
          return;
        }
        if (data.detail?.code === "magic_link_required") {
          setEmail(data.detail.email || "");
          setAuthMode("login");
          setLoginNotice(data.detail.message || "Для безопасности подтвердите вход по ссылке из письма.");
          setAuthed(false);
          return;
        }
        const guestResponse = await fetch(`${API_URL}/auth/guest`, { method: "POST", credentials: "include" });
        const guest = await guestResponse.json();
        setEmail(guest.email || "");
        setUserId(guest.id);
        setIsGuest(true);
        setAuthed(true);
      } catch {
        setAuthed(false);
      } finally {
        setAuthReady(true);
      }
    }
    bootstrapAuth();
  }, [reviewToken, isPrivacyPath, isTermsPath, isLandingPath, isKnowledgePath]);

  async function acceptUnifiedConsent() {
    localStorage.setItem("ai-arbitr-consent-version", CONSENT_VERSION);
    setAccepted(true);
    setReviewForm((form) => ({ ...form, accepted: true }));
    setOwnerForm((form) => ({ ...form, accepted: true }));
    setCookieConsentVisible(false);
    if (authed && !reviewToken) {
      await fetch(`${API_URL}/auth/consent`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          service_rules_accepted: true,
          privacy_accepted: true,
          cookies_accepted: true,
          consent_version: CONSENT_VERSION,
        }),
      }).catch(() => undefined);
    }
  }

  const consentBanner = cookieConsentVisible && !isPrivacyPath && !isTermsPath && (
    <div className="consent-gate" role="dialog" aria-modal="true" aria-label="Согласие с правилами и cookies">
    <aside className="consent-banner">
      <div>
        <strong>{storedConsentVersion ? "Правила обновлены" : "Перед началом работы"}</strong>
        <p><ConsentText /></p>
      </div>
      <button type="button" onClick={acceptUnifiedConsent}>Принять и продолжить</button>
    </aside>
    </div>
  );

  useEffect(() => {
    if (!reviewToken) return;
    loadReview(reviewToken);
  }, [reviewToken]);

  useEffect(() => {
    if (!reviewFormOpen) return;
    window.requestAnimationFrame(() => reviewFormRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
  }, [reviewFormOpen]);

  useEffect(() => {
    if (!ownerSigningOpen) return;
    window.requestAnimationFrame(() => {
      ownerFormRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      ownerFormRef.current?.querySelector("input:not([type='checkbox'])")?.focus({ preventScroll: true });
    });
  }, [ownerSigningOpen]);

  useEffect(() => {
    localStorage.setItem("ai-arbitr-draft", draft);
  }, [draft]);

  useEffect(() => {
    localStorage.setItem("ai-arbitr-model", selectedModel);
  }, [selectedModel]);

  useEffect(() => {
    if (isGuest || partyEmail.trim().length < 2) {
      setEmailSuggestions([]);
      return undefined;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      try {
        const response = await fetch(`${API_URL}/contacts?q=${encodeURIComponent(partyEmail.trim())}`, {
          credentials: "include",
          signal: controller.signal,
        });
        const data = await response.json().catch(() => []);
        setEmailSuggestions(response.ok && Array.isArray(data) ? data : []);
      } catch (error) {
        if (error.name !== "AbortError") setEmailSuggestions([]);
      }
    }, 180);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [partyEmail, isGuest]);

  useEffect(() => {
    if (!toast) return undefined;
    const timer = window.setTimeout(() => setToast(""), 2200);
    return () => window.clearTimeout(timer);
  }, [toast]);

  useEffect(() => {
    if (!inviteConfirmation) return undefined;
    const timer = window.setTimeout(() => setInviteConfirmation(""), 9000);
    return () => window.clearTimeout(timer);
  }, [inviteConfirmation]);

  useEffect(() => {
    if (!authed) return;
    loadSessions();
  }, [authed]);

  useEffect(() => {
    if (!authed || isGuest || !sessions.length || pendingInviteResumeRef.current) return;
    const rawPendingInvite = localStorage.getItem(PENDING_INVITE_KEY);
    if (!rawPendingInvite) return;
    let pendingInvite;
    try {
      pendingInvite = JSON.parse(rawPendingInvite);
    } catch {
      localStorage.removeItem(PENDING_INVITE_KEY);
      return;
    }
    const targetSession = sessions.find((session) => session.id === pendingInvite.sessionId);
    if (!targetSession) return;
    pendingInviteResumeRef.current = true;
    sessionRestoreDoneRef.current = true;
    setCurrentSession(targetSession);
    setPartyEmail(pendingInvite.partyEmail || "");
    setCreatorLegalRole(pendingInvite.creatorLegalRole || "");
    setChatMode("agree");
    setAppNotice("Договор сохранен. Продолжаю отправку ссылки контрагенту...");
    sendInviteRequest(targetSession.id, pendingInvite.partyEmail, pendingInvite.creatorLegalRole).then((sent) => {
      if (sent) localStorage.removeItem(PENDING_INVITE_KEY);
      pendingInviteResumeRef.current = false;
    });
  }, [authed, isGuest, sessions]);

  useEffect(() => {
    if (!currentSession) return;
    const savedMode = localStorage.getItem(sessionModeKey(currentSession.id));
    setChatMode(["question", "add", "agree", "dispute"].includes(savedMode) ? savedMode : "idle");
    loadSession(currentSession.id);
  }, [currentSession?.id]);

  useEffect(() => {
    if (sessionRestoreDoneRef.current || !sessions.length) return;
    const requestedSessionId =
      new URLSearchParams(window.location.search).get("session") || localStorage.getItem(LAST_SESSION_KEY);
    sessionRestoreDoneRef.current = true;
    if (!requestedSessionId || currentSession?.id === requestedSessionId) return;
    const requestedSession = sessions.find((session) => session.id === requestedSessionId);
    if (requestedSession) {
      setCurrentSession(requestedSession);
    } else {
      localStorage.removeItem(LAST_SESSION_KEY);
    }
  }, [sessions]);

  useEffect(() => {
    if (!currentSession?.id || window.location.pathname !== "/") return;
    localStorage.setItem(LAST_SESSION_KEY, currentSession.id);
    const url = new URL(window.location.href);
    url.searchParams.set("session", currentSession.id);
    window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
  }, [currentSession?.id]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, thinking, appNotice, chatMode, questionResolved, ownerSigningOpen, sessionDetail?.latest_version?.id]);

  useEffect(() => {
    if (chatMode !== "agree") return;
    window.requestAnimationFrame(() => {
      agreementRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      agreementRef.current?.querySelector("select")?.focus({ preventScroll: true });
    });
  }, [chatMode]);

  function getReviewTokenFromPath() {
    const match = window.location.pathname.match(/^\/review\/([^/]+)$/);
    return match ? match[1] : "";
  }

  function reviewLegalTitle(contract, fallback) {
    const firstLine = (contract || "").split("\n").find((line) => line.trim()) || fallback || "Договор";
    return firstLine
      .replace(/^\s{0,3}#{1,6}\s*/, "")
      .replace(/\*\*/g, "")
      .replace(/\s*№\s*\S+.*$/i, "")
      .trim()
      .toLocaleLowerCase("ru-RU")
      .replace(/^./, (letter) => letter.toLocaleUpperCase("ru-RU"));
  }

  function reviewContractBody(contract) {
    const lines = (contract || "").split("\n");
    const firstContentLine = lines.findIndex((line) => line.trim());
    if (firstContentLine >= 0 && /договор/i.test(lines[firstContentLine])) {
      lines.splice(firstContentLine, 1);
    }
    return lines.join("\n").trim();
  }

  function formatReviewDate(value) {
    if (!value) return "";
    return new Intl.DateTimeFormat("ru-RU", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    }).format(new Date(value));
  }

  async function loadReview(token) {
    setReviewLoading(true);
    setReviewNotice("");
    try {
      const response = await fetch(`${API_URL}/review/${token}`);
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        setReviewNotice(apiErrorMessage(data.detail, "Ссылка согласования не найдена"));
        setReviewData(null);
        return;
      }
      setReviewData(data);
      if (data.party_email) {
        setReviewForm((form) => ({ ...form, email: form.email || data.party_email }));
      }
    } finally {
      setReviewLoading(false);
    }
  }

  async function approveReview(event) {
    event.preventDefault();
    if (!reviewToken || reviewSubmitting) return;
    setReviewNotice("");
    const demoDataLeft =
      reviewForm.fullName.trim() === "Иванов Иван Иванович" ||
      (reviewForm.partyType === "individual" && reviewForm.passport.trim() === DEMO_REVIEW_PASSPORT);
    if (
      demoDataLeft &&
      !window.confirm("В форме остались примерные ФИО или паспорт. Подписать с ними или сначала заменить на реальные данные?")
    ) {
      return;
    }
    setReviewSubmitting(true);
    try {
      const response = await fetch(`${API_URL}/review/${reviewToken}/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          party_type: reviewForm.partyType,
          full_name: reviewForm.fullName,
          passport: reviewForm.passport,
          phone: reviewForm.phone,
          inn: reviewForm.inn,
          ogrn: reviewForm.ogrn,
          organization_name: reviewForm.organizationName,
          email: reviewForm.email,
          personal_data_accepted: reviewForm.accepted,
          service_rules_accepted: reviewForm.accepted,
          cookies_accepted: reviewForm.accepted,
          consent_version: CONSENT_VERSION,
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        setReviewNotice(apiErrorMessage(data.detail, "Не удалось подписать договор"));
        reviewFormRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
        return;
      }
      const confirmation = `Вы подписали договор. Он направлен на подписание первой стороне: ${data.owner_email || "адрес первой стороны"}. После подписания первой стороной вам придет уведомление о заключении договора.`;
      setReviewNotice("");
      setReviewConfirmation({ title: "Договор подписан", message: confirmation });
      setReviewData((current) => ({
        ...current,
        finalized: Boolean(data.finalized),
        approved: true,
      }));
    } catch {
      setReviewNotice("Не удалось подписать договор. Проверьте подключение и попробуйте еще раз.");
    } finally {
      setReviewSubmitting(false);
    }
  }

  async function loadSession(sessionId) {
    const requestId = sessionLoadRequestRef.current + 1;
    sessionLoadRequestRef.current = requestId;
    setAppNotice("");
    const response = await fetch(`${API_URL}/sessions/${sessionId}`, { credentials: "include" });
    if (!response.ok || requestId !== sessionLoadRequestRef.current) return;
    const detail = await response.json();
    if (requestId !== sessionLoadRequestRef.current) return;
    setSessionDetail(detail);
    setCurrentSession((current) => (
      current?.id === detail.session?.id ? { ...current, ...detail.session } : detail.session
    ));
    setCreatorLegalRole(detail.session?.party_1_legal_role || "");
    setMessages(detail.messages || []);
  }

  async function loadSessions() {
    try {
      const response = await fetch(`${API_URL}/sessions`, { credentials: "include" });
      if (!response.ok) {
        setSessions([]);
        return;
      }
      const data = await response.json();
      setSessions(Array.isArray(data) ? data : []);
    } catch {
      setSessions([]);
    }
  }

  async function openStats() {
    setStatsOpen(true);
    setStatsLoading(true);
    try {
      const response = await fetch(`${API_URL}/stats`, { credentials: "include" });
      const data = await response.json().catch(() => ({}));
      if (response.ok) {
        setStats(data);
      } else {
        setToast(apiErrorMessage(data.detail, "Не удалось загрузить статистику"));
      }
    } catch {
      setToast("Не удалось загрузить статистику");
    } finally {
      setStatsLoading(false);
    }
  }

  async function login(event) {
    event.preventDefault();
    setLoginNotice("");
    setDevLink("");
    setAuthSubmitting(true);
    const endpoint =
      afterAuthAction === "invite" && isGuest && authMode === "register"
        ? "/auth/quick-register"
        : authMode === "register"
          ? "/auth/register"
          : "/auth/login";
    const payload = authMode === "register"
      ? {
          email,
          personal_data_accepted: accepted,
          service_rules_accepted: accepted,
          cookies_accepted: accepted,
          consent_version: CONSENT_VERSION,
        }
      : { email };
    try {
      const response = await fetch(`${API_URL}${endpoint}`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        setLoginNotice(apiErrorMessage(data.detail, "Не удалось отправить ссылку. Проверьте email и попробуйте еще раз."));
        return;
      }
      if (endpoint === "/auth/quick-register") {
        if (data.verification_required) {
          setLoginNotice(data.message || "Откройте ссылку из письма, чтобы сохранить договор и продолжить отправку.");
          setDevLink(data.dev_link || "");
          return;
        }
        setEmail(data.email || email);
        setUserId(data.id || userId);
        setIsGuest(false);
        setAuthed(true);
        setAuthPromptOpen(false);
        setAfterAuthAction("");
        setLoginNotice("");
        setAppNotice(`Шаг 1 готов: договор сохранен за ${data.email || email}. Шаг 2: отправляю ссылку второй стороне.`);
        const sent = await sendInviteRequest();
        if (sent) localStorage.removeItem(PENDING_INVITE_KEY);
        loadSessions();
        return;
      }
      setLoginNotice(data.message);
      setDevLink(data.dev_link || "");
    } finally {
      setAuthSubmitting(false);
    }
  }

  async function createSession() {
    setAppNotice("");
    setDeleteCandidateId("");
    const response = await fetch(`${API_URL}/sessions`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
    });
    const session = await response.json();
    setCurrentSession(session);
    setSessionDetail(null);
    setInviteLink("");
    setPartyEmail("");
    setChatMode("idle");
    setQuestionResolved(false);
    setExpandedSessionGroups(["draft"]);
    setSessionSearch("");
    setSessions([session, ...sessions]);
    setMessages([]);
    setSidebarOpen(false);
    setToast("Новый договор создан");
  }

  async function confirmDeleteSession(event, session) {
    event.stopPropagation();
    setDeleteCandidateId(session.id);
  }

  async function deleteSession(event, session) {
    event.stopPropagation();
    const response = await fetch(`${API_URL}/sessions/${session.id}`, {
      method: "DELETE",
      credentials: "include",
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      setAppNotice(apiErrorMessage(data.detail, "Не удалось удалить договор. Попробуйте еще раз."));
      return;
    }

    setSessions((items) => items.map((item) => (item.id === session.id ? { ...item, is_deleted: true } : item)));
    setDeleteCandidateId("");
    setToast("Договор перемещен в удаленные");
    loadSessions();
    if (currentSession?.id === session.id) {
      localStorage.removeItem(LAST_SESSION_KEY);
      window.history.replaceState({}, "", "/");
      setCurrentSession(null);
      setSessionDetail(null);
      setMessages([]);
      setInviteLink("");
      setAppNotice("");
    }
  }

  async function sendMessage() {
    if (!draft.trim() || !currentSession) return;
    const rawContent = draft.trim();
    const isContractUpdate = chatMode === "add";
    const isDispute = chatMode === "dispute";
    const isQuestion = chatMode === "question" || (hasContractVersion && chatMode === "idle");
    const isInitialContract = !hasContractVersion && !isContractUpdate && !isQuestion;
    const content = isContractUpdate
      ? `ДОПОЛНИТЬ ДОГОВОР: ${rawContent}`
      : isDispute
        ? `СПОР: ${rawContent}`
        : rawContent;
    const thinkingSteps = isContractUpdate
      ? ["Подготовка изменения", "Обновление версии", "Завершение"]
      : isQuestion
        ? ["Подготовка ответа", "Формирование ответа", "Завершение"]
        : isDispute
          ? ["Открытие спора", "Подготовка ответа", "Завершение"]
          : getThinkingSteps(rawContent);
    setDraft("");
    setQuestionResolved(false);
    setMessages((items) => [...items, { role: "user", content: rawContent }]);
    setThinking(true);
    setThinkingStep(thinkingSteps[0]);
    setThinkingProgress(8);
    let thinkingTimer;
    const thinkingStartedAt = Date.now();
    try {
      let stepIndex = 1;
      thinkingTimer = window.setInterval(() => {
        const cappedStepIndex = Math.min(stepIndex, thinkingSteps.length - 1);
        setThinkingStep(thinkingSteps[cappedStepIndex]);
        setThinkingProgress((current) => {
          const stepProgress = Math.round(((cappedStepIndex + 1) / thinkingSteps.length) * 86);
          return Math.min(92, Math.max(current + 3, stepProgress));
        });
        stepIndex += 1;
        if (stepIndex >= thinkingSteps.length) {
          setThinkingProgress((current) => Math.max(current, 92));
        }
      }, 1900);
      const response = await fetch(`${API_URL}/sessions/${currentSession.id}/messages`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content, model: selectedModel }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(apiErrorMessage(data.detail, "Не удалось получить ответ. Попробуйте отправить запрос еще раз."));
      }
      if (thinkingTimer) window.clearInterval(thinkingTimer);
      const minThinkingMs = isInitialContract ? MIN_INITIAL_THINKING_MS : MIN_REGULAR_THINKING_MS;
      const remainingThinkingMs = minThinkingMs - (Date.now() - thinkingStartedAt);
      if (remainingThinkingMs > 0) {
        await sleep(remainingThinkingMs);
      }
      setThinkingStep(thinkingSteps[thinkingSteps.length - 1]);
      setThinkingProgress(100);
      await sleep(450);
      setThinking(false);
      if (!isQuestion && data.reasoning) {
        setMessages((items) => [...items, { role: "system", content: data.reasoning || buildReasoningNote(thinkingSteps) }]);
      }
      if (isInitialContract) {
        await typeAssistantMessage(data.content);
      } else {
        setMessages((items) => [...items, { role: "assistant", content: data.content }]);
      }
      if (data.next_action === "choose_norm" || data.next_action === "email" || data.next_action === "sent") {
        setQuestionResolved(false);
      } else if (data.next_action === "agreement") {
        setQuestionResolved(false);
      } else if (isQuestion) {
        setQuestionResolved(true);
      }
      setChatMode("idle");
      localStorage.removeItem(sessionModeKey(currentSession.id));
      if (data.next_action === "sent") {
        if (data.invite_link) setInviteLink(data.invite_link);
        setAppNotice(
          data.sent_to
            ? `Ссылка отправлена на ${data.sent_to}. Копия письма отправлена на ${data.copy_to || "ваш email"}.`
            : "Ссылка отправлена второй стороне."
        );
        if (data.sent_to) {
          setInviteConfirmation(
            `Получатель: ${data.sent_to}. Попросите вторую сторону проверить почту. Письмо могло попасть в папку «Спам».`
          );
        }
      }
      loadSession(currentSession.id);
      loadSessions();
    } catch (error) {
      setMessages((items) => [
        ...items,
        {
          role: "assistant",
          content:
            error.message ||
            "Не удалось получить ответ. Попробуйте отправить запрос еще раз.",
        },
      ]);
    } finally {
      if (thinkingTimer) window.clearInterval(thinkingTimer);
      setThinking(false);
      setThinkingStep("");
      setThinkingProgress(0);
    }
  }

  async function typeAssistantMessage(content) {
    const chunkSize = Math.max(TYPEWRITER_CHUNK_SIZE, Math.ceil(content.length / TYPEWRITER_MAX_STEPS));
    setMessages((items) => [...items, { role: "assistant", content: "" }]);
    for (let index = 0; index < content.length; index += chunkSize) {
      const visibleContent = content.slice(0, index + chunkSize);
      setMessages((items) => {
        const nextItems = [...items];
        nextItems[nextItems.length - 1] = { role: "assistant", content: visibleContent };
        return nextItems;
      });
      await sleep(TYPEWRITER_DELAY_MS);
    }
  }

  async function sendInviteRequest(
    sessionId = currentSession?.id,
    recipientEmail = partyEmail,
    legalRole = creatorLegalRole,
  ) {
    if (!sessionId || inviteSending) return false;
    setInviteSending(true);
    setAppNotice(recipientEmail ? `Отправляю ссылку на ${recipientEmail}...` : "Готовлю ссылку согласования...");
    try {
      const response = await fetch(`${API_URL}/sessions/${sessionId}/invite`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: recipientEmail || null,
          creator_legal_role: legalRole,
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        setAppNotice(apiErrorMessage(data.detail, "Не удалось отправить ссылку согласования."));
        return false;
      }
      setInviteLink(data.invite_link);
      setAppNotice(
        data.sent
          ? `Ссылка отправлена на ${data.sent_to || recipientEmail}. Копия письма отправлена на ${data.copy_to || "ваш email"}.`
          : "SMTP пока не настроен. Скопируйте ссылку просмотра и отправьте второй стороне вручную."
      );
      if (data.sent) {
        setInviteConfirmation(
          `Получатель: ${data.sent_to || recipientEmail}. Попросите вторую сторону проверить почту. Письмо могло попасть в папку «Спам».`
        );
      }
      loadSession(sessionId);
      loadSessions();
      return true;
    } finally {
      setInviteSending(false);
    }
  }

  async function createInvite() {
    if (!partyEmail.trim()) {
      setAppNotice("Введите email второй стороны, чтобы отправить ссылку согласования.");
      return;
    }
    if (!creatorLegalRole) {
      setAppNotice("Выберите, кем вы выступаете в договоре.");
      return;
    }
    if (isGuest) {
      localStorage.setItem(PENDING_INVITE_KEY, JSON.stringify({
        sessionId: currentSession.id,
        partyEmail: partyEmail.trim(),
        creatorLegalRole,
      }));
      setAuthMode("register");
      setAfterAuthAction("invite");
      setAuthPromptTitle("Шаг 1. Сохранить договор");
      setAuthPromptCopy(
        `Сначала привяжем этот договор к вашей почте. Это не письмо второй стороне. После сохранения я отдельным шагом отправлю ссылку согласования на ${partyEmail.trim()}.`
      );
      setAuthPromptOpen(true);
      setLoginNotice("");
      return;
    }
    await sendInviteRequest();
  }

  function startQuestion() {
    setAppNotice("");
    setChatMode("question");
    if (currentSession) localStorage.setItem(sessionModeKey(currentSession.id), "question");
    setDraft("");
    setQuestionResolved(false);
    setToast("Режим вопроса включен");
  }

  function startAddition() {
    setAppNotice("");
    setChatMode("add");
    if (currentSession) localStorage.setItem(sessionModeKey(currentSession.id), "add");
    setDraft("");
    setQuestionResolved(false);
    setToast("Режим добавления условия включен");
  }

  function startAgreement() {
    setAppNotice("");
    setChatMode("agree");
    if (currentSession) localStorage.setItem(sessionModeKey(currentSession.id), "agree");
    setQuestionResolved(false);
  }

  function startDispute() {
    setAppNotice("");
    setChatMode("dispute");
    if (currentSession) localStorage.setItem(sessionModeKey(currentSession.id), "dispute");
    setDraft("");
    setQuestionResolved(false);
    setToast("Режим спора включен");
  }

  function showCurrentContract(term) {
    setContractPreviewOpen(true);
    setToast(term ? `Открыл текущую версию: ${term.label}` : "Открыл текущую версию договора");
  }

  function goBack() {
    if (authPromptOpen) {
      setAuthPromptOpen(false);
      setAfterAuthAction("");
      return true;
    }
    if (helpOpen) {
      setHelpOpen(false);
      return true;
    }
    if (aboutOpen) {
      setAboutOpen(false);
      return true;
    }
    if (statsOpen) {
      setStatsOpen(false);
      return true;
    }
    if (sidebarOpen) {
      setSidebarOpen(false);
      return true;
    }
    if (contractPreviewOpen) {
      setContractPreviewOpen(false);
      return true;
    }
    if (currentSession) {
      localStorage.removeItem(LAST_SESSION_KEY);
      window.history.replaceState({}, "", "/");
      setCurrentSession(null);
      setSessionDetail(null);
      setMessages([]);
      setInviteLink("");
      setChatMode("idle");
      return true;
    }
    return false;
  }

  function closeOverlay() {
    if (authPromptOpen || helpOpen || aboutOpen || statsOpen || sidebarOpen || contractPreviewOpen) {
      goBack();
      return true;
    }
    return false;
  }

  function handleTouchStart(event) {
    const touch = event.changedTouches?.[0];
    if (!touch) return;
    gestureRef.current = { x: touch.clientX, y: touch.clientY };
  }

  function handleTouchEnd(event) {
    const touch = event.changedTouches?.[0];
    if (!touch) return;
    const dx = touch.clientX - gestureRef.current.x;
    const dy = touch.clientY - gestureRef.current.y;
    if (Math.abs(dx) < 70 || Math.abs(dx) < Math.abs(dy) * 1.25) return;
    if (dx > 0) {
      goBack();
    } else {
      closeOverlay();
    }
  }

  function downloadCertificate() {
    if (!currentSession) return;
    setToast("Открываю справку");
    window.open(`${API_URL}/sessions/${currentSession.id}/certificate.pdf`, "_blank", "noopener,noreferrer");
  }

  async function signAsFirstParty(event) {
    event.preventDefault();
    if (!currentSession || ownerSubmitting) return;
    const demoDataLeft =
      ownerForm.fullName.trim() === "Петров Петр Петрович" ||
      (ownerForm.partyType === "individual" && ownerForm.passport.trim() === DEMO_REVIEW_PASSPORT);
    if (demoDataLeft && !window.confirm("В форме остались примерные реквизиты. Подписать с ними или сначала заменить на реальные данные?")) {
      return;
    }
    setOwnerSubmitting(true);
    try {
      const response = await fetch(`${API_URL}/sessions/${currentSession.id}/approve`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          party_type: ownerForm.partyType,
          full_name: ownerForm.fullName,
          passport: ownerForm.passport,
          phone: ownerForm.phone,
          inn: ownerForm.inn,
          ogrn: ownerForm.ogrn,
          organization_name: ownerForm.organizationName,
          email,
          personal_data_accepted: ownerForm.accepted,
          service_rules_accepted: ownerForm.accepted,
          cookies_accepted: ownerForm.accepted,
          consent_version: CONSENT_VERSION,
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        setAppNotice(apiErrorMessage(data.detail, "Не удалось подписать договор."));
        return;
      }
      setOwnerSigningOpen(false);
      setInviteConfirmation(
        data.finalized
          ? "Договор подписан обеими сторонами. Финальный PDF и справка направлены на email сторон."
          : "Ваша подпись зафиксирована."
      );
      setAppNotice(data.finalized ? "Договор подписан обеими сторонами." : "Подпись зафиксирована.");
      loadSession(currentSession.id);
      loadSessions();
    } finally {
      setOwnerSubmitting(false);
    }
  }

  async function markCompleted() {
    if (!currentSession) return;
    const response = await fetch(`${API_URL}/sessions/${currentSession.id}/complete`, {
      method: "POST",
      credentials: "include",
    });
    const data = await response.json().catch(() => ({}));
    setAppNotice(response.ok ? data.message : apiErrorMessage(data.detail, "Не удалось отметить исполнение."));
    loadSession(currentSession.id);
  }

  const hasContractVersion = Boolean(sessionDetail?.latest_version);
  const isFinalized = currentSession?.status === "finalized";
  const chatSuggestions = composerFocused && !thinking
    ? getChatSuggestions({
        query: draft,
        mode: chatMode,
        hasVersion: hasContractVersion,
        contractTypeId: sessionDetail?.contract_type?.id,
      })
    : [];
  const sessionSearchSuggestions = sessionSearchFocused
    ? getSessionSearchSuggestions(sessions, sessionSearch)
    : [];
  const normalizedSessionSearch = sessionSearch.trim().toLowerCase();
  const matchesSessionSearch = (session) => {
    if (!normalizedSessionSearch) return true;
    const searchableText = [
      session.title,
      session.party_2_email,
      getSessionStatusLabel(session),
      formatSessionTimestamp(session),
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return searchableText.includes(normalizedSessionSearch);
  };
  const sessionsByGroup = SESSION_FILTERS.reduce((acc, filter) => {
    acc[filter.id] = sessions.filter((session) => getSessionBucket(session) === filter.id && matchesSessionSearch(session));
    return acc;
  }, {});
  const partyTwoSigned = (sessionDetail?.participants || []).some(
    (participant) => participant.role === "party_2" && participant.approval_status === "approved"
  );
  const partyOneSigned = (sessionDetail?.participants || []).some(
    (participant) => participant.role === "party_1" && participant.approval_status === "approved"
  );
  const currentParticipant = (sessionDetail?.participants || []).find(
    (participant) => participant.user_id === userId
  );
  const completionConfirmed = Boolean(currentParticipant?.completed_at);
  const isEmptySession = currentSession && messages.length === 0 && !thinking && !appNotice;
  const composerPlaceholder =
    chatMode === "question"
      ? getQuestionPlaceholder(currentSession, sessionDetail)
      : chatMode === "add"
        ? getAdditionPlaceholder(currentSession, sessionDetail)
        : chatMode === "dispute"
          ? "Опишите, что произошло: кто, когда, какое условие нарушил"
          : messages.length === 0 && !hasContractVersion
            ? "Например: составь договор найма квартиры"
            : "Напишите сообщение";
  const composerHint = hasContractVersion
    ? "Можно задать вопрос, добавить условие или написать email второй стороны для согласования"
    : "Напишите коротко, какой договор нужно составить";

  if (isLandingPath) {
    return <><LandingPage />{consentBanner}</>;
  }

  if (isKnowledgePath) {
    return <><KnowledgeBase />{consentBanner}</>;
  }

  if (!authReady) {
    return (
      <main className="login-page">
        <div className="login-form">
          <h1>AI-Арбитр</h1>
          <p className="notice">Загружаю рабочее пространство...</p>
        </div>
      </main>
    );
  }

  if (isPrivacyPath) {
    return <PrivacyPage />;
  }

  if (isTermsPath) {
    return <TermsPage />;
  }

  if (reviewToken) {
    return (
      <main className="review-page">
        {consentBanner}
        {reviewConfirmation && (
          <div className="invite-confirmation" role="status" aria-live="polite">
            <div>
              <strong>{reviewConfirmation.title}</strong>
              <p>{reviewConfirmation.message}</p>
            </div>
            <button type="button" onClick={() => setReviewConfirmation(null)} aria-label="Закрыть уведомление">
              ×
            </button>
          </div>
        )}
        <section className="review-shell">
          <header className="review-header">
            <LogoMark compact />
            {reviewData && (
              <>
                <h1>{reviewLegalTitle(reviewData.contract, reviewData.title)}</h1>
                <p>Версия № {reviewData.version_number} от {formatReviewDate(reviewData.version_created_at)}</p>
              </>
            )}
          </header>
          {reviewLoading && <p className="notice">Загружаю договор...</p>}
          {reviewNotice && <p className="app-notice">{reviewNotice}</p>}
          {reviewData && (
            <>
              <article className="review-contract">{reviewContractBody(reviewData.contract)}</article>
              {reviewData.approved || reviewData.finalized ? (
                <div className="review-approved">
                  <Check size={18} /> Подпись уже зафиксирована.
                </div>
              ) : !reviewFormOpen ? (
                <button
                  className="review-agree-button"
                  type="button"
                  onClick={() => {
                    setReviewFormOpen(true);
                    setReviewConfirmation({
                      title: "Проверка реквизитов",
                      message: "Проверьте реквизиты и при необходимости исправьте примерные данные. Все верно?",
                    });
                  }}
                >
                  <Check size={17} /> Подписать
                </button>
              ) : (
                <form className="review-form" onSubmit={approveReview} ref={reviewFormRef}>
                  <h2>Ваши данные · {reviewData.legal_role || "сторона договора"}</h2>
                  <div className="party-type-switch" aria-label="Тип стороны">
                    <button
                      type="button"
                      className={reviewForm.partyType === "individual" ? "active" : ""}
                      onClick={() => setReviewForm((form) => ({ ...form, partyType: "individual" }))}
                    >
                      Физлицо
                    </button>
                    <button
                      type="button"
                      className={reviewForm.partyType === "business" ? "active" : ""}
                      onClick={() => setReviewForm((form) => ({ ...form, partyType: "business" }))}
                    >
                      Организация / ИП
                    </button>
                  </div>
                  {reviewForm.partyType === "business" && (
                    <input
                      value={reviewForm.organizationName}
                      onChange={(event) => setReviewForm((form) => ({ ...form, organizationName: event.target.value }))}
                      placeholder={FORM_HINTS.organization}
                      autoComplete="organization"
                      required
                    />
                  )}
                  <input
                    value={reviewForm.fullName}
                    onChange={(event) => setReviewForm((form) => ({ ...form, fullName: event.target.value }))}
                    placeholder={reviewForm.partyType === "business" ? FORM_HINTS.signerName : FORM_HINTS.fullName}
                    autoComplete="name"
                    required
                  />
                  {reviewForm.partyType === "individual" ? (
                  <input
                    value={reviewForm.passport}
                    onChange={(event) => setReviewForm((form) => ({ ...form, passport: event.target.value }))}
                    placeholder={FORM_HINTS.passport}
                    autoComplete="off"
                    inputMode="numeric"
                    pattern="[0-9]{4} ?[0-9]{6}"
                    required
                  />
                  ) : (
                    <>
                      <input
                        value={reviewForm.inn}
                        onChange={(event) => setReviewForm((form) => ({ ...form, inn: event.target.value }))}
                        placeholder={FORM_HINTS.inn}
                        inputMode="numeric"
                        pattern="[0-9]{10}|[0-9]{12}"
                        required
                      />
                      <input
                        value={reviewForm.ogrn}
                        onChange={(event) => setReviewForm((form) => ({ ...form, ogrn: event.target.value }))}
                        placeholder={FORM_HINTS.ogrn}
                        inputMode="numeric"
                        pattern="[0-9]{13}|[0-9]{15}"
                        required
                      />
                    </>
                  )}
                  <input
                    value={reviewForm.phone}
                    onChange={(event) => setReviewForm((form) => ({ ...form, phone: event.target.value }))}
                    placeholder={FORM_HINTS.phone}
                    autoComplete="tel"
                    required
                  />
                  <input
                    value={reviewForm.email}
                    placeholder={FORM_HINTS.email}
                    autoComplete="email"
                    readOnly
                    aria-readonly="true"
                    required
                  />
                  <label className="checkbox-row">
                    <input
                      type="checkbox"
                      checked={reviewForm.accepted}
                      onChange={(event) => setReviewForm((form) => ({ ...form, accepted: event.target.checked }))}
                      required
                    />
                    <ConsentText />
                  </label>
                  <button disabled={reviewSubmitting}>
                    <Check size={16} /> {reviewSubmitting ? "Подписываю..." : "Подписать"}
                  </button>
                </form>
              )}
            </>
          )}
        </section>
      </main>
    );
  }

  if (!authed) {
    return (
      <main className="login-page">
        {consentBanner}
        <form className="login-form" onSubmit={login}>
          <h1>AI-Арбитр</h1>
          <div className="auth-switch" role="tablist" aria-label="Регистрация или вход">
            <button
              type="button"
              className={authMode === "register" ? "active" : ""}
              onClick={() => {
                setAuthMode("register");
                setLoginNotice("");
                setDevLink("");
              }}
            >
              Регистрация
            </button>
            <button
              type="button"
              className={authMode === "login" ? "active" : ""}
              onClick={() => {
                setAuthMode("login");
                setLoginNotice("");
                setDevLink("");
              }}
            >
              Вход
            </button>
          </div>
          <input value={email} onChange={(event) => setEmail(event.target.value)} placeholder={FORM_HINTS.email} />
          {authMode === "register" && (
            <label className="checkbox-row">
              <input type="checkbox" checked={accepted} onChange={(event) => setAccepted(event.target.checked)} />
              <ConsentText />
            </label>
          )}
          <button>{authMode === "register" ? "Зарегистрироваться" : "Отправить ссылку для входа"}</button>
          {loginNotice && <p className="notice">{loginNotice}</p>}
          {devLink && (
            <a className="dev-link" href={devLink}>
              Dev-вход без SMTP
            </a>
          )}
          <a href="/privacy">Политика конфиденциальности</a>
        </form>
      </main>
    );
  }

  return (
    <main className="app-shell" onTouchStart={handleTouchStart} onTouchEnd={handleTouchEnd}>
      {consentBanner}
      <div className="mobile-topbar">
        <button className="mobile-menu" onClick={() => setSidebarOpen(true)} aria-label="Открыть меню">
          <Menu size={20} />
        </button>
        <ModelSelector
          selectedModel={selectedModel}
          onChange={(model) => {
            setSelectedModel(model);
            setToast(model === "qwen" ? "Включен Qwen 2.5" : "Включен YandexGPT 5.1 Pro");
          }}
        />
        <button className="mobile-stat" onClick={openStats} aria-label="Статистика сервиса">
          <BarChart3 size={20} />
        </button>
      </div>
      {sidebarOpen && (
        <button
          className="sidebar-backdrop"
          onClick={() => setSidebarOpen(false)}
          onTouchStart={handleTouchStart}
          onTouchEnd={handleTouchEnd}
          aria-label="Закрыть меню"
        />
      )}
      {authPromptOpen && (
        <div className="auth-modal-backdrop" onTouchStart={handleTouchStart} onTouchEnd={handleTouchEnd}>
          <form className="login-form auth-modal" onSubmit={login}>
            <h1>{authPromptTitle}</h1>
            <p className="auth-copy">{authPromptCopy}</p>
            {afterAuthAction === "invite" && (
              <div className="auth-steps" aria-label="Шаги отправки ссылки">
                <div className="auth-step active">
                  <span>1</span>
                  <div>
                    <strong>Сохранить вашу сессию</strong>
                    <p>Договор будет привязан к вашей почте, чтобы не потерять историю.</p>
                  </div>
                </div>
                <div className="auth-step">
                  <span>2</span>
                  <div>
                    <strong>Отправить ссылку второй стороне</strong>
                    <p>{partyEmail.trim() || "Email второй стороны будет использован на следующем шаге."}</p>
                  </div>
                </div>
              </div>
            )}
            <input value={email} onChange={(event) => setEmail(event.target.value)} placeholder={FORM_HINTS.email} />
            <label className="checkbox-row">
              <input type="checkbox" checked={accepted} onChange={(event) => setAccepted(event.target.checked)} />
              <ConsentText />
            </label>
            <button disabled={authSubmitting}>
              {authSubmitting
                ? "Сохраняю..."
                : afterAuthAction === "invite"
                  ? "Сохранить мою сессию"
                  : "Отправить ссылку для входа"}
            </button>
            {loginNotice && <p className="notice">{loginNotice}</p>}
            {devLink && (
              <a className="dev-link" href={devLink}>
                Dev-вход без SMTP
              </a>
            )}
            <button
              className="modal-secondary"
              type="button"
              onClick={() => {
                setAuthPromptOpen(false);
                setAfterAuthAction("");
              }}
            >
              Отмена
            </button>
          </form>
        </div>
      )}
      {helpOpen && (
        <div className="auth-modal-backdrop" onTouchStart={handleTouchStart} onTouchEnd={handleTouchEnd}>
          <section className="help-modal">
            <h1>Что умеет MVP</h1>
            <p>
              MVP убедительно отрабатывает типовой сценарий договора найма жилого помещения:
              подготовка проекта, вопросы по условиям, добавление положений, отправка второй стороне,
              подписание двумя сторонами, финальный PDF и открытие спора.
            </p>
            <h2>Основной сценарий</h2>
            <ul>
              <li>Составьте договор найма жилого помещения.</li>
              <li>Проверьте карточку ключевых условий и текст договора.</li>
              <li>Задайте мне вопросы или добавьте новое условие.</li>
              <li>Отправьте ссылку второй стороне на email.</li>
              <li>Вторая сторона подписывает договор по ссылке.</li>
              <li>Первая сторона подписывает договор в своем чате.</li>
              <li>Формируется PDF с отметками простой электронной подписи.</li>
            </ul>
            <h2>Другие договоры</h2>
            <p>
              Договоры подряда, услуг, разработки сайта и похожие документы генерируются
              по упрощенному промту. Это рабочий черновик для обсуждения, а не такой же
              глубоко проработанный сценарий, как найм жилого помещения.
            </p>
            <h2>После подписания</h2>
            <p>
              Подписанные договоры попадают в архив и защищены от удаления. В чате остаются
              действия «Открыть спор» и «Договор исполнен».
            </p>
            <h2>FAQ</h2>
            <div className="faq-list">
              <details>
                <summary>Как удостовериться, что AI-Arbitr не включил в договор невыгодные для меня условия?</summary>
                <p>
                  Промпты и код проекта открыты на GitHub: https://github.com/avnamchuk-afk/AI-Arbitr.
                  В логике сервиса прямо заложен баланс интересов сторон: договор не должен превращаться
                  в инструмент давления одной стороны на другую. Мы тестируем генерацию и фиксируем ключевые
                  формулировки, чтобы снижать риск галлюцинаций и не пропускать явно чрезмерные условия,
                  например неустойку 300%.
                </p>
              </details>
              <details>
                <summary>Имеет ли договор юридическую силу?</summary>
                <p>
                  Да, если стороны согласовали условия и подтвердили согласие. Финальный PDF содержит текст
                  договора и отметки простой электронной подписи. Дополнительно формируется справка о факте
                  электронного взаимодействия, которую можно сохранить вместе с договором.
                </p>
              </details>
              <details>
                <summary>Почему второй стороне не дают бесконечно править договор в MVP?</summary>
                <p>
                  MVP специально упрощен: вторая сторона смотрит проект, вводит свои данные и либо подписывает,
                  либо не подписывает. Циклическое согласование версий будет добавлено позже, чтобы не усложнять
                  первый пользовательский путь.
                </p>
              </details>
              <details>
                <summary>Что делать, если AI ошибся или условие выглядит странно?</summary>
                <p>
                  Задайте вопрос прямо в чате. AI-Arbitr должен объяснить, есть ли условие в договоре, какая
                  норма ГК применяется и стоит ли уточнить договор. Если риск сохраняется, можно добавить новое
                  условие и выбрать краткую или расширенную редакцию.
                </p>
              </details>
              <details>
                <summary>Что происходит с персональными данными?</summary>
                <p>
                  Полные данные используются для формирования финального PDF и отправки сторонам. После этого
                  сервис хранит только технические сведения, UID, хэши и маскированные данные, необходимые для
                  истории договора и доказательственной базы.
                </p>
              </details>
              <details>
                <summary>Зачем нужен AI-Arbitr после подписания договора?</summary>
                <p>
                  После подписания сервис помогает не забыть договорные события, сохранить финальный PDF,
                  открыть спор и зафиксировать результат исполнения. Идея в том, чтобы договор не лежал мертвым
                  файлом, а сопровождал стороны до завершения отношений.
                </p>
              </details>
            </div>
            <button className="modal-secondary" type="button" onClick={() => setHelpOpen(false)}>
              Закрыть
            </button>
          </section>
        </div>
      )}
      {aboutOpen && (
        <div
          className="auth-modal-backdrop"
          onClick={() => setAboutOpen(false)}
          onTouchStart={handleTouchStart}
          onTouchEnd={handleTouchEnd}
        >
          <section className="help-modal about-modal" onClick={(event) => event.stopPropagation()}>
            <LogoMark compact />
            <span className="app-version">Версия {APP_VERSION}</span>
            <h1>AI-Arbitr помогает пройти договор до конца</h1>
            <p>
              Это не просто генератор текста. Я веду пользователя по шагам: проект договора,
              вопросы, новые условия, согласование, подписание, PDF и спор, если он возникнет.
            </p>
            <div className="about-grid">
              <button
                type="button"
                onClick={() => {
                  setAboutOpen(false);
                  createSession();
                }}
              >
                <Plus size={16} /> Новый договор
              </button>
              <button
                type="button"
                onClick={() => {
                  setAboutOpen(false);
                  setHelpOpen(true);
                }}
              >
                <FileText size={16} /> Сценарий MVP
              </button>
            </div>
            <ul className="about-list">
              <li>В договоры добавляются вымышленные данные, чтобы текст сразу выглядел живым.</li>
              <li>После вопросов можно добавить краткую или расширенную редакцию условия.</li>
              <li>Финальный договор и справка электронного взаимодействия уходят сторонам на email.</li>
            </ul>
            <section className="technical-section">
              <h2>Техническое описание</h2>
              <dl className="technical-list">
                <div>
                  <dt>Исходный код</dt>
                  <dd><a href="https://github.com/avnamchuk-afk/AI-Arbitr" target="_blank" rel="noreferrer">GitHub · MIT License</a></dd>
                </div>
                <div>
                  <dt>Инфраструктура</dt>
                  <dd>Yandex Cloud · Docker · Nginx · PostgreSQL</dd>
                </div>
                <div>
                  <dt>Нейросети</dt>
                  <dd>YandexGPT 5.1 Pro и Qwen 2.5 7B Instruct через Foundation Models API</dd>
                </div>
                <div>
                  <dt>Шрифт</dt>
                  <dd>ALS Staromoskovsky Regular 3.1 · Студия Артемия Лебедева · бессрочная лицензия владельца проекта</dd>
                </div>
                <div>
                  <dt>Версия</dt>
                  <dd>{APP_VERSION}</dd>
                </div>
                <div>
                  <dt>Обратная связь</dt>
                  <dd><a href={SUPPORT_MAILTO}>{SUPPORT_EMAIL}</a></dd>
                </div>
              </dl>
            </section>
            <section className="team-section">
              <h2>Команда проекта</h2>
              <p>Технологии, право, финансы и поведенческая психология в одной команде.</p>
              <div className="team-grid">
                {PROJECT_TEAM.map((member) => (
                  <article className="team-card" key={member.name}>
                    <strong>{member.name}</strong>
                    <span>{member.role}</span>
                    <p>{member.text}</p>
                    <div className="team-links" aria-label={`Контакты: ${member.name}`}>
                      <button type="button">Max</button>
                      <button type="button">TG</button>
                      <button type="button">WA</button>
                      <button type="button">VK</button>
                    </div>
                  </article>
                ))}
              </div>
            </section>
            <button className="modal-secondary" type="button" onClick={() => setAboutOpen(false)}>
              Понятно
            </button>
          </section>
        </div>
      )}
      {statsOpen && (
        <div
          className="auth-modal-backdrop"
          onClick={() => setStatsOpen(false)}
          onTouchStart={handleTouchStart}
          onTouchEnd={handleTouchEnd}
        >
          <section className="help-modal stats-modal" onClick={(event) => event.stopPropagation()}>
            <div className="stats-head">
              <BarChart3 size={22} />
              <h1>Статистика AI-Arbitr</h1>
            </div>
            {statsLoading ? (
              <p>Загружаю статистику...</p>
            ) : (
              <div className="stats-grid">
                <div>
                  <span>{stats?.users ?? 0}</span>
                  <small>пользователей</small>
                </div>
                <div>
                  <span>{stats?.generated_contracts ?? 0}</span>
                  <small>сгенерировано</small>
                </div>
                <div>
                  <span>{stats?.signed_contracts ?? 0}</span>
                  <small>подписано</small>
                </div>
                <div>
                  <span>{stats?.disputed_contracts ?? 0}</span>
                  <small>оспорено</small>
                </div>
                <div>
                  <span>{stats?.closed_without_dispute_contracts ?? 0}</span>
                  <small>исполнено без спора</small>
                </div>
              </div>
            )}
            <p>Показываются только агрегированные числа без персональных данных.</p>
            <button className="modal-secondary" type="button" onClick={() => setStatsOpen(false)}>
              Закрыть
            </button>
          </section>
        </div>
      )}
      <aside className={sidebarOpen ? "sidebar open" : "sidebar"}>
        <div className="account">
          {!isGuest && <strong>{email}</strong>}
          {isGuest ? (
            <button
              onClick={() => {
                setAuthMode("login");
                setAuthPromptTitle("Вход");
                setAuthPromptCopy("Укажите email, чтобы войти, сохранить историю и продолжить работу с договорами.");
                setLoginNotice("");
                setAuthPromptOpen(true);
              }}
            >
              Вход
            </button>
          ) : (
            <button
              onClick={() => {
                localStorage.removeItem(LAST_SESSION_KEY);
                window.history.replaceState({}, "", "/");
                fetch(`${API_URL}/auth/logout`, { method: "POST", credentials: "include" })
                  .then(() => fetch(`${API_URL}/auth/guest`, { method: "POST", credentials: "include" }))
                  .then((res) => res.json())
                  .then((user) => {
                    setEmail(user.email || "");
                    setUserId(user.id);
                    setIsGuest(true);
                    setAuthed(true);
                    setSessions([]);
                    setCurrentSession(null);
                    loadSessions();
                  });
              }}
            >
              <LogOut size={16} /> Выход
            </button>
          )}
        </div>
        <button className="new-contract" onClick={createSession}>
          <Plus size={18} /> Новый договор
        </button>
        <div className="session-search-wrap">
          <label className="session-search">
            <Search size={15} />
            <input
              value={sessionSearch}
              onChange={(event) => setSessionSearch(event.target.value)}
              onFocus={() => setSessionSearchFocused(true)}
              onBlur={() => setSessionSearchFocused(false)}
              placeholder={FORM_HINTS.sessionSearch}
              autoComplete="off"
            />
          </label>
          <SuggestionList
            items={sessionSearchSuggestions}
            label="Ваши договоры"
            onSelect={(session) => {
              setCurrentSession(session);
              setSessionSearch("");
              setSessionSearchFocused(false);
              setInviteLink("");
              setDeleteCandidateId("");
              setSidebarOpen(false);
            }}
          />
        </div>
        <div className="session-tabs" role="list" aria-label="Список договоров">
          {SESSION_FILTERS.map((filter) => {
            const visibleCount = sessionsByGroup[filter.id].length;
            const isExpanded = expandedSessionGroups.includes(filter.id);
            return (
              <section className="session-group" key={filter.id}>
                <button
                  className={isExpanded ? "active" : ""}
                  disabled={!visibleCount}
                  onClick={() => {
                    if (!visibleCount) return;
                    setExpandedSessionGroups((groups) =>
                      groups.includes(filter.id)
                        ? groups.filter((group) => group !== filter.id)
                        : [...groups, filter.id]
                    );
                  }}
                  type="button"
                >
                  <span className="session-group-title">
                    {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    {filter.label}
                  </span>
                  <span className={visibleCount ? "session-count has-items" : "session-count"}>
                    {visibleCount}
                  </span>
                </button>
                {isExpanded && (
                <div className="session-list">
                  {sessionsByGroup[filter.id].length === 0 ? (
                    <p className="session-empty">
                      {normalizedSessionSearch ? "Поиск ничего не нашел." : "В этой категории пока нет договоров."}
                    </p>
                  ) : (
                    sessionsByGroup[filter.id].map((session) => (
                      <div key={session.id} className="session-item">
                        <button
                          className="session-open"
                          onClick={() => {
                            setCurrentSession(session);
                            setInviteLink("");
                            setDeleteCandidateId("");
                            setSidebarOpen(false);
                          }}
                        >
                          <span className="session-type-icon">
                            {React.createElement(getSessionIcon(session), { size: 17 })}
                          </span>
                          <span className="session-compact">
                            <strong>{getSessionCounterparty(session)}</strong>
                            <small>
                              {formatSessionTimestamp(session)} · {getSessionStatusLabel(session)}
                            </small>
                          </span>
                        </button>
                        {session.status === "finalized" || session.is_deleted ? null : deleteCandidateId === session.id ? (
                          <div className="delete-confirm">
                            <button className="delete-yes" onClick={(event) => deleteSession(event, session)}>
                              Удалить
                            </button>
                            <button
                              className="delete-no"
                              onClick={(event) => {
                                event.stopPropagation();
                                setDeleteCandidateId("");
                              }}
                            >
                              Отмена
                            </button>
                          </div>
                        ) : (
                          <button className="delete-session" onClick={(event) => confirmDeleteSession(event, session)} aria-label="Удалить чат">
                            <Trash2 size={16} />
                          </button>
                        )}
                      </div>
                    ))
                  )}
                </div>
              )}
            </section>
            );
          })}
        </div>
        <div className="sidebar-footer">
          <button onClick={() => setHelpOpen(true)}>Помощь / FAQ</button>
          <a href={SUPPORT_MAILTO}>Обратная связь · {SUPPORT_EMAIL}</a>
        </div>
      </aside>
      <section className="chat-area">
        {toast && <div className="toast">{toast}</div>}
        {inviteConfirmation && (
          <div className="invite-confirmation" role="status" aria-live="polite">
            <div>
              <strong>{inviteConfirmation.startsWith("Договор подписан") ? "Договор подписан" : "Ссылка направлена"}</strong>
              <p>{inviteConfirmation}</p>
            </div>
            <button type="button" onClick={() => setInviteConfirmation("")} aria-label="Закрыть уведомление">
              ×
            </button>
          </div>
        )}
        {!currentSession ? (
          <div className="empty-state">
            <LogoMark onClick={() => setAboutOpen(true)} />
            <strong className="hero-offer">Бесплатно в смартфоне</strong>
            <div className="hero-flow" aria-label="Клиентский путь AI-Arbitr">
              <span>Составить</span>
              <i aria-hidden="true">→</i>
              <span>Согласовать</span>
              <i aria-hidden="true">→</i>
              <span>Подписать договор</span>
              <i aria-hidden="true">→</i>
              <span>Разрешить спор</span>
            </div>
            <button onClick={createSession}>
              <Plus size={18} /> Новый договор
            </button>
          </div>
        ) : (
          <div className={isEmptySession ? "session-stage start-session" : "session-stage active-session"}>
            <div className="chat-thread">
              <div className="messages">
                {messages.map((message, index) => {
                  const historyEvent = getHistoryEvent(message);
                  if (historyEvent) {
                    return (
                      <article key={index} className="history-event">
                        <strong>{historyEvent.title}</strong>
                        {historyEvent.meta && <span>{historyEvent.meta}</span>}
                      </article>
                    );
                  }
                  return (
                    <article key={index} className={`message ${message.role}`}>
                      <div className="message-body">
                        {message.role === "system" ? <em>{message.content}</em> : message.content}
                      </div>
                      <MessageActions message={message} onToast={setToast} />
                    </article>
                  );
                })}
                {thinking && (
                  <article className="message assistant thinking">
                    <div className="thinking-head">
                      <span>Генерация ответа</span>
                      <strong>{thinkingProgress}%</strong>
                    </div>
                    <div className="thinking-bar" aria-hidden="true">
                      <i style={{ width: `${thinkingProgress}%` }} />
                    </div>
                    <p>{thinkingStep || "Подготовка"}</p>
                  </article>
                )}
                {hasContractVersion && contractPreviewOpen && (
                  <section className="message assistant contract-preview">
                    <div className="preview-head">
                      <strong>Текущая версия договора</strong>
                      <button type="button" onClick={() => setContractPreviewOpen(false)} aria-label="Скрыть договор">
                        Скрыть
                      </button>
                    </div>
                    <article>{sessionDetail?.latest_version?.content}</article>
                  </section>
                )}
                {hasContractVersion && !isFinalized && (
                  <section className="message assistant chat-actions">
                    {partyTwoSigned && !partyOneSigned ? (
                      <div className="quick-flow">
                        <strong>Вторая сторона подписала договор.</strong>
                        <p>Проверьте финальную редакцию и подпишите договор со своей стороны. После этого будет сформирована PDF-версия с отметками простой электронной подписи.</p>
                        {!ownerSigningOpen ? (
                          <button
                            onClick={() => {
                              setOwnerSigningOpen(true);
                              setAppNotice("Проверьте реквизиты и при необходимости исправьте примерные данные. Все верно?");
                            }}
                          >
                            <Check size={16} /> Подписать со своей стороны
                          </button>
                        ) : (
                          <form className="review-form owner-signing-form" onSubmit={signAsFirstParty} ref={ownerFormRef}>
                            <h2>Ваши данные · {currentSession?.party_1_legal_role || "сторона договора"}</h2>
                            <div className="party-type-switch" aria-label="Тип стороны">
                              <button type="button" className={ownerForm.partyType === "individual" ? "active" : ""} onClick={() => setOwnerForm((form) => ({ ...form, partyType: "individual" }))}>Физлицо</button>
                              <button type="button" className={ownerForm.partyType === "business" ? "active" : ""} onClick={() => setOwnerForm((form) => ({ ...form, partyType: "business" }))}>Организация / ИП</button>
                            </div>
                            {ownerForm.partyType === "business" && (
                              <input value={ownerForm.organizationName} onChange={(event) => setOwnerForm((form) => ({ ...form, organizationName: event.target.value }))} placeholder={FORM_HINTS.organization} autoComplete="organization" required />
                            )}
                            <input value={ownerForm.fullName} onChange={(event) => setOwnerForm((form) => ({ ...form, fullName: event.target.value }))} placeholder={ownerForm.partyType === "business" ? FORM_HINTS.signerName : FORM_HINTS.fullName} autoComplete="name" required />
                            {ownerForm.partyType === "individual" ? (
                              <input value={ownerForm.passport} onChange={(event) => setOwnerForm((form) => ({ ...form, passport: event.target.value }))} placeholder={FORM_HINTS.passport} autoComplete="off" inputMode="numeric" pattern="[0-9]{4} ?[0-9]{6}" required />
                            ) : (
                              <>
                                <input value={ownerForm.inn} onChange={(event) => setOwnerForm((form) => ({ ...form, inn: event.target.value }))} placeholder={FORM_HINTS.inn} inputMode="numeric" pattern="[0-9]{10}|[0-9]{12}" required />
                                <input value={ownerForm.ogrn} onChange={(event) => setOwnerForm((form) => ({ ...form, ogrn: event.target.value }))} placeholder={FORM_HINTS.ogrn} inputMode="numeric" pattern="[0-9]{13}|[0-9]{15}" required />
                              </>
                            )}
                            <input value={ownerForm.phone} onChange={(event) => setOwnerForm((form) => ({ ...form, phone: event.target.value }))} placeholder={FORM_HINTS.phone} autoComplete="tel" required />
                            <input value={email} autoComplete="email" readOnly aria-readonly="true" />
                            <label className="checkbox-row">
                              <input type="checkbox" checked={ownerForm.accepted} onChange={(event) => setOwnerForm((form) => ({ ...form, accepted: event.target.checked }))} required />
                              <ConsentText />
                            </label>
                            <button disabled={ownerSubmitting}><Check size={16} /> {ownerSubmitting ? "Подписываю..." : "Подписать"}</button>
                          </form>
                        )}
                      </div>
                    ) : questionResolved ? (
                      <div className="quick-flow">
                        <strong>Что дальше?</strong>
                        <div className="action-row">
                          <button onClick={startAddition}>Дополнить новым условием</button>
                          <button onClick={startAgreement}>
                            <Check size={16} /> Согласовать версию
                          </button>
                        </div>
                      </div>
                    ) : chatMode === "question" ? (
                      <div className="quick-flow active-flow">
                        <strong>Напишите вопрос по договору.</strong>
                        <p>Я отвечу по текущей версии договора простым языком.</p>
                      </div>
                    ) : chatMode === "add" ? (
                      <div className="quick-flow active-flow">
                        <strong>Добавим новое условие.</strong>
                        <p>Опишите условие, которое нужно добавить. Я предложу редакцию пункта.</p>
                      </div>
                    ) : chatMode === "agree" ? (
                      <div className="quick-flow" ref={agreementRef}>
                        <strong>Переходим к согласованию.</strong>
                        <p>
                          Сначала укажите, кем вы выступаете в договоре. Затем введите email контрагента.
                        </p>
                        <div className="agreement-steps" aria-label="Порядок отправки на согласование">
                          <div className={isGuest ? "agreement-step active" : "agreement-step done"}>
                            <span>{isGuest ? "1" : <Check size={13} />}</span>
                            <div>
                              <strong>{isGuest ? "Сначала сохранить вашу сессию" : "Ваша сессия сохранена"}</strong>
                              <p>{isGuest ? "Это нужно, чтобы история договора не потерялась." : email}</p>
                            </div>
                          </div>
                          <div className={isGuest ? "agreement-step" : "agreement-step active"}>
                            <span>2</span>
                            <div>
                              <strong>Отправить ссылку второй стороне</strong>
                              <p>После отправки вы увидите адрес получателя и копию письма у себя.</p>
                            </div>
                          </div>
                        </div>
                        <div className="party-form">
                          <p className="form-hint">
                            В договоре сейчас стоят игровые данные сторон для удобного чтения.
                            Перед финальной подписью каждая сторона заменит их на свои реальные данные.
                          </p>
                          <label>
                            <span>Кем вы выступаете в договоре?</span>
                            <select
                              value={creatorLegalRole}
                              onChange={(event) => setCreatorLegalRole(event.target.value)}
                              required
                            >
                              <option value="">Выберите роль</option>
                              {getLegalRoleOptions(currentSession, sessionDetail).map((role) => (
                                <option key={role} value={role}>{role}</option>
                              ))}
                            </select>
                          </label>
                          {creatorLegalRole && (
                            <p className="form-hint">
                              Вы: {creatorLegalRole}. Контрагент: {getLegalRoleOptions(currentSession, sessionDetail).find((role) => role !== creatorLegalRole)}.
                            </p>
                          )}
                          <input
                            value={partyEmail}
                            onChange={(event) => setPartyEmail(event.target.value)}
                            placeholder={FORM_HINTS.counterpartyEmail}
                            type="email"
                            autoComplete="email"
                            list="contract-email-suggestions"
                          />
                          <datalist id="contract-email-suggestions">
                            {emailSuggestions.map((contact) => (
                              <option key={contact.email} value={contact.email} />
                            ))}
                          </datalist>
                          <button onClick={createInvite} disabled={inviteSending}>
                            {inviteSending ? "Отправляю..." : "Отправить ссылку согласования"}
                          </button>
                        </div>
                        {inviteLink && (
                          <button
                            className="copy-link"
                            onClick={() => {
                              navigator.clipboard?.writeText(inviteLink);
                              setToast("Ссылка скопирована");
                            }}
                          >
                            <Copy size={16} /> {inviteLink}
                          </button>
                        )}
                      </div>
                    ) : (
                      <div className="quick-flow">
                        <strong>Что дальше?</strong>
                        <div className="action-row">
                          <button onClick={startQuestion}>Задать вопрос по договору</button>
                          <button onClick={startAddition}>Дополнить новым условием</button>
                          <button onClick={() => showCurrentContract()}>
                            <FileText size={16} /> Текущая версия
                          </button>
                          <button onClick={startAgreement}>
                            <Check size={16} /> Согласиться с версией
                          </button>
                        </div>
                      </div>
                    )}
                  </section>
                )}
                {isFinalized && (
                  <section className="signed-contract-card">
                    <div>
                      <span>Договор подписан</span>
                      <strong>Договор подписан сторонами</strong>
                      <p>Подписан сторонами путем согласования: {formatFinalizedDate(sessionDetail?.session || currentSession)}. Финальный PDF направлен сторонам на email.</p>
                    </div>
                    <div className="signed-actions">
                      <button className="dispute-button" onClick={startDispute}>
                        Открыть спор
                      </button>
                      <button className="download-button" onClick={downloadCertificate}>
                        <Download size={16} /> Скачать справку
                      </button>
                      {!currentSession?.is_completed && (
                        <button className="download-button" onClick={markCompleted} disabled={completionConfirmed}>
                          {completionConfirmed ? "Ожидается вторая сторона" : "Договор исполнен"}
                        </button>
                      )}
                    </div>
                    {chatMode === "dispute" && (
                      <p className="panel-hint">
                        Опишите ситуацию. Я проверю условия договора, историю согласования и подготовлю позицию по спору.
                      </p>
                    )}
                  </section>
                )}
                {appNotice && <div className="app-notice" role="status" aria-live="polite">{appNotice}</div>}
                <div ref={messagesEndRef} />
              </div>
            </div>
            <div className="composer-shell">
              <SuggestionList
                items={chatSuggestions}
                activeIndex={activeSuggestionIndex}
                label={draft.trim() ? "Подходящие запросы" : "Популярные запросы"}
                onSelect={(value) => {
                  setDraft(value);
                  setActiveSuggestionIndex(-1);
                }}
              />
              <div className="composer">
                <textarea
                  value={draft}
                  onChange={(event) => {
                    setDraft(event.target.value);
                    setActiveSuggestionIndex(-1);
                  }}
                  onFocus={() => setComposerFocused(true)}
                  onBlur={() => {
                    setComposerFocused(false);
                    setActiveSuggestionIndex(-1);
                  }}
                  onKeyDown={(event) => {
                    if (event.key === "ArrowDown" && chatSuggestions.length) {
                      event.preventDefault();
                      setActiveSuggestionIndex((index) => (index + 1) % chatSuggestions.length);
                      return;
                    }
                    if (event.key === "ArrowUp" && chatSuggestions.length) {
                      event.preventDefault();
                      setActiveSuggestionIndex((index) => (index <= 0 ? chatSuggestions.length - 1 : index - 1));
                      return;
                    }
                    if ((event.key === "Tab" || event.key === "Enter") && activeSuggestionIndex >= 0) {
                      event.preventDefault();
                      setDraft(chatSuggestions[activeSuggestionIndex]);
                      setActiveSuggestionIndex(-1);
                      return;
                    }
                    if (event.key === "Escape") {
                      setComposerFocused(false);
                      setActiveSuggestionIndex(-1);
                      return;
                    }
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      sendMessage();
                    }
                  }}
                  placeholder={composerPlaceholder}
                  aria-autocomplete="list"
                  aria-expanded={chatSuggestions.length > 0}
                />
                <button onClick={sendMessage} aria-label="Отправить">
                  <Send size={20} />
                </button>
              </div>
              <small className="hint">{composerHint}. Enter для отправки</small>
            </div>
          </div>
        )}
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
