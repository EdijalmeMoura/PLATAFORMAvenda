# 🚀 ProdutoVenda IA — Central de Vendas Autônomas com IA

> **Você cadastra o que vende. A IA ajuda a transformar isso em vendas.**

Plataforma SaaS completa (v1 funcional) que reúne em um único sistema:
**LOJA + CRM + PROSPECÇÃO + MARKETING + WHATSAPP + E-MAIL + AUTOMAÇÃO + CUPONS + PÓS-VENDA + ANALYTICS + INTELIGÊNCIA ARTIFICIAL** — tudo conectado e com dados persistentes.

Fluxo central: **CADASTRAR PRODUTO → IA ANALISA → CRIA LOJA → CRIA CAMPANHAS → ENCONTRA CLIENTES → VENDE → ACOMPANHA → RECUPERA CLIENTES → ANALISA RESULTADOS**

Funciona para qualquer segmento (Modo Produto): chocolates, bolos, pizzas, hambúrgueres, roupas, cosméticos, perfumes, artesanato, presentes, produtos digitais, serviços e mais.

---

## ▶️ Como rodar

Sem nenhuma dependência externa (só Python 3.10+):

```bash
python3 server.py
# abre http://localhost:8000
```

### 🐳 Com Docker (produção)

```bash
cp .env.example .env   # defina PV_MASTER_KEY forte
docker compose up -d --build
# http://localhost:8000/api/health -> {"status":"ok", ...}
```

### 🧪 Testes automatizados

```bash
python3 -m unittest discover -s tests -v   # 6 smoke tests com servidor+banco temporários
```

Cobrem: health, login/dashboard, isolamento multi-tenant, loja pública (carrinho salvo → checkout com cupom → avaliação), integrações (segredo mascarado **e criptografado em repouso**), webhook do WhatsApp, recuperação de senha completa e exportação sem segredos.

### 🔑 Conta de demonstração (caso de uso inicial: Chocolates 🍫)

| Campo | Valor |
|---|---|
| E-mail | `demo@produtovenda.com.br` |
| Senha | `demo1234` |

A demo vem com a empresa fictícia **Choco Encanto** (Recife): 5 produtos (Caixa 6/12/Premium, Kit Presente, Kit Corporativo), clientes, leads no CRM, pedidos dos últimos 30 dias, cupons, campanhas, automações, oportunidades e avaliações. O segmento pode ser trocado a qualquer momento em **Configurações**.

Também é possível **criar uma conta nova**: o onboarding em 8 passos (negócio → o que vende → produto → preço/custo → região → WhatsApp → redes → IA prepara a primeira campanha) já gera a página do produto e a primeira campanha automaticamente.

---

## 🧩 Módulos implementados (todos funcionais, com persistência em SQLite)

| Área | O que faz |
|---|---|
| **Dashboard** | Faturamento hoje/mês, lucro estimado, pedidos, ticket médio, clientes, leads, conversão, top produtos, gráfico de 14 dias, carrinhos abandonados, follow-ups e **META DO MÊS** com barra de progresso e cálculo de pedidos necessários (planejamento, sem promessa de resultado) |
| **🚀 Central de Vendas IA** | 9 ações rápidas (Encontrar clientes, Criar campanha, Gerar oferta, Criar cupom, Recuperar clientes, Gerar conteúdo, Enviar follow-up, Analisar vendas, Melhorar loja) + comando *"O que você quer vender hoje?"* |
| **🤖 Sales Agent IA** | Chat que analisa produtos/vendas/clientes e responde com plano + botões executáveis: `[CRIAR CAMPANHA]` `[CRIAR CUPOM]` `[ENCONTRAR CLIENTES]` `[CRIAR MENSAGENS]` `[RECUPERAR CARRINHOS]`… |
| **Modo Produto** | Cadastro simples (nome, preço, custo, estoque, público) → IA gera descrição comercial, benefícios, diferenciais, FAQ, CTA e urgência verdadeira (estoque) |
| **Minha Store** | Loja pública automática por empresa (`#/loja/<slug>`): vitrine, página de produto, avaliações, carrinho, checkout com cupom validado, baixa de estoque e pedido real no painel. Personalização de nome, logo, cor, banner e descrição |
| **Pedidos / Clientes** | CRUD completo, lucro por pedido, Clientes VIP, código de indicação (*Indique e ganhe*), consentimento LGPD por cliente |
| **CRM Kanban** | 9 etapas (Novo Lead → … → Pós-venda/Perdido) com arrastar-e-soltar, valor, potencial e **próxima ação sugerida pela IA** em cada card |
| **Oportunidades + Prospecção IA** | Filtros por cidade/segmento/produto/potencial, ações `CONTATAR` (mensagem pronta), `CRIAR PROPOSTA`, `ADICIONAR CRM`. Apenas fontes permitidas — ver nota de ética abaixo |
| **Campanhas IA** | Gerador completo: estratégia, oferta, anúncio, post, story, roteiro de vídeo, WhatsApp, e-mail, follow-ups e cupom sugerido + 5 conteúdos agendados |
| **Cupons** | Percentual/fixo, primeira compra, VIP, retorno, valor mínimo, limite de usos; sugestões automáticas da IA; validação real no checkout |
| **Recuperação & Automações** | Construtor **QUANDO X → FAZER Y**: carrinho abandonado (lembrete → 2ª mensagem → cupom opcional), cliente inativo 60d, estoque baixo, pós-venda/avaliação, boas-vindas. Execução gera mensagens registradas, oportunidades de reativação e alertas |
| **Content Studio IA** | Gera Instagram, Stories, Reels, WhatsApp, E-mail, Facebook, Blog e Pinterest com calendário de agendamento |
| **WhatsApp / E-mail** | Templates, envio registrado em fila com checagem de consentimento, campanhas de e-mail com segmentação. Estrutura pronta para WhatsApp Cloud API e provedor de e-mail oficiais |
| **Propostas** | Gerador com IA (cliente, valor, desconto, validade, condições), compartilhar por link, imprimir/PDF |
| **Insights IA** | Calculados dos dados reais: produto líder, combo p/ ticket médio, clientes 60d+ inativos, leads com proposta parada, carrinhos, meta — cada um com `[EXECUTAR AÇÃO]` |
| **Relatórios** | Receita/lucro por mês, produtos, canais, campanhas e cupons com gráficos |
| **Metas** | Mensal/semanal/diária configuráveis com cálculo de pedidos e ticket necessários |
| **Autopilot IA** | Manual / Assistido / Automático — ações externas sensíveis sempre exigem aprovação ou integração autorizada |
| **Admin & Planos** | FREE/STARTER/PRO/BUSINESS com limites configuráveis, usuários, uso de IA, integrações, logs de auditoria e métricas por tenant |

