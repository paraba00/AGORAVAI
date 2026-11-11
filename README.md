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
4. Clique em **Criar minha conta**. O cadastro será confirmado, os campos serão limpos e você deverá digitar novamente e-mail e senha para entrar.
5. Nas próximas visitas, use apenas e-mail e senha e clique em **Entrar**.

O campo de e-mail começa vazio, sem texto de exemplo. O cadastro público é sempre de **aluno**; não existe escolha de perfil administrativo no site.

**O domínio institucional é conferido, mas o sistema não comprova que a pessoa é dona do e-mail.** Esse é o limite da opção sem verificação por mensagem. Não use a informação como identidade institucional verificada.

## Acessar no PC e no celular

As mudanças feitas somente no seu computador não aparecem no GitHub. Esta versão mantém o `.env` local e acrescenta um modo próprio para testar na rede:

```sh
python ouvidoria.py --rede-local
```

O programa escuta a porta 8000 nas interfaces do computador e mostra sugestões de endereço. No celular, abra `http://IP_DO_COMPUTADOR:8000`. No PC, você pode usar esse mesmo endereço ou `http://localhost:8000`. As sessões são separadas por endereço, mas as contas e os relatos ficam no mesmo banco.

Use o IPv4 da conexão Wi-Fi ou Ethernet mostrado por `ipconfig`. PC e celular precisam estar na mesma rede, sem isolamento entre dispositivos. Permita Python no firewall somente na rede privada; não é necessário desativar o firewall. Não use `0.0.0.0` ou `localhost` como endereço no celular. Mantenha o terminal e o computador ligados.

A validação de origem continua ativa. Para endereços locais literais, o endereço de origem precisa corresponder ao Host da requisição e à porta real do servidor. Domínios externos só são aceitos quando configurados em `APP_URL` ou `ALLOWED_ORIGINS`; não há liberação por curinga. O token CSRF e as permissões continuam obrigatórios nas operações autenticadas.

Esse modo é para testes na rede local, não publicação na internet. Em hospedagem, use proxy HTTPS e configure o endereço definitivo.

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

As situações são **Recebida**, **Em análise**, **Respondida** e **Resolvida**. O aluno pode confirmar a solução, e a equipe também pode concluir pelo botão **Resolver e arquivar**. O aluno mantém a opção de pedir nova análise. Respostas e mudanças de situação ficam no histórico. O aluno acompanha pelo painel, sem notificações automáticas por e-mail.

**Anonimato significa identidade oculta para o atendimento, com consulta pelo diretor na aplicação.** O cadastro e o login continuam obrigatórios. Se a pessoa escrever nome ou e-mail no relato, esse texto ficará visível. Quem administra o computador ou o banco também pode acessar os arquivos; restrinja o acesso à infraestrutura.

## Filtro por área e manifestações arquivadas

Supervisor e diretor têm um seletor **Todas as áreas**, no qual podem escolher Infraestrutura, Financeiro, Secretaria e as demais áreas do formulário. O filtro combina com a busca por assunto/protocolo e com a situação, tanto na lista principal quanto na aba **Arquivadas**. Trocar de aba mantém os filtros escolhidos. É um filtro de consulta da fila autorizada, não uma restrição de acesso por departamento.

Na aba **Todas as manifestações**, a equipe vê os protocolos que ainda não foram arquivados. Para concluir um atendimento, abra o protocolo e clique em **Resolver e arquivar**. Essa ação muda a situação para **Resolvida**, tira o registro da lista principal e o coloca em **Arquivadas**. A confirmação de solução pelo aluno também arquiva o protocolo para a equipe.

Na aba **Arquivadas**, supervisor e diretor podem consultar o histórico e usar **Desarquivar e retomar atendimento**. A situação volta para **Em análise** e o registro reaparece na lista principal. A equipe precisa retomar o atendimento antes de enviar outra resposta pela interface. O aluno continua vendo os próprios protocolos, inclusive os arquivados; se pedir nova análise ou escrever outra mensagem, o protocolo volta ao atendimento automaticamente.

Arquivar não exclui dados e não altera a proteção da autoria anônima. A autoria permanece indisponível para o supervisor; o diretor precisa usar a consulta restrita. Ações de resolver/arquivar e desarquivar pelo atendimento ficam no histórico e na auditoria, com conta responsável e data.

A tabela `tickets` recebeu o campo `archived`, inteiro restrito a 0 ou 1. A migração acrescenta esse campo aos bancos existentes sem apagar relatos ou respostas, e coloca os protocolos anteriormente resolvidos no arquivo. A situação e a marca de arquivamento são atualizadas na mesma transação. Faça backup com o serviço parado antes de substituir o programa, mantenha a pasta `data` e reinicie. Não é necessário cadastrar novamente as contas da versão que já usava senha.

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

## Leitura do código e do banco

O arquivo `ouvidoria.py` foi organizado com o servidor, as funções do banco e os comandos no início. O esquema SQL e os conteúdos HTML, CSS e JavaScript ficam ao final, sem repetir as mesmas telas para a demonstração. Comentários explicam decisões e permissões; a formatação usa blocos separados e uma instrução por linha quando possível. Não é necessário instalar formatadores para executar o programa.

- [BANCO_DE_DADOS.md](BANCO_DE_DADOS.md): tabelas, campos, relações, integridade, dados sensíveis e recuperação.
- [banco.sql](banco.sql): o mesmo esquema usado pelo programa, com as tabelas e colunas em linhas separadas.

Para ver caminho, integridade e contagens sem imprimir dados pessoais:

```sh
python ouvidoria.py --banco
```

Para criar uma cópia consistente com a API do SQLite:

```sh
python ouvidoria.py --backup
```

Os backups ficam em `data/backups`; não são criptografados nem enviados para outro local automaticamente. Veja o guia do banco para proteção, retenção e restauração.

## Testes

```sh
python -m unittest discover -s tests -v
```

Os testes usam banco temporário e verificam cadastro/login sem SMTP, domínio institucional, senha incorreta, bloqueio de tentativas, hashes, perfis, diretor único, recuperação local, migração, isolamento dos protocolos, autoria restrita, auditoria, respostas, solução/reabertura, CSRF, logout, migração de arquivamento, conclusão pela equipe, histórico arquivado e retomada pelo aluno. Os filtros de área, aba, busca e situação também foram verificados em conjunto. Há testes adicionais para cadastro sem sessão automática, origem de rede local e integridade dos backups. As telas precisam de conferência visual em computador e celular antes da publicação.
