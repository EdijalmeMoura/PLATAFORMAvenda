# 🚀 Deploy público com HTTPS — ProdutoVenda IA

Para os **webhooks da Meta (WhatsApp) e do Mercado Pago funcionarem**, o sistema precisa estar num endereço público **HTTPS**. Este guia cobre o caminho mais simples (Docker + Caddy com HTTPS automático) e o alternativo (systemd + Nginx).

## Pré-requisitos
- Uma VPS/servidor Linux (1 GB de RAM já basta) com Docker instalado **ou** Python 3.10+
- Um domínio (ex.: `app.suaempresa.com.br`) apontando (registro **A**) para o IP do servidor
- Portas **80** e **443** liberadas no firewall/provedor

---

## Opção A — Docker + Caddy (recomendada, HTTPS automático)

1. No servidor, clone e configure:
   ```bash
   git clone -b arena/34496ed2-plataformavenda https://github.com/EdijalmeMoura/PLATAFORMAvenda.git
   cd PLATAFORMAvenda
   cp .env.example .env
   # edite .env: defina PV_MASTER_KEY forte
   python3 -c "import secrets; print(secrets.token_hex(32))"   # gere a chave
   ```
2. Edite `deploy/Caddyfile` e troque `app.suaempresa.com.br` pelo seu domínio.
3. Suba tudo:
   ```bash
   docker compose up -d --build
   docker compose -f docker-compose.yml -f deploy/docker-compose.caddy.yml up -d   # app + Caddy (HTTPS)
   curl https://app.suaempresa.com.br/api/health
   # {"status":"ok", ...}
   ```
   O Caddy emite e renova o certificado Let's Encrypt sozinho. 🎉

## Opção B — Python direto + systemd + Nginx

1. Instale o app:
   ```bash
   sudo useradd -r -s /usr/sbin/nologin produtovenda || true
   sudo mkdir -p /opt/produtovenda /var/lib/produtovenda
   # copie server.py, integrations.py e static/ para /opt/produtovenda
   sudo cp deploy/produtovenda.service /etc/systemd/system/
   sudo systemctl daemon-reload && sudo systemctl enable --now produtovenda
   curl http://127.0.0.1:8000/api/health
   ```
2. Publique com Nginx + HTTPS:
   ```bash
   sudo cp deploy/nginx.conf /etc/nginx/sites-available/produtovenda
   sudo ln -s /etc/nginx/sites-available/produtovenda /etc/nginx/sites-enabled/
   sudo nginx -t && sudo systemctl reload nginx
   sudo certbot --nginx -d app.suaempresa.com.br   # HTTPS gratuito
   ```

---

## Depois do deploy (checklist)

- [ ] `https://SEU-DOMINIO/api/health` retorna `{"status":"ok"}`
- [ ] Abra `https://SEU-DOMINIO`, entre e troque a senha da conta demo **ou crie sua conta**
- [ ] **Admin → Integrações**: configure WhatsApp Cloud API, Mercado Pago e SMTP com credenciais de **teste**, clique em *Testar conexão*
- [ ] Cadastre nos provedores os webhooks exibidos no painel:
  - Meta: `https://SEU-DOMINIO/api/webhooks/whatsapp` (campo `messages`, mesmo Verify Token)
  - Mercado Pago: `https://SEU-DOMINIO/api/webhooks/mercadopago` (tópico Pagamentos)
- [ ] Faça uma venda de teste na loja (Pix de valor baixo com conta de teste do MP) e confirme que o pedido vira **pago** sozinho
- [ ] Troque para credenciais de **produção** e rotacione qualquer token exposto

## Backup

O estado fica em um único arquivo SQLite (volume `produtovenda-data` no Docker, ou `/var/lib/produtovenda` no systemd) + pasta `uploads/` (fotos de produtos). Backup simples (cron diário):

```bash
# Docker
docker run --rm -v produtovenda_produtovenda-data:/data -v "$PWD":/backup alpine \
  sh -c "cp /data/plataformavenda.db /backup/backup-$(date +%F).db"
```

Além disso, cada empresa pode baixar um **JSON dos próprios dados** em *Admin → Exportar dados* a qualquer momento.

## Atualizando

```bash
git pull
docker compose up -d --build     # (ou: systemctl restart produtovenda)
python3 -m unittest discover -s tests -v   # rode os testes antes em homologação
```

As migrações de banco são automáticas na inicialização (novas colunas/tabelas são criadas sem apagar dados).
