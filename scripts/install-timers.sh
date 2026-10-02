#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
require_root
[[ "$PROJECT_DIR" == /opt/logicpulse ]] || { echo 'Для таймеров разместите проект в /opt/logicpulse'; exit 1; }
for task in renew backup; do
  if [[ "$task" == renew ]]; then script=renew-cert.sh; schedule='*-*-* 03,15:20:00'; else script=backup.sh; schedule='*-*-* 02:30:00'; fi
  cat > "/etc/systemd/system/logicpulse-$task.service" <<EOF
[Unit]
Description=LogicPulse $task
Requires=docker.service
After=docker.service network-online.target
[Service]
Type=oneshot
WorkingDirectory=/opt/logicpulse
ExecStart=/usr/bin/bash /opt/logicpulse/scripts/$script
UMask=0077
EOF
  cat > "/etc/systemd/system/logicpulse-$task.timer" <<EOF
[Unit]
Description=LogicPulse $task schedule
[Timer]
OnCalendar=$schedule
RandomizedDelaySec=900
Persistent=true
[Install]
WantedBy=timers.target
EOF
done
systemctl daemon-reload
systemctl enable --now logicpulse-renew.timer logicpulse-backup.timer
systemctl list-timers 'logicpulse-*'
