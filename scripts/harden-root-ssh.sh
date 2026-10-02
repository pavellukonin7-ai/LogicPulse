#!/usr/bin/env bash
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo 'Запустите от root'; exit 1; }
[[ "${1:-}" == --key-login-verified ]] || { echo 'Сначала проверьте ВТОРОЕ SSH-подключение с отключённым паролем, затем передайте --key-login-verified. Сохраните текущую сессию.'; exit 1; }
[[ -s /root/.ssh/authorized_keys ]] || { echo 'authorized_keys пуст'; exit 1; }
command -v sshd >/dev/null
sshd -t
[[ ! -f /etc/ssh/sshd_config.d/00-logicpulse-root.conf ]] || { echo 'Конфигурация уже существует. Проверьте её вручную.'; exit 1; }
grep -Eq '^[[:space:]]*Include[[:space:]]+/etc/ssh/sshd_config.d/\*\.conf' /etc/ssh/sshd_config || { echo 'sshd_config не включает conf.d. Нужна ручная настройка.'; exit 1; }
mkdir -p /etc/ssh/sshd_config.d
file=/etc/ssh/sshd_config.d/00-logicpulse-root.conf
trap 'rm -f "$file"; echo "Проверка не пройдена, новый файл удалён." >&2' ERR
cat > "$file" <<'EOF'
PubkeyAuthentication yes
Match User root
    PermitRootLogin prohibit-password
    PasswordAuthentication no
    KbdInteractiveAuthentication no
    AuthenticationMethods publickey
Match all
EOF
chmod 600 "$file"
sshd -t
client_ip="${SSH_CONNECTION%% *}"
[[ -n "$client_ip" ]] || client_ip=127.0.0.1
effective="$(sshd -T -C "user=root,host=logicpulse.ru,addr=$client_ip")"
grep -qx 'passwordauthentication no' <<< "$effective"
grep -qx 'kbdinteractiveauthentication no' <<< "$effective"
grep -qx 'authenticationmethods publickey' <<< "$effective"
grep -qx 'pubkeyauthentication yes' <<< "$effective"
grep -Eq '^permitrootlogin (without-password|prohibit-password)$' <<< "$effective"
if systemctl is-active --quiet ssh; then systemctl reload ssh; else systemctl reload sshd; fi
trap - ERR
echo 'Root: вход только по ключу. Не закрывайте текущую сессию до ещё одной успешной проверки.'
