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

# =========================
# ИМЕНА ПОЛЬЗОВАТЕЛЕЙ
# =========================
USER_NAMES = {
    "Bhded": "Андрей Ильич",
    "Laguzers": "Палъюрич",
    "fekolinakk": "Любимая жена",
}

client = OpenAI(api_key=OPENAI_API_KEY)

# =========================
# ОБРАБ
