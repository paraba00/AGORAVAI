# Ouvidoria Campo Real — login simples

Projeto em **Python 3.10 ou superior**, com código comentado e banco SQLite. Não precisa instalar bibliotecas, configurar Gmail, SMTP ou receber códigos por e-mail.

## Baixar e abrir

No GitHub, clique em **Code → Download ZIP** e extraia a pasta. Abra o terminal nessa pasta e execute:

```sh
python ouvidoria.py
```

No Windows, se necessário, use `py -3 ouvidoria.py`. Depois, abra **http://localhost:8000** no navegador. Para parar o programa, use **Ctrl+C**.

O arquivo `ouvidoria.py` já contém o servidor e os conteúdos das telas. A cópia `ouvidoria-python.txt` tem o mesmo conteúdo; pode ser renomeada para `.py` caso o download dessa extensão seja bloqueado.

## Alunos: criar conta e entrar

1. Na tela de acesso, clique em **Primeiro acesso? Criar conta de aluno**.
2. Digite um e-mail `@camporeal.edu.br`.
3. Escolha uma senha de **8 a 128 caracteres** e repita para confirmar.
4. Clique em **Criar minha conta**. O acesso acontece imediatamente.
5. Nas próximas visitas, use apenas e-mail e senha e clique em **Entrar**.

O campo de e-mail começa vazio, sem texto de exemplo. O cadastro público é sempre de **aluno**; não existe escolha de perfil administrativo no site.

**O domínio institucional é conferido, mas o sistema não comprova que a pessoa é dona do e-mail.** Esse é o limite da opção sem verificação por mensagem. Não use a informação como identidade institucional verificada.

## Criar supervisor e diretor

No computador em que o programa está instalado, pare o servidor com **Ctrl+C** e execute:

```sh
python ouvidoria.py --contas
```

O menu oferece:

- **1 — Criar conta:** informe e-mail institucional, escolha aluno, supervisor ou diretor e defina a senha duas vezes. A senha não aparece enquanto é digitada; isso é normal.
- **2 — Redefinir senha:** informe uma conta existente e uma nova senha. As sessões anteriores dessa conta serão encerradas.
- **3 — Listar contas:** mostra apenas os e-mails e os perfis, nunca senhas.
- **0 — Sair:** fecha o menu.

Depois, inicie novamente com `python ouvidoria.py`.

Crie as contas de equipe por esse menu, antes de tentar cadastrá-las no site. Existe somente **um diretor** no banco. O perfil é atribuído localmente; conhecer o e-mail da direção não permite receber privilégios por cadastro público. Não há senha padrão ou código mestre.

## Esqueci a senha

O aluno deve pedir ao responsável pela instalação para usar a opção **Redefinir senha** no menu `--contas`. Não há recuperação automática por e-mail e não é possível consultar a senha antiga, pois ela não é armazenada em texto simples.

## Atualizar uma instalação anterior

1. Pare o programa.
2. Faça uma cópia privada da pasta `data` com o serviço parado.
3. Substitua `ouvidoria.py` pela versão nova, **na mesma pasta**, mantendo `data`.
4. Execute `python ouvidoria.py --contas` e crie as contas necessárias, com os mesmos e-mails de quem já tem relatos.
5. Inicie o servidor novamente.

A primeira execução cria as tabelas de contas e encerra sessões/códigos antigos. **Os relatos, as respostas e a auditoria são preservados.** E-mails que já têm histórico da versão antiga não podem ser tomados pelo cadastro público: o responsável precisa criar a conta no menu local. A migração não repete o encerramento de sessões a cada reinício.

O `.env` antigo pode continuar na pasta, mas as opções SMTP não são usadas. `DIRECTOR_EMAIL` e `SUPERVISOR_EMAILS`, quando existentes, apenas reservam os antigos endereços contra cadastro público; não concedem perfis automaticamente. Crie as contas no menu local.

## Permissões e atendimento

- **Aluno:** cria reclamação, crítica, sugestão, elogio ou solicitação; consulta somente os próprios protocolos; lê respostas; envia complementos; confirma solução ou pede nova análise.
- **Supervisor:** atende e responde à fila, sem receber a autoria dos relatos anônimos.
- **Diretor:** atende como a equipe e pode consultar explicitamente a autoria anônima. Cada consulta fica registrada na tabela `audit`.

As situações são **Recebida**, **Em análise**, **Respondida** e **Resolvida**. O aluno confirma a solução; a equipe não encerra por ele. Respostas e mudanças de situação ficam no histórico. O aluno acompanha pelo painel, sem notificações automáticas por e-mail.

**Anonimato significa identidade oculta para o atendimento, com consulta pelo diretor na aplicação.** O cadastro e o login continuam obrigatórios. Se a pessoa escrever nome ou e-mail no relato, esse texto ficará visível. Quem administra o computador ou o banco também pode acessar os arquivos; restrinja o acesso à infraestrutura.

## Demonstração sem contas reais

Abra `DEMONSTRACAO.html` com dois cliques ou execute:

```sh
python ouvidoria.py --demo
```

Os botões de aluno, supervisor e diretor usam dados fictícios armazenados no navegador. Não coloque informações pessoais na demonstração. O demonstrador não representa a segurança da API real.

## Configuração opcional

O programa funciona localmente sem `.env`. Se precisar mudar endereço ou porta, gere o modelo com `python ouvidoria.py --configurar`, copie `.env.example` para `.env` e ajuste os valores. Não é necessário preencher parâmetros de e-mail.

O banco fica em `data/ouvidoria.sqlite3`. Não publique `.env` nem `data` no GitHub; ambos estão no `.gitignore`. Não mude `DATABASE_PATH` se quiser continuar usando o banco atual.

As senhas usam PBKDF2-HMAC-SHA256, com sal aleatório e 600 mil iterações. Os cookies de sessão são HttpOnly, SameSite e Secure quando o endereço usa HTTPS. Alterações exigem token CSRF e origem compatível com `APP_URL`. Há limites de tentativas por conta e IP. O menu de contas é local, não uma rota pública do site.

Para uso na faculdade, a TI precisa instalar o programa em servidor persistente e colocar um proxy reverso HTTPS à frente dele. O servidor HTTP da biblioteca padrão foi escolhido para simplificar a instalação e deve ficar atrás desse proxy. Ajuste limites por IP para redes compartilhadas e proxy, pois o programa considera a conexão direta e não confia em `X-Forwarded-For`. Defina privacidade, retenção e backups antes de coletar relatos reais.

## Telas e marcas

HTML, CSS e JavaScript são os conteúdos recebidos pelo navegador e estão embutidos no dicionário `ASSETS`, dentro do Python. O servidor, a autenticação, as permissões e o banco são implementados em Python.

As marcas são reproduções vetoriais de referência das imagens fornecidas, não os arquivos originais. Antes da publicação oficial, substitua os SVGs azul e branco em `ASSETS`. O demonstrador contém cópias próprias que também precisam ser atualizadas.

## Testes

```sh
python -m unittest discover -s tests -v
```

Os testes usam banco temporário e verificam cadastro/login sem SMTP, domínio institucional, senha incorreta, bloqueio de tentativas, hashes, perfis, diretor único, recuperação local, migração, isolamento dos protocolos, autoria restrita, auditoria, respostas, solução/reabertura, CSRF e logout. As telas precisam de conferência visual em computador e celular antes da publicação.
