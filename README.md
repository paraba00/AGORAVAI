# Ouvidoria Campo Real

Sistema em Python 3.10 ou superior, com SQLite e telas embutidas em `ouvidoria.py`. O código é organizado em funções, com comentários nas decisões de segurança e no esquema do banco.

## Instalar e iniciar

No GitHub, use **Code → Download ZIP**, extraia a pasta e abra o terminal nela:

```sh
python -m pip install -r requirements.txt
python ouvidoria.py
```

No Windows, você pode substituir `python` por `py -3`. Abra **http://localhost:8000**. Para encerrar, use **Ctrl+C**. A dependência `cryptography` é usada para criptografar os e-mails com Fernet; não há implementação caseira de criptografia.

Se baixar apenas `ouvidoria.py`, instale a dependência com `python -m pip install cryptography`. A cópia `ouvidoria-python.txt` contém o mesmo programa e pode ser renomeada para `.py`.

## Autorizar o e-mail antes do aluno criar conta

O cadastro pelo site só funciona para e-mails liberados previamente pelo responsável. A autorização cria apenas o registro de permissão: não cria uma conta, não define senha e não cria uma caixa de e-mail na faculdade.

No terminal do VS Code, na pasta do projeto, execute:

```powershell
python .\ouvidoria.py --contas
```

1. Escolha **4 — Autorizar e-mail de aluno (sem senha)**.
2. Digite o e-mail institucional que poderá criar conta.
3. Repita a operação para os demais alunos, se necessário.
4. Escolha **0 — Sair** e inicie o servidor normalmente, ou com `--rede-local` para testes pelo celular.

O aluno então acessa **Primeiro acesso? Criar conta de aluno**, informa exatamente o endereço liberado e escolhe a própria senha. Um endereço com domínio correto, mas que não esteja autorizado, também será recusado. A conferência é feita no servidor, não apenas no formulário.

Use **5 — Listar e-mails autorizados** para ver quem ainda aguarda cadastro e quem já criou a conta. A opção **6 — Cancelar autorização pendente** retira uma liberação que ainda não foi usada; ela não exclui nem bloqueia contas existentes. Autorizar o mesmo endereço pendente novamente não duplica o registro.

A **opção 1** continua criando uma conta já com senha e perfil, sendo indicada para a equipe ou provisionamento direto. Para deixar o aluno definir a própria senha pelo site, use a **opção 4**.

Contas já cadastradas continuam funcionando e não precisam de nova liberação. Não há importação de uma lista real da faculdade: este é um controle manual do protótipo. A autorização prévia também não comprova que a pessoa que digitou o endereço é dona da caixa de e-mail; para implantação real, esse vínculo precisaria ser verificado por integração institucional ou confirmação apropriada.

## Criar conta e entrar

1. Peça ao responsável para liberar seu endereço e clique em **Primeiro acesso? Criar conta de aluno**.
2. Informe seu e-mail `@camporeal.edu.br` e uma senha de 8 a 128 caracteres. Confirme a senha.
3. Guarde o **código de recuperação** exibido uma única vez. Ele não é enviado por e-mail.
4. Marque que guardou o código para fechar a janela.
5. Digite novamente e-mail e senha e clique em **Entrar**. O cadastro não cria uma sessão automaticamente.

O campo de e-mail começa vazio. O cadastro público cria somente alunos previamente autorizados; ele não oferece escolha de perfil administrativo. O domínio é validado, mas a titularidade do endereço não é comprovada. O código de recuperação comprova a posse do segredo da conta, não a propriedade de uma caixa de e-mail.

## Esqueci minha senha

O botão **Esqueci minha senha** abre um formulário funcional. Informe o e-mail da conta, o código de recuperação guardado e a nova senha, duas vezes.

Quando a recuperação é aceita:

- a senha é substituída;
- todas as sessões anteriores da conta são encerradas;
- o código usado deixa de funcionar;
- um novo código é exibido uma única vez;
- a pessoa deve guardar o novo código e entrar com a nova senha.

O código é um segredo de alta entropia. O banco guarda apenas sua verificação com HMAC, nunca o código original. Conhecer somente o e-mail não permite redefinir uma senha. Há limites de tentativas por conta e IP.

**Já tinha conta antes desta atualização?** Entre com sua senha normal e clique em **Código de recuperação**, junto aos dados da conta. Confirme a senha atual para gerar e guardar um código. Esse mesmo botão permite substituir um código perdido; o anterior é invalidado. Não é possível mostrar novamente o código antigo.

Se perdeu a senha e também o código, o responsável pela instalação deve redefinir pelo menu local `--contas`. Não há código mestre nem recuperação automática baseada apenas em e-mail.

