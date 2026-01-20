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
    raise RuntimeError(
        "Не заданы переменные окружения TELEGRAM_BOT_TOKEN или OPENAI_API_KEY"
    )

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
# ОБРАБОТКА ФОТО
# =========================
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("Получено фото")

    # Определяем пользователя
    username = update.message.from_user.username
    display_name = USER_NAMES.get(username, "друг")

    # Получаем фото
    photo = update.message.photo[-1]
    file = await photo.get_file()
    image_bytes = await file.download_as_bytearray()

    image_base64 = base64.b64encode(image_bytes).decode()

    prompt = f"""
Ты — пищевой ассистент.
Обращайся к пользователю по имени: {display_name}.

Определи блюдо на фото и оцени калорийность.

Формат ответа:
Название:
Описание:
Калорийность (ккал):
Точность оценки: низкая / средняя / высокая

Если не уверен — прямо скажи.
"""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
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

    await update.message.reply_text(
        f"{display_name}, вот что у тебя на тарелке:\n\n"
        + response.choices[0].message.content
    )

# =========================
# ЗАПУСК БОТА
# =========================
app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

print("Бот запущен")
app.run_polling()
