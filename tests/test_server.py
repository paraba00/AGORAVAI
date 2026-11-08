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
        cls.codes = {}  # Captura códigos no lugar de enviar mensagens reais.
        server.deliver = lambda email, code: cls.codes.update({email: code})  # Substitui apenas a integração SMTP.
        server.initialize()  # Cria o banco com a mesma estrutura da aplicação.
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
        self.assertEqual(self.request('/api/login', {'email': email})[0], 200)  # Confirma o envio do código.
        status, _, cookie = self.request('/api/verify', {'email': email, 'code': self.codes[email]})  # Confirma o código capturado.
        self.assertEqual(status, 200)  # Exige autenticação bem-sucedida.
        status, profile, _ = self.request('/api/me', session={'cookie': cookie, 'csrf': ''})  # Consulta a sessão recém-criada.
        self.assertEqual(status, 200)  # Verifica que a sessão pode ser usada.
        return {**profile, 'cookie': cookie}  # Entrega a conta autenticada.

    def test_01_authentication_and_domain(self):
        self.assertEqual(self.request('/api/tickets')[0], 401)  # Visitantes não podem ler protocolos.
        for email in ['pessoa@gmail.com', 'a@camporeal.edu.br.evil.com', 'a@sub.camporeal.edu.br']:
            self.assertEqual(self.request('/api/login', {'email': email})[0], 400)  # Rejeita domínios externos ou parecidos.
        email = 'codigo@camporeal.edu.br'  # Define uma conta exclusiva para a verificação.
        self.request('/api/login', {'email': email})  # Gera um código real no fluxo da aplicação.
        wrong = '000000' if self.codes[email] != '000000' else '111111'  # Garante um código diferente do válido.
        for _ in range(5): self.assertEqual(self.request('/api/verify', {'email': email, 'code': wrong})[0], 400)  # Confere o bloqueio progressivo.
        self.assertEqual(self.request('/api/verify', {'email': email, 'code': self.codes[email]})[0], 400)  # Bloqueia até o código correto após cinco falhas.

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

    def test_03_expiration_and_single_use(self):
        account = self.login('unico@camporeal.edu.br')  # Autentica com um código novo.
        self.assertEqual(self.request('/api/verify', {'email': account['email'], 'code': self.codes[account['email']]})[0], 400)  # Não permite reutilizar o código.
        email = 'expirado@camporeal.edu.br'  # Define uma segunda conta.
        self.request('/api/login', {'email': email})  # Solicita um código.
        with server.database() as db: db.execute('UPDATE codes SET expires=0 WHERE email=?', (email,))  # Simula expiração.
        self.assertEqual(self.request('/api/verify', {'email': email, 'code': self.codes[email]})[0], 400)  # Rejeita código vencido.


if __name__ == '__main__':
    unittest.main()  # Executa a suíte quando chamada diretamente.
