/* ProdutoVenda IA — SPA */
const $ = (s, el=document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const money = (v) => "R$ " + Number(v || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const state = { token: localStorage.getItem("pv_token") || "", me: null, route: "dashboard", cart: [], publicData: null, pendingAi: "", dark: localStorage.getItem("pv_dark") === "1" };
if (state.dark) document.body.classList.add("dark");

async function api(path, method = "GET", body = null) {
  const res = await fetch(path, { method, headers: { "Content-Type": "application/json", ...(state.token ? { Authorization: "Bearer " + state.token } : {}) }, body: body ? JSON.stringify(body) : null });
  const data = await res.json().catch(() => ({}));
  if (res.status === 401 && state.token) { logout(false); }
  if (!res.ok) throw new Error(data.error || "Erro na requisição");
  return data;
}
function toast(msg, type = "") {
  const t = document.createElement("div"); t.className = "toast " + type; t.textContent = msg;
  $("#toast").appendChild(t); setTimeout(() => t.remove(), 5200);
}
function openModal(html, wide = false) { $("#modal-root").innerHTML = `<div class="modal-back" onclick="if(event.target===this)App.closeModal()"><div class="modal ${wide ? "wide" : ""}">${html}</div></div>`; }
function closeModal() { $("#modal-root").innerHTML = ""; }
function fieldHtml(f) {
  const v = f.value ?? "";
  if (f.type === "select") return `<label class="f">${esc(f.label)}</label><select id="mf-${f.name}">${(f.options || []).map(o => `<option value="${esc(typeof o === "object" ? o.value : o)}" ${String(typeof o === "object" ? o.value : o) === String(v) ? "selected" : ""}>${esc(typeof o === "object" ? o.label : o)}</option>`).join("")}</select>`;
  if (f.type === "textarea") return `<label class="f">${esc(f.label)}</label><textarea id="mf-${f.name}" placeholder="${esc(f.placeholder || "")}">${esc(v)}</textarea>`;
  if (f.type === "checkbox") return `<label class="f" style="display:flex;gap:9px;align-items:center"><input type="checkbox" id="mf-${f.name}" style="width:auto" ${v ? "checked" : ""}> ${esc(f.label)}</label>`;
  return `<label class="f">${esc(f.label)}</label><input id="mf-${f.name}" type="${f.type || "text"}" value="${esc(v)}" placeholder="${esc(f.placeholder || "")}" ${f.step ? `step="${f.step}"` : ""}>`;
}
function formModal(title, fields, submitLabel, onSubmit) {
  openModal(`<div class="row between"><h3 style="margin:0">${esc(title)}</h3><button class="icon-btn" onclick="App.closeModal()">✕</button></div>
  <form id="modal-form">${fields.map(fieldHtml).join("")}<div class="row mt"><button class="btn" type="submit">${esc(submitLabel)}</button><button class="btn ghost" type="button" onclick="App.closeModal()">Cancelar</button></div></form>`);
  $("#modal-form").onsubmit = async (e) => {
    e.preventDefault(); const out = {};
    fields.forEach(f => { const el = $("#mf-" + f.name); out[f.name] = f.type === "checkbox" ? (el.checked ? 1 : 0) : (f.type === "number" ? Number(el.value || 0) : el.value); });
    try { await onSubmit(out); closeModal(); } catch (err) { toast(err.message, "err"); }
  };
}
function badge(text, cls = "b-gray") { return `<span class="badge ${cls}">${esc(text)}</span>`; }
function thumbHtml(p, size = 52) {
  if (p.image) return `<img src="${esc(p.image)}" alt="${esc(p.name)}" style="width:${size}px;height:${size}px;border-radius:14px;object-fit:cover;flex:none;border:1px solid var(--line)">`;
  return `<span class="prod-thumb" style="width:${size}px;height:${size}px;font-size:${Math.round(size * 0.52)}px">${esc(p.icon || "🎁")}</span>`;
}
function statusBadge(s) { const map = { pago: "b-green", ativa: "b-green", ativo: "b-green", enviada: "b-violet", Proposta: "b-violet", Interessado: "b-violet", "Novo Lead": "b-amber", pendente: "b-amber", agendado: "b-amber", abandonado: "b-red", Perdido: "b-red", entregue: "b-green", "No CRM": "b-green" }; return badge(s || "-", map[s] || "b-gray"); }
async function copyText(text, msg = "Copiado!") { try { await navigator.clipboard.writeText(text); toast(msg, "ok"); } catch { toast("Copie manualmente: " + text); } }

/* ================= AUTH ================= */
function renderAuth(mode = "login") {
  $("#app").innerHTML = `<div class="auth-wrap">
    <div class="auth-hero">
      <span class="pill">🚀 Central de Vendas Autônomas com IA</span>
      <h1>Você cadastra o que vende. A IA transforma isso em vendas.</h1>
      <p>Loja + CRM + Prospecção + Campanhas + WhatsApp + E-mail + Cupons + Automações + Analytics — tudo conectado em uma única plataforma, para qualquer produto ou serviço.</p>
      <div class="flow"><span>CADASTRAR PRODUTO</span><i>→</i><span>IA ANALISA</span><i>→</i><span>CRIA LOJA</span><i>→</i><span>CRIA CAMPANHAS</span><i>→</i><span>ENCONTRA CLIENTES</span><i>→</i><span>VENDE</span><i>→</i><span>RECUPERA CLIENTES</span><i>→</i><span>ANALISA RESULTADOS</span></div>
      <p class="small" style="opacity:.85">🍫🍰🍕🍔👗💄🌸🎨🎁💻⭐ Funciona para chocolates, bolos, pizzas, roupas, cosméticos, artesanato, produtos digitais, serviços e muito mais.</p>
    </div>
    <div class="auth-card"><div class="auth-box">
      <div style="font-size:34px">🚀</div><h2>${mode === "login" ? "Entrar na plataforma" : "Criar sua conta grátis"}</h2>
      <p class="sub">${mode === "login" ? "Acesse sua Central de Vendas IA." : "Em minutos a IA monta sua operação de vendas."}</p>
      <form id="auth-form">
        ${mode === "register" ? `<label class="f">Seu nome</label><input id="a-name" required placeholder="Ex.: Maria Clara"><label class="f">Nome do seu negócio</label><input id="a-company" required placeholder="Ex.: Choco Encanto"><label class="f">O que você vende?</label><select id="a-segment">${["Chocolates e Doces", "Bolos e Confeitaria", "Pizzas", "Hambúrgueres e Lanches", "Roupas e Moda", "Cosméticos e Beleza", "Perfumes", "Artesanato", "Presentes", "Produtos Digitais", "Serviços", "Outro negócio"].map(s => `<option>${s}</option>`).join("")}</select><label class="f">Cidade</label><input id="a-city" placeholder="Ex.: Recife">` : ""}
        <label class="f">E-mail</label><input id="a-email" type="email" required placeholder="voce@empresa.com.br">
        <label class="f">Senha</label><input id="a-password" type="password" required placeholder="Mínimo 6 caracteres">
        <button class="btn block mt" type="submit">${mode === "login" ? "Entrar →" : "Criar conta e começar →"}</button>
      </form>
      ${mode === "login" ? `<p class="small mt"><button class="link-btn" onclick="App.forgotPassword()">Esqueci minha senha</button></p>` : ""}
      <p class="small mt">${mode === "login" ? 'Ainda não tem conta? <button class="link-btn" onclick="App.authMode(\'register\')">Criar conta grátis</button>' : 'Já tem conta? <button class="link-btn" onclick="App.authMode(\'login\')">Entrar</button>'}</p>
      <div class="demo-box"><b>🔑 Conta de demonstração (Chocolates):</b><br>E-mail: <b>demo@produtovenda.com.br</b><br>Senha: <b>demo1234</b><br><button class="btn sm mt" onclick="App.demoLogin()">Entrar na demonstração →</button></div>
      <p class="small mut mt">🔒 Senhas com hash PBKDF2, sessões seguras, isolamento por empresa (multi-tenant) e respeito à LGPD: nada de spam — comunicação só com consentimento.</p>
    </div></div></div>`;
  $("#auth-form").onsubmit = async (e) => {
    e.preventDefault();
    try {
      const payload = mode === "login"
        ? { email: $("#a-email").value, password: $("#a-password").value }
        : { name: $("#a-name").value, company_name: $("#a-company").value, segment: $("#a-segment").value, city: $("#a-city").value, email: $("#a-email").value, password: $("#a-password").value };
      const r = await api("/api/auth/" + mode, "POST", payload);
      state.token = r.token; localStorage.setItem("pv_token", r.token); toast(r.message || "Bem-vindo(a)!", "ok"); boot();
    } catch (err) { toast(err.message, "err"); }
  };
}
function logout(reload = true) { state.token = ""; state.me = null; localStorage.removeItem("pv_token"); if (reload) renderAuth(); }
function renderReset(token) {
  $("#app").innerHTML = `<div style="min-height:100vh;display:flex;align-items:center;justify-content:center;padding:22px"><div class="auth-box">
    <div style="font-size:34px">🔑</div><h2>Redefinir senha</h2><p class="sub">Escolha uma nova senha para sua conta (o link vale 1 hora e só pode ser usado uma vez).</p>
    <form id="reset-form"><label class="f">Nova senha</label><input id="r-pass" type="password" required placeholder="Mínimo 6 caracteres">
    <label class="f">Confirmar nova senha</label><input id="r-pass2" type="password" required>
    <button class="btn block mt" type="submit">Salvar nova senha →</button></form>
    <p class="small mt"><button class="link-btn" onclick="location.search='';location.hash='';location.reload()">Voltar ao login</button></p></div></div>`;
  $("#reset-form").onsubmit = async (e) => {
    e.preventDefault();
    if ($("#r-pass").value !== $("#r-pass2").value) return toast("As senhas não conferem.", "err");
    try { const r = await api("/api/auth/reset", "POST", { token, password: $("#r-pass").value }); toast(r.message, "ok"); history.replaceState({}, "", location.pathname); location.hash = ""; renderAuth(); }
    catch (err) { toast(err.message, "err"); }
  };
}

/* ================= SHELL ================= */
const NAV = [
  ["Principal", [["dashboard", "📊", "Dashboard"], ["central", "🚀", "Central de Vendas IA"], ["agente", "🤖", "Sales Agent IA"], ["insights", "💡", "Insights IA"]]],
  ["Vendas", [["produtos", "📦", "Produtos"], ["loja", "🏪", "Minha Store"], ["pedidos", "🧾", "Pedidos"], ["clientes", "👥", "Clientes"], ["crm", "🗂️", "CRM Kanban"], ["propostas", "📄", "Propostas"]]],
  ["Crescimento", [["oportunidades", "🎯", "Oportunidades"], ["prospeccao", "🔎", "Prospecção IA"], ["campanhas", "📣", "Campanhas IA"], ["cupons", "🎟️", "Cupons"], ["conteudo", "🎨", "Content Studio IA"], ["automacoes", "⚡", "Automações"]]],
  ["Relacionamento", [["whatsapp", "💬", "WhatsApp"], ["email", "✉️", "E-mail Marketing"]]],
  ["Gestão", [["relatorios", "📈", "Relatórios"], ["metas", "🏆", "Metas"], ["admin", "🛡️", "Admin & Planos"], ["configuracoes", "⚙️", "Configurações"]]],
];
function shell(contentHtml, title) {
  const unread = 0;
  $("#app").innerHTML = `<div class="shell">
    <aside class="sidebar" id="sidebar">
      <div class="logo"><div class="mark">🚀</div><div><b>ProdutoVenda IA</b><small>Central de Vendas com IA</small></div></div>
      ${NAV.map(([group, items]) => `<div class="nav-group">${group}</div>${items.map(([r, icon, label]) => `<button class="nav-item ${state.route === r ? "active" : ""}" onclick="App.go('${r}')">${icon} ${label}</button>`).join("")}`).join("")}
      <div class="side-foot"><b style="color:#fff">${esc(state.me.company.name)}</b><br>Plano <b style="color:#fff">${esc(state.me.plan?.name || "FREE")}</b> · ${esc(state.me.company.segment || "")}<br><span style="opacity:.75">${esc(state.me.company.city || "")}</span>
      <button class="btn sm block mt" style="background:rgba(255,255,255,.14)" onclick="App.openPublicStore()">🏪 Ver minha loja</button></div>
      <button class="nav-item" onclick="App.logout()">🚪 Sair</button>
    </aside>
    <div class="main">
      <div class="topbar">
        <button class="icon-btn menu-btn" onclick="document.getElementById('sidebar').classList.toggle('open')">☰</button>
        <h2>${esc(title)}</h2>
        <form class="command" id="command-form"><input id="command-input" placeholder="💬 O que você quer vender hoje? Ex.: Quero vender 20 caixas de chocolate"><button class="btn" type="submit">Perguntar à IA</button></form>
        <button class="icon-btn" title="Alternar tema" onclick="App.toggleDark()">${state.dark ? "☀️" : "🌙"}</button>
        <button class="icon-btn" title="Notificações" onclick="App.go('dashboard')">🔔</button>
        <div class="avatar" title="${esc(state.me.user.name)}">${esc((state.me.user.name || "U")[0].toUpperCase())}</div>
      </div>
      <div class="content">${contentHtml}</div>
    </div></div>`;
  $("#command-form").onsubmit = (e) => { e.preventDefault(); state.pendingAi = $("#command-input").value; App.go("agente"); };
}
function storeUrl() { return location.origin + location.pathname + "#/loja/" + state.me.company.slug; }
async function boot() {
  const resetToken = new URLSearchParams(location.search).get("reset_token");
  if (resetToken) return renderReset(resetToken);
  if (!state.token) return renderAuth();
  try { state.me = await api("/api/auth/me"); } catch { return renderAuth(); }
  if (!state.me.company.onboarded) return renderOnboarding();
  route();
}
function route() {
  const hash = location.hash.replace("#/", "") || "dashboard";
  if (hash.startsWith("loja/")) return renderPublicStore(hash.split("/")[1]);
  state.route = NAV.flatMap(g => g[1]).some(i => i[0] === hash) ? hash : "dashboard";
  const views = { dashboard: viewDashboard, central: viewCentral, agente: viewAgente, insights: viewInsights, produtos: viewProdutos, loja: viewLoja, pedidos: viewPedidos, clientes: viewClientes, crm: viewCrm, propostas: viewPropostas, oportunidades: viewOportunidades, prospeccao: viewProspeccao, campanhas: viewCampanhas, cupons: viewCupons, conteudo: viewConteudo, automacoes: viewAutomacoes, whatsapp: viewWhatsapp, email: viewEmail, relatorios: viewRelatorios, metas: viewMetas, admin: viewAdmin, configuracoes: viewConfig };
  (views[state.route] || viewDashboard)();
}
window.addEventListener("hashchange", route);

/* ================= ONBOARDING ================= */
let obStep = 0; const obData = {};
const OB_STEPS = [
  { t: "Qual é o seu negócio?", d: "Isso ajuda a IA a falar a linguagem dos seus clientes.", fields: [["company_name", "Nome do negócio", "text", "Ex.: Choco Encanto"], ["segment", "Segmento", "select", ["Chocolates e Doces", "Bolos e Confeitaria", "Pizzas", "Hambúrgueres e Lanches", "Roupas e Moda", "Cosméticos e Beleza", "Perfumes", "Artesanato", "Presentes", "Produtos Digitais", "Serviços", "Outro negócio"]]] },
  { t: "O que você vende?", d: "Descreva em poucas palavras — a IA usa isso nas campanhas.", fields: [["what", "O que você vende?", "text", "Ex.: Caixas de chocolates artesanais para presente"]] },
  { t: "Cadastre seu primeiro produto", d: "Só o essencial. A IA cria descrição, página e campanhas depois.", fields: [["product_name", "Nome do produto", "text", "Ex.: Caixa 12 Bombons"], ["icon", "Ícone do produto", "select", ["🍫", "🍬", "🎂", "🍕", "🍔", "👗", "💄", "🌸", "🎨", "🎁", "💻", "⭐"]]] },
  { t: "Defina preço e custo", d: "O custo é opcional, mas ajuda a IA a calcular seu lucro e sua meta.", fields: [["price", "Preço de venda (R$)", "number", "49.90"], ["cost", "Custo (R$)", "number", "22.00"], ["stock", "Estoque inicial", "number", "50"]] },
  { t: "Defina sua região", d: "A prospecção e as campanhas usam sua cidade e região.", fields: [["city", "Cidade", "text", "Ex.: Recife"], ["region", "Região de atendimento", "text", "Ex.: Recife e região metropolitana"]] },
  { t: "Conecte seu WhatsApp", d: "Usado no atendimento e nos pedidos da loja (integração oficial pode ser conectada depois).", fields: [["whatsapp", "WhatsApp com DDD", "text", "(81) 99999-0000"]] },
  { t: "Redes sociais (opcional)", d: "Você pode conectar Instagram/Facebook pelas APIs oficiais quando quiser.", fields: [["instagram", "Instagram (@)", "text", "@seunegocio"]] },
  { t: "A IA prepara sua primeira campanha ✨", d: "Ao concluir, geramos automaticamente a página do produto e uma campanha completa (copy, WhatsApp, post, cupom e conteúdos agendados).", fields: [["goal", "Meta de faturamento do mês (R$)", "number", "6000"]] },
];
function renderOnboarding() {
  const s = OB_STEPS[obStep];
  $("#app").innerHTML = `<div style="min-height:100vh;display:flex;align-items:center;justify-content:center;padding:22px"><div style="width:100%;max-width:620px">
    <div style="text-align:center;font-size:40px">🚀</div><h1 style="text-align:center;margin:6px 0">Vamos montar seu sistema de vendas</h1>
    <p class="mut" style="text-align:center">Passo ${obStep + 1} de ${OB_STEPS.length} · Você cadastra o que vende. A IA cuida do resto.</p>
    <div class="steps">${OB_STEPS.map((_, i) => `<div class="${i <= obStep ? "on" : ""}"></div>`).join("")}</div>
    <div class="card"><h3>${s.t}</h3><p class="mut">${s.d}</p><form id="ob-form">
      ${s.fields.map(([n, l, t, ex]) => t === "select" ? `<label class="f">${l}</label><select id="ob-${n}">${ex.map(o => `<option ${obData[n] === o ? "selected" : ""}>${o}</option>`).join("")}</select>` : `<label class="f">${l}</label><input id="ob-${n}" type="${t}" step="0.01" placeholder="${esc(Array.isArray(ex) ? "" : ex)}" value="${esc(obData[n] ?? "")}">`).join("")}
      <div class="row between mt"><button class="btn ghost" type="button" onclick="App.obBack()" ${obStep === 0 ? "disabled" : ""}>← Voltar</button>
      <button class="btn" type="submit">${obStep === OB_STEPS.length - 1 ? "✨ Criar tudo com IA" : "Continuar →"}</button></div>
      ${obStep >= 5 ? `<button class="link-btn mt" type="button" onclick="App.obSkip()">Pular esta etapa</button>` : ""}
    </form></div></div></div>`;
  $("#ob-form").onsubmit = async (e) => {
    e.preventDefault(); s.fields.forEach(([n]) => obData[n] = $("#ob-" + n).value);
    if (obStep < OB_STEPS.length - 1) { obStep++; return renderOnboarding(); }
    try {
      if (obData.product_name) {
        const p = await api("/api/products", "POST", { name: obData.product_name, price: Number(obData.price || 0), cost: Number(obData.cost || 0), stock: Number(obData.stock || 0), icon: obData.icon || "🎁", audience: obData.what || "", status: "ativo" });
        await api(`/api/products/${p.item.id}/generate-page`, "POST", {});
        await api("/api/campaigns/generate", "POST", { product_id: p.item.id, objective: "primeira campanha de vendas", audience: obData.what || "" });
      }
      await api("/api/auth/onboarding", "POST", { company_name: obData.company_name, segment: obData.segment, city: obData.city, region: obData.region, whatsapp: obData.whatsapp, goal_monthly: Number(obData.goal || 6000) });
      state.me = await api("/api/auth/me");
      openModal(`<div style="text-align:center;padding:12px"><div style="font-size:54px">🎉</div><h2>Seu sistema de vendas está pronto!</h2><p class="mut">Loja, página do produto e primeira campanha criados pela IA. Agora é só começar a vender — e pedir ajuda ao Sales Agent quando quiser.</p><button class="btn block" onclick="App.closeModal();App.go('dashboard')">🚀 COMEÇAR A VENDER</button></div>`);
      route();
    } catch (err) { toast(err.message, "err"); }
  };
}

/* ================= DASHBOARD ================= */
function barChart(series) {
  const max = Math.max(...series.map(s => s.value), 1); const w = 560, h = 150, bw = w / series.length;
  return `<svg viewBox="0 0 ${w} ${h}" style="width:100%">${series.map((s, i) => `<rect x="${i * bw + 5}" y="${h - 22 - (s.value / max) * (h - 42)}" width="${bw - 10}" height="${(s.value / max) * (h - 42)}" rx="5" fill="url(#grad)"><title>${s.label}: ${money(s.value)}</title></rect><text x="${i * bw + bw / 2}" y="${h - 6}" font-size="9" text-anchor="middle" fill="var(--muted)">${s.label.slice(3)}</text>`).join("")}<defs><linearGradient id="grad" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#7c3aed"/><stop offset="1" stop-color="#db2777"/></linearGradient></defs></svg>`;
}
async function viewDashboard() {
  shell(`<div class="card">Carregando seu painel…</div>`, "Dashboard");
  const [d, notifs] = await Promise.all([api("/api/dashboard"), api("/api/notifications")]);
  const k = d.kpis;
  const kpi = (lbl, val, sub, icon) => `<div class="card kpi"><div class="lbl">${icon} ${lbl}</div><div class="val">${val}</div><div class="sub">${sub}</div></div>`;
  shell(`
  <div class="card hero-ia"><div class="row between"><div><h3 style="font-size:21px">🚀 Central de Vendas IA</h3><p style="max-width:640px">Você cadastra o que vende. A IA ajuda a transformar isso em vendas — loja, campanhas, clientes, follow-up e recuperação trabalhando juntos.</p></div>${badge("Autopilot: " + state.me.company.autopilot, "b-violet")}</div>
    <div class="quick-actions">
      <button onclick="App.go('prospeccao')">🔎 Encontrar clientes</button><button onclick="App.quickCampaign()">📣 Criar campanha</button><button onclick="App.quickOffer()">🎁 Gerar oferta</button>
      <button onclick="App.quickCoupon()">🎟️ Criar cupom</button><button onclick="App.runAutomations()">💌 Recuperar clientes</button><button onclick="App.go('conteudo')">🎨 Gerar conteúdo</button>
      <button onclick="App.sendFollowup()">📲 Enviar follow-up</button><button onclick="App.go('relatorios')">📈 Analisar vendas</button><button onclick="App.go('loja')">🏪 Melhorar minha loja</button>
    </div></div>
  <div class="grid g4 mt">
    ${kpi("Faturamento hoje", money(k.revenue_today), "pedidos pagos de hoje", "💰")}${kpi("Faturamento do mês", money(k.revenue_month), k.orders_month + " pedidos no mês", "📅")}${kpi("Lucro estimado (mês)", money(k.profit_month), "preço − custo dos pedidos", "📈")}${kpi("Ticket médio", money(k.ticket), "por pedido pago", "🧾")}
    ${kpi("Clientes", k.customers, k.new_customers + " novos este mês", "👥")}${kpi("Leads ativos", k.leads, "no funil do CRM", "🎯")}${kpi("Taxa de conversão", k.conversion + "%", "leads que viraram Pago", "🔁")}${kpi("Follow-ups pendentes", k.followups, "leads aguardando contato", "📞")}
  </div>
  <div class="grid g2 mt">
    <div class="card"><div class="row between"><h3>🏆 META DO MÊS</h3>${badge(d.goal.percent + "%", "b-violet")}</div>
      <p class="mut">Meta configurável — é planejamento, não promessa de resultado.</p>
      <div class="row between mt"><span>Meta: <b>${money(d.goal.monthly)}</b></span><span>Vendido: <b>${money(d.goal.sold)}</b></span><span>Falta: <b>${money(d.goal.missing)}</b></span></div>
      <div class="progress mt"><div style="width:${d.goal.percent}%"></div></div>
      <p class="mt">💡 ${esc(d.goal.message)}</p>
      <button class="btn sm soft" onclick="App.go('metas')">Ajustar metas</button> <button class="btn sm" onclick="App.askAi('Quero vender mais esta semana para bater minha meta')">Pedir plano à IA</button></div>
    <div class="card"><h3>📊 Vendas — últimos 14 dias</h3>${barChart(d.series)}<p class="small mut">${esc(d.ai_tip)}</p></div>
  </div>
  <div class="grid g3 mt">
    <div class="card"><h3>🏆 Produtos mais vendidos</h3>${d.top_products.map(p => `<div class="row between" style="padding:8px 0;border-bottom:1px solid var(--line)"><span class="row"><span class="prod-thumb" style="width:38px;height:38px;font-size:19px">${esc(p.icon || "🎁")}</span>${esc(p.name)}</span><span>${badge((p.sales || 0) + " vendas", "b-violet")} <b>${money(p.price)}</b></span></div>`).join("") || '<p class="mut">Sem produtos ainda.</p>'}
      <div class="row mt">${badge("Campanhas ativas: " + k.campaigns_active, "b-green")} ${badge("Cupons utilizados: " + k.coupons_used, "b-violet")} ${badge("Carrinhos abandonados: " + k.abandoned_carts, "b-red")}</div></div>
    <div class="card"><h3>🧾 Pedidos recentes</h3>${d.recent_orders.map(o => `<div class="row between" style="padding:7px 0;border-bottom:1px solid var(--line)"><span>#${o.id} ${esc(o.customer_name)}<br><span class="small mut">${esc(o.channel)} · ${esc((o.created_at || "").slice(0, 10))}</span></span><span><b>${money(o.total)}</b> ${statusBadge(o.status)}</span></div>`).join("") || '<p class="mut">Nenhum pedido ainda — compartilhe sua loja!</p>'}</div>
    <div class="card"><h3>🔔 Notificações</h3>${notifs.notifications.map(n => `<div style="padding:8px 0;border-bottom:1px solid var(--line)"><b style="font-size:13.5px">${esc(n.title)}</b><p class="small mut" style="margin:2px 0">${esc(n.body)}</p></div>`).join("") || '<p class="mut">Tudo em dia por aqui.</p>'}</div>
  </div>`, "Dashboard");
}

/* ================= CENTRAL / AGENTE IA ================= */
async function viewCentral() {
  shell(`<div class="card hero-ia"><h3 style="font-size:24px">🚀 Central de Vendas IA</h3><p style="max-width:680px">Um comando e a IA monta o plano: campanha, cupom, prospecção, conteúdo, follow-up e recuperação — sempre com sua aprovação para ações externas.</p>
  <form id="central-form" class="row mt"><input id="central-input" style="flex:1;min-width:240px" placeholder="O que você quer vender hoje? Ex.: Quero vender 20 caixas de chocolate"><button class="btn" style="background:#fff;color:#6d28d9" type="submit">✨ Gerar plano com IA</button></form></div>
  <div class="grid g3 mt">${[
    ["🔎", "Encontrar clientes", "Prospecção IA por cidade, segmento e potencial.", "prospeccao"], ["📣", "Criar campanha", "Campanha completa: oferta, copies, WhatsApp, e-mail e agenda.", "__campaign"], ["🎁", "Gerar oferta", "Oferta do produto líder com página gerada por IA.", "__offer"],
    ["🎟️", "Criar cupom", "Cupons sugeridos pela estratégia (boas-vindas, VIP, retorno).", "cupons"], ["💌", "Recuperar clientes", "Carrinhos abandonados e clientes inativos de volta.", "__recover"], ["🎨", "Gerar conteúdo", "Posts, stories, reels, WhatsApp e e-mail no Content Studio.", "conteudo"],
    ["📲", "Enviar follow-up", "Sequências por etapa do funil, sem spam e com consentimento.", "crm"], ["📈", "Analisar vendas", "Relatórios e Insights IA com ações prontas.", "insights"], ["🏪", "Melhorar minha loja", "Páginas de produto, cores, banner e conversão.", "loja"],
  ].map(([i, t, d, r]) => `<div class="card"><div style="font-size:28px">${i}</div><h3>${t}</h3><p class="mut">${d}</p><button class="btn sm mt" onclick="App.centralAction('${r}')">Começar →</button></div>`).join("")}</div>`, "Central de Vendas IA");
  $("#central-form").onsubmit = (e) => { e.preventDefault(); state.pendingAi = $("#central-input").value; App.go("agente"); };
}
async function viewAgente() {
  shell(`<div class="grid" style="grid-template-columns:1.6fr 1fr;gap:16px">
    <div class="card"><h3>🤖 Sales Agent IA</h3><p class="mut">Seu vendedor digital: analisa produtos, vendas e clientes, cria ofertas, campanhas, cupons, mensagens, follow-ups e propostas. Experimente: <i>"Quero vender mais chocolates esta semana"</i>, <i>"Quero vender para empresas"</i> ou <i>"Quero recuperar clientes antigos"</i>.</p>
    <div class="chat-box mt" id="chat-box"><div class="msg bot">Olá! 👋 Sou o Sales Agent IA. Me diga o que você quer vender hoje e eu monto o plano com ações prontas para executar.</div></div>
    <form id="chat-form" class="row mt"><input id="chat-input" style="flex:1" placeholder="O que você quer vender hoje?"><button class="btn" type="submit">Enviar →</button></form></div>
    <div class="card"><h3>⚡ Autopilot IA</h3><p class="mut">Nível atual: <b>${esc(state.me.company.autopilot)}</b></p>
    ${[["manual", "Manual", "A IA só sugere. Você executa tudo."], ["assistido", "Assistido", "A IA cria campanhas, conteúdos e mensagens e coloca para sua aprovação."], ["automatico", "Automático", "A IA executa ações previamente autorizadas dentro dos seus limites. Ações externas sensíveis sempre exigem aprovação/integração."]].map(([v, l, d]) => `<label class="row" style="align-items:flex-start;padding:9px 0;border-bottom:1px solid var(--line)"><input type="radio" name="autopilot" value="${v}" style="width:auto;margin-top:3px" ${state.me.company.autopilot === v ? "checked" : ""} onchange="App.setAutopilot('${v}')"><span><b>${l}</b><br><span class="small mut">${d}</span></span></label>`).join("")}
    <h3 class="mt">🧠 O que eu faço</h3><p class="small mut">Analisar produtos e vendas · criar ofertas, campanhas e cupons · escrever mensagens · sugerir clientes · follow-ups · recuperar carrinhos · montar propostas · campanhas sazonais · analisar desempenho.</p></div></div>`, "Sales Agent IA");
  const send = async (text) => {
    if (!text.trim()) return;
    const box = $("#chat-box");
    box.insertAdjacentHTML("beforeend", `<div class="msg user">${esc(text)}</div>`); box.scrollTop = box.scrollHeight;
    try {
      const r = await api("/api/ai/chat", "POST", { message: text });
      const acts = (r.actions || []).map((a, i) => `<button class="btn sm" onclick='App.aiAction(${JSON.stringify(a).replace(/'/g, "&#39;")})'>${esc(a.label)}</button>`).join("");
      const plan = r.plan ? `<div style="margin-top:9px">${r.plan.map((p, i) => `<div>✅ ${i + 1}. ${esc(p)}</div>`).join("")}</div>` : "";
      box.insertAdjacentHTML("beforeend", `<div class="msg bot">${esc(r.reply)}${plan}${acts ? `<div class="msg-actions">${acts}</div>` : ""}</div>`);
    } catch (e) { box.insertAdjacentHTML("beforeend", `<div class="msg bot">⚠️ ${esc(e.message)}</div>`); }
    box.scrollTop = box.scrollHeight;
  };
  $("#chat-form").onsubmit = (e) => { e.preventDefault(); const v = $("#chat-input").value; $("#chat-input").value = ""; send(v); };
  if (state.pendingAi) { const p = state.pendingAi; state.pendingAi = ""; send(p); }
}

