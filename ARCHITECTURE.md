# AI-Arbitr: текущая архитектура MVP

Дата анализа: 23 сентября 2026 г.  
Версия приложения: `0.10.0-beta`  
Область анализа: исполняемый код, конфигурация сборки и тесты текущего репозитория. Проектные планы из `docs/` не считаются реализованными, если им нет соответствия в коде.

## 1. Общая картина

AI-Arbitr — монолитное web-приложение с React SPA и FastAPI API. Frontend и backend собираются в отдельные Docker-контейнеры. PostgreSQL хранит пользователей, договорные сессии, версии, сообщения, участников, токены и аналитику. Caddy завершает TLS и проксирует `/api/*`, `/auth/*` и `/download/*` в backend, остальные запросы — в frontend Nginx.

Основная бизнес-логика backend сосредоточена в `backend/app/main.py` (около 3 700 строк). Каталоги договоров, шаблоны, AI gateway, email/PDF и workflow частично вынесены в модули. Frontend аналогично в основном сосредоточен в `frontend/src/main.jsx` (около 2 800 строк), без React Router и отдельного state manager.

## 2. Стек и зависимости

### Backend

- Python 3.12 (production image `python:3.12-slim`).
- FastAPI `0.115.6`, Uvicorn `0.34.0`.
- SQLAlchemy `2.0.36`, PostgreSQL 16, драйвер `psycopg` 3.
- Pydantic Settings для env-конфигурации.
- `itsdangerous` для подписанных cookie.
- `httpx` для Yandex Foundation Models API.
- стандартные `smtplib`/`email` для SMTP.
- ReportLab для PDF.
- `python-multipart` установлен, но upload endpoint в коде отсутствует.

### Frontend

- React и ReactDOM (версии зафиксированы lock-файлом, в `package.json` указаны как `latest`).
- Vite 8 и `@vitejs/plugin-react`.
- Lucide React для иконок.
- Обычный CSS; UI-kit, form library, router, query/cache library и frontend test framework отсутствуют.
- PWA manifest и иконки присутствуют; service worker отсутствует.

### Инфраструктура

- Docker Compose.
- Nginx внутри frontend-контейнера для SPA/static assets.
- Caddy 2.10 как внешний reverse proxy и автоматический TLS.
- Yandex Cloud VM является текущей средой deployment по документации и production-конфигурации.
- Yandex Foundation Models API обслуживает и YandexGPT, и Qwen.
- SMTP по умолчанию настроен на Yandex Mail.

## 3. Структура репозитория

```text
AI-Arbitr/
├── backend/
│   ├── app/
│   │   ├── main.py                    # FastAPI app, schemas, endpoints и основная domain logic
│   │   ├── catalogs/
│   │   │   ├── contracts.py           # типы договоров, роли, builders и каталог
│   │   │   ├── chat_intents.py        # rule-based intent/off-topic detection
│   │   │   └── contract_poll.py       # варианты голосования
│   │   ├── core/config.py             # Settings из env
│   │   ├── db/base.py                 # SQLAlchemy DeclarativeBase
│   │   ├── db/session.py              # engine, SessionLocal, dependency
│   │   ├── models/entities.py         # все ORM entities/enums
│   │   ├── services/
│   │   │   ├── auth.py                # токены и подписанные cookie
│   │   │   ├── contract_templates.py  # фиксированные шаблоны договоров
│   │   │   ├── email.py               # magic link/invite/sign/dispute SMTP
│   │   │   ├── pdf.py                 # договор и справка ReportLab
│   │   │   ├── privacy.py             # детектор паспортоподобных данных
│   │   │   ├── prompts.py             # основные contract/dispute prompts
│   │   │   └── yandex_gpt.py           # Foundation Models gateway/fallback
│   │   ├── workflows/
│   │   │   ├── contract.py            # stages/actions и разрешённые переходы
│   │   │   └── dispute.py             # восстановление спора из message markers
│   │   └── version.py                 # версия приложения/шаблона
│   ├── test_*.py                       # unittest-модули
│   ├── requirements.txt
│   └── Dockerfile / Dockerfile.dev
├── frontend/
│   ├── src/main.jsx                    # SPA, auth, chat, review, signing, dispute, sidebar
│   ├── src/LandingPage.jsx             # лендинг
│   ├── src/KnowledgeBase.jsx            # индекс и статья базы знаний
│   ├── src/ContractTypePoll.jsx         # публичное голосование
│   ├── src/knowledgeContent.js          # статический контент базы знаний
│   ├── src/catalogs/                    # feedback/suggestion dictionaries
│   ├── src/*.css                        # стили приложения/лендинга/knowledge base
│   ├── public/                          # PWA icons, robots, sitemap, llms.txt, runtime config
│   ├── index.html
│   ├── nginx.conf
│   └── Dockerfile / Dockerfile.dev
├── deploy/
│   ├── Caddyfile                        # production TLS/reverse proxy
│   └── config.js                        # production API URL `/api`
├── docs/                                # продуктовые правила, roadmap, lifecycle и ручной E2E
├── scripts/
│   ├── lifecycle_preflight.py           # HTTP smoke/preflight
│   └── check_version.py                 # согласованность VERSION-файлов
├── docker-compose.yml                   # local development
├── docker-compose.prod.yml              # production
├── .env.example / .env.prod.example
└── VERSION, CHANGELOG.md, README.md
```

## 4. Frontend/backend boundary

Frontend — полностью клиентская SPA. Она хранит UI-state в React `useState`, часть восстановления — в `localStorage`, а серверную истину получает через JSON API. Runtime base URL читается из `window.__AI_ARBITR_CONFIG__.apiUrl`; production использует `/api`, development public config — `http://localhost:8000`.

Backend отвечает за:

- аутентификацию и cookie;
- права доступа к сессии;
- создание и версионирование текста;
- workflow checks;
- вызовы LLM;
- SMTP;
- финализацию и PDF;
- аналитику.

