-- Estrutura do banco SQLite da Ouvidoria Campo Real.
-- O programa aplica este mesmo esquema e suas migrações sem apagar dados antigos.

-- E-mails cifrados. A chave fica fora do banco, em segredos/email.key.
CREATE TABLE IF NOT EXISTS identities (
    id TEXT PRIMARY KEY,
    email_cipher TEXT NOT NULL
);

-- Contas e permissões. email contém o identificador opaco de identities.
CREATE TABLE IF NOT EXISTS accounts (
    email   TEXT PRIMARY KEY,
    salt    TEXT NOT NULL,
    hash    TEXT NOT NULL,
    role    TEXT NOT NULL CHECK (role IN ('aluno', 'supervisor', 'diretor')),
    created REAL NOT NULL,
    recovery_hash TEXT NOT NULL DEFAULT ''
);

CREATE UNIQUE INDEX IF NOT EXISTS one_director
    ON accounts (role)
    WHERE role = 'diretor';

-- Acesso temporário. hash é o token de sessão; email é um identificador opaco.
CREATE TABLE IF NOT EXISTS sessions (
    hash    TEXT PRIMARY KEY,
    email   TEXT NOT NULL,
    expires REAL NOT NULL,
    csrf    TEXT NOT NULL
);

-- Relato original. email é um identificador opaco, não o endereço legível.
-- anonymous restringe a autoria no atendimento;
-- archived organiza a fila sem excluir o protocolo.
CREATE TABLE IF NOT EXISTS tickets (
    id        TEXT PRIMARY KEY,
    email     TEXT NOT NULL,
    anonymous INTEGER NOT NULL,
    kind      TEXT NOT NULL,
    subject   TEXT NOT NULL,
    sector    TEXT NOT NULL,
    body      TEXT NOT NULL,
    status    TEXT NOT NULL,
    created   REAL NOT NULL,
    archived  INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0, 1)),
    submission_id TEXT
);

-- Conversa do protocolo. A chave estrangeira evita mensagens órfãs.
CREATE TABLE IF NOT EXISTS messages (
    id      INTEGER PRIMARY KEY,
    ticket  TEXT NOT NULL REFERENCES tickets (id),
    author  TEXT NOT NULL,
    body    TEXT NOT NULL,
    created REAL NOT NULL
);

-- Ações sensíveis. actor é identificador opaco; reason explica a consulta ao aluno.
CREATE TABLE IF NOT EXISTS audit (
    id      INTEGER PRIMARY KEY,
    actor   TEXT NOT NULL,
    action  TEXT NOT NULL,
    ticket  TEXT NOT NULL,
    created REAL NOT NULL,
    reason TEXT NOT NULL DEFAULT ''
);

-- O índice ticket_submission é criado pela migração após garantir submission_id.
-- Contadores de acesso usam identificadores, sem e-mail legível.
CREATE TABLE IF NOT EXISTS limits (
    key   TEXT PRIMARY KEY,
    hits  INTEGER NOT NULL,
    reset REAL NOT NULL
);

-- Migrações já executadas. Não altere esta tabela manualmente.
CREATE TABLE IF NOT EXISTS auth_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
