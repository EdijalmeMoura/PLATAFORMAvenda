#!/usr/bin/env python3
"""
ProdutoVenda IA — Central de Vendas Autônomas com IA
Backend monolitico (Python stdlib apenas): HTTP + SQLite + autenticacao + multi-tenant + motor de IA local.
Nenhuma dependencia externa. Dados persistentes em plataformavenda.db
"""
import json, os, re, sqlite3, hashlib, secrets, random, datetime, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import integrations as integ
from integrations import IntegrationError

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, "plataformavenda.db")
STATIC = os.path.join(BASE, "static")
PORT = int(os.environ.get("PORT", "8000"))

# ---------------------------------------------------------------- DB
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

SCHEMA = """
CREATE TABLE IF NOT EXISTS plans(id INTEGER PRIMARY KEY, name TEXT, price REAL, limits TEXT);
CREATE TABLE IF NOT EXISTS companies(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, slug TEXT UNIQUE, segment TEXT DEFAULT 'Chocolates e Doces',
  city TEXT DEFAULT '', region TEXT DEFAULT '', whatsapp TEXT DEFAULT '', email TEXT DEFAULT '', goal_monthly REAL DEFAULT 6000, goal_weekly REAL DEFAULT 1500,
  goal_daily REAL DEFAULT 200, autopilot TEXT DEFAULT 'assistido', plan_id INTEGER DEFAULT 3, onboarded INTEGER DEFAULT 0, created_at TEXT);
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER, name TEXT, email TEXT UNIQUE, pass_hash TEXT, salt TEXT,
  role TEXT DEFAULT 'owner', is_platform_admin INTEGER DEFAULT 0, created_at TEXT);
CREATE TABLE IF NOT EXISTS sessions(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, token_hash TEXT, created_at TEXT, expires_at TEXT);
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
    conn.commit()
    seed(conn)
    conn.close()

# ---------------------------------------------------------------- HTTP helpers
LOGIN_ATTEMPTS = {}
def rate_limited(key):
    now_ts = datetime.datetime.now().timestamp()
    attempts = [t for t in LOGIN_ATTEMPTS.get(key, []) if now_ts - t < 900]
    LOGIN_ATTEMPTS[key] = attempts
    return len(attempts) >= 10

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_text(self, text, status=200):
        body = str(text).encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def base_url(self):
        host = self.headers.get("Host") or "localhost:8000"
        proto = self.headers.get("X-Forwarded-Proto") or ("https" if host.endswith(".e2b.app") or ".app" in host else "http")
        return f"{proto}://{host}"

    def body_json(self):
        length = int(self.headers.get("Content-Length") or 0)
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

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path.startswith("/api/"):
            return self.api("POST", parsed.path, {}, self.body_json())
        self.send_json({"error": "not found"}, 404)

    def do_PUT(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path.startswith("/api/"):
            return self.api("PUT", parsed.path, {}, self.body_json())
        self.send_json({"error": "not found"}, 404)

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path.startswith("/api/"):
            return self.api("DELETE", parsed.path, {}, {})
        self.send_json({"error": "not found"}, 404)

    def serve_static(self, path):
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
        self.end_headers()
        self.wfile.write(data)

    # ---------- API
    def api(self, method, path, query, data):
        conn = db()
        try:
            result = self.route(conn, method, path, query, data)
            conn.commit()
            return result
        except Exception as e:
            conn.rollback()
            return self.send_json({"error": f"Erro interno: {e}"}, 500)
        finally:
            conn.close()

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
            company = conn.execute("SELECT * FROM companies WHERE slug=?", (m.group(1),)).fetchone()
            if not company:
                return self.send_json({"error": "Loja não encontrada"}, 404)
            return self.public_checkout(conn, company, data)

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
                    if cfg.get("verify_token") and cfg["verify_token"] == token:
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

        # Auth
        if path == "/api/auth/register" and method == "POST":
            return self.register(conn, data)
        if path == "/api/auth/login" and method == "POST":
            return self.login(conn, data)

        user, company = self.require_auth(conn)
        if not user:
            return
        cid = user["company_id"]

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
            conn.execute("UPDATE companies SET name=?, segment=?, city=?, region=?, whatsapp=?, email=?, goal_monthly=?, goal_weekly=?, goal_daily=?, autopilot=? WHERE id=?",
                         (data.get("name", company["name"]), data.get("segment", company["segment"]), data.get("city", ""), data.get("region", ""), data.get("whatsapp", ""), data.get("email", ""), float(data.get("goal_monthly") or 6000), float(data.get("goal_weekly") or 1500), float(data.get("goal_daily") or 200), data.get("autopilot", "assistido"), cid))
            conn.execute("INSERT INTO store_settings(company_id,store_name,logo,primary_color,banner,font,instagram,facebook,description) VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(company_id) DO UPDATE SET store_name=excluded.store_name, logo=excluded.logo, primary_color=excluded.primary_color, banner=excluded.banner, font=excluded.font, instagram=excluded.instagram, facebook=excluded.facebook, description=excluded.description",
                         (cid, data.get("store_name", "Minha Loja"), data.get("logo", "🛍️"), data.get("primary_color", "#7c3aed"), data.get("banner", ""), data.get("font", "Inter"), data.get("instagram", ""), data.get("facebook", ""), data.get("store_description", data.get("description", ""))))
            log_audit(conn, cid, user["id"], "settings_update", "Configurações atualizadas")
            return self.send_json({"ok": True})

        if path == "/api/admin" and method == "GET":
            plans = [dict(r) for r in conn.execute("SELECT * FROM plans ORDER BY price")]
            users = [dict(r) for r in conn.execute("SELECT id,name,email,role,created_at FROM users WHERE company_id=?", (cid,))]
            usage = conn.execute("SELECT COUNT(*) actions, COALESCE(SUM(tokens),0) tokens FROM ai_usage WHERE company_id=? AND strftime('%Y-%m',created_at)=strftime('%Y-%m','now')", (cid,)).fetchone()
            audit = [dict(r) for r in conn.execute("SELECT * FROM audit_logs WHERE company_id=? ORDER BY id DESC LIMIT 15", (cid,))]
            counts = {t: conn.execute(f"SELECT COUNT(*) c FROM {t} WHERE company_id=?", (cid,)).fetchone()["c"] for t in ["products", "customers", "leads", "campaigns", "orders"]}
            integ_items = integ.list_integrations(conn, cid)
            return self.send_json({"plans": plans, "users": users, "usage": dict(usage), "audit": audit, "counts": counts,
                                   "integrations": [{"name": i["name"], "status": i["status"], "desc": i["desc"]} for i in integ_items]})
        if path == "/api/admin/plan" and method == "POST":
            conn.execute("UPDATE companies SET plan_id=? WHERE id=?", (int(data.get("plan_id")), cid))
            log_audit(conn, cid, user["id"], "plan_change", f"Plano alterado para {data.get('plan_id')}")
            return self.send_json({"ok": True, "message": "Plano atualizado (estrutura preparada para billing real)."})

        return self.send_json({"error": "Rota não encontrada"}, 404)

    # ---------- CRUD generico (sempre filtrado por tenant)
    TABLES = {
        "products": ["category_id", "name", "description", "price", "cost", "stock", "audience", "icon", "status"],
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
            cols = [f for f in fields if f in data]
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
        cur = conn.execute("INSERT INTO payments(company_id,order_id,provider,external_id,method,amount,status,qr_code,qr_code_base64,checkout_url,raw,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                           (cid, order["id"] if order else None, "mercadopago", result["external_id"], method, amount, result["status"], qr, qrb64, result.get("checkout_url", ""), json.dumps(result.get("raw", {}), ensure_ascii=False)[:8000], now(), now()))
        log_audit(conn, cid, user["id"], "payment_create", f"{method} {amount} ext={result['external_id']}")
        payment = dict(conn.execute("SELECT * FROM payments WHERE id=?", (cur.lastrowid,)).fetchone())
        payment.pop("raw", None)
        return self.send_json({"payment": payment, "message": "✅ Pix gerado no Mercado Pago! Envie o QR Code/copia e cola ao cliente." if method != "card" else "✅ Link de pagamento (Checkout Pro) gerado! Envie o link ao cliente."}, 201)

    def public_checkout(self, conn, company, data):
        cid = company["id"]
        items = data.get("items") or []
        if not items:
            return self.send_json({"error": "Carrinho vazio."}, 400)
        name = data.get("customer_name") or "Cliente da loja"
        total, profit = 0.0, 0.0
        lines = []
        for it in items:
            product = conn.execute("SELECT * FROM products WHERE id=? AND company_id=?", (it.get("product_id"), cid)).fetchone()
            if not product:
                continue
            qty = max(int(it.get("qty") or 1), 1)
            if (product["stock"] or 0) < qty:
                return self.send_json({"error": f"Estoque insuficiente para {product['name']}."}, 400)
            total += float(product["price"]) * qty
            profit += (float(product["price"]) - float(product["cost"] or 0)) * qty
            lines.append((product, qty))
        discount = 0.0
        coupon_row = None
        if data.get("coupon"):
            coupon_row = conn.execute("SELECT * FROM coupons WHERE company_id=? AND UPPER(code)=UPPER(?) AND active=1", (cid, data["coupon"])).fetchone()
            if not coupon_row:
                return self.send_json({"error": "Cupom inválido ou inativo."}, 400)
            if coupon_row["limit_uses"] and coupon_row["used"] >= coupon_row["limit_uses"]:
                return self.send_json({"error": "Cupom esgotado."}, 400)
            if total < float(coupon_row["min_value"] or 0):
                return self.send_json({"error": f"Este cupom exige compra mínima de {brl(coupon_row['min_value'])}."}, 400)
            discount = total * float(coupon_row["value"]) / 100 if coupon_row["type"] == "percentual" else float(coupon_row["value"])
        total = round(total - discount, 2)
        customer = conn.execute("SELECT * FROM customers WHERE company_id=? AND (phone=? OR email=?)", (cid, data.get("phone", ""), data.get("email", ""))).fetchone() if (data.get("phone") or data.get("email")) else None
        if not customer:
            cur = conn.execute("INSERT INTO customers(company_id,name,email,phone,city,segment,referral_code,created_at) VALUES(?,?,?,?,?,?,?,?)",
                               (cid, name, data.get("email", ""), data.get("phone", ""), "", "Cliente da loja", "LOJA" + str(random.randint(1000, 9999)), now()))
            customer = conn.execute("SELECT * FROM customers WHERE id=?", (cur.lastrowid,)).fetchone()
            conn.execute("INSERT INTO messages(company_id,customer_id,channel,content,status,created_at) VALUES(?,?,?,?,?,?)",
                         (cid, customer["id"], "WhatsApp", f"Oi, {name.split()[0]}! 😊 Bem-vindo(a)! Use BEMVINDO10 na próxima compra.", "registrado (boas-vindas automática)", now()))
        payment_method = (data.get("payment_method") or "manual").lower()
        mp_cfg = integ.get_config(conn, cid, "mercadopago", active_only=True)
        use_gateway = payment_method in ("pix", "card") and integ.configured_status("mercadopago", mp_cfg)[0]
        order_status = "aguardando pagamento" if use_gateway else "pago"
        cur = conn.execute("INSERT INTO orders(company_id,customer_id,customer_name,total,profit,status,channel,coupon,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                           (cid, customer["id"], name, total, round(profit, 2), order_status, "Loja", (coupon_row["code"] if coupon_row else ""), now()))
        order_id = cur.lastrowid
        for product, qty in lines:
            conn.execute("INSERT INTO order_items(company_id,order_id,product_id,product_name,qty,price) VALUES(?,?,?,?,?,?)", (cid, order_id, product["id"], product["name"], qty, product["price"]))
            conn.execute("UPDATE products SET stock=stock-?, sales=COALESCE(sales,0)+? WHERE id=?", (qty, qty, product["id"]))
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
                cur = conn.execute("INSERT INTO payments(company_id,order_id,provider,external_id,method,amount,status,qr_code,qr_code_base64,checkout_url,raw,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                   (cid, order_id, "mercadopago", result["external_id"], payment_method, total, result["status"], qr, qrb64, result.get("checkout_url", ""), json.dumps(result.get("raw", {}), ensure_ascii=False)[:8000], now(), now()))
                payment_info = {"id": cur.lastrowid, "method": payment_method, "status": result["status"], "qr_code": qr, "qr_code_base64": qrb64, "checkout_url": result.get("checkout_url", "")}
            except IntegrationError as e:
                payment_info = {"method": payment_method, "status": "erro", "error": f"{e} {integ.provider_error_detail(e.detail)}".strip()}
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
        for cart in carts:
            msg = "Oi! Seu pedido ainda está esperando por você 🍫 Quer que eu finalize para você?" if cart["stage"] == 0 else "Passando para lembrar do seu pedido 💛 Posso aplicar um cupom especial se você fechar hoje."
            conn.execute("INSERT INTO messages(company_id,channel,content,status,created_at) VALUES(?,?,?,?,?)", (cid, "WhatsApp", f"[{cart['customer_name']}] {msg}", "registrado — recuperação de carrinho (envio via integração oficial quando conectada)", now()))
            conn.execute("UPDATE carts SET stage=stage+1, updated_at=? WHERE id=?", (now(), cart["id"]))
            runs.append(f"Recuperação de carrinho: mensagem registrada para {cart['customer_name']} ({brl(cart['total'])})")
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
