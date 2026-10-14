# 🔌 Guia de Integrações Reais — ProdutoVenda IA

Tudo é configurado em **Admin & Planos → Integrações reais** (botão **⚙️ Configurar** de cada provedor, depois **🔌 Testar conexão**).
As credenciais ficam salvas **somente no servidor da sua empresa**, vinculadas ao seu tenant, e **nunca aparecem inteiras na tela** (sempre mascaradas, ex.: `••••••••abcd`). Nada é simulado: sem credencial válida, o envio/pagamento real não acontece e a plataforma explica o erro.

> ⚠️ **Importante sobre os webhooks:** a Meta e o Mercado Pago precisam alcançar a URL do seu servidor pela internet.
> Em produção, publique o sistema num endereço público HTTPS (seu domínio/VPS) e use essa URL.
> Nos campos de webhook do painel, a plataforma já mostra a URL completa com o endereço atual — copie exatamente a exibida lá.

---

## 💬 1. WhatsApp Cloud API (Meta) — envio e recebimento de verdade

### O que você ganha
- Enviar mensagens da Central WhatsApp direto para o cliente (Graph API oficial)
- **Receber** as respostas dos clientes no histórico (webhook), com status `enviado/lido`
- Usar templates aprovados (obrigatório fora da janela de 24h do cliente)

