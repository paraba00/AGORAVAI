"""Ouvidoria Campo Real.

Execute `python ouvidoria.py` para iniciar ou use `--ajuda` para ver as opções.
O servidor vem primeiro neste arquivo; as telas estão reunidas ao final.
O banco existente é preservado pelas migrações da função initialize().
"""

import argparse
import base64
import getpass
import hashlib
import hmac
import ipaddress
import json
import os
import secrets
import socket
import sqlite3
import time
import webbrowser
from contextlib import contextmanager
from datetime import datetime
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
import re

try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError:
    raise SystemExit(
        "Instale a dependência: python -m pip install cryptography"
    ) from None

ROOT = Path(__file__).parent
config = ROOT / ".env"
if config.exists():
    for line in config.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if separator:
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            os.environ.setdefault(key.strip(), value)
DB = Path(os.getenv("DATABASE_PATH", str(ROOT / "data" / "ouvidoria.sqlite3")))
KEY_PATH = Path(os.getenv("DATA_KEY_FILE", str(ROOT / "segredos" / "email.key")))
APP_URL = os.getenv("APP_URL", "http://localhost:8000").rstrip("/")
DIRECTOR = os.getenv("DIRECTOR_EMAIL", "").strip().lower()
SUPERVISORS = {
    x.strip().lower()
    for x in os.getenv("SUPERVISOR_EMAILS", "").split(",")
    if x.strip()
}
INSTITUTIONAL = re.compile(
    r"[a-z0-9.!#$%&\x27*+/=?^_`{|}~-]+@camporeal\.edu\.br", re.ASCII
)
TYPES = {"Reclamação", "Crítica", "Sugestão", "Elogio", "Solicitação"}
STATUSES = {"Recebida", "Em análise", "Respondida", "Resolvida"}


@contextmanager
def database():
    """Abre uma conexão por operação e confirma ou desfaz a transação ao sair."""
    connection = sqlite3.connect(DB, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA secure_delete=ON")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize():
    """Cria as tabelas e aplica apenas as migrações ainda não executadas."""
    DB.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(DB.parent, 0o700)
    with database() as db:
        db.executescript(SCHEMA_SQL)
        if not db.execute(
            "SELECT 1 FROM auth_meta WHERE key='password_auth_v1'"
        ).fetchone():
            db.execute("DELETE FROM sessions")
            if db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='codes'"
            ).fetchone():
                db.execute("DELETE FROM codes")
            db.execute("INSERT INTO auth_meta VALUES ('password_auth_v1','1')")
        columns = {row["name"] for row in db.execute("PRAGMA table_info(tickets)")}
        if "archived" not in columns:
            db.execute(
                "ALTER TABLE tickets ADD COLUMN archived INTEGER NOT NULL DEFAULT 0 CHECK(archived IN (0,1))"
            )
        if not db.execute("SELECT 1 FROM auth_meta WHERE key='archive_v1'").fetchone():
            db.execute("UPDATE tickets SET archived=1 WHERE status='Resolvida'")
            db.execute("INSERT INTO auth_meta VALUES ('archive_v1','1')")
    os.chmod(DB, 0o600)
    migrate_sensitive_data()


def load_data_key(create=False):
    """A chave fica fora do SQLite. Nunca é enviada ao navegador ou ao GitHub."""
    if not KEY_PATH.exists():
        if not create:
            raise RuntimeError(
                "Chave de e-mails não encontrada. Restaure a pasta segredos do backup; não gere outra chave para um banco já criptografado."
            )
        KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(KEY_PATH.parent, 0o700)
        try:
            descriptor = os.open(KEY_PATH, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(descriptor, "wb") as file:
                file.write(Fernet.generate_key())
                file.flush()
                os.fsync(file.fileno())
    key = KEY_PATH.read_bytes().strip()
    try:
        Fernet(key)
    except (ValueError, TypeError):
        raise RuntimeError(
            "A chave de e-mails está inválida. Restaure a chave original da instalação."
        ) from None
    return key


def keyed_digest(purpose, value):
    master = base64.urlsafe_b64decode(load_data_key())
    key = hmac.new(master, b"ouvidoria-keyed-digests-v1", hashlib.sha256).digest()
    return hmac.new(key, (purpose + ":" + value).encode(), hashlib.sha256).hexdigest()


def account_id(email):
    if email.startswith("id:"):
        return email
    return "id:" + keyed_digest("email-index-v1", email.strip().lower())


def ensure_identity(db, email):
    """Mantém o vínculo por identificador opaco e guarda o endereço com Fernet."""
    email = email.strip().lower()
    identifier = account_id(email)
    if not db.execute("SELECT 1 FROM identities WHERE id=?", (identifier,)).fetchone():
        cipher = Fernet(load_data_key()).encrypt(email.encode()).decode()
        db.execute(
            "INSERT INTO identities(id,email_cipher) VALUES (?,?)", (identifier, cipher)
        )
    return identifier


def email_for(identifier, db):
    row = db.execute(
        "SELECT email_cipher FROM identities WHERE id=?", (identifier,)
    ).fetchone()
    if not row:
        raise RuntimeError(
            "Identidade não encontrada. Verifique a migração e o backup da instalação."
        )
    return Fernet(load_data_key()).decrypt(row["email_cipher"].encode()).decode()


def normalize_recovery(code):
    if not isinstance(code, str) or len(code) > 120:
        return ""
    return re.sub(r"[-\s]", "", code).upper()


def recovery_digest(identifier, code):
    return keyed_digest("recovery-v1", identifier + ":" + normalize_recovery(code))


def new_recovery_code():
    value = secrets.token_hex(16).upper()
    return "CR-" + "-".join(value[index : index + 4] for index in range(0, 32, 4))


def rotate_recovery(db, identifier):
    code = new_recovery_code()
    db.execute(
        "UPDATE accounts SET recovery_hash=? WHERE email=?",
        (recovery_digest(identifier, code), identifier),
    )
    return code


def replace_password(db, identifier, password):
    check_password(password)
    salt = secrets.token_hex(16)
    count = db.execute(
        "UPDATE accounts SET salt=?,hash=? WHERE email=?",
        (salt, password_hash(password, salt), identifier),
    ).rowcount
    if not count:
        raise ValueError("Conta não encontrada.")
    db.execute("DELETE FROM sessions WHERE email=?", (identifier,))
    return rotate_recovery(db, identifier)


def migrate_sensitive_data():
    """Converte as referências antigas sem trocar protocolos, senhas ou relatos."""
    with database() as db:
        marker = db.execute(
            "SELECT value FROM auth_meta WHERE key='email_crypto_v1'"
        ).fetchone()
        key = load_data_key(create=marker is None)
        fingerprint = hashlib.sha256(key).hexdigest()
        if marker and not hmac.compare_digest(marker["value"], fingerprint):
            raise RuntimeError(
                "Esta chave não pertence ao banco. Restaure a chave original; os dados não foram alterados."
            )
        for table, column, definition in (
            ("accounts", "recovery_hash", "TEXT NOT NULL DEFAULT ''"),
            ("audit", "reason", "TEXT NOT NULL DEFAULT ''"),
            ("tickets", "submission_id", "TEXT"),
        ):
            names = {
                row["name"] for row in db.execute("PRAGMA table_info(" + table + ")")
            }
            if column not in names:
                db.execute(
                    "ALTER TABLE " + table + " ADD COLUMN " + column + " " + definition
                )
        db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS ticket_submission ON tickets(email,submission_id) WHERE submission_id IS NOT NULL"
        )
        db.commit()
        if marker:
            pending = db.execute(
                "SELECT 1 FROM auth_meta WHERE key='email_cleanup_pending'"
            ).fetchone()
            if pending:
                finish_email_cleanup(db)
            return
        db.execute("BEGIN IMMEDIATE")
        for table, column in (
            ("accounts", "email"),
            ("tickets", "email"),
            ("audit", "actor"),
        ):
            rows = db.execute(
                "SELECT DISTINCT " + column + " AS address FROM " + table
            ).fetchall()
            for row in rows:
                email = row["address"]
                if "@" not in email or email.startswith("id:"):
                    continue
                identifier = ensure_identity(db, email)
                db.execute(
                    "UPDATE " + table + " SET " + column + "=? WHERE " + column + "=?",
                    (identifier, email),
                )
        db.execute("DELETE FROM sessions")
        db.execute("DELETE FROM limits")
        if db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='codes'"
        ).fetchone():
            db.execute("DELETE FROM codes")
        db.execute(
            "INSERT INTO auth_meta(key,value) VALUES ('email_crypto_v1',?)",
            (fingerprint,),
        )
        db.execute(
            "INSERT OR REPLACE INTO auth_meta(key,value) VALUES ('email_cleanup_pending','1')"
        )
        db.commit()
        finish_email_cleanup(db)


def finish_email_cleanup(db):
    """Remove páginas e quadros antigos após a conversão, sem apagar backups do usuário."""
    db.execute("VACUUM")
    checkpoint = db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    if checkpoint and checkpoint[0] != 0:
        raise RuntimeError(
            "A migração precisa concluir a limpeza do SQLite. Feche outras instâncias do programa e execute novamente."
        )
    db.execute("DELETE FROM auth_meta WHERE key='email_cleanup_pending'")
    db.commit()


def origin_key(value):
    """Normaliza uma origem sem aceitar caminhos, credenciais ou curingas."""
    try:
        parsed = urlparse(value)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return None
        if parsed.username is not None or parsed.password is not None:
            return None
        if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            return None
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        return parsed.scheme, parsed.hostname.lower(), port
    except ValueError:
        return None


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


PASSWORD_ITERATIONS = 600000


def password_hash(password, salt):
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), PASSWORD_ITERATIONS
    ).hex()


def check_password(password):
    if (
        not isinstance(password, str)
        or not 8 <= len(password) <= 128
        or not password.strip()
    ):
        raise ValueError(
            "A senha precisa ter entre 8 e 128 caracteres e não pode conter apenas espaços."
        )


def insert_account(db, email, password, profile):
    """Cria a conta sem guardar o e-mail ou o código de recuperação em texto simples."""
    email = email.strip().lower()
    if not INSTITUTIONAL.fullmatch(email) or profile not in (
        "aluno",
        "supervisor",
        "diretor",
    ):
        raise ValueError("Use um e-mail @camporeal.edu.br e um perfil válido.")
    check_password(password)
    identifier = ensure_identity(db, email)
    salt = secrets.token_hex(16)
    db.execute(
        "INSERT INTO accounts(email,salt,hash,role,created) VALUES (?,?,?,?,?)",
        (identifier, salt, password_hash(password, salt), profile, time.time()),
    )
    return rotate_recovery(db, identifier)


def role(email):
    """Lê a permissão no banco, sem confiar no perfil enviado pelo navegador."""
    with database() as db:
        account = db.execute(
            "SELECT role FROM accounts WHERE email=?", (account_id(email),)
        ).fetchone()
        if not account:
            raise Error(401, "Entre com seu e-mail e senha para continuar.")
        return account["role"]


