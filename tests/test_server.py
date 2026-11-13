"""Verificações reais de autenticação, isolamento e fluxo de atendimento."""

import http.client
import json
import secrets
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ouvidoria as server


class SecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        server.DB = Path(cls.temp.name) / "data" / "test.sqlite3"
        server.KEY_PATH = Path(cls.temp.name) / "segredos" / "email.key"
        server.DIRECTOR = "diretor@camporeal.edu.br"
        server.SUPERVISORS = {"supervisor@camporeal.edu.br"}
        server.initialize()
        with server.database() as db:
            server.insert_account(
                db, "diretor@camporeal.edu.br", "SenhaTeste123!", "diretor"
            )
            server.insert_account(
                db, "supervisor@camporeal.edu.br", "SenhaTeste123!", "supervisor"
            )
        cls.http = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.port = cls.http.server_port
        server.APP_URL = f"http://localhost:{cls.port}"
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.thread.join()
        cls.temp.cleanup()

    def request(self, path, data=None, session=None, origin=None, csrf=True, host=None):
        if data is not None and path == "/api/tickets":
            data = {
                **data,
                "confirmed": True,
                "submission_id": "test-" + secrets.token_hex(12),
            }
        if data is not None and path == "/api/identity" and "reason" not in data:
            data = {
                **data,
                "reason": "Consulta necessária para encaminhar corretamente o atendimento.",
            }
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {
            "Content-Type": "application/json",
            "Origin": origin or server.APP_URL,
        }
        if host:
            headers["Host"] = host
        if session:
            headers["Cookie"] = session["cookie"]
            if csrf:
                headers["X-CSRF-Token"] = session["csrf"]
        connection.request(
            "POST" if data is not None else "GET",
            path,
            json.dumps(data) if data is not None else None,
            headers,
        )
        response = connection.getresponse()
        body = response.read()
        result = (
            json.loads(body)
            if response.getheader("Content-Type", "").startswith("application/json")
            else body.decode()
        )
        cookie = response.getheader("Set-Cookie", "").split(";")[0]
        status = response.status
        connection.close()
        return status, result, cookie

    def login(self, email):
        with server.database() as db:
            exists = db.execute(
                "SELECT 1 FROM accounts WHERE email=?", (server.account_id(email),)
            ).fetchone()
        payload = {"email": email, "password": "SenhaTeste123!"}
        if not exists:
            with server.database() as db:
                server.authorize_student(db, email)
            status, _, cookie = self.request("/api/register", payload)
            self.assertEqual(status, 201)
            self.assertEqual(cookie, "")
        status, _, cookie = self.request("/api/login", payload)
        self.assertEqual(status, 200)
        status, profile, _ = self.request(
            "/api/me", session={"cookie": cookie, "csrf": ""}
        )
        self.assertEqual(status, 200)
        return {**profile, "cookie": cookie}

    def test_01_authentication_and_domain(self):
        with server.database() as db:
            server.authorize_student(db, "novo@camporeal.edu.br")
        self.assertEqual(self.request("/api/tickets")[0], 401)
        for email in [
            "pessoa@gmail.com",
            "a@camporeal.edu.br.evil.com",
            "a@sub.camporeal.edu.br",
        ]:
            self.assertEqual(
                self.request(
                    "/api/register", {"email": email, "password": "SenhaTeste123!"}
                )[0],
                400,
            )
        self.assertEqual(
            self.request(
                "/api/register", {"email": "novo@camporeal.edu.br", "password": "curta"}
            )[0],
            400,
        )
        self.assertEqual(
            self.request(
                "/api/login",
                {"email": "diretor@camporeal.edu.br", "password": "Incorreta123"},
            )[0],
            401,
        )
        status, _, cookie = self.request(
            "/api/register",
            {
                "email": "novo@camporeal.edu.br",
                "password": "SenhaTeste123!",
                "role": "diretor",
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(cookie, "")
        account = self.login("novo@camporeal.edu.br")
        self.assertEqual(account["role"], "aluno")
        self.assertEqual(
            self.request(
                "/api/register",
                {"email": "diretor@camporeal.edu.br", "password": "SenhaTeste123!"},
            )[0],
            409,
        )
        for _ in range(15):
            result = self.request(
                "/api/login",
                {"email": "limite@camporeal.edu.br", "password": "Incorreta123"},
            )
        self.assertEqual(
            self.request(
                "/api/login",
                {"email": "limite@camporeal.edu.br", "password": "Incorreta123"},
            )[0],
            429,
        )

    def test_02_roles_privacy_and_workflow(self):
        alice = self.login("alice@camporeal.edu.br")
        bob = self.login("bob@camporeal.edu.br")
        supervisor = self.login("supervisor@camporeal.edu.br")
        director = self.login("diretor@camporeal.edu.br")
        payload = {
            "kind": "Reclamação",
            "sector": "Geral",
            "subject": "Relato de teste",
            "body": "Relato suficientemente detalhado para validar o atendimento.",
            "anonymous": True,
        }
        status, result, _ = self.request("/api/tickets", payload, alice)
        self.assertEqual(status, 201)
        ticket_id = result["id"]
        self.assertEqual(self.request("/api/tickets", session=bob)[1], [])
        self.assertEqual(
            self.request(
                "/api/reply", {"id": ticket_id, "body": "Mensagem de invasão"}, bob
            )[0],
            404,
        )
        for account in (supervisor, director):
            status, items, _ = self.request("/api/tickets", session=account)
            self.assertEqual(status, 200)
            self.assertIsNone(items[0]["identity"])
            self.assertNotIn(alice["email"], json.dumps(items))
        self.assertEqual(
            self.request("/api/identity", {"id": ticket_id}, supervisor)[0], 403
        )
        self.assertEqual(
            self.request("/api/identity", {"id": ticket_id}, alice)[0], 403
        )
        self.assertEqual(
            self.request("/api/identity", {"id": ticket_id}, director)[1]["email"],
            alice["email"],
        )
        with server.database() as db:
            self.assertEqual(
                db.execute(
                    "SELECT COUNT(*) FROM audit WHERE ticket=?", (ticket_id,)
                ).fetchone()[0],
                1,
            )
        self.assertEqual(
            self.request(
                "/api/reply",
                {"id": ticket_id, "body": "A equipe está verificando o problema."},
                supervisor,
            )[0],
            200,
        )
        self.assertEqual(
            self.request("/api/tickets", session=alice)[1][0]["status"], "Respondida"
        )
        self.assertEqual(
            self.request(
                "/api/status", {"id": ticket_id, "status": "Resolvida"}, supervisor
            )[0],
            400,
        )
        self.assertEqual(
            self.request(
                "/api/status", {"id": ticket_id, "status": "Resolvida"}, alice
            )[0],
            200,
        )
        self.assertEqual(
            self.request(
                "/api/status", {"id": ticket_id, "status": "Em análise"}, alice
            )[0],
            200,
        )
        self.assertEqual(
            self.request(
                "/api/reply",
                {"id": ticket_id, "body": "Ainda preciso de ajuda."},
                alice,
            )[0],
            200,
        )
        self.assertEqual(self.request("/api/tickets", payload, supervisor)[0], 403)
        self.assertEqual(
            self.request(
                "/api/status",
                {"id": ticket_id, "status": "Resolvida"},
                alice,
                csrf=False,
            )[0],
            403,
        )
        self.assertEqual(
            self.request(
                "/api/status",
                {"id": ticket_id, "status": "Resolvida"},
                alice,
                origin="https://outro.site",
            )[0],
            403,
        )
        self.assertEqual(self.request("/data/ouvidoria.sqlite3")[0], 404)
        self.assertEqual(self.request("/server.py")[0], 404)
        self.assertEqual(self.request("/api/logout", {}, alice)[0], 200)
        self.assertEqual(self.request("/api/me", session=alice)[0], 401)

    def test_03_password_storage_and_session_expiration(self):
        account = self.login("expirado@camporeal.edu.br")
        with server.database() as db:
            saved = db.execute(
                "SELECT * FROM accounts WHERE email=?",
                (server.account_id(account["email"]),),
            ).fetchone()
            self.assertNotEqual(saved["hash"], "SenhaTeste123!")
            self.assertEqual(
                saved["hash"], server.password_hash("SenhaTeste123!", saved["salt"])
            )
            db.execute(
                "UPDATE sessions SET expires=0 WHERE email=?",
                (server.account_id(account["email"]),),
            )
        self.assertEqual(self.request("/api/me", session=account)[0], 401)
        self.assertEqual(
            self.request("/api/verify", {"email": account["email"], "code": "123456"})[
                0
            ],
            401,
        )

    def test_04_legacy_email_cannot_be_claimed_publicly(self):
        email = "historico@camporeal.edu.br"
        with server.database() as db:
            db.execute(
                "INSERT INTO tickets(id,email,anonymous,kind,subject,sector,body,status,created) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    "CR-HISTORICO",
                    server.ensure_identity(db, email),
                    1,
                    "Crítica",
                    "Registro anterior",
                    "Geral",
                    "Este relato pertence a uma conta antiga.",
                    "Recebida",
                    1,
                ),
            )
        self.assertEqual(
            self.request(
                "/api/register", {"email": email, "password": "SenhaTeste123!"}
            )[0],
            403,
        )
        with server.database() as db:
            server.insert_account(db, email, "SenhaTeste123!", "aluno")
        account = self.login(email)
        rows = self.request("/api/tickets", session=account)[1]
        self.assertEqual(rows[0]["id"], "CR-HISTORICO")

    def test_05_staff_archive_and_student_reopening(self):
        alice = self.login("alice@camporeal.edu.br")
        supervisor = self.login("supervisor@camporeal.edu.br")
        director = self.login("diretor@camporeal.edu.br")
        payload = {
            "kind": "Reclamação",
            "sector": "Infraestrutura",
            "subject": "Manutenção da iluminação",
            "body": "Precisamos de manutenção na iluminação do estacionamento.",
            "anonymous": True,
        }
        status, created, _ = self.request("/api/tickets", payload, alice)
        self.assertEqual(status, 201)
        ticket_id = created["id"]
        self.assertEqual(
            self.request("/api/archive", {"id": ticket_id, "archived": True}, alice)[0],
            403,
        )
        self.assertEqual(
            self.request(
                "/api/archive", {"id": ticket_id, "archived": "true"}, supervisor
            )[0],
            400,
        )
        self.assertEqual(
            self.request(
                "/api/archive", {"id": ticket_id, "archived": True}, supervisor
            )[0],
            200,
        )
        for account in (alice, supervisor, director):
            record = next(
                t
                for t in self.request("/api/tickets", session=account)[1]
                if t["id"] == ticket_id
            )
            self.assertEqual(record["status"], "Resolvida")
            self.assertEqual(record["archived"], 1)
            self.assertEqual(record["sector"], "Infraestrutura")
            if account["role"] != "aluno":
                self.assertIsNone(record["identity"])
                self.assertNotIn(alice["email"], json.dumps(record))
        self.request("/api/archive", {"id": ticket_id, "archived": True}, supervisor)
        with server.database() as db:
            self.assertEqual(
                db.execute(
                    "SELECT COUNT(*) FROM audit WHERE ticket=? AND action='Resolver e arquivar'",
                    (ticket_id,),
                ).fetchone()[0],
                1,
            )
        self.assertEqual(
            self.request(
                "/api/archive", {"id": ticket_id, "archived": False}, director
            )[0],
            200,
        )
        record = next(
            t
            for t in self.request("/api/tickets", session=supervisor)[1]
            if t["id"] == ticket_id
        )
        self.assertEqual((record["status"], record["archived"]), ("Em análise", 0))
        self.request("/api/archive", {"id": ticket_id, "archived": True}, director)
        self.assertEqual(
            self.request(
                "/api/reply",
                {"id": ticket_id, "body": "Ainda preciso de ajuda neste ponto."},
                alice,
            )[0],
            200,
        )
        record = next(
            t
            for t in self.request("/api/tickets", session=supervisor)[1]
            if t["id"] == ticket_id
        )
        self.assertEqual((record["status"], record["archived"]), ("Em análise", 0))
        self.assertGreaterEqual(len(record["messages"]), 5)
        self.request("/api/status", {"id": ticket_id, "status": "Resolvida"}, alice)
        record = next(
            t
            for t in self.request("/api/tickets", session=supervisor)[1]
            if t["id"] == ticket_id
        )
        self.assertEqual(record["archived"], 1)
        self.request("/api/status", {"id": ticket_id, "status": "Em análise"}, alice)
        record = next(
            t
            for t in self.request("/api/tickets", session=supervisor)[1]
            if t["id"] == ticket_id
        )
        self.assertEqual(record["archived"], 0)

    def test_06_register_requires_a_separate_login(self):
        email = "cadastro-sem-login@camporeal.edu.br"
        with server.database() as db:
            server.authorize_student(db, email)
            before = db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        status, result, cookie = self.request(
            "/api/register", {"email": email, "password": "SenhaTeste123!"}
        )
        self.assertEqual(status, 201)
        self.assertEqual(cookie, "")
        self.assertEqual(self.request("/api/me")[0], 401)
        with server.database() as db:
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0], before
            )
        self.assertEqual(self.login(email)["email"], email)

    def test_07_local_network_origin_is_checked(self):
        payload = {"email": "supervisor@camporeal.edu.br", "password": "SenhaTeste123!"}
        for host in (f"192.168.1.20:{self.port}", f"127.0.0.1:{self.port}"):
            self.assertEqual(
                self.request("/api/login", payload, origin="http://" + host, host=host)[
                    0
                ],
                200,
            )
        host = f"192.168.1.20:{self.port}"
        for origin in (
            f"http://192.168.1.21:{self.port}",
            "https://outro.site",
            "null",
            "http://192.168.1.20:1",
        ):
            self.assertEqual(
                self.request("/api/login", payload, origin=origin, host=host)[0], 403
            )
        malicious = f"outro.site:{self.port}"
        self.assertEqual(
            self.request(
                "/api/login", payload, origin="http://" + malicious, host=malicious
            )[0],
            403,
        )


if __name__ == "__main__":
    unittest.main()
