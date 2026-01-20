import os
import json
import logging
import asyncio
import base64
import random
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
# USER NAMES
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
# POSITIVE PHRASES
# ========================
POSITIVE_PHRASES = [
    "Вкуснотища!",
    "Пальчики оближешь.",
    "Выглядит очень аппетитно.",
    "Зачётная тарелка.",
    "Вот это подход к еде.",
    "Отличный выбор.",
    "Смотрится с душой.",
    "Еда как надо.",
    "Уважение повару.",
    "Прямо захотелось попробовать.",
    "Классика, которая не подводит.",
    "Выглядит по-домашнему.",
    "Надёжный вариант.",
    "Сытно и по делу.",
    "Хорошая порция.",
    "Аппетитно без лишнего.",
    "Это мы одобряем.",
    "Визуально — 🔥",
    "Умеешь выбирать.",
    "Еда, которая радует.",
    "Похоже на удачный приём пищи.",
    "Без лишних слов — вкусно.",
    "Выглядит убедительно.",
    "Приятно глазу.",
    "Честная еда.",
    "С таким не ошибёшься.",
    "Видно, что с настроением.",
    "Еда, которая делает день лучше.",
    "Хороший момент для такого блюда.",
    "Серьёзный кандидат на «вкусно».",
    "Это точно не зря.",
    "Выглядит очень достойно.",
    "Простая радость.",
    "Порция внушает доверие.",
    "Выглядит правильно.",
    "Тут комментарии излишни.",
    "Приятный выбор.",
    "С таким можно жить.",
    "Аппетит говорит сам за себя.",
    "Выглядит уютно.",
    "Сытный вариант.",
    "Вкусно выглядит, спору нет.",
    "Хорошая еда без лишнего пафоса.",
    "Похоже на удачный приём пищи.",
    "Тут всё на месте.",
    "Визуально очень ок.",
    "Приятно видеть такую тарелку.",
    "Похоже, было вкусно.",
    "Это явно доставляет удовольствие.",
    "Хороший выбор для этого момента.",
]

# ========================
# DATA STORAGE
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
        "Можно добавить подпись.\n\n"
        "/today — калории за сегодня"
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

    await update.message.reply_text(
        "Сегодня:\n\n" + "\n".join(lines) + f"\n\nИтого: {total} ккал"
    )

# ========================
# PHOTO HANDLER
# ========================
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
Фото используй для оценки веса и порции.

Подпись пользователя:
\"\"\"{caption}\"\"\"

Ответ дай СТРОГО в формате:

Блюдо:
Вес порции (г):
Калорийность блюда (ккал):
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
            max_tokens=300,
        )

        answer = response.choices[0].message.content.strip()
        lines = [l for l in answer.splitlines() if l.strip()]

        dish = lines[0].replace("Блюдо:", "").strip()
        calories = int(
            lines[2]
            .replace("Калорийность блюда (ккал):", "")
            .strip()
            .split()[0]
        )

        # если комментарий пустой — подставляем фразу
        if len(lines) < 5 or not lines[4].replace("Комментарий:", "").strip():
            phrase = random.choice(POSITIVE_PHRASES)
            lines.append(f"Комментарий: {phrase}")

        final_answer = "\n".join(lines)

        add_entry(update.effective_user.id, dish, calories)

        await update.message.reply_text(final_answer)

    except RateLimitError:
        await update.message.reply_text("⏳ Я сейчас перегружен. Попробуй чуть позже.")

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
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            lambda u, c: u.message.reply_text("Пришли фото еды 📸")
        )
    )

    print("Bot started")
    app.run_polling()

if __name__ == "__main__":
    main()