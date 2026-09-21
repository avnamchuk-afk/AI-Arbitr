const MODEL_LABELS = {
  yandexgpt: "YandexGPT 5.1 Pro",
  qwen: "Qwen 2.5 7B Instruct",
};

function safePagePath(pathname = "/") {
  if (/^\/review\/[^/]+/.test(pathname)) return "/review/[private-link]";
  return pathname || "/";
}

export function buildFeedbackDiagnostics({
  appVersion,
  model,
  sessionId,
  stage,
  pathname,
  userAgent,
  viewport,
  timestamp = new Date().toISOString(),
}) {
  return [
    `Версия: ${appVersion}`,
    `Модель: ${MODEL_LABELS[model] || model || "не выбрана"}`,
    `Этап: ${stage || "не определен"}`,
    `Договор: ${sessionId || "не открыт"}`,
    `Экран: ${safePagePath(pathname)}`,
    `Размер окна: ${viewport || "не определен"}`,
    `Устройство: ${userAgent || "не определено"}`,
    `Время: ${timestamp}`,
  ].join("\n");
}

export { safePagePath };
