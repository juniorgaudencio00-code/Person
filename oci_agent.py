#!/usr/bin/env python3
"""
oci_agent — agente HTTPS minimo para executar comandos no servidor OCI.

Expoe um unico endpoint generico (POST /exec) protegido por token Bearer e TLS.
Sem dependencias externas: usa apenas a biblioteca padrao do Python 3.

Variaveis de ambiente:
  AGENT_TOKEN        token Bearer obrigatorio (>= 16 chars)
  AGENT_PORT         porta de escuta (padrao: 443)
  AGENT_CERT         caminho do certificado TLS (padrao: /etc/oci-agent/cert.pem)
  AGENT_KEY          caminho da chave TLS    (padrao: /etc/oci-agent/key.pem)
  AGENT_CMD_TIMEOUT  timeout por comando, em segundos (padrao: 120)
"""
import hmac
import json
import os
import ssl
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOKEN = os.environ.get("AGENT_TOKEN", "")
PORT = int(os.environ.get("AGENT_PORT", "443"))
CERT = os.environ.get("AGENT_CERT", "/etc/oci-agent/cert.pem")
KEY = os.environ.get("AGENT_KEY", "/etc/oci-agent/key.pem")
CMD_TIMEOUT = int(os.environ.get("AGENT_CMD_TIMEOUT", "120"))


class Handler(BaseHTTPRequestHandler):
    server_version = "oci-agent/1.0"

    def _authorized(self) -> bool:
        header = self.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return False
        return hmac.compare_digest(header[7:], TOKEN)

    def _json(self, code: int, obj: dict) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._json(200, {"status": "ok"})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if not self._authorized():
            self._json(401, {"error": "unauthorized"})
            return
        if self.path != "/exec":
            self._json(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._json(400, {"error": "invalid json"})
            return
        cmd = payload.get("cmd")
        if not cmd or not isinstance(cmd, str):
            self._json(400, {"error": "missing or invalid 'cmd'"})
            return
        try:
            proc = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=CMD_TIMEOUT,
            )
            self._json(200, {
                "exit_code": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            })
        except subprocess.TimeoutExpired:
            self._json(504, {"error": "command timed out"})

    def log_message(self, fmt, *args) -> None:
        # Vai para o journald quando rodando como servico systemd.
        print("%s - %s" % (self.address_string(), fmt % args), flush=True)


def main() -> None:
    if not TOKEN or len(TOKEN) < 16:
        raise SystemExit("AGENT_TOKEN deve estar definido com pelo menos 16 caracteres")
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(CERT, KEY)
    httpd = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
    print(f"oci-agent escutando em 0.0.0.0:{PORT}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
