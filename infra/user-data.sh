#!/bin/bash
# EC2 (Amazon Linux 2023) first-boot script: Docker + Compose + start the stack at every boot.
dnf install -y docker git
systemctl enable --now docker
usermod -aG docker ec2-user

mkdir -p /usr/local/lib/docker/cli-plugins
curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

cat > /etc/systemd/system/cryptosentinel.service <<'EOF'
[Unit]
Description=CryptoSentinel stack
After=docker.service network-online.target
Requires=docker.service
[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/home/ec2-user/cryptosentinel
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose stop
[Install]
WantedBy=multi-user.target
EOF
systemctl enable cryptosentinel.service
