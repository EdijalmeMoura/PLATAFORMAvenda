#!/usr/bin/env python3
"""
Testes de fumaça (smoke) do ProdutoVenda IA — sem dependencias externas.
Sobe o servidor real numa porta e banco temporarios e testa os fluxos principais.

Rodar:  python3 -m unittest discover -s tests -v
    ou:  python3 tests/test_smoke.py
"""
import json, os, sqlite3, subprocess, sys, tempfile, time, unittest, urllib.request, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 8099
BASE = f"http://127.0.0.1:{PORT}"


def call(path, method="GET", body=None, token=None):
    req = urllib.request.Request(BASE + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json",
                                          **({"Authorization": "Bearer " + token} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except Exception:
            return e.code, {}


class ProdutoVendaSmokeTest(unittest.TestCase):
    proc = None
    db_path = None
    demo_token = None

    @classmethod
    def setUpClass(cls):
        fd, cls.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.unlink(cls.db_path)
        env = dict(os.environ, PORT=str(PORT), PV_DB_PATH=cls.db_path,
                   PV_MASTER_KEY="chave-de-teste-local", PV_ALLOW_RESET_LINK="1")
        cls.proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "server.py")],
                                    cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(60):
            try:
                status, data = call("/api/health")
                if status == 200 and data.get("status") == "ok":
                    break
            except Exception:
                pass
            time.sleep(0.5)
        else:
            raise RuntimeError("Servidor não subiu para os testes")
        status, data = call("/api/auth/login", "POST", {"email": "demo@produtovenda.com.br", "password": "demo1234"})
        assert status == 200, data
        cls.demo_token = data["token"]

    @classmethod
    def tearDownClass(cls):
        if cls.proc:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except Exception:
                cls.proc.kill()
        if cls.db_path and os.path.exists(cls.db_path):
            os.unlink(cls.db_path)

    # ---------------------------------------------------------------
    def test_health_and_demo_dashboard(self):
        status, data = call("/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(data["db"], "ok")
        status, dash = call("/api/dashboard", token=self.demo_token)
        self.assertEqual(status, 200)
        self.assertIn("revenue_month", dash["kpis"])
        self.assertGreaterEqual(dash["kpis"]["orders"], 1)

    def test_tenant_isolation(self):
        status, reg = call("/api/auth/register", "POST",
                           {"name": "Isolado", "email": "isolado@teste.com", "password": "123456", "company_name": "Loja Isolada"})
        self.assertEqual(status, 200)
        tok = reg["token"]
        status, products = call("/api/products", token=tok)
        self.assertEqual(products["products"], [])
        # nao enxerga produto do tenant demo (id 1)
        status, _ = call("/api/products/1/generate-page", "POST", {}, tok)
        self.assertEqual(status, 404)

    def test_public_store_flow(self):
        status, store = call("/api/public/store/choco-encanto")
        self.assertEqual(status, 200)
        self.assertGreaterEqual(len(store["products"]), 1)
        pid = store["products"][0]["id"]
        status, cart = call("/api/public/store/choco-encanto/cart", "POST",
                            {"customer_name": "Teste Loja", "phone": "81911112222",
                             "items": [{"product_id": pid, "qty": 1}]})
        self.assertEqual(status, 201)
        status, order = call("/api/public/store/choco-encanto/checkout", "POST",
                             {"customer_name": "Teste Loja", "phone": "81911112222",
                              "coupon": "BEMVINDO10", "items": [{"product_id": pid, "qty": 1}]})
        self.assertEqual(status, 200)
        self.assertEqual(order["order_status"], "pago")
        self.assertGreater(order["discount"], 0)
        status, review = call("/api/public/store/choco-encanto/review", "POST",
                              {"product_id": pid, "customer_name": "Teste Loja", "rating": 5, "comment": "Excelente!"})
        self.assertEqual(status, 201)

    def test_integrations_secrets_encrypted_and_masked(self):
        status, saved = call("/api/integrations/whatsapp", "PUT",
                             {"active": True, "config": {"phone_number_id": "111",
                                                         "access_token": "EAA-SEGREDO-9999",
                                                         "verify_token": "verify-teste"}},
                             self.demo_token)
        self.assertEqual(status, 200)
        self.assertTrue(saved["integration"]["config"]["access_token"].startswith("••••"))
        conn = sqlite3.connect(self.db_path)
        raw = conn.execute("SELECT config FROM integrations WHERE provider='whatsapp'").fetchone()[0]
        conn.close()
        self.assertNotIn("EAA-SEGREDO-9999", raw)  # criptografado em repouso
        self.assertIn("enc:v1:", raw)
        # webhook de verificacao com o token salvo
        try:
            with urllib.request.urlopen(BASE + "/api/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=verify-teste&hub.challenge=CH42") as r:
                self.assertEqual(r.read().decode(), "CH42")
        except Exception as e:
            self.fail(f"webhook verify falhou: {e}")
        # sem Mercado Pago configurado -> erro claro, nada simulado
        status, err = call("/api/payments/create", "POST", {"amount": 10, "method": "pix"}, self.demo_token)
        self.assertEqual(status, 400)

    def test_password_reset_flow(self):
        status, forgot = call("/api/auth/forgot", "POST", {"email": "demo@produtovenda.com.br"})
        self.assertEqual(status, 200)
        self.assertIn("reset_link", forgot)  # PV_ALLOW_RESET_LINK=1 apenas nos testes
        token = forgot["reset_link"].split("reset_token=")[1].split("#")[0]
        status, reset = call("/api/auth/reset", "POST", {"token": token, "password": "novaSenha123"})
        self.assertEqual(status, 200)
        status, _ = call("/api/auth/login", "POST", {"email": "demo@produtovenda.com.br", "password": "novaSenha123"})
        self.assertEqual(status, 200)
        # token nao pode ser reutilizado
        status, _ = call("/api/auth/reset", "POST", {"token": token, "password": "outraSenha123"})
        self.assertEqual(status, 400)
        # restaura a senha demo para nao quebrar outros testes
        status, forgot = call("/api/auth/forgot", "POST", {"email": "demo@produtovenda.com.br"})
        token = forgot["reset_link"].split("reset_token=")[1].split("#")[0]
        call("/api/auth/reset", "POST", {"token": token, "password": "demo1234"})
        status, data = call("/api/auth/login", "POST", {"email": "demo@produtovenda.com.br", "password": "demo1234"})
        type(self).demo_token = data["token"]

    def test_export_and_automations(self):
        status, export = call("/api/admin/export", token=self.demo_token)
        self.assertEqual(status, 200)
        self.assertIn("products", export["data"])
        self.assertNotIn("pass_hash", json.dumps(export))  # nunca exporta segredos
        status, run = call("/api/automations/run", "POST", {}, self.demo_token)
        self.assertEqual(status, 200)
        self.assertTrue(run["runs"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
