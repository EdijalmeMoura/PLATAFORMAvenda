#!/usr/bin/env python3
"""
Integracoes reais do ProdutoVenda IA.
- WhatsApp Cloud API (Meta Graph API): envio de texto/template, teste, webhook (recebimento)
- Mercado Pago: Pix (QR Code/copia e cola) e Checkout Pro (cartao/link), consulta e webhook
- SMTP: envio real de e-mail
- Google Places API (New): prospecção com fonte oficial autorizada
- Meta Social: teste de token de Pagina/Instagram

Sem dependencias externas (urllib/smtplib da stdlib). As credenciais ficam salvas
por tenant (company_id) no banco do servidor e NUNCA sao devolvidas inteiras
pela API (sempre mascaradas). Nada e simulado: sem credencial valida, a chamada
real nao acontece e o erro e explicado.
"""
import json, os, re, base64, hashlib, hmac, smtplib, ssl, struct, urllib.request, urllib.error, urllib.parse
from email.message import EmailMessage

GRAPH = "https://graph.facebook.com"
MP_API = "https://api.mercadopago.com"
PLACES_API = "https://places.googleapis.com/v1/places:searchText"


class IntegrationError(Exception):
    def __init__(self, message, status=502, detail=None):
        super().__init__(message)
        self.status = status
        self.detail = detail


# ------------------------------------------------------------------
# Criptografia das credenciais em repouso (ChaCha20 + HMAC-SHA256,
# encrypt-then-MAC). A chave-mestra fica FORA do banco: variavel de
# ambiente PV_MASTER_KEY ou arquivo .pv_master_key (0600) ao lado do
# banco. Valores antigos em texto puro continuam legiveis (migracao
# transparente: sao regravados criptografados no proximo save).
# ------------------------------------------------------------------
_KEY_CACHE = None


def _master_key():
    global _KEY_CACHE
    if _KEY_CACHE:
        return _KEY_CACHE
    env = os.environ.get("PV_MASTER_KEY", "")
    if env:
        _KEY_CACHE = hashlib.sha256(env.encode()).digest()
        return _KEY_CACHE
    key_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".pv_master_key")
    try:
        if os.path.exists(key_file):
            raw = open(key_file).read().strip()
        else:
            import secrets as _secrets
            raw = _secrets.token_hex(32)
            fd = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            os.write(fd, raw.encode())
            os.close(fd)
        _KEY_CACHE = hashlib.sha256(raw.encode()).digest()
    except Exception:
        _KEY_CACHE = hashlib.sha256(b"pv-fallback-key-change-me").digest()
    return _KEY_CACHE


def _rotl(v, c):
    return ((v << c) & 0xFFFFFFFF) | (v >> (32 - c))


def _quarter(x, a, b, c, d):
    x[a] = (x[a] + x[b]) & 0xFFFFFFFF; x[d] = _rotl(x[d] ^ x[a], 16)
    x[c] = (x[c] + x[d]) & 0xFFFFFFFF; x[b] = _rotl(x[b] ^ x[c], 12)
    x[a] = (x[a] + x[b]) & 0xFFFFFFFF; x[d] = _rotl(x[d] ^ x[a], 8)
    x[c] = (x[c] + x[d]) & 0xFFFFFFFF; x[b] = _rotl(x[b] ^ x[c], 7)


def _chacha20(key, nonce, data, counter=1):
    consts = [0x61707865, 0x3320646E, 0x79622D32, 0x6B206574]
    kw = list(struct.unpack("<8I", key))
    nw = list(struct.unpack("<3I", nonce))
    out = bytearray()
    block_counter = counter
    for offset in range(0, len(data), 64):
        state = consts + kw + [block_counter] + nw
        x = list(state)
        for _ in range(10):
            _quarter(x, 0, 4, 8, 12); _quarter(x, 1, 5, 9, 13); _quarter(x, 2, 6, 10, 14); _quarter(x, 3, 7, 11, 15)
            _quarter(x, 0, 5, 10, 15); _quarter(x, 1, 6, 11, 12); _quarter(x, 2, 7, 8, 13); _quarter(x, 3, 4, 9, 14)
        block = struct.pack("<16I", *[((x[i] + state[i]) & 0xFFFFFFFF) for i in range(16)])
        chunk = data[offset:offset + 64]
        out.extend(bytes(a ^ b for a, b in zip(chunk, block)))
        block_counter += 1
    return bytes(out)