## Contas de supervisor e diretor

No computador responsável pela instalação, execute:

```sh
python ouvidoria.py --contas
```

O menu permite criar contas de aluno, supervisor e diretor, redefinir senhas, listar contas e autorizar, listar ou cancelar liberações pendentes de alunos. A senha não aparece enquanto é digitada. O banco permite apenas um diretor.

Ao criar uma conta ou redefinir uma senha pelo menu, o programa mostra um novo código de recuperação uma única vez. Entregue esse código somente ao titular da conta. Uma redefinição também invalida sessões e o código de recuperação anteriores.

## Enviar uma manifestação

1. Clique em **Nova manifestação** e preencha tipo, área, assunto e relato.
2. Escolha se quer manter a identidade restrita ao diretor.
3. Clique em **Revisar e enviar**. Essa etapa ainda não registra a manifestação.
4. Confira o resumo. Use **Voltar e revisar** para alterar ou **Confirmar envio** para registrar.
5. O site mostra a confirmação e o protocolo no histórico do atendimento.

O servidor exige a confirmação e usa um identificador de envio para que a repetição do mesmo pedido, por exemplo após uma falha de rede, retorne o mesmo protocolo em vez de duplicá-lo.

## Anonimato, justificativa e acompanhamento

- O aluno consulta somente os próprios protocolos e pode ler respostas, complementar relatos e solicitar nova análise.
- O supervisor atende a fila sem receber o e-mail de quem enviou uma manifestação anônima.
- O diretor pode consultar a autoria restrita, mas precisa registrar uma justificativa de 20 a 2.000 caracteres antes de recebê-la.
- A consulta registra conta responsável, protocolo, justificativa e data. O aluno vê a data e o motivo no histórico do próprio protocolo, ao atualizar ou reabrir a página. Não é enviado aviso externo por e-mail.
- Consultar a autoria não muda a opção anônima: o supervisor continua sem receber essa identidade.

A justificativa não fica disponível para o supervisor. Consultas realizadas em versões antigas podem não ter justificativa; o histórico identifica essa situação. Não há alteração retroativa para inventar um motivo.

Evite escrever nomes e e-mails no relato ou na justificativa. Esses textos livres continuam legíveis no banco e podem identificar alguém por seu conteúdo.

## Filtros e arquivo

Supervisor e diretor podem combinar área, situação e busca por assunto/protocolo. A aba **Todas as manifestações** mostra os registros não arquivados; **Arquivadas** mantém o histórico dos atendimentos concluídos.

**Resolver e arquivar** altera a situação para Resolvida e move o protocolo para o arquivo. A confirmação de solução pelo aluno também arquiva. **Desarquivar e retomar atendimento** volta para Em análise. Uma nova mensagem ou pedido de análise do aluno devolve o protocolo à fila principal. Arquivar não apaga dados.

## Criptografia dos e-mails

Os e-mails estruturados são armazenados na tabela `identities` como conteúdo cifrado com Fernet, que oferece criptografia autenticada. As demais tabelas usam identificadores opacos derivados por HMAC, sem guardar o endereço diretamente. Isso inclui contas, autoria das manifestações e responsáveis na auditoria.

A chave é criada automaticamente em **`segredos/email.key`**, fora do SQLite. `DATA_KEY_FILE` pode apontar para outro local protegido. Nunca envie a chave ao GitHub, nunca a substitua e nunca a apague enquanto quiser usar o banco atual. A pasta `segredos` e arquivos `.key` estão no `.gitignore`.

**Limite da proteção:** quem tiver apenas uma cópia do banco não terá os e-mails em texto simples. Quem controlar o computador e conseguir ler a chave, ou alterar o programa, poderá descriptografá-los e contornar as permissões da aplicação. Os identificadores também permitem correlacionar registros; a criptografia não oculta todo o contexto de uma manifestação. Essa solução não garante anonimato contra o administrador da infraestrutura.

O banco inteiro não é criptografado. Relatos, mensagens, assuntos, datas e justificativas continuam legíveis. Os e-mails que uma pessoa escrever voluntariamente nesses textos não são removidos nem cifrados automaticamente.

## Atualizar sem perder dados

1. Pare o serviço e outras instâncias do programa.
2. Faça uma cópia privada do banco atual e da chave, caso a instalação já possua uma.
3. Substitua o código na mesma pasta, preservando **`data`**, **`segredos`** e o seu **`.env`**.
4. Instale a dependência: `python -m pip install -r requirements.txt`.
5. Inicie o programa. A migração mantém contas, hashes de senha, protocolos, respostas e auditoria.

