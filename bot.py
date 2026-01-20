import os
import logging
import asyncio
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    CommandHandler,
    filters,
)
from openai import OpenAI

# ========================
# ENV VARIABLES
# ========================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN not set")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY not set")

# ========================
# OpenAI client (SYNC)
# ========================
client = OpenAI(api_key=OPENAI_API_KEY)

# ========================
# Logging
# ========================
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# ========================
# User name mapping
# ========================
USER_NAMES = {
    "bhded": "Андрей Ильич",
    "laguzers": "Палъюрич",
    "fekolinakk": "Любимая жена",
}

def get_user_name(update: Update) -> str:
    user = update.effective_user
    if user and user.username:
        return USER_NAMES.get(user.username.lower(), user.first_name)
    return "друг"

# ========================
# Handlers
# ========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = get_user_name(update)
    await update.message.reply_text(f"{name}, бот работает. Напиши сообщение.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    name = get_user_name(update)

    prompt = f"Пользователь ({name}) пишет: {text}"

    # ❗ ВАЖНО: OpenAI вызов в отдельном потоке
    response = await asyncio.to_thread(
        client.chat.completions.create,
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Ты дружелюбный помощник."},
            {"role": "user", "content": prompt},
        ],
    )

    answer = response.choices[0].message.content
    await update.message.reply_text(answer)

# ========================
# Main
# ========================
def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    print("Bot started")
    app.run_polling()

if __name__ == "__main__":
    main()