def encrypt_secret(plaintext):
    if plaintext is None or str(plaintext) == "":
        return plaintext
    key = _master_key()
    nonce = os.urandom(12)
    ct = _chacha20(key, nonce, str(plaintext).encode())
    tag = hmac.new(key, nonce + ct, hashlib.sha256).digest()[:16]
    return "enc:v1:" + base64.urlsafe_b64encode(nonce + tag + ct).decode()


def decrypt_secret(value):
    if not value or not str(value).startswith("enc:v1:"):
        return value  # legado em texto puro
    try:
        raw = base64.urlsafe_b64decode(str(value)[7:].encode())
        nonce, tag, ct = raw[:12], raw[12:28], raw[28:]
        key = _master_key()
        expected = hmac.new(key, nonce + ct, hashlib.sha256).digest()[:16]
        if not hmac.compare_digest(tag, expected):
            return ""
        return _chacha20(key, nonce, ct).decode()
    except Exception:
        return ""


def decrypt_field(provider, field_name, value):
    return decrypt_secret(value) if is_secret(provider, field_name) else value


PROVIDERS = {
    "whatsapp": {
        "name": "WhatsApp Business / Cloud API (Meta)", "icon": "💬",
        "desc": "Envio e recebimento oficial de mensagens. Requer app na Meta, número WhatsApp Business e token de acesso.",
        "webhook": "/api/webhooks/whatsapp",
        "fields": [
            {"name": "phone_number_id", "label": "Phone Number ID (ID do número)", "secret": False, "placeholder": "Ex.: 123456789012345"},
            {"name": "waba_id", "label": "WhatsApp Business Account ID (WABA)", "secret": False, "placeholder": "Ex.: 123456789012345"},
            {"name": "access_token", "label": "Token de acesso (permanente, via Usuário do Sistema)", "secret": True, "placeholder": "EAA..."},
            {"name": "verify_token", "label": "Verify Token do Webhook (você inventa e cola igual na Meta)", "secret": True, "placeholder": "Ex.: produtovenda-webhook-2024"},
            {"name": "app_secret", "label": "App Secret (opcional, p/ validar assinatura)", "secret": True, "placeholder": ""},
            {"name": "api_version", "label": "Versão da Graph API", "secret": False, "placeholder": "v21.0"},
        ],
        "required": ["phone_number_id", "access_token", "verify_token"],
    },
    "mercadopago": {
        "name": "Mercado Pago — Pix e Cartão", "icon": "💳",
        "desc": "Pix com QR Code/copia e cola e cartão via Checkout Pro. Use credenciais de teste (TEST-) antes das de produção.",
        "webhook": "/api/webhooks/mercadopago",
        "fields": [
            {"name": "access_token", "label": "Access Token (TEST-... ou APP_USR-...)", "secret": True, "placeholder": "TEST-0000000000000000-0000-..."},
            {"name": "public_key", "label": "Public Key", "secret": True, "placeholder": "TEST-..."},
            {"name": "client_id", "label": "Client ID (opcional)", "secret": False, "placeholder": ""},
            {"name": "client_secret", "label": "Client Secret (opcional)", "secret": True, "placeholder": ""},
        ],
        "required": ["access_token"],
    },
    "smtp": {
        "name": "E-mail (SMTP)", "icon": "✉️",
        "desc": "Envio real de e-mails (Gmail com senha de app, Hostinger, Amazon SES SMTP etc.).",
        "fields": [
            {"name": "host", "label": "Servidor SMTP", "secret": False, "placeholder": "smtp.gmail.com"},
            {"name": "port", "label": "Porta", "secret": False, "placeholder": "587"},
            {"name": "username", "label": "Usuário", "secret": False, "placeholder": "voce@suaempresa.com.br"},
            {"name": "password", "label": "Senha / Senha de app", "secret": True, "placeholder": ""},
            {"name": "from_email", "label": "E-mail remetente", "secret": False, "placeholder": "loja@suaempresa.com.br"},
            {"name": "from_name", "label": "Nome do remetente", "secret": False, "placeholder": "Minha Loja"},
            {"name": "use_tls", "label": "Usar STARTTLS (1 = sim, 0 = não/SSL direto na 465)", "secret": False, "placeholder": "1"},
        ],
        "required": ["host", "port", "username", "password", "from_email"],
    },
    "google_places": {
        "name": "Google Places API (Prospecção)", "icon": "📍",
        "desc": "Fonte oficial/autorizada para encontrar empresas por cidade e segmento na Prospecção IA.",
        "fields": [
            {"name": "api_key", "label": "API Key do Google Cloud (Places API New ativada)", "secret": True, "placeholder": "AIza..."},
        ],
        "required": ["api_key"],
    },
    "meta_social": {
        "name": "Instagram / Facebook (Meta)", "icon": "📸",
        "desc": "Conexão com Página do Facebook/Instagram pelas APIs oficiais da Meta (publicação e métricas quando autorizadas).",
        "fields": [
            {"name": "page_id", "label": "ID da Página do Facebook", "secret": False, "placeholder": ""},
            {"name": "page_access_token", "label": "Token de acesso da Página", "secret": True, "placeholder": "EAA..."},
            {"name": "instagram_user_id", "label": "ID da conta Instagram Business (opcional)", "secret": False, "placeholder": ""},
            {"name": "api_version", "label": "Versão da Graph API", "secret": False, "placeholder": "v21.0"},
        ],
        "required": ["page_id", "page_access_token"],
    },
}

