"""Verifica criação local de contas, proteção de senhas e migração sem SMTP."""
import os  # Isola as configurações usadas nos testes.
import sqlite3  # Simula as tabelas de uma instalação anterior.
import sys  # Localiza o programa Python.
import tempfile  # Cria um banco descartável.
import unittest  # Executa os testes sem dependências.
from pathlib import Path  # Monta os caminhos temporários.
from unittest.mock import patch  # Simula a digitação no menu local.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # Localiza o arquivo principal.
import ouvidoria as app  # Importa sem iniciar o servidor.


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()  # Separa os dados de cada teste.
        self.setting = patch.object(app, 'DB', Path(self.temp.name) / 'data' / 'test.sqlite3')  # Nunca usa banco real.
        self.setting.start()  # Aplica o caminho temporário.
        app.initialize()  # Cria o esquema atual.

    def tearDown(self):
        self.setting.stop()  # Restaura a configuração anterior.
        self.temp.cleanup()  # Apaga apenas os dados do teste.

    def test_only_one_director_and_distinct_salts(self):
        with app.database() as db:
            app.insert_account(db, 'diretor@camporeal.edu.br', 'SenhaForte123', 'diretor')  # Cria o único diretor.
            app.insert_account(db, 'aluno@camporeal.edu.br', 'SenhaForte123', 'aluno')  # Mesma senha, mas outro sal.
            rows = db.execute('SELECT salt,hash FROM accounts').fetchall()
            self.assertNotEqual(rows[0]['salt'], rows[1]['salt'])  # Cada conta tem um sal exclusivo.
            self.assertNotEqual(rows[0]['hash'], rows[1]['hash'])  # A mesma senha produz hashes diferentes.
        with self.assertRaises(sqlite3.IntegrityError), app.database() as db:
            app.insert_account(db, 'outro@camporeal.edu.br', 'SenhaForte123', 'diretor')  # O banco bloqueia um segundo diretor.

    def test_local_menu_creates_and_resets_account(self):
        with patch('builtins.input', side_effect=['1', 'equipe@camporeal.edu.br', '2', '0']), patch('getpass.getpass', side_effect=['SenhaAntiga123', 'SenhaAntiga123']), patch('builtins.print'):
            app.manage_accounts()  # Cria uma conta de supervisor pelo menu local.
        self.assertEqual(app.role('equipe@camporeal.edu.br'), 'supervisor')
        with app.database() as db:
            db.execute('INSERT INTO sessions VALUES (?,?,?,?)', ('hash-falso', 'equipe@camporeal.edu.br', 9999999999, 'csrf-falso'))  # Simula uma sessão aberta.
        with patch('builtins.input', side_effect=['2', 'equipe@camporeal.edu.br', '0']), patch('getpass.getpass', side_effect=['NovaSenha123', 'NovaSenha123']), patch('builtins.print'):
            app.manage_accounts()  # Redefine sem precisar de e-mail.
        with app.database() as db:
            row = db.execute('SELECT * FROM accounts').fetchone()
            self.assertEqual(row['hash'], app.password_hash('NovaSenha123', row['salt']))  # A nova senha substitui a anterior.
            self.assertEqual(db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0], 0)  # Revoga acessos antigos.

    def test_migration_preserves_tickets_and_runs_once(self):
        with app.database() as db:
            db.execute('DELETE FROM auth_meta')  # Simula o estado anterior à migração.
            db.execute('CREATE TABLE codes(email TEXT, hash TEXT)')  # Simula códigos legados.
            db.execute('INSERT INTO codes VALUES (?,?)', ('legado@camporeal.edu.br', 'antigo'))
            db.execute('INSERT INTO sessions VALUES (?,?,?,?)', ('antiga', 'legado@camporeal.edu.br', 9999999999, 'csrf'))
            db.execute('INSERT INTO tickets VALUES (?,?,?,?,?,?,?,?,?)', ('CR-LEGADO', 'legado@camporeal.edu.br', 1, 'Reclamação', 'Relato anterior', 'Geral', 'Histórico anterior preservado.', 'Recebida', 1))
        app.initialize()  # Migra a instalação sem apagar manifestações.
        with app.database() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM tickets').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM codes').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0], 0)
            app.insert_account(db, 'legado@camporeal.edu.br', 'SenhaForte123', 'aluno')  # Provisiona a conta pelo mecanismo local.
            db.execute('INSERT INTO sessions VALUES (?,?,?,?)', ('nova', 'legado@camporeal.edu.br', 9999999999, 'csrf'))
        app.initialize()  # Reinícios seguintes preservam sessões válidas.
        with app.database() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0], 1)


if __name__ == '__main__':
    unittest.main()  # Executa diretamente, se necessário.
