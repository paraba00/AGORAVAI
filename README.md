# Ouvidoria Campo Real — Python

Projeto em **Python 3.10 ou superior**, com banco SQLite e código comentado. O arquivo `ouvidoria.py` contém o servidor, os controles de acesso e os conteúdos das telas. Não precisa instalar bibliotecas adicionais.

O campo de e-mail inicia **vazio**, sem texto de exemplo. O acesso real continua restrito a e-mails `@camporeal.edu.br`, com confirmação por código enviado ao endereço informado.

## Como baixar pelo GitHub

- Para o projeto inteiro: clique no botão verde **Code** e em **Download ZIP**, depois extraia a pasta.
- Para apenas o programa: abra **ouvidoria.py**, clique em **Download raw file** na barra do arquivo e salve no computador.
- Se o navegador bloquear arquivos `.py`, baixe **ouvidoria-python.txt** e renomeie para **ouvidoria.py**. O conteúdo é idêntico.

## Ver a demonstração

Abra `DEMONSTRACAO.html` com dois cliques. Ou, no terminal da pasta onde salvou o programa, execute:

```sh
python ouvidoria.py --demo
```

No Windows, você também pode usar `py -3` no lugar de `python`.

O demonstrador tem perfis de aluno, supervisor e diretor, com relatos fictícios. Os dados ficam no navegador: **não use informações pessoais na demonstração**. Ela não substitui a autenticação e as permissões do servidor real.

## Executar o sistema real

1. Instale Python 3.10 ou superior.
2. Gere o modelo com `python ouvidoria.py --configurar`.
3. Copie `.env.example` para `.env`, na mesma pasta de `ouvidoria.py`.
4. Configure envio de e-mail e contas autorizadas no `.env`.
5. Execute `python ouvidoria.py`.
6. Abra **http://localhost:8000** no navegador. Use exatamente o endereço definido em `APP_URL`.

O banco será criado em `data/ouvidoria.sqlite3`. O servidor permanece em execução enquanto o terminal estiver aberto. Para parar, use `Ctrl+C`.

### Configurações para login real

| Parâmetro | Uso |
| --- | --- |
| `DIRECTOR_EMAIL` | Uma única conta institucional do diretor. |
| `SUPERVISOR_EMAILS` | Contas dos supervisores/administradores, separadas por vírgula. |
| `SMTP_HOST` | Servidor de envio fornecido pela TI da faculdade. |
| `SMTP_PORT` | Porta com STARTTLS, normalmente 587. |
| `SMTP_FROM` | Endereço remetente autorizado. |
| `SMTP_USER` e `SMTP_PASSWORD` | Credenciais de envio, quando exigidas pelo SMTP. |
| `APP_URL` | Endereço exato usado no navegador, sem barra ao final. |

Guarde as credenciais apenas no `.env`, excluído pelo `.gitignore`. Não envie esse arquivo nem o banco ao GitHub. O envio usa STARTTLS obrigatório. Provedores que exigem OAuth para SMTP precisam de integração própria ou relay autorizado pela TI.

O código de acesso vence em dez minutos, é de uso único e bloqueia após cinco erros. A sessão dura oito horas. Sem SMTP configurado, não há desvio de login nem código mestre. Foi usada a alternativa de verificação por e-mail institucional; login com Google não foi implementado.

## Perfis e atendimento

- **Aluno:** registra reclamações, críticas, sugestões, elogios e solicitações; consulta somente os próprios protocolos; lê respostas; complementa relatos; confirma solução ou pede nova análise.
- **Supervisor/administrador:** consulta a fila e responde. Não recebe a autoria de relatos anônimos.
- **Diretor:** atende como a equipe e pode consultar explicitamente a autoria anônima. Cada consulta fica na tabela `audit` do servidor.

A manifestação começa como **Recebida**, passa para **Em análise** e fica **Respondida** quando a equipe envia uma mensagem. O aluno marca **Resolvida** ou pede nova análise. O histórico permanece disponível. Não há notificações automáticas de novas respostas por e-mail; o aluno acompanha pelo painel.

**Anonimato significa identidade oculta para a equipe, com consulta exclusiva do diretor pela aplicação.** O login é obrigatório. O formulário explica isso antes do envio. Se o aluno escrever o nome no relato, o conteúdo continuará visível. Pessoas com acesso administrativo ao servidor ou ao arquivo do banco também podem acessar os dados; restrinja essas permissões na infraestrutura.

Os perfis são definidos no servidor. O aluno não escolhe tornar-se supervisor ou diretor. Mudanças de configuração exigem reiniciar o programa.

## Telas e marcas

HTML, CSS e JavaScript são os conteúdos que o navegador recebe para desenhar e operar as telas. Estão embutidos de forma legível no arquivo Python, no dicionário `ASSETS`. O servidor, a autenticação, a autorização e o banco são implementados em Python.

As cores são azul e branco, com amarelo nos detalhes. As marcas incluídas são **reproduções vetoriais de referência baseadas nas imagens fornecidas**, não os arquivos originais. Antes da publicação oficial, substitua os conteúdos `assets/logo-azul.svg` e `assets/logo-branca.svg` no dicionário `ASSETS`. O demonstrador tem cópias embutidas que precisam ser atualizadas separadamente.

## Instalação na faculdade

A TI precisa hospedar o programa em um servidor persistente, configurar SMTP e colocar um proxy HTTPS à frente dele. O servidor HTTP da biblioteca padrão foi escolhido pela simplicidade e não deve ser exposto diretamente à internet. Mantenha `HOST=127.0.0.1` quando o proxy estiver no mesmo computador e ajuste `APP_URL` ao endereço institucional.

O programa considera o IP da conexão direta nos limites de acesso e não confia em `X-Forwarded-For`. Ajuste essa política para proxy ou redes compartilhadas. Defina política de privacidade, retenção e backups privados antes de coletar relatos reais. Com o serviço parado, copie o arquivo SQLite para realizar um backup simples.

## Testes

```sh
python -m unittest discover -s tests -v
```

Os testes usam banco temporário e substituem somente o envio SMTP. Verificam domínio exato, autenticação, tentativas e validade dos códigos, uso único, isolamento entre alunos, proteção da autoria anônima, acesso e auditoria do diretor, respostas, solução/reabertura, origem HTTP, CSRF, proteção dos arquivos privados e logout.

O arquivo único também passou pela verificação de entrega dos conteúdos embutidos. O envio SMTP real depende das configurações da faculdade. As telas ainda precisam de conferência visual em computador e celular antes da publicação.
