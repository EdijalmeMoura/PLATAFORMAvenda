#!/usr/bin/env python3
"""
ProdutoVenda IA — Central de Vendas Autônomas com IA
Backend monolitico (Python stdlib apenas): HTTP + SQLite + autenticacao + multi-tenant + motor de IA local.
Nenhuma dependencia externa. Dados persistentes em plataformavenda.db
"""
import base64, csv, html as html_lib, io, json, os, re, sqlite3, hashlib, secrets, random, datetime, sys, time, threading, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import integrations as integ
from integrations import IntegrationError

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("PV_DB_PATH") or os.path.join(BASE, "plataformavenda.db")
UPLOAD_DIR = os.environ.get("PV_UPLOAD_DIR") or os.path.join(BASE, "uploads")
STATIC = os.path.join(BASE, "static")
PORT = int(os.environ.get("PORT", "8000"))
APP_VERSION = "1.4.0"
# URL pública canônica (ex.: https://minhaloja.com.br). Quando definida, é usada em
# links de redefinição de senha, webhooks e back_urls — evita depender do header Host.
PUBLIC_URL = (os.environ.get("PV_PUBLIC_URL") or "").rstrip("/")
MAX_BODY_BYTES = int(os.environ.get("PV_MAX_BODY_BYTES") or 8 * 1024 * 1024)  # 8 MB
STARTED_AT = time.time()

# ---------------------------------------------------------------- DB
def db():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=10000")
    try:
        conn.execute("PRAGMA journal_mode=WAL")       # leituras concorrentes sem bloquear escritas
    except sqlite3.DatabaseError:
        pass
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn

# Índices de uso (multi-tenant: toda query filtra por company_id). Criados de forma idempotente.
INDEXES = [
    "products(company_id, status)", "products(company_id, sales DESC)", "customers(company_id)", "customers(company_id, phone)",
    "orders(company_id, created_at)", "order_items(company_id, order_id)", "coupons(company_id, code)", "coupon_usages(company_id, coupon_id)",
    "leads(company_id, stage)", "opportunities(company_id, status)", "carts(company_id, status)",
    "campaigns(company_id, status)", "campaign_contents(company_id, scheduled_at)", "messages(company_id, created_at)",
    "message_templates(company_id)", "proposals(company_id, status)", "reviews(company_id, product_id)", "referrals(company_id)",
    "email_campaigns(company_id)", "integrations(company_id, provider)", "payments(external_id)", "payments(company_id, external_reference)",
    "subscriptions(company_id)", "notifications(company_id, read_flag)", "audit_logs(company_id, created_at)", "automation_runs(company_id, automation_id)",
    "ai_actions(company_id, created_at)", "ai_usage(company_id, created_at)", "ai_conversations(company_id, created_at)",
    "sessions(token_hash)", "sessions(expires_at)", "password_resets(token_hash)",
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS plans(id INTEGER PRIMARY KEY, name TEXT, price REAL, limits TEXT);
CREATE TABLE IF NOT EXISTS companies(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, slug TEXT UNIQUE, segment TEXT DEFAULT 'Chocolates e Doces',
  city TEXT DEFAULT '', region TEXT DEFAULT '', whatsapp TEXT DEFAULT '', email TEXT DEFAULT '', goal_monthly REAL DEFAULT 6000, goal_weekly REAL DEFAULT 1500,
  goal_daily REAL DEFAULT 200, autopilot TEXT DEFAULT 'assistido', plan_id INTEGER DEFAULT 3, onboarded INTEGER DEFAULT 0, created_at TEXT);
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER, name TEXT, email TEXT UNIQUE, pass_hash TEXT, salt TEXT,
  role TEXT DEFAULT 'owner', is_platform_admin INTEGER DEFAULT 0, created_at TEXT);
CREATE TABLE IF NOT EXISTS sessions(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, token_hash TEXT, created_at TEXT, expires_at TEXT);
CREATE TABLE IF NOT EXISTS password_resets(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, token_hash TEXT, expires_at TEXT, used INTEGER DEFAULT 0, created_at TEXT);
CREATE TABLE IF NOT EXISTS categories(id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER, name TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER, category_id INTEGER, name TEXT, description TEXT DEFAULT '',
  price REAL DEFAULT 0, cost REAL DEFAULT 0, stock INTEGER DEFAULT 0, audience TEXT DEFAULT '', icon TEXT DEFAULT '🎁', status TEXT DEFAULT 'ativo',
  sales INTEGER DEFAULT 0, ai_page INTEGER DEFAULT 0, page_data TEXT DEFAULT '', created_at TEXT);
CREATE TABLE IF NOT EXISTS customers(id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER, name TEXT, email TEXT DEFAULT '', phone TEXT DEFAULT '',
  city TEXT DEFAULT '', segment TEXT DEFAULT 'Consumidor final', consent INTEGER DEFAULT 1, vip INTEGER DEFAULT 0, referral_code TEXT DEFAULT '',
  referred_by INTEGER, total_spent REAL DEFAULT 0, purchases INTEGER DEFAULT 0, last_purchase TEXT, birthday TEXT DEFAULT '', created_at TEXT);
