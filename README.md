# OCI Agent — controle do servidor via HTTPS

Agente mínimo para controlar um servidor **Oracle Cloud (OCI / Ubuntu)** a partir
de um ambiente que só tem saída pela porta **443 (HTTPS)** — como o ambiente do
Claude Code na web, onde a porta 22 (SSH) é bloqueada.

Em vez de SSH, o servidor expõe um endpoint HTTPS genérico que executa comandos
shell. O transporte é a porta 443, que passa pelo proxy do ambiente.

```
 [Claude Code] --curl HTTPS 443--> [proxy] ----> [OCI: oci_agent.py :443] --> shell
```

## Componentes

| Arquivo         | Função                                                      |
|-----------------|-------------------------------------------------------------|
| `oci_agent.py`  | Servidor HTTPS. Endpoint `POST /exec` roda comandos.        |
| `setup.sh`      | Instala como serviço systemd, gera token + certificado TLS. |

## Instalação (no servidor OCI)

```bash
# copie os arquivos para o servidor e rode:
sudo bash setup.sh
```

O script:
1. Gera um **token** aleatório (`/etc/oci-agent/token`).
2. Gera um **certificado TLS** auto-assinado para o IP público.
3. Instala e inicia o serviço `oci-agent` na porta **443**.
4. Imprime o token e a impressão digital do certificado.

Depois, libere a porta **443/TCP** na **Security List da OCI** (regra de Ingress)
e no firewall local (`ufw allow 443/tcp` ou regra `iptables`).

## API

### `GET /health`
Sem autenticação. Retorna `{"status":"ok"}`.

### `POST /exec`
Requer header `Authorization: Bearer <TOKEN>`.

Requisição:
```json
{ "cmd": "docker ps -a" }
```

Resposta:
```json
{ "exit_code": 0, "stdout": "...", "stderr": "..." }
```

Exemplo:
```bash
curl -k https://SEU_IP/exec \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"cmd":"uname -a && uptime"}'
```

> `-k` aceita o certificado auto-assinado. Para fixar (pin) o certificado em vez
> de desabilitar a verificação, use `--cacert` com o `cert.pem` do servidor.

## Segurança

Este endpoint executa **comandos arbitrários** — trate-o como acesso root remoto.

- O token é a barreira principal: mantenha-o secreto, rotacione se vazar
  (`openssl rand -hex 32 > /etc/oci-agent/token && systemctl restart oci-agent`).
- TLS protege o tráfego em trânsito.
- **Restrinja a origem**: na Security List da OCI, ao invés de `0.0.0.0/0`,
  limite o Ingress 443 ao IP de origem das requisições (visível em
  `journalctl -u oci-agent`).
- Para reduzir o privilégio, troque `User=root` por um usuário dedicado na
  unidade systemd e conceda apenas o `sudo` necessário.

## Operação

```bash
systemctl status oci-agent      # estado
journalctl -u oci-agent -f      # logs ao vivo (inclui IP de origem)
systemctl restart oci-agent     # reiniciar
```