def manage_accounts():
    """Menu disponível apenas no computador responsável pela instalação."""
    initialize()
    while True:
        print(
            "\nCONTAS DA OUVIDORIA\n1 - Criar conta\n2 - Redefinir senha\n3 - Listar contas\n0 - Sair"
        )
        option = input("Escolha: ").strip()
        if option == "0":
            return
        try:
            if option == "3":
                with database() as db:
                    for row in db.execute(
                        "SELECT email,role FROM accounts ORDER BY role,email"
                    ):
                        print(row["role"] + ": " + email_for(row["email"], db))
                continue
            if option not in ("1", "2"):
                print("Escolha uma das opções do menu.")
                continue
            email = input("E-mail @camporeal.edu.br: ").strip().lower()
            profile = (
                {"1": "aluno", "2": "supervisor", "3": "diretor"}.get(
                    input("Perfil: 1-aluno, 2-supervisor, 3-diretor: ").strip()
                )
                if option == "1"
                else None
            )
            password = getpass.getpass("Nova senha (mínimo 8 caracteres): ")
            if password != getpass.getpass("Repita a senha: "):
                raise ValueError("As senhas não são iguais.")
            check_password(password)
            with database() as db:
                if option == "1":
                    recovery = insert_account(db, email, password, profile)
                else:
                    recovery = replace_password(db, account_id(email), password)
            print(
                "Conta criada."
                if option == "1"
                else "Senha redefinida; sessões antigas encerradas."
            )
            print("Código de recuperação (exibido somente agora):", recovery)
            print(
                "Entregue este código apenas ao titular da conta e peça para guardá-lo em local privado."
            )
        except sqlite3.IntegrityError:
            print(
                "Essa conta já existe ou já há um diretor cadastrado. É permitido somente um diretor."
            )
        except ValueError as error:
            print(str(error))


class Error(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def send(self, status, payload, cookie=None):
        data = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(data)

    def success(self, db, status, payload, cookie=None):
        db.commit()
        return self.send(status, payload, cookie)

    def cookie(self, value, age):
        origin = origin_key(self.headers.get("Origin", ""))
        secure = "; Secure" if origin and origin[0] == "https" else ""
        return f"cr_session={value}; Path=/; HttpOnly; SameSite=Strict; Max-Age={age}{secure}"

    def session(self, db):
        cookies = SimpleCookie()
        try:
            cookies.load(self.headers.get("Cookie", ""))
            token = cookies["cr_session"].value
        except (KeyError, ValueError):
            raise Error(401, "Entre com seu e-mail institucional para continuar.")
        row = db.execute(
            "SELECT sessions.* FROM sessions JOIN accounts ON accounts.email=sessions.email WHERE sessions.hash=? AND sessions.expires>?",
            (digest(token), time.time()),
        ).fetchone()
        if not row:
            raise Error(401, "Sua sessão expirou. Entre novamente.")
        return dict(row)

    def limit(self, db, key, maximum, window):
        now = time.time()
        db.execute("DELETE FROM limits WHERE reset<?", (now,))
        db.execute(
            "INSERT INTO limits VALUES (?,1,?) ON CONFLICT(key) DO UPDATE SET hits=hits+1",
            (key, now + window),
        )
        count = db.execute("SELECT hits FROM limits WHERE key=?", (key,)).fetchone()[0]
        db.commit()
        if count > maximum:
            raise Error(
                429, "Muitas tentativas. Aguarde alguns minutos e tente novamente."
            )

    def text(self, data, key, minimum=1, maximum=5000):
        value = data.get(key, "")
        if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum:
            raise Error(
                400,
                f"Preencha corretamente o campo {key} ({minimum} a {maximum} caracteres).",
            )
        return value.strip()

    def do_GET(self):
        path = urlparse(self.path).path
        try:
            if path.startswith("/api/"):
                with database() as db:
                    session = self.session(db)
                    email = session["email"]
                    profile = role(email)
                    if path == "/api/me":
                        return self.send(
                            200,
                            {
                                "email": email_for(email, db),
                                "role": profile,
                                "csrf": session["csrf"],
                                "has_recovery_code": bool(
                                    db.execute(
                                        "SELECT recovery_hash FROM accounts WHERE email=?",
                                        (email,),
                                    ).fetchone()["recovery_hash"]
                                ),
                            },
                        )
                    if path == "/api/tickets":
                        query = (
                            "SELECT * FROM tickets"
                            + (" WHERE email=?" if profile == "aluno" else "")
                            + " ORDER BY created DESC"
                        )
                        rows = db.execute(
                            query, (email,) if profile == "aluno" else ()
                        ).fetchall()
                        tickets = []
                        for row in rows:
                            ticket = dict(row)
                            owner = ticket.pop("email")
                            ticket["identity"] = (
                                email_for(owner, db)
                                if not ticket["anonymous"] or profile == "aluno"
                                else None
                            )
                            ticket["messages"] = [
                                dict(m)
                                for m in db.execute(
                                    "SELECT author,body,created FROM messages WHERE ticket=? ORDER BY id",
                                    (ticket["id"],),
                                )
                            ]
                            ticket["identity_accesses"] = (
                                [
                                    dict(event)
                                    for event in db.execute(
                                        "SELECT reason,created FROM audit WHERE ticket=? AND action='Consulta de autoria restrita' ORDER BY id",
                                        (ticket["id"],),
                                    )
                                ]
                                if owner == email or profile == "diretor"
                                else []
                            )
                            ticket.pop("submission_id", None)
                            tickets.append(ticket)
                        return self.send(200, tickets)
                    raise Error(404, "Recurso não encontrado.")
            paths = {
                "/": "index.html",
                "/index.html": "index.html",
                "/app.js": "app.js",
                "/style.css": "style.css",
                "/assets/logo-azul.svg": "assets/logo-azul.svg",
                "/assets/logo-branca.svg": "assets/logo-branca.svg",
            }
            if path not in paths:
                raise Error(404, "Página não encontrada.")
            filename = paths[path]
            mime = {
                ".html": "text/html",
                ".js": "text/javascript",
                ".css": "text/css",
                ".svg": "image/svg+xml",
            }[Path(filename).suffix]
            data = ASSETS[filename].encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", mime + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
            )
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(data)
        except Error as error:
            self.send(error.status, {"error": error.message})
        except Exception:
            self.send(500, {"error": "Não foi possível carregar os dados."})

    def origin_allowed(self):
        """Confere a origem antes de qualquer cadastro ou alteração de dados."""
        origin = origin_key(self.headers.get("Origin", ""))
        if origin is None:
            return False

        configured = [APP_URL, *os.getenv("ALLOWED_ORIGINS", "").split(",")]
        if any(origin == origin_key(value.strip()) for value in configured):
            return True

        request_host = origin_key("http://" + self.headers.get("Host", ""))
        if origin != request_host or origin[0] != "http":
            return False
        if origin[2] != self.server.server_port:
            return False
        if origin[1] == "localhost":
            return True

        try:
            address = ipaddress.ip_address(origin[1])
        except ValueError:
            return False

        local_ranges = (
            "10.0.0.0/8",
            "172.16.0.0/12",
            "192.168.0.0/16",
            "fc00::/7",
            "fe80::/10",
        )
        return address.is_loopback or any(
            address in ipaddress.ip_network(network) for network in local_ranges
        )

    def do_POST(self):
        try:
            if not self.origin_allowed():
                raise Error(403, "Origem da solicitação não autorizada.")
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                raise Error(415, "Envie dados no formato JSON.")
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 24000:
                raise Error(413, "Solicitação muito grande ou vazia.")
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise Error(400, "Dados inválidos.")
            path = urlparse(self.path).path
            now = time.time()
            with database() as db:
                if path in ("/api/login", "/api/register", "/api/recover"):
                    self.limit(db, "auth-ip:" + self.client_address[0], 60, 600)
                    email = self.text(data, "email", 1, 254).lower()
                    if not INSTITUTIONAL.fullmatch(email):
                        raise Error(400, "Use seu e-mail @camporeal.edu.br.")
                    identifier = account_id(email)
                    self.limit(db, "auth-email:" + identifier, 15, 600)
                    password = data.get("password")
                    try:
                        check_password(password)
                    except ValueError as error:
                        raise Error(400, str(error)) from None
                    if path == "/api/recover":
                        self.limit(db, "recover:" + identifier, 5, 900)
                        supplied = data.get("recovery_code", "")
                        db.execute("BEGIN IMMEDIATE")
                        account = db.execute(
                            "SELECT * FROM accounts WHERE email=?", (identifier,)
                        ).fetchone()
                        expected = account["recovery_hash"] if account else ""
                        candidate = recovery_digest(identifier, supplied)
                        if not expected or not hmac.compare_digest(expected, candidate):
                            raise Error(
                                400,
                                "Não foi possível recuperar. Confira o e-mail e o código de recuperação.",
                            )
                        recovery = replace_password(db, identifier, password)
                        return self.success(
                            db,
                            200,
                            {
                                "ok": True,
                                "recovery_code": recovery,
                                "message": "Senha alterada. Guarde o novo código e faça login.",
                            },
                            self.cookie("", 0),
                        )
                    if path == "/api/register":
                        db.execute("BEGIN IMMEDIATE")
                        exists = db.execute(
                            "SELECT 1 FROM accounts WHERE email=?", (identifier,)
                        ).fetchone()
                        legacy = db.execute(
                            "SELECT 1 FROM tickets WHERE email=? LIMIT 1", (identifier,)
                        ).fetchone()
                        if (
                            exists
                            or legacy
                            or email == DIRECTOR
                            or email in SUPERVISORS
                        ):
                            raise Error(
                                409,
                                "Conta existente ou reservada. Entre com sua senha ou peça ao responsável para criar ou recuperar a conta.",
                            )
                        recovery = insert_account(db, email, password, "aluno")
                        return self.success(
                            db,
                            201,
                            {
                                "ok": True,
                                "message": "Conta criada. Guarde o código e entre com seu e-mail e senha.",
                                "recovery_code": recovery,
                            },
                        )
                    else:
                        account = db.execute(
                            "SELECT * FROM accounts WHERE email=?", (identifier,)
                        ).fetchone()
                        salt = account["salt"] if account else "0" * 32
                        candidate = password_hash(password, salt)
                        if not account or not hmac.compare_digest(
                            account["hash"], candidate
                        ):
                            raise Error(
                                401,
                                "E-mail ou senha incorretos. No primeiro acesso, crie sua conta de aluno.",
                            )
                    db.execute("DELETE FROM sessions WHERE expires<?", (now,))
                    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
                    db.execute(
                        "INSERT INTO sessions VALUES (?,?,?,?)",
                        (digest(token), identifier, now + 28800, csrf),
                    )
                    return self.success(
                        db, 200, {"ok": True}, self.cookie(token, 28800)
                    )
                session = self.session(db)
                if not hmac.compare_digest(
                    self.headers.get("X-CSRF-Token", ""), session["csrf"]
                ):
                    raise Error(403, "Atualize a página e tente novamente.")
                email, profile = session["email"], role(session["email"])
                if path == "/api/logout":
                    db.execute("DELETE FROM sessions WHERE hash=?", (session["hash"],))
                    return self.success(db, 200, {"ok": True}, self.cookie("", 0))
                self.limit(db, "write:" + email, 60, 600)
                if path == "/api/recovery-code":
                    self.limit(db, "code-change:" + email, 8, 900)
                    current = data.get("current_password")
                    if not isinstance(current, str) or len(current) > 128:
                        raise Error(400, "Informe sua senha atual.")
                    db.execute("BEGIN IMMEDIATE")
                    account = db.execute(
                        "SELECT * FROM accounts WHERE email=?", (email,)
                    ).fetchone()
                    if not hmac.compare_digest(
                        account["hash"], password_hash(current, account["salt"])
                    ):
                        raise Error(400, "Senha atual incorreta.")
                    return self.success(
                        db,
                        200,
                        {"ok": True, "recovery_code": rotate_recovery(db, email)},
                    )
                if path == "/api/tickets":
                    if profile != "aluno":
                        raise Error(
                            403,
                            "Use uma conta de aluno para registrar uma manifestação.",
                        )
                    if data.get("confirmed") is not True:
                        raise Error(400, "Revise a manifestação e confirme o envio.")
                    submission = self.text(data, "submission_id", 16, 80)
                    if not re.fullmatch(r"[a-zA-Z0-9_-]{16,80}", submission):
                        raise Error(
                            400, "Identificação do envio inválida. Atualize a página."
                        )
                    subject, body = self.text(data, "subject", 5, 120), self.text(
                        data, "body", 20, 5000
                    )
                    kind, sector = self.text(data, "kind", 1, 30), self.text(
                        data, "sector", 1, 80
                    )
                    if kind not in TYPES or type(data.get("anonymous")) is not bool:
                        raise Error(400, "Tipo ou identificação inválidos.")
                    db.execute("BEGIN IMMEDIATE")
                    previous = db.execute(
                        "SELECT * FROM tickets WHERE email=? AND submission_id=?",
                        (email, submission),
                    ).fetchone()
                    if previous:
                        matches = all(
                            previous[key] == value
                            for key, value in {
                                "subject": subject,
                                "body": body,
                                "kind": kind,
                                "sector": sector,
                                "anonymous": int(data["anonymous"]),
                            }.items()
                        )
                        if not matches:
                            raise Error(
                                409,
                                "Este envio já foi usado com outro conteúdo. Abra uma nova manifestação.",
                            )
                        return self.success(
                            db, 200, {"id": previous["id"], "duplicate": True}
                        )
                    ticket_id = (
                        "CR-" + time.strftime("%Y") + "-" + secrets.token_hex(4).upper()
                    )
                    db.execute(
                        "INSERT INTO tickets(id,email,anonymous,kind,subject,sector,body,status,created,submission_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (
                            ticket_id,
                            email,
                            int(data["anonymous"]),
                            kind,
                            subject,
                            sector,
                            body,
                            "Recebida",
                            now,
                            submission,
                        ),
                    )
                    return self.success(db, 201, {"id": ticket_id})
                ticket_id = self.text(data, "id", 1, 40)
                ticket = db.execute(
                    "SELECT * FROM tickets WHERE id=?", (ticket_id,)
                ).fetchone()
                if not ticket or (profile == "aluno" and ticket["email"] != email):
                    raise Error(404, "Manifestação não encontrada.")
                if path == "/api/archive":
                    if profile not in ("supervisor", "diretor"):
                        raise Error(
                            403,
                            "Somente supervisor e diretor podem resolver e arquivar pelo atendimento.",
                        )
                    archived = data.get("archived")
                    if type(archived) is not bool:
                        raise Error(400, "Informe se deseja arquivar ou desarquivar.")
                    if bool(ticket["archived"]) == archived:
                        return self.success(db, 200, {"ok": True})
                    status = "Resolvida" if archived else "Em análise"
                    db.execute(
                        "UPDATE tickets SET archived=?,status=? WHERE id=?",
                        (int(archived), status, ticket_id),
                    )
                    message = (
                        "Manifestação resolvida e arquivada pelo atendimento."
                        if archived
                        else "Manifestação desarquivada e devolvida para análise pelo atendimento."
                    )
                    db.execute(
                        "INSERT INTO messages(ticket,author,body,created) VALUES (?,?,?,?)",
                        (ticket_id, "Sistema", message, now),
                    )
                    db.execute(
                        "INSERT INTO audit(actor,action,ticket,created) VALUES (?,?,?,?)",
                        (
                            email,
                            "Resolver e arquivar" if archived else "Desarquivar",
                            ticket_id,
                            now,
                        ),
                    )
                    return self.success(db, 200, {"ok": True})
                if path == "/api/identity":
                    if profile != "diretor":
                        raise Error(
                            403, "Somente o diretor pode consultar a autoria restrita."
                        )
                    reason = self.text(data, "reason", 20, 2000)
                    db.execute(
                        "INSERT INTO audit(actor,action,ticket,created,reason) VALUES (?,?,?,?,?)",
                        (email, "Consulta de autoria restrita", ticket_id, now, reason),
                    )
                    return self.success(
                        db, 200, {"email": email_for(ticket["email"], db)}
                    )
                if path == "/api/reply":
                    body = self.text(data, "body", 3, 5000)
                    db.execute(
                        "INSERT INTO messages(ticket,author,body,created) VALUES (?,?,?,?)",
                        (
                            ticket_id,
                            "Aluno" if profile == "aluno" else "Ouvidoria Campo Real",
                            body,
                            now,
                        ),
                    )
                    if ticket["archived"]:
                        db.execute(
                            "INSERT INTO messages(ticket,author,body,created) VALUES (?,?,?,?)",
                            (
                                ticket_id,
                                "Sistema",
                                "Manifestação desarquivada após nova mensagem.",
                                now,
                            ),
                        )
                    if profile != "aluno":
                        db.execute(
                            "UPDATE tickets SET status=?,archived=0 WHERE id=?",
                            ("Respondida", ticket_id),
                        )
                    elif ticket["status"] in ("Respondida", "Resolvida"):
                        db.execute(
                            "UPDATE tickets SET status=?,archived=0 WHERE id=?",
                            ("Em análise", ticket_id),
                        )
                    return self.success(db, 200, {"ok": True})
                if path == "/api/status":
                    status = self.text(data, "status", 1, 30)
                    allowed = (
                        {"Resolvida", "Em análise"}
                        if profile == "aluno"
                        else {"Em análise", "Respondida"}
                    )
                    if status not in allowed or (
                        status == "Respondida"
                        and not db.execute(
                            "SELECT 1 FROM messages WHERE ticket=? AND author='Ouvidoria Campo Real'",
                            (ticket_id,),
                        ).fetchone()
                    ):
                        raise Error(400, "Alteração de situação não permitida.")
                    db.execute(
                        "UPDATE tickets SET status=?,archived=? WHERE id=?",
                        (status, int(status == "Resolvida"), ticket_id),
                    )
                    db.execute(
                        "INSERT INTO messages(ticket,author,body,created) VALUES (?,?,?,?)",
                        (
                            ticket_id,
                            "Sistema",
                            f"Situação alterada para {status.lower()} pelo "
                            + ("aluno." if profile == "aluno" else "atendimento."),
                            now,
                        ),
                    )
                    return self.success(db, 200, {"ok": True})
                raise Error(404, "Operação não encontrada.")
        except Error as error:
            self.send(error.status, {"error": error.message})
        except (ValueError, TypeError):
            self.send(400, {"error": "Confira os dados enviados."})
        except Exception:
            self.send(500, {"error": "Não foi possível concluir. Tente novamente."})


