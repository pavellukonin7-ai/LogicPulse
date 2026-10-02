> Каталог и форма уже установлены? Для Telegram используйте **TELEGRAM.md**, повторять создание услуг не нужно.

# Обновление LogicPulse: пошагово

`PS C:\Users\pavel>` — Windows. `root@logicpulse:…#` — VPS Ubuntu.

## 1. Передача архива — Windows PowerShell

Сохраните архив как `LogicPulse_Server_v1.1.0.zip` в папку «Загрузки».

```powershell
scp -i "$env:USERPROFILE\.ssh\logicpulse_root_ed25519" "$env:USERPROFILE\Downloads\LogicPulse_Server_v1.1.0.zip" root@185.125.218.116:/root/
```

## 2. Обновление — терминал VPS в Cursor

```bash
cd /root
python3 -m zipfile -e LogicPulse_Server_v1.1.0.zip .
bash /root/LogicPulse_Server_v1.1.0/scripts/upgrade-v1.1.sh /opt/logicpulse
```

Скрипт делает дамп БД и копию старых файлов. В контейнере Node выполняет npm ci и
npm run build, собирает backend, ждёт готовности PostgreSQL/backend, устанавливает
frontend и проверяет/reload Nginx. Существующие .env, сертификаты, htpasswd, SSH и
тома не заменяются. В .env добавляется ADMIN_API_KEY, если его нет.
При ошибке сохраните вывод; не запускайте bootstrap и не удаляйте тома.

## 3. Проверка backend и БД — VPS

```bash
cd /opt/logicpulse
docker compose ps
docker compose exec -T backend python -c 'import socket; print("db ->", socket.gethostbyname("db"))'
curl --fail --show-error https://logicpulse.ru/api/health
```

Ожидаем backend/postgres healthy и `{"status":"ok","database":"connected"}`.
Сервис БД — postgres; db — его сетевой alias. Это сохраняет прежний том с данными.

## 4. Пять услуг вручную через Swagger

1. В Cursor откройте `/opt/logicpulse/.env`, скопируйте значение ADMIN_API_KEY.
2. В браузере откройте `https://logicpulse.ru/docs`.
3. **Authorize** → вставьте ключ в **Value** → **Authorize** → **Close**.
4. **POST /api/services** → **Try it out**.
5. Откройте в Cursor `/opt/logicpulse/docs/services/01-web-development.json`.
6. Вставьте весь JSON в Request body Swagger → **Execute**. Ожидаем **201**.
7. Повторите с файлами 02, 03, 04, 05 из той же папки.
8. **GET /api/services** → **Try it out** → **Execute**: должно быть 5 объектов.

409 означает, что slug уже существует. Проверьте GET, не создавайте дубликаты.
В GET /api/admin/services с ключом видны диапазоны полностью. Публичный GET
показывает price_min/price_max=null, пока prices_approved=false.
Перед согласованием цен сопоставьте объём работ, сроки и себестоимость.
AI-подписки, хостинг, лицензии и другие сервисы рассчитываются отдельно.

| JSON | Услуга | Внутренний диапазон |
|---|---|---|
| 01-web-development.json | Сайты и веб-сервисы | 80 000–350 000 ₽ |
| 02-ai-assistants.json | AI-ассистенты и чат-боты | 100 000–400 000 ₽ |
| 03-business-automation.json | Автоматизация процессов | 120 000–500 000 ₽ |
| 04-api-integration.json | Интеграция систем и API | 60 000–250 000 ₽ |
| 05-internal-platforms.json | Внутренние бизнес-системы | 300 000–1 200 000 ₽ |

## 5. Проверка заявки в браузере

1. Откройте `https://logicpulse.ru`, нажмите Ctrl+F5 → «Обсудить проект».
2. Выберите услугу; имя `Тест LogicPulse`; email `test@example.com`; компания `Тестирование`.
3. Задача: `Проверка формы заявки после обновления LogicPulse. Реальный проект не требуется.`
4. Отметьте согласие, нажмите **Отправить заявку**.
5. Ожидаем **«Заявка отправлена!»** и номер обращения.
6. В Swagger выполните GET /api/admin/requests с ключом; найдите сохранённую запись,
   проверьте услугу, контакт и текст. Тестовая запись остаётся в БД.

Сообщение подтверждает сохранение в БД; отправка писем не подключена. Telegram настраивается отдельно (TELEGRAM.md).
Повтор после сетевого тайм-аута не создаёт дубликат, если данные не менялись.

## 6. CSS, API и журналы

В Chrome F12 → Network → обновить страницу. /assets/*.css и /assets/*.js должны
иметь 200 или 304, корректные типы CSS/JS; /api/services — 200; POST /api/requests — 201.

```bash
cd /opt/logicpulse
bash scripts/check.sh
docker compose logs --tail=100 backend nginx
```

Наблюдение: `docker compose logs -f --tail=50 backend nginx`; Ctrl+C завершает просмотр,
контейнеры продолжают работать. Имя контейнера — logicpulse-backend-1, поэтому
`docker logs backend` в этом стеке не подходит.
502: backend; 503: БД; 422: поля формы; 429: подождите минуту.
Запросы идут через Nginx на том же домене, отдельный CORS не нужен.

## 7. Обслуживание

Ранее настроенные таймеры backup/renew сохраняются. Бэкап БД включает услуги и заявки.
После обновления выполните `bash scripts/backup.sh` и сохраните копию вне VPS.
Автоматическая внешняя копия и проверка восстановления остаются отдельными задачами.