CREATE TABLE IF NOT EXISTS leads(id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER, name TEXT, company TEXT DEFAULT '', email TEXT DEFAULT '', phone TEXT DEFAULT '',
  city TEXT DEFAULT '', segment TEXT DEFAULT '', source TEXT DEFAULT 'Manual', stage TEXT DEFAULT 'Novo Lead', potential TEXT DEFAULT 'Médio', value REAL DEFAULT 0,
  notes TEXT DEFAULT '', next_action TEXT DEFAULT '', last_interaction TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS opportunities(id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER, name TEXT, company TEXT DEFAULT '', segment TEXT DEFAULT '',
  city TEXT DEFAULT '', phone TEXT DEFAULT '', email TEXT DEFAULT '', site TEXT DEFAULT '', source TEXT DEFAULT '', status TEXT DEFAULT 'Nova',
  potential TEXT DEFAULT 'Médio', notes TEXT DEFAULT '', last_interaction TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER, customer_id INTEGER, customer_name TEXT DEFAULT '',
  total REAL DEFAULT 0, profit REAL DEFAULT 0, status TEXT DEFAULT 'pago', channel TEXT DEFAULT 'Loja', coupon TEXT DEFAULT '', created_at TEXT);
CREATE TABLE IF NOT EXISTS order_items(id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER, order_id INTEGER, product_id INTEGER, product_name TEXT, qty INTEGER, price REAL);
CREATE TABLE IF NOT EXISTS coupons(id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER, code TEXT, type TEXT DEFAULT 'percentual', value REAL DEFAULT 10,
  kind TEXT DEFAULT 'campanha', min_value REAL DEFAULT 0, product_id INTEGER, limit_uses INTEGER DEFAULT 0, used INTEGER DEFAULT 0, active INTEGER DEFAULT 1, created_at TEXT);
CREATE TABLE IF NOT EXISTS coupon_usages(id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER, coupon_id INTEGER, customer_id INTEGER, order_id INTEGER, created_at TEXT);
CREATE TABLE IF NOT EXISTS campaigns(id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER, name TEXT, product_id INTEGER, objective TEXT DEFAULT '', audience TEXT DEFAULT '',
  region TEXT DEFAULT '', channel TEXT DEFAULT 'WhatsApp + Instagram', status TEXT DEFAULT 'ativa', budget REAL DEFAULT 0, content TEXT DEFAULT '', created_at TEXT);
CREATE TABLE IF NOT EXISTS campaign_contents(id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER, campaign_id INTEGER, title TEXT, channel TEXT, content TEXT,
  scheduled_at TEXT, status TEXT DEFAULT 'agendado', product_id INTEGER, created_at TEXT);
CREATE TABLE IF NOT EXISTS automations(id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER, name TEXT, trigger_event TEXT, action TEXT, config TEXT DEFAULT '', active INTEGER DEFAULT 1, created_at TEXT);
CREATE TABLE IF NOT EXISTS automation_runs(id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER, automation_id INTEGER, description TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER, customer_id INTEGER, channel TEXT DEFAULT 'WhatsApp', direction TEXT DEFAULT 'out',
  content TEXT, status TEXT DEFAULT 'registrado', template INTEGER DEFAULT 0, created_at TEXT);
CREATE TABLE IF NOT EXISTS message_templates(id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER, name TEXT, channel TEXT, content TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS proposals(id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER, customer_id INTEGER, customer_name TEXT, title TEXT, total REAL DEFAULT 0,
  discount REAL DEFAULT 0, deadline TEXT DEFAULT '', conditions TEXT DEFAULT '', status TEXT DEFAULT 'rascunho', content TEXT DEFAULT '', created_at TEXT);
CREATE TABLE IF NOT EXISTS proposal_items(id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER, proposal_id INTEGER, product_id INTEGER, product_name TEXT, qty INTEGER, price REAL);
CREATE TABLE IF NOT EXISTS reviews(id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER, product_id INTEGER, customer_name TEXT, rating INTEGER, comment TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS referrals(id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER, customer_id INTEGER, code TEXT, referred_name TEXT DEFAULT '', status TEXT DEFAULT 'pendente', reward TEXT DEFAULT '', created_at TEXT);
CREATE TABLE IF NOT EXISTS store_settings(id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER UNIQUE, store_name TEXT DEFAULT 'Minha Loja', logo TEXT DEFAULT '🍫',
  primary_color TEXT DEFAULT '#7c3aed', banner TEXT DEFAULT '', font TEXT DEFAULT 'Inter', domain TEXT DEFAULT '', instagram TEXT DEFAULT '', facebook TEXT DEFAULT '', description TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS carts(id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER, customer_name TEXT, phone TEXT DEFAULT '', items TEXT DEFAULT '', total REAL DEFAULT 0,
  status TEXT DEFAULT 'abandonado', stage INTEGER DEFAULT 0, created_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS ai_conversations(id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER, user_id INTEGER, role TEXT, content TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS ai_actions(id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER, action TEXT, detail TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS ai_usage(id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER, tokens INTEGER DEFAULT 0, action TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER, title TEXT, body TEXT, kind TEXT DEFAULT 'info', read_flag INTEGER DEFAULT 0, created_at TEXT);
CREATE TABLE IF NOT EXISTS audit_logs(id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER, user_id INTEGER, action TEXT, detail TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS email_campaigns(id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER, subject TEXT, content TEXT, segment TEXT DEFAULT 'Todos', status TEXT DEFAULT 'rascunho', sent INTEGER DEFAULT 0, opens INTEGER DEFAULT 0, clicks INTEGER DEFAULT 0, created_at TEXT);
CREATE TABLE IF NOT EXISTS integrations(id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER, provider TEXT, config TEXT DEFAULT '{}', active INTEGER DEFAULT 1,
  last_test_at TEXT, last_test_status TEXT, last_test_detail TEXT, created_at TEXT, updated_at TEXT, UNIQUE(company_id, provider));
CREATE TABLE IF NOT EXISTS payments(id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER, order_id INTEGER, provider TEXT DEFAULT 'mercadopago', external_id TEXT DEFAULT '',
  method TEXT DEFAULT 'pix', amount REAL DEFAULT 0, status TEXT DEFAULT 'pending', qr_code TEXT DEFAULT '', qr_code_base64 TEXT DEFAULT '', checkout_url TEXT DEFAULT '',
  raw TEXT DEFAULT '', created_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS subscriptions(id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER, plan_id INTEGER, provider TEXT DEFAULT 'mercadopago',
  external_reference TEXT DEFAULT '', status TEXT DEFAULT 'pendente', amount REAL DEFAULT 0, current_period_end TEXT, created_at TEXT, updated_at TEXT);
"""

def now():
    return datetime.datetime.now().isoformat(timespec="seconds")

def today():
    return datetime.date.today().isoformat()

def slugify(text):
    text = re.sub(r"[^a-z0-9]+", "-", (text or "loja").lower()).strip("-")
    return text or "loja"

def hash_pass(password, salt=None):
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200000).hex()
    return h, salt

def to_int(value, default=0, minimum=None, maximum=None):
    """Converte entradas do cliente (texto, '1.5', 'abc') sem derrubar a requisição."""
    try:
        out = int(float(str(value).replace(",", ".").strip()))
    except (TypeError, ValueError):
        out = int(default)
    if minimum is not None:
        out = max(out, int(minimum))
    if maximum is not None:
        out = min(out, int(maximum))
    return out

def to_float(value, default=0.0, minimum=None, maximum=None):
    try:
        out = float(str(value).replace(",", ".").strip())
    except (TypeError, ValueError):
        out = float(default)
    if minimum is not None:
        out = max(out, float(minimum))
    if maximum is not None:
        out = min(out, float(maximum))
    return out

def log_audit(conn, company_id, user_id, action, detail=""):
    conn.execute("INSERT INTO audit_logs(company_id,user_id,action,detail,created_at) VALUES(?,?,?,?,?)", (company_id, user_id, action, detail, now()))

def notify(conn, company_id, title, body, kind="info"):
    conn.execute("INSERT INTO notifications(company_id,title,body,kind,created_at) VALUES(?,?,?,?,?)", (company_id, title, body, kind, now()))

def ai_log(conn, company_id, action, detail=""):
    conn.execute("INSERT INTO ai_actions(company_id,action,detail,created_at) VALUES(?,?,?,?)", (company_id, action, detail, now()))
    conn.execute("INSERT INTO ai_usage(company_id,tokens,action,created_at) VALUES(?,?,?,?)", (company_id, random.randint(350, 1400), action, now()))

# ---------------------------------------------------------------- Motor de IA (local, deterministico, sem chave externa)
SEGMENT_HOOKS = {
    "chocolate": ("🍫", "presentear quem se ama", "caixas presenteáveis com cartão personalizado"),
    "bolo": ("🎂", "celebrar momentos especiais", "encomendas com 24h e sabores artesanais"),
    "pizza": ("🍕", "reunir a família e os amigos", "massa artesanal e entrega rápida"),
    "hamburguer": ("🍔", "matar a fome com sabor de verdade", "blend artesanal e molho da casa"),
    "roupa": ("👗", "renovar o guarda-roupa com estilo", "peças selecionadas e troca fácil"),
    "cosmetico": ("💄", "cuidar da beleza todos os dias", "fórmulas de qualidade e rotina personalizada"),
    "perfume": ("🌸", "marcar presença com uma fragrância única", "fixação prolongada e frascos presenteáveis"),
    "artesanato": ("🎨", "ter uma peça única feita à mão", "produção artesanal e personalização"),
    "presente": ("🎁", "surpreender em qualquer ocasião", "embalagem especial e cartão incluso"),
    "digital": ("💻", "aprender e evoluir no seu ritmo", "acesso imediato e suporte incluso"),
    "serviço": ("⭐", "resolver com quem entende do assunto", "atendimento profissional e garantia"),
}
def segment_hook(name="", segment=""):
    text = ((name or "") + " " + (segment or "")).lower()
    for key, val in SEGMENT_HOOKS.items():
        if key in text:
            return val
    return ("✨", "aproveitar uma oferta feita para você", "qualidade garantida e atendimento próximo")

def brl(v):
    try:
        return "R$ " + f"{float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"

# ---------------------------------------------------------------- Loja pública (URL amigável + preview social)
def esc_html(value):
    return html_lib.escape(str(value if value is not None else ""), quote=True)

def store_page_html(company, settings, products, base, focus=None, reviews=None):
    """Página pública servida em /loja/<slug> (e /loja/<slug>/produto/<id>).

    Renderizada no servidor para o link funcionar em preview de WhatsApp/Facebook/Google
    e também abrir rápido no celular; o botão leva para a loja completa (carrinho/checkout).
    """
    settings = settings or {}
    slug = company["slug"]
    store_name = (settings.get("store_name") or company["name"] or "Minha Loja").strip()
    color = settings.get("primary_color") or "#7c3aed"
    logo = settings.get("logo") or "🛍️"
    description = (settings.get("description") or "").strip()
    banner = (settings.get("banner") or description or f"Confira os produtos de {store_name} e faça seu pedido online.").strip()
    backorder = to_int(settings.get("allow_backorder"), 0) > 0
    wa = re.sub(r"\D", "", str(company["whatsapp"] or ""))
    if wa and not wa.startswith("55"):
        wa = "55" + wa
    store_url = f"{base}/loja/{slug}"
    app_url = f"{base}/#/loja/{slug}"
    # Título enxuto para preview: só acrescenta o banner quando o nome é curto e não repete o texto
    title = f"{store_name} · {banner[:70]}" if (banner and len(store_name) <= 30 and banner.lower() not in store_name.lower()) else store_name
    page_desc = description or banner
    if focus:
        title = f"{focus['name']} · {brl(focus['price'])} — {store_name}"
        page_desc = (focus.get("description") or banner)[:180]
    og_image = ""
    for candidate in ([focus] if focus else []) + list(products):
        if candidate and candidate.get("image"):
            img = str(candidate["image"])
            og_image = img if img.startswith("http") else base + img
            break
    cards = []
    for p in products[:24]:
        img = str(p.get("image") or "")
        thumb = (f'<img src="{esc_html(img)}" alt="{esc_html(p["name"])}" loading="lazy">' if img
                 else f'<span class="ph">{esc_html(p.get("icon") or "🎁")}</span>')
        stock = to_int(p.get("stock"), 0)
        tag = (f'<span class="tag">{stock} disponíveis</span>' if stock > 0 else
               ('<span class="tag encomenda">Sob encomenda</span>' if backorder else '<span class="tag esgotado">Esgotado</span>'))
        cards.append(
            f'<a class="p" href="{esc_html(base)}/loja/{esc_html(slug)}/produto/{to_int(p["id"])}">{thumb}'
            f'<div class="pb"><b>{esc_html(p["name"])}</b><p>{esc_html((p.get("description") or "")[:90])}</p>'
            f'<div class="pr"><span class="price">{esc_html(brl(p.get("price")))}</span>{tag}</div></div></a>')
    if focus:
        hero_product = f'<div class="focus"><b>Você recebeu este produto:</b> <span>{esc_html(focus["name"])} — {esc_html(brl(focus["price"]))}</span></div>'
    else:
        hero_product = ""
    reviews_html = ""
    if reviews:
        items = "".join(f'<div class="rev"><b>{"⭐" * to_int(r.get("rating"), 5, minimum=1, maximum=5)}</b>'
                        f'<p>{esc_html((r.get("comment") or "")[:160])}</p><span>— {esc_html(r.get("customer_name") or "Cliente")}</span></div>'
                        for r in reviews[:3])
        reviews_html = f'<h2>Avaliações de quem já comprou</h2><div class="revs">{items}</div>'
    whatsapp_btn = (f'<a class="btn ghost" href="https://wa.me/{esc_html(wa)}?text={urllib.parse.quote("Olá! Vi sua loja e quero comprar: " + store_url)}" rel="noopener" target="_blank">💬 Falar no WhatsApp</a>'
                    if wa else "")
    json_ld = json.dumps({
        "@context": "https://schema.org", "@type": "Store", "name": store_name, "description": page_desc,
        "url": store_url, **({"image": og_image} if og_image else {}),
        "address": {"@type": "PostalAddress", "addressLocality": company["city"] or "", "addressRegion": company["region"] or "", "addressCountry": "BR"},
        "makesOffer": [{"@type": "Offer", "priceCurrency": "BRL", "price": round(to_float(p.get("price")), 2),
                        "availability": ("https://schema.org/InStock" if to_int(p.get("stock"), 0) > 0 else
                                         ("https://schema.org/PreOrder" if backorder else "https://schema.org/OutOfStock")),
                        "itemOffered": {"@type": "Product", "name": p["name"], "description": (p.get("description") or "")[:180]}}
                       for p in (products[:12])],
    }, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc_html(title)}</title>
<meta name="description" content="{esc_html(page_desc)}">
<link rel="canonical" href="{esc_html(store_url)}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{esc_html(store_name)}">
<meta property="og:title" content="{esc_html(title)}">
<meta property="og:description" content="{esc_html(page_desc)}">
<meta property="og:url" content="{esc_html(store_url)}">
{f'<meta property="og:image" content="{esc_html(og_image)}">' if og_image else ""}
<meta name="twitter:card" content="{'summary_large_image' if og_image else 'summary'}">
<meta name="theme-color" content="{esc_html(color)}">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>{esc_html(logo[:2])}</text></svg>">
<script type="application/ld+json">{json_ld}</script>
<style>
:root{{--c:{esc_html(color)}}}
*{{box-sizing:border-box}}
body{{margin:0;font-family:Inter,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;background:#0f172a;color:#0f172a}}
.wrap{{max-width:1020px;margin:0 auto;padding:0 16px 56px}}
.top{{background:linear-gradient(135deg,var(--c),#111827);color:#fff;padding:34px 16px 30px;text-align:center}}
.top .logo{{font-size:46px}}
.top h1{{margin:8px 0 6px;font-size:27px}}
.top p{{margin:0 auto;max-width:640px;opacity:.92;line-height:1.55}}
.cta{{display:flex;gap:10px;justify-content:center;flex-wrap:wrap;margin-top:20px}}
.btn{{display:inline-block;background:var(--c);color:#fff;text-decoration:none;font-weight:700;padding:13px 22px;border-radius:12px}}
.btn.ghost{{background:rgba(255,255,255,.16);border:1px solid rgba(255,255,255,.35)}}
h2{{color:#fff;font-size:19px;margin:30px 0 14px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(215px,1fr));gap:14px}}
.p{{background:#fff;border-radius:16px;overflow:hidden;text-decoration:none;color:inherit;display:flex;flex-direction:column}}
.p img,.p .ph{{width:100%;height:155px;object-fit:cover;display:flex;align-items:center;justify-content:center;font-size:54px;background:linear-gradient(135deg,#ede9fe,#fce7f3)}}
.pb{{padding:13px 14px 15px;display:flex;flex-direction:column;gap:6px;flex:1}}
.pb p{{margin:0;font-size:12.5px;color:#64748b;line-height:1.45;flex:1}}
.pr{{display:flex;align-items:center;justify-content:space-between;gap:8px}}
.price{{font-weight:800;font-size:17px}}
.tag{{font-size:11px;background:#eef2ff;color:#4338ca;border-radius:999px;padding:4px 9px;white-space:nowrap}}
.tag.encomenda{{background:#fef3c7;color:#92400e}}
.tag.esgotado{{background:#fee2e2;color:#991b1b}}
.focus{{background:#fff;border-radius:14px;padding:14px 16px;margin:22px 0 0;text-align:center}}
.revs{{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:12px}}
.rev{{background:#fff;border-radius:14px;padding:14px}}
.rev p{{margin:6px 0;font-size:13px;color:#334155}}
.rev span{{font-size:12px;color:#64748b}}
footer{{color:#94a3b8;font-size:12.5px;text-align:center;margin-top:38px;line-height:1.7}}
footer a{{color:#c4b5fd}}
</style>
</head>
<body>
<header class="top">
  <div class="logo">{esc_html(logo)}</div>
  <h1>{esc_html(store_name)}</h1>
  <p>{esc_html(banner)}</p>
  <div class="cta"><a class="btn" href="{esc_html(app_url)}">🛒 Ver loja completa e comprar</a>{whatsapp_btn}</div>
</header>
<div class="wrap">
  {hero_product}
  <h2>{'Produtos' if products else 'Catálogo em preparação'}</h2>
  <div class="grid">{"".join(cards) or '<p style="color:#cbd5e1">Os produtos desta loja estão sendo cadastrados. Fale com a loja para saber mais.</p>'}</div>
  {reviews_html}
  <footer>
    {esc_html(company["city"] or "")}{' · ' + esc_html(company["region"]) if company["region"] else ''}<br>
    Loja criada com <a href="{esc_html(base)}">ProdutoVenda IA</a> 🚀 — Você cadastra o que vende. A IA transforma em vendas.
  </footer>
</div>
</body>
</html>"""

def ai_product_page(product, company):
    emoji, purpose, diff = segment_hook(product["name"], company["segment"] if company else "")
    price = float(product["price"] or 0)
    audience = product["audience"] or "quem busca qualidade e um presente especial"
    return {
        "title": f"{product['name']} — feito para {purpose}",
        "subtitle": f"A escolha ideal para {audience}. {diff.capitalize()}.",
        "description": (f"O {product['name']} foi pensado para {purpose}, com ingredientes/materiais selecionados, "
                        f"acabamento caprichado e apresentação que encanta desde a primeira olhada. Perfeito para {audience}, "
                        f"ele une qualidade, carinho em cada detalhe e o melhor custo-benefício da região"
                        f"{(' de ' + company['city']) if company and company['city'] else ''}."),
        "benefits": [f"Ideal para {purpose}", diff.capitalize(), "Embalagem pronta para presente", "Produzido sob encomenda / reposição rápida", "Atendimento humanizado pelo WhatsApp"],
        "differentials": [diff.capitalize(), "Qualidade conferida item a item", "Personalização disponível", "Entrega combinada com você"],
        "faq": [
            {"q": "Vocês entregam?", "a": "Sim! Combinamos entrega ou retirada pelo WhatsApp após o pedido."},
            {"q": "Posso personalizar?", "a": "Sim, oferecemos personalização (cartão, mensagem e detalhes). Fale conosco no WhatsApp."},
            {"q": "Quais formas de pagamento?", "a": "Pix, cartão e dinheiro. Confirmamos tudo no atendimento."},
            {"q": "Precisa encomendar com antecedência?", "a": "Para garantir o seu, recomendamos pedir com antecedência — a produção é limitada."},
        ],
        "cta": f"Quero o meu por {brl(price)}",
        "urgency": f"Estoque atual: {product['stock']} unidades — garanta o seu." if (product["stock"] or 0) and product["stock"] <= 20 else "Produção limitada por semana — peça com antecedência.",
    }

def ai_campaign_pack(product, objective, audience, company):
    emoji, purpose, diff = segment_hook(product["name"], company["segment"] if company else "")
    name = product["name"]
    aud = audience or product["audience"] or "clientes da região"
    obj = objective or "vender mais nesta semana"
    city = (company["city"] if company else "") or "sua cidade"
    return {
        "name": f"Campanha {name} — {obj}",
        "strategy": (f"Foco em {aud} em {city}. Oferta principal com cupom exclusivo, sequência de WhatsApp para base consentida, "
                     f"conteúdo orgânico no Instagram por 5 dias e reativação de clientes antigos. Objetivo: {obj}."),
        "offer": f"{name} com condição especial por tempo limitado + cartão personalizado grátis em pedidos para presente.",
        "ad_copy": f"{emoji} {name} por {brl(product['price'])}! Feito para {purpose}. {diff.capitalize()}. Peça agora pelo WhatsApp e garanta o seu. 👇",
        "instagram_post": (f"{emoji} {name}: porque {purpose} merece algo especial.\n\n✨ {diff.capitalize()}\n🎁 Embalagem pronta para presente\n"
                           f"💬 Peça pelo link da bio ou WhatsApp\n\n#presente #{city.lower().replace(' ','')} #feitoamao #oferta"),
        "story": f"Sequência de 3 stories: 1) bastidores/produção, 2) detalhes do {name}, 3) enquete + CTA 'Quero um' com cupom.",
        "video_script": f"Roteiro 20s: abertura mostrando {name} de perto → benefício principal ({diff}) → preço {brl(product['price'])} → CTA WhatsApp.",
        "whatsapp": (f"Oi! 😊 Passando para te contar que o *{name}* está com condição especial esta semana: {brl(product['price'])} "
                     f"e cartão personalizado grátis. Quer que eu reserve um para você? {emoji}"),
        "email_subject": f"{emoji} {name}: condição especial só esta semana",
        "email_body": f"Olá! O {name} é ideal para {purpose}. Nesta semana ele está por {brl(product['price'])} com condição exclusiva para nossa lista. Garanta o seu na loja ou pelo WhatsApp.",
        "followup": [
            f"Oi! Só passando para saber se você viu a condição do *{name}* 😊 Posso te mandar fotos/detalhes?",
            f"Passando para lembrar: a condição especial do *{name}* termina em breve. Quer garantir o seu?",
            "Última chamada 💛 Separei as últimas unidades do *{name}*. Me confirma se quer uma?",
        ],
        "coupon_suggestion": "OFERTA10",
    }

def ai_chat_reply(message, conn, company, user):
    msg = (message or "").lower()
    cid = company["id"]
    products = conn.execute("SELECT * FROM products WHERE company_id=? ORDER BY sales DESC", (cid,)).fetchall()
    if not products:
        return {"reply": "Você ainda não cadastrou produtos. Cadastre seu primeiro produto e eu crio descrição, página, campanha e cupom automaticamente. 🚀",
                "actions": [{"label": "CADASTRAR PRODUTO", "action": "go", "target": "produtos"}]}
    top = products[0]
    def prod_actions(p):
        return [
            {"label": "CRIAR CAMPANHA", "action": "campaign", "product_id": p["id"]},
            {"label": "CRIAR CUPOM", "action": "coupon", "product_id": p["id"]},
            {"label": "ENCONTRAR CLIENTES", "action": "go", "target": "prospeccao"},
            {"label": "CRIAR MENSAGENS", "action": "messages", "product_id": p["id"]},
        ]
    if any(k in msg for k in ["empresa", "corporativo", "b2b", "cnpj"]):
        kit = next((p for p in products if "corporativo" in p["name"].lower() or "kit" in p["name"].lower()), top)
        return {"reply": f"Ótima estratégia! O *{kit['name']}* ({brl(kit['price'])}) é ideal para empresas (presentes corporativos, clientes e equipe). "
                         f"Monte uma prospecção de empresas na sua região, envie uma proposta profissional e ofereça desconto por quantidade a partir de 10 unidades. Quer que eu gere a campanha corporativa agora?",
                "actions": prod_actions(kit) + [{"label": "GERAR PROPOSTA", "action": "go", "target": "propostas"}]}
    if any(k in msg for k in ["recuperar", "antigo", "inativo", "voltar", "carrinho"]):
        inactive = conn.execute("SELECT COUNT(*) c FROM customers WHERE company_id=? AND (last_purchase IS NULL OR last_purchase < date('now','-45 day'))", (cid,)).fetchone()["c"]
        carts = conn.execute("SELECT COUNT(*) c FROM carts WHERE company_id=? AND status='abandonado'", (cid,)).fetchone()["c"]
        return {"reply": f"Analisei sua base: encontrei *{inactive} clientes inativos* e *{carts} carrinhos abandonados*. "
                         f"Recomendo uma campanha de reativação com o cupom VOLTEI15 para clientes antigos e lembrete gentil para os carrinhos com o *{top['name']}*. Posso criar tudo agora:",
                "actions": [{"label": "CRIAR CUPOM VOLTEI15", "action": "coupon_code", "code": "VOLTEI15", "value": 15},
                            {"label": "RECUPERAR CARRINHOS", "action": "run_automations", "target": "automacoes"},
                            {"label": "VER OPORTUNIDADES", "action": "go", "target": "oportunidades"}]}
    if any(k in msg for k in ["ticket", "mais caro", "combo", "aumentar"]):
        second = products[1] if len(products) > 1 else top
        return {"reply": f"Para aumentar o ticket médio, minha sugestão é um combo: *{top['name']}* + *{second['name']}* com 10% de desconto no segundo item, "
                         f"e um cupom de frete/benefício em compras acima de um valor mínimo. Isso eleva o valor por pedido sem depender de novos clientes.",
                "actions": prod_actions(top)}
    if any(k in msg for k in ["promoção", "promocao", "desconto", "oferta", "data", "dia das", "natal", "sazonal"]):
        return {"reply": f"Perfeito! Vou montar uma campanha sazonal com o *{top['name']}*: oferta com prazo real, cupom exclusivo, posts + stories, "
                         f"mensagem de WhatsApp para clientes que autorizaram contato e página do produto atualizada. Nada de spam — só base consentida. 💛",
                "actions": prod_actions(top)}
    if any(k in msg for k in ["vender", "venda", "meta", "faturar", "quero"]):
        sold = conn.execute("SELECT COALESCE(SUM(total),0) s FROM orders WHERE company_id=? AND status IN ('pago','entregue','concluido') AND strftime('%Y-%m',created_at)=strftime('%Y-%m','now')", (cid,)).fetchone()["s"]
        goal = float(company["goal_monthly"] or 6000)
        missing = max(goal - sold, 0)
        avg_profit = 40
        orders_needed = int(missing / avg_profit) + (1 if missing % avg_profit else 0) if missing else 0
        return {"reply": (f"Analisei seus produtos e vendas. Seu mais vendido é o *{top['name']}* ({brl(top['price'])}, {top['sales'] or 0} vendas). "
                          f"No mês você vendeu {brl(sold)} de uma meta de {brl(goal)} — faltam {brl(missing)}"
                          + (f", cerca de {orders_needed} pedidos de ~{brl(avg_profit)} de lucro médio. " if missing else ". Meta batida! 🎉 ")
                          + f"Recomendo: campanha de *{top['name']}* com 10% OFF para novos clientes (BEMVINDO10) e oferta especial para quem já comprou. Quer que eu crie?"),
                "actions": prod_actions(top), "plan": ["Criar campanha do produto mais vendido", "Ativar cupom BEMVINDO10", "Prospectar empresas e clientes antigos", "Agendar 5 conteúdos esta semana", "Acompanhar conversão no Dashboard"]}
    if any(k in msg for k in ["analis", "relat", "desempenho", "como est"]):
        return {"reply": "Fiz uma análise rápida dos seus dados (veja a página Insights IA para detalhes): produto líder, clientes inativos, carrinhos e leads sem follow-up já estão mapeados com ações prontas para executar.",
                "actions": [{"label": "VER INSIGHTS IA", "action": "go", "target": "insights"}, {"label": "VER RELATÓRIOS", "action": "go", "target": "relatorios"}]}
    return {"reply": f"Entendi! Com base no seu catálogo, o maior potencial imediato está no *{top['name']}* ({brl(top['price'])}). "
                     f"Posso criar uma campanha completa, um cupom, encontrar clientes na sua região ou montar mensagens de follow-up. Por onde começamos?",
            "actions": prod_actions(top)}

# ---------------------------------------------------------------- Seed
PROSPECT_BASE = [
    ("Cafeteria", ["Cafeteria Aroma da Praça", "Café & Prosa", "Cafeteria Grão Nobre", "Casa do Café Recife", "Cafeteria Pão Dourado"]),
    ("Empresa", ["Tech Recife Soluções", "Advocacia Prado & Associados", "Clínica Vida Plena", "Imobiliária Lar Certo", "Construtora Horizonte", "Agência Pulso Marketing", "Escritório ContaFácil"]),
    ("Loja", ["Papelaria Criativa", "Floricultura Flor & Cor", "Loja Presentes & Cia", "Empório Sabores do Nordeste"]),
    ("Restaurante", ["Restaurante Sabor da Casa", "Bistrô Varanda", "Pizzaria Forno Alto"]),
    ("Evento", ["Buffet Celebre Eventos", "Casa de Festas Jardim", "Cerimonial Sonhos"]),
]

def seed(conn):
    if conn.execute("SELECT COUNT(*) c FROM plans").fetchone()["c"] == 0:
        plans = [
            ("FREE", 0, {"produtos": 5, "clientes": 50, "leads": 50, "campanhas": 2, "ia_mensal": 30, "automacoes": 1, "usuarios": 1}),
            ("STARTER", 29.9, {"produtos": 30, "clientes": 300, "leads": 300, "campanhas": 10, "ia_mensal": 200, "automacoes": 5, "usuarios": 2}),
            ("PRO", 79.9, {"produtos": 200, "clientes": 2000, "leads": 2000, "campanhas": 50, "ia_mensal": 1000, "automacoes": 20, "usuarios": 5}),
            ("BUSINESS", 199.9, {"produtos": 9999, "clientes": 99999, "leads": 99999, "campanhas": 9999, "ia_mensal": 5000, "automacoes": 9999, "usuarios": 20}),
        ]
        for name, price, limits in plans:
            conn.execute("INSERT INTO plans(name,price,limits) VALUES(?,?,?)", (name, price, json.dumps(limits)))
    if conn.execute("SELECT COUNT(*) c FROM users WHERE email='demo@produtovenda.com.br'").fetchone()["c"]:
        return
    # Empresa demo: Chocolates (primeiro caso de uso) — trocavel depois nas Configuracoes
    cur = conn.execute("INSERT INTO companies(name,slug,segment,city,region,whatsapp,email,goal_monthly,goal_weekly,goal_daily,autopilot,plan_id,onboarded,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       ("Choco Encanto", "choco-encanto", "Chocolates e Doces", "Recife", "Recife e região metropolitana", "(81) 99999-0000", "contato@chocoencanto.com.br", 6000, 1500, 220, "assistido", 3, 1, now()))
    cid = cur.lastrowid
    conn.execute("INSERT INTO store_settings(company_id,store_name,logo,primary_color,banner,font,instagram,facebook,description) VALUES(?,?,?,?,?,?,?,?,?)",
                 (cid, "Choco Encanto — Chocolates Artesanais", "🍫", "#7c3aed", "Chocolates artesanais para presentear quem você ama", "Inter", "@chocoencanto", "chocoencanto", "Caixas de bombons artesanais, kits presente e kits corporativos feitos em Recife."))
    ph, salt = hash_pass("demo1234")
    cur = conn.execute("INSERT INTO users(company_id,name,email,pass_hash,salt,role,is_platform_admin,created_at) VALUES(?,?,?,?,?,?,?,?)",
                       (cid, "Maria Clara (Demo)", "demo@produtovenda.com.br", ph, salt, "owner", 1, now()))
    demo_user = cur.lastrowid
    conn.execute("INSERT INTO categories(company_id,name,created_at) VALUES(?,?,?)", (cid, "Caixas de Bombons", now()))
    conn.execute("INSERT INTO categories(company_id,name,created_at) VALUES(?,?,?)", (cid, "Kits Presente", now()))
    conn.execute("INSERT INTO categories(company_id,name,created_at) VALUES(?,?,?)", (cid, "Corporativo", now()))
    products = [
        ("Caixa 6 Bombons", "Caixa com 6 bombons artesanais de chocolate ao leite e meio amargo, recheios variados.", 29.9, 13.0, 40, "Presentes rápidos, lembranças e mimos", "🍬", 86),
        ("Caixa 12 Bombons", "Caixa presenteável com 12 bombons artesanais, cartão personalizado incluso.", 49.9, 22.0, 50, "Mulheres, presentes, aniversários e datas especiais", "🍫", 142),
        ("Caixa Premium 24 Bombons", "Caixa premium com 24 bombons selecionados, sabores exclusivos e embalagem de luxo.", 89.9, 41.0, 22, "Presentes sofisticados e clientes VIP", "🎁", 58),
        ("Kit Presente Encanto", "Kit com caixa 12 bombons, cartão, pelúcia pequena e embalagem especial.", 119.9, 58.0, 15, "Namorados, aniversários e pedidos de desculpas", "💝", 37),
        ("Kit Corporativo", "Kit de chocolates para empresas: brindes, clientes e equipes, com desconto por quantidade.", 79.9, 36.0, 100, "Empresas, RH, eventos e clientes corporativos", "🏢", 44),
    ]
    pids = []
    for name, desc, price, cost, stock, aud, icon, sales in products:
        page = ai_product_page({"name": name, "price": price, "stock": stock, "audience": aud, "icon": icon}, {"segment": "Chocolates e Doces", "city": "Recife"})
        cur = conn.execute("INSERT INTO products(company_id,name,description,price,cost,stock,audience,icon,sales,ai_page,page_data,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                           (cid, name, page["description"], price, cost, stock, aud, icon, sales, 1, json.dumps(page, ensure_ascii=False), now()))
        pids.append(cur.lastrowid)
    customers = [
        ("Ana Beatriz Souza", "ana@exemplo.com.br", "(81) 98888-1001", "Recife", "Cliente VIP", 1, 1, 1240.0, 9, -3), ("Carlos Menezes", "carlos@exemplo.com.br", "(81) 98888-1002", "Olinda", "Consumidor final", 1, 0, 320.0, 3, -12),
        ("Fernanda Lima", "fernanda@exemplo.com.br", "(81) 98888-1003", "Recife", "Cliente antiga", 1, 0, 540.0, 5, -75), ("Juliana Castro", "juliana@exemplo.com.br", "(81) 98888-1004", "Jaboatão", "Consumidor final", 1, 0, 149.0, 2, -8),
        ("Roberto Alves", "roberto@techrecife.com.br", "(81) 98888-1005", "Recife", "Empresa", 1, 0, 2390.0, 4, -20), ("Patrícia Gomes", "patricia@exemplo.com.br", "(81) 98888-1006", "Paulista", "Cliente inativa", 1, 0, 210.0, 2, -95),
        ("Marcos Vinícius", "marcos@exemplo.com.br", "(81) 98888-1007", "Recife", "Consumidor final", 0, 0, 89.9, 1, -30), ("Luciana Prado", "luciana@exemplo.com.br", "(81) 98888-1008", "Recife", "Cliente VIP", 1, 1, 1890.0, 11, -5),
        ("Empresa Tech Recife (RH)", "rh@techrecife.com.br", "(81) 98888-1009", "Recife", "Empresa", 1, 0, 3196.0, 2, -15), ("Camila Duarte", "camila@exemplo.com.br", "(81) 98888-1010", "Camaragibe", "Consumidor final", 1, 0, 59.8, 1, -68),
    ]
    for i, (name, email, phone, city, seg, consent, vip, spent, purchases, days_ago) in enumerate(customers):
        last = (datetime.date.today() + datetime.timedelta(days=days_ago)).isoformat()
        cur = conn.execute("INSERT INTO customers(company_id,name,email,phone,city,segment,consent,vip,referral_code,total_spent,purchases,last_purchase,birthday,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                           (cid, name, email, phone, city, seg, consent, vip, f"INDICA{i+1:03d}", spent, purchases, last, f"199{ i }-0{ (i%9)+1 }-15", now()))
        if i in (0, 7):
            conn.execute("INSERT INTO referrals(company_id,customer_id,code,referred_name,status,reward,created_at) VALUES(?,?,?,?,?,?,?)",
                         (cid, cur.lastrowid, f"INDICA{i+1:03d}", "Amiga indicada", "comprada" if i == 0 else "pendente", "Cupom 10% próxima compra", now()))
    leads_data = [
        ("Hotel Boa Viagem", "Hotel Boa Viagem", "eventos@hotelbv.com.br", "(81) 4002-1001", "Recife", "Hotelaria", "Prospecção IA", "Proposta", "Alto", 2400, "Kit boas-vindas para hóspedes VIP"),
        ("Clínica Vida Plena", "Clínica Vida Plena", "contato@vidaplena.com.br", "(81) 4002-1002", "Recife", "Saúde", "Prospecção IA", "Interessado", "Alto", 1600, "Brindes para pacientes"),
        ("Escola Saber Viver", "Escola Saber Viver", "diretoria@saberviver.com.br", "(81) 4002-1003", "Olinda", "Educação", "Instagram", "Negociação", "Médio", 950, "Lembranças Dia dos Professores"),
        ("Mariana Lopes", "", "mariana@exemplo.com.br", "(81) 97777-2001", "Recife", "Consumidor final", "Instagram", "Novo Lead", "Médio", 120, "Viu post da Caixa 12"),
        ("Condomínio Alphaville", "Condomínio Alphaville", "sindico@alphaville.com.br", "(81) 4002-1004", "Recife", "Condomínio", "Indicação", "Contato Realizado", "Médio", 800, "Presentes de boas-vindas a moradores"),
        ("Festa da Júlia (aniversário)", "Júlia Mendes", "julia@exemplo.com.br", "(81) 97777-2002", "Jaboatão", "Evento", "WhatsApp", "Pedido", "Alto", 450, "60 caixas 6 bombons para festa"),
        ("Loja Presentes & Cia", "Presentes & Cia", "loja@presentesecia.com.br", "(81) 4002-1005", "Recife", "Varejo", "Prospecção IA", "Novo Lead", "Médio", 1200, "Revenda de caixas presenteáveis"),
        ("Pedro Henrique", "", "pedro@exemplo.com.br", "(81) 97777-2003", "Paulista", "Consumidor final", "Loja", "Pago", "Baixo", 89.9, "Comprou Caixa Premium"),
        ("Buffet Celebre", "Buffet Celebre Eventos", "contato@celebre.com.br", "(81) 4002-1006", "Recife", "Eventos", "Prospecção IA", "Perdido", "Baixo", 0, "Achou caro — retomar em data sazonal"),
    ]
    for name, company_name, email, phone, city, seg, source, stage, potential, value, notes in leads_data:
        conn.execute("INSERT INTO leads(company_id,name,company,email,phone,city,segment,source,stage,potential,value,notes,next_action,last_interaction,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (cid, name, company_name, email, phone, city, seg, source, stage, potential, value, notes, "Enviar follow-up personalizado", (datetime.date.today() - datetime.timedelta(days=random.randint(1, 9))).isoformat(), now()))
    for seg, names in PROSPECT_BASE:
        for name in names[:2]:
            conn.execute("INSERT INTO opportunities(company_id,name,company,segment,city,phone,email,site,source,status,potential,notes,last_interaction,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (cid, name, name, seg, "Recife", "(81) 4002-9" + str(random.randint(100, 999)), "contato@" + slugify(name) + ".com.br", "https://" + slugify(name) + ".com.br", "Prospecção IA (base demonstrativa)", "Nova", random.choice(["Alto", "Médio"]), "Potencial para kits e presentes — validar contato pelos canais oficiais.", today(), now()))
    for code, typ, value, kind, minv in [("BEMVINDO10", "percentual", 10, "primeira compra", 0), ("CHOCOLATE10", "percentual", 10, "campanha", 0), ("CLIENTEVIP", "percentual", 15, "cliente antigo", 100), ("VOLTEI15", "percentual", 15, "campanha", 0)]:
        conn.execute("INSERT INTO coupons(company_id,code,type,value,kind,min_value,limit_uses,used,active,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                     (cid, code, typ, value, kind, minv, 100, random.randint(3, 28), 1, now()))
    pack = ai_campaign_pack({"name": "Caixa 12 Bombons", "price": 49.9, "audience": "Mulheres, presentes e aniversários"}, "vender mais nesta semana", "", {"segment": "Chocolates e Doces", "city": "Recife"})
    conn.execute("INSERT INTO campaigns(company_id,name,product_id,objective,audience,region,channel,status,content,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                 (cid, pack["name"], pids[1], "vender mais nesta semana", "Mulheres, presentes e aniversários", "Recife e região", "WhatsApp + Instagram", "ativa", json.dumps(pack, ensure_ascii=False), now()))
    conn.execute("INSERT INTO campaigns(company_id,name,product_id,objective,audience,region,channel,status,content,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                 (cid, "Campanha Kits Corporativos — Empresas de Recife", pids[4], "vender para empresas", "Empresas, RH e eventos", "Recife", "E-mail + WhatsApp", "ativa", json.dumps(ai_campaign_pack({"name": "Kit Corporativo", "price": 79.9, "audience": "Empresas"}, "vender para empresas", "Empresas", {"segment": "Chocolates e Doces", "city": "Recife"}), ensure_ascii=False), now()))
    for name, trigger, action, config in [
        ("Recuperação de carrinho abandonado", "carrinho_abandonado", "enviar_mensagem", "Aguardar 1h → lembrete; 24h → segunda mensagem; 48h → cupom VOLTEI10 se configurado"),
        ("Follow-up de lead sem resposta", "lead_sem_resposta", "enviar_mensagem", "24h após contato sem resposta"),
        ("Pós-venda e avaliação", "pedido_concluido", "solicitar_avaliacao", "2 dias após entrega"),
        ("Reativação de cliente inativo (60 dias)", "cliente_inativo_60d", "criar_oportunidade", "Criar oportunidade + sugerir cupom VOLTEI15"),
        ("Alerta de estoque baixo", "estoque_baixo", "alertar_admin", "Estoque abaixo de 20 unidades"),
        ("Boas-vindas novo cliente", "novo_cliente", "enviar_mensagem", "Mensagem de boas-vindas + BEMVINDO10"),
    ]:
        conn.execute("INSERT INTO automations(company_id,name,trigger_event,action,config,active,created_at) VALUES(?,?,?,?,?,?,?)", (cid, name, trigger, action, config, 1, now()))
    for name, channel, content in [
        ("Boas-vindas WhatsApp", "WhatsApp", "Oi, {nome}! 😊 Bem-vindo(a) à {loja}. Use o cupom BEMVINDO10 na sua primeira compra!"),
        ("Recuperação de carrinho", "WhatsApp", "Oi, {nome}! Seu pedido ainda está esperando por você 🍫 Quer que eu finalize para você?"),
        ("Pós-venda / avaliação", "WhatsApp", "Oi, {nome}! Gostou dos chocolates? ⭐ Sua avaliação ajuda muito. Como agradecimento: CLIENTEVIP na próxima compra."),
        ("Aniversário", "WhatsApp", "Feliz aniversário, {nome}! 🎂🎉 Preparamos um presente: 15% OFF hoje com o cupom CLIENTEVIP."),
        ("Confirmação de pedido", "E-mail", "Olá, {nome}! Recebemos seu pedido e já estamos preparando tudo com carinho. Acompanhe pelo WhatsApp."),
    ]:
        conn.execute("INSERT INTO message_templates(company_id,name,channel,content,created_at) VALUES(?,?,?,?,?)", (cid, name, channel, content, now()))
    # Pedidos ultimos 30 dias (deterministicos)
    rng = random.Random(42)
    cust_names = [c[0] for c in customers]
    for d in range(30, -1, -1):
        date = datetime.date.today() - datetime.timedelta(days=d)
        n = rng.choice([0, 1, 1, 2, 2, 3, 4]) if d > 2 else rng.choice([1, 2, 3])
        for _ in range(n):
            pi = rng.randrange(len(products))
            qty = rng.choice([1, 1, 1, 2, 3, 5, 10])
            total = round(products[pi][2] * qty, 2)
            profit = round((products[pi][2] - products[pi][3]) * qty, 2)
            cur = conn.execute("INSERT INTO orders(company_id,customer_name,total,profit,status,channel,coupon,created_at) VALUES(?,?,?,?,?,?,?,?)",
                               (cid, rng.choice(cust_names), total, profit, rng.choice(["pago", "pago", "entregue", "pago"]), rng.choice(["Loja", "WhatsApp", "Instagram", "Loja"]), rng.choice(["", "", "BEMVINDO10", "CHOCOLATE10"]), f"{date.isoformat()}T{rng.randint(8,20):02d}:{rng.randint(10,59):02d}:00"))
            conn.execute("INSERT INTO order_items(company_id,order_id,product_id,product_name,qty,price) VALUES(?,?,?,?,?,?)", (cid, cur.lastrowid, pids[pi], products[pi][0], qty, products[pi][2]))
    for name, phone, items, total, days_ago in [("Camila Duarte", "(81) 98888-1010", "Caixa 12 Bombons x1", 49.9, 2), ("Marcos Vinícius", "(81) 98888-1007", "Caixa Premium 24 x1", 89.9, 1), ("Fernanda Lima", "(81) 98888-1003", "Kit Presente Encanto x1", 119.9, 4)]:
        conn.execute("INSERT INTO carts(company_id,customer_name,phone,items,total,status,stage,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                     (cid, name, phone, items, total, "abandonado", 0, (datetime.date.today() - datetime.timedelta(days=days_ago)).isoformat(), now()))
    for i, (title, channel, days) in enumerate([("Post Caixa 12 — presente perfeito", "Instagram", 0), ("Story bastidores da produção", "Instagram Stories", 1), ("WhatsApp: condição da semana (base consentida)", "WhatsApp", 2), ("Reels: abrindo a Caixa Premium", "Reels", 3), ("E-mail: novidades e cupom VIP", "E-mail", 5)]):
        conn.execute("INSERT INTO campaign_contents(company_id,title,channel,content,scheduled_at,status,product_id,created_at) VALUES(?,?,?,?,?,?,?,?)",
                     (cid, title, channel, pack["instagram_post"] if i == 0 else "Conteúdo gerado pelo Content Studio IA — revise antes de publicar.", (datetime.date.today() + datetime.timedelta(days=days)).isoformat() + "T10:00", "agendado", pids[1], now()))
    conn.execute("INSERT INTO proposals(company_id,customer_name,title,total,discount,deadline,conditions,status,content,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                 (cid, "Hotel Boa Viagem", "Proposta — Kits de boas-vindas para hóspedes VIP", 2400, 10, "7 dias", "Pagamento 50% na confirmação e 50% na entrega. Entrega em Recife.", "enviada", "Proposta profissional gerada pela IA: 30 Kits Corporativos com cartão personalizado do hotel.", now()))
    for pid, cname, rating, comment in [(pids[1], "Ana Beatriz Souza", 5, "A caixa é linda e os bombons são deliciosos! Virou meu presente oficial."), (pids[2], "Luciana Prado", 5, "Embalagem impecável, presente perfeito."), (pids[4], "Roberto Alves", 5, "Usamos nos brindes da empresa, todo mundo elogiou.")]:
        conn.execute("INSERT INTO reviews(company_id,product_id,customer_name,rating,comment,created_at) VALUES(?,?,?,?,?,?)", (cid, pid, cname, rating, comment, now()))
    notify(conn, cid, "Bem-vindo ao ProdutoVenda IA 🚀", "Sua Central de Vendas IA está pronta. Experimente perguntar ao Sales Agent: 'Quero vender mais esta semana'.", "success")
    notify(conn, cid, "3 carrinhos abandonados", "Ative a automação de recuperação para tentar recuperar essas vendas.", "warning")
    ai_log(conn, cid, "seed", "Base demonstrativa de chocolates criada")
    log_audit(conn, cid, demo_user, "seed", "Dados demonstrativos criados")
    conn.commit()

def init_db():
    conn = db()
    conn.executescript(SCHEMA)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(messages)")]
    if "external_id" not in cols:
        conn.execute("ALTER TABLE messages ADD COLUMN external_id TEXT DEFAULT ''")
    pcols = [r[1] for r in conn.execute("PRAGMA table_info(payments)")]
    if "external_reference" not in pcols:
        conn.execute("ALTER TABLE payments ADD COLUMN external_reference TEXT DEFAULT ''")
    prcols = [r[1] for r in conn.execute("PRAGMA table_info(products)")]
    if "image" not in prcols:
        conn.execute("ALTER TABLE products ADD COLUMN image TEXT DEFAULT ''")
    stcols = [r[1] for r in conn.execute("PRAGMA table_info(store_settings)")]
    if "allow_backorder" not in stcols:  # vender itens "sob encomenda" mesmo com estoque zerado
        conn.execute("ALTER TABLE store_settings ADD COLUMN allow_backorder INTEGER DEFAULT 0")
    for target in INDEXES:  # depois das migrações, para os índices apontarem para colunas existentes
        name = "idx_" + re.sub(r"[^a-z0-9]+", "_", target.lower()).strip("_")
        conn.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {target}")
    purge_expired(conn)
    conn.commit()
    seed(conn)
    conn.close()

def purge_expired(conn):
    """Remove sessões/tokens vencidos (higiene do banco em execuções longas)."""
    try:
        conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (now(),))
        conn.execute("DELETE FROM password_resets WHERE expires_at <= ? OR used=1", (now(),))
        conn.commit()
    except sqlite3.DatabaseError:
        pass

# ---------------------------------------------------------------- HTTP helpers
LOGIN_ATTEMPTS = {}
RATE_BUCKETS = {}
RATE_LOCK = threading.Lock()

def rate_limit_bucket(key, limit, window_seconds):
    """Janela deslizante em memória. Retorna True se a requisição é permitida."""
    now_ts = time.monotonic()
    with RATE_LOCK:
        hits = [t for t in RATE_BUCKETS.get(key, []) if now_ts - t < window_seconds]
        allowed = len(hits) < limit
        if allowed:
            hits.append(now_ts)
        RATE_BUCKETS[key] = hits
        if len(RATE_BUCKETS) > 5000:  # poda simples de memória
            for k in [k for k, v in RATE_BUCKETS.items() if not v][:2000]:
                RATE_BUCKETS.pop(k, None)
    return allowed

def rate_limited(key):
    now_ts = datetime.datetime.now().timestamp()
    attempts = [t for t in LOGIN_ATTEMPTS.get(key, []) if now_ts - t < 900]
    LOGIN_ATTEMPTS[key] = attempts
    if len(LOGIN_ATTEMPTS) > 5000:
        LOGIN_ATTEMPTS.clear()
    return len(attempts) >= 10

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"          # keep-alive (o Content-Length é sempre enviado)
    server_version = "ProdutoVendaIA/" + APP_VERSION
    timeout = 60                            # conexões ociosas são liberadas (sem thread presa no keep-alive)
    _request_count = 0
    _buffer = None                          # resposta pendente da API (ver _defer_response)
    _status = None

    def log_message(self, *args):
        pass

    def log_error(self, *args):
        pass

    def _is_https(self):
        proto = (self.headers.get("X-Forwarded-Proto") or "").split(",")[0].strip().lower()
        if proto:
            return proto == "https"
        return bool(PUBLIC_URL.startswith("https://"))

    def _security_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline'; "
                         "script-src 'self' 'unsafe-inline'; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'")
        if self._is_https():
            self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")

    # Dentro de uma requisição de API a resposta é montada em memória e só é enviada
    # depois do commit (ou rollback) da transação. Sem isso, o cliente podia ler a
    # resposta e disparar a próxima chamada antes dos dados estarem gravados.
    def _defer_response(self, writer, *args, **kwargs):
        if self._buffer is None:      # fora da API (arquivos estáticos): escreve direto
            return False
        if self._buffer:
            print("[aviso] mais de uma resposta para a mesma requisição — mantida a primeira", file=sys.stderr, flush=True)
            return True
        self._buffer.append((writer, args, kwargs))
        return True

    def send_json(self, data, status=200):
        self._status = status
        if self._defer_response(self._write_json, data, status):
            return
        self._write_json(data, status)

    def _write_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._security_headers()
        self.end_headers()
        self.wfile.write(body)

    def send_download(self, filename, content, content_type="text/csv; charset=utf-8"):
        self._status = 200
        if self._defer_response(self._write_download, filename, content, content_type):
            return
        self._write_download(filename, content, content_type)

    def _write_download(self, filename, content, content_type="text/csv; charset=utf-8"):
        body = content.encode("utf-8") if isinstance(content, str) else content
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(body)))
        self._security_headers()
        self.end_headers()
        self.wfile.write(body)

    def send_text(self, text, status=200):
        self._status = status
        if self._defer_response(self._write_text, text, status):
            return
        self._write_text(text, status)

    def _write_text(self, text, status=200):
        body = str(text).encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._security_headers()
        self.end_headers()
        self.wfile.write(body)

    def base_url(self):
        """URL pública do sistema. PV_PUBLIC_URL tem prioridade — o header Host nunca é usado
        para montar links (evita host header injection em e-mails e back_urls de pagamento)."""
        if PUBLIC_URL:
            return PUBLIC_URL
        host = (self.headers.get("Host") or "localhost:8000").strip()
        if not re.match(r"^[A-Za-z0-9.\-]+(:\d{1,5})?$", host):
            host = "localhost:8000"
        proto = (self.headers.get("X-Forwarded-Proto") or "http").split(",")[0].strip().lower()
        if proto not in ("http", "https"):
            proto = "http"
        return f"{proto}://{host}"

    def client_ip(self):
        fwd = (self.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
        return fwd or (self.client_address[0] if self.client_address else "desconhecido")

    def allowed(self, scope, limit, window_seconds=900, ident=None):
        """Rate limit por IP (+ identificador opcional). Responde 429 e devolve False quando estoura."""
        key = f"{scope}:{ident or self.client_ip()}"
        if not rate_limit_bucket(key, limit, window_seconds):
            self.send_json({"error": "Muitas requisições em sequência. Aguarde alguns instantes e tente novamente."}, 429)
            return False
        return True

    def body_too_large(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length > MAX_BODY_BYTES:
            self.close_connection = True  # não lemos o corpo: encerra a conexão para não corromper o keep-alive
            self.send_json({"error": f"Conteúdo muito grande (limite de {MAX_BODY_BYTES // (1024 * 1024)} MB)."}, 413)
            return True
        return False

    def body_json(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode() or "{}")
        except Exception:
            return {}

    def auth(self, conn):
        header = self.headers.get("Authorization") or ""
        if not header.startswith("Bearer "):
            return None, None
        token_hash = hashlib.sha256(header[7:].encode()).hexdigest()
        row = conn.execute("SELECT u.*, c.name company_name FROM sessions s JOIN users u ON u.id=s.user_id JOIN companies c ON c.id=u.company_id WHERE s.token_hash=? AND s.expires_at>?", (token_hash, now())).fetchone()
        if not row:
            return None, None
        company = conn.execute("SELECT * FROM companies WHERE id=?", (row["company_id"],)).fetchone()
        return row, company

    def require_auth(self, conn):
        user, company = self.auth(conn)
        if not user:
            self.send_json({"error": "Não autenticado. Faça login novamente."}, 401)
            return None, None
        return user, company

    # ---------- routing
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        if path.startswith("/api/"):
            return self.api("GET", path, query, {})
        return self.serve_static(path)

    def do_HEAD(self):
        """Monitoramento/uptime costuma usar HEAD — responde cabeçalhos sem corpo."""
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self.send_response(405)
            self.send_header("Allow", "GET, POST, PUT, DELETE")
            self.send_header("Content-Length", "0")
            self._security_headers()
            self.end_headers()
            return
        path = parsed.path
        file_path = os.path.join(STATIC, "index.html") if path in ("", "/") else os.path.normpath(os.path.join(STATIC, path.lstrip("/")))
        if not file_path.startswith(STATIC) or not os.path.isfile(file_path):
            file_path = os.path.join(STATIC, "index.html")
        ext = os.path.splitext(file_path)[1]
        ctype = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "application/javascript; charset=utf-8"}.get(ext, "text/plain")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(os.path.getsize(file_path)))
        self._security_headers()
        self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path.startswith("/api/"):
            if self.body_too_large():
                return
            return self.api("POST", parsed.path, {}, self.body_json())
        self.close_connection = True
        self.send_json({"error": "not found"}, 404)

    def do_PUT(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path.startswith("/api/"):
            if self.body_too_large():
                return
            return self.api("PUT", parsed.path, {}, self.body_json())
        self.close_connection = True
        self.send_json({"error": "not found"}, 404)

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path.startswith("/api/"):
            return self.api("DELETE", parsed.path, {}, {})
        self.close_connection = True
        self.send_json({"error": "not found"}, 404)

    def send_html(self, content, status=200, cache="public, max-age=120"):
        return self.send_response_body(content, "text/html; charset=utf-8", status, cache)

    def send_response_body(self, content, content_type, status=200, cache="public, max-age=120"):
        body = content.encode("utf-8") if isinstance(content, str) else content
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self._security_headers()
        self.end_headers()
        self.wfile.write(body)

    def _public_stores(self):
        conn = db()
        try:
            return [dict(r) for r in conn.execute(
                "SELECT c.slug FROM companies c WHERE EXISTS (SELECT 1 FROM products p WHERE p.company_id=c.id AND p.status='ativo') ORDER BY c.id LIMIT 2000")]
        finally:
            conn.close()

    def serve_public_store(self, slug, product_id=None):
        conn = db()
        try:
            company = conn.execute("SELECT * FROM companies WHERE slug=?", (slug,)).fetchone()
            if not company:
                return self.send_html(
                    '<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8"><title>Loja não encontrada</title></head>'
                    '<body style="font-family:system-ui;text-align:center;padding:80px 20px;background:#0f172a;color:#e2e8f0">'
                    '<h1>🔍 Loja não encontrada</h1><p>Este link pode ter sido alterado ou a loja foi desativada.</p>'
                    f'<p><a style="color:#c4b5fd" href="{esc_html(self.base_url())}">Ir para a página inicial</a></p></body></html>', 404, "no-cache")
            settings_row = conn.execute("SELECT * FROM store_settings WHERE company_id=?", (company["id"],)).fetchone()
            settings = dict(settings_row) if settings_row else {}
            products = [dict(r) for r in conn.execute("SELECT * FROM products WHERE company_id=? AND status='ativo' ORDER BY sales DESC, id DESC", (company["id"],))]
            reviews = [dict(r) for r in conn.execute("SELECT * FROM reviews WHERE company_id=? ORDER BY id DESC LIMIT 3", (company["id"],))]
            focus = next((p for p in products if product_id and p["id"] == product_id), None)
            if product_id and not focus:
                focus = None
            page = store_page_html(company, settings, products, self.base_url(), focus=focus, reviews=reviews)
            return self.send_html(page)
        finally:
            conn.close()

    def serve_static(self, path):
        if path == "/robots.txt":
            base = self.base_url()
            return self.send_text(f"User-agent: *\nAllow: /loja/\nDisallow: /api/\nDisallow: /uploads/\nSitemap: {base}/sitemap.xml\n")
        if path == "/sitemap.xml":
            base = self.base_url()
            urls = [f"<url><loc>{esc_html(base)}/loja/{esc_html(r['slug'])}</loc></url>"
                    for r in self._public_stores()]
            body = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + "".join(urls) + "</urlset>"
            return self.send_response_body(body, "application/xml; charset=utf-8")
        m = re.match(r"^/loja/([\w-]{1,80})(?:/produto/(\d+))?/?$", path)
        if m:
            return self.serve_public_store(m.group(1), to_int(m.group(2), 0) or None)
        if path.startswith("/uploads/"):
            file_path = os.path.normpath(os.path.join(UPLOAD_DIR, path[len("/uploads/"):]))
            if not file_path.startswith(os.path.normpath(UPLOAD_DIR)) or not os.path.isfile(file_path):
                return self.send_json({"error": "Arquivo não encontrado"}, 404)
            ext = os.path.splitext(file_path)[1].lower()
            ctype = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(ext, "application/octet-stream")
            with open(file_path, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "public, max-age=86400")
            self._security_headers()
            self.end_headers()
            self.wfile.write(data)
            return
        if path == "/" or path == "":
            path = "/index.html"
        file_path = os.path.normpath(os.path.join(STATIC, path.lstrip("/")))
        if not file_path.startswith(STATIC) or not os.path.isfile(file_path):
            file_path = os.path.join(STATIC, "index.html")
        ext = os.path.splitext(file_path)[1]
        ctype = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "application/javascript; charset=utf-8"}.get(ext, "text/plain")
        with open(file_path, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache" if ext == ".html" else "public, max-age=3600")
        self._security_headers()
        self.end_headers()
        self.wfile.write(data)

    # ---------- API
    def api(self, method, path, query, data):
        Handler._request_count += 1
        if Handler._request_count % 500 == 0:          # higiene periódica em execuções longas
            conn0 = db()
            try:
                purge_expired(conn0)
            finally:
                conn0.close()
        conn = db()
        self._status = None
        self._buffer = []
        try:
            self.route(conn, method, path, query, data)
            status = self._status or 200
            # Só confirma a transação quando a resposta foi de sucesso: um erro no meio
            # do fluxo não deixa escritas parciais para trás.
            if status >= 400:
                conn.rollback()
            else:
                conn.commit()
        except sqlite3.DatabaseError as e:
            conn.rollback()
            self._buffer = None
            print(f"[db] {method} {path}: {e}", file=sys.stderr, flush=True)
            return self.send_json({"error": "Banco de dados ocupado ou indisponível no momento. Tente novamente em instantes."}, 503)
        except Exception as e:
            conn.rollback()
            self._buffer = None
            print(f"[erro] {method} {path}: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
            return self.send_json({"error": "Erro interno no servidor. Tente novamente; se persistir, avise o suporte."}, 500)
        finally:
            conn.close()
            # Transação encerrada: agora sim a resposta pode ir para o cliente.
            pending, self._buffer = self._buffer or [], None
            for writer, args, kwargs in pending:
                try:
                    writer(*args, **kwargs)
                except (BrokenPipeError, ConnectionResetError) as e:
                    print(f"[aviso] cliente desconectou antes da resposta ({method} {path}): {e}", file=sys.stderr, flush=True)

    def route(self, conn, method, path, query, data):
        # Public store
        m = re.match(r"^/api/public/store/([\w-]+)$", path)
        if m and method == "GET":
            company = conn.execute("SELECT * FROM companies WHERE slug=?", (m.group(1),)).fetchone()
            if not company:
                return self.send_json({"error": "Loja não encontrada"}, 404)
            settings = conn.execute("SELECT * FROM store_settings WHERE company_id=?", (company["id"],)).fetchone()
            products = [dict(r) for r in conn.execute("SELECT * FROM products WHERE company_id=? AND status='ativo' ORDER BY sales DESC", (company["id"],))]
            reviews = [dict(r) for r in conn.execute("SELECT * FROM reviews WHERE company_id=? ORDER BY id DESC LIMIT 6", (company["id"],))]
            mp_cfg = integ.get_config(conn, company["id"], "mercadopago", active_only=True)
            mp_on = integ.configured_status("mercadopago", mp_cfg)[0]
            return self.send_json({"company": dict(company), "settings": dict(settings) if settings else {}, "products": products, "reviews": reviews,
                                   "payments": {"mercadopago": mp_on, "pix": mp_on, "card": mp_on}})
        m = re.match(r"^/api/public/store/([\w-]+)/checkout$", path)
        if m and method == "POST":
            if not self.allowed("checkout", 100, 600):
                return
            company = conn.execute("SELECT * FROM companies WHERE slug=?", (m.group(1),)).fetchone()
            if not company:
                return self.send_json({"error": "Loja não encontrada"}, 404)
            return self.public_checkout(conn, company, data)
        m = re.match(r"^/api/public/store/([\w-]+)/cart$", path)
        if m and method == "POST":
            if not self.allowed("carrinho", 120, 600):
                return
            company = conn.execute("SELECT * FROM companies WHERE slug=?", (m.group(1),)).fetchone()
            if not company:
                return self.send_json({"error": "Loja não encontrada"}, 404)
            items = data.get("items") or []
            if not items:
                return self.send_json({"error": "Carrinho vazio."}, 400)
            if not (data.get("phone") or "").strip():
                return self.send_json({"error": "Informe seu WhatsApp para salvar o carrinho e receber o lembrete (só sobre este pedido)."}, 400)
            total, labels = 0.0, []
            for it in items:
                p = conn.execute("SELECT * FROM products WHERE id=? AND company_id=? AND status='ativo'", (it.get("product_id"), company["id"])).fetchone()
                if not p:
                    continue
                qty = max(int(it.get("qty") or 1), 1)
                total += float(p["price"]) * qty
                labels.append(f"{p['name']} x{qty}")
            cur = conn.execute("INSERT INTO carts(company_id,customer_name,phone,items,total,status,stage,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                               (company["id"], data.get("customer_name") or "Cliente da loja", data.get("phone", ""), ", ".join(labels), round(total, 2), "abandonado", 0, now(), now()))
            return self.send_json({"ok": True, "cart_id": cur.lastrowid, "total": round(total, 2), "message": "Carrinho salvo! 💾 Se você não concluir, a loja poderá te lembrar pelo WhatsApp (somente sobre este pedido)."}, 201)
        m = re.match(r"^/api/public/store/([\w-]+)/review$", path)
        if m and method == "POST":
            if not self.allowed("avaliacao", 40, 600):
                return
            company = conn.execute("SELECT * FROM companies WHERE slug=?", (m.group(1),)).fetchone()
            if not company:
                return self.send_json({"error": "Loja não encontrada"}, 404)
            rating = max(1, min(5, int(data.get("rating") or 5)))
            if not (data.get("customer_name") or "").strip() or not (data.get("comment") or "").strip():
                return self.send_json({"error": "Informe seu nome e um comentário para avaliar."}, 400)
            product = conn.execute("SELECT * FROM products WHERE id=? AND company_id=?", (data.get("product_id"), company["id"])).fetchone()
            if not product:
                return self.send_json({"error": "Produto não encontrado"}, 404)
            cur = conn.execute("INSERT INTO reviews(company_id,product_id,customer_name,rating,comment,created_at) VALUES(?,?,?,?,?,?)",
                               (company["id"], product["id"], data["customer_name"].strip()[:80], rating, data["comment"].strip()[:500], now()))
            return self.send_json({"ok": True, "review_id": cur.lastrowid, "message": "Obrigado pela avaliação! ⭐ Ela já aparece na loja."}, 201)

        # ---------------- Webhooks publicos (Meta / Mercado Pago) ----------------
        if path == "/api/webhooks/whatsapp" and method == "GET":
            def q1(key):
                v = query.get(key)
                return (v[0] if isinstance(v, list) and v else v) or ""
            mode, token, challenge = q1("hub.mode"), q1("hub.verify_token"), q1("hub.challenge")
            if mode == "subscribe" and token:
                rows = conn.execute("SELECT company_id, config FROM integrations WHERE provider='whatsapp'").fetchall()
                for r in rows:
                    try:
                        cfg = json.loads(r["config"] or "{}")
                    except Exception:
                        cfg = {}
                    saved_verify = integ.decrypt_field("whatsapp", "verify_token", cfg.get("verify_token") or "")
                    if saved_verify and saved_verify == token:
                        return self.send_text(challenge, 200)
            return self.send_text("Forbidden", 403)
        if path == "/api/webhooks/whatsapp" and method == "POST":
            return self.webhook_whatsapp(conn, data)
        if path in ("/api/webhooks/mercadopago", "/api/webhooks/mercadopago/") and method in ("GET", "POST"):
            pid = ""
            if method == "GET":
                v = query.get("data.id") or query.get("id")
                pid = (v[0] if isinstance(v, list) and v else v) or ""
            else:
                pid = str(((data.get("data") or {}).get("id")) or data.get("id") or "")
            return self.webhook_mercadopago(conn, pid)

        # Health publico (monitoramento/deploy)
        if path == "/api/health" and method == "GET":
            try:
                conn.execute("SELECT 1")
                conn.execute("SELECT COUNT(*) FROM companies")
                db_ok = True
            except Exception:
                db_ok = False
            return self.send_json({"status": "ok" if db_ok else "degraded", "app": "ProdutoVenda IA", "version": APP_VERSION,
                                   "db": "ok" if db_ok else "erro", "time": now(),
                                   "uptime_seconds": int(time.time() - STARTED_AT), "public_url": PUBLIC_URL or self.base_url()})

        # Auth
        if path == "/api/auth/register" and method == "POST":
            if not self.allowed("register", 10, 3600):
                return
            return self.register(conn, data)
        if path == "/api/auth/login" and method == "POST":
            if not self.allowed("login-ip", 60, 900):
                return
            return self.login(conn, data)
        if path == "/api/auth/forgot" and method == "POST":
            if not self.allowed("forgot", 15, 900):
                return
            email = (data.get("email") or "").strip().lower()
            user_row = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
            generic = {"ok": True, "message": "Se existir uma conta com este e-mail, enviamos um link de redefinição (válido por 1 hora). Verifique também a caixa de spam."}
            if not user_row:
                return self.send_json(generic)
            token = secrets.token_urlsafe(40)
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            expires = (datetime.datetime.now() + datetime.timedelta(hours=1)).isoformat(timespec="seconds")
            conn.execute("INSERT INTO password_resets(user_id,token_hash,expires_at,used,created_at) VALUES(?,?,?,?,?)", (user_row["id"], token_hash, expires, 0, now()))
            link = f"{self.base_url()}/?reset_token={token}#/login"
            smtp_cfg = integ.get_config(conn, user_row["company_id"], "smtp", active_only=True)
            if integ.configured_status("smtp", smtp_cfg)[0]:
                try:
                    integ.smtp_send(smtp_cfg, email, "Redefinir sua senha — ProdutoVenda IA",
                                    f"Olá!\n\nRecebemos um pedido para redefinir a senha da sua conta.\nUse este link (válido por 1 hora):\n{link}\n\nSe não foi você, ignore este e-mail.")
                    log_audit(conn, user_row["company_id"], user_row["id"], "password_reset_sent", email)
                    return self.send_json(generic)
                except IntegrationError as e:
                    return self.send_json({"error": f"Não foi possível enviar o e-mail de redefinição: {e}"}, 502)
            log_audit(conn, user_row["company_id"], user_row["id"], "password_reset_created", email)
            if os.environ.get("PV_ALLOW_RESET_LINK") == "1":
                return self.send_json({**generic, "reset_link": link, "message": generic["message"] + " (Modo local: link exibido porque o SMTP não está configurado.)"})
            return self.send_json({**generic, "message": generic["message"] + " Dica: configure o SMTP em Integrações para o envio automático do link."})
        if path == "/api/auth/reset" and method == "POST":
            if not self.allowed("reset", 20, 900):
                return
            token = data.get("token") or ""
            password = data.get("password") or ""
            if len(password) < 6:
                return self.send_json({"error": "A nova senha precisa de pelo menos 6 caracteres."}, 400)
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            row = conn.execute("SELECT * FROM password_resets WHERE token_hash=? AND used=0 AND expires_at>?", (token_hash, now())).fetchone()
            if not row:
                return self.send_json({"error": "Link inválido ou expirado. Solicite uma nova redefinição."}, 400)
            ph, salt = hash_pass(password)
            conn.execute("UPDATE users SET pass_hash=?, salt=? WHERE id=?", (ph, salt, row["user_id"]))
            conn.execute("UPDATE password_resets SET used=1 WHERE id=?", (row["id"],))
            conn.execute("DELETE FROM sessions WHERE user_id=?", (row["user_id"],))
            return self.send_json({"ok": True, "message": "Senha redefinida! Faça login com a nova senha."})

        user, company = self.require_auth(conn)
        if not user:
            return
        cid = user["company_id"]

        if path == "/api/auth/logout" and method == "POST":
            header = self.headers.get("Authorization") or ""
            if header.startswith("Bearer "):
                conn.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(header[7:].encode()).hexdigest(),))
            return self.send_json({"ok": True, "message": "Sessão encerrada."})

        if path == "/api/auth/me" and method == "GET":
            plan = conn.execute("SELECT * FROM plans WHERE id=?", (company["plan_id"],)).fetchone()
            return self.send_json({"user": {"id": user["id"], "name": user["name"], "email": user["email"], "role": user["role"], "is_platform_admin": user["is_platform_admin"]},
                                   "company": dict(company), "plan": dict(plan) if plan else None})

        if path == "/api/auth/onboarding" and method == "POST":
            conn.execute("UPDATE companies SET name=?, segment=?, city=?, region=?, whatsapp=?, goal_monthly=?, onboarded=1 WHERE id=?",
                         (data.get("company_name") or company["name"], data.get("segment") or company["segment"], data.get("city", ""), data.get("region", ""), data.get("whatsapp", ""), float(data.get("goal_monthly") or 6000), cid))
            conn.execute("UPDATE store_settings SET store_name=? WHERE company_id=?", (data.get("company_name") or company["name"], cid))
            log_audit(conn, cid, user["id"], "onboarding", "Onboarding concluído")
            return self.send_json({"ok": True, "message": "Seu sistema de vendas está pronto. 🚀"})

        if path == "/api/dashboard" and method == "GET":
            return self.dashboard(conn, company)
        if path == "/api/notifications" and method == "GET":
            rows = [dict(r) for r in conn.execute("SELECT * FROM notifications WHERE company_id=? ORDER BY id DESC LIMIT 12", (cid,))]
            return self.send_json({"notifications": rows})
        if path == "/api/ai/chat" and method == "POST":
            conn.execute("INSERT INTO ai_conversations(company_id,user_id,role,content,created_at) VALUES(?,?,?,?,?)", (cid, user["id"], "user", data.get("message", ""), now()))
            resp = ai_chat_reply(data.get("message", ""), conn, company, user)
            conn.execute("INSERT INTO ai_conversations(company_id,user_id,role,content,created_at) VALUES(?,?,?,?,?)", (cid, user["id"], "assistant", resp["reply"], now()))
            ai_log(conn, cid, "chat", data.get("message", "")[:120])
            return self.send_json(resp)
        if path == "/api/ai/history" and method == "GET":
            rows = [dict(r) for r in conn.execute("SELECT * FROM ai_conversations WHERE company_id=? ORDER BY id DESC LIMIT 30", (cid,))]
            return self.send_json({"history": list(reversed(rows))})

        # ---------------- Integracoes reais ----------------
        if path == "/api/integrations" and method == "GET":
            items = integ.list_integrations(conn, cid)
            for it in items:
                if it.get("webhook_path"):
                    it["webhook_url"] = self.base_url() + it["webhook_path"]
            return self.send_json({"integrations": items, "base_url": self.base_url()})
        m = re.match(r"^/api/integrations/([a-z_]+)$", path)
        if m and method == "PUT":
            provider = m.group(1)
            if provider not in integ.PROVIDERS:
                return self.send_json({"error": "Provedor desconhecido."}, 404)
            try:
                integ.save_config(conn, cid, provider, data)
            except IntegrationError as e:
                return self.send_json({"error": str(e)}, e.status)
            log_audit(conn, cid, user["id"], "integration_save", provider)
            row = integ.integration_row(conn, cid, provider)
            item = integ.public_config(provider, integ.get_config(conn, cid, provider), row)
            if item.get("webhook_path"):
                item["webhook_url"] = self.base_url() + item["webhook_path"]
            return self.send_json({"integration": item, "message": f"{item['name']}: configuração salva (segredos ficam só no servidor, sempre mascarados)." })
        m = re.match(r"^/api/integrations/([a-z_]+)/test$", path)
        if m and method == "POST":
            provider = m.group(1)
            if provider not in integ.PROVIDERS:
                return self.send_json({"error": "Provedor desconhecido."}, 404)
            config = integ.get_config(conn, cid, provider)
            try:
                detail = integ.test_connection(provider, config)
                integ.record_test(conn, cid, provider, "sucesso", detail)
                log_audit(conn, cid, user["id"], "integration_test_ok", provider)
                return self.send_json({"ok": True, "detail": detail, "message": "✅ Conexão real confirmada: " + detail})
            except IntegrationError as e:
                detail = integ.provider_error_detail(e.detail) or str(e)
                integ.record_test(conn, cid, provider, "falha", f"{e} {detail}")
                return self.send_json({"error": f"Teste de conexão falhou: {e} {detail}".strip()}, e.status if e.status != 502 else 502)
        if path == "/api/payments" and method == "GET":
            rows = [dict(r) for r in conn.execute("SELECT * FROM payments WHERE company_id=? ORDER BY id DESC LIMIT 50", (cid,))]
            for r in rows:
                r.pop("raw", None)
            return self.send_json({"payments": rows})
        if path == "/api/payments/create" and method == "POST":
            return self.payments_create(conn, company, user, data)
        m = re.match(r"^/api/payments/(\d+)/refresh$", path)
        if m and method == "POST":
            payment = conn.execute("SELECT * FROM payments WHERE id=? AND company_id=?", (m.group(1), cid)).fetchone()
            if not payment:
                return self.send_json({"error": "Pagamento não encontrado"}, 404)
            config = integ.get_config(conn, cid, "mercadopago", active_only=True)
            try:
                raw = integ.mp_get_payment(config, payment["external_id"])
            except IntegrationError as e:
                return self.send_json({"error": f"{e} {integ.provider_error_detail(e.detail)}".strip()}, e.status)
            self.apply_mp_status(conn, payment, raw.get("status", payment["status"]), raw)
            updated = conn.execute("SELECT * FROM payments WHERE id=?", (payment["id"],)).fetchone()
            return self.send_json({"payment": {k: v for k, v in dict(updated).items() if k != "raw"}})
        m = re.match(r"^/api/email-campaigns/(\d+)/send$", path)
        if m and method == "POST":
            camp = conn.execute("SELECT * FROM email_campaigns WHERE id=? AND company_id=?", (m.group(1), cid)).fetchone()
            if not camp:
                return self.send_json({"error": "Campanha não encontrada"}, 404)
            smtp_cfg = integ.get_config(conn, cid, "smtp", active_only=True)
            if not integ.configured_status("smtp", smtp_cfg)[0]:
                return self.send_json({"error": "SMTP não configurado/ativo. Configure em Admin & Planos → Integrações para enviar de verdade."}, 400)
            targets = conn.execute("SELECT * FROM customers WHERE company_id=? AND consent=1 AND email LIKE '%@%' LIMIT 500", (cid,)).fetchall()
            sent, errors = 0, []
            for t in targets:
                try:
                    integ.smtp_send(smtp_cfg, t["email"], camp["subject"], (camp["content"] or "").replace("{nome}", (t["name"] or "").split(" ")[0]))
                    sent += 1
                except IntegrationError as e:
                    errors.append(str(e))
                    if sent == 0 and len(errors) >= 3:
                        break
            conn.execute("UPDATE email_campaigns SET sent=sent+?, status='enviada' WHERE id=?", (sent, camp["id"]))
            log_audit(conn, cid, user["id"], "email_campaign_send", f"{camp['subject']}: {sent} enviados")
            if sent == 0 and errors:
                return self.send_json({"error": f"Nenhum e-mail enviado: {errors[0]}"}, 502)
            return self.send_json({"ok": True, "sent": sent, "message": f"✉️ {sent} e-mail(s) enviados via SMTP para clientes que autorizaram contato." + (f" {len(errors)} falha(s)." if errors else "")})
        if path == "/api/admin/export" and method == "GET":
            tables = ["products", "customers", "leads", "opportunities", "orders", "order_items", "coupons", "campaigns", "campaign_contents",
                      "automations", "proposals", "reviews", "payments", "email_campaigns", "carts", "messages"]
            export = {"app": "ProdutoVenda IA", "version": APP_VERSION, "exported_at": now(), "company": dict(company), "data": {}}
            for t in tables:
                try:
                    export["data"][t] = [dict(r) for r in conn.execute(f"SELECT * FROM {t} WHERE company_id=? ORDER BY id", (cid,))]
                except Exception:
                    export["data"][t] = []
            integ_summary = [{"provider": i["provider"], "name": i["name"], "status": i["status"]} for i in integ.list_integrations(conn, cid)]
            export["integrations"] = integ_summary
            log_audit(conn, cid, user["id"], "data_export", f"{sum(len(v) for v in export['data'].values())} registros")
            return self.send_json(export)
        m = re.match(r"^/api/customers/(\d+)/timeline$", path)
        if m and method == "GET":
            cust = conn.execute("SELECT * FROM customers WHERE id=? AND company_id=?", (m.group(1), cid)).fetchone()
            if not cust:
                return self.send_json({"error": "Cliente não encontrado"}, 404)
            orders = [dict(r) for r in conn.execute("SELECT * FROM orders WHERE company_id=? AND (customer_id=? OR customer_name=?) ORDER BY id DESC LIMIT 30", (cid, cust["id"], cust["name"]))]
            msgs = [dict(r) for r in conn.execute("SELECT * FROM messages WHERE company_id=? AND customer_id=? ORDER BY id DESC LIMIT 30", (cid, cust["id"]))]
            leads = [dict(r) for r in conn.execute("SELECT * FROM leads WHERE company_id=? AND (email=? AND email!='' OR name=?) ORDER BY id DESC LIMIT 10", (cid, cust["email"], cust["name"]))]
            return self.send_json({"customer": dict(cust), "orders": orders, "messages": msgs, "leads": leads})
        if path == "/api/messages" and method == "GET":
            rows = [dict(r) for r in conn.execute("SELECT m.*, c.name customer_name FROM messages m LEFT JOIN customers c ON c.id=m.customer_id WHERE m.company_id=? ORDER BY m.id DESC LIMIT 60", (cid,))]
            return self.send_json({"messages": rows})

        # Generic CRUD resources
        if self.crud(conn, method, path, data, cid, user):
            return

        m = re.match(r"^/api/products/(\d+)/generate-page$", path)
        if m and method == "POST":
            product = conn.execute("SELECT * FROM products WHERE id=? AND company_id=?", (m.group(1), cid)).fetchone()
            if not product:
                return self.send_json({"error": "Produto não encontrado"}, 404)
            page = ai_product_page(product, company)
            conn.execute("UPDATE products SET description=?, ai_page=1, page_data=? WHERE id=?", (page["description"], json.dumps(page, ensure_ascii=False), product["id"]))
            ai_log(conn, cid, "generate_page", product["name"])
            return self.send_json({"page": page, "product": dict(product)})

        m = re.match(r"^/api/products/(\d+)/image$", path)
        if m and method == "POST":
            product = conn.execute("SELECT * FROM products WHERE id=? AND company_id=?", (m.group(1), cid)).fetchone()
            if not product:
                return self.send_json({"error": "Produto não encontrado"}, 404)
            data_url = data.get("image_data") or ""
            match = re.match(r"^data:image/(png|jpeg|jpg|webp);base64,(.+)$", data_url, re.DOTALL)
            if not match:
                return self.send_json({"error": "Envie uma imagem PNG, JPG ou WEBP (campo image_data em base64)."}, 400)
            try:
                raw = base64.b64decode(match.group(2), validate=True)
            except Exception:
                return self.send_json({"error": "Imagem inválida (base64 corrompido)."}, 400)
            if len(raw) > 2_000_000:
                return self.send_json({"error": "Imagem muito grande: máximo 2 MB. Reduza a foto e tente de novo."}, 400)
            if len(raw) < 20:
                return self.send_json({"error": "Imagem inválida (arquivo muito pequeno)."}, 400)
            ext = "png" if match.group(1) == "png" else ("webp" if match.group(1) == "webp" else "jpg")
            folder = os.path.join(UPLOAD_DIR, str(cid))
            os.makedirs(folder, exist_ok=True)
            filename = f"product-{product['id']}-{secrets.token_hex(6)}.{ext}"
            with open(os.path.join(folder, filename), "wb") as f:
                f.write(raw)
            old = product["image"] or ""
            if old.startswith("/uploads/"):
                old_path = os.path.normpath(os.path.join(UPLOAD_DIR, old[len("/uploads/"):]))
                if old_path.startswith(os.path.normpath(UPLOAD_DIR)) and os.path.isfile(old_path):
                    try:
                        os.unlink(old_path)
                    except Exception:
                        pass
            image_url = f"/uploads/{cid}/{filename}"
            conn.execute("UPDATE products SET image=? WHERE id=?", (image_url, product["id"]))
            log_audit(conn, cid, user["id"], "product_image", product["name"])
            return self.send_json({"ok": True, "image": image_url, "message": "Foto do produto atualizada! 📷 Ela já aparece no painel e na loja."})
        m = re.match(r"^/api/products/(\d+)/image$", path)
        if m and method == "DELETE":
            product = conn.execute("SELECT * FROM products WHERE id=? AND company_id=?", (m.group(1), cid)).fetchone()
            if not product:
                return self.send_json({"error": "Produto não encontrado"}, 404)
            conn.execute("UPDATE products SET image='' WHERE id=?", (product["id"],))
            return self.send_json({"ok": True, "message": "Foto removida. O produto volta a usar o ícone."})

        if path == "/api/coupons/suggest" and method == "POST":
            segment = (company["segment"] or "").lower()
            suggestions = [
                {"code": "BEMVINDO10", "type": "percentual", "value": 10, "kind": "primeira compra", "reason": "Converter novos clientes da loja"},
                {"code": "VOLTEI15", "type": "percentual", "value": 15, "kind": "cliente antigo", "reason": "Reativar quem não compra há 60+ dias"},
                {"code": "CLIENTEVIP", "type": "percentual", "value": 15, "kind": "cliente antigo", "min_value": 100, "reason": "Recompensar clientes VIP e elevar ticket"},
                {"code": "OFERTA10", "type": "percentual", "value": 10, "kind": "campanha", "reason": "Campanha da semana do produto mais vendido"},
            ]
            ai_log(conn, cid, "coupon_suggest", "Sugestões de cupons geradas")
            return self.send_json({"suggestions": suggestions})

        if path == "/api/campaigns/generate" and method == "POST":
            product = conn.execute("SELECT * FROM products WHERE id=? AND company_id=?", (data.get("product_id"), cid)).fetchone()
            if not product:
                products = conn.execute("SELECT * FROM products WHERE company_id=? ORDER BY sales DESC LIMIT 1", (cid,)).fetchone()
                product = products
            if not product:
                return self.send_json({"error": "Cadastre um produto primeiro."}, 400)
            pack = ai_campaign_pack(product, data.get("objective", ""), data.get("audience", ""), company)
            cur = conn.execute("INSERT INTO campaigns(company_id,name,product_id,objective,audience,region,channel,status,budget,content,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                               (cid, pack["name"], product["id"], data.get("objective", ""), data.get("audience", ""), data.get("region", ""), data.get("channel", "WhatsApp + Instagram"), "ativa", float(data.get("budget") or 0), json.dumps(pack, ensure_ascii=False), now()))
            # agenda conteudos da campanha por 5 dias
            for i, (title, channel) in enumerate([("Post principal da campanha", "Instagram"), ("Story de bastidores", "Instagram Stories"), ("Mensagem WhatsApp (base consentida)", "WhatsApp"), ("Reels do produto", "Reels"), ("E-mail da campanha", "E-mail")]):
                conn.execute("INSERT INTO campaign_contents(company_id,campaign_id,title,channel,content,scheduled_at,status,product_id,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                             (cid, cur.lastrowid, title, channel, [pack["instagram_post"], pack["story"], pack["whatsapp"], pack["video_script"], pack["email_body"]][i], (datetime.date.today() + datetime.timedelta(days=i)).isoformat() + "T10:00", "agendado", product["id"], now()))
            ai_log(conn, cid, "campaign_generate", pack["name"])
            notify(conn, cid, "Campanha criada pela IA 🎯", pack["name"], "success")
            campaign = conn.execute("SELECT * FROM campaigns WHERE id=?", (cur.lastrowid,)).fetchone()
            return self.send_json({"campaign": dict(campaign), "pack": pack})

        if path == "/api/content/generate" and method == "POST":
            product = conn.execute("SELECT * FROM products WHERE id=? AND company_id=?", (data.get("product_id"), cid)).fetchone()
            if not product:
                return self.send_json({"error": "Selecione um produto."}, 400)
            pack = ai_campaign_pack(product, data.get("objective", ""), data.get("audience", ""), company)
            channel = data.get("channel", "Instagram")
            content_map = {"Instagram": pack["instagram_post"], "Instagram Stories": pack["story"], "Stories": pack["story"], "Reels": pack["video_script"], "WhatsApp": pack["whatsapp"], "E-mail": pack["email_body"], "Facebook": pack["instagram_post"], "Blog": pack["email_body"], "Pinterest": pack["instagram_post"]}
            cur = conn.execute("INSERT INTO campaign_contents(company_id,title,channel,content,scheduled_at,status,product_id,created_at) VALUES(?,?,?,?,?,?,?,?)",
                               (cid, f"{channel} — {product['name']}", channel, content_map.get(channel, pack["instagram_post"]), (data.get("scheduled_at") or (today() + "T10:00")), "agendado", product["id"], now()))
            ai_log(conn, cid, "content_generate", channel)
            return self.send_json({"item": dict(conn.execute("SELECT * FROM campaign_contents WHERE id=?", (cur.lastrowid,)).fetchone()), "pack": pack})

        if path == "/api/prospect" and method == "POST":
            city = data.get("city") or company["city"] or "sua cidade"
            segment_filter = data.get("segment") or "Empresa"
            product_name = data.get("product") or "seu produto"
            # --- Fonte oficial: Google Places API, quando configurada ---
            places_cfg = integ.get_config(conn, cid, "google_places", active_only=True)
            if integ.configured_status("google_places", places_cfg)[0]:
                try:
                    places = integ.places_search(places_cfg, segment_filter, city, 10)
                    created_places = []
                    for pl in places:
                        if conn.execute("SELECT id FROM opportunities WHERE company_id=? AND name=?", (cid, pl["name"])).fetchone():
                            continue
                        cur = conn.execute("INSERT INTO opportunities(company_id,name,company,segment,city,phone,email,site,source,status,potential,notes,last_interaction,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                           (cid, pl["name"], pl["name"], segment_filter, city, pl["phone"], "", pl["site"], "Google Places API (fonte oficial)", "Nova", "Alto" if (pl["rating"] or 0) and float(pl["rating"]) >= 4.5 else "Médio",
                                            f"Endereço: {pl['address']}" + (f" · Avaliação Google: {pl['rating']}★" if pl["rating"] else "") + f" · Potencial para {product_name}. Validar contato pelos canais oficiais; sem spam.", today(), now()))
                        created_places.append(dict(conn.execute("SELECT * FROM opportunities WHERE id=?", (cur.lastrowid,)).fetchone()))
                    ai_log(conn, cid, "prospect_places", f"{segment_filter} em {city}: {len(created_places)} via Google Places")
                    return self.send_json({"created": created_places, "source": "google_places", "message": f"📍 {len(created_places)} novas oportunidades REAIS encontradas via Google Places para {segment_filter} em {city} (as demais já estavam na base). Aborde só por canais oficiais, sem spam."})
                except IntegrationError as e:
                    return self.send_json({"error": f"Google Places falhou: {e} {integ.provider_error_detail(e.detail)}".strip()}, e.status)
            created = []
            bases = [(s, names) for s, names in PROSPECT_BASE if segment_filter in ("", "Todos", s) or segment_filter == "Empresa" and s in ("Empresa", "Loja")]
            if not bases:
                bases = PROSPECT_BASE
            for seg, names in bases:
                for name in names:
                    exists = conn.execute("SELECT id FROM opportunities WHERE company_id=? AND name=?", (cid, name)).fetchone()
                    if exists:
                        continue
                    cur = conn.execute("INSERT INTO opportunities(company_id,name,company,segment,city,phone,email,site,source,status,potential,notes,last_interaction,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                       (cid, name, name, seg, city, "(81) 4002-9" + str(random.randint(100, 999)), "contato@" + slugify(name) + ".com.br", "https://" + slugify(name) + ".com.br", "Prospecção IA (base demonstrativa — conectar API autorizada)", "Nova", random.choice(["Alto", "Médio", "Médio"]), f"Potencial para {product_name}. Validar contato pelos canais oficiais antes de abordar; sem spam.", today(), now()))
                    created.append(dict(conn.execute("SELECT * FROM opportunities WHERE id=?", (cur.lastrowid,)).fetchone()))
            ai_log(conn, cid, "prospect", f"{segment_filter} em {city}: {len(created)} novas")
            return self.send_json({"created": created, "message": f"{len(created)} novas oportunidades geradas para {segment_filter} em {city}. Em produção, conecte uma API autorizada (ex.: Google Places) — nada de scraping ou spam."})

        m = re.match(r"^/api/opportunities/(\d+)/to-crm$", path)
        if m and method == "POST":
            opp = conn.execute("SELECT * FROM opportunities WHERE id=? AND company_id=?", (m.group(1), cid)).fetchone()
            if not opp:
                return self.send_json({"error": "Oportunidade não encontrada"}, 404)
            cur = conn.execute("INSERT INTO leads(company_id,name,company,email,phone,city,segment,source,stage,potential,value,notes,next_action,last_interaction,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                               (cid, opp["name"], opp["company"], opp["email"], opp["phone"], opp["city"], opp["segment"], "Oportunidade IA", "Novo Lead", opp["potential"], 0, opp["notes"], "Fazer primeiro contato (canal oficial, sem spam)", today(), now()))
            conn.execute("UPDATE opportunities SET status='No CRM' WHERE id=?", (opp["id"],))
            return self.send_json({"lead": dict(conn.execute("SELECT * FROM leads WHERE id=?", (cur.lastrowid,)).fetchone())})

        if path == "/api/automations/run" and method == "POST":
            return self.run_automations(conn, company, user)

        if path == "/api/insights" and method == "GET":
            return self.send_json({"insights": self.compute_insights(conn, company)})

        if path == "/api/reports" and method == "GET":
            return self.reports(conn, company)

        if path == "/api/messages/send" and method == "POST":
            customer = conn.execute("SELECT * FROM customers WHERE id=? AND company_id=?", (data.get("customer_id"), cid)).fetchone()
            if not customer:
                return self.send_json({"error": "Cliente não encontrado"}, 404)
            if not customer["consent"]:
                return self.send_json({"error": "LGPD: este cliente não autorizou comunicações comerciais (sem consentimento/opt-in). Registre o consentimento antes de enviar."}, 400)
            content = data.get("content", "")
            channel = data.get("channel", "WhatsApp")
            # --- Envio REAL via integracoes, quando configuradas ---
            if channel == "WhatsApp":
                wa_cfg = integ.get_config(conn, cid, "whatsapp", active_only=True)
                if integ.configured_status("whatsapp", wa_cfg)[0]:
                    try:
                        wamid, _raw = integ.whatsapp_send(wa_cfg, customer["phone"], content, data.get("template_name") or None)
                        cur = conn.execute("INSERT INTO messages(company_id,customer_id,channel,content,status,external_id,created_at) VALUES(?,?,?,?,?,?,?)",
                                           (cid, customer["id"], channel, content, "enviado via WhatsApp Cloud API", wamid, now()))
                        ai_log(conn, cid, "message_send_real", f"WhatsApp para {customer['name']}")
                        return self.send_json({"message": dict(conn.execute("SELECT * FROM messages WHERE id=?", (cur.lastrowid,)).fetchone()), "note": f"✅ Mensagem enviada de verdade via WhatsApp Cloud API para {customer['phone']} (id {wamid})."})
                    except IntegrationError as e:
                        detail = integ.provider_error_detail(e.detail)
                        cur = conn.execute("INSERT INTO messages(company_id,customer_id,channel,content,status,created_at) VALUES(?,?,?,?,?,?)",
                                           (cid, customer["id"], channel, content, f"falha no envio WhatsApp: {e} {detail}"[:240], now()))
                        return self.send_json({"error": f"Meta/WhatsApp recusou o envio: {e} {detail}".strip(), "message": dict(conn.execute("SELECT * FROM messages WHERE id=?", (cur.lastrowid,)).fetchone())}, e.status)
                cur = conn.execute("INSERT INTO messages(company_id,customer_id,channel,content,status,created_at) VALUES(?,?,?,?,?,?)",
                                   (cid, customer["id"], channel, content, "na fila — WhatsApp Cloud API não configurada", now()))
                ai_log(conn, cid, "message_send", f"WhatsApp (fila) para {customer['name']}")
                return self.send_json({"message": dict(conn.execute("SELECT * FROM messages WHERE id=?", (cur.lastrowid,)).fetchone()), "note": "Mensagem registrada na fila. Configure a WhatsApp Cloud API em Admin & Planos → Integrações para enviar de verdade — nunca por spam."})
            if channel == "E-mail":
                smtp_cfg = integ.get_config(conn, cid, "smtp", active_only=True)
                if integ.configured_status("smtp", smtp_cfg)[0]:
                    try:
                        integ.smtp_send(smtp_cfg, customer["email"], data.get("subject") or f"Mensagem de {company['name']}", content)
                        cur = conn.execute("INSERT INTO messages(company_id,customer_id,channel,content,status,created_at) VALUES(?,?,?,?,?,?)",
                                           (cid, customer["id"], channel, content, "enviado via SMTP", now()))
                        return self.send_json({"message": dict(conn.execute("SELECT * FROM messages WHERE id=?", (cur.lastrowid,)).fetchone()), "note": f"✅ E-mail enviado via SMTP para {customer['email']}."})
                    except IntegrationError as e:
                        return self.send_json({"error": str(e)}, e.status)
                cur = conn.execute("INSERT INTO messages(company_id,customer_id,channel,content,status,created_at) VALUES(?,?,?,?,?,?)",
                                   (cid, customer["id"], channel, content, "na fila — SMTP não configurado", now()))
                return self.send_json({"message": dict(conn.execute("SELECT * FROM messages WHERE id=?", (cur.lastrowid,)).fetchone()), "note": "E-mail registrado na fila. Configure o SMTP em Admin & Planos → Integrações para enviar de verdade."})
            cur = conn.execute("INSERT INTO messages(company_id,customer_id,channel,content,status,created_at) VALUES(?,?,?,?,?,?)",
                               (cid, customer["id"], channel, content, "registrado", now()))
            return self.send_json({"message": dict(conn.execute("SELECT * FROM messages WHERE id=?", (cur.lastrowid,)).fetchone()), "note": "Mensagem registrada."})

        if path == "/api/settings" and method == "GET":
            settings = conn.execute("SELECT * FROM store_settings WHERE company_id=?", (cid,)).fetchone()
            return self.send_json({"company": dict(company), "store": dict(settings) if settings else {}})
        if path == "/api/settings" and method == "PUT":
            # Campos ausentes preservam o valor atual (evita apagar dados em atualizações parciais)
            autopilot = data.get("autopilot") or company["autopilot"] or "assistido"
            if autopilot not in ("manual", "assistido", "automatico"):
                autopilot = "assistido"
            conn.execute("UPDATE companies SET name=?, segment=?, city=?, region=?, whatsapp=?, email=?, goal_monthly=?, goal_weekly=?, goal_daily=?, autopilot=? WHERE id=?",
                         (str(data.get("name") or company["name"])[:120], data.get("segment") or company["segment"], data.get("city", company["city"] or ""),
                          data.get("region", company["region"] or ""), data.get("whatsapp", company["whatsapp"] or ""), data.get("email", company["email"] or ""),
                          round(to_float(data.get("goal_monthly"), company["goal_monthly"] or 6000, minimum=0), 2),
                          round(to_float(data.get("goal_weekly"), company["goal_weekly"] or 1500, minimum=0), 2),
                          round(to_float(data.get("goal_daily"), company["goal_daily"] or 200, minimum=0), 2), autopilot, cid))
            if data.get("allow_backorder") is None:  # campo ausente (ex.: salvar só a personalização) mantém o valor atual
                current = conn.execute("SELECT allow_backorder FROM store_settings WHERE company_id=?", (cid,)).fetchone()
                backorder = to_int(current["allow_backorder"], 0) if current else 0
            else:
                backorder = to_int(data.get("allow_backorder"), 0, minimum=0, maximum=1)
            conn.execute("INSERT INTO store_settings(company_id,store_name,logo,primary_color,banner,font,instagram,facebook,description,allow_backorder) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(company_id) DO UPDATE SET store_name=excluded.store_name, logo=excluded.logo, primary_color=excluded.primary_color, banner=excluded.banner, font=excluded.font, instagram=excluded.instagram, facebook=excluded.facebook, description=excluded.description, allow_backorder=excluded.allow_backorder",
                         (cid, str(data.get("store_name") or "Minha Loja")[:120], str(data.get("logo") or "🛍️")[:4], str(data.get("primary_color") or "#7c3aed")[:20],
                          str(data.get("banner") or "")[:200], str(data.get("font") or "Inter")[:40], str(data.get("instagram") or "")[:120], str(data.get("facebook") or "")[:120],
                          str(data.get("store_description", data.get("description", "")))[:600], backorder))
            log_audit(conn, cid, user["id"], "settings_update", "Configurações atualizadas")
            return self.send_json({"ok": True})

        if path == "/api/admin" and method == "GET":
            plans = [dict(r) for r in conn.execute("SELECT * FROM plans ORDER BY price")]
            users = [dict(r) for r in conn.execute("SELECT id,name,email,role,created_at FROM users WHERE company_id=?", (cid,))]
            usage = conn.execute("SELECT COUNT(*) actions, COALESCE(SUM(tokens),0) tokens FROM ai_usage WHERE company_id=? AND strftime('%Y-%m',created_at)=strftime('%Y-%m','now')", (cid,)).fetchone()
            audit = [dict(r) for r in conn.execute("SELECT * FROM audit_logs WHERE company_id=? ORDER BY id DESC LIMIT 15", (cid,))]
            counts = {t: conn.execute(f"SELECT COUNT(*) c FROM {t} WHERE company_id=?", (cid,)).fetchone()["c"] for t in ["products", "customers", "leads", "campaigns", "orders"]}
            integ_items = integ.list_integrations(conn, cid)
            return self.send_json({"plans": plans, "users": users, "usage": dict(usage), "audit": audit, "counts": counts, "version": APP_VERSION,
                                   "integrations": [{"name": i["name"], "status": i["status"], "desc": i["desc"]} for i in integ_items]})
        if path == "/api/billing" and method == "GET":
            sub = conn.execute("SELECT s.*, p.name plan_name FROM subscriptions s LEFT JOIN plans p ON p.id=s.plan_id WHERE s.company_id=? ORDER BY s.id DESC LIMIT 1", (cid,)).fetchone()
            plan = conn.execute("SELECT * FROM plans WHERE id=?", (company["plan_id"],)).fetchone()
            history = [dict(r) for r in conn.execute("SELECT * FROM payments WHERE company_id=? AND external_reference LIKE 'sub-%' ORDER BY id DESC LIMIT 10", (cid,))]
            for h in history:
                h.pop("raw", None)
                h.pop("qr_code_base64", None)
            return self.send_json({"plan": dict(plan) if plan else None, "subscription": dict(sub) if sub else None, "history": history})
        if path == "/api/billing/subscribe" and method == "POST":
            plan = conn.execute("SELECT * FROM plans WHERE id=?", (data.get("plan_id"),)).fetchone()
            if not plan:
                return self.send_json({"error": "Plano não encontrado"}, 404)
            if float(plan["price"] or 0) <= 0:
                period_end = (datetime.date.today() + datetime.timedelta(days=36500)).isoformat()
                conn.execute("INSERT INTO subscriptions(company_id,plan_id,provider,external_reference,status,amount,current_period_end,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                             (cid, plan["id"], "interno", f"sub-{cid}-{plan['id']}-free", "ativa", 0, period_end, now(), now()))
                conn.execute("UPDATE companies SET plan_id=? WHERE id=?", (plan["id"], cid))
                log_audit(conn, cid, user["id"], "billing_subscribe_free", plan["name"])
                return self.send_json({"ok": True, "active": True, "message": f"Plano {plan['name']} ativado! 🎉 (sem cobrança)"})
            config = integ.get_config(conn, cid, "mercadopago", active_only=True)
            if not integ.configured_status("mercadopago", config)[0]:
                return self.send_json({"error": "Para cobrar a assinatura, a empresa precisa conectar o Mercado Pago em Admin → Integrações (em produção, o billing usa a conta da plataforma). Sem gateway, nenhum plano pago é ativado."}, 400)
            method_pay = data.get("method", "pix")
            external_ref = f"sub-{cid}-{plan['id']}-{int(datetime.datetime.now().timestamp())}"
            notification_url = self.base_url() + "/api/webhooks/mercadopago"
            try:
                if method_pay == "card":
                    result = integ.mp_create_preference(config, [{"title": f"Assinatura ProdutoVenda IA — Plano {plan['name']} (mensal)", "quantity": 1, "unit_price": plan["price"]}], external_ref, self.base_url(), notification_url)
                    qr, qrb64 = "", ""
                else:
                    result = integ.mp_create_pix(config, float(plan["price"]), f"Assinatura ProdutoVenda IA — Plano {plan['name']} (mensal)", user["email"], external_ref, notification_url)
                    qr, qrb64 = result.get("qr_code", ""), result.get("qr_code_base64", "")
            except IntegrationError as e:
                return self.send_json({"error": f"Mercado Pago recusou: {e} {integ.provider_error_detail(e.detail)}".strip()}, e.status)
            conn.execute("INSERT INTO subscriptions(company_id,plan_id,provider,external_reference,status,amount,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                         (cid, plan["id"], "mercadopago", external_ref, "pendente", float(plan["price"]), now(), now()))
            cur = conn.execute("INSERT INTO payments(company_id,order_id,provider,external_id,external_reference,method,amount,status,qr_code,qr_code_base64,checkout_url,raw,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                               (cid, None, "mercadopago", result["external_id"], external_ref, method_pay, float(plan["price"]), result["status"], qr, qrb64, result.get("checkout_url", ""), json.dumps(result.get("raw", {}), ensure_ascii=False)[:8000], now(), now()))
            log_audit(conn, cid, user["id"], "billing_subscribe_pending", f"{plan['name']} via {method_pay}")
            payment = dict(conn.execute("SELECT * FROM payments WHERE id=?", (cur.lastrowid,)).fetchone())
            payment.pop("raw", None)
            return self.send_json({"ok": True, "active": False, "payment": payment,
                                   "message": f"Cobrança da assinatura {plan['name']} gerada! Assim que o pagamento for aprovado (webhook), o plano é ativado automaticamente por 30 dias."}, 201)
        if path == "/api/reports/export.csv" and method == "GET":
            kind = (query.get("type") or ["orders"])
            kind = kind[0] if isinstance(kind, list) else kind
            output = io.StringIO()
            writer = csv.writer(output, delimiter=";")
            if kind == "products":
                writer.writerow(["produto", "preco", "custo", "estoque", "vendas", "status"])
                for r in conn.execute("SELECT * FROM products WHERE company_id=? ORDER BY sales DESC", (cid,)):
                    writer.writerow([r["name"], r["price"], r["cost"], r["stock"], r["sales"], r["status"]])
            elif kind == "customers":
                writer.writerow(["cliente", "email", "telefone", "cidade", "segmento", "compras", "total_gasto", "ultima_compra", "vip", "consentimento"])
                for r in conn.execute("SELECT * FROM customers WHERE company_id=? ORDER BY total_spent DESC", (cid,)):
                    writer.writerow([r["name"], r["email"], r["phone"], r["city"], r["segment"], r["purchases"], r["total_spent"], r["last_purchase"] or "", r["vip"], r["consent"]])
            elif kind == "payments":
                writer.writerow(["id", "pedido", "metodo", "valor", "status_mp", "id_externo", "referencia", "criado_em"])
                for r in conn.execute("SELECT * FROM payments WHERE company_id=? ORDER BY id DESC", (cid,)):
                    writer.writerow([r["id"], r["order_id"] or "", r["method"], r["amount"], r["status"], r["external_id"], r["external_reference"] if "external_reference" in r.keys() else "", r["created_at"]])
            else:
                kind = "orders"
                writer.writerow(["pedido", "data", "cliente", "canal", "total", "lucro_estimado", "status", "cupom"])
                for r in conn.execute("SELECT * FROM orders WHERE company_id=? ORDER BY id DESC", (cid,)):
                    writer.writerow([r["id"], (r["created_at"] or "")[:10], r["customer_name"], r["channel"], r["total"], r["profit"], r["status"], r["coupon"] or ""])
            log_audit(conn, cid, user["id"], "report_csv", kind)
            return self.send_download(f"relatorio-{kind}.csv", "\ufeff" + output.getvalue())

        if path == "/api/admin/plan" and method == "POST":
            conn.execute("UPDATE companies SET plan_id=? WHERE id=?", (int(data.get("plan_id")), cid))
            log_audit(conn, cid, user["id"], "plan_change", f"Plano alterado para {data.get('plan_id')}")
            return self.send_json({"ok": True, "message": "Plano atualizado (estrutura preparada para billing real)."})

        return self.send_json({"error": "Rota não encontrada"}, 404)

    # ---------- CRUD generico (sempre filtrado por tenant)
    TABLES = {
        "products": ["category_id", "name", "description", "price", "cost", "stock", "audience", "icon", "status", "image"],
        "customers": ["name", "email", "phone", "city", "segment", "consent", "vip", "birthday"],
        "leads": ["name", "company", "email", "phone", "city", "segment", "source", "stage", "potential", "value", "notes", "next_action"],
        "orders": ["customer_name", "total", "profit", "status", "channel", "coupon"],
        "coupons": ["code", "type", "value", "kind", "min_value", "product_id", "limit_uses", "active"],
        "campaigns": ["name", "product_id", "objective", "audience", "region", "channel", "status", "budget"],
        "automations": ["name", "trigger_event", "action", "config", "active"],
        "opportunities": ["name", "company", "segment", "city", "phone", "email", "site", "source", "status", "potential", "notes"],
        "proposals": ["customer_name", "title", "total", "discount", "deadline", "conditions", "status", "content"],
        "content": ["title", "channel", "content", "scheduled_at", "status", "product_id"],
        "email-campaigns": ["subject", "content", "segment", "status"],
        "templates": ["name", "channel", "content"],
        "reviews": ["product_id", "customer_name", "rating", "comment"],
    }
    TABLE_MAP = {"content": "campaign_contents", "email-campaigns": "email_campaigns", "templates": "message_templates"}
    COUPON_TYPES = ("percentual", "fixo")

    def prepare(self, conn, cid, resource, data, rid=None):
        """Normaliza e valida os campos antes de gravar (tenant-safe). Retorna a mensagem de erro ou None."""
        if resource == "coupons":
            if "code" in data:
                code = re.sub(r"\s+", "", str(data.get("code") or "")).upper()
                if not re.match(r"^[A-Z0-9\-_]{3,24}$", code):
                    return "Código do cupom inválido: use de 3 a 24 caracteres (letras, números, - ou _)."
                if conn.execute("SELECT id FROM coupons WHERE company_id=? AND UPPER(code)=? AND id<>?", (cid, code, to_int(rid, 0))).fetchone():
                    return f"Já existe um cupom com o código {code}. Use outro código."
                data["code"] = code
            type_ = data.get("type") or "percentual"
            if type_ not in self.COUPON_TYPES:
                return "Tipo de cupom inválido: use percentual ou valor fixo."
            if "value" in data:
                value = to_float(data.get("value"))
                if value <= 0:
                    return "Informe um valor de desconto maior que zero."
                if type_ == "percentual" and value > 100:
                    return "O desconto percentual não pode passar de 100%."
                data["value"] = round(value, 2)
            if "min_value" in data:
                data["min_value"] = round(to_float(data.get("min_value"), 0, minimum=0), 2)
            if "limit_uses" in data:
                data["limit_uses"] = to_int(data.get("limit_uses"), 0, minimum=0)
            if "active" in data:
                data["active"] = to_int(data.get("active"), 1, minimum=0, maximum=1)
            if "product_id" in data:
                data["product_id"] = to_int(data.get("product_id"), 0, minimum=0) or None
        elif resource == "products":
            if "name" in data:
                name = str(data.get("name") or "").strip()
                if not name:
                    return "Informe o nome do produto."
                data["name"] = name[:120]
            for field in ("price", "cost"):
                if field in data:
                    data[field] = round(to_float(data.get(field), 0, minimum=0), 2)
            if "stock" in data:
                data["stock"] = to_int(data.get("stock"), 0, minimum=0)
            if "status" in data and data["status"] not in ("ativo", "inativo", "pausado"):
                data["status"] = "ativo"
        elif resource == "orders":
            for field in ("total", "profit"):
                if field in data:
                    data[field] = round(to_float(data.get(field), 0, minimum=0), 2)
        elif resource == "customers":
            for field, default in (("consent", 1), ("vip", 0)):
                if field in data:
                    data[field] = to_int(data.get(field), default, minimum=0, maximum=1)
        elif resource == "reviews":
            if "rating" in data:
                data["rating"] = to_int(data.get("rating"), 5, minimum=1, maximum=5)
        elif resource == "leads":
            if "value" in data:
                data["value"] = round(to_float(data.get("value"), 0, minimum=0), 2)
        return None

    def crud(self, conn, method, path, data, cid, user):
        m = re.match(r"^/api/([a-z\-]+)(?:/(\d+))?$", path)
        if not m or m.group(1) not in self.TABLES:
            return False
        resource, rid = m.group(1), m.group(2)
        table = self.TABLE_MAP.get(resource, resource)
        fields = self.TABLES[resource]
        if method == "GET" and not rid:
            rows = [dict(r) for r in conn.execute(f"SELECT * FROM {table} WHERE company_id=? ORDER BY id DESC", (cid,))]
            extra = {}
            if resource == "leads":
                extra["stages"] = ["Novo Lead", "Contato Realizado", "Interessado", "Proposta", "Negociação", "Pedido", "Pago", "Pós-venda", "Perdido"]
            if resource == "customers":
                for r in rows:
                    refs = conn.execute("SELECT COUNT(*) c FROM referrals WHERE company_id=? AND customer_id=?", (cid, r["id"])).fetchone()["c"]
                    r["referrals"] = refs
            return self.send_json({resource.replace("-", "_"): rows, **extra}) or True
        if method == "GET" and rid:
            row = conn.execute(f"SELECT * FROM {table} WHERE id=? AND company_id=?", (rid, cid)).fetchone()
            return self.send_json({"item": dict(row) if row else None}) or True
        if method == "POST" and not rid:
            err = self.prepare(conn, cid, resource, data)
            if err:
                self.send_json({"error": err}, 400)
                return True
            cols = [f for f in fields if f in data]
            if not cols:
                self.send_json({"error": "Informe ao menos um campo válido para criar o registro."}, 400)
                return True
            values = [data[f] for f in cols]
            cur = conn.execute(f"INSERT INTO {table}(company_id,{','.join(cols)},created_at) VALUES(?,{','.join('?'*len(cols))},?)", [cid] + values + [now()])
            if resource == "products":
                conn.execute("UPDATE products SET sales=0 WHERE id=?", (cur.lastrowid,))
            if resource == "orders":
                self.after_order(conn, cid, cur.lastrowid, data)
            log_audit(conn, cid, user["id"], f"create_{resource}", str(data)[:160])
            row = conn.execute(f"SELECT * FROM {table} WHERE id=?", (cur.lastrowid,)).fetchone()
            self.send_json({"item": dict(row)}, 201)
            return True
        if method == "PUT" and rid:
            exists = conn.execute(f"SELECT id FROM {table} WHERE id=? AND company_id=?", (rid, cid)).fetchone()
            if not exists:
                self.send_json({"error": "Registro não encontrado neste tenant"}, 404)
                return True
            err = self.prepare(conn, cid, resource, data, rid)
            if err:
                self.send_json({"error": err}, 400)
                return True
            cols = [f for f in fields if f in data]
            if cols:
                conn.execute(f"UPDATE {table} SET {','.join(f+'=?' for f in cols)} WHERE id=? AND company_id=?", [data[f] for f in cols] + [rid, cid])
            if table == "leads" and data.get("stage"):
                conn.execute("UPDATE leads SET last_interaction=? WHERE id=?", (today(), rid))
            row = conn.execute(f"SELECT * FROM {table} WHERE id=?", (rid,)).fetchone()
            self.send_json({"item": dict(row)})
            return True
        if method == "DELETE" and rid:
            conn.execute(f"DELETE FROM {table} WHERE id=? AND company_id=?", (rid, cid))
            self.send_json({"ok": True})
            return True
        return False

    def after_order(self, conn, cid, order_id, data):
        # baixa de estoque simples quando item informado pelo painel
        pass

    # ---------- auth impl
    def register(self, conn, data):
        email = (data.get("email") or "").strip().lower()
        password = data.get("password") or ""
        if not email or len(password) < 6:
            return self.send_json({"error": "Informe e-mail e senha com pelo menos 6 caracteres."}, 400)
        if conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone():
            return self.send_json({"error": "Este e-mail já possui conta. Faça login."}, 400)
        company_name = data.get("company_name") or "Minha Empresa"
        slug = slugify(company_name)
        base_slug, i = slug, 2
        while conn.execute("SELECT id FROM companies WHERE slug=?", (slug,)).fetchone():
            slug = f"{base_slug}-{i}"; i += 1
        cur = conn.execute("INSERT INTO companies(name,slug,segment,city,goal_monthly,plan_id,onboarded,created_at) VALUES(?,?,?,?,?,?,?,?)",
                           (company_name, slug, data.get("segment", "Meu negócio"), data.get("city", ""), 6000, 1, 0, now()))
        cid = cur.lastrowid
        conn.execute("INSERT INTO store_settings(company_id,store_name,logo,primary_color,description) VALUES(?,?,?,?,?)", (cid, company_name, "🛍️", "#7c3aed", ""))
        ph, salt = hash_pass(password)
        cur = conn.execute("INSERT INTO users(company_id,name,email,pass_hash,salt,role,created_at) VALUES(?,?,?,?,?,?,?)", (cid, data.get("name", "Usuário"), email, ph, salt, "owner", now()))
        token = self.create_session(conn, cur.lastrowid)
        log_audit(conn, cid, cur.lastrowid, "register", email)
        conn.commit()
        return self.send_json({"token": token, "message": "Conta criada! Vamos montar seu sistema de vendas."})

    def login(self, conn, data):
        email = (data.get("email") or "").strip().lower()
        if rate_limited(email):
            return self.send_json({"error": "Muitas tentativas. Aguarde alguns minutos."}, 429)
        user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if not user:
            LOGIN_ATTEMPTS.setdefault(email, []).append(datetime.datetime.now().timestamp())
            return self.send_json({"error": "E-mail ou senha inválidos."}, 401)
        ph, _ = hash_pass(data.get("password") or "", user["salt"])
        if ph != user["pass_hash"]:
            LOGIN_ATTEMPTS.setdefault(email, []).append(datetime.datetime.now().timestamp())
            return self.send_json({"error": "E-mail ou senha inválidos."}, 401)
        token = self.create_session(conn, user["id"])
        log_audit(conn, user["company_id"], user["id"], "login", email)
        conn.commit()
        return self.send_json({"token": token})

    def create_session(self, conn, user_id):
        token = secrets.token_urlsafe(48)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        expires = (datetime.datetime.now() + datetime.timedelta(days=7)).isoformat(timespec="seconds")
        conn.execute("INSERT INTO sessions(user_id,token_hash,created_at,expires_at) VALUES(?,?,?,?)", (user_id, token_hash, now(), expires))
        return token

    # ---------- Webhooks / pagamentos (integracoes reais) ----------
    def webhook_whatsapp(self, conn, data):
        try:
            for entry in (data.get("entry") or []):
                for change in (entry.get("changes") or []):
                    value = change.get("value") or {}
                    metadata = value.get("metadata") or {}
                    phone_number_id = str(metadata.get("phone_number_id") or "")
                    company_id = None
                    for r in conn.execute("SELECT company_id, config FROM integrations WHERE provider='whatsapp'").fetchall():
                        try:
                            cfg = json.loads(r["config"] or "{}")
                        except Exception:
                            cfg = {}
                        if phone_number_id and str(cfg.get("phone_number_id") or "") == phone_number_id:
                            company_id = r["company_id"]
                            break
                    if not company_id:
                        continue
                    profiles = {}
                    for c in (value.get("contacts") or []):
                        profiles[c.get("wa_id", "")] = (c.get("profile") or {}).get("name", "")
                    for msg in (value.get("messages") or []):
                        wa_id = msg.get("from", "")
                        text = ((msg.get("text") or {}).get("body")) or f"[{msg.get('type', 'mensagem')}]"
                        customer = None
                        for cand in conn.execute("SELECT * FROM customers WHERE company_id=?", (company_id,)).fetchall():
                            cand_digits = re.sub(r"\D", "", cand["phone"] or "")
                            if cand_digits and (cand_digits.endswith(wa_id[-11:]) if len(wa_id) >= 11 else cand_digits == wa_id):
                                customer = cand
                                break
                        if not customer:
                            cur = conn.execute("INSERT INTO customers(company_id,name,phone,segment,consent,referral_code,created_at) VALUES(?,?,?,?,?,?,?)",
                                               (company_id, profiles.get(wa_id) or wa_id, wa_id, "WhatsApp", 1, "WA" + str(random.randint(1000, 9999)), now()))
                            customer = conn.execute("SELECT * FROM customers WHERE id=?", (cur.lastrowid,)).fetchone()
                        conn.execute("INSERT INTO messages(company_id,customer_id,channel,direction,content,status,external_id,created_at) VALUES(?,?,?,?,?,?,?,?)",
                                     (company_id, customer["id"], "WhatsApp", "in", text, "recebido via WhatsApp Cloud API", msg.get("id", ""), now()))
                        notify(conn, company_id, "💬 Nova mensagem no WhatsApp", f"{customer['name']}: {text[:120]}", "info")
                    for st in (value.get("statuses") or []):
                        if st.get("id"):
                            conn.execute("UPDATE messages SET status=? WHERE company_id=? AND external_id=?", (f"WhatsApp: {st.get('status')}", company_id, st["id"]))
        except Exception as e:
            print(f"[webhook whatsapp] {e}")
        return self.send_json({"received": True})

    def apply_mp_status(self, conn, payment, mp_status, raw):
        previous = payment["status"]
        conn.execute("UPDATE payments SET status=?, raw=?, updated_at=? WHERE id=?", (mp_status, json.dumps(raw, ensure_ascii=False)[:8000], now(), payment["id"]))
        external_ref = (payment["external_reference"] if "external_reference" in payment.keys() else "") or (raw.get("external_reference") if isinstance(raw, dict) else "") or ""
        if mp_status == "approved" and previous != "approved" and str(external_ref).startswith("sub-"):
            sub = conn.execute("SELECT * FROM subscriptions WHERE company_id=? AND external_reference=? AND status!='ativa'", (payment["company_id"], external_ref)).fetchone()
            if sub:
                period_end = (datetime.date.today() + datetime.timedelta(days=30)).isoformat()
                conn.execute("UPDATE subscriptions SET status='ativa', current_period_end=?, updated_at=? WHERE id=?", (period_end, now(), sub["id"]))
                conn.execute("UPDATE companies SET plan_id=? WHERE id=?", (sub["plan_id"], payment["company_id"]))
                plan = conn.execute("SELECT name FROM plans WHERE id=?", (sub["plan_id"],)).fetchone()
                notify(conn, payment["company_id"], "💎 Assinatura ativada!", f"Plano {plan['name'] if plan else sub['plan_id']} ativo até {period_end}. Obrigado!", "success")
        if mp_status == "approved" and previous != "approved" and payment["order_id"]:
            order = conn.execute("SELECT * FROM orders WHERE id=? AND company_id=?", (payment["order_id"], payment["company_id"])).fetchone()
            if order:
                conn.execute("UPDATE orders SET status='pago' WHERE id=?", (order["id"],))
                if order["customer_id"]:
                    conn.execute("UPDATE customers SET total_spent=COALESCE(total_spent,0)+?, purchases=COALESCE(purchases,0)+1, last_purchase=? WHERE id=?", (order["total"], today(), order["customer_id"]))
                notify(conn, payment["company_id"], "💰 Pagamento aprovado (Mercado Pago)", f"Pedido #{order['id']} — {order['customer_name']} — {brl(order['total'])}", "success")

    def webhook_mercadopago(self, conn, payment_external_id):
        if not payment_external_id:
            return self.send_json({"received": True})
        payment = conn.execute("SELECT * FROM payments WHERE external_id=?", (str(payment_external_id),)).fetchone()
        if payment:
            config = integ.get_config(conn, payment["company_id"], "mercadopago", active_only=True)
            try:
                raw = integ.mp_get_payment(config, payment_external_id)
                self.apply_mp_status(conn, payment, raw.get("status", payment["status"]), raw)
            except Exception as e:
                print(f"[webhook mercadopago] {e}")
        else:
            # Pagamento de Checkout Pro: o ID do webhook e o do pagamento (nao o da preferencia).
            # Busca a empresa dona tentando consultar o pagamento e casa pela external_reference.
            for row in conn.execute("SELECT DISTINCT company_id FROM integrations WHERE provider='mercadopago' AND active=1").fetchall():
                config = integ.get_config(conn, row["company_id"], "mercadopago", active_only=True)
                if not integ.configured_status("mercadopago", config)[0]:
                    continue
                try:
                    raw = integ.mp_get_payment(config, payment_external_id)
                except Exception:
                    continue
                ext_ref = raw.get("external_reference") or ""
                local = conn.execute("SELECT * FROM payments WHERE company_id=? AND external_reference=?", (row["company_id"], ext_ref)).fetchone() if ext_ref else None
                if local:
                    conn.execute("UPDATE payments SET external_id=? WHERE id=?", (str(payment_external_id), local["id"]))
                    local = conn.execute("SELECT * FROM payments WHERE id=?", (local["id"],)).fetchone()
                    self.apply_mp_status(conn, local, raw.get("status", local["status"]), raw)
                break
        return self.send_json({"received": True})

    def payments_create(self, conn, company, user, data):
        cid = company["id"]
        config = integ.get_config(conn, cid, "mercadopago", active_only=True)
        ok, missing = integ.configured_status("mercadopago", config)
        if not ok:
            return self.send_json({"error": f"Mercado Pago não configurado (faltam: {', '.join(missing)}). Configure em Admin & Planos → Integrações. Sem credencial, nenhum pagamento real é criado."}, 400)
        order = None
        amount = float(data.get("amount") or 0)
        if data.get("order_id"):
            order = conn.execute("SELECT * FROM orders WHERE id=? AND company_id=?", (data["order_id"], cid)).fetchone()
            if not order:
                return self.send_json({"error": "Pedido não encontrado"}, 404)
            amount = float(order["total"] or 0)
        if amount <= 0:
            return self.send_json({"error": "Informe um valor maior que zero (ou um pedido válido)."}, 400)
        method = data.get("method", "pix")
        notification_url = self.base_url() + "/api/webhooks/mercadopago"
        payer_email = data.get("payer_email") or ""
        if order and order["customer_id"]:
            cust = conn.execute("SELECT email FROM customers WHERE id=?", (order["customer_id"],)).fetchone()
            payer_email = payer_email or (cust["email"] if cust else "")
        external_ref = f"order-{order['id']}" if order else f"manual-{int(datetime.datetime.now().timestamp())}"
        try:
            if method == "card":
                items = []
                if order:
                    items = [{"title": i["product_name"], "quantity": i["qty"], "unit_price": i["price"]} for i in conn.execute("SELECT * FROM order_items WHERE order_id=?", (order["id"],))]
                if not items:
                    items = [{"title": data.get("description") or "Pedido ProdutoVenda IA", "quantity": 1, "unit_price": amount}]
                result = integ.mp_create_preference(config, items, external_ref, self.base_url(), notification_url)
                qr, qrb64 = "", ""
            else:
                result = integ.mp_create_pix(config, amount, data.get("description") or (f"Pedido #{order['id']}" if order else "Pagamento ProdutoVenda IA"), payer_email, external_ref, notification_url)
                qr, qrb64 = result.get("qr_code", ""), result.get("qr_code_base64", "")
        except IntegrationError as e:
            return self.send_json({"error": f"Mercado Pago recusou a criação: {e} {integ.provider_error_detail(e.detail)}".strip()}, e.status)
        cur = conn.execute("INSERT INTO payments(company_id,order_id,provider,external_id,external_reference,method,amount,status,qr_code,qr_code_base64,checkout_url,raw,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                           (cid, order["id"] if order else None, "mercadopago", result["external_id"], external_ref, method, amount, result["status"], qr, qrb64, result.get("checkout_url", ""), json.dumps(result.get("raw", {}), ensure_ascii=False)[:8000], now(), now()))
        log_audit(conn, cid, user["id"], "payment_create", f"{method} {amount} ext={result['external_id']}")
        payment = dict(conn.execute("SELECT * FROM payments WHERE id=?", (cur.lastrowid,)).fetchone())
        payment.pop("raw", None)
        return self.send_json({"payment": payment, "message": "✅ Pix gerado no Mercado Pago! Envie o QR Code/copia e cola ao cliente." if method != "card" else "✅ Link de pagamento (Checkout Pro) gerado! Envie o link ao cliente."}, 201)

    def public_checkout(self, conn, company, data):
        cid = company["id"]
        items = data.get("items") or []
        if not items:
            return self.send_json({"error": "Carrinho vazio."}, 400)
        payment_method = (data.get("payment_method") or "manual").strip().lower()
        if payment_method not in ("manual", "pix", "card"):
            return self.send_json({"error": "Forma de pagamento inválida."}, 400)
        name = (data.get("customer_name") or "Cliente da loja").strip()[:120] or "Cliente da loja"
        store = conn.execute("SELECT * FROM store_settings WHERE company_id=?", (cid,)).fetchone()
        backorder = bool(store and store["allow_backorder"])
        total, profit = 0.0, 0.0
        lines = []
        for it in items:
            product = conn.execute("SELECT * FROM products WHERE id=? AND company_id=? AND status='ativo'", (it.get("product_id"), cid)).fetchone()
            if not product:
                continue
            qty = to_int(it.get("qty"), 1, minimum=1, maximum=999)
            if not backorder and (product["stock"] or 0) < qty:
                return self.send_json({"error": f"Estoque insuficiente para {product['name']}. Disponível: {product['stock'] or 0} un."}, 400)
            total += float(product["price"]) * qty
            profit += (float(product["price"]) - float(product["cost"] or 0)) * qty
            lines.append((product, qty))
        if not lines:
            return self.send_json({"error": "Nenhum produto válido no carrinho."}, 400)
        discount = 0.0
        coupon_row = None
        if data.get("coupon"):
            coupon_row = conn.execute("SELECT * FROM coupons WHERE company_id=? AND UPPER(code)=UPPER(?) AND active=1", (cid, str(data["coupon"]).strip())).fetchone()
            if not coupon_row:
                return self.send_json({"error": "Cupom inválido ou inativo."}, 400)
            if coupon_row["limit_uses"] and coupon_row["used"] >= coupon_row["limit_uses"]:
                return self.send_json({"error": "Cupom esgotado."}, 400)
            if total < float(coupon_row["min_value"] or 0):
                return self.send_json({"error": f"Este cupom exige compra mínima de {brl(coupon_row['min_value'])}."}, 400)
            discount = total * float(coupon_row["value"]) / 100 if coupon_row["type"] == "percentual" else float(coupon_row["value"])
            discount = max(0.0, min(discount, total))   # cupom nunca gera total negativo nem desconto fantasma
        total = round(total - discount, 2)
        customer = conn.execute("SELECT * FROM customers WHERE company_id=? AND (phone=? OR email=?)", (cid, data.get("phone", ""), data.get("email", ""))).fetchone() if (data.get("phone") or data.get("email")) else None
        if not customer:
            cur = conn.execute("INSERT INTO customers(company_id,name,email,phone,city,segment,referral_code,created_at) VALUES(?,?,?,?,?,?,?,?)",
                               (cid, name, data.get("email", ""), data.get("phone", ""), "", "Cliente da loja", "LOJA" + str(random.randint(1000, 9999)), now()))
            customer = conn.execute("SELECT * FROM customers WHERE id=?", (cur.lastrowid,)).fetchone()
            conn.execute("INSERT INTO messages(company_id,customer_id,channel,content,status,created_at) VALUES(?,?,?,?,?,?)",
                         (cid, customer["id"], "WhatsApp", f"Oi, {name.split()[0]}! 😊 Bem-vindo(a)! Use BEMVINDO10 na próxima compra.", "registrado (boas-vindas automática)", now()))
        # Pagamento online só é aceito com gateway realmente conectado: sem isso o pedido
        # ficaria marcado como pago sem nenhum dinheiro ter entrado.
        mp_cfg = integ.get_config(conn, cid, "mercadopago", active_only=True)
        mp_on = integ.configured_status("mercadopago", mp_cfg)[0]
        if payment_method in ("pix", "card") and not mp_on:
            return self.send_json({"error": "Esta loja ainda não está com pagamento online ativo. Escolha “combinar pagamento com a loja” para finalizar seu pedido."}, 400)
        use_gateway = payment_method in ("pix", "card")
        order_status = "aguardando pagamento" if use_gateway else "pago"
        cur = conn.execute("INSERT INTO orders(company_id,customer_id,customer_name,total,profit,status,channel,coupon,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                           (cid, customer["id"], name, total, round(profit, 2), order_status, "Loja", (coupon_row["code"] if coupon_row else ""), now()))
        order_id = cur.lastrowid
        for product, qty in lines:
            if backorder:
                # sob encomenda: vende mesmo sem estoque; o estoque nunca fica negativo
                conn.execute("UPDATE products SET stock=MAX(COALESCE(stock,0)-?,0), sales=COALESCE(sales,0)+? WHERE id=? AND company_id=?",
                             (qty, qty, product["id"], cid))
            else:
                # baixa condicional: dois pedidos simultâneos nunca deixam estoque negativo
                updated = conn.execute("UPDATE products SET stock=stock-?, sales=COALESCE(sales,0)+? WHERE id=? AND company_id=? AND stock>=?",
                                       (qty, qty, product["id"], cid, qty))
                if updated.rowcount != 1:
                    return self.send_json({"error": f"O estoque de {product['name']} mudou agora e não é mais suficiente. Ajuste a quantidade e tente de novo — nada foi cobrado."}, 409)
            conn.execute("INSERT INTO order_items(company_id,order_id,product_id,product_name,qty,price) VALUES(?,?,?,?,?,?)", (cid, order_id, product["id"], product["name"], qty, product["price"]))
        if coupon_row:
            conn.execute("UPDATE coupons SET used=used+1 WHERE id=?", (coupon_row["id"],))
            conn.execute("INSERT INTO coupon_usages(company_id,coupon_id,customer_id,order_id,created_at) VALUES(?,?,?,?,?)", (cid, coupon_row["id"], customer["id"], order_id, now()))
        if order_status == "pago":
            conn.execute("UPDATE customers SET total_spent=COALESCE(total_spent,0)+?, purchases=COALESCE(purchases,0)+1, last_purchase=? WHERE id=?", (total, today(), customer["id"]))
        # --- Pagamento real via Mercado Pago (Pix QR / Checkout Pro cartao) ---
        payment_info = None
        if use_gateway:
            notification_url = self.base_url() + "/api/webhooks/mercadopago"
            try:
                if payment_method == "card":
                    result = integ.mp_create_preference(mp_cfg, [{"title": p["name"], "quantity": q, "unit_price": p["price"]} for p, q in lines], f"order-{order_id}", self.base_url(), notification_url)
                    qr, qrb64 = "", ""
                else:
                    result = integ.mp_create_pix(mp_cfg, total, f"Pedido #{order_id} — {company['name']}", data.get("email") or customer["email"], f"order-{order_id}", notification_url)
                    qr, qrb64 = result.get("qr_code", ""), result.get("qr_code_base64", "")
                cur = conn.execute("INSERT INTO payments(company_id,order_id,provider,external_id,external_reference,method,amount,status,qr_code,qr_code_base64,checkout_url,raw,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                   (cid, order_id, "mercadopago", result["external_id"], f"order-{order_id}", payment_method, total, result["status"], qr, qrb64, result.get("checkout_url", ""), json.dumps(result.get("raw", {}), ensure_ascii=False)[:8000], now(), now()))
                payment_info = {"id": cur.lastrowid, "method": payment_method, "status": result["status"], "qr_code": qr, "qr_code_base64": qrb64, "checkout_url": result.get("checkout_url", "")}
            except IntegrationError as e:
                payment_info = {"method": payment_method, "status": "erro", "error": f"{e} {integ.provider_error_detail(e.detail)}".strip()}
        if data.get("phone"):
            conn.execute("UPDATE carts SET status='recuperado', updated_at=? WHERE company_id=? AND phone=? AND status='abandonado'", (now(), cid, data["phone"]))
        conn.commit()
        if use_gateway and payment_info and payment_info.get("status") != "erro":
            msg = "Pedido criado! ✅ Conclua o pagamento Pix para confirmar." if payment_method == "pix" else "Pedido criado! ✅ Conclua o pagamento no link do Mercado Pago para confirmar."
        elif use_gateway:
            msg = "Pedido registrado, mas o gateway falhou ao gerar a cobrança. A loja entrará em contato para concluir o pagamento."
        else:
            msg = "Pedido confirmado! 🎉 Obrigado pela compra. Você receberá as atualizações pelo WhatsApp."
        return self.send_json({"ok": True, "order_id": order_id, "total": total, "discount": round(discount, 2), "order_status": order_status, "payment": payment_info, "message": msg})

    # ---------- dashboard / insights / reports / automations
    def dashboard(self, conn, company):
        cid = company["id"]
        paid = "status IN ('pago','entregue','concluido')"
        today_rev = conn.execute(f"SELECT COALESCE(SUM(total),0) s FROM orders WHERE company_id=? AND {paid} AND date(created_at)=date('now')", (cid,)).fetchone()["s"]
        month = conn.execute(f"SELECT COALESCE(SUM(total),0) s, COALESCE(SUM(profit),0) p, COUNT(*) n FROM orders WHERE company_id=? AND {paid} AND strftime('%Y-%m',created_at)=strftime('%Y-%m','now')", (cid,)).fetchone()
        orders_count = conn.execute("SELECT COUNT(*) c FROM orders WHERE company_id=?", (cid,)).fetchone()["c"]
        customers_count = conn.execute("SELECT COUNT(*) c FROM customers WHERE company_id=?", (cid,)).fetchone()["c"]
        new_customers = conn.execute("SELECT COUNT(*) c FROM customers WHERE company_id=? AND strftime('%Y-%m',created_at)=strftime('%Y-%m','now')", (cid,)).fetchone()["c"]
        leads_count = conn.execute("SELECT COUNT(*) c FROM leads WHERE company_id=? AND stage NOT IN ('Perdido','Pago')", (cid,)).fetchone()["c"]
        carts = conn.execute("SELECT COUNT(*) c FROM carts WHERE company_id=? AND status='abandonado'", (cid,)).fetchone()["c"]
        followups = conn.execute("SELECT COUNT(*) c FROM leads WHERE company_id=? AND stage IN ('Proposta','Interessado','Contato Realizado')", (cid,)).fetchone()["c"]
        coupon_used = conn.execute("SELECT COALESCE(SUM(used),0) s FROM coupons WHERE company_id=?", (cid,)).fetchone()["s"]
        campaigns_active = conn.execute("SELECT COUNT(*) c FROM campaigns WHERE company_id=? AND status='ativa'", (cid,)).fetchone()["c"]
        ticket = (month["s"] / month["n"]) if month["n"] else 0
        paid_leads = conn.execute("SELECT COUNT(*) c FROM leads WHERE company_id=? AND stage='Pago'", (cid,)).fetchone()["c"]
        total_leads = conn.execute("SELECT COUNT(*) c FROM leads WHERE company_id=?", (cid,)).fetchone()["c"]
        conversion = round((paid_leads / total_leads * 100), 1) if total_leads else 0
        goal = float(company["goal_monthly"] or 6000)
        missing = max(goal - month["s"], 0)
        avg_profit_order = (month["p"] / month["n"]) if month["n"] else 40
        orders_needed = int(missing / avg_profit_order) + (1 if missing % avg_profit_order else 0) if missing and avg_profit_order else 0
        top_products = [dict(r) for r in conn.execute("SELECT name, icon, price, sales, stock FROM products WHERE company_id=? ORDER BY sales DESC LIMIT 5", (cid,))]
        series = []
        for d in range(13, -1, -1):
            date = (datetime.date.today() - datetime.timedelta(days=d)).isoformat()
            val = conn.execute(f"SELECT COALESCE(SUM(total),0) s FROM orders WHERE company_id=? AND {paid} AND date(created_at)=?", (cid, date)).fetchone()["s"]
            series.append({"date": date, "label": date[5:], "value": round(val, 2)})
        recent_orders = [dict(r) for r in conn.execute("SELECT * FROM orders WHERE company_id=? ORDER BY id DESC LIMIT 6", (cid,))]
        return self.send_json({
            "kpis": {"revenue_today": today_rev, "revenue_month": month["s"], "profit_month": month["p"], "orders": orders_count, "orders_month": month["n"],
                     "ticket": round(ticket, 2), "customers": customers_count, "new_customers": new_customers, "leads": leads_count, "conversion": conversion,
                     "campaigns_active": campaigns_active, "coupons_used": coupon_used, "abandoned_carts": carts, "followups": followups},
            "goal": {"monthly": goal, "sold": month["s"], "missing": round(missing, 2), "percent": round(min(month["s"] / goal * 100, 100), 1) if goal else 0,
                     "orders_needed": orders_needed, "avg_profit": round(avg_profit_order, 2),
                     "message": f"Você precisa de aproximadamente {orders_needed} pedidos de {brl(avg_profit_order)} de lucro médio para alcançar essa meta." if missing else "Meta do mês alcançada! 🎉 Defina uma nova meta nas Configurações."},
            "top_products": top_products, "series": series, "recent_orders": recent_orders,
            "ai_tip": "Produto mais vendido em destaque: crie uma campanha esta semana e recupere os carrinhos abandonados para acelerar a meta (sem promessas — é planejamento).",
        })

    def compute_insights(self, conn, company):
        cid = company["id"]
        insights = []
        top = conn.execute("SELECT * FROM products WHERE company_id=? ORDER BY sales DESC LIMIT 1", (cid,)).fetchone()
        if top:
            insights.append({"icon": "🏆", "text": f"Seu produto líder é {top['name']} ({top['sales'] or 0} vendas, {brl(top['price'])}). Ele merece campanha e destaque na loja esta semana.", "action_label": "CRIAR CAMPANHA", "action": "campaign", "product_id": top["id"]})
            low = conn.execute("SELECT * FROM products WHERE company_id=? AND stock<=20 ORDER BY stock ASC LIMIT 1", (cid,)).fetchone()
            if low:
                insights.append({"icon": "⚠️", "text": f"Estoque baixo: {low['name']} tem apenas {low['stock']} unidades. Planeje reposição antes de impulsionar campanha.", "action_label": "VER PRODUTO", "action": "go", "target": "produtos"})
            pair = conn.execute("SELECT * FROM products WHERE company_id=? AND id!=? ORDER BY sales DESC LIMIT 1", (cid, top["id"])).fetchone()
            if pair:
                insights.append({"icon": "🧺", "text": f"Clientes que compram {top['name']} também costumam se interessar por {pair['name']}. Crie um combo para elevar o ticket médio.", "action_label": "CRIAR COMBO/CAMPANHA", "action": "campaign", "product_id": top["id"]})
        inactive = conn.execute("SELECT COUNT(*) c FROM customers WHERE company_id=? AND (last_purchase IS NULL OR last_purchase < date('now','-60 day'))", (cid,)).fetchone()["c"]
        if inactive:
            insights.append({"icon": "💌", "text": f"Você possui {inactive} clientes sem comprar há mais de 60 dias (ou sem compra registrada). Uma campanha de reativação com VOLTEI15 pode trazê-los de volta.", "action_label": "CRIAR CUPOM VOLTEI15", "action": "coupon_code", "code": "VOLTEI15", "value": 15})
        stale = conn.execute("SELECT COUNT(*) c FROM leads WHERE company_id=? AND stage='Proposta'", (cid,)).fetchone()["c"]
        if stale:
            insights.append({"icon": "📞", "text": f"Existem {stale} leads que receberam proposta e ainda aguardam acompanhamento. Follow-up rápido aumenta a chance de fechamento.", "action_label": "ABRIR CRM", "action": "go", "target": "crm"})
        carts = conn.execute("SELECT COUNT(*) c, COALESCE(SUM(total),0) s FROM carts WHERE company_id=? AND status='abandonado'", (cid,)).fetchone()
        if carts["c"]:
            insights.append({"icon": "🛒", "text": f"{carts['c']} carrinhos abandonados somam {brl(carts['s'])} em potencial. Ative a recuperação automática (lembrete + segunda mensagem + cupom opcional).", "action_label": "EXECUTAR RECUPERAÇÃO", "action": "run_automations", "target": "automacoes"})
        month = conn.execute("SELECT COALESCE(SUM(total),0) s, COUNT(*) n FROM orders WHERE company_id=? AND status IN ('pago','entregue','concluido') AND strftime('%Y-%m',created_at)=strftime('%Y-%m','now')", (cid,)).fetchone()
        goal = float(company["goal_monthly"] or 6000)
        if month["n"]:
            ticket = month["s"] / month["n"]
            insights.append({"icon": "🎯", "text": f"Ticket médio do mês: {brl(ticket)} em {month['n']} pedidos. Faltam {brl(max(goal-month['s'],0))} para a meta de {brl(goal)} — planejamento, não garantia.", "action_label": "VER METAS", "action": "go", "target": "metas"})
        vips = conn.execute("SELECT COUNT(*) c FROM customers WHERE company_id=? AND vip=1", (cid,)).fetchone()["c"]
        if vips:
            insights.append({"icon": "👑", "text": f"Você tem {vips} clientes VIP. Ofereça acesso antecipado e cupom CLIENTEVIP para aumentar recompra.", "action_label": "VER CLIENTES VIP", "action": "go", "target": "clientes"})
        return insights

    def reports(self, conn, company):
        cid = company["id"]
        by_product = [dict(r) for r in conn.execute("SELECT p.name, COALESCE(SUM(oi.qty),0) qty, COALESCE(SUM(oi.qty*oi.price),0) revenue FROM products p LEFT JOIN order_items oi ON oi.product_id=p.id AND oi.company_id=? WHERE p.company_id=? GROUP BY p.id ORDER BY revenue DESC", (cid, cid))]
        by_channel = [dict(r) for r in conn.execute("SELECT channel, COUNT(*) orders, COALESCE(SUM(total),0) revenue FROM orders WHERE company_id=? GROUP BY channel ORDER BY revenue DESC", (cid,))]
        by_campaign = [dict(r) for r in conn.execute("SELECT name, status, channel, objective FROM campaigns WHERE company_id=? ORDER BY id DESC", (cid,))]
        coupons = [dict(r) for r in conn.execute("SELECT code, used, type, value FROM coupons WHERE company_id=? ORDER BY used DESC", (cid,))]
        monthly = []
        for i in range(5, -1, -1):
            d = datetime.date.today().replace(day=1) - datetime.timedelta(days=i * 30)
            label = d.strftime("%Y-%m")
            row = conn.execute("SELECT COALESCE(SUM(total),0) s, COALESCE(SUM(profit),0) p, COUNT(*) n FROM orders WHERE company_id=? AND status IN ('pago','entregue','concluido') AND strftime('%Y-%m',created_at)=?", (cid, label)).fetchone()
            monthly.append({"label": label, "revenue": row["s"], "profit": row["p"], "orders": row["n"]})
        totals = conn.execute("SELECT COALESCE(SUM(total),0) revenue, COALESCE(SUM(profit),0) profit, COUNT(*) orders FROM orders WHERE company_id=? AND status IN ('pago','entregue','concluido')", (cid,)).fetchone()
        return self.send_json({"by_product": by_product, "by_channel": by_channel, "by_campaign": by_campaign, "coupons": coupons, "monthly": monthly, "totals": dict(totals)})

    def run_automations(self, conn, company, user):
        cid = company["id"]
        runs = []
        carts = conn.execute("SELECT * FROM carts WHERE company_id=? AND status='abandonado'", (cid,)).fetchall()
        wa_cfg = integ.get_config(conn, cid, "whatsapp", active_only=True)
        wa_ready = integ.configured_status("whatsapp", wa_cfg)[0]
        for cart in carts:
            first = (cart["customer_name"] or "você").split(" ")[0]
            msg = (f"Oi, {first}! Seu pedido na {company['name']} ainda está esperando por você 🛒 ({cart['items'] or 'seus itens'} — {brl(cart['total'])}). Quer que eu finalize para você?"
                   if cart["stage"] == 0 else
                   f"Oi, {first}! Passando para lembrar do seu pedido na {company['name']} 💛 Se fechar hoje, consigo te ajudar com um cupom especial. Posso finalizar?")
            # cliente vinculado (consentimento) por telefone/nome
            cust = None
            for cand in conn.execute("SELECT * FROM customers WHERE company_id=?", (cid,)).fetchall():
                cd_ = re.sub(r"\D", "", cand["phone"] or "")
                ct_ = re.sub(r"\D", "", cart["phone"] or "")
                if (ct_ and cd_ and cd_.endswith(ct_[-11:])) or cand["name"] == cart["customer_name"]:
                    cust = cand
                    break
            status_log, sent_real = "na fila — WhatsApp Cloud API não configurada", False
            if wa_ready and cart["phone"] and (cust is None or cust["consent"]):
                try:
                    wamid, _ = integ.whatsapp_send(wa_cfg, cart["phone"], msg)
                    status_log, sent_real = "enviado via WhatsApp Cloud API", True
                    conn.execute("INSERT INTO messages(company_id,customer_id,channel,content,status,external_id,created_at) VALUES(?,?,?,?,?,?,?)",
                                 (cid, cust["id"] if cust else None, "WhatsApp", msg, status_log, wamid, now()))
                except IntegrationError as e:
                    status_log = f"falha no envio WhatsApp: {e} {integ.provider_error_detail(e.detail)}"[:240]
                    conn.execute("INSERT INTO messages(company_id,customer_id,channel,content,status,created_at) VALUES(?,?,?,?,?,?)",
                                 (cid, cust["id"] if cust else None, "WhatsApp", msg, status_log, now()))
            elif cust is not None and not cust["consent"]:
                status_log = "bloqueado — cliente sem consentimento (LGPD)"
                conn.execute("INSERT INTO messages(company_id,customer_id,channel,content,status,created_at) VALUES(?,?,?,?,?,?)",
                             (cid, cust["id"], "WhatsApp", msg, status_log, now()))
            else:
                conn.execute("INSERT INTO messages(company_id,customer_id,channel,content,status,created_at) VALUES(?,?,?,?,?,?)",
                             (cid, cust["id"] if cust else None, "WhatsApp", msg, status_log, now()))
            conn.execute("UPDATE carts SET stage=stage+1, updated_at=? WHERE id=?", (now(), cart["id"]))
            runs.append(f"Recuperação de carrinho: {'✅ enviado via WhatsApp' if sent_real else status_log} para {cart['customer_name']} ({brl(cart['total'])})")
        inactive = conn.execute("SELECT * FROM customers WHERE company_id=? AND (last_purchase IS NULL OR last_purchase < date('now','-60 day'))", (cid,)).fetchall()
        for cust in inactive:
            exists = conn.execute("SELECT id FROM opportunities WHERE company_id=? AND name=? AND status='Nova'", (cid, cust["name"])).fetchone()
            if not exists:
                conn.execute("INSERT INTO opportunities(company_id,name,segment,city,phone,email,source,status,potential,notes,last_interaction,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                             (cid, cust["name"], "Cliente inativo", cust["city"], cust["phone"], cust["email"], "Automação IA", "Nova", "Médio", "Cliente sem comprar há 60+ dias — sugerir reativação com VOLTEI15 (somente com consentimento).", today(), now()))
                runs.append(f"Reativação: oportunidade criada para {cust['name']}")
        low = conn.execute("SELECT * FROM products WHERE company_id=? AND stock<=20", (cid,)).fetchall()
        for p in low:
            runs.append(f"Estoque baixo: {p['name']} ({p['stock']} un.) — alerta gerado")
            notify(conn, cid, "Estoque baixo ⚠️", f"{p['name']} tem apenas {p['stock']} unidades.", "warning")
        for auto in conn.execute("SELECT * FROM automations WHERE company_id=? AND active=1", (cid,)).fetchall():
            conn.execute("INSERT INTO automation_runs(company_id,automation_id,description,created_at) VALUES(?,?,?,?)", (cid, auto["id"], f"Verificação executada: {auto['name']}", now()))
        if not runs:
            runs = ["Verificação concluída: nenhum carrinho, cliente inativo ou estoque baixo no momento."]
        ai_log(conn, cid, "automations_run", "; ".join(runs)[:200])
        log_audit(conn, cid, user["id"], "automations_run", "; ".join(runs)[:200])
        return self.send_json({"runs": runs, "message": "Automações verificadas. Mensagens externas só são enviadas com integração oficial + consentimento do cliente."})

if __name__ == "__main__":
    init_db()
    print(f"ProdutoVenda IA rodando em http://0.0.0.0:{PORT}  |  Demo: demo@produtovenda.com.br / demo1234")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
