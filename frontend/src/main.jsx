import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { LogOut, Menu, Plus, Send } from "lucide-react";
import "./styles.css";

const API_URL = "http://localhost:8000";

function App() {
  const [email, setEmail] = useState("");
  const [accepted, setAccepted] = useState(false);
  const [authed, setAuthed] = useState(false);
  const [sessions, setSessions] = useState([]);
  const [currentSession, setCurrentSession] = useState(null);
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState(localStorage.getItem("ai-arbitr-draft") || "");
  const [thinking, setThinking] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [loginNotice, setLoginNotice] = useState("");
  const [devLink, setDevLink] = useState("");

  useEffect(() => {
    fetch(`${API_URL}/auth/me`, { credentials: "include" })
      .then((res) => {
        if (!res.ok) throw new Error("not authed");
        return res.json();
      })
      .then((user) => {
        setEmail(user.email);
        setAuthed(true);
      })
      .catch(() => setAuthed(false));
  }, []);

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
    setSessions([session, ...sessions]);
    setMessages([]);
    setSidebarOpen(false);
  }

  async function sendMessage() {
    if (!draft.trim() || !currentSession) return;
    const content = draft.trim();
    setDraft("");
    setMessages((items) => [...items, { role: "user", content }]);
    setThinking(true);
    try {
      const response = await fetch(`${API_URL}/sessions/${currentSession.id}/messages`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      });
      const data = await response.json();
      setMessages((items) => [...items, { role: "assistant", content: data.content }]);
    } finally {
      setThinking(false);
    }
  }

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
            <h2>Здравствуйте! Я — AI-Арбитр.</h2>
            <p>
              Помогу составить договор по нормам ГК РФ, согласовать его с другой стороной и затем
              разобрать спор, если он возникнет.
            </p>
            <button onClick={createSession}>Создать первый договор</button>
          </div>
        ) : (
          <>
            <div className="messages">
              {messages.map((message, index) => (
                <article key={index} className={`message ${message.role}`}>
                  {message.content}
                </article>
              ))}
              {thinking && <article className="message assistant">Арби думает...</article>}
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
                placeholder="Опишите, какой договор нужно составить"
              />
              <button onClick={sendMessage} aria-label="Отправить">
                <Send size={20} />
              </button>
            </div>
            <small className="hint">Нажмите Enter для отправки</small>
          </>
        )}
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
