import React, { useEffect, useState } from "react";

const API_URL = window.__AI_ARBITR_CONFIG__?.apiUrl || "http://localhost:8000";
const VOTER_KEY = "ai-arbitr-contract-poll-voter";
const CHOICE_KEY = "ai-arbitr-contract-poll-choice";

function getStoredValue(key) {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function storeValue(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // Private browsing can disable persistent storage; the vote still succeeds.
  }
}

export default function ContractTypePoll() {
  const [poll, setPoll] = useState(null);
  const [choice, setChoice] = useState(() => getStoredValue(CHOICE_KEY) || "");
  const [otherText, setOtherText] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [voted, setVoted] = useState(() => Boolean(getStoredValue(CHOICE_KEY)));

  useEffect(() => {
    fetch(`${API_URL}/contract-type-poll`)
      .then((response) => {
        if (!response.ok) throw new Error("Голосование временно недоступно");
        return response.json();
      })
      .then(setPoll)
      .catch((cause) => setError(cause.message));
  }, []);

  async function submitVote(event) {
    event.preventDefault();
    if (!choice || pending) return;
    setPending(true);
    setError("");
    try {
      const voterId = getStoredValue(VOTER_KEY) || crypto.randomUUID();
      const response = await fetch(`${API_URL}/contract-type-poll`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ voter_id: voterId, choice, other_text: otherText }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "Не удалось сохранить голос");
      storeValue(VOTER_KEY, voterId);
      storeValue(CHOICE_KEY, choice);
      setPoll(result);
      setVoted(true);
    } catch (cause) {
      setError(cause.message || "Не удалось сохранить голос");
    } finally {
      setPending(false);
    }
  }

  return (
    <form className="landing-poll" onSubmit={submitVote}>
      <fieldset disabled={pending || !poll}>
        <legend>Какой договор проработать следующим?</legend>
        {poll?.options.map((option) => (
          <label className="landing-poll-option" key={option.id}>
            <span className="landing-poll-option-main">
              <input type="radio" name="contract-type" value={option.id} checked={choice === option.id} onChange={() => setChoice(option.id)} />
              <span>{option.label}</span>
            </span>
            {voted && <span className="landing-poll-count">{option.votes}</span>}
          </label>
        ))}
        {choice === "other" && (
          <input
            className="landing-poll-other"
            value={otherText}
            onChange={(event) => setOtherText(event.target.value)}
            placeholder="Какой договор?"
            maxLength={120}
            required
          />
        )}
      </fieldset>
      <div className="landing-poll-footer">
        <button type="submit" disabled={!poll || !choice || pending}>{pending ? "Сохраняю…" : voted ? "Изменить выбор" : "Проголосовать"}</button>
        {voted && poll && <span>Всего голосов: {poll.total}</span>}
      </div>
      {error && <p className="landing-poll-error" role="alert">{error}</p>}
      {voted && !error && <p className="landing-poll-success" role="status">Спасибо, ваш выбор учтён.</p>}
      <small>Без входа. Для учёта одного голоса браузер сохраняет случайный идентификатор.</small>
    </form>
  );
}
