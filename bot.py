import os
import logging
import asyncio
import base64
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
# OpenAI client
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
# User names
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
# /start
# ========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = get_user_name(update)
    await update.message.reply_text(
        f"{name}, пришли фото еды — я скажу, что это и сколько там калорий 🍽️"
    )

# ========================
# TEXT handler
# ========================
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Пришли фото еды 📸"
    )

# ========================
# PHOTO handler (MAIN)
# ========================
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = get_user_name(update)

    # Берём фото максимального размера
    photo = update.message.photo[-1]
    file = await photo.get_file()
    image_bytes = await file.download_as_bytearray()

    image_base64 = base64.b64encode(image_bytes).decode()

    prompt = f"""
Ты — ассистент по питанию.
Обращайся к пользователю: {name}.

Определи блюдо на фото и оцени калорийность.

Формат ответа:
Название:
Описание:
Примерная калорийность (ккал):
Точность оценки: низкая / средняя / высокая

Если не уверен — скажи прямо.
"""

    # ❗ OpenAI в отдельном потоке
    response = await asyncio.to_thread(
        client.chat.completions.create,
        model="gpt-4o-mini",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_base64}"
                        },
                    },
                ],
            }
        ],
        max_tokens=300,
    )

    answer = response.choices[0].message.content

    await update.message.reply_text(
        f"{name}, вот что у тебя на тарелке:\n\n{answer}"
    )

# ========================
# MAIN
# ========================
def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("Bot started")
    app.run_polling()

if __name__ == "__main__":
    main()