Frontend местами использует backend `workflow`, но не полностью управляется им. Например, часть видимости кнопок вычисляется из `status`, participant approvals и локального `chatMode`. Публичный review-flow вызывает отдельный `/review/{token}/request-changes`; generic authenticated `/sessions/{id}/request-changes` и `/versions` frontend не вызывает.

## 5. Pages и маршруты

Маршрутизация сделана вручную через `window.location.pathname` в `main.jsx`.

| Path | Реализация | Назначение |
|---|---|---|
| `/` | `App` в `main.jsx` | чат, история, создание/подписание/исполнение/спор |
| `/landing` | `LandingPage.jsx` | публичный лендинг |
| `/knowledge` | `KnowledgeBase.jsx` | каталог статей |
| `/knowledge/:slug` | `KnowledgeBase.jsx` | статья из `knowledgeContent.js` |
| `/privacy` | `PrivacyPage` в `main.jsx` | политика |
| `/terms` | `TermsPage` в `main.jsx` | правила сервиса |
| `/review/:invite_token` | review branch в `main.jsx` | публичный просмотр и подпись стороны B |

Nginx возвращает `index.html` для неизвестного frontend path. Отдельного SSR нет; `index.html` содержит короткий SEO fallback, который React заменяет при запуске.

### Основной UI flow

1. На `/` frontend вызывает `/auth/me`; при 401 автоматически создаёт guest через `/auth/guest`.
2. Пользователь создаёт сессию кнопкой «Новый договор» (`POST /sessions`).
3. Сообщение уходит в `POST /sessions/{id}/messages`.
4. После появления версии пользователь задаёт вопросы, добавляет условия или переходит к согласованию.
5. Для отправки приглашения guest должен привязать email через quick registration/magic link flow.
6. Сторона B открывает `/review/:token`, вводит реквизиты и подписывает.
7. Сторона A получает уведомление, открывает сессию и подписывает.
8. После финализации UI блокирует обычное редактирование и показывает исполнение/спор/справку.

## 6. Модель данных и связи

Все ORM entities находятся в `backend/app/models/entities.py`.

### `users`

- UUID `id`, unique `email`.
- timestamps/login counter.
- флаги согласий и `consent_version`.
- guest определяется не отдельным полем, а суффиксом email `@guest.ai-arbitr.local`.

### `auth_tokens`

- hash одноразового magic-link token, email, expiry, `used`.
- опциональный `guest_user_id` позволяет при подтверждении перенести owned guest sessions к существующему пользователю.

### `sessions` (`ContractSession`)

- owner (`owner_user_id -> users`).
- `status`: только `draft | in_review | finalized`.
- soft-delete `is_deleted`, completion `is_completed`.
- invite/download tokens и expiry.
- `pending_signing_content` — временный полный текст с внесёнными реквизитами.
- `final_content_hash` SHA-256.
- юридические роли сторон хранятся строками отдельно от технических `party_1/party_2`.
- one-to-many: participants, versions, messages.

### `contract_participants`

- unique `(session_id, role)`; роли только `party_1`, `party_2`.
- nullable `user_id`; для стороны B изначально пустой, при invite присваивается User.
- `approval_status`, `approved_version_id`, `joined_at`, `signed_at`, `completed_at`.
- `approved_version_id` хранит UUID, но в ORM не объявлен ForeignKey к `contract_versions`.

### `contract_versions`

- номер, полный текст, created time, `is_final`.
- app version, template id и template version.
- уникальное ограничение `(session_id, version_number)` отсутствует.

### `messages`

- роли `user | assistant | system`, text и timestamp.
- хранит и чат, и machine-readable event markers (`VERSION_CREATED|...`, `DELAY_NOTICE|...` и др.).

### Служебные таблицы

- `rate_limit_events`: счётчик действий по user/email/IP.
- `analytics_events`: append-only продуктовые события и JSON properties.
- `contract_analytics_snapshots`: денормализованный срез договора и отдельных условий.
- `contract_type_votes`: публичное голосование по типам договоров.

Схема создаётся через `Base.metadata.create_all()`. Alembic/migration framework отсутствует. `ensure_runtime_schema()` выполняет ручные `ALTER TABLE ... ADD COLUMN` для части исторически добавленных полей. На startup выполняется backfill analytics snapshots.

## 7. Авторизация и идентификация сторон

### Cookie/session

- Cookie содержит подписанный `user_id` (`itsdangerous.URLSafeTimedSerializer`), не серверную session запись.
- TTL cookie: 30 дней; `HttpOnly`, `SameSite=Lax`, `Secure` только если `APP_BASE_URL` начинается с HTTPS.
- Password auth отсутствует.

### Guest

`POST /auth/guest` всегда создаёт новый User с техническим email и demo-session, затем устанавливает cookie. Это обеспечивает вход без регистрационного экрана.

### Email account

- `/auth/register` и `/auth/magic-link` принимают согласия и отправляют одноразовую ссылку (10 минут).
- `/auth/quick-register` преобразует нового guest в email-user без предварительной проверки адреса, если такого email ещё нет. Если email существует, отправляется magic link и guest sessions затем переносятся при verify.
- `/auth/login` доступен только для уже существующего email.
- `verified_ip` cookie и `trusted_login_count` существуют, но логика VPN-проверки/каждого десятого входа в текущем коде не реализована; счётчик только сбрасывается.

### Стороны договора

- `party_1` — owner/создатель, не юридическая роль.
- `party_2` — получатель приглашения.
- `creator_legal_role` выбирается перед invite; противоположная роль назначается через каталог типов договоров.
- Invite создаёт/находит User второй стороны сразу по email и связывает его с participant.
- Review link не требует auth cookie. Подписание B защищено possession of token + точным совпадением payload email с invited email.
- Review approval не устанавливает auth cookie стороне B. Для последующего входа в основной чат B нужен отдельный magic-link login.

## 8. Состояние и жизненный цикл договора

Coarse state хранится в `sessions.status`, но точный этап вычисляется `build_workflow_context()` + `workflows/contract.py` из набора признаков:

