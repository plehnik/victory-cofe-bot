"""База данных: SQLite (один файл). Работает без сервера."""
import aiosqlite
import secrets
import string
import datetime as dt

DB_PATH = "victory.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                tg_id INTEGER PRIMARY KEY,
                name TEXT,
                username TEXT,
                is_staff INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                created_at TEXT,
                used_at TEXT
            );
            CREATE TABLE IF NOT EXISTS spins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                prize TEXT,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                prize TEXT,
                code TEXT UNIQUE,
                expires_at TEXT,
                used_at TEXT
            );
        """)
        await db.commit()

async def get_user(tg_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT * FROM users WHERE tg_id=?", (tg_id,))
        return await cur.fetchone()

async def add_user(tg_id: int, name: str, username: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (tg_id, name, username) VALUES (?,?,?)",
            (tg_id, name, username),
        )
        await db.commit()

async def has_active_ticket(tg_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id FROM tickets WHERE user_id=? AND used_at IS NULL",
            (tg_id,),
        )
        return await cur.fetchone() is not None

async def issue_ticket(tg_id: int) -> bool:
    """Выдаёт билет. Возвращает False, если у клиента уже есть неиспользованный."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id FROM tickets WHERE user_id=? AND used_at IS NULL",
            (tg_id,),
        )
        if await cur.fetchone():
            return False
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        await db.execute(
            "INSERT INTO tickets (user_id, created_at) VALUES (?,?)",
            (tg_id, now),
        )
        await db.commit()
        return True

async def consume_ticket(tg_id: int) -> bool:
    """Сжигает билет. Атомарно: два параллельных запроса дадут только один спин."""
    async with aiosqlite.connect(DB_PATH) as db:
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        cur = await db.execute(
            "UPDATE tickets SET used_at=? WHERE user_id=? AND used_at IS NULL",
            (now, tg_id),
        )
        await db.commit()
        return cur.rowcount > 0

async def save_spin(tg_id: int, prize: str):
    async with aiosqlite.connect(DB_PATH) as db:
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        await db.execute(
            "INSERT INTO spins (user_id, prize, created_at) VALUES (?,?,?)",
            (tg_id, prize, now),
        )
        await db.commit()

async def save_code(tg_id: int, prize: str, code: str, expires_at: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO codes (user_id, prize, code, expires_at) VALUES (?,?,?,?)",
            (tg_id, prize, code, expires_at),
        )
        await db.commit()

async def active_codes(tg_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT prize, code, expires_at FROM codes WHERE user_id=? AND used_at IS NULL",
            (tg_id,),
        )
        return await cur.fetchall()

async def verify_code(code: str):
    """Проверка промокода сотрудником: атомарно помечает код использованным.

    Возвращает None (код не найден) или {"status": ..., "prize": ...},
    где status: "ok" (подтверждён и сожжён), "used" (уже использован),
    "expired" (истёк).
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT prize, expires_at, used_at FROM codes WHERE code=?", (code,)
        )
        row = await cur.fetchone()
        if not row:
            return None
        prize, expires_at, used_at = row
        if used_at:
            return {"status": "used", "prize": prize}
        try:
            exp = dt.datetime.fromisoformat(expires_at)
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=dt.timezone.utc)
        except ValueError:
            exp = None
        if exp and exp < dt.datetime.now(dt.timezone.utc):
            return {"status": "expired", "prize": prize}
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        # атомарно: второй параллельный запрос уже не сожжёт код повторно
        cur = await db.execute(
            "UPDATE codes SET used_at=? WHERE code=? AND used_at IS NULL",
            (now, code),
        )
        await db.commit()
        if cur.rowcount == 0:
            return {"status": "used", "prize": prize}
        return {"status": "ok", "prize": prize}

def generate_code() -> str:
    """Промокод вида VICTO-XXXXXX"""
    alphabet = string.ascii_uppercase + string.digits
    letters = "".join(secrets.choice(alphabet) for _ in range(6))
    return f"VICTO-{letters}"
