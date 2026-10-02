#!/usr/bin/env bash
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo 'Запустите от root'; exit 1; }
source /etc/os-release
case "${ID}:${VERSION_ID}" in
  ubuntu:22.04|ubuntu:24.04|ubuntu:26.04) ;;
  *) echo "ОС $ID $VERSION_ID: этот комплект рассчитан на Ubuntu 22.04/24.04/26.04 LTS. Установка остановлена до любых изменений; рекомендуемая ОС — Ubuntu 24.04 LTS."; exit 1 ;;
esac
if command -v docker >/dev/null; then
  docker version
  docker compose version || { echo 'Docker уже установлен, но Compose отсутствует. Не меняю существующую установку.'; exit 1; }
  echo 'Существующая установка Docker сохранена.'
else
  for pkg in docker.io docker-compose docker-compose-v2 docker-doc docker-buildx podman-docker containerd runc; do
    if dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -qx 'install ok installed'; then
      echo "Найден конфликтующий пакет $pkg. Сначала оцените существующие сервисы; автоматическое удаление отменено."; exit 1
    fi
  done
  apt-get update
  apt-get install -y ca-certificates curl
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL "https://download.docker.com/linux/$ID/gpg" -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  cat > /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/$ID
Suites: ${UBUNTU_CODENAME:-$VERSION_CODENAME}
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
fi
apt-get update
apt-get install -y apache2-utils python3 curl ca-certificates dnsutils unzip
# Installing apache2-utils does not install/start the Apache web server.
docker version
docker compose version
