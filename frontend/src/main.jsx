import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { Check, Copy, Download, LogOut, Menu, Plus, Send, Trash2 } from "lucide-react";
import "./styles.css";

const API_URL = window.__AI_ARBITR_CONFIG__?.apiUrl || "http://localhost:8000";
const TYPEWRITER_DELAY_MS = 17;
const TYPEWRITER_CHUNK_SIZE = 2;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function getThinkingSteps(content) {
  const normalized = content.toLowerCase();
  if (normalized.includes("найм") || normalized.includes("квартир") || normalized.includes("жил")) {
    return [
      "Понятно, делаем договор найма жилого помещения.",
      "Проверяю применимые нормы ГК РФ о найме жилого помещения.",
      "Выделяю существенные условия: жилое помещение, стороны, срок найма, размер и порядок оплаты.",
      "Добавляю обычные условия: порядок передачи квартиры, коммунальные платежи, ремонт, доступ в помещение, ответственность.",
      "Учитываю спорные места: депозит, просрочка оплаты, повреждение имущества, досрочное расторжение.",
      "Генерирую первую версию договора.",
    ];
  }
  return [
    "Понятно, готовлю проект договора по вашему запросу.",
    "Проверяю применимые нормы ГК РФ и обязательные условия договора.",
    "Выделяю существенные условия, без которых договор может работать плохо.",
    "Добавляю обычные условия: порядок оплаты, сроки, приемка, ответственность, изменение и расторжение.",
    "Учитываю типовые спорные места и формулирую условия понятным языком.",
    "Генерирую первую версию договора.",
  ];
}

