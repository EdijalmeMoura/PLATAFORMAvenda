#!/usr/bin/env python3
"""
Testes das melhorias da v1.4 (correções de negócio, integridade e links públicos).

Rodar:  python3 -m unittest discover -s tests -v
    ou:  python3 tests/test_improvements.py
"""
import json, os, sqlite3, subprocess, sys, tempfile, threading, time, unittest, urllib.request, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 8098
BASE = f"http://127.0.0.1:{PORT}"
SLUG = "choco-encanto"


def call(path, method="GET", body=None, token=None, raw_headers=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if raw_headers:
        headers.update(raw_headers)
    req = urllib.request.Request(BASE + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except Exception:
            return e.code, {}


def fetch(path):
    """GET que devolve o texto bruto (páginas HTML públicas)."""
    req = urllib.request.Request(BASE + path, headers={"Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, r.read().decode("utf-8"), dict(r.headers)


class ImprovementsTest(unittest.TestCase):
    proc = None
    db_path = None
    token = None

    # ---------------------------------------------------------------- setup
    @classmethod
    def setUpClass(cls):
        fd, cls.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.unlink(cls.db_path)
        env = dict(os.environ, PORT=str(PORT), PV_DB_PATH=cls.db_path, PV_MASTER_KEY="chave-teste-melhorias",
                   PV_ALLOW_RESET_LINK="1", PV_MAX_BODY_BYTES="4096")
        cls.proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "server.py")],
                                    cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for _ in range(60):
            try:
                status, data = call("/api/health")
                if status == 200 and data.get("status") == "ok":
                    break
            except Exception:
                pass
            time.sleep(0.5)
        else:
            raise RuntimeError("Servidor não subiu para os testes de melhorias")
        status, data = call("/api/auth/login", "POST", {"email": "demo@produtovenda.com.br", "password": "demo1234"})
        assert status == 200, data
        cls.token = data["token"]

    @classmethod
    def tearDownClass(cls):
        if cls.proc:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except Exception:
                cls.proc.kill()
        for path in (cls.db_path, cls.db_path + "-wal", cls.db_path + "-shm"):
            if path and os.path.exists(path):
                os.unlink(path)

    # ---------------------------------------------------------------- helpers
    def product(self, name, price=50.0, cost=20.0, stock=10):
        status, data = call("/api/products", "POST",
                            {"name": name, "price": price, "cost": cost, "stock": stock, "status": "ativo"}, self.token)
        self.assertEqual(status, 201, data)
        return data["item"]["id"]

    def order_count(self):
        status, data = call("/api/orders", token=self.token)
        self.assertEqual(status, 200, data)
        return len(data["orders"])

    def stock_of(self, product_id):
        conn = sqlite3.connect(self.db_path)
        try:
            return conn.execute("SELECT stock FROM products WHERE id=?", (product_id,)).fetchone()[0]
        finally:
            conn.close()

    def checkout(self, items, **extra):
        body = {"customer_name": "Cliente Teste", "phone": "81999990000", "items": items}
        body.update(extra)
        return call(f"/api/public/store/{SLUG}/checkout", "POST", body)

    # ---------------------------------------------------------------- cupons
    def test_coupon_discount_never_goes_negative(self):
        pid = self.product("Produto Cupom Gigante", price=30.0, stock=30)
        status, data = call("/api/coupons", "POST",
                            {"code": "gigante500", "type": "fixo", "value": 500, "kind": "campanha", "active": 1}, self.token)
        self.assertEqual(status, 201, data)
        self.assertEqual(data["item"]["code"], "GIGANTE500")  # normalizado em maiúsculas
        status, order = self.checkout([{"product_id": pid, "qty": 1}], coupon="GIGANTE500")
        self.assertEqual(status, 200, order)
        self.assertEqual(order["total"], 0.0)                 # nunca negativo
        self.assertEqual(order["discount"], 30.0)             # desconto limitado ao valor do carrinho

    def test_coupon_duplicate_and_invalid_percent_are_blocked(self):
        status, first = call("/api/coupons", "POST",
                             {"code": "UNICO10", "type": "percentual", "value": 10, "kind": "campanha", "active": 1}, self.token)
        self.assertEqual(status, 201, first)
        status, dup = call("/api/coupons", "POST", {"code": "unico10", "type": "percentual", "value": 5}, self.token)
        self.assertEqual(status, 400)
        self.assertIn("já existe", dup["error"].lower())
        status, invalid = call("/api/coupons", "POST", {"code": "MAIS150", "type": "percentual", "value": 150}, self.token)
        self.assertEqual(status, 400)
        status, invalid_code = call("/api/coupons", "POST", {"code": "ab", "type": "percentual", "value": 10}, self.token)
        self.assertEqual(status, 400)
        status, zero = call("/api/coupons", "POST", {"code": "ZERO10", "type": "percentual", "value": 0}, self.token)
        self.assertEqual(status, 400)

    # ---------------------------------------------------------------- pagamentos
    def test_online_payment_without_gateway_does_not_mark_order_as_paid(self):
        pid = self.product("Produto Pix Sem Gateway", price=40.0, stock=5)
        before = self.order_count()
        status, err = self.checkout([{"product_id": pid, "qty": 1}], payment_method="pix")
        self.assertEqual(status, 400, err)
        self.assertIn("pagamento online", err["error"].lower())
        self.assertEqual(self.order_count(), before)      # nada de pedido fantasma marcado como pago
        self.assertEqual(self.stock_of(pid), 5)           # estoque intacto
        status, err = self.checkout([{"product_id": pid, "qty": 1}], payment_method="boleto")
        self.assertEqual(status, 400)                     # método desconhecido recusado

    # ---------------------------------------------------------------- estoque
    def test_insufficient_stock_rolls_back_everything(self):
        pid = self.product("Produto Estoque Curto", price=25.0, stock=2)
        before = self.order_count()
        status, err = self.checkout([{"product_id": pid, "qty": 5}])
        self.assertEqual(status, 400, err)
        self.assertIn("estoque insuficiente", err["error"].lower())
        self.assertEqual(self.order_count(), before)
        self.assertEqual(self.stock_of(pid), 2)
        conn = sqlite3.connect(self.db_path)
        try:
            itens = conn.execute("SELECT COUNT(*) FROM order_items WHERE product_id=?", (pid,)).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(itens, 0)                        # sem item de pedido órfão

    def test_garbage_quantity_does_not_break_checkout(self):
        pid = self.product("Produto Qtd Estranha", price=10.0, stock=3)
        status, order = self.checkout([{"product_id": pid, "qty": "abc"}])
        self.assertEqual(status, 200, order)              # cai para 1 em vez de estourar 500
        self.assertEqual(order["total"], 10.0)

    def test_concurrent_checkout_never_sells_more_than_stock(self):
        for attempt in range(2):
            pid = self.product(f"Produto Concorrente {attempt}", price=99.0, stock=1)
            before = self.order_count()
            results = []
            lock = threading.Lock()

            def buy():
                status, _ = self.checkout([{"product_id": pid, "qty": 1}])
                with lock:
                    results.append(status)

            threads = [threading.Thread(target=buy) for _ in range(2)]
            [t.start() for t in threads]
            [t.join(timeout=30) for t in threads]
            sucessos = results.count(200)
            if sucessos == 0 and attempt == 0:
                continue                                   # rede/agenda instável: tenta de novo
            self.assertEqual(sucessos, 1, f"esperava 1 venda, veio {results}")
            self.assertEqual(self.stock_of(pid), 0)        # estoque nunca fica negativo
            self.assertEqual(self.order_count(), before + 1)
            return
        self.fail(f"nenhuma venda concluída nos dois cenários: {results}")

    # ---------------------------------------------------------------- sob encomenda
    def test_backorder_setting_allows_selling_out_of_stock(self):
        pid = self.product("Produto Sob Encomenda", price=70.0, stock=0)
        status, err = self.checkout([{"product_id": pid, "qty": 1}])
        self.assertEqual(status, 400)                      # padrão: bloqueia venda sem estoque
        status, saved = call("/api/settings", "PUT", {"allow_backorder": 1}, self.token)
        self.assertEqual(status, 200, saved)
        status, order = self.checkout([{"product_id": pid, "qty": 2}])
        self.assertEqual(status, 200, order)
        self.assertEqual(order["total"], 140.0)
        self.assertEqual(self.stock_of(pid), 0)            # nunca fica negativo
        call("/api/settings", "PUT", {"allow_backorder": 0}, self.token)

    def test_partial_settings_update_preserves_other_fields(self):
        status, before = call("/api/settings", token=self.token)
        self.assertEqual(status, 200, before)
        status, _ = call("/api/settings", "PUT", {"store_name": "Loja Renomeada"}, self.token)
        self.assertEqual(status, 200)
        status, after = call("/api/settings", token=self.token)
        self.assertEqual(after["store"]["store_name"], "Loja Renomeada")
        self.assertEqual(after["company"]["city"], before["company"]["city"])
        self.assertEqual(after["company"]["segment"], before["company"]["segment"])
        self.assertEqual(after["company"]["goal_monthly"], before["company"]["goal_monthly"])
        self.assertEqual(after["store"].get("allow_backorder"), before["store"].get("allow_backorder"))

    # ---------------------------------------------------------------- links públicos
    def test_pretty_store_url_has_social_preview(self):
        status, html, headers = fetch(f"/loja/{SLUG}")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers.get("Content-Type", ""))
        self.assertIn('property="og:title"', html)
        self.assertIn('property="og:description"', html)
        self.assertIn('rel="canonical"', html)
        self.assertIn('application/ld+json', html)
        self.assertIn("#/loja/" + SLUG, html)                     # botão leva para a loja completa
        status, store = call(f"/api/public/store/{SLUG}")
        self.assertIn(store["products"][0]["name"], html)         # catálogo aparece no HTML (crawlers)

    def test_pretty_product_url_and_missing_store_page(self):
        status, store = call(f"/api/public/store/{SLUG}")
        pid = store["products"][0]["id"]
        status, html, _ = fetch(f"/loja/{SLUG}/produto/{pid}")
        self.assertEqual(status, 200)
        self.assertIn(store["products"][0]["name"], html)
        self.assertIn("BR", html)                                 # dados estruturados schema.org
        status, _ = call("/api/public/store/loja-que-nao-existe")
        self.assertEqual(status, 404)
        try:
            fetch("/loja/loja-que-nao-existe")
            self.fail("esperava 404 para loja inexistente")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 404)

    def test_robots_and_sitemap(self):
        status, robots, _ = fetch("/robots.txt")
        self.assertEqual(status, 200)
        self.assertIn("Sitemap:", robots)
        self.assertIn("Disallow: /api/", robots)
        status, sitemap, _ = fetch("/sitemap.xml")
        self.assertEqual(status, 200)
        self.assertIn(f"/loja/{SLUG}", sitemap)

    def test_write_then_read_on_same_connection_sees_new_data(self):
        """Regressão: a resposta HTTP só pode sair depois do commit (antes, ler logo após
        gravar na mesma conexão keep-alive podia devolver dados desatualizados)."""
        import http.client
        conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=20)
        try:
            for i in range(10):
                body = json.dumps({"code": f"SEQ{i:02d}", "type": "percentual", "value": 5, "kind": "campanha", "active": 1})
                conn.request("POST", "/api/coupons", body=body,
                             headers={"Content-Type": "application/json", "Authorization": "Bearer " + self.token})
                resp = conn.getresponse()
                self.assertEqual(resp.status, 201, resp.read())
                resp.read()
                conn.request("GET", "/api/coupons", headers={"Authorization": "Bearer " + self.token})
                resp = conn.getresponse()
                data = json.loads(resp.read())
                self.assertEqual(resp.status, 200)
                self.assertIn(f"SEQ{i:02d}", {c["code"] for c in data["coupons"]})
        finally:
            conn.close()

    # ---------------------------------------------------------------- infraestrutura
    def test_health_reports_uptime_and_version(self):
        status, data = call("/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(data["version"], "1.4.0")
        self.assertIsInstance(data["uptime_seconds"], int)
        self.assertIn("public_url", data)

    def test_indexes_and_wal_are_configured(self):
        conn = sqlite3.connect(self.db_path)
        try:
            indexes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
            self.assertIn("idx_products_company_id_status", indexes)
            self.assertIn("idx_sessions_token_hash", indexes)
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(mode.lower(), "wal")

    def test_huge_body_is_rejected(self):
        big = {"image_data": "data:image/png;base64," + "A" * 5000}
        # Content-Length acima do limite configurado (PV_MAX_BODY_BYTES=4096)
        req = urllib.request.Request(BASE + "/api/products/1/image", method="POST",
                                     data=json.dumps(big).encode(),
                                     headers={"Content-Type": "application/json", "Authorization": "Bearer " + self.token})
        try:
            urllib.request.urlopen(req, timeout=20)
            self.fail("esperava 413")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 413)

    def test_rate_limiter_blocks_after_limit(self):
        status, _ = call("/api/auth/forgot", "POST", {"email": "ninguem@teste.com"})
        self.assertEqual(status, 200)
        limited = False
        for _ in range(30):
            status, _ = call("/api/auth/forgot", "POST", {"email": "ninguem2@teste.com"})
            if status == 429:
                limited = True
                break
        self.assertTrue(limited, "o limite de requisições do /api/auth/forgot não entrou em ação")


if __name__ == "__main__":
    unittest.main(verbosity=2)
