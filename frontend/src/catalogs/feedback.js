const MODEL_LABELS = {
  yandexgpt: "YandexGPT 5.1 Pro",
  qwen: "Qwen 2.5 7B Instruct",
};

function safePagePath(pathname = "/") {
  if (/^\/review\/[^/]+/.test(pathname)) return "/review/[private-link]";
  return pathname || "/";
}

export function buildFeedbackMailto({
  supportEmail,
  appVersion,
  model,
  sessionId,
  stage,
  pathname,
  userAgent,
  viewport,
  timestamp = new Date().toISOString(),
}) {
  const subject = `Ошибка AI-Arbitr ${appVersion}${stage ? ` · ${stage}` : ""}`;
  const body = [
    "Что произошло:",
    "",
    "",
    "Что ожидалось:",
    "",
    "",
    "Приложите скриншот к письму, если это возможно.",
    "",
    "Диагностика:",
    `Версия: ${appVersion}`,
    `Модель: ${MODEL_LABELS[model] || model || "не выбрана"}`,
    `Этап: ${stage || "не определен"}`,
    `Договор: ${sessionId || "не открыт"}`,
    `Экран: ${safePagePath(pathname)}`,
    `Размер окна: ${viewport || "не определен"}`,
    `Устройство: ${userAgent || "не определено"}`,
    `Время: ${timestamp}`,
    "",
    "Текст договора и персональные данные в диагностику не включены.",
  ].join("\n");
  return `mailto:${supportEmail}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
}

export { safePagePath };