`draft → ready_to_invite → awaiting_counterparty → awaiting_creator → active → dispute/completed/deleted`.

`save_contract_version()` является центральной операцией версионирования:

- чистит markdown;
- принудительно вставляет утверждённый AI-Arbitr dispute section;
- назначает очередной номер и номер договора;
- определяет template metadata;
- ставит session `in_review`;
- сбрасывает approvals/signatures обеих сторон;
- очищает pending signing content/hash;
- пишет `VERSION_CREATED` и analytics.

Invite token живёт до 7 дней и становится недействительным после подписи B или запроса правок. Workflow считает приглашение активным только при наличии token и `VERSION_SENT|`; повторная отправка создаёт новый token.

После подписи B полный текст с её реквизитами хранится в `pending_signing_content`. После подписи A в него добавляются реквизиты A, этот текст записывается в текущую `ContractVersion.content`, версия становится final, session — finalized, вычисляется hash и создаётся download token. Затем `pending_signing_content` очищается.

После финализации текст менять и session удалять нельзя. Исполнение закрывается только после `completed_at` обоих participants.

Автоматическое истечение срока/пролонгация не реализованы: нет структурированных contract start/end dates и scheduler/background worker.

## 9. Переговоры и редактирование

Основной negotiation механизм до invite — чат стороны A:

- intent detector отличает question/addition/agreement/show/rollback;
- вопрос не создаёт версию;
- addition сначала проходит rule-based/LLM legal review и предлагает краткую/расширенную редакцию;
- выбор редакции вставляет норму эвристически в подходящий раздел и создаёт новую полную версию;
- rollback не переключает pointer, а создаёт новую версию с текстом предыдущей;
- «покажи договор» возвращает последнюю сохранённую версию.

`collect_pending_norms_into_contract()` дополнительно собирает нормы из assistant messages перед invite, если они ещё не вошли в текст.

Для второй стороны текущий MVP UI предлагает только просмотр и подпись. `POST /sessions/{id}/request-changes` существует и сбрасывает approvals, но frontend его не вызывает, AI новую версию автоматически не создаёт, email другой стороне не отправляет. Полного циклического согласования двух сторон в реальном UI нет.

## 10. AI-архитектура

### Gateway и модели

`backend/app/services/yandex_gpt.py` вызывает:

`POST https://llm.api.cloud.yandex.net/foundationModels/v1/completion`

Поддерживаемые ключи UI/API:

- `yandexgpt` → `yandexgpt-5.1` или `YANDEX_GPT_MODEL_URI`;
- `qwen` → `qwen2.5-7b-instruct`.

Если первая выбранная модель отвечает timeout/429/5xx/ошибкой availability, gateway пробует вторую. Hidden reasoning запрашивается первым вызовом; при unsupported response запрос повторяется без reasoning. Streaming отсутствует, timeout 90 секунд, max tokens 4000, temperature 0.2.

### Prompts

- `services/prompts.py`: большой `CONTRACT_SYSTEM_PROMPT`, облегчённый `SIMPLE_CONTRACT_SYSTEM_PROMPT`, `build_dispute_prompt()`, утверждённый dispute text/disclaimer.
- `main.py`: inline prompts для ответов на вопросы, проверки добавления, вариантов нормы и краткого summary.
- `services/yandex_gpt.py`: fallback legal system prompt, если вызывающая функция не передала system message.

### Генерация договора

`catalogs/contracts.py` сначала классифицирует запрос rule-based. Для найма жилья, сайта и AI-помощника магазина используются фиксированные builders из `contract_templates.py`; LLM не вызывается. Для остальных видов `send_message()` вызывает `SIMPLE_CONTRACT_SYSTEM_PROMPT` и передаёт историю текущего чата через `llm_conversation()` плюс последний запрос.

Ответ проходит:

- юридическую нормализацию заголовка;
- очистку markdown;
- принудительную вставку единого dispute section;
- numbering/version metadata;
- сохранение полной версии.

### Вопросы и изменения

При вопросе модели передаются system instructions, полная последовательность user/assistant messages, последний вопрос, краткое представление последних сообщений и полный текущий договор как reference. Ответ не должен менять договор.

При addition LLM получает текущий договор, пользовательскую просьбу и предыдущую conversation. После выбора редакции изменение применяет backend-функция `add_norm_to_contract()`, а не свободный текст «внесено» модели.

Rule-based special cases покрывают, среди прочего, повышение платы, депозит, кальян и использование жилья для услуг.

## 11. Реализованный AI-Arbitr / спор

Спор не является отдельной entity. Его состояние восстанавливается `workflows/dispute.py` из system messages:

- `DISPUTE_OPENED`;
- `DELAY_NOTICE` с deadline;
- `DELAY_RESPONSE`;
- `BREACH_NOTICE`;
- `DISPUTE_DECISION`;
- `DISPUTE_ACCEPTED`;
- `DISPUTE_CLOSED`.

Фактический процесс в `send_message()`:

1. На finalized contract первое сообщение `СПОР: ...` создаёт notice и срок +3 рабочих дня, email другой стороне.
2. Другая сторона отвечает `ОТВЕТ: ...`; ответ и marker сохраняются, инициатору отправляется email.
3. Инициатор повторно описывает неисполнение после ответа либо после истечения срока.
4. `build_dispute_prompt()` передаёт модели финальный договор, всю историю сообщений и описание спора. Модель должна выдать факты, заключение, рекомендации и disclaimer, процитировать ответственность и рассчитать требование при наличии данных.
5. Ответ сохраняется как assistant message, добавляются `BREACH_NOTICE` и `DISPUTE_DECISION`, другой стороне отправляется email.
6. `POST /sessions/{id}/dispute/accept` пишет согласие пользователя. После согласия обоих session помечается completed, пишется `DISPUTE_CLOSED|agreement`, обеим сторонам отправляется email о прекращении.

Нет upload документов, проверки содержимого доказательств, отдельной сущности decision, неизменяемого hash решения, фонового job по deadline или ветки «не согласен/обратиться в суд». Запуск второго этапа требует нового сообщения инициатора.

