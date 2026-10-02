# Telegram без Windows: обновление 1.1.3

Для действующего `/opt/logicpulse` с Telegram v1.1.2, сохранённым токеном и
приватным сокетом `/run/logicpulse-telegram/proxy.sock`.
Backend и worker остаются на образе **1.1.2**: обновление 1.1.3 меняет только
способ выхода в интернет. БД, `.env`, сайт, Compose, Nginx, сертификаты и SSH
не перезаписываются. Повторно привязывать чат не нужно.

## Подготовить приватный JSON на Windows

В Happ скопируйте полный JSON нужного профиля, как при предыдущем экспорте.
Нужен профиль VLESS / TCP / TLS с одним outbound `proxy` и одним пользователем.
Здесь нет поддержки зашифрованных подписок, REALITY или автоматического обновления
подписки. Параметры адреса, SNI, ALPN, fingerprint и flow сохраняются из экспорта.
Для другого протокола установщик остановится до переключения.

Сразу после копирования JSON выполните в **Windows PowerShell**:

```powershell
$proxyText = Get-Clipboard -Raw
try { $proxyProfile = $proxyText | ConvertFrom-Json -ErrorAction Stop } catch { throw 'В буфере обмена нет корректного JSON. Скопируйте его из Happ ещё раз.' }
if (-not $proxyProfile.outbounds) { throw 'Это не полный JSON конфигурации Happ.' }
$proxyDir = Join-Path $env:LOCALAPPDATA 'LogicPulse'
New-Item -ItemType Directory -Force -Path $proxyDir | Out-Null
[System.IO.File]::WriteAllText((Join-Path $proxyDir 'happ-export.json'), $proxyText, [System.Text.UTF8Encoding]::new($false))
Remove-Variable proxyText, proxyProfile
Set-Clipboard -Value ''
Write-Host 'JSON сохранён локально. Содержимое не выводится.'
```

Файл содержит доступ к VPN-профилю. Не отправляйте его в чат, GitHub или общую папку.
Это не Telegram-токен. Если профиль перевыпущен провайдером, нужен новый экспорт.

## Передать архив и JSON на VPS

Сохраните архив `LogicPulse_Server_v1.1.3.zip` в Windows Downloads. В отдельном
PowerShell (не в занятом окне туннеля) выполните:

```powershell
scp -i "$env:USERPROFILE\.ssh\logicpulse_root_ed25519" "$env:USERPROFILE\Downloads\LogicPulse_Server_v1.1.3.zip" root@185.125.218.116:/root/
scp -i "$env:USERPROFILE\.ssh\logicpulse_root_ed25519" "$env:LOCALAPPDATA\LogicPulse\happ-export.json" root@185.125.218.116:/root/logicpulse-happ.json
```

## Обновить существующий проект

В **терминале VPS**, где приглашение `root@logicpulse`, выполните:

```bash
chmod 600 /root/logicpulse-happ.json
python3 -m zipfile -e /root/LogicPulse_Server_v1.1.3.zip /root/
bash /root/LogicPulse_Server_v1.1.3/scripts/upgrade-server-proxy.sh
```

Оставьте работающими Happ и Windows SSH-туннель до сообщения об успешном
переключении. Они также используются как резервный путь для скачивания Xray.

Установщик:

1. Проверяет исходный профиль, права файла и действующую настройку worker.
2. Загружает закреплённый официальный Xray `v26.3.27` с GitHub XTLS/Xray-core,
   сверяет SHA256 с файлом `.dgst`, проверяет конфигурацию командой `run -test`.
   Эта версия выбрана явно; установщик не обновляет её автоматически.
3. Запускает `logicpulse-xray.service` под DynamicUser. Приватный конфиг передаётся
   через systemd LoadCredential. На VPS слушается только `127.0.0.1:18081`.
4. Через этот SOCKS проверяет HTTPS api.telegram.org с проверкой TLS.
5. На время переключения приостанавливает только telegram-worker; сайт продолжает
   принимать заявки. Меняет цель существующего Unix-реле через отдельный drop-in.
