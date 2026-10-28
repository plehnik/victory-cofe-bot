"""Сервер мини-приложения Victory Cofe: отдаёт страницу + API для рулетки.

Запуск:  source venv/bin/activate && uvicorn server:app --port 8080
"""
import hmac
import hashlib
import json
import secrets
import datetime as dt
import logging
import random
import urllib.parse

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import config
import database as db

log = logging.getLogger("victory.server")

app = FastAPI()

# ---------- Проверка подписи Telegram (initData) ----------

def verify_init_data(init_data: str) -> dict | None:
    """Проверяет криптографическую подпись данных от Telegram Mini App.

    Возвращает dict с пользователем или None, если подпись не сходится.
    """
    try:
        parsed = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
    except Exception:
        return None
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        return None
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", config.BOT_TOKEN.encode(), hashlib.sha256).digest()
    calc = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, received_hash):
        return None
    user = json.loads(parsed.get("user", "{}"))
    return user


def get_user_from_request(request: Request) -> dict:
    init_data = request.headers.get("X-Telegram-Init-Data", "")
    user = verify_init_data(init_data)
    if not user or "id" not in user:
        raise HTTPException(401, "Подпись не прошла проверку")
    return user


# ---------- Отдача страницы ----------

@app.get("/")
async def index():
    return FileResponse("webapp/index.html")

app.mount("/static", StaticFiles(directory="webapp"), name="static")


# ---------- API ----------

@app.get("/api/me")
async def api_me(request: Request):
    tg = get_user_from_request(request)
    await db.add_user(tg["id"], tg.get("full_name", ""), tg.get("username"))
    user = await db.get_user(tg["id"])
    has_ticket = await db.has_active_ticket(tg["id"])
    codes = await db.active_codes(tg["id"])
    visit_code = f"VC-{tg['id']}"  # код визита для QR
    return {
        "name": tg.get("first_name", ""),
        "is_staff": bool(user and user[3]),
        "has_ticket": has_ticket,
        "visit_code": visit_code,
        "codes": [
            {"prize": p, "code": c, "expires": e} for p, c, e in codes
        ],
    }


@app.get("/api/prizes")
async def api_prizes():
    """Секторы колеса для анимации. Вероятности НЕ отдаём — клиенты не должны их знать."""
    return [{"label": label} for label, _ in config.PRIZES]


@app.post("/api/spin")
async def api_spin(request: Request):
    tg = get_user_from_request(request)
    tg_id = tg["id"]

    if not await db.consume_ticket(tg_id):
        raise HTTPException(403, "Нет билета")

    names = [p[0] for p in config.PRIZES]
    weights = [p[1] for p in config.PRIZES]
    prize = random.choices(names, weights=weights, k=1)[0]
    index = names.index(prize)

    await db.save_spin(tg_id, prize)

    code = None
    if "Почти" not in prize:
        code = db.generate_code()
        expires = (dt.datetime.now(dt.timezone.utc)
                   + dt.timedelta(days=config.CODE_TTL_DAYS))
        await db.save_code(tg_id, prize, code, expires.isoformat())
        expires = expires.isoformat()
    return {"index": index, "prize": prize, "code": code}


@app.post("/api/redeem")
async def api_redeem(request: Request):
    """Сотрудник сканирует QR клиента: body = {"visit_code": "VC-123456789"}"""
    tg = get_user_from_request(request)
    user = await db.get_user(tg["id"])
    if not (user and user[3]):
        raise HTTPException(403, "Только для сотрудников")
    body = await request.json()
    visit_code = body.get("visit_code", "")
    if not visit_code.startswith("VC-"):
        raise HTTPException(400, "Неверный код")
    client_id = int(visit_code[3:])
    ok = await db.issue_ticket(client_id)
    return {"ok": ok, "message": ("Билет выдан ✅" if ok
                                  else "У клиента уже есть неиспользованный билет")}


@app.post("/api/verify")
async def api_verify(request: Request):
    """Сотрудник проверяет промокод победителя: body = {"code": "VICTO-XXXXXX"}.

    Код одноразовый: после успешной проверки помечается использованным.
    """
    tg = get_user_from_request(request)
    user = await db.get_user(tg["id"])
    if not (user and user[3]):
        raise HTTPException(403, "Только для сотрудников")
    body = await request.json()
    code = (body.get("code") or "").strip().upper()
    if not code.startswith("VICTO-"):
        raise HTTPException(400, "Неверный формат: промокод начинается с VICTO-")
    res = await db.verify_code(code)
    if res is None:
        raise HTTPException(404, "Код не найден")
    if res["status"] == "used":
        raise HTTPException(400, f"Код уже использован (приз: {res['prize']})")
    if res["status"] == "expired":
        raise HTTPException(400, f"Срок кода истёк (приз: {res['prize']})")
    return {"ok": True, "prize": res["prize"],
            "message": f"Код подтверждён ✅ Приз: {res['prize']}"}