SECRET_HINTS = ("token", "secret", "password", "key")


def is_secret(provider, field_name):
    for f in PROVIDERS.get(provider, {}).get("fields", []):
        if f["name"] == field_name:
            return bool(f.get("secret"))
    return any(h in field_name for h in SECRET_HINTS)


def mask_value(value):
    if not value:
        return ""
    v = str(value)
    return "••••••••" + v[-4:] if len(v) > 4 else "••••"


def get_config(conn, company_id, provider, active_only=False):
    row = conn.execute("SELECT * FROM integrations WHERE company_id=? AND provider=?", (company_id, provider)).fetchone()
    if not row:
        return {}
    if active_only and not row["active"]:
        return {}
    try:
        cfg = json.loads(row["config"] or "{}")
    except Exception:
        return {}
    return {k: decrypt_field(provider, k, v) for k, v in cfg.items()}


def integration_row(conn, company_id, provider):
    return conn.execute("SELECT * FROM integrations WHERE company_id=? AND provider=?", (company_id, provider)).fetchone()


def configured_status(provider, config):
    required = PROVIDERS.get(provider, {}).get("required", [])
    missing = [f for f in required if not str(config.get(f) or "").strip()]
    return (len(missing) == 0), missing


def public_config(provider, config, row=None):
    masked = {}
    for key, value in (config or {}).items():
        masked[key] = mask_value(value) if is_secret(provider, key) else value
    ok, missing = configured_status(provider, config)
    out = {
        "provider": provider,
        "name": PROVIDERS[provider]["name"],
        "icon": PROVIDERS[provider]["icon"],
        "desc": PROVIDERS[provider]["desc"],
        "fields": PROVIDERS[provider]["fields"],
        "webhook_path": PROVIDERS[provider].get("webhook"),
        "config": masked,
        "configured": ok,
        "missing": missing,
        "active": bool(row["active"]) if row else False,
        "connected": bool(ok and row and row["active"]),
        "last_test_at": row["last_test_at"] if row else None,
        "last_test_status": row["last_test_status"] if row else None,
        "last_test_detail": row["last_test_detail"] if row else None,
        "updated_at": row["updated_at"] if row else None,
    }
    out["status"] = "Conectada e ativa" if out["connected"] else ("Configurada (desativada)" if ok else "Não configurada")
    return out


def list_integrations(conn, company_id):
    out = []
    for provider in PROVIDERS:
        row = integration_row(conn, company_id, provider)
        config = get_config(conn, company_id, provider) if row else {}
        out.append(public_config(provider, config, row))
    return out


