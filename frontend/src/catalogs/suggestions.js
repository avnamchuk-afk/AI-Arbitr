const CHAT_SUGGESTIONS = {
  create: [
    "Составь договор на разработку сервиса AI-помощника для интернет-магазина",
    "Составь договор найма квартиры",
    "Составь договор на разработку сайта",
    "Составь договор оказания услуг",
    "Составь договор подряда на ремонт",
    "Составь договор поставки товара",
    "Составь договор займа между физическими лицами",
  ],
  question: [
    "Какие условия этого договора наиболее важны?",
    "Какие риски есть для моей стороны?",
    "Можно ли досрочно расторгнуть договор?",
    "В каких случаях можно изменить цену?",
    "Какая ответственность предусмотрена за нарушение?",
  ],
  housingQuestion: [
    "Может ли наймодатель увеличить плату и на каких условиях?",
    "Когда возвращается обеспечительный платеж?",
    "Можно ли досрочно прекратить договор найма?",
    "Кто оплачивает коммунальные услуги?",
  ],
  add: [
    "Добавь условие об изменении цены",
    "Добавь условие о досрочном расторжении",
    "Добавь ответственность за просрочку",
    "Добавь порядок направления уведомлений",
  ],
  housingAdd: [
    "Разбей депозит — обеспечительный платеж — на два платежа",
    "Добавь запрет содержания животных без согласия наймодателя",
    "Добавь порядок ежегодного изменения платы",
    "Добавь срок возврата обеспечительного платежа",
  ],
  dispute: [
    "Вторая сторона пропустила срок исполнения обязательства",
    "Вторая сторона не оплатила предусмотренную договором сумму",
    "Полученный результат не соответствует условиям договора",
  ],
};

function normalize(value) {
  return value.toLowerCase().replaceAll("ё", "е").trim();
}

function rankSuggestions(items, query) {
  const normalizedQuery = normalize(query);
  if (!normalizedQuery) return items.slice(0, 5);
  const words = normalizedQuery.split(/\s+/).filter(Boolean);
  return items
    .map((value, index) => {
      const normalizedValue = normalize(value);
      const matches = words.every((word) => normalizedValue.includes(word));
      const score = normalizedValue.startsWith(normalizedQuery) ? 0 : normalizedValue.includes(normalizedQuery) ? 1 : 2;
      return { value, index, matches, score };
    })
    .filter((item) => item.matches)
    .sort((left, right) => left.score - right.score || left.index - right.index)
    .slice(0, 5)
    .map((item) => item.value);
}

export function getChatSuggestions({ query, mode, hasVersion, contractTypeId }) {
  const housing = contractTypeId === "housing_rent";
  let items;
  if (!hasVersion) items = CHAT_SUGGESTIONS.create;
  else if (mode === "add") items = housing ? [...CHAT_SUGGESTIONS.housingAdd, ...CHAT_SUGGESTIONS.add] : CHAT_SUGGESTIONS.add;
  else if (mode === "dispute") items = CHAT_SUGGESTIONS.dispute;
  else items = housing ? [...CHAT_SUGGESTIONS.housingQuestion, ...CHAT_SUGGESTIONS.question] : CHAT_SUGGESTIONS.question;
  return rankSuggestions(items, query);
}

export function getSessionSearchSuggestions(sessions, query) {
  const normalizedQuery = normalize(query);
  if (!normalizedQuery) return [];
  const seen = new Set();
  return sessions
    .filter((session) => {
      const source = normalize(`${session.title || ""} ${session.party_2_email || ""}`);
      return normalizedQuery.split(/\s+/).every((word) => source.includes(word));
    })
    .filter((session) => {
      if (seen.has(session.id)) return false;
      seen.add(session.id);
      return true;
    })
    .slice(0, 5);
}

export const SUGGESTION_BEHAVIOR = Object.freeze({
  maxVisible: 5,
  keyboard: ["ArrowDown", "ArrowUp", "Enter", "Tab", "Escape"],
  privateSearchHistoryOnly: true,
});

export const FORM_HINTS = Object.freeze({
  organization: "Наименование организации или ИП",
  signerName: "ФИО подписанта",
  fullName: "Фамилия Имя Отчество",
  passport: "Паспорт: 0000 000000",
  inn: "ИНН: 10 или 12 цифр",
  ogrn: "ОГРН или ОГРНИП: 13 или 15 цифр",
  phone: "Телефон: +7 900 000-00-00",
  email: "name@example.com",
  counterpartyEmail: "Email второй стороны",
  sessionSearch: "Название, контрагент или статус",
});
