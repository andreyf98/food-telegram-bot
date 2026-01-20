import os
import logging
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    filters,
)
from openai import OpenAI

# ========================
# ENV VARIABLES (Railway)
# ========================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not TELEGRAM_BOT_TOKEN or not OPENAI_API_KEY:
    raise RuntimeError("TELEGRAM_BOT_TOKEN or OPENAI_API_KEY not set")

# ========================
# OpenAI client
# ========================
client = OpenAI(api_key=OPENAI_API_KEY)

# ========================
# Logging
# ========================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# ========================
# User name mapping
# ========================
USER_NAMES = {
    "Bhded": "Андрей Ильич",
    "Laguzers": "Палъюрич",
    "fekolinakk": "Любимая жена",
}

def get_user_name(update: Update) -> str:
    user = update.effective_user
    if user and user.username and user.username in USER_NAMES:
        return USER_NAMES[user.username]
    return user.first_name if user else "друг"

# ========================
# Handlers
# ========================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    name = get_user_name(update)

    prompt = f"Пользователь ({name}) пишет: {text}"

    response = client.chat.completions.create(
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

    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    print("Bot started")
    app.run_polling()

if __name__ == "__main__":
    main()
