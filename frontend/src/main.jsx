import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { Check, Copy, Download, LogOut, Menu, Plus, Send } from "lucide-react";
import "./styles.css";

const API_URL = window.__AI_ARBITR_CONFIG__?.apiUrl || "http://localhost:8000";
const TYPEWRITER_DELAY_MS = 34;
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

function App() {
  const [email, setEmail] = useState("");
  const [userId, setUserId] = useState("");
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
  const [contractText, setContractText] = useState("");
  const [changesText, setChangesText] = useState("");
  const [appNotice, setAppNotice] = useState("");
  const [partyName, setPartyName] = useState("");
  const [partyEmail, setPartyEmail] = useState("");
  const messagesEndRef = useRef(null);

  const pendingInvite = getInviteTokenFromPath();

  useEffect(() => {
    if (pendingInvite) localStorage.setItem("ai-arbitr-pending-invite", pendingInvite);
    fetch(`${API_URL}/auth/me`, { credentials: "include" })
      .then((res) => {
        if (!res.ok) throw new Error("not authed");
        return res.json();
      })
      .then((user) => {
        setEmail(user.email);
        setUserId(user.id);
        setAuthed(true);
      })
      .catch(() => setAuthed(false));
  }, [pendingInvite]);

  useEffect(() => {
    localStorage.setItem("ai-arbitr-draft", draft);
  }, [draft]);

  useEffect(() => {
    if (!authed || !email) return;
    fetch(`${API_URL}/sessions`, { credentials: "include" })
      .then((res) => res.json())
      .then(setSessions)
      .catch(() => setSessions([]));
  }, [authed, email]);

  useEffect(() => {
    if (!authed) return;
    const token = localStorage.getItem("ai-arbitr-pending-invite");
    if (!token) return;
    fetch(`${API_URL}/invites/${token}/accept`, { method: "POST", credentials: "include" })
      .then((res) => {
        if (!res.ok) throw new Error("invite failed");
        return res.json();
      })
      .then((data) => {
        localStorage.removeItem("ai-arbitr-pending-invite");
        loadSession(data.session_id);
        window.history.replaceState({}, "", "/");
      })
      .catch(() => setLoginNotice("Приглашение недействительно или уже принято другой стороной"));
  }, [authed]);

  useEffect(() => {
    if (!currentSession) return;
    loadSession(currentSession.id);
  }, [currentSession?.id]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, thinking, appNotice, sessionDetail?.latest_version?.id]);

  function getInviteTokenFromPath() {
    const match = window.location.pathname.match(/^\/invite\/([^/]+)$/);
    return match ? match[1] : "";
  }

  async function loadSession(sessionId) {
    const response = await fetch(`${API_URL}/sessions/${sessionId}`, { credentials: "include" });
    if (!response.ok) return;
    const detail = await response.json();
    setSessionDetail(detail);
    setCurrentSession(detail.session);
    setMessages(detail.messages || []);
    setContractText(detail.latest_version?.content || "");
  }

  async function login(event) {
    event.preventDefault();
    const response = await fetch(`${API_URL}/auth/magic-link`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, personal_data_accepted: accepted }),
    });
    if (!response.ok) return;
    const data = await response.json();
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
    setContractText("");
    setChangesText("");
    setSessions([session, ...sessions]);
    setMessages([]);
    setSidebarOpen(false);
  }

  async function sendMessage() {
    if (!draft.trim() || !currentSession) return;
    const content = draft.trim();
    const thinkingSteps = getThinkingSteps(content);
    setDraft("");
    setMessages((items) => [...items, { role: "user", content }]);
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
      setMessages((items) => [...items, { role: "system", content: data.reasoning || buildReasoningNote(thinkingSteps) }]);
      await typeAssistantMessage(data.content);
      if (data.contract_saved) {
        setAppNotice("Проект договора сгенерирован и сохранен как текущая версия.");
      }
      loadSession(currentSession.id);
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

  async function saveVersion() {
    if (!contractText.trim() || !currentSession) return;
    const response = await fetch(`${API_URL}/sessions/${currentSession.id}/versions`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: contractText }),
    });
    if (response.ok) loadSession(currentSession.id);
  }

  async function createInvite() {
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
        ? "Ссылка отправлена второй стороне на email."
        : "SMTP пока не настроен. Скопируйте ссылку и отправьте второй стороне вручную."
    );
  }

  async function approve() {
    const response = await fetch(`${API_URL}/sessions/${currentSession.id}/approve`, {
      method: "POST",
      credentials: "include",
    });
    if (!response.ok) {
      const error = await response.json().catch(() => null);
      setAppNotice(error?.detail || "Не удалось согласовать договор");
      return;
    }
    const data = await response.json();
    setAppNotice(data.finalized ? "Договор финализирован. PDF доступен для скачивания." : "Согласие зафиксировано.");
    loadSession(currentSession.id);
  }

  async function requestChanges() {
    if (!changesText.trim()) return;
    const response = await fetch(`${API_URL}/sessions/${currentSession.id}/request-changes`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: changesText }),
    });
    if (response.ok) {
      setChangesText("");
      loadSession(currentSession.id);
    }
  }

  function downloadPdf() {
    const token = sessionDetail?.session?.download_token || currentSession?.download_token;
    if (!token) return;
    window.open(`${API_URL}/download/${token}.pdf`, "_blank", "noopener,noreferrer");
  }

  const hasContractVersion = Boolean(sessionDetail?.latest_version);
  const isFinalized = currentSession?.status === "finalized";
  const isEmptySession = currentSession && messages.length === 0 && !thinking && !appNotice;

  if (!authed) {
    return (
      <main className="login-page">
        <form className="login-form" onSubmit={login}>
          <h1>AI-Арбитр</h1>
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
          <a href="/privacy">Политика конфиденциальности</a>
        </form>
      </main>
    );
  }

  return (
    <main className="app-shell">
      <button className="mobile-menu" onClick={() => setSidebarOpen(true)} aria-label="Открыть меню">
        <Menu size={20} />
      </button>
      <aside className={sidebarOpen ? "sidebar open" : "sidebar"}>
        <div className="account">
          <strong>{email}</strong>
          <button
            onClick={() => {
              fetch(`${API_URL}/auth/logout`, { method: "POST", credentials: "include" }).finally(() => {
                setAuthed(false);
                setSessions([]);
                setCurrentSession(null);
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
            <button
              key={session.id}
              onClick={() => {
                setCurrentSession(session);
                setInviteLink("");
                setChangesText("");
                setSidebarOpen(false);
              }}
            >
              <span>{session.title}</span>
              <small>{new Date(session.created_at).toLocaleDateString("ru-RU")}</small>
            </button>
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
            <button onClick={createSession}>Создать первый договор</button>
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
                  <section className="next-step">
                    <div>
                      <strong>Проект договора сохранён.</strong>
                      <p>
                        Задайте Арби вопросы по тексту договора. Когда всё понятно и вопросов не осталось,
                        укажите данные второй стороны и email для отправки ссылки на согласование.
                      </p>
                    </div>
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
                      <button onClick={createInvite}>Подготовить ссылку согласования</button>
                    </div>
                    {inviteLink && (
                      <button className="copy-link" onClick={() => navigator.clipboard?.writeText(inviteLink)}>
                        <Copy size={16} /> {inviteLink}
                      </button>
                    )}
                    <details className="contract-details">
                      <summary>Посмотреть текущую версию договора</summary>
                      <textarea
                        value={contractText}
                        onChange={(event) => setContractText(event.target.value)}
                        placeholder="Текущая версия договора"
                      />
                      <div className="panel-actions">
                        <button onClick={saveVersion}>Сохранить правки</button>
                        <button onClick={approve}>
                          <Check size={16} /> Согласен с версией
                        </button>
                      </div>
                    </details>
                  </section>
                )}
                {isFinalized && (
                  <section className="next-step">
                    <strong>Договор финализирован.</strong>
                    <p>Теперь в этом чате можно разобрать спор. Напишите “СПОР” и опишите ситуацию.</p>
                    {(sessionDetail?.session?.download_token || currentSession.download_token) && (
                      <button className="download-button" onClick={downloadPdf}>
                        <Download size={16} /> Скачать PDF
                      </button>
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
                placeholder="Например: составь договор найма квартиры"
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
