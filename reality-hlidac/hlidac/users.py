"""People who use the watcher: login, own rules, own ntfy topic and priority.

  python -m hlidac.users add Tomas --admin     # first account (prints the password)
  python -m hlidac.users add Petr              # a friend
  python -m hlidac.users list
  python -m hlidac.users passwd Petr           # new password
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import sys
from dataclasses import dataclass

from hlidac import db

PBKDF2_ITERATIONS = 200_000
# ntfy priorities: 3 = default, 4 = high, 5 = urgent (iPhone: time-sensitive, passes Focus)
PRIORITIES = {3: "normální", 4: "vysoká", 5: "nejvyšší"}
DEFAULT_PRIORITY = 4


@dataclass(frozen=True)
class User:
    id: int
    name: str
    is_admin: bool
    ntfy_topic: str | None
    priority: int


class UserError(ValueError):
    pass


# --- passwords -----------------------------------------------------------------------------

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt),
                                 PBKDF2_ITERATIONS).hex()
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iterations, salt, digest = stored.split("$")
        check = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt),
                                    int(iterations)).hex()
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(check, digest)


def generate_password() -> str:
    """Easy to type on a phone: 'k7mq-2xwd-9tbn'."""
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"
    return "-".join("".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(3))


def generate_topic() -> str:
    return "hlidac-" + secrets.token_urlsafe(12).replace("_", "x").replace("-", "y")


# --- storage -------------------------------------------------------------------------------

def _from_row(row: sqlite3.Row) -> User:
    return User(id=row["id"], name=row["name"], is_admin=bool(row["is_admin"]),
                ntfy_topic=row["ntfy_topic"], priority=row["priority"])


def list_users(conn: sqlite3.Connection) -> list[User]:
    return [_from_row(r) for r in conn.execute("SELECT * FROM users ORDER BY id")]


def get_user(conn: sqlite3.Connection, user_id: int) -> User | None:
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _from_row(row) if row else None


def admins(conn: sqlite3.Connection) -> list[User]:
    return [u for u in list_users(conn) if u.is_admin]


def authenticate(conn: sqlite3.Connection, name: str, password: str) -> User | None:
    row = conn.execute("SELECT * FROM users WHERE name = ? COLLATE NOCASE",
                       (name.strip(),)).fetchone()
    if row is None:
        verify_password(password, hash_password("x"))  # same timing for unknown names
        return None
    return _from_row(row) if verify_password(password, row["password_hash"]) else None


def create_user(conn: sqlite3.Connection, name: str, *, admin: bool = False,
                topic: str | None = None, priority: int = DEFAULT_PRIORITY,
                password: str | None = None) -> tuple[User, str]:
    """Returns the user and the plain password (show it once, it is not stored)."""
    name = name.strip()
    if not name:
        raise UserError("Jméno nesmí být prázdné.")
    if conn.execute("SELECT 1 FROM users WHERE name = ? COLLATE NOCASE", (name,)).fetchone():
        raise UserError(f"Uživatel „{name}“ už existuje.")
    password = password or generate_password()
    with conn:
        cur = conn.execute(
            "INSERT INTO users (name, password_hash, is_admin, ntfy_topic, priority, created_at)"
            " VALUES (?,?,?,?,?,?)",
            (name, hash_password(password), int(admin), topic or generate_topic(), priority,
             db.ts(db.utcnow())))
        user_id = cur.lastrowid
        if admin:  # rules created before accounts existed belong to the first admin
            conn.execute("UPDATE rules SET user_id = ? WHERE user_id IS NULL", (user_id,))
            conn.execute("UPDATE alerts SET user_id = ? WHERE user_id IS NULL", (user_id,))
    return get_user(conn, user_id), password


def update_user(conn: sqlite3.Connection, user_id: int, *, topic: str | None,
                priority: int) -> None:
    if priority not in PRIORITIES:
        raise UserError("Neplatná priorita.")
    with conn:
        conn.execute("UPDATE users SET ntfy_topic = ?, priority = ? WHERE id = ?",
                     (topic or None, priority, user_id))


def set_password(conn: sqlite3.Connection, user_id: int, password: str | None = None) -> str:
    password = password or generate_password()
    with conn:
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                     (hash_password(password), user_id))
    return password


def delete_user(conn: sqlite3.Connection, user_id: int) -> None:
    user = get_user(conn, user_id)
    if user and user.is_admin and len(admins(conn)) == 1:
        raise UserError("Posledního správce nejde smazat.")
    with conn:
        conn.execute("DELETE FROM rules WHERE user_id = ?", (user_id,))
        conn.execute("UPDATE alerts SET user_id = NULL WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))


# --- CLI -----------------------------------------------------------------------------------

def main() -> None:
    from hlidac import config
    cfg = config.load()
    conn = db.connect(cfg.db_path)
    args = sys.argv[1:]
    try:
        if args[:1] == ["add"] and len(args) >= 2:
            admin = "--admin" in args
            first_topic = cfg.ntfy_topics[0] if cfg.ntfy_topics and not list_users(conn) else None
            user, password = create_user(conn, args[1], admin=admin, topic=first_topic)
            print(f"Vytvořen uživatel {user.name}{' (správce)' if admin else ''}")
            print(f"  heslo:      {password}")
            print(f"  ntfy kanál: {user.ntfy_topic}")
        elif args == ["list"]:
            for u in list_users(conn):
                print(f"{u.id}. {u.name}{' (správce)' if u.is_admin else ''} · "
                      f"ntfy {u.ntfy_topic} · priorita {PRIORITIES.get(u.priority)}")
        elif args[:1] == ["passwd"] and len(args) == 2:
            row = conn.execute("SELECT id FROM users WHERE name = ? COLLATE NOCASE",
                               (args[1],)).fetchone()
            if not row:
                sys.exit(f"Uživatel {args[1]} neexistuje.")
            print(f"Nové heslo: {set_password(conn, row['id'])}")
        else:
            sys.exit(__doc__)
    except UserError as exc:
        sys.exit(f"Chyba: {exc}")


if __name__ == "__main__":
    main()
