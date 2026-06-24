#!/usr/bin/env bash
#
# setup.sh — instala o oci_agent como servico systemd no servidor OCI (Ubuntu).
#
# Uso (no servidor OCI, como usuario com sudo):
#   sudo bash setup.sh
#
# Gera token + certificado TLS auto-assinado, instala o servico e o inicia
# na porta 443. Ao final, imprime o token (guarde-o) e a impressao digital
# do certificado.
#
set -euo pipefail

DIR=/etc/oci-agent
APP=/opt/oci-agent
SERVICE=/etc/systemd/system/oci-agent.service
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ "$(id -u)" -ne 0 ]; then
  echo "Rode como root: sudo bash setup.sh" >&2
  exit 1
fi

echo "==> Preparando diretorios"
mkdir -p "$DIR" "$APP"
cp "$SCRIPT_DIR/oci_agent.py" "$APP/oci_agent.py"

echo "==> Gerando token (se ainda nao existir)"
if [ ! -f "$DIR/token" ]; then
  openssl rand -hex 32 > "$DIR/token"
  chmod 600 "$DIR/token"
fi
TOKEN="$(cat "$DIR/token")"

echo "==> Detectando IP publico"
PUBLIC_IP="$(curl -s --max-time 10 ifconfig.me || true)"
PUBLIC_IP="${PUBLIC_IP:-$(hostname -I | awk '{print $1}')}"

echo "==> Gerando certificado TLS auto-assinado (CN/SAN = $PUBLIC_IP)"
if [ ! -f "$DIR/cert.pem" ]; then
  openssl req -x509 -newkey rsa:2048 -nodes \
    -keyout "$DIR/key.pem" -out "$DIR/cert.pem" -days 825 \
    -subj "/CN=${PUBLIC_IP}" \
    -addext "subjectAltName=IP:${PUBLIC_IP}"
  chmod 600 "$DIR/key.pem"
fi
FINGERPRINT="$(openssl x509 -in "$DIR/cert.pem" -noout -fingerprint -sha256 | cut -d= -f2)"

echo "==> Escrevendo unidade systemd"
cat > "$SERVICE" <<EOF
[Unit]
Description=OCI command agent (HTTP)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
Environment=AGENT_TOKEN=${TOKEN}
Environment=AGENT_PORT=80
Environment=AGENT_TLS=0
Environment=AGENT_CMD_TIMEOUT=120
ExecStart=/usr/bin/python3 ${APP}/oci_agent.py
Restart=on-failure
RestartSec=3
User=root
AmbientCapabilities=CAP_NET_BIND_SERVICE

[Install]
WantedBy=multi-user.target
EOF

echo "==> Habilitando e iniciando o servico"
systemctl daemon-reload
systemctl enable --now oci-agent.service
sleep 1
systemctl --no-pager --full status oci-agent.service | head -n 12 || true

cat <<EOF

============================================================
 oci-agent instalado e rodando na porta 443
============================================================
 TOKEN (guarde com seguranca):
   ${TOKEN}

 Impressao digital do certificado (SHA-256):
   ${FINGERPRINT}

 Proximos passos:
  1) Libere a porta 443/TCP na Security List da OCI (Ingress).
  2) No firewall local, se ativo:
       sudo iptables -I INPUT -p tcp --dport 443 -j ACCEPT
     (ou: sudo ufw allow 443/tcp)
  3) Teste local:
       curl -k https://localhost/health
  4) Me passe o TOKEN para eu controlar o servidor a partir daqui.
============================================================
EOF