def build_demo():
    """Monta a apresentação usando as mesmas telas do sistema, sem duplicar fontes."""
    html = ASSETS["index.html"]
    html = re.sub(
        r'<link\s+rel="stylesheet"\s+href="style.css"\s*/?>',
        lambda match: "<style>\n" + ASSETS["style.css"] + "\n</style>",
        html,
    )
    html = re.sub(r'<script\s+src="app.js"\s+defer></script>', "", html)
    html = html.replace(
        "</body>", "<script>\n" + ASSETS["app.js"] + "\n</script>\n</body>"
    )
    for name in ("azul", "branca"):
        filename = "assets/logo-" + name + ".svg"
        content = base64.b64encode(ASSETS[filename].encode()).decode()
        html = html.replace(filename, "data:image/svg+xml;base64," + content)
    return html


def backup_database():
    """Copia uma visão consistente do SQLite, inclusive com o servidor em uso."""
    initialize()
    directory = DB.parent / "backups"
    directory.mkdir(parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    filename = directory / (
        "ouvidoria-"
        + datetime.now().strftime("%Y%m%d-%H%M%S")
        + "-"
        + secrets.token_hex(2)
        + ".sqlite3"
    )
    try:
        with database() as source, sqlite3.connect(filename) as destination:
            source.backup(destination)
        os.chmod(filename, 0o600)
    except Exception:
        filename.unlink(missing_ok=True)
        raise
    return filename


def show_database_summary():
    """Mostra a estrutura e contagens, sem imprimir nomes, e-mails ou relatos."""
    initialize()
    print("Banco:", DB.resolve())
    with database() as db:
        check = db.execute("PRAGMA integrity_check").fetchone()[0]
        print("Integridade:", check)
        for table, description in (
            ("accounts", "Contas"),
            ("tickets", "Manifestações"),
            ("messages", "Mensagens"),
            ("audit", "Registros de auditoria"),
        ):
            count = db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
            print(f"{description}: {count}")
    print("Consulte BANCO_DE_DADOS.md e banco.sql para entender campos e relações.")


def local_addresses():
    """Sugere IPs do computador sem fazer conexão com serviços externos."""
    addresses = set()
    try:
        for entry in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            value = entry[4][0]
            address = ipaddress.ip_address(value)
            if address.is_private and not address.is_loopback:
                addresses.add(value)
    except OSError:
        pass
    return sorted(addresses)


def main():
    parser = argparse.ArgumentParser(
        description="Ouvidoria Campo Real — acesso com e-mail e senha."
    )
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument(
        "--contas", action="store_true", help="criar contas ou redefinir senhas"
    )
    actions.add_argument(
        "--demo", action="store_true", help="abrir a demonstração fictícia"
    )
    actions.add_argument(
        "--configurar", action="store_true", help="gerar o modelo opcional de .env"
    )
    actions.add_argument(
        "--rede-local",
        action="store_true",
        help="permitir acesso pelo PC e celular na mesma rede",
    )
    actions.add_argument(
        "--backup", action="store_true", help="criar uma cópia consistente do banco"
    )
    actions.add_argument(
        "--banco",
        action="store_true",
        help="consultar integridade e contagens do banco",
    )
    parser.add_argument("--ajuda", action="help", help="mostrar estas instruções")
    args = parser.parse_args()

    if args.contas:
        try:
            manage_accounts()
        except (EOFError, KeyboardInterrupt):
            print("\nMenu encerrado.")
        return

    if args.configurar:
        target = ROOT / ".env.example"
        if not target.exists():
            target.write_text(ASSETS["configuracao.env.example"], encoding="utf-8")
        print("Modelo:", target)
        print("O .env é opcional. Para testar no celular, use --rede-local.")
        return

    if args.demo:
        target = ROOT / "DEMONSTRACAO.html"
        target.write_text(build_demo(), encoding="utf-8")
        print("Demonstração fictícia:", target)
        webbrowser.open(target.resolve().as_uri())
        return

    if args.backup:
        print("Backup criado:", backup_database())
        print(
            "Guarde uma cópia protegida em outro local. O arquivo contém relatos sensíveis, embora os e-mails estejam cifrados."
        )
        print("Guarde também a chave separadamente:", KEY_PATH)
        print(
            "Sem a chave original, os e-mails desse backup não poderão ser recuperados."
        )
        return

    if args.banco:
        show_database_summary()
        return

    initialize()
    host = "0.0.0.0" if args.rede_local else os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"No computador: http://localhost:{port}")
    print("Endereço configurado:", APP_URL)
    if host == "0.0.0.0":
        for address in local_addresses():
            print(f"Na mesma rede: http://{address}:{port}")
        print(
            "No celular, use o IP do computador. Se não aparecer, consulte o IPv4 com ipconfig."
        )
        print(
            "Mantenha a rede como privada e permita Python no firewall apenas na rede privada."
        )
    else:
        print(
            "Para acesso pelo celular na mesma rede: python ouvidoria.py --rede-local"
        )
    print("Contas: python ouvidoria.py --contas | Encerrar: Ctrl+C")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor encerrado.")
    finally:
        server.server_close()