## 12. API endpoints

### Public/system

| Method/path | Назначение |
|---|---|
| `GET /health` | health + app version |
| `GET /workflow/catalog` | stages/actions dictionary |
| `GET /contracts/catalog` | contract types/roles/template metadata |
| `GET/POST /contract-type-poll` | публичное голосование |
| `GET /stats` | публичные агрегированные счётчики |

### Auth/feedback

| Method/path | Назначение |
|---|---|
| `POST /auth/guest` | новый guest + cookie |
| `POST /auth/register` | регистрация и magic link |
| `POST /auth/quick-register` | привязка нового email к guest либо verify existing account |
| `POST /auth/login` | magic link существующему user |
| `POST /auth/magic-link` | create-or-login с consent |
| `GET /auth/verify` | consume token, migration guest sessions, cookie, redirect |
| `GET /auth/me` | текущий user/guest/consent state |
| `POST /auth/consent` | сохранить unified consent |
| `POST /auth/logout` | удалить cookies |
| `POST /feedback` | отправить feedback через SMTP |

### Contracts

| Method/path | Назначение |
|---|---|
| `POST /sessions` | создать session + два participants |
| `GET /sessions` | список доступных sessions + demo session |
| `GET /sessions/{id}` | полная session detail, versions, messages, workflow, key terms, dispute |
| `DELETE /sessions/{id}` | soft delete owner draft/review |
| `GET /contacts?q=` | email suggestions из общих contracts |
| `POST /sessions/{id}/messages` | единая chat/generation/edit/dispute command |
| `POST /sessions/{id}/versions` | вручную сохранить полный текст как новую версию |
| `POST /sessions/{id}/invite` | назначить роли/B, token, email invite |
| `POST /sessions/{id}/approve` | подпись A и возможная финализация |
| `POST /sessions/{id}/request-changes` | сохранить запрос правок и сбросить approvals |
| `POST /sessions/{id}/complete` | подтверждение исполнения одной стороной |
| `POST /sessions/{id}/dispute/accept` | принять AI decision; закрыть после двух согласий |
| `GET /sessions/{id}/certificate.pdf` | auth-protected interaction certificate |

### Public review/download

| Method/path | Назначение |
|---|---|
| `GET /review/{token}` | направленная версия, terms, email/role B |
| `GET /review/{token}.pdf` | inline review PDF |
| `POST /review/{token}/approve` | реквизиты и подпись B |
| `POST /review/{token}/request-changes` | сохранить предложение B, сбросить подписи и уведомить A |
| `GET /sessions/{id}/contract.pdf` | финальный PDF для authenticated participant |
| `GET /download/{token}.pdf` | всегда `410`; постоянное хранение final PDF отключено |

## 13. Файлы и PDF

Пользовательские файлы не загружаются и не хранятся. Object storage/local upload directory отсутствуют.

PDF создаётся ReportLab в `BytesIO`:

- review PDF строится on demand;
- final contract и certificate строятся после подписи A и прикрепляются к email;
- certificate можно повторно сгенерировать через auth endpoint;
- final PDF повторно генерируется и скачивается authenticated участником через session endpoint; legacy permanent link возвращает `410`.

Лицензионный OTF ожидается вне Git в host path `../ai-arbitr-assets/fonts`, монтируется read-only в frontend. PDF ищет доступный font path и имеет DejaVu fallback.

## 14. Email/invite

`services/email.py` синхронно открывает SMTP SSL connection на каждый send. Queue/retry/delivery webhook отсутствуют.

Реализованы:

- magic link;
- invite B с web link и review PDF link, отдельная копия A;
- уведомление A о подписи B;
- финальное письмо обеим сторонам с contract PDF и certificate PDF attachments + calendar link;
- dispute notices;
- feedback на support mailbox.

Invite/finalization сначала фиксируют бизнес-операцию, затем выполняют SMTP как побочный эффект. API возвращает `email_delivery`/`email_deliveries` со статусом `sent`, `failed` или `not_configured`; при сбое остаётся ручная review-ссылка. Bounce handling и retry queue отсутствуют.

## 15. Переменные окружения и внешние сервисы

Без значений секретов используются:

- `APP_ENV`, `APP_BASE_URL`, `API_BASE_URL`;
- `APP_SECRET_KEY`;
- `CORS_ORIGINS`;
- `DATABASE_URL`, а в compose также `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`;
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`;
- `YANDEX_GPT_API_KEY`, `YANDEX_GPT_FOLDER_ID`, `YANDEX_GPT_MODEL_URI`.

Внешние сервисы: Yandex Foundation Models API, Yandex-compatible SMTP, DNS/domain/TLS и Yandex Cloud VM. Calendar integration — сформированная Google Calendar URL, API/OAuth календаря нет.

## 16. Build и deployment

Local `docker-compose.yml`:

- PostgreSQL exposed `5432`;
- backend dev container exposed `8000` с bind mount;
- Vite dev server exposed `5173` с bind mount.

Production `docker-compose.prod.yml`:

- DB с named volume `postgres_data`;
- backend Uvicorn без host port;
- frontend multi-stage build Node → Nginx;
- Caddy публикует `80/443`, TLS data/config в named volumes;
- Caddy HTTP/3 отключён (`h1 h2`) и UDP 443 не публикуется;
- runtime frontend config и лицензированный font монтируются с host.

Frontend hashed assets cache immutable; HTML/config имеют no-cache. CI/CD pipeline в репозитории отсутствует; deployment выполняется Docker Compose вручную.

## 17. Тесты

Backend использует стандартный `unittest`: сейчас 45 тестов в десяти файлах, включая 44 существующих regression-теста и migration smoke test.

Покрыты:

- model fallback;
- intent/off-topic detection;
- catalog/template selection и role pairs;
- poll behavior;
- workflow stages/actions;
- отдельная email formatting проверка;
- key terms;
- consent, demo data replacement и несколько addition rules.

Не покрыты автоматическими тестами:

- реальные FastAPI endpoint chains с isolated SQLite test DB, mock LLM и mock SMTP;
- auth cookies/magic links;
- invite expiry/access control;
- bilateral review/change/reinvite, обе подписи, PDF и email-failure continuity;
- dispute E2E до принятия решения обеими сторонами;
- frontend component/browser behavior;
- deployment/SMTP/LLM integration.

`scripts/lifecycle_preflight.py` — HTTP smoke check, а `docs/e2e-test-protocol.md` — ручной протокол, не автоматический E2E suite.

## 18. Незавершённая и временная логика

- Запрос правок B подключён к review UI, но сам не создаёт новую AI-версию: A принимает предложение в основном чате и вручную запускает добавление условия.
- Файловые доказательства спора нельзя приложить, хотя dispute prompt их предполагает.
- Автоматические deadlines, reminders, expiry contract и prolongation отсутствуют.
- `/download/{token}.pdf` содержит недостижимый legacy code после безусловного `410`.
- UI action «перегенерировать ответ» показывает toast «добавим следующим шагом».
- thumbs up/down дают только toast, не пишут feedback/analytics.
- `trusted_login_count` и verified-IP cookie не реализуют заявленную периодическую/VPN verification.
- В `main.py` остаётся legacy demo contract text, отличный от основного fixed template.
- Docs lifecycle содержит устаревший `GAP-02`: acceptance/closure спора уже есть в коде, но весь процесс всё ещё неполон по доказательствам/автоматизации.
- README содержит старые Cloudflare tunnel URLs и местами более сильные заявления, чем подтверждено реализацией.
- Нет schema migration history, background worker, transactional outbox, task queue и delivery status.

# 19. План эволюции: «Договорились» и AI-Arbitr

Этот раздел описывает целевую архитектуру и план миграции. В отличие от разделов 1–18, он не утверждает, что перечисленные компоненты уже реализованы. Главное ограничение: действующий AI-Arbitr и его данные продолжают работать на каждом этапе.

## 19.1 AS-IS и повторное использование

Фактический aggregate root системы — строка `sessions`, представленная ORM-классом `ContractSession`. Она уже связывает владельца, двух участников, общий диалог, версии юридического документа, приглашение, подписи, исполнение и спор. Поэтому создавать рядом независимый aggregate `dogovorilis_agreements` нельзя.

Переиспользуются без копирования:

| Существующая часть | Роль в общей модели Agreement |
|---|---|
| `sessions.id` | стабильный идентификатор Agreement в обоих интерфейсах |
| `contract_participants` | стороны и их связь с аккаунтами |
| `messages` | общий разговор сторон и AI, включая существующую историю |
| `contract_versions` | представления `LEGAL_DOCUMENT`; не источник существенных условий |
| approval/signature fields | подтверждение и подписание юридической версии |
| invite token и email | начальный механизм присоединения второй стороны |
| `pending_signing_content`, final version/hash | действующий signing/PDF pipeline |
| auth cookie и `users` | общая идентичность для двух frontend-приложений |
| Foundation Models gateway | общий AI transport/fallback, но не будущая orchestration layer |
| analytics events | журнал продуктовых событий с добавлением surface/agreement state |

Нельзя считать полноценной Agreement-моделью:

- `SessionStatus` с тремя значениями: он описывает документ, но не переговоры и исполнение;
- workflow, вычисляемый из текстовых маркеров `messages`;
- свободный текст договора как единственный источник условий;
- dispute, полностью восстановленный из строк `DISPUTE_*`;
- `completed_at` участника как единственная модель исполнения.

## 19.2 TO-BE: один aggregate, два UX

На переходном этапе Agreement остаётся физически строкой `sessions`. В новом domain/API используется имя `Agreement`, а существующий `ContractSession` становится compatibility representation той же записи. Создание через `/agreements` и через `/sessions` всегда возвращает один и тот же UUID; открытие в другом интерфейсе не создаёт копию и не запускает миграцию данных.

```text
                    ┌─ «Договорились» frontend ─ /agreements API ─┐
User/Auth/Cookie ───┤                                               ├─ Agreement aggregate (`sessions.id`)
                    └─ AI-Arbitr frontend ──── /sessions API ──────┘
                                                                      ├─ participants
                                                                      ├─ messages
                                                                      ├─ structured terms
                                                                      ├─ legal documents/versions
                                                                      ├─ performance facts/events
                                                                      ├─ dispute/positions
                                                                      └─ settlement