A primeira conversão dos e-mails cria a chave se ela ainda não existir, converte os campos estruturados, encerra sessões antigas, limpa contadores que continham endereços e recompõe o SQLite para remover cópias antigas das páginas. O processo também tenta concluir o checkpoint do WAL. Se outra instância impedir a limpeza, feche-a e execute novamente.

Se o banco já está cifrado e a chave estiver ausente ou diferente, o programa recusa a inicialização em vez de gerar uma substituta. Restaure a chave original. Não apague o banco como tentativa de correção.

Backups, cópias exportadas e arquivos antigos criados antes da migração podem continuar contendo e-mails legíveis. A atualização não apaga esses arquivos pessoais. Eles devem ser protegidos e tratados conforme a política de retenção.

As contas da versão anterior continuam usando as mesmas senhas. Elas podem gerar seu código de recuperação depois de entrar. Para e-mails com relatos antigos e sem conta, o responsável pode provisionar a conta pela opção 1 ou autorizar o cadastro pela opção 4 após conferir o titular correto. O cadastro público continua bloqueado sem essa autorização.

## PC e celular na mesma rede

```sh
python ouvidoria.py --rede-local
```

No celular, abra **http://IP_DO_COMPUTADOR:8000**. No PC, use esse endereço ou **http://localhost:8000**. Ambos precisam estar na mesma rede, sem isolamento de clientes. Mantenha o computador e o terminal ligados e permita Python no firewall apenas na rede privada. Use `ipconfig` para consultar o IPv4 do Wi-Fi ou Ethernet.

O modo local valida endereços literais de loopback ou rede privada, exigindo correspondência entre origem, Host e porta real do servidor. Domínios externos só são aceitos quando configurados em `APP_URL` ou `ALLOWED_ORIGINS`. Não há liberação por curinga; CSRF e permissões continuam ativos.

Esse modo é para testes locais. Em instalação institucional, use servidor persistente, proxy HTTPS, controle de acesso ao sistema operacional e política de privacidade. Em rede compartilhada, ajuste a política de limites por IP, pois o programa considera a conexão direta e não confia em `X-Forwarded-For`.

## Banco, integridade e backups

- [BANCO_DE_DADOS.md](BANCO_DE_DADOS.md) explica tabelas, campos, relações e informações sensíveis.
- [banco.sql](banco.sql) contém o mesmo esquema embutido no programa. Migrações acrescentam os campos faltantes nos bancos antigos.

```sh
python ouvidoria.py --banco
python ouvidoria.py --backup
```

`--banco` mostra integridade e contagens, sem listar e-mails ou relatos. `--backup` usa a API do SQLite e salva uma cópia consistente em `data/backups`.

**Guarde também uma cópia protegida da chave, separada do banco e com acesso restrito.** O comando de backup não inclui nem envia a chave automaticamente. Sem a chave original, os e-mails de um backup não poderão ser recuperados. Relatos e justificativas exigem proteção mesmo com os e-mails cifrados.

Não há agendamento, retenção automática nem cópia externa automática. Defina essas rotinas e teste a restauração. Veja o guia do banco antes de restaurar.

## Demonstração e organização

Abra `DEMONSTRACAO.html` para apresentar as telas com dados fictícios. Ela ilustra a revisão do envio e a consulta justificada, mas não representa a segurança do servidor. Recuperação de senha, códigos reais e autorizações do terminal funcionam apenas no programa Python. No formulário de cadastro da demonstração, use o endereço fictício autorizado `aluno.exemplo@camporeal.edu.br`.

O servidor e as funções do banco vêm primeiro em `ouvidoria.py`. O SQL e os conteúdos HTML, CSS e JavaScript estão ao final, sem duplicação das telas na demonstração. O `.env` é opcional para os testes locais; gere o modelo com `--configurar` se precisar ajustar o endereço.

As marcas são reproduções vetoriais de referência das imagens fornecidas, não os arquivos originais. Substitua os SVGs antes de uma publicação oficial.

## Testes

```sh
python -m unittest discover -s tests -v
```

Com Node.js, também é possível executar os testes opcionais das interações:

```sh
node tests/test_frontend.cjs
node tests/test_security_frontend.cjs
```

Os testes usam bancos temporários e verificam autorização prévia pelo terminal, bloqueio de e-mails não liberados, consumo único da autorização, cancelamento pendente, preservação de contas existentes, recuperação de uso único, revogação de sessões, ausência de e-mails estruturados e códigos legíveis no SQLite, chave ausente/incorreta, migração, justificativa obrigatória e visível ao titular, confirmação de envio, repetição sem duplicidade, permissões, CSRF, arquivamento e acesso local. As telas ainda devem ser conferidas nos dispositivos reais antes da publicação institucional.
