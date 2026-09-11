# Деплой тестовой версии на Yandex Cloud VM

## 1. Создать VM

Рекомендуемый минимум для MVP:

- Ubuntu 22.04
- 2 vCPU
- 2-4 GB RAM
- 20 GB SSD
- публичный IPv4
- открыть входящие порты `22` и `80`

## 2. Установить Docker на VM

```bash
sudo apt update
sudo apt install -y ca-certificates curl git
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker $USER
```

После этого выйдите из SSH и зайдите снова.

## 3. Склонировать проект

```bash
git clone https://github.com/avnamchuk-afk/AI-Arbitr.git
cd AI-Arbitr
```

## 4. Настроить переменные

```bash
cp .env.prod.example .env
cp deploy/config.example.js deploy/config.js
```

В `.env` заменить:

- `YOUR_SERVER_IP` на публичный IP или домен
- `APP_SECRET_KEY`
- `POSTGRES_PASSWORD`
- `DATABASE_URL` с тем же паролем Postgres
- `YANDEX_GPT_API_KEY`
- `YANDEX_GPT_FOLDER_ID`
- SMTP-поля, если нужны настоящие Magic Link письма

В `deploy/config.js` заменить `YOUR_SERVER_IP` на тот же IP или домен.

Для быстрого теста без SMTP можно оставить SMTP пустым: на login-экране появится dev-ссылка входа.

## 5. Запустить

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Проверить:

```bash
docker compose -f docker-compose.prod.yml ps
curl http://YOUR_SERVER_IP/api/health
```

Ссылка для тестирования:

```text
http://YOUR_SERVER_IP
```

## 6. Обновление после новых коммитов

```bash
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

## HTTPS

Для публичного теста по IP достаточно HTTP. Для домена и настоящих secure cookies нужно добавить HTTPS через Let's Encrypt или Yandex Certificate Manager.