### Passo a passo
1. Acesse [developers.facebook.com](https://developers.facebook.com) → **Meus apps** → **Criar app** → tipo **Empresa** → adicione o produto **WhatsApp**.
2. Em **WhatsApp → Configuração da API**, você verá um **número de teste** e o **Phone Number ID** (ID do número). Para produção, em **Adicionar número**, cadastre seu número WhatsApp Business.
3. **Token permanente (recomendado):** em [business.facebook.com](https://business.facebook.com) → Configurações do negócio → **Usuários do sistema** → crie um usuário, atribua o app e o WhatsApp, e gere um token com as permissões `whatsapp_business_messaging` e `whatsapp_business_management`. (O token temporário da tela de configuração expira em 24h — serve só para testar.)
4. Na plataforma: **Admin → Integrações → WhatsApp → Configurar** e preencha:
   - `Phone Number ID` · `WhatsApp Business Account ID (WABA)` · `Token de acesso` · `Verify Token` (**você inventa** uma senha qualquer, ex.: `produtovenda-webhook`) · versão `v21.0`. Marque **ativa** e salve.
5. Clique em **🔌 Testar conexão** — a plataforma chama a Graph API de verdade e mostra seu número verificado.
6. **Webhook (para receber mensagens):** na Meta, em **WhatsApp → Configuração → Webhook**:
   - URL: a exibida no painel (formato `https://SEU-ENDERECO/api/webhooks/whatsapp`)
   - Verify Token: **o mesmo** que você inventou no passo 4
   - Assine os campos **`messages`**.
7. Pronto! Envie da **Central WhatsApp** e veja as respostas chegarem no histórico. 🕘

**Regras da Meta (e da plataforma):** texto livre só dentro da **janela de 24h** após a última mensagem do cliente; fora dela, use um **template aprovado** (Utilitário/Marketing criado em WhatsApp Manager → Modelos). A plataforma só envia para clientes com consentimento registrado (LGPD) — sem spam, sempre.

---

## 💳 2. Mercado Pago — Pix (QR/copia e cola) e Cartão

### O que você ganha
- Loja pública com opção **Pix (QR Code gerado na hora)** e **Cartão (Checkout Pro)**
- Botão **💳 Cobrar** em qualquer pedido do painel
- **Confirmação automática:** quando o pagamento é aprovado, o webhook marca o pedido como `pago` sozinho

### Passo a passo
1. Acesse [mercadopago.com.br/developers](https://www.mercadopago.com.br/developers) → **Suas integrações** → crie uma aplicação (Checkout Pro / pagamentos online).
2. Em **Credenciais**: comece pelas de **teste** (`TEST-...`) e troque pelas de **produção** (`APP_USR-...`) quando for vender de verdade. Para testar Pix sem dinheiro real, use as contas de teste do Mercado Pago.
3. Na plataforma: **Admin → Integrações → Mercado Pago → Configurar**: cole `Access Token` (e `Public Key`, se quiser), marque **ativa**, salve e clique em **🔌 Testar conexão** (mostra o nome/e-mail da conta conectada).
4. **Webhook (confirmação automática):** no painel da sua aplicação no Mercado Pago → **Webhooks/Notificações IPN**, cadastre a URL exibida no painel (formato `https://SEU-ENDERECO/api/webhooks/mercadopago`) e assine o tópico **Pagamentos**.
   *(A plataforma também registra essa URL automaticamente em cada cobrança criada.)*
5. Venda! Na **Minha Store**, o cliente escolhe Pix/cartão; no painel, qualquer pedido pode ser cobrado pelo botão **💳 Cobrar**, e o status se atualiza em **Pedidos → Pagamentos (Mercado Pago)** (botão 🔄 Atualizar status força a consulta).

---

## ✉️ 3. E-mail via SMTP

1. Pegue os dados do seu provedor:
   - **Gmail/Google Workspace:** ative a verificação em 2 etapas e crie uma **Senha de app** (minha conta Google → Segurança → Senhas de app). Servidor `smtp.gmail.com`, porta `587`, STARTTLS `1`.
   - Outros: Hostinger, Locaweb, Amazon SES (SMTP), SendGrid SMTP etc. funcionam com host/porta/usuário/senha.
2. **Admin → Integrações → E-mail (SMTP) → Configurar**, salve, **Testar conexão** (autentica de verdade no servidor).
3. Use na **Central WhatsApp** (canal E-mail), nos clientes (💬 Mensagem → E-mail) ou envie uma campanha inteira em **E-mail Marketing → ✉️ Enviar agora (SMTP)** — somente para clientes que autorizaram contato, com personalização `{nome}`.

---

## 📍 4. Google Places API — Prospecção com dados reais

1. No [Google Cloud Console](https://console.cloud.google.com), crie um projeto, ative a **Places API (New)** e a cobrança (billing), e crie uma **API Key** (APIs e serviços → Credenciais). Restrinja a chave à Places API.
2. **Admin → Integrações → Google Places → Configurar**, salve e teste.
3. Em **Prospecção IA**, as buscas passam a retornar **empresas reais** da cidade/segmento (nome, endereço, telefone público comercial, site e avaliação), marcadas com a origem `Google Places API (fonte oficial)`. Sem a chave, a plataforma usa apenas a base demonstrativa e avisa. Nada de scraping — só API autorizada.

---

## 📸 5. Instagram / Facebook (Meta)

1. No seu app da Meta, adicione o produto **Facebook Login/Graph API** e conecte sua **Página** (a conta do Instagram precisa ser Business/Creator vinculada à Página).
2. Gere um **Page Access Token** com as permissões necessárias (`pages_manage_posts`, `instagram_basic`, `instagram_content_publish` — sujeitas à revisão da Meta para publicação).
3. **Admin → Integrações → Instagram/Facebook → Configurar** com `Page ID` + token, salve e teste (mostra o nome e os seguidores da Página).
4. Com a conexão ativa, o Content Studio passa a ter a base para publicar/medir pelas APIs oficiais (a publicação automática depende das permissões aprovadas pela Meta para o seu app).

---

## 🧪 Como saber se está tudo funcionando

| Integração | Teste rápido |
|---|---|
| WhatsApp | Admin → Testar conexão mostra seu número; envie para seu próprio celular da Central WhatsApp e responda — a resposta aparece no histórico |
| Mercado Pago | Admin → Testar mostra sua conta; cobre um pedido de R$ 1,00 com credenciais de teste e pague com conta teste — o pedido vira `pago` sozinho |
| SMTP | Admin → Testar autentica; envie uma mensagem para você em Clientes → 💬 Mensagem (E-mail) |
| Google Places | Prospecte "Cafeterias" na sua cidade e confira endereços/avaliações reais |
| Meta Social | Admin → Testar mostra o nome da Página |

## 🔐 Boas práticas
- Use primeiro as **credenciais de teste** do Mercado Pago e o **número de teste** da Meta; troque para produção só depois de validar.
- **Rotacione** tokens se suspeitar de vazamento (gere um novo e atualize no painel — salvar um campo vazio mantém o segredo atual).
- Mantenha o endereço público do sistema em **HTTPS** antes de cadastrar webhooks de produção.
