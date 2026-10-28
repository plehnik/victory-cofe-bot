"""Victory Cofe — Telegram-бот с рулеткой бонусов за визит.

Запуск:  source venv/bin/activate && python bot.py
Остановка: Ctrl+C
"""
import asyncio
import logging
import random
import datetime as dt

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes,
)

import config
import database as db

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO
)
log = logging.getLogger("victory")

# ---------- Команды ----------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    await db.add_user(u.id, u.full_name, u.username)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎡 Открыть рулетку", web_app=WebAppInfo(url=config.WEBAPP_URL))],
    ])
    # Удаляем предыдущее приветствие если есть
    old_msg_id = context.user_data.get('last_start_msg_id')
    if old_msg_id:
        try:
            await update.bot.delete_message(u.id, old_msg_id)
        except Exception:
            pass
    msg = await update.message.reply_html(
        f"👋 Добро пожаловать в <b>{config.CAFE_NAME}</b>!\n\n"
        "Бонусная рулетка за визит:\n\n"
        "1️⃣ Оплати заказ → покажи код визита официанту\n"
        "2️⃣ Получи билет → крути рулетку\n"
        "3️⃣ Забирай приз на следующий визит 🎯",
        reply_markup=kb,
    )
    context.user_data['last_start_msg_id'] = msg.message_id

async def cmd_myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Твой Telegram ID: {update.effective_user.id}")

async def cmd_addstaff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if config.OWNER_ID is None or update.effective_user.id != config.OWNER_ID:
        await update.message.reply_text("Эта команда только для владельца.")
        return
    if not context.args:
        await update.message.reply_text("Использование: /addstaff <Telegram ID>")
        return
    try:
        tg_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID должен быть числом. Пример: /addstaff 123456789")
        return
    await db.add_user(tg_id, "Сотрудник", None)
    async with __import__("aiosqlite").connect(db.DB_PATH) as conn:
        await conn.execute("UPDATE users SET is_staff=1 WHERE tg_id=?", (tg_id,))
        await conn.commit()
    await update.message.reply_text(f"✅ Пользователь {tg_id} теперь сотрудник.")

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if config.OWNER_ID is None or update.effective_user.id != config.OWNER_ID:
        await update.message.reply_text("Эта команда только для владельца.")
        return
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)).isoformat()
    async with __import__("aiosqlite").connect(db.DB_PATH) as conn:
        cur = await conn.execute(
            "SELECT COUNT(*) FROM spins WHERE created_at >= ?", (since,)
        )
        spins_day = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT COUNT(*) FROM spins")
        spins_total = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT COUNT(*) FROM users")
        users = (await cur.fetchone())[0]
    await update.message.reply_text(
        f"📊 Статистика\nСпинов за 24ч: {spins_day}\nСпинов всего: {spins_total}\nПользователей: {users}"
    )

# ---------- Кнопки ----------

async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    u = update.effective_user

    if q.data == "spin":
        await q.message.reply_text("🎡 Открываю рулетку…")
        await open_wheel(update, context)

    elif q.data == "myprizes":
        codes = await db.active_codes(u.id)
        if not codes:
            await q.message.reply_text("🎁 Активных призов пока нет. Крути рулетку после визита!")
            return
        lines = []
        for prize, code, expires in codes:
            exp = dt.datetime.fromisoformat(expires).strftime("%d.%m.%Y")
            lines.append(f"🎫 <b>{prize}</b>\nКод: <code>{code}</code> (до {exp})")
        await q.message.reply_html("\n\n".join(lines))

# ---------- Рулетка ----------

def pick_prize() -> str:
    names = [p[0] for p in config.PRIZES]
    weights = [p[1] for p in config.PRIZES]
    return random.choices(names, weights=weights, k=1)[0]

async def open_wheel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user

    if not await db.has_active_ticket(u.id):
        await update.effective_message.reply_text(
            "🎫 У тебя нет билета.\n\n"
            "Билет выдаёт официант после оплаты заказа — покажи ему свой код визита."
        )
        return

    if not await db.consume_ticket(u.id):
        await update.effective_message.reply_text("Билет уже использован.")
        return

    prize = pick_prize()

    # Логируем и выдаём код (кроме утешительного сектора)
    await db.save_spin(u.id, prize)
    code_text = ""
    if "Почти" not in prize:
        code = db.generate_code()
        expires = (dt.datetime.now(dt.timezone.utc)
                   + dt.timedelta(days=config.CODE_TTL_DAYS)).isoformat()
        await db.save_code(u.id, prize, code, expires)
        code_text = f"\n\nТвой промокод: <code>{code}</code>\n(действует до {expires[:10]})"

    await update.effective_message.reply_html(
        f"🎉 <b>Выигрыш: {prize}</b>{code_text}"
    )

# ---------- Запуск ----------

async def on_startup(app):
    await db.init_db()
    log.info("База данных готова.")

def main():
    app = Application.builder().token(config.BOT_TOKEN).post_init(on_startup).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("myid", cmd_myid))
    app.add_handler(CommandHandler("addstaff", cmd_addstaff))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CallbackQueryHandler(on_button))
    log.info("Бот запущен. Ctrl+C — остановить.")
    app.run_polling()

if __name__ == "__main__":
    main()
