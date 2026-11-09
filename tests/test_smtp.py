"""Testa diagnóstico SMTP sem conectar à internet nem enviar mensagens."""
import os  # Permite isolar configurações sem ler credenciais reais.
import runpy  # Verifica o carregamento de um .env temporário.
import smtplib  # Fornece classes de falhas SMTP para simular recusas.
import sys  # Localiza o programa na pasta principal.
import tempfile  # Isola os arquivos de configuração de teste.
import unittest  # Executa os testes sem dependências adicionais.
from pathlib import Path  # Monta os caminhos temporários.
from unittest.mock import MagicMock, patch  # Substitui o provedor por conexões simuladas.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # Localiza o programa da ouvidoria.
import ouvidoria as app  # Importa a aplicação sem iniciar o servidor.


class SMTPTests(unittest.TestCase):
    def settings(self, **changes):
        values = {'SMTP_HOST': 'smtp.gmail.com', 'SMTP_PORT': '587', 'SMTP_FROM': 'exemplo@gmail.com', 'SMTP_USER': 'exemplo@gmail.com', 'SMTP_PASSWORD': 'aaaa bbbb cccc dddd'}  # Define somente credenciais fictícias.
        values.update(changes)  # Permite simular configurações diferentes.
        return patch.dict(os.environ, values, clear=True)  # Isola totalmente o ambiente durante cada teste.

    def test_missing_settings(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(app.SMTPConfigurationError) as error:
                app.smtp_settings()  # Exige os campos mínimos antes de conectar.
            self.assertIn('SMTP_HOST', str(error.exception))  # Explica qual parâmetro falta.

    def test_starttls_and_google_grouped_password(self):
        client = MagicMock()  # Simula um servidor sem rede.
        with self.settings(), patch.object(app.smtplib, 'SMTP', return_value=client):
            with app.smtp_connection() as connected:
                self.assertIs(connected, client)  # Entrega a conexão já autenticada.
            client.starttls.assert_called_once()  # Exige TLS antes da autenticação.
            client.login.assert_called_once_with('exemplo@gmail.com', 'aaaabbbbccccdddd')  # Aceita a senha copiada em grupos.
            client.send_message.assert_not_called()  # Abrir a conexão não envia e-mail.
            client.quit.assert_called_once()  # Encerra a conexão.

    def test_port_465_uses_implicit_tls(self):
        client = MagicMock()  # Simula um servidor TLS direto.
        with self.settings(SMTP_PORT='465'), patch.object(app.smtplib, 'SMTP_SSL', return_value=client) as factory:
            with app.smtp_connection():
                pass  # Apenas verifica conexão e autenticação.
            self.assertEqual(factory.call_args.args, ('smtp.gmail.com', 465))  # Usa a porta configurada.
            client.starttls.assert_not_called()  # A conexão já começa criptografada.

    def test_auth_failure_never_exposes_provider_details(self):
        private = b'password SUPERSECRETO rejected'  # Simula uma resposta inadequada do provedor.
        error = smtplib.SMTPAuthenticationError(535, private)  # Simula credenciais recusadas.
        message = app.smtp_error_message(error)  # Gera uma orientação segura.
        self.assertIn('senha de app', message)  # Orienta sobre o caso mais comum no Gmail.
        self.assertNotIn('SUPERSECRETO', message)  # Não repassa detalhes privados do SMTP.
        client = MagicMock()  # Simula o cliente para testar liberação de recursos.
        client.login.side_effect = error  # Recusa a autenticação.
        with self.settings(), patch.object(app.smtplib, 'SMTP', return_value=client):
            with self.assertRaises(smtplib.SMTPAuthenticationError):
                with app.smtp_connection():
                    self.fail('Não deve liberar uma conexão não autenticada.')
            client.quit.assert_called_once()  # Fecha o cliente mesmo quando o login falha.

    def test_bad_port_and_host(self):
        for changes in ({'SMTP_PORT': 'abc'}, {'SMTP_PORT': '70000'}, {'SMTP_HOST': 'https://smtp.gmail.com'}):
            with self.settings(**changes):
                with self.assertRaises(app.SMTPConfigurationError):
                    app.smtp_settings()  # Recusa configuração inválida antes de acessar a rede.

    def test_env_accepts_bom_and_quoted_values(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)  # Cria uma instalação temporária sem dados reais.
            script = root / 'ouvidoria.py'  # Copia apenas o programa Python.
            script.write_text(Path(app.__file__).read_text(), encoding='utf-8')  # Não depende dos demais arquivos do projeto.
            (root / '.env').write_text('SMTP_HOST="smtp.gmail.com"\nSMTP_PASSWORD=\'senha-ficticia\'\n', encoding='utf-8-sig')  # Simula um arquivo salvo pelo editor do Windows.
            with patch.dict(os.environ, {}, clear=True):
                runpy.run_path(str(script), run_name='teste_configuracao')  # Carrega o arquivo sem executar o servidor.
                self.assertEqual(os.environ['SMTP_HOST'], 'smtp.gmail.com')  # Remove BOM e aspas externas.
                self.assertEqual(os.environ['SMTP_PASSWORD'], 'senha-ficticia')  # Mantém o conteúdo da senha sem aspas artificiais.


if __name__ == '__main__':
    unittest.main()  # Permite executar este arquivo diretamente.