def save_config(conn, company_id, provider, incoming):
    """Salva mesclando: segredo vazio ou mascarado mantem o valor anterior."""
    if provider not in PROVIDERS:
        raise IntegrationError(f"Provedor desconhecido: {provider}", 404)
    current = get_config(conn, company_id, provider)
    merged = dict(current)
    allowed = {f["name"] for f in PROVIDERS[provider]["fields"]}
    for key, value in (incoming.get("config") or {}).items():
        if key not in allowed:
            continue
        if is_secret(provider, key) and (not value or str(value).startswith("••••")):
            continue  # mantem o segredo ja salvo
        merged[key] = str(value).strip() if isinstance(value, str) else value
    if provider == "whatsapp" and not merged.get("api_version"):
        merged["api_version"] = "v21.0"
    if provider == "meta_social" and not merged.get("api_version"):
        merged["api_version"] = "v21.0"
    active = 1 if incoming.get("active", True) else 0
    existing = integration_row(conn, company_id, provider)
    import datetime as _dt
    ts = _dt.datetime.now().isoformat(timespec="seconds")
    stored = {k: (encrypt_secret(v) if is_secret(provider, k) and v else v) for k, v in merged.items()}
    if existing:
        conn.execute("UPDATE integrations SET config=?, active=?, updated_at=? WHERE company_id=? AND provider=?",
                     (json.dumps(stored, ensure_ascii=False), active, ts, company_id, provider))
    else:
        conn.execute("INSERT INTO integrations(company_id,provider,config,active,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                     (company_id, provider, json.dumps(stored, ensure_ascii=False), active, ts, ts))
    return merged


def record_test(conn, company_id, provider, status, detail):
    import datetime as _dt
    conn.execute("UPDATE integrations SET last_test_at=?, last_test_status=?, last_test_detail=? WHERE company_id=? AND provider=?",
                 (_dt.datetime.now().isoformat(timespec="seconds"), status, str(detail)[:500], company_id, provider))


# ------------------------------------------------------------------ HTTP real
def http_json(url, method="GET", headers=None, payload=None, timeout=18):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "ProdutoVendaIA/1.0")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "ignore")
            try:
                return resp.status, json.loads(raw) if raw else {}
            except Exception:
                return resp.status, {"raw": raw}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "ignore") if hasattr(e, "read") else ""
        try:
            parsed = json.loads(raw) if raw else {}
        except Exception:
            parsed = {"raw": raw}
        raise IntegrationError(f"A API retornou HTTP {e.code}", e.code if 400 <= e.code < 600 else 502, parsed)
    except Exception as e:
        raise IntegrationError(f"Não foi possível alcançar a API ({e}). Verifique a conexão do servidor e tente de novo.", 502)


def provider_error_detail(detail):
    """Extrai mensagem amigavel de erros Meta/Mercado Pago."""
    try:
        if isinstance(detail, dict):
            err = detail.get("error") or {}
            if isinstance(err, dict) and err.get("message"):
                return err["message"]
            if detail.get("message"):
                return detail["message"]
            if detail.get("cause"):
                return str(detail["cause"])[:300]
    except Exception:
        pass
    return str(detail)[:300] if detail else ""


