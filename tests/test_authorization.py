"""E-mails precisam ser liberados pelo operador antes do cadastro público."""

import http.client
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ouvidoria as app


class StudentAuthorizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        root = Path(cls.temp.name)
        cls.db_patch = patch.object(app, "DB", root / "data" / "teste.sqlite3")
        cls.key_patch = patch.object(app, "KEY_PATH", root / "segredos" / "email.key")
        cls.db_patch.start()
        cls.key_patch.start()
        app.initialize()
        cls.http = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        cls.origin_patch = patch.object(
            app, "APP_URL", f"http://localhost:{cls.http.server_port}"
        )
        cls.origin_patch.start()
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.thread.join()
        cls.origin_patch.stop()
        cls.key_patch.stop()
        cls.db_patch.stop()
        cls.temp.cleanup()

    def request(self, path, data=None, cookie=""):
        conn = http.client.HTTPConnection(
            "127.0.0.1", self.http.server_port, timeout=10
        )
        conn.request(
            "POST" if data is not None else "GET",
            path,
            json.dumps(data) if data is not None else None,
            {
                "Origin": app.APP_URL,
                "Content-Type": "application/json",
                "Cookie": cookie,
            },
        )
        response = conn.getresponse()
        result = json.loads(response.read())
        status = response.status
        cookie = response.getheader("Set-Cookie", "").split(";")[0]
        conn.close()
        return status, result, cookie

    def payload(self, email):
        return {"email": email, "password": "SenhaTeste123!"}

    def test_unlisted_email_cannot_register_even_with_forged_flags(self):
        email = "nao-liberado@camporeal.edu.br"
        status, _, cookie = self.request(
            "/api/register",
            {**self.payload(email), "authorized": True, "role": "diretor"},
        )
        self.assertEqual(status, 403)
        self.assertEqual(cookie, "")
        with app.database() as db:
            self.assertFalse(
                db.execute(
                    "SELECT 1 FROM accounts WHERE email=?", (app.account_id(email),)
                ).fetchone()
            )
            self.assertFalse(
                db.execute(
                    "SELECT 1 FROM student_authorizations WHERE email=?",
                    (app.account_id(email),),
                ).fetchone()
            )

    def test_menu_authorizes_without_creating_account_or_password(self):
        email = "liberado@camporeal.edu.br"
        with patch("builtins.input", side_effect=["4", email, "0"]), patch(
            "getpass.getpass"
        ) as password, patch("builtins.print"):
            app.manage_accounts()
            password.assert_not_called()
        identifier = app.account_id(email)
        with app.database() as db:
            row = db.execute(
                "SELECT * FROM student_authorizations WHERE email=?", (identifier,)
            ).fetchone()
            self.assertIsNone(row["activated_at"])
            self.assertFalse(
                db.execute(
                    "SELECT 1 FROM accounts WHERE email=?", (identifier,)
                ).fetchone()
            )
            self.assertNotIn(email, "\n".join(db.iterdump()))
        status, result, cookie = self.request(
            "/api/register", {**self.payload(email), "role": "diretor"}
        )
        self.assertEqual(status, 201)
        self.assertIn("recovery_code", result)
        self.assertEqual(cookie, "")
        with app.database() as db:
            self.assertGreater(
                db.execute(
                    "SELECT activated_at FROM student_authorizations WHERE email=?",
                    (identifier,),
                ).fetchone()[0],
                0,
            )
            self.assertEqual(
                db.execute(
                    "SELECT role FROM accounts WHERE email=?", (identifier,)
                ).fetchone()[0],
                "aluno",
            )
        self.assertEqual(self.request("/api/register", self.payload(email))[0], 409)
        cookie = self.request("/api/login", self.payload(email))[2]
        self.assertEqual(self.request("/api/me", cookie=cookie)[1]["role"], "aluno")

    def test_pending_authorization_can_be_cancelled_and_recreated(self):
        email = "cancelado@camporeal.edu.br"
        with app.database() as db:
            self.assertTrue(app.authorize_student(db, email))
            self.assertFalse(app.authorize_student(db, email))
            self.assertTrue(app.cancel_student_authorization(db, email))
            self.assertFalse(app.cancel_student_authorization(db, email))
        self.assertEqual(self.request("/api/register", self.payload(email))[0], 403)
        with app.database() as db:
            app.authorize_student(db, email)
        self.assertEqual(self.request("/api/register", self.payload(email))[0], 201)
        with app.database() as db:
            with self.assertRaises(ValueError):
                app.cancel_student_authorization(db, email)
        self.assertEqual(self.request("/api/login", self.payload(email))[0], 200)

    def test_addresses_are_normalized_and_invalid_domains_rejected(self):
        with app.database() as db:
            with self.assertRaises(ValueError):
                app.authorize_student(db, "pessoa@gmail.com")
            app.authorize_student(db, " Normalizado@camporeal.edu.br ")
        app.initialize()
        status, _, _ = self.request(
            "/api/register", self.payload(" NORMALIZADO@CAMPOREAL.EDU.BR ")
        )
        self.assertEqual(status, 201)
        self.assertEqual(
            self.request("/api/register", self.payload("a@camporeal.edu.br.outro.com"))[
                0
            ],
            400,
        )

    def test_existing_accounts_do_not_need_a_new_authorization(self):
        email = "conta-existente@camporeal.edu.br"
        with app.database() as db:
            app.insert_account(db, email, "SenhaTeste123!", "aluno")
        self.assertEqual(self.request("/api/login", self.payload(email))[0], 200)
        self.assertEqual(self.request("/api/register", self.payload(email))[0], 409)
        with app.database() as db:
            with self.assertRaises(ValueError):
                app.authorize_student(db, email)

    def test_staff_reserved_address_cannot_be_authorized_as_student(self):
        with patch.object(
            app, "DIRECTOR", "reservado@camporeal.edu.br"
        ), app.database() as db:
            with self.assertRaises(ValueError):
                app.authorize_student(db, "reservado@camporeal.edu.br")

    def test_list_menu_shows_pending_and_used_without_changing_accounts(self):
        email = "lista-pendente@camporeal.edu.br"
        with app.database() as db:
            app.authorize_student(db, email)
            before = db.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
        with patch("builtins.input", side_effect=["5", "0"]), patch(
            "builtins.print"
        ) as output:
            app.manage_accounts()
        text = "\n".join(str(call) for call in output.call_args_list)
        self.assertIn(email, text)
        self.assertIn("Aguardando cadastro no site", text)
        with app.database() as db:
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM accounts").fetchone()[0], before
            )


if __name__ == "__main__":
    unittest.main()