/* ================= PRODUTOS / LOJA ================= */
async function viewProdutos() {
  const { products } = await api("/api/products");
  shell(`<div class="row between mb"><div><p class="mut" style="margin:0">Cadastre um produto e a IA cria descrição comercial, página, campanhas, cupons e mensagens. Funciona para qualquer segmento — é o <b>Modo Produto</b>.</p></div><button class="btn" onclick="App.productForm()">+ Novo produto</button></div>
  ${products.length ? `<div class="grid g2">${products.map(p => { const margin = p.price ? Math.round((p.price - (p.cost || 0)) / p.price * 100) : 0; return `<div class="card"><div class="row">${thumbHtml(p)}<div style="flex:1"><b>${esc(p.name)}</b><br><span class="small mut">${esc(p.audience || "")}</span></div>${(p.stock || 0) <= 20 ? badge("Estoque baixo: " + p.stock, "b-red") : badge("Estoque: " + p.stock, "b-green")}</div>
    <p class="small mut mt" style="min-height:36px">${esc((p.description || "").slice(0, 130))}…</p>
    <div class="row small"><span>💰 <b>${money(p.price)}</b></span><span>Custo ${money(p.cost)}</span><span>Margem ${margin}%</span><span>🏆 ${p.sales || 0} vendas</span>${p.ai_page ? badge("Página IA ✓", "b-violet") : ""}</div>
    <div class="row mt"><button class="btn sm" onclick="App.generatePage(${p.id})">✨ GERAR PÁGINA COM IA</button><button class="btn sm soft" onclick="App.productImage(${p.id})">📷 ${p.image ? "Trocar foto" : "Enviar foto"}</button><button class="btn sm soft" onclick="App.campaignFor(${p.id})">📣 Campanha</button><button class="btn sm ghost" onclick="App.productForm(${p.id})">Editar</button><button class="btn sm ghost" onclick="App.del('/api/products/${p.id}','Produto removido')">🗑️</button></div></div>`; }).join("")}</div>` : `<div class="empty">📦 Nenhum produto ainda.<br><br><button class="btn" onclick="App.productForm()">Cadastrar primeiro produto</button></div>`}`, "Produtos — Modo Produto");
  state._products = products;
}
async function viewLoja() {
  const [{ store, company }, { products }] = await Promise.all([api("/api/settings"), api("/api/products")]);
  shell(`<div class="card"><div class="row between"><div><h3>🏪 Minha Store — ${esc(store.store_name || company.name)}</h3><p class="mut">Sua loja é gerada automaticamente a partir dos produtos. Compartilhe o link e venda com carrinho, checkout e cupom.</p></div><div class="row"><button class="btn ghost" onclick="App.copyStoreLink()">🔗 Copiar link da loja</button><button class="btn" onclick="App.openPublicStore()">Ver loja →</button></div></div>
  <p class="small mt">Link público: <a href="${storeUrl()}" target="_blank">${storeUrl()}</a></p></div>
  <div class="grid g2 mt"><div class="card"><h3>🎨 Personalização</h3><form id="store-form">
    <label class="f">Nome da loja</label><input id="s-name" value="${esc(store.store_name || "")}">
    <label class="f">Logo (emoji)</label><input id="s-logo" value="${esc(store.logo || "🛍️")}">
    <label class="f">Cor principal</label><input id="s-color" type="color" value="${esc(store.primary_color || "#7c3aed")}" style="height:44px;padding:4px">
    <label class="f">Banner / chamada principal</label><input id="s-banner" value="${esc(store.banner || "")}" placeholder="Ex.: Feito à mão para presentear quem você ama">
    <label class="f">Descrição da loja</label><textarea id="s-desc">${esc(store.description || "")}</textarea>
    <label class="f">Instagram</label><input id="s-insta" value="${esc(store.instagram || "")}">
    <button class="btn mt" type="submit">Salvar personalização</button></form></div>
  <div class="card"><h3>🛍️ Vitrine atual (${products.length} produtos)</h3>${products.map(p => `<div class="row between" style="padding:8px 0;border-bottom:1px solid var(--line)"><span class="row"><span class="prod-thumb" style="width:38px;height:38px;font-size:19px">${esc(p.icon || "🎁")}</span>${esc(p.name)}</span><span><b>${money(p.price)}</b> ${statusBadge(p.status)}</span></div>`).join("")}
  <p class="small mut mt">💡 Dica da IA: gere a página de cada produto com IA (título, benefícios, FAQ e CTA) para converter mais. Páginas prontas aparecem na loja pública.</p>
  <button class="btn sm soft" onclick="App.go('produtos')">Gerar páginas com IA →</button></div></div>`, "Minha Store");
  $("#store-form").onsubmit = async (e) => {
    e.preventDefault();
    const s = await api("/api/settings");
    await api("/api/settings", "PUT", { ...s.company, store_name: $("#s-name").value, logo: $("#s-logo").value, primary_color: $("#s-color").value, banner: $("#s-banner").value, store_description: $("#s-desc").value, instagram: $("#s-insta").value });
    toast("Loja personalizada! 🎨", "ok"); state.me = await api("/api/auth/me"); viewLoja();
  };
}
async function renderPublicStore(slug) {
  $("#app").innerHTML = `<div class="boot"><div class="boot-logo">🏪</div><p>Abrindo a loja…</p></div>`;
  let data; try { data = await api("/api/public/store/" + slug); } catch (e) { $("#app").innerHTML = `<div class="empty" style="margin:40px">${esc(e.message)}<br><br><a href="#/dashboard">Voltar</a></div>`; return; }
  state.publicData = data;
  const s = data.settings || {}; const color = s.primary_color || "#7c3aed";
  const render = () => {
    const cartTotal = state.cart.reduce((a, c) => a + c.price * c.qty, 0);
    $("#app").innerHTML = `<div style="max-width:1150px;margin:0 auto;padding:22px">
    <div class="row between"><b style="font-size:19px">${esc(s.logo || "🛍️")} ${esc(s.store_name || data.company.name)}</b><span class="row"><button class="btn ghost sm" onclick="location.hash='#/dashboard'">← Painel</button><button class="btn sm" style="background:${color}" onclick="document.getElementById('cart-section').scrollIntoView({behavior:'smooth'})">🛒 Carrinho (${state.cart.reduce((a, c) => a + c.qty, 0)}) · ${money(cartTotal)}</button></span></div>
    <div class="store-hero mt" style="--sc:${color};background:linear-gradient(135deg,${color},#db2777)"><span class="chip" style="background:rgba(255,255,255,.18);color:#fff;border:none">${esc(data.company.segment || "")} · ${esc(data.company.city || "")}</span><h1 style="margin:12px 0 6px;font-size:32px">${esc(s.banner || s.store_name || data.company.name)}</h1><p style="opacity:.92;max-width:620px">${esc(s.description || "")}</p><p class="small" style="opacity:.85">💬 Pedidos e dúvidas também pelo WhatsApp ${esc(data.company.whatsapp || "")} ${s.instagram ? "· Instagram " + esc(s.instagram) : ""}</p></div>
    <h3 class="mt">🛍️ Produtos</h3><div class="store-grid">${data.products.map(p => { let page = {}; try { page = JSON.parse(p.page_data || "{}"); } catch {} return `<div class="store-card">${p.image ? `<img src="${esc(p.image)}" alt="${esc(p.name)}" style="width:100%;height:150px;object-fit:cover;display:block">` : `<div style="height:130px;background:linear-gradient(135deg,#ede9fe,#fce7f3);display:flex;align-items:center;justify-content:center;font-size:58px">${esc(p.icon || "🎁")}</div>`}<div class="body"><b>${esc(p.name)}</b><p class="small mut" style="min-height:34px">${esc(page.subtitle || (p.description || "").slice(0, 80))}</p><div class="row between"><b style="font-size:17px">${money(p.price)}</b><span class="small mut">${(p.stock || 0) > 0 ? p.stock + " em estoque" : "Sob encomenda"}</span></div>
    ${page.benefits ? `<p class="small" style="margin:8px 0">✨ ${esc(page.benefits[0])}<br>🎁 ${esc(page.benefits[2] || "")}</p>` : ""}
    ${page.faq ? `<details class="small mut"><summary style="cursor:pointer;font-weight:700">Perguntas frequentes</summary>${page.faq.map(f => `<p><b>${esc(f.q)}</b><br>${esc(f.a)}</p>`).join("")}</details>` : ""}
    <button class="btn block mt" style="background:${color}" onclick="App.addCart(${p.id})">Adicionar ao carrinho 🛒</button></div></div>`; }).join("")}</div>
    ${data.reviews.length ? `<h3 class="mt">⭐ O que dizem nossos clientes</h3><div class="grid g3">${data.reviews.map(r => `<div class="card"><b>${"⭐".repeat(r.rating || 5)}</b><p class="small">"${esc(r.comment)}"</p><p class="small mut">— ${esc(r.customer_name)}</p></div>`).join("")}</div>` : ""}
    <div class="card mt"><h3>⭐ Avalie sua compra</h3><div class="grid g3"><div><label class="f">Produto</label><select id="rv-product">${data.products.map(p => `<option value="${p.id}">${esc(p.name)}</option>`).join("")}</select></div><div><label class="f">Seu nome</label><input id="rv-name" placeholder="Ex.: Maria S."></div><div><label class="f">Nota</label><select id="rv-rating">${[5, 4, 3, 2, 1].map(n => `<option value="${n}">${"⭐".repeat(n)}</option>`).join("")}</select></div></div>
    <label class="f">Comentário</label><textarea id="rv-comment" placeholder="Conte como foi sua experiência…"></textarea><button class="btn mt" style="background:${color}" onclick="App.submitReview()">Enviar avaliação</button></div>
    <div class="card mt" id="cart-section"><h3>🛒 Seu carrinho</h3>
    ${state.cart.length ? state.cart.map((c, i) => `<div class="row between" style="padding:7px 0;border-bottom:1px solid var(--line)"><span>${esc(c.icon || "")} ${esc(c.name)}</span><span class="row"><button class="icon-btn" onclick="App.cartQty(${i},-1)">−</button><b>${c.qty}</b><button class="icon-btn" onclick="App.cartQty(${i},1)">+</button><b>${money(c.price * c.qty)}</b><button class="icon-btn" onclick="App.cartRemove(${i})">🗑️</button></span></div>`).join("") + `<p class="row between mt"><span>Total</span><b style="font-size:19px">${money(cartTotal)}</b></p>
    <form id="checkout-form"><div class="grid g3"><div><label class="f">Seu nome</label><input id="co-name" required></div><div><label class="f">WhatsApp</label><input id="co-phone"></div><div><label class="f">E-mail</label><input id="co-email" type="email"></div></div>
    <div class="row mt"><button class="btn ghost sm" type="button" onclick="App.savePublicCart()">💾 Salvar carrinho e receber lembrete no WhatsApp</button><span class="small mut">Sem compromisso — só sobre este pedido.</span></div>
    <label class="f">Cupom de desconto</label><input id="co-coupon" placeholder="Ex.: BEMVINDO10">
    <label class="f">Pagamento</label><select id="co-pay">${data.payments && data.payments.pix ? `<option value="pix">📱 Pix — Mercado Pago (QR Code na hora)</option><option value="card">💳 Cartão — Mercado Pago (link seguro)</option>` : ""}<option value="manual">💬 Combinar pagamento com a loja (WhatsApp/dinheiro)</option></select>${data.payments && data.payments.mercadopago ? `<p class="small mut">🔒 Pagamentos processados pelo Mercado Pago. Pedidos Pix/cartão são confirmados automaticamente quando o pagamento é aprovado.</p>` : ""}
    <button class="btn block mt" style="background:${color}" type="submit">Finalizar pedido · ${money(cartTotal)} →</button><p class="small mut">Frete/entrega combinados pelo WhatsApp após o pedido. Sem spam: só falamos sobre o seu pedido.</p></form>`
    : `<p class="mut">Seu carrinho está vazio. Adicione um produto acima 👆</p>`}</div>
    <p class="small mut" style="text-align:center;margin:22px 0">Loja criada com <b>ProdutoVenda IA</b> 🚀 — Você cadastra o que vende. A IA transforma em vendas.</p></div>`;
    const form = $("#checkout-form");
    if (form) form.onsubmit = async (e) => {
      e.preventDefault();
      try {
        const r = await api("/api/public/store/" + slug + "/checkout", "POST", { customer_name: $("#co-name").value, phone: $("#co-phone").value, email: $("#co-email").value, coupon: $("#co-coupon").value, payment_method: $("#co-pay").value, items: state.cart.map(c => ({ product_id: c.id, qty: c.qty })) });
        state.cart = []; state._lastPayment = r.payment || null;
        const payHtml = !r.payment ? "" : r.payment.status === "erro" ? `<div class="card" style="background:var(--panel2)"><b>⚠️ Cobrança não gerada</b><p class="small">${esc(r.payment.error || "")}</p><p class="small mut">Seu pedido foi registrado e a loja concluirá o pagamento com você.</p></div>`
          : r.payment.method === "pix" ? `<div class="card" style="background:var(--panel2)"><h3>📱 Pague com Pix</h3>${r.payment.qr_code_base64 ? `<img src="data:image/png;base64,${r.payment.qr_code_base64}" alt="QR Code Pix" style="width:210px;height:210px;border-radius:14px;border:1px solid var(--line)">` : ""}<p class="small"><b>Pix copia e cola:</b></p><textarea readonly onclick="this.select()">${esc(r.payment.qr_code || "")}</textarea><button class="btn sm mt" onclick="App.copyText(state._lastPayment.qr_code,'Pix copia e cola copiado!')">📋 Copiar código Pix</button><p class="small mut">Assim que o Pix for aprovado, seu pedido é confirmado automaticamente. 💚</p></div>`
          : `<div class="card" style="background:var(--panel2)"><h3>💳 Pagar com cartão</h3><p class="small mut">Você será direcionado ao ambiente seguro do Mercado Pago.</p><a class="btn block" href="${esc(r.payment.checkout_url)}" target="_blank" rel="noopener">Ir para o pagamento seguro →</a></div>`;
        openModal(`<div style="text-align:center"><div style="font-size:52px">${r.payment && r.payment.status !== "erro" && r.order_status === "aguardando pagamento" ? "🧾" : "🎉"}</div><h2>Pedido #${r.order_id} ${r.order_status === "aguardando pagamento" ? "criado!" : "confirmado!"}</h2><p class="mut">${esc(r.message)}<br>Total: <b>${money(r.total)}</b>${r.discount ? ` (desconto de ${money(r.discount)} aplicado 🎟️)` : ""}</p>${payHtml}<button class="btn mt" onclick="App.closeModal();location.reload()">Continuar comprando</button></div>`);
        render();
      } catch (err) { toast(err.message, "err"); }
    };
  };
  state._renderStore = render; render();
}

