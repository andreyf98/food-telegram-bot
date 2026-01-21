import os
import json
import logging
import asyncio
import base64
import random
from datetime import date, datetime
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

logging.basicConfig(level=logging.INFO)

# ========================
# PHRASES
# ========================
NORMAL_MEAL_PHRASES = [
    "Хороший приём пищи.",
    "Выглядит сбалансированно.",
    "Нормальный, спокойный вариант.",
    "Всё на месте.",
    "Хорошая еда без лишнего.",
    "Выглядит по-человечески.",
    "Похоже на сытный приём пищи.",
    "Такой вариант часто работает.",
    "Выглядит разумно.",
    "Всё выглядит вполне ок.",
    "По-домашнему.",
    "Выглядит уютно.",
    "Спокойная еда.",
    "Приятный вариант.",
    "Такое обычно заходит.",
    "Видно, что с настроением.",
    "Простая и понятная еда.",
    "Выглядит привычно.",
    "Ничего лишнего.",
    "Еда как еда — и это хорошо.",
    "Аппетитно выглядит.",
    "Хороший выбор на сейчас.",
    "С таким не прогадаешь.",
    "Выглядит аккуратно.",
    "Вполне удачный вариант.",
    "Сытно, но без перебора.",
    "Спокойный приём пищи.",
    "Всё выглядит логично.",
    "Неплохая тарелка.",
    "Хорошо вписывается в день.",
]

SPECIAL_MEAL_PHRASES = [
    "Кайфани как следует, роднулька ❤️😌",
    "Сегодня можно, роднулька 😌🍻",
    "Живём один раз — кайфуй ❤️🔥",
    "Вот ради этого и старались 😎",
    "Да и правильно, иногда надо 🤝",
    "Чистый кайф, без оправданий 🔥",
    "Такое надо уважать 👌",
    "Красиво живёшь, роднулька 😎",
    "Такое не каждый день — и слава богу",
    "Вот за это мы и любим еду",
    "Чистое гастрономическое счастье",
]

MORNING_MEAL_PHRASES = [
    "Отличное начало дня.",
    "Вот так и надо начинать утро.",
    "Завтрак чемпионов.",
    "Утро удалось.",
    "С таким завтраком день пойдёт.",
    "Доброе утро начинается здесь.",
    "Правильный старт.",
    "Утро стало добрее.",
    "Хороший заряд на день.",
]

EVENING_MEAL_PHRASES = [
    "Отличный финал дня.",
    "Вечер можно считать удавшимся.",
    "Самое время расслабиться.",
    "Хороший ужин — половина счастья.",
    "После такого ужина день отпускает.",
    "Вечерняя классика.",
    "Ужин как надо.",
    "Хороший способ закрыть день.",
    "Вечер стал уютнее.",
    "После такого можно спокойно отдыхать.",
]

SPECIAL_KEYWORDS = [
    "пиво", "пивко", "ipa", "lager", "stout", "эль",
    "алкоголь", "бургер", "пицца", "фри", "картофель фри",
    "торт", "десерт"
]

# ========================
# DATA
# ========================
def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def add_entry(user_id, title, calories):
    data = load_data()
    today = str(date.today())
    data.setdefault(str(user_id), {})
    data[str(user_id)].setdefault(today, [])
    data[str(user_id)][today].append({
        "dish": title,
        "calories": calories
    })
    save_data(data)

def is_special_case(text: str, calories: int) -> bool:
    if calories >= 800:
        return True
    t = text.lower()
    return any(k in t for k in SPECIAL_KEYWORDS)

def get_time_phrase():
    hour = datetime.now().hour
    if hour < 11:
        return random.choice(MORNING_MEAL_PHRASES)
    if hour >= 18:
        return random.choice(EVENING_MEAL_PHRASES)
    return None

# ========================
# COMMANDS
# ========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Пришли фото еды 🍽️\n"
        "Можно добавить подпись.\n\n"
        "Команды:\n"
        "• /today — калории за сегодня\n"
        "• /reset — сбросить сегодняшний счётчик"
    )

async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user_id = str(update.effective_user.id)
    today_key = str(date.today())
    meals = data.get(user_id, {}).get(today_key, [])

    if not meals:
        await update.message.reply_text("Сегодня пока ничего не записано.")
        return

    total = sum(m["calories"] for m in meals)
    lines = [f"• {m['dish']} — {m['calories']} ккал" for m in meals]

    await update.message.reply_text(
        "Сегодня:\n\n" + "\n".join(lines) + f"\n\nИтого: {total} ккал"
    )

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user_id = str(update.effective_user.id)
    today_key = str(date.today())

    if user_id in data and today_key in data[user_id]:
        del data[user_id][today_key]
        save_data(data)
        await update.message.reply_text("Готово. Сегодняшний счётчик сброшен.")
    else:
        await update.message.reply_text("Сегодня пока нечего сбрасывать.")

# ========================
# PHOTO
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

Если на фото одно блюдо — опиши его.
Если несколько блюд — раздели и посчитай каждое.

Подпись пользователя:
\"\"\"{caption}\"\"\"

Формат:
Блюда:
• название — вес/объём — ккал

Итого (ккал):
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

        answer = response.choices[0].message.content.strip()

        total_calories = 0
        for line in answer.splitlines():
            if "ккал" in line:
                digits = "".join(c for c in line if c.isdigit())
                if digits:
                    total_calories += int(digits)

        add_entry(update.effective_user.id, "Приём пищи", total_calories)

        phrases = []
        if is_special_case(answer, total_calories):
            phrases.append(random.choice(SPECIAL_MEAL_PHRASES))
        else:
            phrases.append(random.choice(NORMAL_MEAL_PHRASES))

        time_phrase = get_time_phrase()
        if time_phrase:
            phrases.append(time_phrase)

        await update.message.reply_text(answer + "\n\n" + "\n".join(phrases))

    except RateLimitError:
        await update.message.reply_text("⏳ Я сейчас перегружен. Попробуй чуть позже.")

# ========================
# MAIN
# ========================
def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("today", today))
    app.add_handler(CommandHandler("reset", reset))

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