"""Verifica criação local de contas, proteção de senhas e migração sem SMTP."""

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ouvidoria as app


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.setting = patch.object(
            app, "DB", Path(self.temp.name) / "data" / "test.sqlite3"
        )
        self.setting.start()
        app.initialize()

    def tearDown(self):
        self.setting.stop()
        self.temp.cleanup()

    def test_only_one_director_and_distinct_salts(self):
        with app.database() as db:
            app.insert_account(
                db, "diretor@camporeal.edu.br", "SenhaForte123", "diretor"
            )
            app.insert_account(db, "aluno@camporeal.edu.br", "SenhaForte123", "aluno")
            rows = db.execute("SELECT salt,hash FROM accounts").fetchall()
            self.assertNotEqual(rows[0]["salt"], rows[1]["salt"])
            self.assertNotEqual(rows[0]["hash"], rows[1]["hash"])
        with self.assertRaises(sqlite3.IntegrityError), app.database() as db:
            app.insert_account(db, "outro@camporeal.edu.br", "SenhaForte123", "diretor")

    def test_local_menu_creates_and_resets_account(self):
        with patch(
            "builtins.input", side_effect=["1", "equipe@camporeal.edu.br", "2", "0"]
        ), patch(
            "getpass.getpass", side_effect=["SenhaAntiga123", "SenhaAntiga123"]
        ), patch(
            "builtins.print"
        ):
            app.manage_accounts()
        self.assertEqual(app.role("equipe@camporeal.edu.br"), "supervisor")
        with app.database() as db:
            db.execute(
                "INSERT INTO sessions VALUES (?,?,?,?)",
                ("hash-falso", "equipe@camporeal.edu.br", 9999999999, "csrf-falso"),
            )
        with patch(
            "builtins.input", side_effect=["2", "equipe@camporeal.edu.br", "0"]
        ), patch(
            "getpass.getpass", side_effect=["NovaSenha123", "NovaSenha123"]
        ), patch(
            "builtins.print"
        ):
            app.manage_accounts()
        with app.database() as db:
            row = db.execute("SELECT * FROM accounts").fetchone()
            self.assertEqual(
                row["hash"], app.password_hash("NovaSenha123", row["salt"])
            )
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0], 0
            )

    def test_migration_preserves_tickets_and_runs_once(self):
        with app.database() as db:
            db.execute("DELETE FROM auth_meta")
            db.execute("CREATE TABLE codes(email TEXT, hash TEXT)")
            db.execute(
                "INSERT INTO codes VALUES (?,?)", ("legado@camporeal.edu.br", "antigo")
            )
            db.execute(
                "INSERT INTO sessions VALUES (?,?,?,?)",
                ("antiga", "legado@camporeal.edu.br", 9999999999, "csrf"),
            )
            db.execute(
                "INSERT INTO tickets(id,email,anonymous,kind,subject,sector,body,status,created) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    "CR-LEGADO",
                    "legado@camporeal.edu.br",
                    1,
                    "Reclamação",
                    "Relato anterior",
                    "Geral",
                    "Histórico anterior preservado.",
                    "Recebida",
                    1,
                ),
            )
        app.initialize()
        with app.database() as db:
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM tickets").fetchone()[0], 1
            )
            self.assertEqual(db.execute("SELECT COUNT(*) FROM codes").fetchone()[0], 0)
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0], 0
            )
            app.insert_account(db, "legado@camporeal.edu.br", "SenhaForte123", "aluno")
            db.execute(
                "INSERT INTO sessions VALUES (?,?,?,?)",
                ("nova", "legado@camporeal.edu.br", 9999999999, "csrf"),
            )
        app.initialize()
        with app.database() as db:
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0], 1
            )

    def test_archive_migration_keeps_old_schema_data(self):
        legacy = Path(self.temp.name) / "old-data" / "legacy.sqlite3"
        legacy.parent.mkdir()
        with sqlite3.connect(legacy) as db:
            db.execute(
                "CREATE TABLE tickets(id TEXT PRIMARY KEY,email TEXT NOT NULL,anonymous INTEGER NOT NULL,kind TEXT NOT NULL,subject TEXT NOT NULL,sector TEXT NOT NULL,body TEXT NOT NULL,status TEXT NOT NULL,created REAL NOT NULL)"
            )
            db.execute(
                "INSERT INTO tickets VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    "CR-ANTIGO",
                    "antigo@camporeal.edu.br",
                    1,
                    "Reclamação",
                    "Relato anterior",
                    "Infraestrutura",
                    "Este relato já estava resolvido.",
                    "Resolvida",
                    1,
                ),
            )
        with patch.object(app, "DB", legacy):
            app.initialize()
            with app.database() as db:
                row = db.execute(
                    "SELECT * FROM tickets WHERE id=?", ("CR-ANTIGO",)
                ).fetchone()
                self.assertEqual(row["archived"], 1)
                self.assertEqual(row["email"], "antigo@camporeal.edu.br")
                self.assertEqual(row["body"], "Este relato já estava resolvido.")
                self.assertEqual(
                    db.execute("PRAGMA integrity_check").fetchone()[0], "ok"
                )
                db.execute(
                    "UPDATE tickets SET archived=0,status='Em análise' WHERE id='CR-ANTIGO'"
                )
            app.initialize()
            with app.database() as db:
                self.assertEqual(
                    db.execute(
                        "SELECT archived FROM tickets WHERE id='CR-ANTIGO'"
                    ).fetchone()[0],
                    0,
                )

    def test_backup_preserves_data_and_integrity(self):
        with app.database() as db:
            app.insert_account(db, "backup@camporeal.edu.br", "SenhaTeste123!", "aluno")
        backup = app.backup_database()
        self.assertTrue(backup.exists())
        self.assertEqual(backup.parent, app.DB.parent / "backups")
        with sqlite3.connect(backup) as db:
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(
                db.execute("SELECT email FROM accounts").fetchone()[0],
                "backup@camporeal.edu.br",
            )
        self.assertEqual(
            app.SCHEMA_SQL.strip(),
            (Path(app.__file__).parent / "banco.sql").read_text().strip(),
        )


if __name__ == "__main__":
    unittest.main()