# Esquema do banco (também disponível em banco.sql).
SCHEMA_SQL = r"""
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
"""

# Telas do navegador, mantidas aqui para permitir baixar apenas este arquivo.
ASSETS = {
    "app.js": r"""let pendingTicket = null;
let identityTicketId = null;
("use strict");

const $ = (id) => document.getElementById(id);

const DEMO = location.protocol === "file:";

const statuses = ["Recebida", "Em análise", "Respondida", "Resolvida"];

const demoEmails = {
  aluno: "aluno.exemplo@camporeal.edu.br",
  supervisor: "supervisor.exemplo@camporeal.edu.br",
  diretor: "diretor.exemplo@camporeal.edu.br",
};

let user = null,
  tickets = [],
  activeId = null,
  registerMode = false,
  archiveView = false,
  toastTimer;

const escapeHTML = (text) =>
  String(text ?? "").replace(
    /[&<>"']/g,
    (x) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      })[x],
  );

const date = (value) =>
  new Date(value * 1e3).toLocaleString("pt-BR", {
    timeZone: "America/Sao_Paulo",
    dateStyle: "short",
    timeStyle: "short",
  });

const badge = (status) =>
  `<span class="badge ${["", "analysis", "answered", "solved"][statuses.indexOf(status)] || ""}">${escapeHTML(status)}</span>`;

function notify(message, error = false) {
  $("toast").textContent = (error ? "Atenção: " : "") + message;
  $("toast").className = "toast" + (error ? " error" : "");
  $("toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => ($("toast").hidden = true), 6500);
}

async function busy(button, task) {
  button.disabled = true;
  try {
    await task();
  } catch (error) {
    notify(error.message || "Não foi possível concluir.", true);
  } finally {
    button.disabled = false;
  }
}

function demoData() {
  try {
    return JSON.parse(localStorage.getItem("camporeal-demo-v1")) || seedDemo();
  } catch {
    return seedDemo();
  }
}

function saveDemo(data) {
  try {
    localStorage.setItem("camporeal-demo-v1", JSON.stringify(data));
  } catch {
    throw new Error(
      "O navegador bloqueou o armazenamento local. Abra o arquivo em outro navegador.",
    );
  }
}

function seedDemo() {
  const now = Date.now() / 1e3;
  return [
    {
      id: "CR-DEMO-001",
      email: demoEmails.aluno,
      anonymous: true,
      kind: "Reclamação",
      subject: "Iluminação no estacionamento",
      sector: "Infraestrutura",
      body: "A iluminação perto da saída do estacionamento precisa de manutenção. Seria possível verificar as lâmpadas desse trecho?",
      status: "Respondida",
      created: now - 172800,
      messages: [
        {
          author: "Ouvidoria Campo Real",
          body: "Exemplo de resposta: encaminhamos o pedido à manutenção. Você pode acompanhar e nos informar se o problema foi resolvido.",
          created: now - 86400,
        },
      ],
    },
    {
      id: "CR-DEMO-002",
      email: demoEmails.aluno,
      anonymous: false,
      kind: "Sugestão",
      subject: "Mais horários para grupos de estudo",
      sector: "Ensino e aprendizagem",
      body: "Gostaria de sugerir mais horários para utilização das salas por grupos de estudo durante o período de provas.",
      status: "Em análise",
      created: now - 86400,
      messages: [],
    },
    {
      id: "CR-DEMO-003",
      email: "outro.aluno@camporeal.edu.br",
      anonymous: true,
      kind: "Elogio",
      subject: "Atendimento da biblioteca",
      sector: "Geral",
      body: "Quero registrar um elogio pelo apoio da equipe da biblioteca na pesquisa dos materiais para as atividades.",
      status: "Recebida",
      created: now - 3600,
      messages: [],
    },
  ];
}

async function demoAPI(path, data) {
  if (path === "/api/me") {
    if (!user) throw new Error("Entre para continuar.");
    return user;
  }
  if (path === "/api/logout") {
    user = null;
    return {
      ok: true,
    };
  }
  const list = demoData().map((t) => ({
    ...t,
    archived: t.archived ?? t.status === "Resolvida",
  }));
  if (path === "/api/tickets" && !data)
    return list
      .filter((t) => user.role !== "aluno" || t.email === user.email)
      .map((t) => ({
        ...t,
        identity: !t.anonymous || user.role === "aluno" ? t.email : null,
        email: undefined,
      }));
  if (path === "/api/tickets") {
    const item = {
      ...data,
      id: "CR-DEMO-" + Math.random().toString(16).slice(2, 10).toUpperCase(),
      email: user.email,
      created: Date.now() / 1e3,
      status: "Recebida",
      archived: false,
      messages: [],
    };
    list.unshift(item);
    saveDemo(list);
    return {
      id: item.id,
    };
  }
  const item = list.find((t) => t.id === data.id);
  if (!item) throw new Error("Protocolo não encontrado.");
  if (path === "/api/identity") {
    if (user.role !== "diretor") throw new Error("Somente o diretor pode consultar.");
    if (!data.reason || data.reason.trim().length < 20)
      throw new Error("Escreva uma justificativa com pelo menos 20 caracteres.");
    item.identity_accesses = [
      ...(item.identity_accesses || []),
      { reason: data.reason.trim(), created: Date.now() / 1000 },
    ];
    saveDemo(list);
    return { email: item.email };
  }
  if (path === "/api/reply") {
    item.archived = false;
    item.messages.push({
      author: user.role === "aluno" ? "Aluno" : "Ouvidoria Campo Real",
      body: data.body,
      created: Date.now() / 1e3,
    });
    item.status = user.role === "aluno" ? "Em análise" : "Respondida";
  }
  if (path === "/api/status") {
    item.archived = data.status === "Resolvida";
    item.status = data.status;
    item.messages.push({
      author: "Sistema",
      body: "Situação alterada para " + data.status.toLowerCase() + ".",
      created: Date.now() / 1e3,
    });
  }
  if (path === "/api/archive") {
    if (user.role === "aluno") throw new Error("Somente a equipe pode arquivar.");
    item.archived = data.archived;
    item.status = data.archived ? "Resolvida" : "Em análise";
    item.messages.push({
      author: "Sistema",
      body: data.archived
        ? "Manifestação resolvida e arquivada pelo atendimento."
        : "Manifestação desarquivada para nova análise.",
      created: Date.now() / 1e3,
    });
  }
  saveDemo(list);
  return {
    ok: true,
  };
}

async function api(path, data) {
  if (DEMO) return demoAPI(path, data);
  const response = await fetch(path, {
    method: data ? "POST" : "GET",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": user?.csrf || "",
    },
    body: data ? JSON.stringify(data) : undefined,
  });
  const result = await response.json();
  if (!response.ok) {
    if (response.status === 401) loggedOut();
    throw new Error(result.error || "Não foi possível concluir a solicitação.");
  }
  return result;
}

function loggedOut() {
  user = null;
  tickets = [];
  activeId = null;
  archiveView = false;
  resetLogin();
  $("sectorFilter").value = "";
  $("search").value = "";
  $("statusFilter").value = "";
  $("workspace").hidden = true;
  $("welcome").hidden = false;
  $("how").hidden = false;
  $("account").replaceChildren();
  $("ticketList").replaceChildren();
  $("detailContent").replaceChildren();
  document.querySelectorAll("dialog[open]").forEach((dialog) => dialog.close());
}

async function loggedIn() {
  $("welcome").hidden = true;
  $("how").hidden = true;
  $("workspace").hidden = false;
  const student = user.role === "aluno";
  $("panelLabel").textContent = student ? "ÁREA DO ALUNO" : "GESTÃO DA OUVIDORIA";
  $("panelTitle").textContent = student
    ? "Minhas manifestações"
    : "Central de manifestações";
  $("panelDescription").textContent = student
    ? "Acompanhe cada conversa, do primeiro contato à solução."
    : "Acolha os relatos, acompanhe os protocolos e responda aos alunos.";
  archiveView = false;
  $("archivedTab").hidden = student;
  $("sectorFilterField").hidden = student;
  $("sectorFilter").value = "";
  $("search").value = "";
  $("statusFilter").value = "";
  $("newTicket").hidden = !student;
  $("account").innerHTML =
    `<strong>${escapeHTML(user.role)}</strong><span>${escapeHTML(user.email)}</span> <button class="text-button" id="manageRecovery" type="button">Código de recuperação</button> <button class="text-button" id="logout" type="button">Sair</button>`;
  $("manageRecovery").onclick = () => {
    $("rotateCodeForm").reset();
    $("rotateCodeDialog").showModal();
  };
  if (!DEMO && !user.has_recovery_code)
    notify(
      "Sua conta ainda não tem código de recuperação. Use Código de recuperação para gerar e guardar o seu.",
    );
  $("logout").onclick = (event) =>
    busy(event.currentTarget, async () => {
      await api("/api/logout", {});
      loggedOut();
    });
  await refresh();
}

async function refresh() {
  tickets = await api("/api/tickets");
  $("stats").innerHTML = [
    ["Total de manifestações", tickets.length],
    [
      "Em atendimento",
      tickets.filter((t) => ["Recebida", "Em análise"].includes(t.status)).length,
    ],
    ["Respondidas", tickets.filter((t) => t.status === "Respondida").length],
    ["Resolvidas", tickets.filter((t) => t.status === "Resolvida").length],
  ]
    .map(
      ([label, count]) =>
        `<div class="stat"><strong>${count}</strong><span>${label}</span></div>`,
    )
    .join("");
  const selectedSector = $("sectorFilter").value;
  const sectors = [
    ...new Set([
      ...Array.from($("sector").options, (option) => option.value),
      ...tickets.map((t) => t.sector),
    ]),
  ].sort((a, b) => a.localeCompare(b, "pt-BR"));
  $("sectorFilter").innerHTML =
    '<option value="">Todas as áreas</option>' +
    sectors
      .map(
        (sector) =>
          `<option value="${escapeHTML(sector)}">${escapeHTML(sector)}</option>`,
      )
      .join("");
  $("sectorFilter").value = selectedSector;
  renderList();
}

function renderList() {
  const search = $("search").value.trim().toLocaleLowerCase("pt-BR");
  const staff = user?.role !== "aluno";
  $("allTab").classList.toggle("active", !archiveView);
  $("archivedTab").classList.toggle("active", archiveView);
  $("allTab").setAttribute("aria-pressed", String(!archiveView));
  $("archivedTab").setAttribute("aria-pressed", String(archiveView));
  const filtered = tickets.filter(
    (t) =>
      (!staff || Boolean(t.archived) === archiveView) &&
      (!staff || !$("sectorFilter").value || t.sector === $("sectorFilter").value) &&
      (!$("statusFilter").value || t.status === $("statusFilter").value) &&
      (t.subject + " " + t.id).toLocaleLowerCase("pt-BR").includes(search),
  );
  $("ticketList").innerHTML = filtered.length
    ? filtered
        .map(
          (t) =>
            `<button type="button" class="ticket-card" data-ticket="${escapeHTML(t.id)}"><div><span class="protocol">${escapeHTML(t.id)}</span><h3>${escapeHTML(t.subject)}</h3><span class="meta">${escapeHTML(t.kind)} · ${escapeHTML(t.sector)} · ${date(t.created)}<br>${t.anonymous ? "Identidade restrita ao diretor" : "Manifestação identificada"}${user.role === "aluno" && t.identity_accesses?.length ? "<br>Consulta de autoria registrada pela direção" : ""}</span></div>${badge(t.status)}${t.archived ? '<span class="badge">Arquivada</span>' : ""}</button>`,
        )
        .join("")
    : `<div class="empty"><h3>${archiveView ? "Nenhuma manifestação arquivada nesta busca." : "Nenhuma manifestação por aqui."}</h3><p>Ajuste os filtros${staff ? " ou consulte a outra aba" : " ou crie uma nova manifestação"}.</p></div>`;
}

function showDetail(id) {
  activeId = id;
  const t = tickets.find((item) => item.id === id);
  if (!t) return;
  $("detailProtocol").textContent = t.id;
  $("detailSubject").textContent = t.subject;
  const identity = t.anonymous
    ? "Identidade restrita ao diretor"
    : `Identificado: ${t.identity || ""}`;
  $("detailContent").innerHTML =
    `${badge(t.status)}${t.archived ? ' <span class="badge">Arquivada</span>' : ""}<p class="meta">${escapeHTML(t.kind)} · ${escapeHTML(t.sector)} · ${date(t.created)}<br>${escapeHTML(identity)}</p><p class="detail-body">${escapeHTML(t.body)}</p><h3>Histórico de atendimento</h3>${t.messages.length ? t.messages.map((m) => `<div class="message ${m.author === "Ouvidoria Campo Real" ? "staff" : ""}"><strong>${escapeHTML(m.author)}</strong><span class="meta"> · ${date(m.created)}</span><p>${escapeHTML(m.body)}</p></div>`).join("") : '<p class="form-note">Aguardando atendimento. As respostas aparecerão aqui.</p>'}`;
  if (
    (user.role === "aluno" || user.role === "diretor") &&
    t.identity_accesses?.length
  ) {
    const notice = document.createElement("section");
    notice.className = "identity-notice";
    notice.innerHTML =
      "<h3>Consultas da direção à autoria</h3>" +
      t.identity_accesses
        .map(
          (event) =>
            `<p><strong>${date(event.created)}</strong><br>${escapeHTML(event.reason || "Consulta realizada na versão anterior, sem justificativa registrada.")}</p>`,
        )
        .join("");
    $("detailContent").append(notice);
  }
  $("detailActions").replaceChildren();
  if (user.role === "aluno") {
    action(t.status === "Resolvida" ? "Pedir nova análise" : "✓ Foi resolvido", () =>
      updateStatus(t.status === "Resolvida" ? "Em análise" : "Resolvida"),
    );
    if (t.status === "Respondida")
      action("Ainda não foi resolvido", () => updateStatus("Em análise"));
  } else {
    if (t.archived)
      action("Desarquivar e retomar atendimento", () => updateArchive(false));
    else {
      action("Marcar em análise", () => updateStatus("Em análise"));
      action("Resolver e arquivar", () => updateArchive(true));
    }
    if (user.role === "diretor" && t.anonymous)
      action("Justificar e consultar autoria", async () => {
        identityTicketId = activeId;
        $("identityReasonForm").reset();
        $("identityReasonDialog").showModal();
      });
  }
  $("replyForm").hidden = user.role !== "aluno" && Boolean(t.archived);
  $("replyForm").reset();
  if (!$("detailDialog").open) $("detailDialog").showModal();
}

function action(label, handler) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "button";
  button.textContent = label;
  button.onclick = () => busy(button, handler);
  $("detailActions").append(button);
}

async function updateStatus(status) {
  await api("/api/status", {
    id: activeId,
    status: status,
  });
  await refresh();
  showDetail(activeId);
  notify("Situação atualizada.");
}

async function updateArchive(archived) {
  await api("/api/archive", {
    id: activeId,
    archived: archived,
  });
  await refresh();
  $("detailDialog").close();
  notify(
    archived
      ? "Manifestação resolvida e movida para Arquivadas."
      : "Manifestação desarquivada e devolvida ao atendimento.",
  );
}

function setRegisterMode(enabled) {
  registerMode = enabled;
  $("confirmField").hidden = !enabled;
  $("confirmPassword").required = enabled;
  $("password").autocomplete = enabled ? "new-password" : "current-password";
  $("loginButton").textContent = enabled ? "Criar minha conta →" : "Entrar →";
  $("toggleRegister").textContent = enabled
    ? "Já tenho conta. Entrar"
    : "Primeiro acesso? Criar conta de aluno";
  $("forgotPassword").hidden = enabled;
  $("password").value = "";
  $("confirmPassword").value = "";
}

$("loginForm").onsubmit = (event) => {
  event.preventDefault();
  busy($("loginButton"), async () => {
    const email = $("email").value.trim().toLowerCase();
    const password = $("password").value;
    if (!/^[^\s@]+@camporeal\.edu\.br$/.test(email))
      throw new Error("Use seu e-mail @camporeal.edu.br.");
    if (registerMode && password !== $("confirmPassword").value)
      throw new Error("As senhas precisam ser iguais.");
    if (registerMode) {
      let registration = null;
      if (!DEMO) registration = await api("/api/register", { email, password });
      resetLogin();
      $("email").focus();
      notify(
        DEMO
          ? "Cadastro ilustrativo concluído. Digite novamente o e-mail e a senha para explorar."
          : "Conta criada. Digite novamente seu e-mail e sua senha para entrar.",
      );
      if (registration?.recovery_code) showRecoveryCode(registration.recovery_code);
      return;
    }
    if (DEMO) {
      user = {
        email: email,
        role: "aluno",
      };
    } else {
      await api("/api/login", {
        email: email,
        password: password,
      });
      user = await api("/api/me");
    }
    await loggedIn();
    resetLogin();
  });
};

function resetLogin() {
  $("loginForm").reset();
  setRegisterMode(false);
}

$("toggleRegister").onclick = () => setRegisterMode(!registerMode);

$("forgotPassword").onclick = () => {
  $("recoverForm").reset();
  $("recoverDialog").showModal();
};

$("newTicket").onclick = () => {
  $("ticketForm").reset();
  $("composeDialog").showModal();
};

$("ticketForm").onsubmit = (event) => {
  event.preventDefault();
  const payload = Object.fromEntries(new FormData(event.currentTarget));
  payload.anonymous = $("anonymous").checked;
  const random = Array.from(crypto.getRandomValues(new Uint8Array(16)), (value) =>
    value.toString(16).padStart(2, "0"),
  ).join("");
  pendingTicket = { ...payload, confirmed: true, submission_id: random };
  $("confirmTicketSummary").textContent =
    `${payload.kind} • ${payload.sector}\n${payload.subject}\n\n${payload.body}\n\n${payload.anonymous ? "Identidade restrita ao diretor. Qualquer consulta exigirá justificativa visível para você." : "Manifestação identificada para a equipe de atendimento."}`;
  $("confirmTicketDialog").showModal();
};
$("backToTicket").onclick = () => {
  pendingTicket = null;
  $("confirmTicketDialog").close();
};
$("confirmTicketForm").onsubmit = (event) => {
  event.preventDefault();
  busy($("confirmTicketSubmit"), async () => {
    if (!pendingTicket)
      throw new Error("Abra e revise a manifestação antes de confirmar.");
    const result = await api("/api/tickets", pendingTicket);
    pendingTicket = null;
    $("confirmTicketDialog").close();
    $("composeDialog").close();
    await refresh();
    showDetail(result.id);
    notify("Envio confirmado. Manifestação registrada com o protocolo: " + result.id);
  });
};

$("replyForm").onsubmit = (event) => {
  event.preventDefault();
  busy(event.submitter, async () => {
    await api("/api/reply", {
      id: activeId,
      body: $("replyBody").value.trim(),
    });
    await refresh();
    showDetail(activeId);
    notify("Mensagem enviada.");
  });
};

$("ticketList").onclick = (event) => {
  const card = event.target.closest("[data-ticket]");
  if (card) showDetail(card.dataset.ticket);
};

$("search").oninput = renderList;

$("statusFilter").onchange = renderList;

$("sectorFilter").onchange = renderList;

$("allTab").onclick = () => {
  archiveView = false;
  renderList();
};

$("archivedTab").onclick = () => {
  if (user?.role === "aluno") return;
  archiveView = true;
  renderList();
};

document
  .querySelectorAll("[data-close]")
  .forEach((button) => (button.onclick = () => $(button.dataset.close).close()));

function showRecoveryCode(code) {
  $("recoveryCodeText").textContent = code;
  $("savedRecoveryCode").checked = false;
  $("closeRecoveryCode").disabled = true;
  $("recoveryCodeDialog").showModal();
}
$("savedRecoveryCode").onchange = () => {
  $("closeRecoveryCode").disabled = !$("savedRecoveryCode").checked;
};
$("closeRecoveryCode").onclick = () => {
  if (!$("savedRecoveryCode").checked) return;
  $("recoveryCodeDialog").close();
  $("recoveryCodeText").textContent = "";
};
$("recoveryCodeDialog").oncancel = (event) => {
  if (!$("savedRecoveryCode").checked) {
    event.preventDefault();
    notify("Guarde o código e marque a confirmação antes de continuar.");
  }
};
$("recoveryCodeDialog").onclose = () => {
  $("recoveryCodeText").textContent = "";
};
$("recoverForm").onsubmit = (event) => {
  event.preventDefault();
  busy($("recoverSubmit"), async () => {
    if (DEMO)
      throw new Error(
        "A recuperação real funciona somente no servidor Python. Esta página é uma demonstração.",
      );
    const password = $("recoverPassword").value;
    if (password !== $("recoverConfirm").value)
      throw new Error("As novas senhas precisam ser iguais.");
    const result = await api("/api/recover", {
      email: $("recoverEmail").value.trim().toLowerCase(),
      recovery_code: $("recoverCode").value.trim(),
      password,
    });
    $("recoverForm").reset();
    loggedOut();
    showRecoveryCode(result.recovery_code);
    notify("Senha redefinida. Guarde o novo código e entre com sua nova senha.");
  });
};
$("rotateCodeForm").onsubmit = (event) => {
  event.preventDefault();
  busy($("rotateCodeSubmit"), async () => {
    if (DEMO) throw new Error("Códigos reais só podem ser gerados no servidor Python.");
    const result = await api("/api/recovery-code", {
      current_password: $("currentPassword").value,
    });
    $("rotateCodeForm").reset();
    $("rotateCodeDialog").close();
    user.has_recovery_code = true;
    showRecoveryCode(result.recovery_code);
  });
};
$("identityReasonForm").onsubmit = (event) => {
  event.preventDefault();
  busy($("identityReasonSubmit"), async () => {
    const id = identityTicketId;
    const result = await api("/api/identity", {
      id,
      reason: $("identityReason").value.trim(),
    });
    $("identityReasonDialog").close();
    $("identityReasonForm").reset();
    await refresh();
    showDetail(id);
    const note = document.createElement("p");
    note.className = "form-note";
    note.textContent =
      "Autoria: " +
      result.email +
      ". A consulta e a justificativa foram registradas para o aluno.";
    $("detailActions").append(note);
  });
};

$("recoverDialog").onclose = () => $("recoverForm").reset();
$("rotateCodeDialog").onclose = () => $("rotateCodeForm").reset();
$("identityReasonDialog").onclose = () => $("identityReasonForm").reset();
$("confirmTicketDialog").oncancel = () => {
  pendingTicket = null;
};

if (DEMO) {
  $("demoBanner").hidden = false;
  $("demoAccounts").hidden = false;
  $("loginButton").textContent = "Explorar como aluno →";
  $("password").required = false;
  document.querySelectorAll("[data-demo]").forEach(
    (button) =>
      (button.onclick = () =>
        busy(button, async () => {
          user = {
            email: demoEmails[button.dataset.demo],
            role: button.dataset.demo,
          };
          await loggedIn();
        })),
  );
} else {
  api("/api/me")
    .then(async (result) => {
      user = result;
      await loggedIn();
    })
    .catch((error) => {
      if (
        error.message &&
        !error.message.includes("Entre com") &&
        !error.message.includes("expirou")
      )
        notify(error.message, true);
    });
}
""",
    "assets/logo-azul.svg": r"""<!-- Reprodução vetorial de referência baseada na marca anexada; substituir pelo arquivo oficial para publicação. -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 680 335" role="img" aria-label="Centro Universitário Campo Real, excelência no ensino superior">
<!-- Estrela amarela da identidade visual. -->
<polygon fill="#ffdd00" points="575,0 606,66 678,74 625,123 639,197 575,160 509,197 523,123 470,74 544,66"/>
<!-- Nome superior e nome principal em fonte serifada. -->
<g fill="#004c70" text-anchor="middle" font-family="Georgia,Times New Roman,serif" font-weight="bold">
<text x="335" y="141" font-size="40">CENTRO</text>
<text x="335" y="187" font-size="40">UNIVERSITÁRIO</text>
<text x="340" y="282" font-size="98" textLength="675" lengthAdjust="spacingAndGlyphs">CAMPO REAL</text>
<text x="340" y="330" font-size="37" textLength="675" lengthAdjust="spacingAndGlyphs">EXCELÊNCIA NO ENSINO SUPERIOR</text>
</g>
</svg>""",
    "assets/logo-branca.svg": r"""<!-- Reprodução vetorial de referência baseada na marca anexada; substituir pelo arquivo oficial para publicação. -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 680 335" role="img" aria-label="Centro Universitário Campo Real, excelência no ensino superior">
<!-- Estrela amarela da identidade visual. -->
<polygon fill="#ffdd00" points="575,0 606,66 678,74 625,123 639,197 575,160 509,197 523,123 470,74 544,66"/>
<!-- Nome superior e nome principal em fonte serifada. -->
<g fill="#ffffff" text-anchor="middle" font-family="Georgia,Times New Roman,serif" font-weight="bold">
<text x="335" y="141" font-size="40">CENTRO</text>
<text x="335" y="187" font-size="40">UNIVERSITÁRIO</text>
<text x="340" y="282" font-size="98" textLength="675" lengthAdjust="spacingAndGlyphs">CAMPO REAL</text>
<text x="340" y="330" font-size="37" textLength="675" lengthAdjust="spacingAndGlyphs">EXCELÊNCIA NO ENSINO SUPERIOR</text>
</g>
</svg>""",
    "index.html": r"""<!doctype html>
<html lang="pt-BR">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Ouvidoria | Campo Real</title>
    <meta
      name="description"
      content="Ouvidoria Campo Real: manifeste-se e acompanhe seu atendimento."
    />
    <link rel="stylesheet" href="style.css" />
    <script src="app.js" defer></script>
  </head>
  <body>
    <div id="demoBanner" class="demo-banner" hidden>
      Demonstração local • Dados fictícios • Não envie informações pessoais.
    </div>
    <header class="header">
      <a class="brand" href="#inicio" aria-label="Campo Real, início">
        <img
          src="assets/logo-azul.svg"
          alt="Centro Universitário Campo Real"
          width="220"
          height="108"
        />
      </a>
      <div class="header-label">
        <span class="eyebrow">CENTRO UNIVERSITÁRIO</span>
        <strong>Ouvidoria</strong>
      </div>
      <div id="account" class="account"></div>
    </header>
    <main id="inicio">
      <section id="welcome" class="welcome">
        <div class="intro">
          <span class="eyebrow light">OUVIDORIA CAMPO REAL</span>
          <h1>
            Sua voz faz
            <br />
            parte da mudança
            <span>.</span>
          </h1>
          <p>
            Um espaço para ouvir você, acolher suas ideias e construir uma faculdade
            cada vez melhor.
          </p>
          <div class="intro-points">
            <span>✓ Escuta com respeito</span>
            <span>✓ Acompanhamento por protocolo</span>
          </div>
          <div class="intro-bottom">
            <span class="small-star" aria-hidden="true">✦</span>
            <p>
              Reclamações, críticas, sugestões e elogios.
              <br />
              <strong>Toda manifestação importa.</strong>
            </p>
          </div>
        </div>
        <div class="login-card">
          <span class="step-label">SEU ESPAÇO DE ESCUTA</span>
          <h2>Vamos conversar?</h2>
          <p>
            Entre com seu e-mail institucional e senha. Se ainda não tem conta,
            cadastre-se e depois faça o login.
          </p>
          <form id="loginForm">
            <label for="email">E-mail institucional</label>
            <input
              id="email"
              type="email"
              required
              maxlength="254"
              autocomplete="username"
            />
            <label for="password">Senha</label>
            <input
              id="password"
              type="password"
              required
              minlength="8"
              maxlength="128"
              autocomplete="current-password"
            />
            <div id="confirmField" hidden>
              <label for="confirmPassword">Confirmar senha</label>
              <input
                id="confirmPassword"
                type="password"
                minlength="8"
                maxlength="128"
                autocomplete="new-password"
              />
            </div>
            <button id="loginButton" class="button primary" type="submit">
              Entrar →
            </button>
            <button id="toggleRegister" type="button" class="text-button">
              Primeiro acesso? Criar conta de aluno
            </button>
            <button id="forgotPassword" type="button" class="text-button">
              Esqueci minha senha
            </button>
            <p id="authHint" class="form-note">
              Use seu e-mail @camporeal.edu.br. O cadastro verifica o domínio, mas não
              comprova a titularidade do e-mail.
            </p>
          </form>
          <div id="demoAccounts" class="demo-accounts" hidden>
            <p>Explore os perfis fictícios:</p>
            <button type="button" data-demo="aluno">Aluno</button>
            <button type="button" data-demo="supervisor">Supervisor</button>
            <button type="button" data-demo="diretor">Diretor</button>
          </div>
          <div class="privacy-note">
            <span aria-hidden="true">◈</span>
            <p>
              <strong>Você escolhe como se identificar.</strong>
              <br />
              Na opção anônima, sua identidade fica oculta para a equipe de atendimento
              e pode ser consultada somente pelo diretor. O login continua obrigatório.
            </p>
          </div>
        </div>
      </section>
      <section id="workspace" class="workspace" hidden>
        <div class="workspace-heading">
          <div>
            <span id="panelLabel" class="eyebrow">ÁREA DO ALUNO</span>
            <h1 id="panelTitle">Minhas manifestações</h1>
            <p id="panelDescription">
              Acompanhe cada conversa, do primeiro contato à solução.
            </p>
          </div>
          <button id="newTicket" class="button primary" type="button">
            ＋ Nova manifestação
          </button>
        </div>
        <div id="stats" class="stats"></div>
        <div class="toolbar">
          <div class="tabs" role="group" aria-label="Listas de manifestações">
            <button id="allTab" class="tab active" type="button" aria-pressed="true">
              Todas as manifestações
            </button>
            <button
              id="archivedTab"
              class="tab"
              type="button"
              aria-pressed="false"
              hidden
            >
              Arquivadas
            </button>
          </div>
          <div class="filters">
            <div id="sectorFilterField" hidden>
              <label class="sr-only" for="sectorFilter">
                Filtrar área da manifestação
              </label>
              <select id="sectorFilter">
                <option value="">Todas as áreas</option>
              </select>
            </div>
            <label class="sr-only" for="search">Buscar manifestações</label>
            <input
              id="search"
              type="search"
              placeholder="Buscar assunto ou protocolo"
            />
            <label class="sr-only" for="statusFilter">Filtrar situação</label>
            <select id="statusFilter">
              <option value="">Todas as situações</option>
              <option>Recebida</option>
              <option>Em análise</option>
              <option>Respondida</option>
              <option>Resolvida</option>
            </select>
          </div>
        </div>
        <div id="ticketList" class="ticket-list"></div>
      </section>
      <section id="how" class="how">
        <div>
          <span class="eyebrow">SIMPLES, DO COMEÇO AO FIM</span>
          <h2>Da sua voz à nossa ação.</h2>
        </div>
        <div class="how-step">
          <span>01</span>
          <h3>Conte o que aconteceu</h3>
          <p>Escolha o tipo de manifestação e compartilhe seu relato.</p>
        </div>
        <div class="how-step">
          <span>02</span>
          <h3>Acompanhe a resposta</h3>
          <p>Consulte o protocolo e converse com a ouvidoria.</p>
        </div>
        <div class="how-step">
          <span>03</span>
          <h3>Ajude a concluir</h3>
          <p>Informe se foi resolvido ou peça uma nova análise.</p>
        </div>
      </section>
    </main>
    <footer>
      <div class="footer-brand">
        <img src="assets/logo-branca.svg" alt="Campo Real" width="100" height="50" />
        <p>Ouvidoria</p>
      </div>
      <p>Escutar. Acolher. Transformar.</p>
    </footer>
    <dialog id="composeDialog">
      <div class="dialog-header">
        <div>
          <span class="eyebrow">ESTAMOS AQUI PARA OUVIR</span>
          <h2>Nova manifestação</h2>
        </div>
        <button
          class="close"
          data-close="composeDialog"
          type="button"
          aria-label="Fechar formulário"
        >
          ×
        </button>
      </div>
      <form id="ticketForm">
        <div class="form-row">
          <div>
            <label for="kind">Tipo de manifestação</label>
            <select id="kind" name="kind">
              <option>Reclamação</option>
              <option>Crítica</option>
              <option>Sugestão</option>
              <option>Elogio</option>
              <option>Solicitação</option>
            </select>
          </div>
          <div>
            <label for="sector">Área relacionada</label>
            <select id="sector" name="sector">
              <option>Geral</option>
              <option>Coordenação de curso</option>
              <option>Atendimento / Secretaria</option>
              <option>Infraestrutura</option>
              <option>Financeiro</option>
              <option>Ensino e aprendizagem</option>
              <option>Outros</option>
            </select>
          </div>
        </div>
        <label for="subject">Assunto</label>
        <input
          id="subject"
          name="subject"
          minlength="5"
          maxlength="120"
          placeholder="Resuma sua manifestação"
          required
        />
        <label for="body">Seu relato</label>
        <textarea
          id="body"
          name="body"
          minlength="20"
          maxlength="5000"
          rows="5"
          placeholder="Conte o que aconteceu e como podemos ajudar. Mínimo de 20 caracteres."
          required
        ></textarea>
        <label class="anonymous-option">
          <input id="anonymous" name="anonymous" type="checkbox" />
          <span>
            <strong>Enviar de forma anônima para o atendimento</strong>
            <small>
              Supervisores não verão seu e-mail. Somente o diretor poderá consultar sua
              identidade; a consulta ficará registrada. Evite escrever seu nome ou
              e-mail no relato.
            </small>
          </span>
        </label>
        <p class="form-note">
          Você poderá consultar o protocolo e receber respostas mesmo na opção anônima.
        </p>
        <button class="button primary" type="submit">Revisar e enviar →</button>
      </form>
    </dialog>
    <dialog id="detailDialog">
      <div class="dialog-header">
        <div>
          <span id="detailProtocol" class="eyebrow"></span>
          <h2 id="detailSubject"></h2>
        </div>
        <button
          class="close"
          data-close="detailDialog"
          type="button"
          aria-label="Fechar manifestação"
        >
          ×
        </button>
      </div>
      <div id="detailContent"></div>
      <div id="detailActions" class="detail-actions"></div>
      <form id="replyForm">
        <label for="replyBody">Escrever uma mensagem</label>
        <textarea
          id="replyBody"
          rows="3"
          minlength="3"
          maxlength="5000"
          required
          placeholder="Continue a conversa por aqui..."
        ></textarea>
        <button class="button primary" type="submit">Enviar mensagem →</button>
      </form>
    </dialog>

    <dialog id="recoverDialog">
      <div class="dialog-header">
        <div>
          <h2>Recuperar minha senha</h2>
          <p>Use o código privado que você guardou ao criar ou atualizar sua conta.</p>
        </div>
        <button
          class="close"
          data-close="recoverDialog"
          type="button"
          aria-label="Fechar recuperação"
        >
          ×
        </button>
      </div>
      <form id="recoverForm">
        <label for="recoverEmail">E-mail institucional</label>
        <input
          id="recoverEmail"
          type="email"
          maxlength="254"
          autocomplete="username"
          required
        />
        <label for="recoverCode">Código de recuperação</label>
        <input
          id="recoverCode"
          type="text"
          maxlength="120"
          autocomplete="off"
          spellcheck="false"
          required
        />
        <label for="recoverPassword">Nova senha</label>
        <input
          id="recoverPassword"
          type="password"
          minlength="8"
          maxlength="128"
          autocomplete="new-password"
          required
        />
        <label for="recoverConfirm">Confirme a nova senha</label>
        <input
          id="recoverConfirm"
          type="password"
          minlength="8"
          maxlength="128"
          autocomplete="new-password"
          required
        />
        <p class="form-note">
          O código é de uso único. Depois da recuperação, você receberá outro. Sem o
          código, peça ajuda ao responsável pela instalação; informar apenas o e-mail
          não permite trocar a senha.
        </p>
        <button id="recoverSubmit" class="button primary" type="submit">
          Redefinir senha
        </button>
      </form>
    </dialog>
    <dialog id="recoveryCodeDialog" aria-labelledby="recoveryCodeTitle">
      <h2 id="recoveryCodeTitle">Guarde seu código de recuperação</h2>
      <p>
        Este código permite recuperar sua conta sem e-mail de confirmação. Ele será
        mostrado somente agora. Não compartilhe com outras pessoas.
      </p>
      <pre class="private-code" id="recoveryCodeText"></pre>
      <p class="form-note">
        Guarde em um gerenciador de senhas ou outro local privado. O sistema armazena
        apenas a verificação do código, não consegue mostrar o código antigo novamente.
      </p>
      <label class="anonymous-option">
        <input id="savedRecoveryCode" type="checkbox" />
        <span>Guardei o código em um local seguro.</span>
      </label>
      <button id="closeRecoveryCode" class="button primary" type="button" disabled>
        Continuar
      </button>
    </dialog>
    <dialog id="rotateCodeDialog">
      <div class="dialog-header">
        <h2>Código de recuperação</h2>
        <button
          class="close"
          data-close="rotateCodeDialog"
          type="button"
          aria-label="Fechar"
        >
          ×
        </button>
      </div>
      <form id="rotateCodeForm">
        <p>
          Crie um código para sua conta existente ou substitua o anterior. O código
          antigo deixará de funcionar.
        </p>
        <label for="currentPassword">Confirme sua senha atual</label>
        <input
          id="currentPassword"
          type="password"
          maxlength="128"
          autocomplete="current-password"
          required
        />
        <button id="rotateCodeSubmit" class="button primary" type="submit">
          Gerar novo código
        </button>
      </form>
    </dialog>
    <dialog id="identityReasonDialog">
      <div class="dialog-header">
        <h2>Justificar consulta de autoria</h2>
        <button
          class="close"
          data-close="identityReasonDialog"
          type="button"
          aria-label="Cancelar consulta"
        >
          ×
        </button>
      </div>
      <form id="identityReasonForm">
        <p>
          A identidade será exibida somente para a direção. O aluno verá a data e a
          justificativa desta consulta. A manifestação continua anônima para o
          supervisor.
        </p>
        <label for="identityReason">Por que é necessário consultar a autoria?</label>
        <textarea
          id="identityReason"
          rows="4"
          minlength="20"
          maxlength="2000"
          required
        ></textarea>
        <p class="form-note">
          Use pelo menos 20 caracteres. Evite incluir nomes ou e-mails no texto da
          justificativa.
        </p>
        <button id="identityReasonSubmit" class="button primary" type="submit">
          Registrar justificativa e consultar
        </button>
      </form>
    </dialog>
    <dialog id="confirmTicketDialog">
      <h2>Confirmar envio da manifestação</h2>
      <div id="confirmTicketSummary" class="detail-body"></div>
      <p>
        Confira as informações antes de enviar. Depois da confirmação, seu protocolo
        será gerado.
      </p>
      <form id="confirmTicketForm">
        <div class="detail-actions">
          <button id="backToTicket" class="button" type="button">
            Voltar e revisar
          </button>
          <button id="confirmTicketSubmit" class="button primary" type="submit">
            Confirmar envio
          </button>
        </div>
      </form>
    </dialog>

    <div id="toast" class="toast" role="status" aria-live="polite" hidden></div>
  </body>
</html>
""",
    "style.css": r""":root {
  --blue: #004c70;
  --navy: #06344d;
  --yellow: #ffdd00;
  --ink: #17394b;
  --muted: #637683;
  --line: #dce5ea;
  --paper: #f5f8fa;
  --radius: 14px;
  font-family: Arial, Helvetica, sans-serif;
  color: var(--ink);
  background: var(--paper);
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  line-height: 1.5;
}

[hidden] {
  display: none !important;
}

button,
input,
textarea,
select {
  font: inherit;
}

button {
  cursor: pointer;
  min-height: 44px;
}

:focus-visible {
  outline: 3px solid #b08d00;
  outline-offset: 3px;
}

button:disabled {
  opacity: 0.6;
  cursor: wait;
}

.demo-banner {
  padding: 9px 20px;
  text-align: center;
  background: #fff4bc;
  color: #665100;
  font-size: 12px;
  font-weight: 700;
}

.header {
  min-height: 116px;
  padding: 15px 6%;
  background: white;
  display: flex;
  align-items: center;
  gap: 30px;
  border-bottom: 1px solid var(--line);
}

.brand img {
  display: block;
  width: 205px;
  height: 86px;
  object-fit: contain;
}

.header-label {
  border-left: 1px solid var(--line);
  padding-left: 28px;
}

.header-label strong {
  display: block;
  font-size: 24px;
  letter-spacing: -0.5px;
}

.eyebrow,
.step-label {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 1.8px;
}

.account {
  margin-left: auto;
  text-align: right;
  font-size: 12px;
  overflow-wrap: anywhere;
}

.account strong {
  display: block;
  color: var(--blue);
  text-transform: capitalize;
}

.welcome {
  max-width: 1320px;
  margin: 46px auto 0;
  display: grid;
  grid-template-columns: 1.14fr 1fr;
  padding: 0 48px;
}

.intro {
  padding: 56px 48px 36px;
  color: white;
  background: var(--blue);
  border-radius: 18px 0 0 18px;
  position: relative;
  overflow: hidden;
}

.intro:after {
  content: "✦";
  position: absolute;
  right: -56px;
  bottom: -170px;
  font-size: 440px;
  color: #ffffff08;
  pointer-events: none;
}

.light {
  color: #bed6e1;
}

h1 {
  font-size: 48px;
  line-height: 1.12;
  letter-spacing: -1.8px;
  margin: 24px 0;
}

h1 span {
  color: var(--yellow);
}

.intro > p {
  color: #d6e7ee;
  max-width: 350px;
  font-size: 16px;
  line-height: 1.7;
}

.intro-points {
  display: flex;
  flex-direction: column;
  gap: 9px;
  margin: 26px 0 40px;
  font-size: 12px;
  color: #e8f1f5;
}

.intro-bottom {
  display: flex;
  align-items: center;
  gap: 16px;
  border-top: 1px solid #ffffff28;
  padding-top: 22px;
  position: relative;
  z-index: 1;
}

.small-star {
  color: var(--yellow);
  font-size: 37px;
}

.intro-bottom p {
  font-size: 11px;
  color: #c6dce6;
  margin: 0;
  line-height: 1.8;
}

.login-card {
  background: white;
  border: 1px solid var(--line);
  border-left: 0;
  border-radius: 0 18px 18px 0;
  padding: 48px 44px 36px;
}

.step-label {
  color: var(--blue);
}

h2 {
  font-size: 28px;
  line-height: 1.2;
  letter-spacing: -0.8px;
  margin: 14px 0;
}

.login-card > p,
.workspace-heading p,
.how p {
  color: var(--muted);
  font-size: 13px;
}

#loginForm {
  margin-top: 28px;
}

label {
  display: block;
  font-size: 12px;
  font-weight: 700;
  margin: 15px 0 7px;
}

input:not([type="checkbox"]),
select,
textarea {
  width: 100%;
  border: 1px solid #cddae2;
  border-radius: 8px;
  padding: 12px 13px;
  background: white;
  color: var(--ink);
  font-size: 13px;
  min-height: 45px;
}

textarea {
  resize: vertical;
}

.button {
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 12px 19px;
  font-size: 12px;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 15px;
  background: white;
  color: var(--blue);
}

.primary {
  background: var(--blue);
  border-color: var(--blue);
  color: white;
}

.primary:hover {
  background: var(--navy);
}

#loginButton {
  width: 100%;
  margin-top: 18px;
  justify-content: space-between;
}

.text-button {
  border: 0;
  background: none;
  padding: 4px;
  color: var(--blue);
  font-size: 12px;
  text-decoration: underline;
}

.privacy-note {
  border-top: 1px solid var(--line);
  margin-top: 28px;
  padding-top: 20px;
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.privacy-note > span {
  color: #a88b00;
  font-size: 24px;
}

.privacy-note p {
  margin: 0;
  font-size: 11px;
  line-height: 1.7;
  color: var(--muted);
}

.privacy-note strong {
  color: var(--ink);
}

.demo-accounts {
  border: 1px dashed #c5ad3e;
  border-radius: 8px;
  padding: 10px;
  margin-top: 18px;
}

.demo-accounts p {
  font-size: 11px;
  margin: 0 0 5px;
}

.demo-accounts button {
  border: 0;
  background: #eef4f7;
  border-radius: 5px;
  color: var(--blue);
  padding: 6px 10px;
  margin: 2px;
  font-size: 11px;
}

.how {
  max-width: 1224px;
  margin: 42px auto 40px;
  padding: 0 48px;
  display: grid;
  grid-template-columns: 1.1fr 1fr 1fr 1fr;
  gap: 30px;
}

.how h2 {
  font-size: 23px;
  margin-top: 10px;
}

.how-step {
  border-left: 1px solid var(--line);
  padding-left: 24px;
}

.how-step > span {
  color: var(--blue);
  font-weight: 700;
  font-size: 12px;
  border-bottom: 3px solid var(--yellow);
  padding-bottom: 4px;
}

h3 {
  font-size: 13px;
  margin: 18px 0 6px;
}

.how-step p {
  margin: 0;
  font-size: 11px;
}

footer {
  border-top: 1px solid var(--line);
  display: flex;
  justify-content: space-between;
  padding: 18px 6%;
  color: #c6dce6;
  font-size: 11px;
  background: var(--navy);
  align-items: center;
}

footer span {
  color: #c4a300;
  margin: 0 7px;
}

.workspace {
  max-width: 1200px;
  margin: 42px auto;
  padding: 0 32px;
  min-height: 55vh;
}

.workspace-heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 20px;
}

.workspace h1 {
  font-size: 34px;
  margin: 10px 0;
  letter-spacing: -1px;
}

.stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin: 28px 0;
}

.stat {
  background: white;
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 18px 22px;
}

.stat strong {
  display: block;
  font-size: 29px;
  line-height: 1.2;
  color: var(--blue);
}

.stat span {
  color: var(--muted);
  font-size: 12px;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 15px;
  border-bottom: 1px solid var(--line);
  padding-bottom: 14px;
}

.tab {
  border: 0;
  background: none;
  color: var(--blue);
  border-bottom: 3px solid var(--yellow);
  font-weight: 700;
  font-size: 12px;
}

.filters {
  display: flex;
  gap: 10px;
}

.filters input {
  max-width: 230px;
}

.ticket-list {
  display: grid;
  gap: 12px;
  margin-top: 20px;
}

.ticket-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  text-align: left;
  background: white;
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 22px;
  width: 100%;
  color: var(--ink);
}

.ticket-card:hover {
  border-color: #5d94ad;
  box-shadow: 0 3px 12px #004c7009;
}

.ticket-card h3 {
  margin: 7px 0;
  font-size: 16px;
  overflow-wrap: anywhere;
}

.meta {
  color: var(--muted);
  font-size: 11px;
}

.protocol {
  color: var(--blue);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.5px;
}

.badge {
  display: inline-block;
  border-radius: 20px;
  padding: 5px 10px;
  background: #eef3f6;
  color: #526d7c;
  font-size: 10px;
  font-weight: 700;
  white-space: nowrap;
}

.badge.analysis {
  background: #fff4c9;
  color: #826a00;
}

.badge.answered {
  background: #e4f0fb;
  color: #235b8a;
}

.badge.solved {
  background: #e5f3eb;
  color: #28734c;
}

.empty {
  text-align: center;
  padding: 45px 20px;
  background: white;
  border: 1px dashed var(--line);
  border-radius: 10px;
  color: var(--muted);
}

dialog {
  border: 0;
  border-radius: 16px;
  padding: 30px;
  width: min(660px, 94vw);
  max-height: 90vh;
  color: var(--ink);
  box-shadow: 0 20px 90px #032c4960;
}

dialog::backdrop {
  background: #052c46a6;
}

.dialog-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.dialog-header h2 {
  overflow-wrap: anywhere;
  font-size: 25px;
}

.close {
  border: 0;
  background: #eef3f6;
  border-radius: 50%;
  width: 38px;
  min-height: 38px;
  flex-shrink: 0;
  font-size: 24px;
  color: var(--blue);
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.anonymous-option {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  padding: 16px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--paper);
}

.anonymous-option input {
  margin-top: 3px;
  width: 18px;
  height: 18px;
  accent-color: var(--blue);
  flex-shrink: 0;
}

.anonymous-option small {
  display: block;
  color: var(--muted);
  font-weight: 400;
  margin-top: 5px;
  font-size: 11px;
  line-height: 1.6;
}

.form-note {
  font-size: 11px;
  color: var(--muted);
}

.detail-body {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  background: var(--paper);
  border-radius: 10px;
  padding: 18px;
  font-size: 13px;
}

.message {
  border-left: 3px solid var(--line);
  padding: 9px 14px;
  margin: 15px 0;
  font-size: 13px;
  overflow-wrap: anywhere;
}

.message p {
  white-space: pre-wrap;
  margin: 7px 0;
}

.message.staff {
  border-color: var(--blue);
  background: #f2f7fa;
}

.detail-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 16px 0;
  border-top: 1px solid var(--line);
  margin-top: 20px;
}

.toast {
  position: fixed;
  bottom: 22px;
  left: 50%;
  transform: translateX(-50%);
  background: var(--navy);
  color: white;
  padding: 15px 22px;
  border-radius: 9px;
  box-shadow: 0 5px 22px #0002;
  max-width: min(580px, 92vw);
  font-size: 13px;
  z-index: 50;
}

.toast.error {
  background: #873c32;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

@media (max-width: 950px) {
  .welcome {
    padding: 0 24px;
  }
  .intro {
    padding: 40px 28px;
  }
  .login-card {
    padding: 36px 28px;
  }
  h1 {
    font-size: 39px;
  }
  .how {
    padding: 0 28px;
    gap: 18px;
  }
  .header {
    padding: 14px 24px;
    gap: 20px;
  }
  .brand img {
    width: 170px;
  }
  .header-label {
    padding-left: 20px;
  }
  .toolbar {
    align-items: flex-start;
    flex-direction: column;
  }
  .filters {
    width: 100%;
  }
  .filters input {
    max-width: none;
  }
}

@media (max-width: 650px) {
  .header {
    min-height: 95px;
    flex-wrap: wrap;
    gap: 12px;
  }
  .brand img {
    width: 145px;
    height: 65px;
  }
  .header-label {
    padding-left: 15px;
  }
  .header-label strong {
    font-size: 20px;
  }
  .eyebrow {
    font-size: 9px;
  }
  .account {
    width: 100%;
    text-align: left;
    border-top: 1px solid var(--line);
    padding-top: 8px;
  }
  .account strong {
    display: inline;
    margin-right: 10px;
  }
  .welcome {
    grid-template-columns: 1fr;
    margin-top: 22px;
    padding: 0 16px;
  }
  .intro {
    border-radius: 14px 14px 0 0;
    padding: 32px 26px;
  }
  .intro h1 {
    font-size: 38px;
  }
  .intro-points {
    margin-bottom: 22px;
  }
  .intro-bottom {
    padding-top: 18px;
  }
  .login-card {
    border-left: 1px solid var(--line);
    border-top: 0;
    border-radius: 0 0 14px 14px;
    padding: 30px 26px;
  }
  .how {
    grid-template-columns: 1fr;
    padding: 0 22px;
    margin-top: 30px;
  }
  .how-step {
    padding: 0 0 0 18px;
  }
  .how-step h3 {
    margin-top: 10px;
  }
  .workspace {
    padding: 0 16px;
    margin-top: 24px;
  }
  .workspace-heading {
    align-items: flex-start;
    flex-direction: column;
  }
  .workspace h1 {
    font-size: 29px;
  }
  .stats {
    grid-template-columns: 1fr 1fr;
    gap: 10px;
  }
  .stat {
    padding: 16px;
  }
  .filters {
    flex-direction: column;
  }
  .ticket-card {
    padding: 17px;
    gap: 8px;
    align-items: flex-start;
  }
  .ticket-card h3 {
    font-size: 14px;
  }
  .ticket-card > .badge {
    font-size: 9px;
  }
  .form-row {
    grid-template-columns: 1fr;
    gap: 0;
  }
  dialog {
    padding: 22px;
  }
  .detail-actions .button {
    flex: 1;
  }
  footer {
    padding: 16px 22px;
    gap: 12px;
    font-size: 10px;
  }
}

.footer-brand {
  display: flex;
  align-items: center;
  gap: 22px;
}

.footer-brand img {
  object-fit: contain;
}

#toggleRegister,
#forgotPassword {
  display: block;
  text-align: left;
  margin-top: 8px;
}

.tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
}

.tab {
  border-bottom-color: transparent;
}

.tab.active {
  border-bottom-color: var(--yellow);
}

.filters {
  flex-wrap: wrap;
}

#sectorFilterField {
  min-width: 170px;
  flex: 1;
}

.ticket-card {
  flex-wrap: wrap;
}

@media (max-width: 650px) {
  #sectorFilterField {
    width: 100%;
  }
}

/* As consultas à autoria permanecem visíveis no histórico do titular. */
.identity-notice {
  border: 1px solid #d0ae39;
  border-radius: 8px;
  background: #fff9e4;
  padding: 15px;
  margin: 16px 0;
  font-size: 13px;
}
.identity-notice p {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.private-code {
  user-select: all;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  background: #f1f5f8;
  padding: 16px;
  border: 1px solid #cddae2;
  border-radius: 8px;
  font: 16px monospace;
}
#recoveryCodeDialog p,
#recoverDialog p,
#rotateCodeDialog p,
#identityReasonDialog p {
  font-size: 13px;
  line-height: 1.7;
}
""",
    "configuracao.env.example": r"""# Configuração opcional. O padrão funciona apenas no próprio computador.
APP_URL=http://localhost:8000
HOST=127.0.0.1
PORT=8000

# Para testar no PC e no celular na mesma rede:
# python ouvidoria.py --rede-local
# No celular, abra http://IP_DO_COMPUTADOR:8000 (não use localhost).

# Em uma hospedagem HTTPS, preencha APP_URL com o endereço definitivo.
# Se houver mais de um endereço externo autorizado, separe por vírgula:
# ALLOWED_ORIGINS=https://ouvidoria.exemplo.edu.br,https://outro.exemplo.edu.br

# O caminho padrão é data/ouvidoria.sqlite3, ao lado do programa.
# Não altere DATABASE_PATH se quiser continuar usando o mesmo banco.

# A chave é criada fora do banco, em segredos/email.key.
# Não altere nem apague a chave de uma instalação existente.
# DATA_KEY_FILE=C:/caminho/protegido/email.key
""",
}


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, InvalidToken) as error:
        raise SystemExit(
            "Não foi possível iniciar com segurança: " + str(error)
        ) from None