# ------------------------------------------------------------------ Testes de conexao (chamadas reais)
def test_connection(provider, config):
    ok, missing = configured_status(provider, config)
    if not ok:
        raise IntegrationError(f"Faltam campos obrigatórios: {', '.join(missing)}. Preencha e salve antes de testar.", 400)
    if provider == "whatsapp":
        ver = config.get("api_version") or "v21.0"
        status, data = http_json(f"{GRAPH}/{ver}/{config['phone_number_id']}?fields=display_phone_number,verified_name,quality_rating",
                                 headers={"Authorization": f"Bearer {config['access_token']}"})
        return f"Número conectado: {data.get('display_phone_number', '?')} · {data.get('verified_name', '')} · qualidade: {data.get('quality_rating', '-')}"
    if provider == "mercadopago":
        status, data = http_json(f"{MP_API}/users/me", headers={"Authorization": f"Bearer {config['access_token']}"})
        return f"Conta Mercado Pago conectada: {data.get('first_name', '')} {data.get('last_name', '')} · {data.get('email', '')} · site: {data.get('site_id', '')} · id: {data.get('id', '')}"
    if provider == "smtp":
        host, port = config["host"], int(config.get("port") or 587)
        try:
            if port == 465:
                server = smtplib.SMTP_SSL(host, port, timeout=15, context=ssl.create_default_context())
            else:
                server = smtplib.SMTP(host, port, timeout=15)
                if str(config.get("use_tls", "1")) == "1":
                    server.starttls(context=ssl.create_default_context())
            server.login(config["username"], config["password"])
            server.quit()
        except Exception as e:
            raise IntegrationError(f"Falha no SMTP: {e}", 502)
        return f"SMTP autenticado com sucesso em {host}:{port} como {config['username']}."
    if provider == "google_places":
        status, data = http_json(PLACES_API, "POST",
                                 headers={"X-Goog-Api-Key": config["api_key"], "X-Goog-FieldMask": "places.displayName"},
                                 payload={"textQuery": "cafeteria em Recife", "maxResultCount": 1, "languageCode": "pt-BR"})
        n = len(data.get("places", []))
        return f"Google Places API respondendo (teste retornou {n} resultado(s))."
    if provider == "meta_social":
        ver = config.get("api_version") or "v21.0"
        status, data = http_json(f"{GRAPH}/{ver}/{config['page_id']}?fields=name,fan_count",
                                 headers={"Authorization": f"Bearer {config['page_access_token']}"})
        return f"Página conectada: {data.get('name', '')} · seguidores: {data.get('fan_count', '-')}"
    raise IntegrationError("Provedor sem teste disponível.", 400)


# ------------------------------------------------------------------ WhatsApp Cloud API
def normalize_phone(phone):
    digits = re.sub(r"\D", "", str(phone or ""))
    if digits.startswith("55") and len(digits) >= 12:
        return digits
    if len(digits) in (10, 11):
        return "55" + digits
    return digits


def whatsapp_send(config, phone, text, template_name=None, language="pt_BR"):
    ok, missing = configured_status("whatsapp", config)
    if not ok:
        raise IntegrationError(f"WhatsApp não configurado (faltam: {', '.join(missing)}).", 400)
    ver = config.get("api_version") or "v21.0"
    to = normalize_phone(phone)
    if len(to) < 12:
        raise IntegrationError(f"Telefone inválido para WhatsApp internacional: '{phone}'. Use DDD + número.", 400)
    if template_name:
        payload = {"messaging_product": "whatsapp", "to": to, "type": "template",
                   "template": {"name": template_name, "language": {"code": language}}}
    else:
        payload = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"preview_url": False, "body": text}}
    status, data = http_json(f"{GRAPH}/{ver}/{config['phone_number_id']}/messages", "POST",
                             headers={"Authorization": f"Bearer {config['access_token']}"}, payload=payload)
    messages = data.get("messages") or [{}]
    return messages[0].get("id", ""), data


# ------------------------------------------------------------------ Mercado Pago
def mp_create_pix(config, amount, description, payer_email, external_reference, notification_url=""):
    ok, missing = configured_status("mercadopago", config)
    if not ok:
        raise IntegrationError(f"Mercado Pago não configurado (faltam: {', '.join(missing)}).", 400)
    payload = {
        "transaction_amount": round(float(amount), 2),
        "description": (description or "Pedido ProdutoVenda IA")[:230],
        "payment_method_id": "pix",
        "external_reference": str(external_reference),
        "payer": {"email": payer_email or "cliente@produtovenda.com.br"},
    }
    if notification_url:
        payload["notification_url"] = notification_url
    status, data = http_json(f"{MP_API}/v1/payments", "POST",
                             headers={"Authorization": f"Bearer {config['access_token']}", "X-Idempotency-Key": f"pv-{external_reference}-pix"},
                             payload=payload)
    tx = (data.get("point_of_interaction") or {}).get("transaction_data") or {}
    return {"external_id": str(data.get("id", "")), "status": data.get("status", "pending"),
            "qr_code": tx.get("qr_code", ""), "qr_code_base64": tx.get("qr_code_base64", ""),
            "ticket_url": tx.get("ticket_url", ""), "raw": data}


