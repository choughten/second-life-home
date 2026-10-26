#!/bin/sh
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
python_bin=$(command -v python3)
test -f "$project_dir/config.json" || { echo 'Run python3 setup.py first.'; exit 1; }
mkdir -p "$HOME/.config/systemd/user"
cat > "$HOME/.config/systemd/user/second-life-home.service" <<EOF
[Unit]
Description=Second Life Home dashboard
After=network-online.target
[Service]
WorkingDirectory=$project_dir
ExecStart=$python_bin "$project_dir/server.py"
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload
systemctl --user enable --now second-life-home.service
echo 'Installed. For startup without an interactive login: sudo loginctl enable-linger "$USER"'