6. Возобновляет worker, проверяет HTTPS из контейнера и `getMe` с сохранённым токеном.
   При ошибке пытается вернуть прежний маршрут и явно сообщает о неудаче отката.
7. Включает автозапуск Xray и существующего приватного сокета.

Правило Xray разрешает только **api.telegram.org:443** через провайдера;
другие назначения блокируются. Системный маршрут, SSH и веб-трафик не меняются.
Внешний провайдер всё равно должен быть доступен с VPS: работоспособность на Windows
сама по себе этого не доказывает. Если загрузка/соединение не проходит, пришлите
только вывод установщика, без JSON и `.env`.

## Проверить независимость от компьютера

Только после сообщения «Готово: Telegram использует серверный Xray»:

1. В Windows-окне с командой `ssh -N -T ... -R ...` нажмите Ctrl+C.
2. Оставьте Happ включённым, если он нужен вашему Telegram на Windows.
   Это уже не канал доставки с VPS, но Telegram-клиенту по-прежнему нужен интернет.
3. На VPS выполните:

```bash
python3 /opt/logicpulse/scripts/install-server-proxy.py --check
```

4. Отправьте новую тестовую заявку на https://logicpulse.ru/.
5. Убедитесь, что сообщение появилось в @LogicPulseLeadsBot.

Новые уведомления обычно обрабатываются за несколько секунд. Уже ожидающие
повтора после сетевой ошибки могут быть отложены до часа (либо на срок retry_after).
Старая очередь не очищается. Повторный вызов setup-telegram.py не нужен.

## Проверка после перезагрузки

Перезагружать VPS прямо во время установки не требуется. Когда потребуется
плановая перезагрузка, проверьте:

```bash
systemctl is-active logicpulse-xray.service logicpulse-telegram-proxy.socket
systemctl is-enabled logicpulse-xray.service logicpulse-telegram-proxy.socket
python3 /opt/logicpulse/scripts/install-server-proxy.py --check
```

`logicpulse-telegram-proxy.service` может запускаться по обращению к сокету.
Работу при реальной перезагрузке должен подтвердить тест на VPS.

## Откат

Сначала снова включите Happ и Windows SSH-туннель:

```powershell
ssh -i "$env:USERPROFILE\.ssh\logicpulse_root_ed25519" -N -T -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -R 127.0.0.1:18080:127.0.0.1:10808 root@185.125.218.116
```

Затем на VPS:

```bash
python3 /opt/logicpulse/scripts/install-server-proxy.py --rollback
```

Откат сначала проверит старый канал, затем вернёт реле на порт 18080 и отключит
автозапуск Xray. Файлы Xray и приватная конфигурация останутся для повторного
подключения. Не запускайте enable-windows-proxy.py поверх серверного drop-in.

## Обслуживание

Это статический экспорт профиля. Продление VPN-подписки, изменение адреса,
идентификатора или ограничений у провайдера может потребовать нового экспорта.
Нет обещания бессрочной доступности провайдера или автоматического обновления
его профилей. При смене настроек верните Windows-канал через --rollback,
передайте новый приватный JSON и повторите обновление.

Секретный рабочий файл: `/etc/logicpulse-xray/config.json`, root:600, каталог 700.
Архив проекта не содержит экспорта, UUID, токена или подписки пользователя.
Резервные копии настроек: `/root/logicpulse-proxy-before-*`, каталог 700.
Диагностика: `systemctl status logicpulse-xray.service --no-pager` и
`journalctl -u logicpulse-xray.service -n 30 --no-pager`. В журнале могут быть
адреса провайдера; просмотрите вывод перед отправкой.

Источники: https://github.com/XTLS/Xray-core/releases/tag/v26.3.27,
https://github.com/XTLS/Xray-install,
https://xtls.github.io/en/config/inbounds/socks.html,
https://xtls.github.io/en/config/routing.html.
