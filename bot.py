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
from openai import RateLimitError

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
# /start
# ========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = get_user_name(update)
    await update.message.reply_text(
        f"{name}, пришли фото еды.\n"
        f"Можешь добавить подпись, например:\n"
        f"«это вареники с картошкой» 🍽️"
    )

# ========================
# PHOTO HANDLER
# ========================
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = get_user_name(update)

    # Получаем подпись пользователя (если есть)
    user_caption = update.message.caption or ""

    # Получаем файл
    if update.message.photo:
        file = await update.message.photo[-1].get_file()
    elif (
        update.message.document
        and update.message.document.mime_type
        and update.message.document.mime_type.startswith("image/")
    ):
        file = await update.message.document.get_file()
    else:
        return

    image_bytes = await file.download_as_bytearray()
    image_base64 = base64.b64encode(image_bytes).decode()

    prompt = f"""
Ты — эксперт по питанию.

ВАЖНО:
- Если пользователь явно указал блюдо текстом — СЧИТАЙ ЭТО ФАКТОМ.
- Не спорь с пользователем.
- Фото используй для оценки веса и порции.

Подпись пользователя (если есть):
\"\"\"{user_caption}\"\"\"

Задача:
1. Определи блюдо (или используй подпись).
2. Оцени примерный вес порции по фото.
3. Укажи калорийность на 100 г.
4. Рассчитай ОБЩУЮ калорийность блюда.
5. Укажи точность оценки: низкая / средняя / высокая.

Формат ответа СТРОГО такой:
Блюдо:
Вес порции (г):
Калорийность на 100 г (ккал):
Итого калорий (ккал):
Точность оценки:
Комментарий:
"""

    try:
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
            max_tokens=400,
        )

        answer = response.choices[0].message.content

        await update.message.reply_text(
            f"{name}, вот оценка твоего блюда:\n\n{answer}"
        )

    except RateLimitError:
        await update.message.reply_text(
            "⏳ Я сейчас перегружен. Подожди немного и попробуй снова."
        )

# ========================
# TEXT HANDLER
# ========================
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Пришли фото еды 📸\n"
        "Можешь добавить подпись, чтобы уточнить блюдо."
    )

# ========================
# MAIN
# ========================
def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    # Фото ОБЯЗАТЕЛЬНО выше текста
    app.add_handler(
        MessageHandler(filters.PHOTO | filters.Document.IMAGE, handle_photo)
    )

    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)
    )

    print("Bot started")
    app.run_polling()

if __name__ == "__main__":
    main()