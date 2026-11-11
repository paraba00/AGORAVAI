-- Estrutura do banco SQLite da Ouvidoria Campo Real.
-- O programa aplica este mesmo esquema e suas migrações sem apagar dados antigos.

-- Contas e permissões. A senha original nunca é guardada.
CREATE TABLE IF NOT EXISTS accounts (
    email   TEXT PRIMARY KEY,
    salt    TEXT NOT NULL,
    hash    TEXT NOT NULL,
    role    TEXT NOT NULL CHECK (role IN ('aluno', 'supervisor', 'diretor')),
    created REAL NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS one_director
    ON accounts (role)
    WHERE role = 'diretor';

-- Acesso temporário. hash representa o token de sessão, não a senha.
CREATE TABLE IF NOT EXISTS sessions (
    hash    TEXT PRIMARY KEY,
    email   TEXT NOT NULL,
    expires REAL NOT NULL,
    csrf    TEXT NOT NULL
);

-- Relato original. anonymous restringe a autoria no atendimento;
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
    archived  INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0, 1))
);

-- Conversa do protocolo. A chave estrangeira evita mensagens órfãs.
CREATE TABLE IF NOT EXISTS messages (
    id      INTEGER PRIMARY KEY,
    ticket  TEXT NOT NULL REFERENCES tickets (id),
    author  TEXT NOT NULL,
    body    TEXT NOT NULL,
    created REAL NOT NULL
);

-- Ações sensíveis: consulta de autoria, arquivamento e desarquivamento.
CREATE TABLE IF NOT EXISTS audit (
    id      INTEGER PRIMARY KEY,
    actor   TEXT NOT NULL,
    action  TEXT NOT NULL,
    ticket  TEXT NOT NULL,
    created REAL NOT NULL
);

-- Contadores temporários para limitar tentativas de acesso e alterações.
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
