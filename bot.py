import os
import json
import logging
import asyncio
import base64
from datetime import date
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
# ENV
# ========================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not TELEGRAM_BOT_TOKEN or not OPENAI_API_KEY:
    raise RuntimeError("Env variables not set")

client = OpenAI(api_key=OPENAI_API_KEY)

DATA_FILE = "data.json"

# ========================
# LOGGING
# ========================
logging.basicConfig(level=logging.INFO)

# ========================
# USERS
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
# DATA HELPERS
# ========================
def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def add_entry(user_id, dish, calories):
    data = load_data()
    today = str(date.today())

    data.setdefault(str(user_id), {})
    data[str(user_id)].setdefault(today, [])

    data[str(user_id)][today].append({
        "dish": dish,
        "calories": calories
    })

    save_data(data)

# ========================
# COMMANDS
# ========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Пришли фото еды 🍽️\n"
        "Я запишу калории.\n\n"
        "Команда /today — сколько съел сегодня."
    )

async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = load_data()
    today_key = str(date.today())

    meals = data.get(str(user_id), {}).get(today_key, [])

    if not meals:
        await update.message.reply_text("Сегодня пока ничего не записано.")
        return

    total = sum(m["calories"] for m in meals)

    lines = [f"• {m['dish']} — {m['calories']} ккал" for m in meals]
    text = "Сегодня ты съел:\n\n" + "\n".join(lines)
    text += f"\n\nИтого: {total} ккал"

    await update.message.reply_text(text)

# ========================
# PHOTO
# ========================
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = get_user_name(update)
    caption = update.message.caption or ""

    if update.message.photo:
        file = await update.message.photo[-1].get_file()
    elif update.message.document and update.message.document.mime_type.startswith("image/"):
        file = await update.message.document.get_file()
    else:
        return

    image_bytes = await file.download_as_bytearray()
    image_base64 = base64.b64encode(image_bytes).decode()

    prompt = f"""
Ты — эксперт по питанию.

Если пользователь указал блюдо текстом — считай это фактом.

Подпись:
\"\"\"{caption}\"\"\"

Определи блюдо, оцени вес порции и посчитай
ИТОГОВУЮ калорийность блюда.

Ответ дай СТРОГО в формате:
Блюдо:
Итого калорий (ккал):
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
            max_tokens=200,
        )

        answer = response.choices[0].message.content

        lines = answer.splitlines()
        dish = lines[0].replace("Блюдо:", "").strip()
        calories = int(
            lines[1]
            .replace("Итого калорий (ккал):", "")
            .strip()
            .split()[0]
        )

        add_entry(update.effective_user.id, dish, calories)

        await update.message.reply_text(
            f"{name}, записал:\n{dish} — {calories} ккал"
        )

    except RateLimitError:
        await update.message.reply_text("⏳ Лимит запросов. Попробуй позже.")

# ========================
# MAIN
# ========================
def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("today", today))
    app.add_handler(
        MessageHandler(filters.PHOTO | filters.Document.IMAGE, handle_photo)
    )
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND,
                       lambda u, c: u.message.reply_text("Пришли фото еды 📸"))
    )

    print("Bot started")
    app.run_polling()

if __name__ == "__main__":
    main()