# Telegram через Windows SOCKS5 — обновление 1.1.2

Проверенный владельцем маршрут: VPS → SSH-туннель 127.0.0.1:18080 →
Windows SOCKS5 127.0.0.1:10808 → Telegram (HTTP 302).

Теперь этот маршрут поддерживают настройка бота и контейнер telegram-worker.
Это обновление того же `/opt/logicpulse`. Новая БД/сайт не создаются.

## 1. Оставьте Windows-прокси и SSH-туннель включёнными

В отдельном Windows PowerShell уже должна работать команда:

```powershell
ssh -i "$env:USERPROFILE\.ssh\logicpulse_root_ed25519" -N -T -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -R 127.0.0.1:18080:127.0.0.1:10808 root@185.125.218.116
```

Если это окно уже открыто и проверка curl прошла, второй туннель не запускайте.
Нужен работающий прокси Windows. Закрытие окна/сон/отключение ПК прерывают маршрут.

## 2. В ДРУГОМ окне Windows PowerShell загрузите архив

```powershell
scp -i "$env:USERPROFILE\.ssh\logicpulse_root_ed25519" "$env:USERPROFILE\Downloads\LogicPulse_Server_v1.1.2.zip" root@185.125.218.116:/root/
```

## 3. Терминал VPS в Cursor — установить и привязать

```bash
cd /root
python3 -m zipfile -e LogicPulse_Server_v1.1.2.zip .
bash /root/LogicPulse_Server_v1.1.2/scripts/upgrade-windows-proxy.sh /opt/logicpulse
```

Сначала создаётся дамп БД и копия файлов. Затем обновляются backend/worker,
добавляется поддержка SOCKS5 и проверяется Telegram из контейнера (ожидаем 302).
После этого скрипт попросит токен @LogicPulseLeadsBot. Ввод скрыт.
Отправьте выведенную `/connect_...` команду в личный чат боту и нажмите Enter в терминале.
Дождитесь «Telegram включён». Токен в чат/команды/скриншоты не вставляйте.

При ошибке установка останавливается. Пришлите вывод без .env и токена.
Если обновление уже выполнено, продолжить настройку можно без повторной сборки:

```bash
cd /opt/logicpulse
python3 scripts/enable-windows-proxy.py
python3 scripts/setup-telegram.py
```

## 4. Новая заявка

Отправьте новую тестовую заявку через https://logicpulse.ru.
Ожидаем сообщение «LogicPulse | Новая заявка» у @LogicPulseLeadsBot.
Старая заявка автоматически не пересылается.

```bash
cd /opt/logicpulse
docker compose ps backend telegram-worker
docker compose logs --tail=30 telegram-worker
```

В Swagger GET /api/admin/telegram с ключом администратора показывает pending/sent/failed.
Не показывайте Curl или ADMIN_API_KEY на скриншотах.

## Как контейнер использует туннель

- Установщик создаёт на VPS учётную запись logicpulse-notify (UID 10001, без домашнего каталога и входа в shell). При конфликте UID/имени он останавливается.
- systemd слушает Unix-сокет `/run/logicpulse-telegram/proxy.sock`, доступный UID 10001
  (пользователь приложения) с режимом 0600.
- systemd-socket-proxyd передаёт соединение на фиксированный `127.0.0.1:18080` VPS.
- Каталог сокета смонтирован только в worker, read-only. Другим контейнерам он не передаётся.
- В `.env` устанавливается `BOT_PROXY=socks5h://localhost/run/logicpulse-telegram/proxy.sock`.
- На VPS setup-telegram.py читает это значение. Docker передаёт BOT_PROXY только worker.
- curl использует SOCKS5 с удалённым DNS. Проверка TLS остаётся включённой.
- Токен/прокси/тело заявки передаются curl через stdin, не аргументы процесса.
- Новые публичные TCP-порты и изменения sshd/GatewayPorts/firewall не требуются.

Если BOT_PROXY пустой, используется прежний прямой HTTPS-запрос.
Для внешнего постоянного SOCKS5/HTTP(S) прокси можно задать его URL в BOT_PROXY
и пересоздать только worker. Токен не меняется; адрес 127.0.0.1 Windows для этого
не подходит. Не публикуйте URL прокси с логином/паролем.

## После отключения или перезагрузки Windows

Включите Windows-прокси и заново запустите SSH-команду из пункта 1.
Токен и привязку чата повторять не нужно. Pending-уведомления отправятся при
следующей попытке; после длительного сбоя интервал может вырасти до часа.
Сайт продолжает сохранять заявки независимо от туннеля. Если необходим немедленный
повтор после долгого сбоя, согласуйте отдельное действие; перезапуск не сбрасывает
сохранённое время следующей попытки.

Служба socket включена на сервере автоматически. После перезагрузки VPS также
нужно восстановить SSH-туннель с Windows. Для круглосуточной работы потребуется
независимый от компьютера доступ VPS к Telegram.

## Диагностика без секретов

```bash
systemctl status logicpulse-telegram-proxy.socket logicpulse-telegram-proxy.service --no-pager
curl --socks5-hostname 127.0.0.1:18080 -I --connect-timeout 10 --max-time 20 https://api.telegram.org/
docker compose exec -T telegram-worker curl -q --proxy socks5h://localhost/run/logicpulse-telegram/proxy.sock --noproxy '' -I --connect-timeout 10 --max-time 20 https://api.telegram.org/
```

`proxy_network` — туннель/прокси недоступен; `proxy_tls` — проверка сертификата;
401 — Telegram отверг токен; 403 — бот заблокирован. Не отключайте проверку TLS.
Очередь и правила повторов описаны в TELEGRAM.md.

Для отключения всего режима: сначала TELEGRAM_ENABLED=false и пересоздание
backend/worker, затем `systemctl disable --now logicpulse-telegram-proxy.socket`
и `systemctl stop logicpulse-telegram-proxy.service`. Закройте окно SSH Ctrl+C.
Рабочие данные и токен останутся в .env; резервные копии содержат секреты.

Документация curl: https://curl.se/docs/manpage.html#--proxy
(SOCKS через Unix socket, конфигурация через stdin). Службы проверяются
`systemd-analyze verify`; реальную доставку проверяет владелец на VPS.

## Исправление 217/USER для ранее скачанного архива

Причина: UID контейнера отсутствует в NSS сервера. При подтверждённом
`Failed to resolve user 10001: Unknown user` выполните от root:

```bash
useradd --uid 10001 --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin logicpulse-notify
id logicpulse-notify
cd /opt/logicpulse
python3 scripts/enable-windows-proxy.py
```

После «Прокси подключён»: `python3 scripts/setup-telegram.py`.
При ошибке useradd остановитесь и проверьте конфликт; существующих пользователей
не переименовывайте и UID не меняйте. Новая редакция установщика создаёт эту
учётную запись автоматически; повторная сборка для текущего сервера не нужна.
