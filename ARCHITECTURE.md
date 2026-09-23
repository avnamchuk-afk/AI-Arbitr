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

Frontend местами использует backend `workflow`, но не полностью управляется им. Например, часть видимости кнопок вычисляется из `status`, participant approvals и локального `chatMode`. Endpoint `/request-changes` и generic `/versions` frontend не вызывает.

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

Invite token живёт 7 дней. Признак «invite sent» workflow восстанавливает по наличию `VERSION_SENT|` в system messages, а не только по token.

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
| `GET /download/{token}.pdf` | всегда `410`; постоянное хранение final PDF отключено |

## 13. Файлы и PDF

Пользовательские файлы не загружаются и не хранятся. Object storage/local upload directory отсутствуют.

PDF создаётся ReportLab в `BytesIO`:

- review PDF строится on demand;
- final contract и certificate строятся после подписи A и прикрепляются к email;
- certificate можно повторно сгенерировать через auth endpoint;
- final PDF повторно скачать по permanent link нельзя (`410`).

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

`sent` у invite означает наличие SMTP configuration, а не подтверждённую доставку. Bounce handling отсутствует. Ошибка SMTP может прервать request.

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

Backend использует стандартный `unittest`: сейчас 41 тест в восьми файлах.

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

- реальные FastAPI endpoint chains с test DB;
- auth cookies/magic links;
- invite expiry/access control;
- обе подписи и PDF/email finalization;
- dispute E2E;
- frontend component/browser behavior;
- deployment/SMTP/LLM integration.

`scripts/lifecycle_preflight.py` — HTTP smoke check, а `docs/e2e-test-protocol.md` — ручной протокол, не автоматический E2E suite.

## 18. Незавершённая и временная логика

- `request-changes` не подключён к UI и не создаёт новую AI-версию.
- Переговоры B и циклическое согласование отсутствуют.
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

# 1. End-to-end flow MVP

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

Реально реализованный MVP: B не редактирует и не ведёт переговоры, а только просматривает и решает подписать. До invite условия меняет A. Endpoint `request-changes` существует, но не участвует в UI/E2E.

## Шаг 6. B подписывает

- UI: review form для individual/business в `main.jsx`.
- API: `POST /review/{token}/approve`.
- Domain: consent/format/email validation, `apply_ephemeral_party_data()`.
- DB: B `approved/signed_at/approved_version_id`; masked event в `messages`; полный текст временно в `sessions.pending_signing_content`.
- External: email A о готовности его подписи.

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

- B должен войти в основной аккаунт отдельно и открыть session из email link.
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

# 2. Architecture map

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

# 3. MVP risks

1. **Party B continuity:** review signing does not authenticate B. Later execution/dispute acceptance requires a separate login flow, so the full two-party path can break after signing.
2. **No real bilateral negotiation:** B cannot reject or edit in the production UI; `request-changes` is orphaned.
3. **Dispute evidence gap:** no file upload despite prompts referring to documents; AI can only evaluate text entered into chat and stored history.
4. **No background jobs:** three-day deadline, reminders, contract expiry and prolongation do not advance automatically.
5. **State encoded in free-text markers:** workflow/dispute/analytics parse `messages.content` prefixes; typo or manual format drift can corrupt derived state.
6. **Monolithic endpoints/components:** `send_message()` and `main.jsx` combine many states and order-sensitive branches, making regressions likely.
7. **Schema management:** `create_all` + ad hoc ALTERs provide no reversible/ordered migrations or deployment-time schema verification.
8. **Email delivery:** synchronous SMTP, no queue/retry/bounce status; configured SMTP can be reported as sent without confirmed delivery.
9. **Final PDF availability:** final contract PDF is only emailed and not durably stored/re-downloadable; loss/non-delivery cannot be repaired through `/download`.
10. **Personal data transient state:** full party data is temporarily persisted in `pending_signing_content`, then final full data is persisted in final `ContractVersion.content`; this must be reconciled with privacy claims.
11. **Version race/integrity:** version number is `count()+1` without unique constraint or locking; concurrent writes can duplicate numbers.
12. **Approval reference integrity:** `approved_version_id` has no database ForeignKey.
13. **Token exposure model:** review token grants read access to the full contract and remains reusable until expiry; approval additionally checks email but no authenticated ownership.
14. **AI reliability:** universal contracts and dispute decisions depend on remote models, one 90-second synchronous request and prompt compliance; fallback does not validate legal correctness.
15. **Fixed vs universal divergence:** fixed templates, legacy demo text and prompts can encode different rules/numbering.
16. **Workflow enforcement is partial:** not every chat branch calls `require_workflow_action`; frontend also reconstructs some states independently.
17. **Insufficient automated E2E:** critical auth/invite/sign/PDF/dispute chain is manual and therefore vulnerable to unnoticed integration regressions.
18. **Claims vs implementation:** README/docs contain stale URLs and statements (audit metadata, protected archive, dispute behavior) stronger or older than current code.