```

Новые поля `sessions` вводятся аддитивно и nullable/default-safe:

- `relationship_state`: lifecycle самого Agreement: `intent`, `negotiating`, `agreed`, `documenting`, `signed`, `performing`, `completed` или `terminated`;
- `product_surface`: где объект был создан (`ai_arbitr` или `dogovorilis`), но не где он может открываться;
- `intent_text` и `understanding_summary`;
- `based_on_agreement_id` для необязательной связи «создано на основе Agreement»; несколько новых Agreement могут ссылаться на один источник, линейная последовательность не предполагается;
- `state_version` для optimistic concurrency;
- timestamps ключевых переходов без удаления существующих `status/finalized_at/completed_at`.

Споры и урегулирования имеют независимые состояния в собственных сущностях. Agreement может оставаться `performing` во время и после одного или нескольких disputes/settlements; settlement изменяет условия или фиксирует результат, но не завершает отношения автоматически. Старый `SessionStatus` сохраняется как compatibility projection: `intent..documenting` отображаются в `draft/in_review`, а `signed..performing` совместимы с `finalized`. Новый workflow не должен выводить состояние обратно из текста сообщений.

## 19.3 Минимальные новые доменные сущности

Структура строится вокруг операций пользователей, а не механического переноса всех пунктов задания в таблицы.

### AgreementTerm

Структурированное условие до генерации юридического текста:

- agreement и расширяемый строковый `semantic_key` (`core.subject`, `payment.price`, `delivery.deadline` или namespaced ключ нового домена);
- понятный сторонам label/value;
- kind: essential/additional;
- status: proposed/agreed/rejected/superseded;
- автор: A, B или AI;
- revision и timestamps.

`semantic_key` не является DB enum и не ограничивается CHECK constraint: новые типы условий добавляются каталогом/application code без migration. Значение хранится в расширяемом JSON payload с отдельным человекочитаемым представлением. Подтверждения хранятся отдельно (`AgreementTermConfirmation`) по participant и revision. Условие становится agreed только после требуемых подтверждений обеих сторон. Юридический документ строится из agreed terms, но последующие версии документа не уничтожают их.

### PerformanceEvent

Единый журнал исполнения и фактов:

- type и понятное описание;
- actor/subject participant;
- статус `claimed`, `confirmed`, `disputed`;
- сумма/дата и расширяемый JSON payload;
- связь с условием и предыдущим событием при необходимости.

Подтверждение другой стороны хранится как отдельное действие. Evidence не требуется для confirmed/undisputed event и подключается только после оспаривания.

### Dispute и Settlement

Спор получает собственную запись, а не только message markers:

- disputed performance events/terms;
- позиции участников (`DisputePosition`);
- выделенные AI undisputed/disputed facts;
- предлагаемое урегулирование;
- состояние и timestamps.

`Settlement` содержит структурированный результат и подтверждения обеих сторон. Только после двух подтверждений он становится частью истории Agreement. Существующие `DISPUTE_*` markers сохраняются для старых объектов и compatibility UI, но новые записи становятся источником истины.

### LegalDocument

На первом этапе отдельная таблица не обязательна: `contract_versions` остаётся реализацией legal document revisions для одного Agreement. Когда понадобится несколько документов/допсоглашений, вводится контейнер `legal_documents`, а существующие версии связываются с автоматически созданным primary document без копирования текста.

## 19.4 Conversation и knowledge layer

`messages` остаётся общей хронологией, но ключевые ответы больше не собираются ad hoc внутри `main.py`.

Вводится versioned каталог conversation scenarios с тремя режимами ответа:

- `fixed`: неизменяемые подтверждения, предупреждения и критичные domain transitions;
- `templated`: контролируемая структура с подстановкой проверенных domain values;
- `generative`: естественный разговор, объяснения и уточнения через LLM в заданных границах и schema.

```text
scenario key + version + lifecycle state + actor role
→ allowed intents
→ response mode: fixed / templated / generative
→ fixed text, template или AI task/schema
→ required domain command
→ next-state hints
```

Ключевые подтверждения и переходы состояния используют fixed/templated сценарии и тестируются snapshot/contract-тестами отдельно от LLM. Understanding, обычные вопросы, объяснения и совместное уточнение условий остаются generative: каталог контролирует задачу и допустимое действие, но не превращает разговор в набор canned responses. Сценарии покрывают как минимум understanding, term confirmation, invite, negotiation, signing, performance confirmation, dispute positions и settlement acceptance.

AI orchestration получает:

1. разрешённую задачу и JSON schema ответа;
2. текущее состояние Agreement;
3. agreed/proposed terms;
4. последние релевантные сообщения обеих сторон;
5. retrieved fragments публичной Knowledge Base;
6. юридический контекст только для задач, где он нужен.

Ответ модели не меняет состояние напрямую. Сначала он валидируется, затем domain command сохраняет terms/facts/positions. Продуктовые вопросы обслуживаются тем же conversation endpoint с retrieval по Knowledge Base; отдельный help-bot не создаётся.

## 19.5 API boundary

Новый API добавляется рядом со старым, а не заменяет его:

```text
POST   /agreements                         создать intent Agreement
GET    /agreements                         список отношений для текущего пользователя
GET    /agreements/{id}                    human-oriented projection
POST   /agreements/{id}/conversation       intent routing + conversation scenario
POST   /agreements/{id}/terms/{id}/confirm подтверждение/отклонение условия
POST   /agreements/{id}/invite             присоединение второй стороны
POST   /agreements/{id}/legal-document     построение документа из agreed terms
POST   /agreements/{id}/performance-events заявить факт исполнения
POST   /performance-events/{id}/confirm    подтвердить или оспорить факт
POST   /agreements/{id}/disputes            открыть спор по disputed facts
POST   /disputes/{id}/positions             позиция стороны
POST   /disputes/{id}/settlement            сформировать предложение
POST   /settlements/{id}/accept             принять результат
POST   /agreements/{id}/continue            создать новый связанный Agreement
```

Имена и payload будут закрепляться OpenAPI contract-тестами до реализации frontend. Старые `/sessions`, `/review`, PDF и auth endpoints сохраняются. Access control всегда проверяется по общему `sessions.id` и `contract_participants`, независимо от вызывающего frontend.

## 19.6 Frontend boundary

Создаётся отдельное React-приложение `dogovorilis-frontend`; существующий `frontend` не переделывается и продолжает собираться как AI-Arbitr. Оба используют один backend и auth cookie domain.

Минимальные пространства «Договорились»:

- START: «О чём хотите договориться?» и одно поле;
- «Договариваемся»: understanding и terms в разговоре;
- «Договорились»: общее подтверждение, legal document и signing;
- «Исполняем»: следующее действие, факты исполнения и подтверждения;
- dispute/settlement внутри того же разговора;
- dashboard «Мои договорённости» с контрагентом, предметом, состоянием и следующим действием;
- контекстная ссылка «Открыть в AI-Arbitr» с тем же Agreement ID.

Progressive auth использует существующего guest User. До сохранения/invite Agreement принадлежит guest; quick registration переносит этот же user/session, поэтому первое AI-взаимодействие не требует формы входа.

## 19.7 Capability layer

Paywall в core lifecycle не добавляется. Backend получает декларативные capabilities (`agreement.core`, `legal_document.advanced_edit`, `ai.model.select`, `organization.manage`, `api.access` и т. п.). На первом этапе все core capabilities разрешены, а существующий AI-Arbitr не ограничивается. Проверки capability централизуются и не зашиваются в frontend conditionals.

## 19.8 Безопасный migration plan

### Фаза A: migration foundation

1. Подключить Alembic и зафиксировать baseline текущей production schema без пересоздания таблиц.
2. Добавить nullable/default-safe поля `sessions` и новые таблицы terms/events/disputes/settlements.
3. Оставить `Base.metadata.create_all()` только для тестовой/первичной среды, production schema изменять миграциями.
4. Добавить backup/restore rehearsal и migration smoke test на копии schema.

Rollback: код старой версии игнорирует новые поля/таблицы; destructive migration отсутствует.

### Фаза B: domain facade

1. Вынести Agreement queries/commands из новых endpoints в отдельный domain/application layer.
2. Добавить adapter, который строит новый Agreement projection из старой session, participants, messages и versions.
3. Dual-write только для новых структурированных действий; существующие endpoint semantics не менять.
4. Ввести optimistic state transition и audit event на каждую команду.

### Фаза C: additive API и AI orchestration

1. Закрепить `/agreements` OpenAPI contract.
2. Реализовать versioned conversation scenarios и structured LLM responses.
3. Подключить Knowledge Base retrieval сначала как локальный индекс статических статей; внешний vector service для MVP не требуется.
4. Добавить entitlement API с разрешёнными по умолчанию core capabilities.

### Фаза D: отдельный frontend

1. Добавить `dogovorilis-frontend` отдельным build/service.
2. Настроить маршрут или отдельный host в Caddy, не меняя маршрутизацию AI-Arbitr.
3. Использовать общий cookie и deep links `/agreements/{id}` ↔ AI-Arbitr `/?session={id}`.
4. Сначала включить для test host/feature flag, затем для ограниченной аудитории.

### Фаза E: новый lifecycle

Реализовывать вертикальными срезами: intent/understanding → terms → joint negotiation → legal document/signing → performance facts → dispute/settlement → continuation. Каждый срез включает domain test, API integration test и mobile browser test. Не создавать все таблицы и UI заранее без проходящего сценария.

### Фаза F: совместимость и rollout

1. Прогнать существующие 44 backend tests и новый двухклиентный Agreement E2E.
2. Проверить старые review links, подписи, PDF, SMTP fallback и dispute flow на production-like копии БД.
3. Выполнить expand migration, deploy backward-compatible backend, deploy новый frontend; contract/cleanup migration проводить только после периода наблюдения.
4. Метрики разделять по `product_surface`, сохраняя общую аналитику Agreement.

## 19.9 Новый обязательный E2E

Два изолированных клиента A/B должны пройти один тест без прямых изменений БД:

```text
A guest intent → AI understanding → A confirms → progressive auth → invite B
→ B joins → essential terms confirmed by both → additional terms proposed/confirmed
→ legal document generated → B signs → A signs
→ A claims performance → B confirms (undisputed fact)
→ A/B create conflicting claims (disputed fact)
→ both submit positions → AI separates agreed/disputed facts
→ settlement proposed → A accepts → B accepts
→ settlement active while Agreement may keep performing
→ similar Agreement created with based_on_agreement_id
```

Тест обязан дополнительно доказать:

- один UUID открывается в обоих frontend projections;
- AI не может записать term/fact/settlement без валидированной domain command;
- подтверждение одного участника не считается согласием обоих;
- старый ContractSession API продолжает читать legal document и signing state;
- SMTP/LLM failure не откатывает уже подтверждённое действие.

## 19.10 Решения, отложенные до реализации

- публичное название/домен «Договорились»;
- окончательный URL нового frontend;
- необходимость отдельного `legal_documents` контейнера до появления второго документа;
- vector search: для MVP достаточно локального retrieval по текущей Knowledge Base;
- организации и многопользовательские роли;
- доказательства-файлы и object storage;
- automation/queue/reminders;
- тарифы и конкретные entitlement limits.

# 20. Текущий end-to-end flow MVP

## Шаг 1. A открывает сервис и создаёт договор

- UI: `App`, `createSession()`, `sendMessage()` в `frontend/src/main.jsx`.
- API: `POST /auth/guest` при отсутствии cookie; `POST /sessions`; затем `POST /sessions/{id}/messages`.
- Domain: catalog detection в `catalogs/contracts.py`; fixed builder либо LLM; `save_contract_version()`.
- DB: `users`, `sessions`, два `contract_participants`, `messages`, `contract_versions`, analytics tables.

## Шаг 2. A обсуждает и меняет договор

- UI: один chat composer; `chatMode`, suggestions и contract preview в `main.jsx`.
- API: `POST /sessions/{id}/messages`.
- Domain: `chat_intents.py`, question/addition prompts в `main.py`, `add_norm_to_contract()`, `save_contract_version()`.
- AI: Foundation Models для вопросов/universal contracts/addition review; fixed templates обходят AI.
- DB: chat в `messages`; каждое принятое изменение — новая строка `contract_versions`.

## Шаг 3. A регистрируется и приглашает B

- UI: auth modal/quick registration и `createInvite()` в `main.jsx`.
- API: `POST /auth/quick-register` или magic link; `POST /sessions/{id}/invite`.
- Domain: `assign_legal_roles()`, `collect_pending_norms_into_contract()`.
- DB: email user B создаётся/находится; `party_2.user_id`, `invite_token`, expiry, `VERSION_SENT`.
- External: `send_contract_invite()` отправляет B ссылку и A копию.

## Шаг 4. B открывает договор

- UI: `/review/:token` branch в `main.jsx`, `loadReview()`.
- API: `GET /review/{token}`, опционально `GET /review/{token}.pdf`.
- Domain: token lookup + 7-day expiry.
- DB: latest `contract_versions`, party_2 participant и session roles.

## Шаг 5. Согласование условий

На review-странице B выбирает: подписать текущую версию или предложить изменения. `POST /review/{token}/request-changes` сохраняет предложение в chat history, сбрасывает approvals/signatures, инвалидирует token и уведомляет A. A обрабатывает формулировку через обычный addition-flow, создаёт новую версию и отправляет новый token. Цикл можно повторять.

## Шаг 6. B подписывает

- UI: review form для individual/business в `main.jsx`.
- API: `POST /review/{token}/approve`.
- Domain: consent/format/email validation, `apply_ephemeral_party_data()`.
- DB: B `approved/signed_at/approved_version_id`; masked event в `messages`; полный текст временно в `sessions.pending_signing_content`.
- External: email A о готовности его подписи.
- Auth: успешная подпись устанавливает обычную signed session cookie B; token инвалидируется, а договор появляется в списке сессий B.

## Шаг 7. A подписывает и договор финализируется

- UI: owner signing form, `signAsFirstParty()`.
- API: `POST /sessions/{id}/approve`.
- Domain: добавление реквизитов A, проверка approvals обоих, `finalize_signed_session()`.
- DB: A approval/signature, current version content становится заполненным и `is_final`, session `finalized`, hash и finalized timestamp.
- PDF/email: два PDF генерируются в памяти; обеим сторонам отправляются attachments и calendar link.

## Шаг 8. Исполнение

- UI: finalized card, кнопка «Договор исполнен».
- API: `POST /sessions/{id}/complete` каждой стороной.
- DB: participant `completed_at`; после двух подтверждений `sessions.is_completed=true` и system message.

## Шаг 9. Возникает разногласие

- UI: «Открыть спор» включает dispute chat mode; `sendMessage()` добавляет смысловой prefix.
- API: `POST /sessions/{id}/messages` с `СПОР: ...`.
- DB: `DELAY_NOTICE`, `DISPUTE_OPENED`, assistant notice.
- External: email B, deadline +3 рабочих дня.

## Шаг 10. B отвечает или истекает срок

- После review-подписи B уже authenticated и открывает session из своего списка договоров.
- API: тот же messages endpoint, effective prefix `ОТВЕТ`.
- DB: user response + `DELAY_RESPONSE`.
- External: email инициатору.
- Фоновой автоматизации нет; для продолжения инициатор отправляет ещё одно сообщение.

## Шаг 11. AI-Arbitr формирует предложение

- API/domain: finalized dispute branch `send_message()` → `build_dispute_prompt()` → `ask_yandex_gpt()`.
- AI input: final contract, весь chat history, последнее описание, mandatory disclaimer.
- DB: assistant decision + `BREACH_NOTICE` + `DISPUTE_DECISION`.
- External: решение email-ится другой стороне; инициатор видит его в чате.

## Шаг 12. Стороны принимают результат

- UI: «Согласиться с решением» показывается по parsed dispute state.
- API: `POST /sessions/{id}/dispute/accept` от каждого authenticated participant.
- DB: `DISPUTE_ACCEPTED` для каждого; после двух — `DISPUTE_CLOSED|agreement`, `is_completed=true`, completed timestamp.
- External: при первом согласии email другой стороне, при втором — email обеим о завершении.

# 21. Текущая architecture map

```text
React SPA (main.jsx / LandingPage / KnowledgeBase)
  → fetch JSON/PDF
  → Caddy (/api, /auth, /download)
  → FastAPI endpoints (main.py)
  → domain helpers + workflow catalogs
      → contract catalog/fixed templates
      → intent detection/versioning/signing/dispute parser
      → PDF/email services
      → Yandex Foundation Models gateway
          → YandexGPT 5.1 or Qwen 2.5 7B fallback
  → SQLAlchemy
  → PostgreSQL

