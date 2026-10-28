# Конфигурация бота Victory Cofe
BOT_TOKEN = "9202554531:AAF7HlVhHUWZ_IRluqqotPfXHLS-pCJuSW8"

# HTTPS-адрес мини-приложения (Cloudflare Tunnel)
WEBAPP_URL = "https://occupation-pink-specify-strip.trycloudflare.com"

# Название кафе (для текстов)
CAFE_NAME = "Victory Coffee"

# ID владельца (можно узнать командой /myid в боте)
OWNER_ID = None

# Призы: (название, вероятность в %)
# В сумме должно быть 100
PRIZES = [
    ("Скидка 10% на следующий заказ", 30),
    ("Скидка 15% на следующий заказ", 25),
    ("Десерт в подарок", 10),
    ("Бесплатный кофе", 5),
    ("Почти получилось — повезёт в следующий раз", 30),
]

# Срок действия промокода, дней
CODE_TTL_DAYS = 30
