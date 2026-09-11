# AI-Arbitr

MVP веб-сервиса "AI-Арбитр": генерация договоров через YandexGPT, двустороннее согласование, финализация и PDF-выгрузка истории.

## Стек

- Backend: FastAPI, SQLAlchemy, PostgreSQL
- Frontend: React + Vite
- Auth: Magic Link по email
- AI: YandexGPT API
- Deploy: Docker Compose, готово для Yandex Cloud/VPS

## Быстрый запуск

```bash
cp .env.example .env
docker compose up --build
```

Frontend: http://localhost:5173
Backend API: http://localhost:8000/docs

## Важные переменные

Все секреты задаются в `.env`; ключи и токены не должны попадать в git.

- `YANDEX_GPT_API_KEY`
- `YANDEX_GPT_FOLDER_ID`
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USER`
- `SMTP_PASSWORD`
- `APP_SECRET_KEY`

## Логика согласования

1. Сторона 1 создает договор в чате.
2. Система генерирует ссылку-приглашение для Стороны 2.
3. Сторона 2 авторизуется по Magic Link и принимает приглашение.
4. Каждая сторона может согласиться с текущей версией или предложить правки.
5. При правках создается новая версия договора, статусы согласия сбрасываются.
6. Финализация происходит только после согласия обеих сторон с одной версией.