def mp_create_preference(config, items, external_reference, back_base="", notification_url=""):
    """Checkout Pro: link para cartao/boleto. items: [{title, quantity, unit_price}]"""
    ok, missing = configured_status("mercadopago", config)
    if not ok:
        raise IntegrationError(f"Mercado Pago não configurado (faltam: {', '.join(missing)}).", 400)
    payload = {
        "items": [{"title": (i.get("title") or "Produto")[:250], "quantity": int(i.get("quantity") or 1),
                   "unit_price": round(float(i.get("unit_price") or 0), 2), "currency_id": "BRL"} for i in items],
        "external_reference": str(external_reference),
        "payment_methods": {"installments": 12},
    }
    if back_base:
        payload["back_urls"] = {"success": back_base, "pending": back_base, "failure": back_base}
        payload["auto_return"] = "approved"
    if notification_url:
        payload["notification_url"] = notification_url
    status, data = http_json(f"{MP_API}/checkout/preferences", "POST",
                             headers={"Authorization": f"Bearer {config['access_token']}"}, payload=payload)
    return {"external_id": str(data.get("id", "")), "status": "pending",
            "checkout_url": data.get("init_point", "") or data.get("sandbox_init_point", ""), "raw": data}


def mp_get_payment(config, payment_id):
    ok, missing = configured_status("mercadopago", config)
    if not ok:
        raise IntegrationError(f"Mercado Pago não configurado (faltam: {', '.join(missing)}).", 400)
    status, data = http_json(f"{MP_API}/v1/payments/{payment_id}", headers={"Authorization": f"Bearer {config['access_token']}"})
    return data


# ------------------------------------------------------------------ SMTP
def smtp_send(config, to_email, subject, body):
    ok, missing = configured_status("smtp", config)
    if not ok:
        raise IntegrationError(f"SMTP não configurado (faltam: {', '.join(missing)}).", 400)
    if not to_email or "@" not in to_email:
        raise IntegrationError(f"E-mail de destino inválido: '{to_email}'.", 400)
    msg = EmailMessage()
    from_name = config.get("from_name") or ""
    msg["From"] = f"{from_name} <{config['from_email']}>" if from_name else config["from_email"]
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)
    host, port = config["host"], int(config.get("port") or 587)
    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=20, context=ssl.create_default_context())
        else:
            server = smtplib.SMTP(host, port, timeout=20)
            if str(config.get("use_tls", "1")) == "1":
                server.starttls(context=ssl.create_default_context())
        server.login(config["username"], config["password"])
        server.send_message(msg)
        server.quit()
    except Exception as e:
        raise IntegrationError(f"Falha ao enviar e-mail via SMTP: {e}", 502)
    return True


# ------------------------------------------------------------------ Google Places
SEGMENT_QUERIES = {
    "empresa": "empresas e escritórios", "empresas": "empresas e escritórios", "cafeteria": "cafeterias", "cafeterias": "cafeterias",
    "loja": "lojas de presentes", "lojas": "lojas de presentes", "restaurante": "restaurantes", "restaurantes": "restaurantes",
    "evento": "buffets e espaços de eventos", "eventos": "buffets e espaços de eventos", "hotel": "hotéis", "todos": "empresas",
}


def places_search(config, segment, city, max_results=10):
    ok, missing = configured_status("google_places", config)
    if not ok:
        raise IntegrationError(f"Google Places não configurado (faltam: {', '.join(missing)}).", 400)
    query_term = SEGMENT_QUERIES.get((segment or "").strip().lower(), segment or "empresas")
    status, data = http_json(PLACES_API, "POST",
                             headers={"X-Goog-Api-Key": config["api_key"],
                                      "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.nationalPhoneNumber,places.websiteUri,places.rating,places.googleMapsUri"},
                             payload={"textQuery": f"{query_term} em {city}", "maxResultCount": max_results, "languageCode": "pt-BR"})
    out = []
    for p in data.get("places", []):
        name = (p.get("displayName") or {}).get("text", "")
        if not name:
            continue
        out.append({"name": name, "address": p.get("formattedAddress", ""), "phone": p.get("nationalPhoneNumber", ""),
                    "site": p.get("websiteUri", "") or p.get("googleMapsUri", ""), "rating": p.get("rating", "")})
    return out