/* ================= PEDIDOS / CLIENTES / CRM ================= */
async function viewPedidos() {
  const [{ orders }, pays] = await Promise.all([api("/api/orders"), api("/api/payments").catch(() => ({ payments: [] }))]);
  const payments = pays.payments || [];
  shell(`<div class="row between mb"><p class="mut" style="margin:0">Pedidos da loja, WhatsApp e canais — com lucro estimado por pedido. Cobre qualquer pedido com <b>Pix ou cartão reais (Mercado Pago)</b>.</p><button class="btn" onclick="App.orderForm()">+ Novo pedido manual</button></div>
  <div class="card"><table><tr><th>#</th><th>Cliente</th><th>Canal</th><th>Total</th><th>Lucro est.</th><th>Cupom</th><th>Data</th><th>Status</th><th></th></tr>
  ${orders.map(o => `<tr><td>#${o.id}</td><td><b>${esc(o.customer_name)}</b></td><td>${esc(o.channel)}</td><td><b>${money(o.total)}</b></td><td>${money(o.profit)}</td><td>${o.coupon ? badge(o.coupon, "b-violet") : "-"}</td><td class="small">${esc((o.created_at || "").slice(0, 10))}</td><td><select onchange="App.put('/api/orders/${o.id}',{status:this.value},'Status atualizado')" style="width:auto;padding:6px 9px">${["pendente", "aguardando pagamento", "pago", "entregue", "concluido", "cancelado"].map(s => `<option ${o.status === s ? "selected" : ""}>${s}</option>`).join("")}</select></td><td>${o.status !== "pago" && o.status !== "entregue" && o.status !== "concluido" ? `<button class="btn sm" onclick="App.chargeOrder(${o.id},${o.total})">💳 Cobrar</button>` : ""}</td></tr>`).join("") || '<tr><td colspan="9" class="mut">Nenhum pedido ainda.</td></tr>'}</table></div>
  <div class="card mt"><h3>💰 Pagamentos (Mercado Pago)</h3>${payments.length ? `<table><tr><th>#</th><th>Pedido</th><th>Método</th><th>Valor</th><th>Status no MP</th><th>ID externo</th><th></th></tr>${payments.map(p => `<tr><td>${p.id}</td><td>${p.order_id ? "#" + p.order_id : "—"}</td><td>${p.method === "pix" ? "📱 Pix" : "💳 Cartão/Link"}</td><td><b>${money(p.amount)}</b></td><td>${badge(p.status, p.status === "approved" ? "b-green" : p.status === "rejected" ? "b-red" : "b-amber")}</td><td class="small">${esc(p.external_id)}</td><td><span class="row">${p.method === "pix" && p.qr_code ? `<button class="btn sm ghost" onclick="App.copyText(\`${esc(p.qr_code).slice(0, 4000)}\`,'Pix copia e cola copiado!')">📋 Pix</button>` : ""}${p.checkout_url ? `<a class="btn sm ghost" href="${esc(p.checkout_url)}" target="_blank" rel="noopener">Abrir link</a>` : ""}<button class="btn sm soft" onclick="App.refreshPayment(${p.id})">🔄 Atualizar status</button></span></td></tr>`).join("")}</table>` : '<p class="mut">Nenhum pagamento gerado ainda. Configure o Mercado Pago em Admin & Planos → Integrações e use o botão <b>Cobrar</b> em um pedido — ou venda pela loja com Pix/cartão.</p>'}</div>`, "Pedidos");
}
async function viewClientes() {
  const { customers } = await api("/api/customers");
  shell(`<div class="row between mb"><p class="mut" style="margin:0">Base de clientes com VIP, indicações ("Indique e ganhe") e consentimento LGPD para comunicações.</p><button class="btn" onclick="App.customerForm()">+ Novo cliente</button></div>
  <div class="card"><input placeholder="🔎 Buscar cliente por nome, telefone, e-mail ou cidade…" oninput="App.searchRows(this,'clientes-body')" style="margin-bottom:12px"><table><thead><tr><th>Cliente</th><th>Contato</th><th>Cidade/Segmento</th><th>Compras</th><th>Total gasto</th><th>Última compra</th><th>VIP / Indicação</th><th>Consent.</th><th></th></tr></thead><tbody id="clientes-body">
  ${customers.map(c => `<tr><td><b>${esc(c.name)}</b></td><td class="small">${esc(c.phone)}<br>${esc(c.email)}</td><td class="small">${esc(c.city)}<br>${esc(c.segment)}</td><td>${c.purchases || 0}</td><td><b>${money(c.total_spent)}</b></td><td class="small">${esc(c.last_purchase || "—")}</td><td>${c.vip ? badge("👑 VIP", "b-amber") : ""} <span class="small mut">${esc(c.referral_code || "")} · ${c.referrals || 0} ind.</span></td><td>${c.consent ? badge("✓ Autorizou", "b-green") : badge("✕ Sem consent.", "b-red")}</td>
  <td><span class="row"><button class="btn sm soft" onclick="App.messageCustomer(${c.id},'${esc(c.name).replace(/'/g, "")}')">💬 Mensagem</button><button class="btn sm ghost" onclick="App.customerTimeline(${c.id})">📜 Histórico</button><button class="btn sm ghost" onclick="App.customerForm(${c.id})">Editar</button></span></td></tr>`).join("")}</tbody></table>
  <p class="small mut mt">👑 <b>Clientes VIP:</b> critérios configuráveis (nº de compras, valor gasto, frequência, indicação, aniversário) com cupons e ofertas exclusivas. 🎁 <b>Indique e ganhe:</b> cada cliente tem um código — quando o indicado compra, ele ganha o benefício configurado.</p></div>`, "Clientes");
  state._customers = customers;
}
const CRM_AI_NEXT = { "Novo Lead": "Enviar mensagem inicial personalizada hoje", "Contato Realizado": "Se sem resposta em 24h, enviar lembrete gentil", "Interessado": "Enviar benefícios + prova social (avaliações)", "Proposta": "Fazer follow-up da proposta em até 48h", "Negociação": "Entender a objeção e oferecer condição/cupom", "Pedido": "Confirmar pedido e combinar pagamento/entrega", "Pago": "Iniciar pós-venda: agradecer e pedir avaliação", "Pós-venda": "Sugerir produto relacionado e cupom de retorno", "Perdido": "Agendar retomada em data sazonal" };
async function viewCrm() {
  const { leads, stages } = await api("/api/leads");
  shell(`<div class="row between mb"><p class="mut" style="margin:0">Arraste os cards entre as etapas. A IA sugere a próxima ação em cada card. 🖱️</p><button class="btn" onclick="App.leadForm()">+ Novo lead</button></div>
  <div class="kanban">${stages.map(st => { const items = leads.filter(l => l.stage === st); return `<div class="kcol" ondragover="event.preventDefault()" ondrop="App.dropLead(event,'${st}')"><h4>${st} <span class="badge b-violet">${items.length}</span></h4>
  ${items.map(l => `<div class="kcard" draggable="true" ondragstart="event.dataTransfer.setData('text/plain','${l.id}')"><b>${esc(l.name)}</b><p>${esc(l.company || l.segment || "")} · ${esc(l.city || "")}<br>${esc(l.source)} · Potencial ${esc(l.potential)}<br>💰 ${money(l.value)} · Últ. contato: ${esc(l.last_interaction || "—")}</p><p>🤖 <i>${esc(l.next_action || CRM_AI_NEXT[st] || "")}</i></p><div class="row"><button class="btn sm soft" onclick="App.leadForm(${l.id})">Abrir</button><button class="btn sm ghost" onclick="App.del('/api/leads/${l.id}','Lead removido')">🗑️</button></div></div>`).join("") || '<p class="small mut" style="padding:4px">Nenhum card aqui.</p>'}</div>`; }).join("")}</div>
  <div class="card"><h3>🤖 Leitura da IA</h3><p class="mut">Leads em <b>Proposta</b> sem retorno são sua maior alavanca imediata. Use o Sales Agent: <i>"Quero fazer follow-up dos leads em proposta"</i> — ou abra um card e siga a próxima ação sugerida.</p></div>`, "CRM — Kanban de Vendas");
  state._leads = leads;
}

/* ================= OPORTUNIDADES / PROSPECÇÃO ================= */
async function viewOportunidades() {
  const { opportunities } = await api("/api/opportunities");
  shell(`<div class="row between mb"><p class="mut" style="margin:0">Oportunidades identificadas pela IA a partir de fontes permitidas e da sua própria base (clientes inativos, carrinhos, indicações).</p><button class="btn" onclick="App.go('prospeccao')">🔎 Nova prospecção</button></div>
  <div class="card"><table><tr><th>Nome/Empresa</th><th>Segmento</th><th>Cidade</th><th>Contato (quando disponível legalmente)</th><th>Origem</th><th>Potencial</th><th>Status</th><th>Ações</th></tr>
  ${opportunities.map(o => `<tr><td><b>${esc(o.name)}</b><br><span class="small mut">${esc(o.notes || "")}</span></td><td>${esc(o.segment)}</td><td>${esc(o.city)}</td><td class="small">${esc(o.phone)}<br>${esc(o.email)}<br>${o.site ? `<a href="${esc(o.site)}" target="_blank">${esc(o.site)}</a>` : ""}</td><td class="small">${esc(o.source)}</td><td>${badge(o.potential, o.potential === "Alto" ? "b-green" : "b-amber")}</td><td>${statusBadge(o.status)}</td>
  <td><div class="row"><button class="btn sm" onclick="App.oppContact(${o.id})">CONTATAR</button><button class="btn sm soft" onclick="App.oppProposal(${o.id},'${esc(o.company || o.name).replace(/'/g, "")}')">CRIAR PROPOSTA</button><button class="btn sm ghost" onclick="App.oppToCrm(${o.id})">ADICIONAR CRM</button></div></td></tr>`).join("") || '<tr><td colspan="8" class="mut">Nenhuma oportunidade. Faça uma prospecção IA.</td></tr>'}</table></div>`, "Central de Oportunidades");
  state._opps = opportunities;
}
async function viewProspeccao() {
  const { products } = await api("/api/products");
  shell(`<div class="grid g2"><div class="card"><h3>🔎 Prospecção IA</h3><p class="mut">A IA gera uma lista de oportunidades por cidade, segmento e produto — usando apenas fontes e APIs autorizadas. Sem scraping proibido, sem spam, respeitando privacidade e LGPD.</p>
  <form id="prospect-form"><label class="f">Produto a oferecer</label><select id="p-product">${products.map(p => `<option>${esc(p.name)}</option>`).join("")}</select>
  <label class="f">Cidade</label><input id="p-city" value="${esc(state.me.company.city || "")}">
  <label class="f">Segmento</label><select id="p-segment">${["Empresas", "Cafeterias", "Lojas", "Restaurantes", "Eventos", "Todos"].map(s => `<option>${s}</option>`).join("")}</select>
  <label class="f">Potencial comercial mínimo</label><select id="p-pot"><option>Todos</option><option>Alto</option><option>Médio</option></select>
  <button class="btn block mt" type="submit">✨ GERAR OPORTUNIDADES COM IA</button></form>
  <div id="prospect-result" class="mt"></div></div>
  <div class="card"><h3>🛡️ Como funciona (do jeito certo)</h3><p class="mut">Em produção, conecte fontes autorizadas — como a <b>Google Places API</b> — na página Admin & Planos. A plataforma nunca faz scraping proibido nem envia spam: toda abordagem deve usar canais oficiais, com consentimento/base legal e opção de opt-out.</p>
  <h3 class="mt">💡 Estratégia sugerida pela IA</h3><p class="mut">Para <b>presentes corporativos</b>: filtre Empresas na sua cidade, adicione ao CRM, envie uma proposta profissional com desconto por quantidade e faça follow-up em 48h.</p>
  <button class="btn soft mt" onclick="App.askAi('Quero vender para empresas')">Pedir estratégia ao Sales Agent →</button></div></div>`, "Prospecção IA");
  $("#prospect-form").onsubmit = async (e) => {
    e.preventDefault();
    try { const r = await api("/api/prospect", "POST", { product: $("#p-product").value, city: $("#p-city").value, segment: $("#p-segment").value }); $("#prospect-result").innerHTML = `<div class="card" style="background:var(--panel2)"><b>✅ ${esc(r.message)}</b><br><button class="btn sm mt" onclick="App.go('oportunidades')">Ver oportunidades →</button></div>`; toast("Prospecção concluída!", "ok"); }
    catch (err) { toast(err.message, "err"); }
  };
}

/* ================= CAMPANHAS / CUPONS / CONTEÚDO ================= */
async function viewCampanhas() {
  const [{ campaigns }, { products }] = await Promise.all([api("/api/campaigns"), api("/api/products")]);
  shell(`<div class="card"><h3>📣 Gerar campanha completa com IA</h3><p class="mut">Escolha produto, objetivo, público e região. A IA gera nome, estratégia, oferta, anúncio, post, story, roteiro de vídeo, WhatsApp, e-mail, cupom sugerido e agenda 5 conteúdos.</p>
  <form id="camp-form"><div class="grid g3">
  <div><label class="f">Produto</label><select id="c-product">${products.map(p => `<option value="${p.id}">${esc(p.name)}</option>`).join("")}</select></div>
  <div><label class="f">Objetivo</label><select id="c-objective">${["Vender mais esta semana", "Lançamento", "Vender para empresas", "Reativar clientes antigos", "Campanha sazonal / data comemorativa", "Aumentar ticket médio", "Queima de estoque"].map(o => `<option>${o}</option>`).join("")}</select></div>
  <div><label class="f">Canal principal</label><select id="c-channel">${["WhatsApp + Instagram", "Instagram", "WhatsApp", "E-mail", "Todos os canais"].map(o => `<option>${o}</option>`).join("")}</select></div>
  <div><label class="f">Público</label><input id="c-audience" placeholder="Ex.: Mulheres, presentes, empresas"></div>
  <div><label class="f">Região</label><input id="c-region" value="${esc(state.me.company.region || state.me.company.city || "")}"></div>
  <div><label class="f">Orçamento de mídia (opcional, R$)</label><input id="c-budget" type="number" step="0.01" placeholder="0"></div></div>
  <button class="btn mt" type="submit">✨ GERAR CAMPANHA COMPLETA</button></form></div>
  <div class="grid g2 mt">${campaigns.map(c => { let pack = {}; try { pack = JSON.parse(c.content || "{}"); } catch {} return `<div class="card"><div class="row between"><b>${esc(c.name)}</b>${statusBadge(c.status)}</div><p class="small mut">${esc(c.objective)} · ${esc(c.channel)} · ${esc(c.region || "")}</p>
  <p class="small"><b>Estratégia:</b> ${esc((pack.strategy || "").slice(0, 180))}…</p><div class="row mt"><button class="btn sm soft" onclick="App.campaignPack(${c.id})">Ver campanha completa</button><button class="btn sm ghost" onclick="App.put('/api/campaigns/${c.id}',{status:'${c.status === "ativa" ? "pausada" : "ativa"}'},'Campanha atualizada')">${c.status === "ativa" ? "Pausar" : "Ativar"}</button><button class="btn sm ghost" onclick="App.del('/api/campaigns/${c.id}','Campanha removida')">🗑️</button></div></div>`; }).join("") || '<div class="empty">Nenhuma campanha ainda. Gere a primeira acima ✨</div>'}</div>`, "Central de Campanhas IA");
  state._campaigns = campaigns;
  $("#camp-form").onsubmit = async (e) => {
    e.preventDefault();
    try { const r = await api("/api/campaigns/generate", "POST", { product_id: Number($("#c-product").value), objective: $("#c-objective").value, audience: $("#c-audience").value, region: $("#c-region").value, channel: $("#c-channel").value, budget: Number($("#c-budget").value || 0) }); toast("Campanha criada pela IA! 🎯", "ok"); showCampaignPack(r.pack); viewCampanhas(); }
    catch (err) { toast(err.message, "err"); }
  };
}
function showCampaignPack(pack) {
  if (!pack || !pack.name) return toast("Esta campanha não tem o pacote de conteúdo salvo.");
  const row = (l, v) => v ? `<div style="padding:9px 0;border-bottom:1px solid var(--line)"><b class="small">${l}</b><p class="small" style="margin:3px 0;white-space:pre-wrap">${esc(v)}</p><button class="link-btn small" onclick="App.copyText(\`${String(v).replace(/`/g, "")}\`)">📋 Copiar</button></div>` : "";
  openModal(`<div class="row between"><h3 style="margin:0">📣 ${esc(pack.name)}</h3><button class="icon-btn" onclick="App.closeModal()">✕</button></div>
  ${row("🎯 Estratégia", pack.strategy)}${row("🎁 Oferta", pack.offer)}${row("📢 Anúncio", pack.ad_copy)}${row("📸 Post Instagram", pack.instagram_post)}${row("⭕ Story", pack.story)}${row("🎬 Roteiro de vídeo/Reels", pack.video_script)}${row("💬 WhatsApp", pack.whatsapp)}${row("✉️ Assunto do e-mail", pack.email_subject)}${row("✉️ E-mail", pack.email_body)}
  ${(pack.followup || []).map((f, i) => row("📲 Follow-up " + (i + 1), f)).join("")}
  <p class="mt">🎟️ Cupom sugerido: <b>${esc(pack.coupon_suggestion || "OFERTA10")}</b></p>
  <div class="row"><button class="btn" onclick="App.createCouponCode('${esc(pack.coupon_suggestion || "OFERTA10")}',10)">Criar cupom sugerido</button><button class="btn ghost" onclick="App.closeModal();App.go('conteudo')">Ver conteúdos agendados</button></div>`, true);
}
async function viewCupons() {
  const { coupons } = await api("/api/coupons");
  shell(`<div class="row between mb"><p class="mut" style="margin:0">Cupons de campanha, boas-vindas, VIP, retorno e indicação — validados automaticamente no checkout da loja.</p><span class="row"><button class="btn soft" onclick="App.suggestCoupons()">🤖 Sugerir com IA</button><button class="btn" onclick="App.couponForm()">+ Novo cupom</button></span></div>
  <div id="coupon-suggestions" class="mb"></div>
  <div class="grid g3">${coupons.map(c => `<div class="card"><div class="row between"><b style="font-size:18px;letter-spacing:.03em">🎟️ ${esc(c.code)}</b>${c.active ? badge("Ativo", "b-green") : badge("Inativo", "b-red")}</div>
  <p class="small mut">${esc(c.kind)} · ${c.type === "percentual" ? c.value + "% OFF" : money(c.value) + " OFF"}${c.min_value ? " · mínimo " + money(c.min_value) : ""}${c.limit_uses ? ` · ${c.used}/${c.limit_uses} usos` : ` · ${c.used} usos`}</p>
  <div class="row"><button class="btn sm ghost" onclick="App.copyText('${esc(c.code)}','Cupom copiado!')">📋 Copiar código</button><button class="btn sm ghost" onclick="App.put('/api/coupons/${c.id}',{active:${c.active ? 0 : 1}},'Cupom atualizado')">${c.active ? "Desativar" : "Ativar"}</button><button class="btn sm ghost" onclick="App.del('/api/coupons/${c.id}','Cupom removido')">🗑️</button></div></div>`).join("") || '<div class="empty">Nenhum cupom ainda.</div>'}</div>`, "Cupons");
}
async function viewConteudo() {
  const [{ content }, { products }] = await Promise.all([api("/api/content"), api("/api/products")]);
  shell(`<div class="grid" style="grid-template-columns:1fr 1.5fr;gap:16px"><div class="card"><h3>🎨 Content Studio IA</h3><p class="mut">Gere posts, stories, reels, WhatsApp, e-mail, blog e Pinterest — e agende no calendário. A publicação automática usa as APIs oficiais quando conectadas; sem API, nada é simulado como publicado.</p>
  <form id="content-form"><label class="f">Produto</label><select id="ct-product">${products.map(p => `<option value="${p.id}">${esc(p.name)}</option>`).join("")}</select>
  <label class="f">Canal</label><select id="ct-channel">${["Instagram", "Instagram Stories", "Reels", "WhatsApp", "E-mail", "Facebook", "Blog", "Pinterest"].map(c => `<option>${c}</option>`).join("")}</select>
  <label class="f">Objetivo / tom</label><input id="ct-objective" placeholder="Ex.: Promoção da semana, tom acolhedor">
  <label class="f">Data e hora</label><input id="ct-date" type="datetime-local">
  <button class="btn block mt" type="submit">✨ Gerar e agendar conteúdo</button></form></div>
  <div class="card"><h3>🗓️ Calendário de conteúdo</h3>${content.length ? content.map(c => `<div class="row between" style="padding:10px 0;border-bottom:1px solid var(--line)"><div><b class="small">${esc(c.title)}</b><br><span class="small mut">${esc(c.channel)} · ${esc((c.scheduled_at || "").replace("T", " "))}</span><p class="small" style="margin:4px 0;white-space:pre-wrap">${esc((c.content || "").slice(0, 220))}${(c.content || "").length > 220 ? "…" : ""}</p></div><span class="row">${statusBadge(c.status)}<button class="btn sm ghost" onclick="App.copyText(\`${esc(c.content || "").replace(/`/g, "")}\`)">📋</button><button class="btn sm ghost" onclick="App.put('/api/content/${c.id}',{status:'${c.status === "publicado" ? "agendado" : "publicado"}'},'Status atualizado (publicação real exige API oficial conectada)')">${c.status === "publicado" ? "Desmarcar" : "Marcar pronto"}</button><button class="btn sm ghost" onclick="App.del('/api/content/${c.id}','Conteúdo removido')">🗑️</button></span></div>`).join("") : '<p class="mut">Nenhum conteúdo agendado. Gere o primeiro ao lado ✨</p>'}</div></div>`, "Content Studio IA + Agendamento");
  $("#content-form").onsubmit = async (e) => {
    e.preventDefault();
    try { await api("/api/content/generate", "POST", { product_id: Number($("#ct-product").value), channel: $("#ct-channel").value, objective: $("#ct-objective").value, scheduled_at: $("#ct-date").value || undefined }); toast("Conteúdo gerado e agendado! 🎨", "ok"); viewConteudo(); }
    catch (err) { toast(err.message, "err"); }
  };
}

/* ================= PROPOSTAS / AUTOMACOES / INSIGHTS ================= */
async function viewPropostas() {
  const [{ proposals }, { products }, { customers }] = await Promise.all([api("/api/proposals"), api("/api/products"), api("/api/customers")]);
  state._propProducts = products; state._propCustomers = customers;
  shell(`<div class="row between mb"><p class="mut" style="margin:0">Propostas profissionais geradas com IA — prontas para PDF, link, e-mail ou WhatsApp.</p><button class="btn" onclick="App.proposalForm()">+ Nova proposta com IA</button></div>
  <div class="grid g2">${proposals.map(p => `<div class="card"><div class="row between"><b>${esc(p.title)}</b>${statusBadge(p.status)}</div><p class="small mut">Para: ${esc(p.customer_name)} · Total ${money(p.total)}${p.discount ? ` · ${p.discount}% desc.` : ""} · Validade: ${esc(p.deadline || "—")}</p><p class="small" style="white-space:pre-wrap">${esc((p.content || "").slice(0, 260))}</p>
  <div class="row mt"><button class="btn sm soft" onclick="App.shareProposal(${p.id})">🔗 Compartilhar link</button><button class="btn sm ghost" onclick="window.print()">🖨️ PDF/Imprimir</button><button class="btn sm ghost" onclick="App.put('/api/proposals/${p.id}',{status:'enviada'},'Proposta marcada como enviada')">Marcar enviada</button><button class="btn sm ghost" onclick="App.del('/api/proposals/${p.id}','Proposta removida')">🗑️</button></div></div>`).join("") || '<div class="empty">Nenhuma proposta ainda.</div>'}</div>`, "Propostas Comerciais");
}
async function viewAutomacoes() {
  const { automations } = await api("/api/automations");
  shell(`<div class="row between mb"><p class="mut" style="margin:0">Construtor <b>QUANDO acontecer X → FAZER Y</b>. Mensagens externas só saem com integração oficial + consentimento (LGPD).</p><span class="row"><button class="btn warn" onclick="App.runAutomations()">▶ Executar verificações agora</button><button class="btn" onclick="App.automationForm()">+ Nova automação</button></span></div>
  <div id="automation-runs" class="mb"></div>
  <div class="grid g2">${automations.map(a => `<div class="card"><div class="row between"><b>${esc(a.name)}</b><label class="switch"><input type="checkbox" ${a.active ? "checked" : ""} onchange="App.put('/api/automations/${a.id}',{active:this.checked?1:0},'Automação atualizada')"><i></i></label></div>
  <p class="small mt"><span class="badge b-violet">QUANDO</span> ${esc(a.trigger_event)} &nbsp;→&nbsp; <span class="badge b-green">FAZER</span> ${esc(a.action)}</p><p class="small mut">${esc(a.config || "")}</p>
  <button class="btn sm ghost" onclick="App.del('/api/automations/${a.id}','Automação removida')">🗑️ Remover</button></div>`).join("")}</div>
  <div class="card mt"><h3>🔁 Fluxos prontos incluídos</h3><p class="mut">Recuperação de carrinho (aguarda período configurável → lembrete → 2ª mensagem → cupom opcional) · Follow-up por etapa (lead novo → sem resposta → interessado → proposta → pós-venda → reativação) · Pós-venda (confirmar pedido → avaliação → depoimento → produto relacionado → cupom de retorno).</p></div>`, "Automações");
}
async function viewInsights() {
  const { insights } = await api("/api/insights");
  shell(`<div class="grid g2">${insights.map((ins, i) => `<div class="card"><div style="font-size:26px">${esc(ins.icon)}</div><p style="line-height:1.6">${esc(ins.text)}</p><button class="btn sm mt" onclick='App.aiAction(${JSON.stringify({ action: ins.action, product_id: ins.product_id, code: ins.code, value: ins.value, target: ins.target }).replace(/'/g, "&#39;")})'>${esc(ins.action_label || "EXECUTAR AÇÃO")}</button></div>`).join("") || '<div class="empty">Sem insights no momento — cadastre produtos e registre vendas.</div>'}</div>
  <p class="small mut mt">Insights calculados dos seus dados reais (produtos, pedidos, clientes, CRM e carrinhos). Nenhuma promessa de resultado: são recomendações de planejamento.</p>`, "Insights IA — Inteligência Comercial");
}

/* ================= WHATSAPP / EMAIL / RELATORIOS / METAS ================= */
async function viewWhatsapp() {
  const [{ templates }, { customers }, ig, hist] = await Promise.all([api("/api/templates"), api("/api/customers"), api("/api/integrations").catch(() => ({ integrations: [] })), api("/api/messages").catch(() => ({ messages: [] }))]);
  state._integrations = ig.integrations || [];
  const wa = state._integrations.find(i => i.provider === "whatsapp") || {};
  state._waCustomers = customers; state._waTemplates = templates;
  shell(`<div class="card mb"><div class="row between"><div><h3>💬 Central WhatsApp — Cloud API (Meta)</h3><p class="mut">${wa.connected ? "✅ <b>Conectada e ativa:</b> os envios abaixo saem de verdade pela Graph API e as respostas dos clientes chegam pelo webhook." : "⚠️ <b>Não conectada:</b> configure Phone Number ID + token em Admin & Planos → Integrações. Sem conexão, as mensagens ficam na fila — nada é fingido como enviado."} Atendimento e campanhas só para contatos que autorizaram. <b>Nunca spam.</b></p></div><span class="row"><button class="btn soft" onclick="App.integrationForm('whatsapp')">⚙️ Configurar WhatsApp</button>${wa.configured ? `<button class="btn ghost" onclick="App.testIntegration('whatsapp')">🔌 Testar conexão</button>` : ""}</span></div>
  ${wa.webhook_url ? `<p class="small mut">Webhook p/ receber mensagens (cole na Meta): <a href="#" onclick="event.preventDefault();App.copyText('${esc(wa.webhook_url)}')">${esc(wa.webhook_url)}</a> 📋</p>` : ""}</div>
  <div class="grid g2"><div class="card"><h3>📤 Enviar mensagem ${wa.connected ? "(envio real)" : "(fila)"}</h3><form id="wa-form">
  <label class="f">Cliente (somente com consentimento)</label><select id="wa-customer">${customers.map(c => `<option value="${c.id}">${esc(c.name)} ${c.consent ? "✓" : "✕ sem consentimento"}</option>`).join("")}</select>
  <label class="f">Template interno (preenche o texto)</label><select id="wa-template" onchange="App.fillTemplate()"><option value="">— Escrever do zero —</option>${templates.map(t => `<option value="${t.id}">${esc(t.name)}</option>`).join("")}</select>
  <label class="f">Template aprovado na Meta (opcional — fora da janela de 24h use um template aprovado)</label><input id="wa-template-name" placeholder="Ex.: hello_world (deixe vazio p/ texto livre)">
  <label class="f">Mensagem</label><textarea id="wa-content" placeholder="Use {nome} para personalizar"></textarea>
  <button class="btn block mt" type="submit">${wa.connected ? "Enviar via WhatsApp Cloud API →" : "Registrar na fila"}</button></form></div>
  <div class="card"><h3>📝 Templates</h3>${templates.map(t => `<div style="padding:9px 0;border-bottom:1px solid var(--line)"><b class="small">${esc(t.name)}</b> ${badge(t.channel, "b-violet")}<p class="small mut" style="margin:3px 0">${esc(t.content)}</p><button class="btn sm ghost" onclick="App.del('/api/templates/${t.id}','Template removido')">🗑️</button></div>`).join("")}
  <button class="btn sm soft mt" onclick="App.templateForm()">+ Novo template</button></div></div>
  <div class="card mt"><h3>🕘 Histórico de mensagens (enviadas e recebidas)</h3>${(hist.messages || []).length ? (hist.messages || []).map(m => `<div style="padding:8px 0;border-bottom:1px solid var(--line)"><span class="row between"><span>${m.direction === "in" ? "📥" : "📤"} <b>${esc(m.customer_name || "Cliente")}</b> <span class="small mut">${esc(m.channel)} · ${esc((m.created_at || "").slice(0, 16).replace("T", " "))}</span></span>${badge(m.status || "", String(m.status || "").startsWith("enviado") || String(m.status || "").startsWith("recebido") ? "b-green" : String(m.status || "").startsWith("falha") ? "b-red" : "b-amber")}</span><p class="small" style="margin:4px 0">${esc(m.content)}</p></div>`).join("") : '<p class="mut">Nenhuma mensagem ainda. As recebidas pelo webhook aparecem aqui automaticamente.</p>'}</div>`, "WhatsApp Business");
  $("#wa-form").onsubmit = async (e) => {
    e.preventDefault();
    const cust = state._waCustomers.find(c => c.id === Number($("#wa-customer").value));
    const content = ($("#wa-content").value || "").replace("{nome}", (cust?.name || "").split(" ")[0]);
    try { const r = await api("/api/messages/send", "POST", { customer_id: Number($("#wa-customer").value), channel: "WhatsApp", content, template_name: $("#wa-template-name").value.trim() }); toast("✅ " + r.note, "ok"); viewWhatsapp(); }
    catch (err) { toast(err.message, "err"); }
  };
}
async function viewEmail() {
  const { email_campaigns } = await api("/api/email-campaigns");
  shell(`<div class="row between mb"><p class="mut" style="margin:0">Campanhas, segmentação e sequências com assunto e CTA gerados por IA. Envio real via provedor conectado, sempre com opt-out.</p><button class="btn" onclick="App.emailForm()">+ Nova campanha de e-mail</button></div>
  <div class="grid g2">${email_campaigns.map(c => `<div class="card"><div class="row between"><b>${esc(c.subject)}</b>${statusBadge(c.status)}</div><p class="small mut">Segmento: ${esc(c.segment)} · Enviados ${c.sent || 0} · Aberturas ${c.opens || 0} · Cliques ${c.clicks || 0}</p><p class="small" style="white-space:pre-wrap">${esc((c.content || "").slice(0, 240))}</p><div class="row"><button class="btn sm" onclick="App.sendEmailCampaign(${c.id})">✉️ Enviar agora (SMTP)</button><button class="btn sm ghost" onclick="App.put('/api/email-campaigns/${c.id}',{status:'agendada'},'Campanha agendada')">Agendar</button><button class="btn sm ghost" onclick="App.del('/api/email-campaigns/${c.id}','Campanha removida')">🗑️</button></div></div>`).join("") || '<div class="empty">Nenhuma campanha de e-mail ainda. Crie a primeira com ajuda da IA ✨</div>'}</div>`, "E-mail Marketing");
}
async function viewRelatorios() {
  const r = await api("/api/reports");
  const max = Math.max(...r.monthly.map(m => m.revenue), 1);
  shell(`<div class="row between mb"><p class="mut" style="margin:0">Exporte para planilha ou gere o PDF do relatório.</p><span class="row">
  <button class="btn sm soft" onclick="App.downloadCsv('orders')">📊 CSV Pedidos</button><button class="btn sm soft" onclick="App.downloadCsv('products')">📊 CSV Produtos</button>
  <button class="btn sm soft" onclick="App.downloadCsv('customers')">📊 CSV Clientes</button><button class="btn sm soft" onclick="App.downloadCsv('payments')">📊 CSV Pagamentos</button>
  <button class="btn sm" onclick="window.print()">🖨️ Imprimir / Salvar PDF</button></span></div>
  <div class="grid g3"><div class="card kpi"><div class="lbl">Receita total</div><div class="val">${money(r.totals.revenue)}</div></div><div class="card kpi"><div class="lbl">Lucro total estimado</div><div class="val">${money(r.totals.profit)}</div></div><div class="card kpi"><div class="lbl">Pedidos</div><div class="val">${r.totals.orders}</div></div></div>
  <div class="card mt"><h3>📈 Receita por mês</h3>${r.monthly.map(m => `<div class="row" style="gap:12px;margin:8px 0"><span class="small" style="width:64px">${esc(m.label)}</span><div class="progress" style="flex:1"><div style="width:${Math.round(m.revenue / max * 100)}%"></div></div><b class="small">${money(m.revenue)}</b><span class="small mut">${m.orders} ped. · lucro ${money(m.profit)}</span></div>`).join("")}</div>
  <div class="grid g2 mt"><div class="card"><h3>🏆 Produtos (receita)</h3><table><tr><th>Produto</th><th>Qtd</th><th>Receita</th></tr>${r.by_product.map(p => `<tr><td>${esc(p.name)}</td><td>${p.qty}</td><td><b>${money(p.revenue)}</b></td></tr>`).join("")}</table></div>
  <div class="card"><h3>🔀 Canais de venda</h3><table><tr><th>Canal</th><th>Pedidos</th><th>Receita</th></tr>${r.by_channel.map(c => `<tr><td>${esc(c.channel)}</td><td>${c.orders}</td><td><b>${money(c.revenue)}</b></td></tr>`).join("")}</table>
  <h3 class="mt">🎟️ Cupons mais usados</h3>${r.coupons.map(c => `<div class="row between small" style="padding:5px 0;border-bottom:1px solid var(--line)"><span>${esc(c.code)} (${c.type === "percentual" ? c.value + "%" : money(c.value)})</span><b>${c.used} usos</b></div>`).join("")}</div></div>
  <div class="card mt"><h3>📣 Campanhas</h3><table><tr><th>Campanha</th><th>Objetivo</th><th>Canal</th><th>Status</th></tr>${r.by_campaign.map(c => `<tr><td>${esc(c.name)}</td><td>${esc(c.objective)}</td><td>${esc(c.channel)}</td><td>${statusBadge(c.status)}</td></tr>`).join("")}</table></div>`, "Relatórios de Vendas");
}
async function viewMetas() {
  const [d, s] = await Promise.all([api("/api/dashboard"), api("/api/settings")]);
  const c = s.company;
  shell(`<div class="grid g3"><div class="card kpi"><div class="lbl">🎯 Meta mensal</div><div class="val">${money(c.goal_monthly)}</div><div class="sub">Vendido ${money(d.goal.sold)} · Falta ${money(d.goal.missing)} (${d.goal.percent}%)</div><div class="progress mt"><div style="width:${d.goal.percent}%"></div></div></div>
  <div class="card kpi"><div class="lbl">📅 Meta semanal</div><div class="val">${money(c.goal_weekly)}</div><div class="sub">Acompanhamento semanal do plano</div></div>
  <div class="card kpi"><div class="lbl">☀️ Meta diária</div><div class="val">${money(c.goal_daily)}</div><div class="sub">Hoje: ${money((await api("/api/dashboard")).kpis.revenue_today)}</div></div></div>
  <div class="grid g2 mt"><div class="card"><h3>🧮 O que falta para a meta</h3><p style="line-height:1.7">${esc(d.goal.message)}<br>Lucro médio por pedido: <b>${money(d.goal.avg_profit)}</b> · Pedidos necessários: <b>${d.goal.orders_needed}</b>.<br><span class="mut">Ajuste o plano: suba o ticket com combos, recupere carrinhos e reative clientes inativos. Isto é planejamento e acompanhamento — <b>não é garantia de resultado</b>.</span></p>
  <button class="btn" onclick="App.askAi('Quero bater minha meta do mês. Monte um plano.')">🤖 Pedir plano de meta à IA</button></div>
  <div class="card"><h3>⚙️ Configurar metas</h3><form id="goal-form"><label class="f">Meta mensal (R$)</label><input id="g-month" type="number" step="0.01" value="${c.goal_monthly}"><label class="f">Meta semanal (R$)</label><input id="g-week" type="number" step="0.01" value="${c.goal_weekly}"><label class="f">Meta diária (R$)</label><input id="g-day" type="number" step="0.01" value="${c.goal_daily}"><button class="btn mt" type="submit">Salvar metas</button></form></div></div>`, "Metas de Faturamento");
  $("#goal-form").onsubmit = async (e) => { e.preventDefault(); const s2 = await api("/api/settings"); await api("/api/settings", "PUT", { ...s2.company, ...s2.store, store_name: s2.store.store_name, goal_monthly: Number($("#g-month").value), goal_weekly: Number($("#g-week").value), goal_daily: Number($("#g-day").value) }); toast("Metas atualizadas! 🎯", "ok"); state.me = await api("/api/auth/me"); viewMetas(); };
}

/* ================= ADMIN / CONFIG ================= */
async function viewAdmin() {
  const a = await api("/api/admin");
  const ig = await api("/api/integrations").catch(() => ({ integrations: [] }));
  const billing = await api("/api/billing").catch(() => ({}));
  state._integrations = ig.integrations || [];
  shell(`<div class="card mb"><h3>🛡️ Administração da plataforma</h3><p class="mut">Usuários, planos, assinaturas, uso de IA, integrações, logs e métricas. Cada empresa (tenant) só enxerga os próprios dados.</p>
  <div class="row mt">${Object.entries(a.counts).map(([k, v]) => badge(k + ": " + v, "b-violet")).join("")} ${badge("Ações de IA no mês: " + a.usage.actions, "b-green")} ${badge("Tokens estimados: " + a.usage.tokens, "b-gray")} ${badge("Sistema: v" + (a.version || "1.2.0") + " · /api/health", "b-green")}</div>
  <div class="row mt"><button class="btn sm soft" onclick="App.exportData()">📦 Exportar dados da empresa (JSON)</button><span class="small mut">Backup portátil dos seus dados — nunca inclui senhas nem segredos de integração.</span></div>
  ${billing.subscription ? `<p class="small mt">💎 Assinatura: <b>${esc(billing.subscription.plan_name || "")}</b> · status <b>${esc(billing.subscription.status)}</b>${billing.subscription.current_period_end ? ` · vigente até <b>${esc(billing.subscription.current_period_end)}</b>` : ""} · ${money(billing.subscription.amount)}/mês</p>` : `<p class="small mut mt">💎 Nenhuma assinatura registrada — escolha um plano abaixo (pagos são cobrados via Mercado Pago e ativados no webhook).</p>`}</div>
  <div class="card mb"><h3>🔌 Integrações reais</h3><p class="mut">Conecte suas credenciais oficiais — elas ficam salvas <b>apenas no servidor da sua empresa</b>, sempre mascaradas na tela, e nada é simulado: o botão <b>Testar conexão</b> faz uma chamada real à API. Guia passo a passo no arquivo <b>INTEGRACOES.md</b> do projeto.</p>
  <div class="grid g2 mt">${state._integrations.map(it => `<div style="border:1px solid var(--line);border-radius:14px;padding:15px">
    <div class="row between"><b>${esc(it.icon)} ${esc(it.name)}</b>${it.connected ? badge("● Conectada e ativa", "b-green") : it.configured ? badge("Configurada (desativada)", "b-amber") : badge("Não configurada", "b-gray")}</div>
    <p class="small mut" style="margin:7px 0">${esc(it.desc)}</p>
    ${it.missing && it.missing.length ? `<p class="small">Faltam: <b>${it.missing.join(", ")}</b></p>` : ""}
    ${it.last_test_status ? `<p class="small mut">Último teste: ${it.last_test_status === "sucesso" ? "✅" : "❌"} ${esc(it.last_test_detail || "")} <span>(${esc((it.last_test_at || "").slice(0, 16).replace("T", " "))})</span></p>` : ""}
    ${it.webhook_url ? `<p class="small mut">Webhook (cole no provedor):<br><a href="#" onclick="event.preventDefault();App.copyText('${esc(it.webhook_url)}','URL do webhook copiada!')">${esc(it.webhook_url)}</a> 📋</p>` : ""}
    <div class="row mt"><button class="btn sm" onclick="App.integrationForm('${it.provider}')">⚙️ Configurar</button><button class="btn sm soft" onclick="App.testIntegration('${it.provider}')" ${it.configured ? "" : "disabled"}>🔌 Testar conexão</button>
    ${it.configured ? `<button class="btn sm ghost" onclick="App.toggleIntegration('${it.provider}',${it.active ? 0 : 1})">${it.active ? "Desativar" : "Ativar"}</button>` : ""}</div></div>`).join("")}</div></div>
  <h3 class="mb">💎 Planos (limites configuráveis)</h3><div class="grid g4">${a.plans.map(p => { const lim = JSON.parse(p.limits || "{}"); const current = state.me.company.plan_id === p.id; return `<div class="card" style="${current ? "border:2px solid var(--brand)" : ""}"><b>${esc(p.name)}</b>${current ? ' ' + badge("PLANO ATUAL", "b-violet") : ""}<div class="val" style="font-size:24px;font-weight:850;margin:8px 0">${p.price ? money(p.price) + "<span class='small mut'>/mês</span>" : "Grátis"}</div><p class="small mut" style="line-height:1.8">${Object.entries(lim).map(([k, v]) => `${k}: <b>${v >= 9999 ? "ilimitado" : v}</b>`).join("<br>")}</p>${current ? "" : `<button class="btn sm block mt" onclick="App.subscribePlan(${p.id},'${esc(p.name)}',${p.price})">${p.price ? "Assinar " + money(p.price) + "/mês" : "Ativar plano grátis"}</button>`}</div>`; }).join("")}</div>
  <div class="grid g2 mt"><div class="card"><h3>👥 Usuários da empresa</h3>${a.users.map(u => `<div class="row between" style="padding:8px 0;border-bottom:1px solid var(--line)"><span><b>${esc(u.name)}</b><br><span class="small mut">${esc(u.email)}</span></span>${badge(u.role, "b-violet")}</div>`).join("")}</div>
  <div class="card"><h3>🔌 Integrações (APIs oficiais)</h3>${a.integrations.map(i => `<div style="padding:9px 0;border-bottom:1px solid var(--line)"><div class="row between"><b class="small">${esc(i.name)}</b>${badge(i.status, "b-amber")}</div><p class="small mut" style="margin:3px 0">${esc(i.desc)}</p></div>`).join("")}</div></div>
  <div class="card mt"><h3>📜 Logs de auditoria</h3><table><tr><th>Data</th><th>Ação</th><th>Detalhe</th></tr>${a.audit.map(l => `<tr><td class="small">${esc((l.created_at || "").slice(0, 16).replace("T", " "))}</td><td>${esc(l.action)}</td><td class="small mut">${esc((l.detail || "").slice(0, 120))}</td></tr>`).join("")}</table></div>`, "Admin & Planos");
}
async function viewConfig() {
  const { company: c, store: s } = await api("/api/settings");
  shell(`<div class="grid g2"><div class="card"><h3>🏢 Minha empresa</h3><form id="cfg-form">
  <label class="f">Nome da empresa</label><input id="cf-name" value="${esc(c.name)}">
  <label class="f">Segmento (troque quando quiser — a IA se adapta)</label><select id="cf-segment">${["Chocolates e Doces", "Bolos e Confeitaria", "Pizzas", "Hambúrgueres e Lanches", "Roupas e Moda", "Cosméticos e Beleza", "Perfumes", "Artesanato", "Presentes", "Produtos Digitais", "Serviços", "Outro negócio"].map(x => `<option ${c.segment === x ? "selected" : ""}>${x}</option>`).join("")}</select>
  <label class="f">Cidade</label><input id="cf-city" value="${esc(c.city || "")}"><label class="f">Região de atendimento</label><input id="cf-region" value="${esc(c.region || "")}">
  <label class="f">WhatsApp</label><input id="cf-whats" value="${esc(c.whatsapp || "")}"><label class="f">E-mail</label><input id="cf-email" value="${esc(c.email || "")}">
  <label class="f">Nível do Autopilot IA</label><select id="cf-auto">${["manual", "assistido", "automatico"].map(x => `<option ${c.autopilot === x ? "selected" : ""}>${x}</option>`).join("")}</select>
  <button class="btn mt" type="submit">Salvar configurações</button></form></div>
  <div class="card"><h3>🔐 Segurança & LGPD</h3><p class="mut" style="line-height:1.75">✓ Senhas com hash PBKDF2 (nunca em texto puro)<br>✓ Sessões com token, expiração e rate limiting no login<br>✓ Isolamento multi-tenant: seus dados nunca se misturam com outra empresa<br>✓ Validação de dados e queries parametrizadas no servidor<br>✓ Comunicações só com consentimento/opt-in e opção de opt-out<br>✓ Logs de auditoria das ações importantes<br>✓ Loja pública: <a href="${storeUrl()}" target="_blank">${storeUrl()}</a></p>
  <h3 class="mt">🚀 Sua loja</h3><p class="mut">Slug: <b>${esc(c.slug)}</b> · Plano: <b>${esc(state.me.plan?.name || "")}</b></p><button class="btn soft" onclick="App.openPublicStore()">Abrir minha loja →</button></div></div>`, "Configurações");
  $("#cfg-form").onsubmit = async (e) => {
    e.preventDefault(); const cur = await api("/api/settings");
    await api("/api/settings", "PUT", { ...cur.company, ...cur.store, store_name: cur.store.store_name, name: $("#cf-name").value, segment: $("#cf-segment").value, city: $("#cf-city").value, region: $("#cf-region").value, whatsapp: $("#cf-whats").value, email: $("#cf-email").value, autopilot: $("#cf-auto").value });
    toast("Configurações salvas! ⚙️", "ok"); state.me = await api("/api/auth/me"); viewConfig();
  };
}

/* ================= ACTIONS (globais) ================= */
const App = {
  closeModal, copyText,
  authMode: (m) => renderAuth(m),
  demoLogin: async () => { const r = await api("/api/auth/login", "POST", { email: "demo@produtovenda.com.br", password: "demo1234" }); state.token = r.token; localStorage.setItem("pv_token", r.token); toast("Bem-vindo(a) à demonstração! 🍫", "ok"); boot(); },
  logout: async () => { try { if (state.token) await api("/api/auth/logout", "POST", {}); } catch {} logout(); toast("Até logo! Sessão encerrada no servidor. 👋"); },
  forgotPassword() {
    openModal(`<div class="row between"><h3 style="margin:0">🔑 Esqueci minha senha</h3><button class="icon-btn" onclick="App.closeModal()">✕</button></div>
    <p class="mut">Informe seu e-mail. Se a conta existir, enviaremos um link de redefinição válido por 1 hora (via SMTP, quando configurado em Integrações).</p>
    <form id="forgot-form"><label class="f">E-mail da conta</label><input id="fg-email" type="email" required placeholder="voce@empresa.com.br">
    <button class="btn block mt" type="submit">Enviar link de redefinição</button></form><div id="forgot-result" class="mt"></div>`);
    $("#forgot-form").onsubmit = async (e) => {
      e.preventDefault();
      try { const r = await api("/api/auth/forgot", "POST", { email: $("#fg-email").value });
        $("#forgot-result").innerHTML = `<div class="card" style="background:var(--panel2)"><p class="small">${esc(r.message)}</p>${r.reset_link ? `<p class="small"><b>Link (modo local):</b><br><a href="${esc(r.reset_link)}">${esc(r.reset_link)}</a></p>` : ""}</div>`;
      } catch (err) { toast(err.message, "err"); }
    };
  },
  async exportData() {
    try {
      const data = await api("/api/admin/export");
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
      a.download = `produtovenda-export-${state.me.company.slug}-${new Date().toISOString().slice(0, 10)}.json`; a.click();
      URL.revokeObjectURL(a.href); toast("Exportação baixada! 📦 (sem senhas nem segredos de integração)", "ok");
    } catch (e) { toast(e.message, "err"); }
  },
  searchRows(input, tbodyId) {
    const q = (input.value || "").toLowerCase();
    document.querySelectorAll(`#${tbodyId} tr`).forEach(tr => { tr.style.display = tr.innerText.toLowerCase().includes(q) ? "" : "none"; });
  },
  async customerTimeline(id) {
    try {
      const t = await api(`/api/customers/${id}/timeline`);
      const c = t.customer;
      openModal(`<div class="row between"><h3 style="margin:0">👤 ${esc(c.name)}</h3><button class="icon-btn" onclick="App.closeModal()">✕</button></div>
      <p class="small mut">${esc(c.phone)} · ${esc(c.email)} · ${esc(c.city)} · ${esc(c.segment)} · Total gasto <b>${money(c.total_spent)}</b> em ${c.purchases || 0} compra(s) · Última: ${esc(c.last_purchase || "—")} ${c.vip ? "· 👑 VIP" : ""} · Código de indicação: ${esc(c.referral_code || "—")}</p>
      <h4>🧾 Pedidos (${t.orders.length})</h4>${t.orders.map(o => `<div class="row between small" style="padding:6px 0;border-bottom:1px solid var(--line)"><span>#${o.id} · ${esc(o.channel)} · ${esc((o.created_at || "").slice(0, 10))}</span><span><b>${money(o.total)}</b> ${statusBadge(o.status)}</span></div>`).join("") || '<p class="small mut">Nenhum pedido vinculado.</p>'}
      <h4>💬 Mensagens (${t.messages.length})</h4>${t.messages.map(m => `<div class="small" style="padding:6px 0;border-bottom:1px solid var(--line)">${m.direction === "in" ? "📥" : "📤"} ${esc(m.content)}<br><span class="mut">${esc(m.status)} · ${esc((m.created_at || "").slice(0, 16).replace("T", " "))}</span></div>`).join("") || '<p class="small mut">Nenhuma mensagem registrada.</p>'}
      ${t.leads.length ? `<h4>🗂️ No CRM (${t.leads.length})</h4>${t.leads.map(l => `<div class="small" style="padding:5px 0">• ${esc(l.name)} — ${statusBadge(l.stage)} (${money(l.value)})</div>`).join("")}` : ""}`, true);
    } catch (e) { toast(e.message, "err"); }
  },
  async savePublicCart() {
    const phone = ($("#co-phone")?.value || "").trim();
    if (!phone) return toast("Informe seu WhatsApp no formulário para salvar o carrinho 📱", "err");
    try {
      const slug = state.publicData.company.slug;
      const r = await api("/api/public/store/" + slug + "/cart", "POST", { customer_name: $("#co-name")?.value || "", phone, items: state.cart.map(c => ({ product_id: c.id, qty: c.qty })) });
      toast(r.message, "ok");
    } catch (e) { toast(e.message, "err"); }
  },
  async submitReview() {
    try {
      const slug = state.publicData.company.slug;
      const r = await api("/api/public/store/" + slug + "/review", "POST", { product_id: Number($("#rv-product").value), customer_name: $("#rv-name").value, rating: Number($("#rv-rating").value), comment: $("#rv-comment").value });
      toast(r.message, "ok"); state.publicData = await api("/api/public/store/" + slug); state._renderStore();
    } catch (e) { toast(e.message, "err"); }
  },
  go: (r) => { location.hash = "#/" + r; if (state.route === r) route(); },
  toggleDark: () => { state.dark = !state.dark; document.body.classList.toggle("dark", state.dark); localStorage.setItem("pv_dark", state.dark ? "1" : "0"); route(); },
  askAi: (text) => { state.pendingAi = text; App.go("agente"); },
  openPublicStore: () => { location.hash = "#/loja/" + state.me.company.slug; },
  copyStoreLink: () => copyText(storeUrl(), "Link da loja copiado! 🔗"),
  obBack: () => { if (obStep > 0) { obStep--; renderOnboarding(); } },
  obSkip: () => { if (obStep < OB_STEPS.length - 1) { obStep++; renderOnboarding(); } },
  setAutopilot: async (v) => { const s = await api("/api/settings"); await api("/api/settings", "PUT", { ...s.company, ...s.store, store_name: s.store.store_name, autopilot: v }); state.me = await api("/api/auth/me"); toast("Autopilot: " + v, "ok"); },
  setStoreRender: () => {},
  addCart: (id) => { const p = state.publicData.products.find(x => x.id === id); const ex = state.cart.find(c => c.id === id); if (ex) ex.qty++; else state.cart.push({ id: p.id, name: p.name, price: p.price, icon: p.icon, qty: 1 }); state._renderStore(); toast("Adicionado ao carrinho 🛒", "ok"); },
  cartQty: (i, d) => { state.cart[i].qty += d; if (state.cart[i].qty <= 0) state.cart.splice(i, 1); state._renderStore(); },
  cartRemove: (i) => { state.cart.splice(i, 1); state._renderStore(); },
  async put(path, body, msg) { try { await api(path, "PUT", body); toast(msg || "Salvo!", "ok"); route(); } catch (e) { toast(e.message, "err"); } },
  async del(path, msg) { if (!confirm("Tem certeza que deseja remover?")) return; try { await api(path, "DELETE"); toast(msg || "Removido!", "ok"); route(); } catch (e) { toast(e.message, "err"); } },
  async aiAction(a) {
    try {
      if (a.action === "go") return App.go(a.target);
      if (a.action === "campaign" || a.action === "coupon") {
        if (a.action === "campaign") { const r = await api("/api/campaigns/generate", "POST", { product_id: a.product_id }); toast("Campanha criada pela IA! 📣", "ok"); showCampaignPack(r.pack); }
        else { const r = await api("/api/coupons", "POST", { code: "OFERTA10", type: "percentual", value: 10, kind: "campanha", active: 1 }); toast("Cupom OFERTA10 criado! 🎟️", "ok"); }
        return;
      }
      if (a.action === "coupon_code") return App.createCouponCode(a.code, a.value || 10);
      if (a.action === "run_automations") return App.runAutomations();
      if (a.action === "messages") { const r = await api("/api/content/generate", "POST", { product_id: a.product_id, channel: "WhatsApp" }); toast("Mensagem gerada no Content Studio! 💬", "ok"); App.go("conteudo"); return; }
    } catch (e) { toast(e.message, "err"); }
  },
  async createCouponCode(code, value) {
    try { await api("/api/coupons", "POST", { code, type: "percentual", value, kind: "campanha", active: 1 }); toast(`Cupom ${code} criado! 🎟️`, "ok"); closeModal(); if (state.route === "cupons") route(); }
    catch (e) { toast(e.message + " (pode já existir — veja em Cupons)", "err"); }
  },
  async runAutomations() {
    try { const r = await api("/api/automations/run", "POST", {}); openModal(`<div class="row between"><h3 style="margin:0">⚡ Automações executadas</h3><button class="icon-btn" onclick="App.closeModal()">✕</button></div><p class="mut">${esc(r.message)}</p>${r.runs.map(x => `<p style="padding:7px 0;border-bottom:1px solid var(--line)">✅ ${esc(x)}</p>`).join("")}<button class="btn mt" onclick="App.closeModal();App.go('automacoes')">Ver automações</button>`); }
    catch (e) { toast(e.message, "err"); }
  },
  quickCampaign: async () => { const { products } = await api("/api/products"); if (!products.length) return toast("Cadastre um produto primeiro 📦"); const r = await api("/api/campaigns/generate", "POST", { product_id: products[0].id, objective: "vender mais esta semana" }); toast("Campanha criada! 📣", "ok"); showCampaignPack(r.pack); },
  quickOffer: async () => { const { products } = await api("/api/products"); if (!products.length) return toast("Cadastre um produto primeiro 📦"); await api(`/api/products/${products[0].id}/generate-page`, "POST", {}); toast("Oferta/página do produto líder gerada! 🎁 Veja em Produtos.", "ok"); App.go("produtos"); },
  quickCoupon: async () => { App.createCouponCode("OFERTA10", 10); },
  campaignFor: async (id) => { const r = await api("/api/campaigns/generate", "POST", { product_id: id }); toast("Campanha criada! 📣", "ok"); showCampaignPack(r.pack); },
  sendFollowup: () => { state.pendingAi = "Quero enviar follow-up para meus leads e clientes"; App.go("agente"); },
  centralAction: (r) => { if (r === "__campaign") return App.quickCampaign(); if (r === "__offer") return App.quickOffer(); if (r === "__recover") return App.runAutomations(); App.go(r); },
  async generatePage(id) {
    try { const r = await api(`/api/products/${id}/generate-page`, "POST", {}); const p = r.page;
      openModal(`<div class="row between"><h3 style="margin:0">✨ Página gerada com IA</h3><button class="icon-btn" onclick="App.closeModal()">✕</button></div>
      <h2 style="margin:14px 0 4px">${esc(p.title)}</h2><p class="mut">${esc(p.subtitle)}</p><p style="line-height:1.65">${esc(p.description)}</p>
      <h4>✅ Benefícios</h4>${p.benefits.map(b => `<div>• ${esc(b)}</div>`).join("")}<h4>⭐ Diferenciais</h4>${p.differentials.map(b => `<div>• ${esc(b)}</div>`).join("")}
      <h4>❓ Perguntas frequentes</h4>${p.faq.map(f => `<p class="small"><b>${esc(f.q)}</b><br>${esc(f.a)}</p>`).join("")}
      <p>⏰ ${esc(p.urgency)}</p><button class="btn block" onclick="App.closeModal()">${esc(p.cta)}</button>
      <p class="small mut mt">Página salva e já visível na sua loja pública. 🎉</p>`, true);
      if (state.route === "produtos") viewProdutos();
    } catch (e) { toast(e.message, "err"); }
  },
  productForm(id) {
    const p = (state._products || []).find(x => x.id === id) || {};
    formModal(id ? "Editar produto" : "Novo produto — Modo Produto", [
      { name: "name", label: "Nome do produto *", value: p.name || "", placeholder: "Ex.: Caixa de Chocolates Gourmet" },
      { name: "icon", label: "Ícone", type: "select", value: p.icon || "🎁", options: ["🍫", "🍬", "🎂", "🍕", "🍔", "👗", "💄", "🌸", "🎨", "🎁", "💝", "🏢", "💻", "⭐"] },
      { name: "price", label: "Preço de venda (R$)", type: "number", step: "0.01", value: p.price ?? "" },
      { name: "cost", label: "Custo (R$) — para lucro e meta", type: "number", step: "0.01", value: p.cost ?? "" },
      { name: "stock", label: "Estoque", type: "number", value: p.stock ?? 0 },
      { name: "audience", label: "Público-alvo", value: p.audience || "", placeholder: "Ex.: Mulheres, presentes, empresas e eventos" },
      { name: "description", label: "Descrição (a IA pode gerar depois)", type: "textarea", value: p.description || "" },
      { name: "status", label: "Status", type: "select", value: p.status || "ativo", options: ["ativo", "pausado"] },
    ], id ? "Salvar produto" : "Cadastrar e gerar com IA ✨", async (out) => {
      if (!out.name) throw new Error("Informe o nome do produto.");
      let saved;
      if (id) saved = await api("/api/products/" + id, "PUT", out); else saved = await api("/api/products", "POST", out);
      if (!id) { await api(`/api/products/${saved.item.id}/generate-page`, "POST", {}); toast("Produto cadastrado e página gerada pela IA! ✨", "ok"); }
      else toast("Produto atualizado!", "ok");
      viewProdutos();
    });
  },
  orderForm() {
    formModal("Novo pedido manual", [
      { name: "customer_name", label: "Cliente *", placeholder: "Nome do cliente" },
      { name: "total", label: "Total (R$)", type: "number", step: "0.01" },
      { name: "profit", label: "Lucro estimado (R$)", type: "number", step: "0.01" },
      { name: "channel", label: "Canal", type: "select", options: ["Loja", "WhatsApp", "Instagram", "Presencial", "Telefone"] },
      { name: "status", label: "Status", type: "select", options: ["pago", "pendente", "entregue", "concluido"] },
      { name: "coupon", label: "Cupom (se houver)", placeholder: "Ex.: BEMVINDO10" },
    ], "Registrar pedido", async (out) => { await api("/api/orders", "POST", out); toast("Pedido registrado! 🧾", "ok"); viewPedidos(); });
  },
  customerForm(id) {
    const c = (state._customers || []).find(x => x.id === id) || {};
    formModal(id ? "Editar cliente" : "Novo cliente", [
      { name: "name", label: "Nome *", value: c.name || "" }, { name: "phone", label: "WhatsApp/telefone", value: c.phone || "" }, { name: "email", label: "E-mail", value: c.email || "" },
      { name: "city", label: "Cidade", value: c.city || "" }, { name: "segment", label: "Segmento", value: c.segment || "Consumidor final" },
      { name: "birthday", label: "Aniversário", type: "date", value: c.birthday || "" },
      { name: "vip", label: "👑 Cliente VIP (ofertas exclusivas e acesso antecipado)", type: "checkbox", value: c.vip || 0 },
      { name: "consent", label: "✓ Autorizou receber comunicações (LGPD — necessário para marketing)", type: "checkbox", value: c.consent ?? 1 },
    ], "Salvar cliente", async (out) => { if (!out.name) throw new Error("Informe o nome."); if (id) await api("/api/customers/" + id, "PUT", out); else await api("/api/customers", "POST", out); toast("Cliente salvo! 👥", "ok"); viewClientes(); });
  },
  messageCustomer(id, name) {
    openModal(`<div class="row between"><h3 style="margin:0">💬 Mensagem para ${esc(name)}</h3><button class="icon-btn" onclick="App.closeModal()">✕</button></div>
    <label class="f">Canal</label><select id="mc-channel"><option>WhatsApp</option><option>E-mail</option></select>
    <label class="f">Mensagem</label><textarea id="mc-content">Oi, ${esc(name.split(" ")[0])}! 😊 Temos uma novidade especial para você esta semana. Quer que eu te mostre?</textarea>
    <button class="btn block mt" onclick="App.sendMessageCustomer(${id})">Registrar envio (fila oficial)</button>
    <p class="small mut">Envio real apenas com consentimento + integração oficial conectada. Sem spam, sempre. 🛡️</p>`);
  },
  async sendMessageCustomer(id) {
    try { const r = await api("/api/messages/send", "POST", { customer_id: id, channel: $("#mc-channel").value, content: $("#mc-content").value }); closeModal(); toast("✅ " + r.note, "ok"); }
    catch (e) { toast(e.message, "err"); }
  },
  leadForm(id) {
    const l = (state._leads || []).find(x => x.id === id) || {};
    formModal(id ? "Lead — histórico e próxima ação" : "Novo lead", [
      { name: "name", label: "Nome *", value: l.name || "" }, { name: "company", label: "Empresa", value: l.company || "" },
      { name: "phone", label: "Telefone", value: l.phone || "" }, { name: "email", label: "E-mail", value: l.email || "" }, { name: "city", label: "Cidade", value: l.city || "" },
      { name: "segment", label: "Segmento", value: l.segment || "" }, { name: "source", label: "Origem", value: l.source || "Manual" },
      { name: "stage", label: "Etapa do funil", type: "select", value: l.stage || "Novo Lead", options: ["Novo Lead", "Contato Realizado", "Interessado", "Proposta", "Negociação", "Pedido", "Pago", "Pós-venda", "Perdido"] },
      { name: "potential", label: "Potencial", type: "select", value: l.potential || "Médio", options: ["Alto", "Médio", "Baixo"] },
      { name: "value", label: "Valor potencial (R$)", type: "number", step: "0.01", value: l.value ?? 0 },
      { name: "next_action", label: "🤖 Próxima ação sugerida/definida", value: l.next_action || "" },
      { name: "notes", label: "Notas e histórico", type: "textarea", value: l.notes || "" },
    ], "Salvar lead", async (out) => { if (!out.name) throw new Error("Informe o nome."); if (id) await api("/api/leads/" + id, "PUT", out); else await api("/api/leads", "POST", out); toast("Lead salvo! 🗂️", "ok"); viewCrm(); });
  },
  async dropLead(ev, stage) { ev.preventDefault(); const id = ev.dataTransfer.getData("text/plain"); try { await api("/api/leads/" + id, "PUT", { stage }); toast("Lead movido para " + stage, "ok"); viewCrm(); } catch (e) { toast(e.message, "err"); } },
  oppContact(id) {
    const o = (state._opps || []).find(x => x.id === id); if (!o) return;
    openModal(`<div class="row between"><h3 style="margin:0">📞 Contatar ${esc(o.name)}</h3><button class="icon-btn" onclick="App.closeModal()">✕</button></div>
    <p class="mut">Abordagem sugerida pela IA (canais oficiais, sem spam):</p>
    <div class="card" style="background:var(--panel2)"><p class="small" id="opp-msg" style="white-space:pre-wrap">Olá, equipe ${esc(o.company || o.name)}! 😊 Sou da ${esc(state.me.company.name)}. Trabalhamos com ${esc(state.me.company.segment || "produtos presenteáveis")} e percebi que vocês poderiam oferecer isso a clientes/equipe em datas especiais. Posso enviar uma proposta sem compromisso, com condições para empresas?</p></div>
    <div class="row mt"><button class="btn" onclick="App.copyText(document.getElementById('opp-msg').innerText)">📋 Copiar mensagem</button><button class="btn soft" onclick="App.closeModal();App.oppToCrm(${id})">Adicionar ao CRM e acompanhar</button></div>
    <p class="small mut">Telefone: ${esc(o.phone || "—")} · E-mail: ${esc(o.email || "—")} — valide sempre pelos canais oficiais antes de contatar.</p>`);
  },
  async oppProposal(id, company) {
    try { await api("/api/proposals", "POST", { customer_name: company, title: "Proposta comercial — " + state.me.company.name, total: 0, discount: 10, deadline: "7 dias", conditions: "Condições para empresas: desconto por quantidade, pagamento facilitado e entrega programada.", status: "rascunho", content: `Proposta gerada a partir da oportunidade ${company}: apresentar produto principal, benefícios para a empresa, condições por quantidade e próximos passos.` }); toast("Proposta criada em rascunho! 📄", "ok"); App.go("propostas"); }
    catch (e) { toast(e.message, "err"); }
  },
  async oppToCrm(id) { try { await api(`/api/opportunities/${id}/to-crm`, "POST", {}); toast("Adicionado ao CRM! 🗂️", "ok"); closeModal(); App.go("crm"); } catch (e) { toast(e.message, "err"); } },
  campaignPack(id) { const c = (state._campaigns || []).find(x => x.id === id); let pack = {}; try { pack = JSON.parse(c?.content || "{}"); } catch {} showCampaignPack(pack); },
  couponForm() {
    formModal("Novo cupom", [
      { name: "code", label: "Código *", placeholder: "Ex.: BEMVINDO10" },
      { name: "type", label: "Tipo", type: "select", options: [{ value: "percentual", label: "Percentual (%)" }, { value: "fixo", label: "Valor fixo (R$)" }] },
      { name: "value", label: "Valor", type: "number", step: "0.01", value: 10 },
      { name: "kind", label: "Finalidade", type: "select", options: ["primeira compra", "cliente antigo", "aniversário", "campanha", "indicação", "geral"] },
      { name: "min_value", label: "Valor mínimo do pedido (R$)", type: "number", step: "0.01", value: 0 },
      { name: "limit_uses", label: "Limite de usos (0 = sem limite)", type: "number", value: 0 },
      { name: "active", label: "Cupom ativo", type: "checkbox", value: 1 },
    ], "Criar cupom 🎟️", async (out) => { if (!out.code) throw new Error("Informe o código."); await api("/api/coupons", "POST", out); toast("Cupom criado! 🎟️", "ok"); viewCupons(); });
  },
  async suggestCoupons() {
    const r = await api("/api/coupons/suggest", "POST", {});
    $("#coupon-suggestions").innerHTML = `<div class="card"><h3>🤖 Sugestões da IA para sua estratégia</h3><div class="grid g2 mt">${r.suggestions.map(s => `<div style="padding:11px;border:1px solid var(--line);border-radius:13px"><b>🎟️ ${esc(s.code)}</b> <span class="small mut">${s.value}% · ${esc(s.kind)}</span><p class="small mut">${esc(s.reason)}</p><button class="btn sm" onclick="App.createCouponCode('${esc(s.code)}',${s.value})">Criar este cupom</button></div>`).join("")}</div></div>`;
  },
  proposalForm() {
    const products = state._propProducts || []; const customers = state._propCustomers || [];
    formModal("Nova proposta com IA", [
      { name: "customer_name", label: "Cliente/empresa *", placeholder: "Ex.: Hotel Boa Viagem", value: "" },
      { name: "title", label: "Título", placeholder: "Ex.: Proposta — Kits corporativos de fim de ano" },
      { name: "total", label: "Valor total (R$)", type: "number", step: "0.01" },
      { name: "discount", label: "Desconto (%)", type: "number", step: "0.01", value: 0 },
      { name: "deadline", label: "Validade", placeholder: "Ex.: 7 dias" },
      { name: "conditions", label: "Condições", type: "textarea", placeholder: "Pagamento, entrega, prazos…" },
    ], "Gerar proposta com IA ✨", async (out) => {
      if (!out.customer_name) throw new Error("Informe o cliente.");
      out.content = `Prezado(a) ${out.customer_name},\n\nA ${state.me.company.name} preparou esta proposta especialmente para você:\n\n• Produto/serviço: ${out.title || "condições especiais"}\n• Valor: ${money(out.total)}${out.discount ? ` (com ${out.discount}% de desconto já considerado na negociação)` : ""}\n• Validade: ${out.deadline || "7 dias"}\n• Condições: ${out.conditions || "a combinar"}\n\nSerá um prazer atender você. Qualquer dúvida, fale conosco pelo WhatsApp ${state.me.company.whatsapp || ""}.\n\nAtenciosamente,\n${state.me.company.name}`;
      out.status = "rascunho";
      await api("/api/proposals", "POST", out); toast("Proposta gerada! 📄", "ok"); viewPropostas();
    });
  },
  shareProposal(id) { copyText(location.origin + location.pathname + "#/proposta/" + id, "Link da proposta copiado! 🔗 (proposta #" + id + ")"); },
  automationForm() {
    formModal("Nova automação — QUANDO → FAZER", [
      { name: "name", label: "Nome *", placeholder: "Ex.: Reativar clientes em 45 dias" },
      { name: "trigger_event", label: "QUANDO (gatilho)", type: "select", options: ["novo_cliente", "pedido_concluido", "carrinho_abandonado", "cliente_inativo_60d", "lead_sem_resposta", "estoque_baixo", "campanha_encerrada"] },
      { name: "action", label: "FAZER (ação)", type: "select", options: ["enviar_mensagem", "criar_oportunidade", "solicitar_avaliacao", "alertar_admin", "criar_tarefa_followup"] },
      { name: "config", label: "Configuração (intervalos, mensagens, cupom…)", type: "textarea", placeholder: "Ex.: Aguardar 1h → lembrete; 48h → cupom VOLTEI10" },
      { name: "active", label: "Ativa", type: "checkbox", value: 1 },
    ], "Criar automação ⚡", async (out) => { if (!out.name) throw new Error("Informe o nome."); await api("/api/automations", "POST", out); toast("Automação criada! ⚡", "ok"); viewAutomacoes(); });
  },
  templateForm() {
    formModal("Novo template de mensagem", [
      { name: "name", label: "Nome *", placeholder: "Ex.: Reativação de cliente" },
      { name: "channel", label: "Canal", type: "select", options: ["WhatsApp", "E-mail", "Instagram"] },
      { name: "content", label: "Conteúdo (use {nome})", type: "textarea", placeholder: "Oi, {nome}! …" },
    ], "Salvar template", async (out) => { await api("/api/templates", "POST", out); toast("Template salvo! 📝", "ok"); viewWhatsapp(); });
  },
  fillTemplate() { const t = (state._waTemplates || []).find(x => x.id === Number($("#wa-template").value)); if (t) $("#wa-content").value = t.content; },
  emailForm() {
    formModal("Nova campanha de e-mail (IA ajuda no texto)", [
      { name: "subject", label: "Assunto *", placeholder: "Ex.: 🍫 Condição especial só esta semana" },
      { name: "segment", label: "Segmento da lista", type: "select", options: ["Todos os clientes consentidos", "Clientes VIP", "Clientes inativos", "Novos clientes", "Empresas"] },
      { name: "content", label: "Conteúdo", type: "textarea", placeholder: "Escreva ou peça ao Sales Agent: 'crie um e-mail para reativar clientes'" },
      { name: "status", label: "Status", type: "select", options: ["rascunho", "agendada"] },
    ], "Salvar campanha ✉️", async (out) => { if (!out.subject) throw new Error("Informe o assunto."); await api("/api/email-campaigns", "POST", out); toast("Campanha salva! ✉️", "ok"); viewEmail(); });
  },
  integrationForm(provider) {
    const it = (state._integrations || []).find(x => x.provider === provider); if (!it) return;
    const fields = it.fields.map(f => ({
      name: f.name, label: f.label + (f.secret ? " 🔒" : ""), type: f.secret ? "password" : "text",
      value: f.secret ? "" : (it.config[f.name] || ""),
      placeholder: f.secret ? (it.config[f.name] ? `Atual: ${it.config[f.name]} — deixe vazio para manter` : (f.placeholder || "")) : (f.placeholder || ""),
    }));
    fields.push({ name: "__active", label: "Integração ativa (envios/pagamentos reais ligados)", type: "checkbox", value: it.active ? 1 : 0 });
    formModal(`${it.icon} Configurar — ${it.name}`, fields, "Salvar credenciais", async (out) => {
      const active = out.__active; delete out.__active;
      Object.keys(out).forEach(k => { if (out[k] === "") delete out[k]; });
      const r = await api("/api/integrations/" + provider, "PUT", { config: out, active: !!active });
      toast(r.message, "ok");
      viewAdmin();
    });
    toast("🔒 Segredos nunca aparecem inteiros na tela — ficam só no servidor.");
  },
  async testIntegration(provider) {
    toast("🔌 Testando conexão real com a API…");
    try { const r = await api(`/api/integrations/${provider}/test`, "POST", {}); toast(r.message, "ok"); viewAdmin(); }
    catch (e) { toast(e.message, "err"); viewAdmin(); }
  },
  async toggleIntegration(provider, active) {
    try { await api("/api/integrations/" + provider, "PUT", { config: {}, active: !!active }); toast(active ? "Integração ativada ✅" : "Integração desativada", "ok"); viewAdmin(); }
    catch (e) { toast(e.message, "err"); }
  },
  chargeOrder(id, total) {
    openModal(`<div class="row between"><h3 style="margin:0">💳 Cobrar pedido #${id} — ${money(total)}</h3><button class="icon-btn" onclick="App.closeModal()">✕</button></div>
    <p class="mut">Gera uma cobrança real no Mercado Pago (requer integração configurada e ativa).</p>
    <div class="grid g2 mt"><button class="btn" onclick="App.createCharge(${id},'pix')">📱 Gerar Pix (QR Code)</button><button class="btn soft" onclick="App.createCharge(${id},'card')">💳 Gerar link de cartão</button></div>
    <div id="charge-result" class="mt"></div>`);
  },
  async createCharge(orderId, method) {
    const box = $("#charge-result"); if (box) box.innerHTML = "Gerando cobrança no Mercado Pago…";
    try {
      const r = await api("/api/payments/create", "POST", { order_id: orderId, method });
      const p = r.payment; state._lastPayment = p;
      const html = method === "pix"
        ? `${p.qr_code_base64 ? `<img src="data:image/png;base64,${p.qr_code_base64}" alt="QR Code Pix" style="width:210px;height:210px;border-radius:14px;border:1px solid var(--line)">` : ""}<p class="small"><b>Pix copia e cola:</b></p><textarea readonly onclick="this.select()">${esc(p.qr_code || "")}</textarea><button class="btn sm mt" onclick="App.copyText(state._lastPayment.qr_code,'Pix copia e cola copiado!')">📋 Copiar código Pix</button>`
        : `<p>Link de pagamento (cartão/Checkout Pro):</p><p><a href="${esc(p.checkout_url)}" target="_blank" rel="noopener">${esc(p.checkout_url)}</a></p><button class="btn sm" onclick="App.copyText(state._lastPayment.checkout_url,'Link copiado!')">📋 Copiar link</button>`;
      if (box) box.innerHTML = `<div class="card" style="background:var(--panel2);text-align:center"><b>✅ Cobrança criada!</b><p class="small mut">Status inicial: ${esc(p.status)} · ID Mercado Pago: ${esc(p.external_id)}</p>${html}<p class="small mut mt">Quando o cliente pagar, o webhook do Mercado Pago marca o pedido como <b>pago</b> automaticamente. Você também pode conferir em Pedidos → Pagamentos.</p></div>`;
      toast(r.message, "ok");
    } catch (e) { if (box) box.innerHTML = `<div class="card" style="background:var(--panel2)">❌ ${esc(e.message)}</div>`; toast(e.message, "err"); }
  },
  async refreshPayment(id) {
    try { const r = await api(`/api/payments/${id}/refresh`, "POST", {}); toast(`Status no Mercado Pago: ${r.payment.status}`, "ok"); viewPedidos(); }
    catch (e) { toast(e.message, "err"); }
  },
  async sendEmailCampaign(id) {
    if (!confirm("Enviar esta campanha agora via SMTP para todos os clientes que autorizaram contato?")) return;
    try { const r = await api(`/api/email-campaigns/${id}/send`, "POST", {}); toast(r.message, "ok"); viewEmail(); }
    catch (e) { toast(e.message, "err"); }
  },
  async changePlan(id) { try { await api("/api/admin/plan", "POST", { plan_id: id }); state.me = await api("/api/auth/me"); toast("Plano atualizado! 💎", "ok"); viewAdmin(); } catch (e) { toast(e.message, "err"); } },
  productImage(id) {
    const p = (state._products || []).find(x => x.id === id) || {};
    state._imgData = "";
    openModal(`<div class="row between"><h3 style="margin:0">📷 Foto de ${esc(p.name || "produto")}</h3><button class="icon-btn" onclick="App.closeModal()">✕</button></div>
    ${p.image ? `<img src="${esc(p.image)}" style="width:100%;max-height:240px;object-fit:cover;border-radius:14px;margin-top:12px">` : `<div class="empty mt">Sem foto — o produto usa o ícone ${esc(p.icon || "🎁")} na loja.</div>`}
    <label class="f">Enviar nova foto (PNG, JPG ou WEBP, até 2 MB)</label>
    <input type="file" id="img-file" accept="image/png,image/jpeg,image/webp">
    <img id="img-preview" style="display:none;width:100%;max-height:240px;object-fit:cover;border-radius:14px;margin-top:12px">
    <div class="row mt"><button class="btn" onclick="App.uploadProductImage(${id})">Salvar foto</button>
    ${p.image ? `<button class="btn ghost" onclick="App.removeProductImage(${id})">Remover foto</button>` : ""}</div>
    <p class="small mut">A foto aparece no painel, na vitrine da loja e na página do produto.</p>`);
    $("#img-file").onchange = (e) => {
      const file = e.target.files[0]; if (!file) return;
      if (file.size > 2_000_000) return toast("Imagem maior que 2 MB. Reduza e tente de novo.", "err");
      const reader = new FileReader();
      reader.onload = () => { state._imgData = reader.result; const img = $("#img-preview"); img.src = reader.result; img.style.display = "block"; };
      reader.readAsDataURL(file);
    };
  },
  async uploadProductImage(id) {
    if (!state._imgData) return toast("Escolha uma foto primeiro 📷", "err");
    try { const r = await api(`/api/products/${id}/image`, "POST", { image_data: state._imgData }); toast(r.message, "ok"); closeModal(); viewProdutos(); }
    catch (e) { toast(e.message, "err"); }
  },
  async removeProductImage(id) {
    try { const r = await api(`/api/products/${id}/image`, "DELETE"); toast(r.message, "ok"); closeModal(); viewProdutos(); }
    catch (e) { toast(e.message, "err"); }
  },
  subscribePlan(id, name, price) {
    if (!price) {
      api("/api/billing/subscribe", "POST", { plan_id: id }).then(async (r) => { state.me = await api("/api/auth/me"); toast(r.message, "ok"); viewAdmin(); }).catch(e => toast(e.message, "err"));
      return;
    }
    openModal(`<div class="row between"><h3 style="margin:0">💎 Assinar plano ${esc(name)} — ${money(price)}/mês</h3><button class="icon-btn" onclick="App.closeModal()">✕</button></div>
    <p class="mut">A cobrança é gerada no Mercado Pago conectado. O plano é ativado automaticamente por 30 dias quando o pagamento for aprovado (webhook).</p>
    <div class="grid g2 mt"><button class="btn" onclick="App.createSubscription(${id},'pix')">📱 Pagar com Pix</button><button class="btn soft" onclick="App.createSubscription(${id},'card')">💳 Pagar com cartão</button></div>
    <div id="sub-result" class="mt"></div>`);
  },
  async createSubscription(planId, method) {
    const box = $("#sub-result"); if (box) box.innerHTML = "Gerando cobrança da assinatura no Mercado Pago…";
    try {
      const r = await api("/api/billing/subscribe", "POST", { plan_id: planId, method });
      const p = r.payment; state._lastPayment = p;
      const html = method === "pix"
        ? `${p.qr_code_base64 ? `<img src="data:image/png;base64,${p.qr_code_base64}" alt="QR Code Pix" style="width:210px;height:210px;border-radius:14px;border:1px solid var(--line)">` : ""}<p class="small"><b>Pix copia e cola:</b></p><textarea readonly onclick="this.select()">${esc(p.qr_code || "")}</textarea><button class="btn sm mt" onclick="App.copyText(state._lastPayment.qr_code,'Pix copiado!')">📋 Copiar Pix</button>`
        : `<p>Link seguro do Mercado Pago:</p><p><a href="${esc(p.checkout_url)}" target="_blank" rel="noopener">${esc(p.checkout_url)}</a></p><button class="btn sm" onclick="App.copyText(state._lastPayment.checkout_url,'Link copiado!')">📋 Copiar link</button>`;
      if (box) box.innerHTML = `<div class="card" style="background:var(--panel2);text-align:center"><b>✅ Cobrança gerada!</b><p class="small mut">${esc(r.message)}</p>${html}</div>`;
    } catch (e) { if (box) box.innerHTML = `<div class="card" style="background:var(--panel2)">❌ ${esc(e.message)}</div>`; toast(e.message, "err"); }
  },
  async downloadCsv(type) {
    try {
      const res = await fetch("/api/reports/export.csv?type=" + type, { headers: { Authorization: "Bearer " + state.token } });
      if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.error || "Erro ao exportar"); }
      const blob = await res.blob();
      const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = `relatorio-${type}.csv`; a.click();
      URL.revokeObjectURL(a.href); toast("CSV baixado! 📊 Abra no Excel/Sheets.", "ok");
    } catch (e) { toast(e.message, "err"); }
  },
};
window.App = App;
boot();