External side effects:
FastAPI → SMTP → magic links/invites/notices/PDF attachments
FastAPI → Google Calendar URL (link only)
```

# 22. MVP risks

1. **Party B identity assurance:** review signing authenticates B as the pre-created email user by possession of the invite token plus exact email match, but does not separately verify mailbox ownership at signing time.
2. **Negotiation remains intentionally minimal:** B can propose text changes, but only A can turn them into a new contract version; there is no structured diff or per-clause acceptance.
3. **Dispute evidence gap:** no file upload despite prompts referring to documents; AI can only evaluate text entered into chat and stored history.
4. **No background jobs:** three-day deadline, reminders, contract expiry and prolongation do not advance automatically.
5. **State encoded in free-text markers:** workflow/dispute/analytics parse `messages.content` prefixes; typo or manual format drift can corrupt derived state.
6. **Monolithic endpoints/components:** `send_message()` and `main.jsx` combine many states and order-sensitive branches, making regressions likely.
7. **Schema management:** `create_all` + ad hoc ALTERs provide no reversible/ordered migrations or deployment-time schema verification.
8. **Email delivery:** synchronous SMTP has no queue/retry/bounce processing. API reports immediate SMTP success/failure, not actual inbox delivery.
9. **Final PDF regeneration:** PDF is regenerated from current final DB state rather than stored as immutable bytes; integrity relies on final-version immutability and `final_content_hash` rather than object storage.
10. **Personal data transient state:** full party data is temporarily persisted in `pending_signing_content`, then final full data is persisted in final `ContractVersion.content`; this must be reconciled with privacy claims.
11. **Version race/integrity:** version number is `count()+1` without unique constraint or locking; concurrent writes can duplicate numbers.
12. **Approval reference integrity:** `approved_version_id` has no database ForeignKey.
13. **Token exposure model:** review token grants read access to the full contract until expiry or first sign/change action; approval additionally checks the invited email, but possession of the token remains the main access factor.
14. **AI reliability:** universal contracts and dispute decisions depend on remote models, one 90-second synchronous request and prompt compliance; fallback does not validate legal correctness.
15. **Fixed vs universal divergence:** fixed templates, legacy demo text and prompts can encode different rules/numbering.
16. **Workflow enforcement is partial:** not every chat branch calls `require_workflow_action`; frontend also reconstructs some states independently.
17. **Frontend E2E gap:** backend lifecycle is covered by integration tests, but browser rendering, navigation and mobile interaction still lack automated Playwright coverage.
18. **Claims vs implementation:** README/docs contain stale URLs and statements (audit metadata, protected archive, dispute behavior) stronger or older than current code.
