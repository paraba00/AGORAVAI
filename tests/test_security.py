"""Testes HTTP de recuperação, criptografia e acesso justificado à autoria."""

import ast
import hashlib
import http.client
import json
import secrets
import sqlite3
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ouvidoria as app
from cryptography.fernet import Fernet


class SecurityFeaturesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        root = Path(cls.temp.name)
        cls.db_patch = patch.object(app, "DB", root / "data" / "test.sqlite3")
        cls.key_patch = patch.object(app, "KEY_PATH", root / "segredos" / "email.key")
        cls.db_patch.start()
        cls.key_patch.start()
        app.initialize()
        with app.database() as db:
            app.insert_account(
                db, "direcao@camporeal.edu.br", "SenhaTeste123!", "diretor"
            )
            app.insert_account(
                db, "equipe@camporeal.edu.br", "SenhaTeste123!", "supervisor"
            )
        cls.http = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        cls.port = cls.http.server_port
        cls.origin_patch = patch.object(app, "APP_URL", f"http://localhost:{cls.port}")
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

    def request(self, path, data=None, session=None, csrf=True):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        headers = {"Content-Type": "application/json", "Origin": app.APP_URL}
        if session:
            headers["Cookie"] = session["cookie"]
            if csrf:
                headers["X-CSRF-Token"] = session["csrf"]
        conn.request(
            "POST" if data is not None else "GET",
            path,
            json.dumps(data) if data is not None else None,
            headers,
        )
        response = conn.getresponse()
        raw = response.read()
        result = (
            json.loads(raw)
            if response.getheader("Content-Type", "").startswith("application/json")
            else raw
        )
        cookie = response.getheader("Set-Cookie", "").split(";")[0]
        status = response.status
        conn.close()
        return status, result, cookie

    def register(self, label):
        email = label + "@camporeal.edu.br"
        with app.database() as db:
            app.authorize_student(db, email)
        status, result, cookie = self.request(
            "/api/register", {"email": email, "password": "SenhaTeste123!"}
        )
        self.assertEqual(status, 201)
        self.assertEqual(cookie, "")
        self.assertIn("recovery_code", result)
        return email, result["recovery_code"]

    def login(self, email, password="SenhaTeste123!"):
        status, _, cookie = self.request(
            "/api/login", {"email": email, "password": password}
        )
        self.assertEqual(status, 200)
        status, profile, _ = self.request(
            "/api/me", session={"cookie": cookie, "csrf": ""}
        )
        self.assertEqual(status, 200)
        self.assertEqual(profile["email"], email)
        return {**profile, "cookie": cookie}

    def ticket(self, account):
        return {
            "subject": "Melhorar a iluminação",
            "body": "A iluminação do estacionamento precisa de manutenção.",
            "kind": "Reclamação",
            "sector": "Infraestrutura",
            "anonymous": True,
            "confirmed": True,
            "submission_id": secrets.token_hex(16),
        }

    def test_01_emails_and_codes_are_not_plaintext(self):
        email, code = self.register("privacidade")
        session = self.login(email)
        self.assertTrue(session["has_recovery_code"])
        status, _, _ = self.request("/api/tickets", self.ticket(session), session)
        self.assertEqual(status, 201)
        with app.database() as db:
            row = db.execute(
                "SELECT * FROM accounts WHERE email=?", (app.account_id(email),)
            ).fetchone()
            self.assertTrue(row["email"].startswith("id:"))
            self.assertNotIn(
                email,
                db.execute(
                    "SELECT email_cipher FROM identities WHERE id=?", (row["email"],)
                ).fetchone()[0],
            )
            self.assertEqual(app.email_for(row["email"], db), email)
            dump = "\n".join(db.iterdump())
        self.assertNotIn(email, dump)
        self.assertNotIn(code, dump)
        self.assertNotIn(email.encode(), app.DB.read_bytes())
        self.assertNotIn(code.encode(), app.DB.read_bytes())
        self.assertEqual(self.request("/segredos/email.key")[0], 404)
        self.assertEqual(self.request("/data/ouvidoria.sqlite3")[0], 404)

    def test_02_recovery_is_single_use_and_revokes_sessions(self):
        email, code = self.register("recuperacao")
        session = self.login(email)
        status, _, _ = self.request(
            "/api/recover",
            {"email": email, "password": "NovaSenha123!", "recovery_code": "INCORRETO"},
        )
        self.assertEqual(status, 400)
        status, result, cookie = self.request(
            "/api/recover",
            {"email": email, "password": "NovaSenha123!", "recovery_code": code},
        )
        self.assertEqual(status, 200)
        self.assertNotEqual(result["recovery_code"], code)
        self.assertNotIn("csrf", result)
        self.assertEqual(cookie, "cr_session=")
        self.assertEqual(self.request("/api/me", session=session)[0], 401)
        self.assertEqual(
            self.request("/api/login", {"email": email, "password": "SenhaTeste123!"})[
                0
            ],
            401,
        )
        self.assertEqual(
            self.request(
                "/api/recover",
                {"email": email, "password": "OutraSenha123!", "recovery_code": code},
            )[0],
            400,
        )
        self.login(email, "NovaSenha123!")
        self.assertEqual(
            self.request(
                "/api/recover",
                {
                    "email": email,
                    "password": "OutraSenha123!",
                    "recovery_code": result["recovery_code"],
                },
            )[0],
            200,
        )

    def test_03_rotate_requires_password_and_csrf(self):
        email, old_code = self.register("rotacao")
        session = self.login(email)
        self.assertEqual(
            self.request(
                "/api/recovery-code", {"current_password": "Errada123!"}, session
            )[0],
            400,
        )
        self.assertEqual(
            self.request(
                "/api/recovery-code",
                {"current_password": "SenhaTeste123!"},
                session,
                csrf=False,
            )[0],
            403,
        )
        status, result, _ = self.request(
            "/api/recovery-code", {"current_password": "SenhaTeste123!"}, session
        )
        self.assertEqual(status, 200)
        self.assertNotEqual(result["recovery_code"], old_code)
        self.assertEqual(
            self.request(
                "/api/recover",
                {
                    "email": email,
                    "password": "OutraSenha123!",
                    "recovery_code": old_code,
                },
            )[0],
            400,
        )

    def test_04_reason_is_required_and_visible_only_to_owner_and_director(self):
        email, _ = self.register("autoria")
        owner = self.login(email)
        supervisor = self.login("equipe@camporeal.edu.br")
        director = self.login("direcao@camporeal.edu.br")
        ticket = self.request("/api/tickets", self.ticket(owner), owner)[1]["id"]
        reason = "Consulta necessária para realizar o encaminhamento formal solicitado."
        self.assertEqual(
            self.request("/api/identity", {"id": ticket, "reason": reason}, supervisor)[
                0
            ],
            403,
        )
        self.assertEqual(
            self.request("/api/identity", {"id": ticket}, director)[0], 400
        )
        self.assertEqual(
            self.request("/api/identity", {"id": ticket, "reason": "curta"}, director)[
                0
            ],
            400,
        )
        self.assertEqual(
            self.request("/api/identity", {"id": ticket, "reason": reason}, director)[
                1
            ]["email"],
            email,
        )
        row = next(
            t
            for t in self.request("/api/tickets", session=owner)[1]
            if t["id"] == ticket
        )
        self.assertEqual(row["anonymous"], 1)
        self.assertEqual(row["identity_accesses"][0]["reason"], reason)
        self.assertGreater(row["identity_accesses"][0]["created"], 0)
        row = next(
            t
            for t in self.request("/api/tickets", session=supervisor)[1]
            if t["id"] == ticket
        )
        self.assertIsNone(row["identity"])
        self.assertEqual(row["identity_accesses"], [])
        self.assertNotIn(email, json.dumps(row))

    def test_05_confirmation_and_idempotency(self):
        email, _ = self.register("confirmacao")
        owner = self.login(email)
        payload = self.ticket(owner)
        self.assertEqual(
            self.request("/api/tickets", {**payload, "confirmed": False}, owner)[0], 400
        )
        status, created, _ = self.request("/api/tickets", payload, owner)
        self.assertEqual(status, 201)
        status, repeated, _ = self.request("/api/tickets", payload, owner)
        self.assertEqual(status, 200)
        self.assertEqual(created["id"], repeated["id"])
        self.assertEqual(
            self.request(
                "/api/tickets", {**payload, "subject": "Outro assunto"}, owner
            )[0],
            409,
        )
        with app.database() as db:
            self.assertEqual(
                db.execute(
                    "SELECT COUNT(*) FROM tickets WHERE email=? AND submission_id=?",
                    (app.account_id(email), payload["submission_id"]),
                ).fetchone()[0],
                1,
            )

    def test_06_missing_or_wrong_key_fails_closed(self):
        root = Path(self.temp.name)
        missing = root / "outra-chave.key"
        with patch.object(app, "KEY_PATH", missing):
            with self.assertRaises(RuntimeError):
                app.initialize()
            self.assertFalse(missing.exists())
        missing.write_bytes(Fernet.generate_key())
        with patch.object(app, "KEY_PATH", missing):
            with self.assertRaises(RuntimeError):
                app.initialize()
        app.initialize()

    def test_07_migrates_plaintext_without_losing_credentials_or_tickets(self):
        root = Path(self.temp.name) / "legado"
        root.mkdir()
        legacy = root / "antigo.sqlite3"
        email = "pessoa-legada@camporeal.edu.br"
        salt = secrets.token_hex(16)
        hashed = app.password_hash("SenhaLegada123!", salt)
        with sqlite3.connect(legacy) as db:
            db.executescript(
                """CREATE TABLE accounts(email TEXT PRIMARY KEY,salt TEXT NOT NULL,hash TEXT NOT NULL,role TEXT NOT NULL,created REAL NOT NULL);
            CREATE TABLE tickets(id TEXT PRIMARY KEY,email TEXT NOT NULL,anonymous INTEGER NOT NULL,kind TEXT NOT NULL,subject TEXT NOT NULL,sector TEXT NOT NULL,body TEXT NOT NULL,status TEXT NOT NULL,created REAL NOT NULL);
            CREATE TABLE audit(id INTEGER PRIMARY KEY,actor TEXT NOT NULL,action TEXT NOT NULL,ticket TEXT NOT NULL,created REAL NOT NULL);
            CREATE TABLE sessions(hash TEXT PRIMARY KEY,email TEXT NOT NULL,expires REAL NOT NULL,csrf TEXT NOT NULL);
            CREATE TABLE limits(key TEXT PRIMARY KEY,hits INTEGER NOT NULL,reset REAL NOT NULL);"""
            )
            db.execute(
                "INSERT INTO accounts VALUES (?,?,?,?,?)",
                (email, salt, hashed, "aluno", 1),
            )
            db.execute(
                "INSERT INTO tickets VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    "CR-LEGADO",
                    email,
                    1,
                    "Crítica",
                    "Relato antigo",
                    "Geral",
                    "Conteúdo anterior preservado.",
                    "Recebida",
                    1,
                ),
            )
            db.execute(
                "INSERT INTO audit VALUES (1,?,?,?,1)",
                (email, "Consulta de autoria restrita", "CR-LEGADO"),
            )
            db.execute(
                "INSERT INTO sessions VALUES (?,?,?,?)",
                ("sessao", email, 9999999999, "csrf"),
            )
            db.execute(
                "INSERT INTO limits VALUES (?,1,9999999999)", ("auth-email:" + email,)
            )
        with patch.object(app, "DB", legacy), patch.object(
            app, "KEY_PATH", root / "segredos" / "email.key"
        ):
            app.initialize()
            with app.database() as db:
                row = db.execute("SELECT * FROM accounts").fetchone()
                self.assertEqual(row["hash"], hashed)
                self.assertEqual(app.email_for(row["email"], db), email)
                self.assertEqual(
                    db.execute("SELECT email FROM tickets").fetchone()[0], row["email"]
                )
                self.assertEqual(
                    db.execute("SELECT actor FROM audit").fetchone()[0], row["email"]
                )
                self.assertEqual(
                    db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0], 0
                )
                self.assertNotIn(email, "\n".join(db.iterdump()))
                self.assertEqual(
                    db.execute("PRAGMA integrity_check").fetchone()[0], "ok"
                )
            self.assertNotIn(email.encode(), legacy.read_bytes())
            app.initialize()

    def test_08_legacy_wal_does_not_keep_old_email(self):
        root = Path(self.temp.name) / "wal-legado"
        root.mkdir()
        legacy = root / "antigo.sqlite3"
        email = "wal-legado@camporeal.edu.br"
        connection = sqlite3.connect(legacy)
        try:
            self.assertEqual(
                connection.execute("PRAGMA journal_mode=WAL").fetchone()[0], "wal"
            )
            connection.execute(
                "CREATE TABLE accounts(email TEXT PRIMARY KEY,salt TEXT NOT NULL,hash TEXT NOT NULL,role TEXT NOT NULL,created REAL NOT NULL)"
            )
            salt = secrets.token_hex(16)
            connection.execute(
                "INSERT INTO accounts VALUES (?,?,?,?,?)",
                (email, salt, app.password_hash("SenhaLegada123!", salt), "aluno", 1),
            )
            connection.commit()
            with patch.object(app, "DB", legacy), patch.object(
                app, "KEY_PATH", root / "segredos" / "email.key"
            ):
                app.initialize()
                self.assertNotIn(email.encode(), legacy.read_bytes())
                wal = Path(str(legacy) + "-wal")
                if wal.exists():
                    self.assertNotIn(email.encode(), wal.read_bytes())
        finally:
            connection.close()

    def test_09_recovery_attempts_are_limited(self):
        email, code = self.register("limite-recuperacao")
        for _ in range(5):
            self.assertEqual(
                self.request(
                    "/api/recover",
                    {
                        "email": email,
                        "password": "NovaSenha123!",
                        "recovery_code": "ERRADO",
                    },
                )[0],
                400,
            )
        self.assertEqual(
            self.request(
                "/api/recover",
                {"email": email, "password": "NovaSenha123!", "recovery_code": code},
            )[0],
            429,
        )
        self.login(email)


if __name__ == "__main__":
    unittest.main()