function buildReasoningNote(steps) {
  return `Что делает Арби:\n${steps.map((step) => `• ${step}`).join("\n")}`;
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

function KeyTermsCard({ terms }) {
  const visibleTerms = (terms || []).filter((term) => term.value && term.value !== "не указано");
  if (!visibleTerms.length) return null;
  return (
    <section className="key-terms-card">
      <strong>Ключевые условия</strong>
      <div className="key-terms-list">
        {visibleTerms.map((term, index) => (
          <div className="key-term" key={`${term.label}-${index}`}>
            <span className="key-check">
              <Check size={14} />
            </span>
            <div>
              <small>{term.label}</small>
              <p>{term.value}</p>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function App() {
  const [email, setEmail] = useState("");
  const [authMode, setAuthMode] = useState("register");
  const [userId, setUserId] = useState("");
  const [authReady, setAuthReady] = useState(false);
  const [isGuest, setIsGuest] = useState(false);
  const [authPromptOpen, setAuthPromptOpen] = useState(false);
  const [accepted, setAccepted] = useState(false);
  const [authed, setAuthed] = useState(false);
  const [sessions, setSessions] = useState([]);
  const [currentSession, setCurrentSession] = useState(null);
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState(localStorage.getItem("ai-arbitr-draft") || "");
  const [thinking, setThinking] = useState(false);
  const [thinkingStep, setThinkingStep] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [loginNotice, setLoginNotice] = useState("");
  const [devLink, setDevLink] = useState("");
  const [sessionDetail, setSessionDetail] = useState(null);
  const [inviteLink, setInviteLink] = useState("");
  const [appNotice, setAppNotice] = useState("");
  const [partyName, setPartyName] = useState("");
  const [partyEmail, setPartyEmail] = useState("");
  const [deleteCandidateId, setDeleteCandidateId] = useState("");
  const [chatMode, setChatMode] = useState("idle");
  const [questionResolved, setQuestionResolved] = useState(false);
  const [authPromptTitle, setAuthPromptTitle] = useState("Сохранить историю");
  const [authPromptCopy, setAuthPromptCopy] = useState(
    "Укажите email, чтобы сохранить этот договор, получить ссылку для входа и отправить договор второй стороне."
  );
  const [reviewData, setReviewData] = useState(null);
  const [reviewForm, setReviewForm] = useState({ fullName: "", passport: "", email: "", accepted: false });
  const [reviewNotice, setReviewNotice] = useState("");
  const [reviewLoading, setReviewLoading] = useState(false);
  const messagesEndRef = useRef(null);

  const reviewToken = getReviewTokenFromPath();

  useEffect(() => {
    if (reviewToken) {
      setAuthReady(true);
      return;
    }
    fetch(`${API_URL}/auth/me`, { credentials: "include" })
      .then((res) => {
        if (!res.ok) throw new Error("not authed");
        return res.json();
      })
      .then((user) => {
        setEmail(user.email);
        setUserId(user.id);
        setIsGuest(Boolean(user.is_guest));
        setAuthed(true);
      })
      .catch(() =>
        fetch(`${API_URL}/auth/guest`, { method: "POST", credentials: "include" })
          .then((res) => res.json())
          .then((user) => {
            setEmail(user.email || "");
            setUserId(user.id);
            setIsGuest(true);
            setAuthed(true);
          })
          .catch(() => setAuthed(false))
      )
      .finally(() => setAuthReady(true));
  }, [reviewToken]);

  useEffect(() => {
    if (!reviewToken) return;
    loadReview(reviewToken);
  }, [reviewToken]);

  useEffect(() => {
    localStorage.setItem("ai-arbitr-draft", draft);
  }, [draft]);

  useEffect(() => {
    if (!authed) return;
    loadSessions();
  }, [authed]);

  useEffect(() => {
    if (!currentSession) return;
    loadSession(currentSession.id);
  }, [currentSession?.id]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, thinking, appNotice, sessionDetail?.latest_version?.id]);

  function getReviewTokenFromPath() {
    const match = window.location.pathname.match(/^\/review\/([^/]+)$/);
    return match ? match[1] : "";
  }

  async function loadReview(token) {
    setReviewLoading(true);
    setReviewNotice("");
    try {
      const response = await fetch(`${API_URL}/review/${token}`);
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        setReviewNotice(data.detail || "Ссылка согласования не найдена");
        setReviewData(null);
        return;
      }
      setReviewData(data);
    } finally {
      setReviewLoading(false);
    }
  }

  async function approveReview(event) {
    event.preventDefault();
    if (!reviewToken) return;
    setReviewNotice("");
    const response = await fetch(`${API_URL}/review/${reviewToken}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        full_name: reviewForm.fullName,
        passport: reviewForm.passport,
        email: reviewForm.email,
        personal_data_accepted: reviewForm.accepted,
      }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      setReviewNotice(data.detail || "Не удалось подтвердить согласие");
      return;
    }
    setReviewNotice("Согласие зафиксировано. Финальная PDF-версия договора сформирована.");
    setReviewData((current) => ({
      ...current,
      finalized: true,
      approved: true,
      download_token: data.download_token,
    }));
  }

  async function loadSession(sessionId) {
    const response = await fetch(`${API_URL}/sessions/${sessionId}`, { credentials: "include" });
    if (!response.ok) return;
    const detail = await response.json();
    setSessionDetail(detail);
    setCurrentSession(detail.session);
    setMessages(detail.messages || []);
  }

  async function loadSessions() {
    try {
      const response = await fetch(`${API_URL}/sessions`, { credentials: "include" });
      setSessions(await response.json());
    } catch {
      setSessions([]);
    }
  }

  async function login(event) {
    event.preventDefault();
    setLoginNotice("");
    setDevLink("");
    const endpoint = authMode === "register" ? "/auth/register" : "/auth/login";
    const payload =
      authMode === "register" ? { email, personal_data_accepted: accepted } : { email };
    const response = await fetch(`${API_URL}${endpoint}`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      setLoginNotice(data.detail || "Не удалось отправить ссылку. Проверьте email и попробуйте еще раз.");
      return;
    }
    setLoginNotice(data.message);
    setDevLink(data.dev_link || "");
  }

  async function createSession() {
    const response = await fetch(`${API_URL}/sessions`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
    });
    const session = await response.json();
    setCurrentSession(session);
    setSessionDetail(null);
    setInviteLink("");
    setSessions([session, ...sessions]);
    setMessages([]);
    setSidebarOpen(false);
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
      setAppNotice("Не удалось удалить договор. Попробуйте еще раз.");
      return;
    }

    setSessions((items) => items.filter((item) => item.id !== session.id));
    setDeleteCandidateId("");
    loadSessions();
    if (currentSession?.id === session.id) {
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
      ? [
          "Нужно добавить условие в договор.",
          "Проверяю, не противоречит ли оно ГК РФ и логике договора.",
          "ГК РФ не противоречит: условие можно включить, если оно сформулировано ясно и справедливо.",
          "Ищу правильный раздел договора и формулирую норму.",
          "Готово. Встраиваю условие в новую редакцию.",
        ]
      : isQuestion
        ? [
            "Понял вопрос по договору.",
            "Сверяю вопрос с текущей редакцией договора.",
            "Формулирую ответ простым языком.",
          ]
        : isDispute
          ? [
              "Понял, открываем спор по финализированному договору.",
              "Проверяю условия договора и историю согласования.",
              "Формирую позицию AI-Арбитра.",
            ]
          : getThinkingSteps(rawContent);
    setDraft("");
    setQuestionResolved(false);
    setMessages((items) => [...items, { role: "user", content: rawContent }]);
    setThinking(true);
    setThinkingStep(thinkingSteps[0]);
    let thinkingTimer;
    try {
      let stepIndex = 1;
      thinkingTimer = window.setInterval(() => {
        setThinkingStep(thinkingSteps[Math.min(stepIndex, thinkingSteps.length - 1)]);
        stepIndex += 1;
        if (stepIndex >= thinkingSteps.length) {
          window.clearInterval(thinkingTimer);
        }
      }, 1900);
      const response = await fetch(`${API_URL}/sessions/${currentSession.id}/messages`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      });
      const data = await response.json();
      if (thinkingTimer) window.clearInterval(thinkingTimer);
      setThinkingStep(thinkingSteps[thinkingSteps.length - 1]);
      await sleep(450);
      setThinking(false);
      if (!isQuestion) {
        setMessages((items) => [...items, { role: "system", content: data.reasoning || buildReasoningNote(thinkingSteps) }]);
      }
      if (isInitialContract) {
        await typeAssistantMessage(data.content);
      } else {
        setMessages((items) => [...items, { role: "assistant", content: data.content }]);
      }
      if (isQuestion) {
        setQuestionResolved(true);
      }
      setChatMode("idle");
      loadSession(currentSession.id);
      loadSessions();
    } finally {
      if (thinkingTimer) window.clearInterval(thinkingTimer);
      setThinking(false);
      setThinkingStep("");
    }
  }

  async function typeAssistantMessage(content) {
    setMessages((items) => [...items, { role: "assistant", content: "" }]);
    for (let index = 0; index < content.length; index += TYPEWRITER_CHUNK_SIZE) {
      const visibleContent = content.slice(0, index + TYPEWRITER_CHUNK_SIZE);
      setMessages((items) => {
        const nextItems = [...items];
        nextItems[nextItems.length - 1] = { role: "assistant", content: visibleContent };
        return nextItems;
      });
      await sleep(TYPEWRITER_DELAY_MS);
    }
  }

  async function createInvite() {
    if (isGuest) {
      setAuthMode("register");
      setAuthPromptTitle("Сохранить историю");
      setAuthPromptCopy("Укажите email, чтобы сохранить этот договор, получить ссылку для входа и отправить договор второй стороне.");
      setAuthPromptOpen(true);
      setLoginNotice("Укажите email, чтобы сохранить сессию и отправить ссылку второй стороне.");
      return;
    }
    const response = await fetch(`${API_URL}/sessions/${currentSession.id}/invite`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ party_name: partyName, email: partyEmail || null }),
    });
    if (!response.ok) return;
    const data = await response.json();
    setInviteLink(data.invite_link);
    setAppNotice(
      data.sent
        ? "Ссылка на просмотр договора отправлена второй стороне на email."
        : "SMTP пока не настроен. Скопируйте ссылку просмотра и отправьте второй стороне вручную."
    );
  }

  function startQuestion() {
    setChatMode("question");
    setDraft("");
    setQuestionResolved(false);
  }

  function startAddition() {
    setChatMode("add");
    setDraft("");
    setQuestionResolved(false);
  }

  function startAgreement() {
    setChatMode("agree");
    setQuestionResolved(false);
  }

  function startDispute() {
    setChatMode("dispute");
    setDraft("");
    setQuestionResolved(false);
  }

  function downloadPdf() {
    const token = sessionDetail?.session?.download_token || currentSession?.download_token;
    if (!token) return;
    window.open(`${API_URL}/download/${token}.pdf`, "_blank", "noopener,noreferrer");
  }

  const hasContractVersion = Boolean(sessionDetail?.latest_version);
  const isFinalized = currentSession?.status === "finalized";
  const isEmptySession = currentSession && messages.length === 0 && !thinking && !appNotice;
  const composerPlaceholder =
    chatMode === "question"
      ? "Например: что означает обеспечительный платеж и когда его вернут?"
      : chatMode === "add"
        ? "Например: добавить запрет проживания с животными без согласия"
        : chatMode === "dispute"
          ? "Опишите, что произошло: кто, когда, какое условие нарушил"
          : "Например: составь договор найма квартиры";

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

  if (reviewToken) {
    const finalPdfLink = reviewData?.download_token ? `${API_URL}/download/${reviewData.download_token}.pdf` : "";
    return (
      <main className="review-page">
        <section className="review-shell">
          <header className="review-header">
            <span>AI-arbitr</span>
            <h1>{reviewData?.title || "Согласование договора"}</h1>
            <p>Вам направлен договор на согласование. Проверьте текст и подтвердите согласие, если условия подходят.</p>
          </header>
          {reviewLoading && <p className="notice">Загружаю договор...</p>}
          {reviewNotice && <p className="app-notice">{reviewNotice}</p>}
          {reviewData && (
            <>
              <div className="review-actions">
                <a className="review-link-button" href={reviewData.pdf_link} target="_blank" rel="noreferrer">
                  <Download size={16} /> Открыть PDF
                </a>
                {finalPdfLink && (
                  <a className="review-link-button" href={finalPdfLink} target="_blank" rel="noreferrer">
                    <Download size={16} /> Финальная PDF-версия
                  </a>
                )}
              </div>
              <KeyTermsCard terms={reviewData.key_terms} />
              <article className="review-contract">{reviewData.contract}</article>
              {reviewData.approved || reviewData.finalized ? (
                <div className="review-approved">
                  <Check size={18} /> Согласие уже зафиксировано.
                </div>
              ) : (
                <form className="review-form" onSubmit={approveReview}>
                  <h2>Согласиться с договором</h2>
                  <input
                    value={reviewForm.fullName}
                    onChange={(event) => setReviewForm((form) => ({ ...form, fullName: event.target.value }))}
                    placeholder="ФИО"
                    required
                  />
                  <input
                    value={reviewForm.passport}
                    onChange={(event) => setReviewForm((form) => ({ ...form, passport: event.target.value }))}
                    placeholder="Паспортные данные"
                    required
                  />
                  <input
                    value={reviewForm.email}
                    onChange={(event) => setReviewForm((form) => ({ ...form, email: event.target.value }))}
                    placeholder="email@example.com"
                    required
                  />
                  <label className="checkbox-row">
                    <input
                      type="checkbox"
                      checked={reviewForm.accepted}
                      onChange={(event) => setReviewForm((form) => ({ ...form, accepted: event.target.checked }))}
                    />
                    <span>Я согласен на обработку персональных данных</span>
                  </label>
                  <button>
                    <Check size={16} /> Согласиться
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
          <input value={email} onChange={(event) => setEmail(event.target.value)} placeholder="email@example.com" />
          {authMode === "register" && (
            <label className="checkbox-row">
              <input type="checkbox" checked={accepted} onChange={(event) => setAccepted(event.target.checked)} />
              <span>Я согласен на обработку персональных данных</span>
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
    <main className="app-shell">
      <div className="mobile-topbar">
        <button className="mobile-menu" onClick={() => setSidebarOpen(true)} aria-label="Открыть меню">
          <Menu size={20} />
        </button>
        <strong>AI-arbitr</strong>
      </div>
      {sidebarOpen && (
        <button className="sidebar-backdrop" onClick={() => setSidebarOpen(false)} aria-label="Закрыть меню" />
      )}
      {authPromptOpen && (
        <div className="auth-modal-backdrop">
          <form className="login-form auth-modal" onSubmit={login}>
            <h1>{authPromptTitle}</h1>
            <p className="auth-copy">{authPromptCopy}</p>
            <input value={email} onChange={(event) => setEmail(event.target.value)} placeholder="email@example.com" />
            <label className="checkbox-row">
              <input type="checkbox" checked={accepted} onChange={(event) => setAccepted(event.target.checked)} />
              <span>Я согласен на обработку персональных данных</span>
            </label>
            <button>Отправить ссылку для входа</button>
            {loginNotice && <p className="notice">{loginNotice}</p>}
            {devLink && (
              <a className="dev-link" href={devLink}>
                Dev-вход без SMTP
              </a>
            )}
            <button className="modal-secondary" type="button" onClick={() => setAuthPromptOpen(false)}>
              Продолжить без отправки
            </button>
          </form>
        </div>
      )}
      <aside className={sidebarOpen ? "sidebar open" : "sidebar"}>
        <div className="account">
          <strong>{isGuest ? "Гостевой режим" : email}</strong>
          <button
            onClick={() => {
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
        </div>
        <button className="new-contract" onClick={createSession}>
          <Plus size={18} /> Новый договор
        </button>
        <div className="session-list">
          {sessions.map((session) => (
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
                <span>{session.title}</span>
                <small>{formatSessionTimestamp(session)}</small>
              </button>
              {deleteCandidateId === session.id ? (
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
          ))}
        </div>
        <div className="sidebar-footer">
          <a>Помощь / FAQ</a>
          <a>Обратная связь</a>
        </div>
      </aside>
      <section className="chat-area">
        {!currentSession ? (
          <div className="empty-state">
            <h2>AI-arbitr</h2>
            <p>
              Работаю на базе Яндекс GPT. Помогу составить справедливый договор в соответствии
              с ГК и обычной практикой, согласовать его с другой стороной, напомнить о сроках
              и разрешить спор, если он возникнет.
            </p>
            <button onClick={createSession}>
              <Plus size={18} /> Новый договор
            </button>
          </div>
        ) : (
          <div className={isEmptySession ? "session-stage start-session" : "session-stage active-session"}>
            <div className="chat-thread">
              {appNotice && <div className="app-notice">{appNotice}</div>}
              <div className="messages">
                {messages.map((message, index) => (
                  <article key={index} className={`message ${message.role}`}>
                    {message.role === "system" ? <em>{message.content}</em> : message.content}
                  </article>
                ))}
                {thinking && (
                  <article className="message assistant thinking">
                    <span /> {thinkingStep || "Арби думает..."}
                  </article>
                )}
                {hasContractVersion && !isFinalized && (
                  <section className="message assistant chat-actions">
                    {questionResolved ? (
                      <div className="quick-flow">
                        <strong>Все понятно?</strong>
                        <div className="action-row">
                          <button onClick={() => setQuestionResolved(false)}>Да</button>
                          <button onClick={startQuestion}>Нет, задать еще вопрос</button>
                        </div>
                      </div>
                    ) : chatMode === "question" ? (
                      <div className="quick-flow active-flow">
                        <strong>Понял. Напишите вопрос по договору.</strong>
                        <p>Сверю его с текущей редакцией и отвечу простым языком.</p>
                      </div>
                    ) : chatMode === "add" ? (
                      <div className="quick-flow active-flow">
                        <strong>Добавим новое условие.</strong>
                        <p>
                          Сначала проверю его соответствие ГК РФ, затем найду правильный раздел
                          и сформулирую одну норму для новой редакции.
                        </p>
                      </div>
                    ) : chatMode === "agree" ? (
                      <div className="quick-flow">
                        <strong>Если все понятно и вопросов нет, сохраняю версию.</strong>
                        <p>
                          Введите данные второй стороны и email. На него будет направлена ссылка для просмотра
                          договора и подтверждения согласия без регистрации.
                        </p>
                        <KeyTermsCard terms={sessionDetail?.key_terms} />
                        <div className="party-form">
                          <input
                            value={partyName}
                            onChange={(event) => setPartyName(event.target.value)}
                            placeholder="Имя или название второй стороны"
                          />
                          <input
                            value={partyEmail}
                            onChange={(event) => setPartyEmail(event.target.value)}
                            placeholder="email второй стороны"
                          />
                          <button onClick={createInvite}>Отправить ссылку согласования</button>
                        </div>
                        {inviteLink && (
                          <button className="copy-link" onClick={() => navigator.clipboard?.writeText(inviteLink)}>
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
                      <strong>
                        {(sessionDetail?.key_terms || []).find((term) => term.label === "Вид договора")?.value ||
                          "Договор подписан сторонами"}
                      </strong>
                      <p>Подписан сторонами путем согласования: {formatFinalizedDate(sessionDetail?.session || currentSession)}</p>
                    </div>
                    <div className="signed-actions">
                      {(sessionDetail?.session?.download_token || currentSession.download_token) && (
                        <button className="download-button" onClick={downloadPdf}>
                          <Download size={16} /> Открыть PDF
                        </button>
                      )}
                      <button className="dispute-button" onClick={startDispute}>
                        Открыть спор
                      </button>
                    </div>
                    {chatMode === "dispute" && (
                      <p className="panel-hint">
                        Опишите ситуацию. Я проверю условия договора, историю согласования и подготовлю позицию AI-Арбитра.
                      </p>
                    )}
                  </section>
                )}
                <div ref={messagesEndRef} />
              </div>
            </div>
            <div className="composer">
              <textarea
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    sendMessage();
                  }
                }}
                placeholder={composerPlaceholder}
              />
              <button onClick={sendMessage} aria-label="Отправить">
                <Send size={20} />
              </button>
            </div>
            <small className="hint">Нажмите Enter для отправки</small>
          </div>
        )}
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