## 🏗️ Arquitetura

```
server.py          Backend monolítico (Python stdlib): HTTP, API REST, auth, motor de IA local, seed
static/index.html  Shell da SPA
static/styles.css  Design system premium (responsivo, dark/light)
static/app.js      SPA completa (22 módulos)
plataformavenda.db SQLite (criado automaticamente; ignorado no Git)
```

- **Banco**: 30+ tabelas (`users, companies, products, customers, leads/crm, orders, order_items, coupons, coupon_usages, campaigns, campaign_contents, automations, automation_runs, messages, message_templates, proposals, reviews, referrals, store_settings, carts, ai_conversations, ai_actions, ai_usage, notifications, subscriptions/plans, audit_logs`…), sempre com `company_id`, índices de uso e timestamps.
- **Multi-tenant**: toda query é filtrada pelo `company_id` da sessão — nenhum tenant acessa dados de outro (testado).
- **Motor de IA local e determinístico**: gera páginas, campanhas e respostas a partir do segmento do negócio e dos dados reais do tenant, **sem precisar de chave de API**. A arquitetura permite plugar um LLM externo depois (OpenAI etc.) nas mesmas rotas `/api/ai/*`, `/api/campaigns/generate` e `/api/content/generate`.

## 🔐 Segurança & LGPD

- Senhas com **PBKDF2-HMAC-SHA256** (200k iterações + salt), sessões com token hasheado e expiração, **rate limiting** no login, queries parametrizadas, validação de entrada, logs de auditoria.
- **Credenciais das integrações criptografadas em repouso** (ChaCha20 + HMAC-SHA256, chave-mestra fora do banco via `PV_MASTER_KEY` ou `.pv_master_key` 0600, com migração transparente de valores antigos) e sempre mascaradas na API.
- **Recuperação de senha** com token de uso único (1h, hasheado) enviado por SMTP quando configurado; logout invalida a sessão no servidor.
- Headers de segurança (`nosniff`, `X-Frame-Options`, `Referrer-Policy`…), `/api/health` para monitoramento e **exportação de dados** da empresa em JSON (sem senhas/segredos) em Admin.
- **Nada de spam/scraping**: mensagens comerciais só para clientes com consentimento registrado (o servidor bloqueia o envio sem opt-in), prospecção desenhada para APIs autorizadas (ex.: Google Places), opt-out respeitado. Enquanto integrações oficiais (WhatsApp Cloud API, Meta, gateway de pagamento, e-mail) não estão conectadas, envios/publicações ficam **registrados em fila — nunca simulados como feitos**.

## 🧪 Testes rápidos da API

```bash
curl -X POST localhost:8000/api/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"demo@produtovenda.com.br","password":"demo1234"}'
# use o token retornado em: Authorization: Bearer <token>
# GET /api/dashboard · /api/insights · /api/reports · POST /api/ai/chat · /api/campaigns/generate …
```

## 🔌 Integrações reais (implementadas)

Configuráveis por empresa em **Admin & Planos → Integrações reais**, com credenciais mascaradas, **teste de conexão real** e webhooks — guia completo em [INTEGRACOES.md](INTEGRACOES.md):

| Integração | O que funciona de verdade |
|---|---|
| **WhatsApp Cloud API (Meta)** | Envio de texto/template pela Graph API, **recebimento de mensagens e status (lido/entregue) via webhook**, histórico no painel |
| **Mercado Pago** | **Pix com QR Code/copia e cola** e **cartão (Checkout Pro)** na loja e no botão *Cobrar* dos pedidos; webhook/IPN marca o pedido como pago automaticamente |
| **SMTP** | Envio real de e-mail (Central, clientes e campanhas em massa para consentidos) |
| **Google Places API (New)** | Prospecção IA com empresas reais (endereço, telefone comercial, site, avaliação) |
| **Meta Social** | Teste/validação de Página do Facebook/Instagram pelas APIs oficiais |

Sem credencial configurada, nada é simulado: envios ficam em fila, cobranças não são criadas e o erro do provedor é mostrado com a explicação.

## 🔮 Próximos passos sugeridos

1. Trocar/complementar o motor de IA local por LLM externo com a chave da plataforma.
2. Billing real dos planos (assinaturas recorrentes) e domínio customizado por loja.
3. Publicação automática no Instagram após aprovação de permissões da Meta.
