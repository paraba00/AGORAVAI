"""Verificações reais de autenticação, isolamento e fluxo de atendimento."""
import http.client  # Faz requisições HTTP ao servidor de teste.
import json  # Codifica os dados enviados e recebidos.
import sys  # Permite importar o servidor a partir da pasta principal.
import tempfile  # Cria um banco isolado, sem dados reais.
import threading  # Executa o servidor durante os testes.
import unittest  # Usa os testes disponíveis no próprio Python.
from pathlib import Path  # Monta os caminhos do projeto.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # Localiza o módulo do servidor.
import ouvidoria as server  # Importa o programa Python em arquivo único.


class SecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()  # Isola os arquivos gerados pelos testes.
        server.DB = Path(cls.temp.name) / 'data' / 'test.sqlite3'  # Define um banco temporário.
        server.DIRECTOR = 'diretor@camporeal.edu.br'  # Define o único diretor do teste.
        server.SUPERVISORS = {'supervisor@camporeal.edu.br'}  # Define a equipe autorizada.
        server.initialize()  # Cria as tabelas e migra a autenticação antiga.
        with server.database() as db:
            server.insert_account(db, 'diretor@camporeal.edu.br', 'SenhaTeste123!', 'diretor')  # Cria a direção pelo mecanismo local.
            server.insert_account(db, 'supervisor@camporeal.edu.br', 'SenhaTeste123!', 'supervisor')  # Cria a equipe sem cadastro público privilegiado.
        cls.http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)  # Usa uma porta livre.
        cls.port = cls.http.server_port  # Guarda a porta escolhida.
        server.APP_URL = f'http://localhost:{cls.port}'  # Define a origem permitida para as chamadas.
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)  # Prepara o servidor em segundo plano.
        cls.thread.start()  # Inicia o atendimento aos testes.

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown(); cls.http.server_close(); cls.thread.join()  # Finaliza o servidor de teste.
        cls.temp.cleanup()  # Remove o banco temporário.

    def request(self, path, data=None, session=None, origin=None, csrf=True):
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)  # Conecta ao servidor local.
        headers = {'Content-Type': 'application/json', 'Origin': origin or server.APP_URL}  # Simula a origem do navegador.
        if session:
            headers['Cookie'] = session['cookie']  # Envia o cookie da conta de teste.
            if csrf: headers['X-CSRF-Token'] = session['csrf']  # Envia ou omite intencionalmente a proteção CSRF.
        connection.request('POST' if data is not None else 'GET', path, json.dumps(data) if data is not None else None, headers)  # Executa a chamada.
        response = connection.getresponse()  # Obtém o resultado HTTP.
        body = response.read()  # Consome a resposta antes de fechar a conexão.
        result = json.loads(body) if response.getheader('Content-Type', '').startswith('application/json') else body.decode()  # Suporta API e arquivos.
        cookie = response.getheader('Set-Cookie', '').split(';')[0]  # Captura o cookie de autenticação.
        status = response.status  # Guarda o status para as verificações.
        connection.close()  # Fecha a conexão do teste.
        return status, result, cookie  # Retorna as informações para as asserções.

    def login(self, email):
        with server.database() as db:
            exists = db.execute('SELECT 1 FROM accounts WHERE email=?', (email,)).fetchone()  # Decide entre cadastro público e acesso.
        path = '/api/login' if exists else '/api/register'  # O aluno entra diretamente depois de criar a conta.
        status, _, cookie = self.request(path, {'email': email, 'password': 'SenhaTeste123!'})
        self.assertIn(status, (200, 201))  # Exige uma sessão criada após verificação da senha.
        status, profile, _ = self.request('/api/me', session={'cookie': cookie, 'csrf': ''})
        self.assertEqual(status, 200)  # A consulta confirma o perfil atribuído pelo servidor.
        return {**profile, 'cookie': cookie}

    def test_01_authentication_and_domain(self):
        self.assertEqual(self.request('/api/tickets')[0], 401)  # Visitantes continuam sem acesso.
        for email in ['pessoa@gmail.com', 'a@camporeal.edu.br.evil.com', 'a@sub.camporeal.edu.br']:
            self.assertEqual(self.request('/api/register', {'email': email, 'password': 'SenhaTeste123!'})[0], 400)
        self.assertEqual(self.request('/api/register', {'email': 'novo@camporeal.edu.br', 'password': 'curta'})[0], 400)  # Rejeita senhas insuficientes.
        self.assertEqual(self.request('/api/login', {'email': 'diretor@camporeal.edu.br', 'password': 'Incorreta123'})[0], 401)  # Conhecer o e-mail do diretor não basta.
        status, _, cookie = self.request('/api/register', {'email': 'novo@camporeal.edu.br', 'password': 'SenhaTeste123!', 'role': 'diretor'})  # Tenta escolher um perfil privilegiado.
        self.assertEqual(status, 201)
        self.assertEqual(self.request('/api/me', session={'cookie': cookie, 'csrf': ''})[1]['role'], 'aluno')  # O servidor ignora o perfil enviado.
        self.assertEqual(self.request('/api/register', {'email': 'diretor@camporeal.edu.br', 'password': 'SenhaTeste123!'})[0], 409)  # Não sobrescreve equipe existente.
        for _ in range(15):
            result = self.request('/api/login', {'email': 'limite@camporeal.edu.br', 'password': 'Incorreta123'})
        self.assertEqual(self.request('/api/login', {'email': 'limite@camporeal.edu.br', 'password': 'Incorreta123'})[0], 429)  # Limita adivinhação de senha.

    def test_02_roles_privacy_and_workflow(self):
        alice = self.login('alice@camporeal.edu.br')  # Autentica a autora do protocolo.
        bob = self.login('bob@camporeal.edu.br')  # Autentica outro aluno.
        supervisor = self.login('supervisor@camporeal.edu.br')  # Autentica um atendente.
        director = self.login('diretor@camporeal.edu.br')  # Autentica o diretor autorizado.
        payload = {'kind': 'Reclamação', 'sector': 'Geral', 'subject': 'Relato de teste', 'body': 'Relato suficientemente detalhado para validar o atendimento.', 'anonymous': True}  # Cria um relato anônimo.
        status, result, _ = self.request('/api/tickets', payload, alice)  # Registra a manifestação.
        self.assertEqual(status, 201); ticket_id = result['id']  # Guarda o protocolo gerado.
        self.assertEqual(self.request('/api/tickets', session=bob)[1], [])  # Outro aluno não recebe o registro.
        self.assertEqual(self.request('/api/reply', {'id': ticket_id, 'body': 'Mensagem de invasão'}, bob)[0], 404)  # Impede acesso por protocolo adivinhado.
        for account in (supervisor, director):
            status, items, _ = self.request('/api/tickets', session=account)  # Obtém a fila institucional.
            self.assertEqual(status, 200); self.assertIsNone(items[0]['identity'])  # A lista não inclui identidade anônima.
            self.assertNotIn(alice['email'], json.dumps(items))  # Não vaza a identidade em campos ocultos da resposta.
        self.assertEqual(self.request('/api/identity', {'id': ticket_id}, supervisor)[0], 403)  # Supervisor não pode consultar a autoria.
        self.assertEqual(self.request('/api/identity', {'id': ticket_id}, alice)[0], 403)  # A rota restrita não é liberada ao aluno.
        self.assertEqual(self.request('/api/identity', {'id': ticket_id}, director)[1]['email'], alice['email'])  # Somente o diretor recebe a autoria.
        with server.database() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM audit WHERE ticket=?', (ticket_id,)).fetchone()[0], 1)  # Confirma o registro de auditoria.
        self.assertEqual(self.request('/api/reply', {'id': ticket_id, 'body': 'A equipe está verificando o problema.'}, supervisor)[0], 200)  # Permite resposta institucional.
        self.assertEqual(self.request('/api/tickets', session=alice)[1][0]['status'], 'Respondida')  # Aluno vê a nova resposta.
        self.assertEqual(self.request('/api/status', {'id': ticket_id, 'status': 'Resolvida'}, supervisor)[0], 400)  # Equipe não confirma solução pelo aluno.
        self.assertEqual(self.request('/api/status', {'id': ticket_id, 'status': 'Resolvida'}, alice)[0], 200)  # Aluno confirma que foi solucionado.
        self.assertEqual(self.request('/api/status', {'id': ticket_id, 'status': 'Em análise'}, alice)[0], 200)  # Aluno consegue reabrir a análise.
        self.assertEqual(self.request('/api/reply', {'id': ticket_id, 'body': 'Ainda preciso de ajuda.'}, alice)[0], 200)  # Permite manifestação posterior à resposta.
        self.assertEqual(self.request('/api/tickets', payload, supervisor)[0], 403)  # Perfil administrativo não cria registros como aluno.
        self.assertEqual(self.request('/api/status', {'id': ticket_id, 'status': 'Resolvida'}, alice, csrf=False)[0], 403)  # Protege alterações sem CSRF.
        self.assertEqual(self.request('/api/status', {'id': ticket_id, 'status': 'Resolvida'}, alice, origin='https://outro.site')[0], 403)  # Protege contra chamadas de outra origem.
        self.assertEqual(self.request('/data/ouvidoria.sqlite3')[0], 404)  # Banco não é exposto pelo servidor web.
        self.assertEqual(self.request('/server.py')[0], 404)  # Código e configurações não são servidos como arquivos públicos.
        self.assertEqual(self.request('/api/logout', {}, alice)[0], 200)  # Encerra a sessão.
        self.assertEqual(self.request('/api/me', session=alice)[0], 401)  # O cookie antigo deixa de funcionar.

    def test_03_password_storage_and_session_expiration(self):
        account = self.login('expirado@camporeal.edu.br')  # Cria uma conta nova.
        with server.database() as db:
            saved = db.execute('SELECT * FROM accounts WHERE email=?', (account['email'],)).fetchone()
            self.assertNotEqual(saved['hash'], 'SenhaTeste123!')  # Nunca persiste a senha em texto simples.
            self.assertEqual(saved['hash'], server.password_hash('SenhaTeste123!', saved['salt']))  # Confere derivação do hash com sal.
            db.execute('UPDATE sessions SET expires=0 WHERE email=?', (account['email'],))  # Simula sessão vencida.
        self.assertEqual(self.request('/api/me', session=account)[0], 401)
        self.assertEqual(self.request('/api/verify', {'email': account['email'], 'code': '123456'})[0], 401)  # A rota de código antigo não autentica.

    def test_04_legacy_email_cannot_be_claimed_publicly(self):
        email = 'historico@camporeal.edu.br'  # Representa quem usou o antigo login por código.
        with server.database() as db:
            db.execute('INSERT INTO tickets(id,email,anonymous,kind,subject,sector,body,status,created) VALUES (?,?,?,?,?,?,?,?,?)', ('CR-HISTORICO', email, 1, 'Crítica', 'Registro anterior', 'Geral', 'Este relato pertence a uma conta antiga.', 'Recebida', 1))
        self.assertEqual(self.request('/api/register', {'email': email, 'password': 'SenhaTeste123!'})[0], 409)  # Um visitante não pode reivindicar esse histórico.
        with server.database() as db:
            server.insert_account(db, email, 'SenhaTeste123!', 'aluno')  # O responsável provisiona a conta preservada pelo mecanismo local.
        account = self.login(email)
        rows = self.request('/api/tickets', session=account)[1]
        self.assertEqual(rows[0]['id'], 'CR-HISTORICO')  # O histórico é recuperado sem copiar ou apagar registros.

    def test_05_staff_archive_and_student_reopening(self):
        alice = self.login('alice@camporeal.edu.br')  # Usa uma conta que já tem histórico.
        supervisor = self.login('supervisor@camporeal.edu.br')
        director = self.login('diretor@camporeal.edu.br')
        payload = {'kind': 'Reclamação', 'sector': 'Infraestrutura', 'subject': 'Manutenção da iluminação', 'body': 'Precisamos de manutenção na iluminação do estacionamento.', 'anonymous': True}
        status, created, _ = self.request('/api/tickets', payload, alice)
        self.assertEqual(status, 201)
        ticket_id = created['id']
        self.assertEqual(self.request('/api/archive', {'id': ticket_id, 'archived': True}, alice)[0], 403)  # Aluno não aciona o arquivo administrativo.
        self.assertEqual(self.request('/api/archive', {'id': ticket_id, 'archived': 'true'}, supervisor)[0], 400)  # Não aceita texto no lugar de booleano.
        self.assertEqual(self.request('/api/archive', {'id': ticket_id, 'archived': True}, supervisor)[0], 200)  # Supervisor resolve e arquiva.
        for account in (alice, supervisor, director):
            record = next(t for t in self.request('/api/tickets', session=account)[1] if t['id'] == ticket_id)
            self.assertEqual(record['status'], 'Resolvida')
            self.assertEqual(record['archived'], 1)
            self.assertEqual(record['sector'], 'Infraestrutura')
            if account['role'] != 'aluno':
                self.assertIsNone(record['identity'])  # O arquivamento não revela a autoria anônima.
                self.assertNotIn(alice['email'], json.dumps(record))
        self.request('/api/archive', {'id': ticket_id, 'archived': True}, supervisor)  # Repete a mesma ação.
        with server.database() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM audit WHERE ticket=? AND action='Resolver e arquivar'", (ticket_id,)).fetchone()[0], 1)  # Não duplica o histórico.
        self.assertEqual(self.request('/api/archive', {'id': ticket_id, 'archived': False}, director)[0], 200)  # Diretor retoma o protocolo.
        record = next(t for t in self.request('/api/tickets', session=supervisor)[1] if t['id'] == ticket_id)
        self.assertEqual((record['status'], record['archived']), ('Em análise', 0))
        self.request('/api/archive', {'id': ticket_id, 'archived': True}, director)
        self.assertEqual(self.request('/api/reply', {'id': ticket_id, 'body': 'Ainda preciso de ajuda neste ponto.'}, alice)[0], 200)
        record = next(t for t in self.request('/api/tickets', session=supervisor)[1] if t['id'] == ticket_id)
        self.assertEqual((record['status'], record['archived']), ('Em análise', 0))  # Nova mensagem do aluno tira o protocolo do arquivo.
        self.assertGreaterEqual(len(record['messages']), 5)  # Preserva as ações e a conversa anteriores.
        self.request('/api/status', {'id': ticket_id, 'status': 'Resolvida'}, alice)
        record = next(t for t in self.request('/api/tickets', session=supervisor)[1] if t['id'] == ticket_id)
        self.assertEqual(record['archived'], 1)  # Confirmação de solução pelo aluno também arquiva.
        self.request('/api/status', {'id': ticket_id, 'status': 'Em análise'}, alice)
        record = next(t for t in self.request('/api/tickets', session=supervisor)[1] if t['id'] == ticket_id)
        self.assertEqual(record['archived'], 0)  # Pedido de nova análise devolve o protocolo à lista principal.


if __name__ == '__main__':
    unittest.main()  # Executa a suíte quando chamada diretamente.
