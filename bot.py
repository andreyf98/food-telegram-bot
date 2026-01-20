import os
import base64
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from openai import OpenAI

# =========================
# КЛЮЧИ ИЗ ENV (Railway)
# =========================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not TELEGRAM_BOT_TOKEN or not OPENAI_API_KEY:
    raise RuntimeError("Не заданы переменные окружения TELEGRAM_BOT_TOKEN или OPENAI_API_KEY")

# =========================
# ИМЕНА ПОЛЬЗОВАТЕЛЕЙ
# =========================
USER_NAMES = {
    "Bhded": "Андрей Ильич",
    "Laguzers": "Палъюрич"
}

client = OpenAI(api_key=OPENAI_API_KEY)

# =========================
# ОБРАБОТКА ФОТО
# =========================
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("Получено фото")

    # Определяем пользователя
    username = update.message.from_user.username
    display_name = USER_NAMES.get(use
