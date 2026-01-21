import os
import json
import logging
import asyncio
import base64
import random
from datetime import date, timedelta
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
# COMMENTS
# ========================
SPECIAL_COMMENTS = [
    "Кайфани как следует, роднулька ❤️ 🎉",
    "Сегодня можно 😌 💎",
    "Живём один раз — кайфуй ❤️ 🥇",
    "Вот ради этого и старались 🎉",
    "Да и правильно, иногда надо 💎",
    "Чистый кайф, без оправданий 🥇",
    "Вот за это мы и любим еду 🎉",
    "Чистое гастрономическое счастье 💎",
    "Такое надо уважать 🥇",
]

NORMAL_COMMENTS = [
    "Хороший приём пищи.",
    "Выглядит сбалансированно.",
    "Нормальный, спокойный вариант.",
    "Всё на месте.",
    "Хорошая еда без лишнего.",
    "Выглядит по-человечески.",
    "Похоже на сытный приём пищи.",
    "Выглядит разумно.",
    "Всё выглядит вполне ок.",
    "По-домашнему.",
    "Выглядит уютно.",
    "Спокойная еда.",
    "Приятный вариант.",
    "Такое обычно заходит.",
    "Простая и понятная еда.",
    "Ничего лишнего.",
    "Еда как еда — и это хорошо.",
    "Сытно, но без перебора.",
    "Хорошо вписывается в день.",
]

ALCOHOL_KEYWORDS = ["пиво", "пивко", "ipa", "lager", "stout", "эль", "алкоголь"]

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

def is_stopped(user_id):
    data = load_data()
    return data.get("stopped", {}).get(str(user_id), False)

def set_stopped(user_id, value: bool):
    data = load_data()
    data.setdefault("stopped", {})
    data["stopped"][str(user_id)] = value
    save_data(data)

def add_meal(user_id, meal):
    data = load_data()
    today = str(date.today())
    data.setdefault(str(user_id), {})
    data[str(user_id)].setdefault(today, [])
    data[str(user_id)][today].append(meal)
    save_data(data)

def get_last_meal(user_id):
    data = load_data()
    today = str(date.today())
    meals = data.get(str(user_id), {}).get(today, [])
    return meals[-1] if meals else None

def update_last_meal(user_id, meal):
    data = load_data()
    today = str(date.today())
    data[str(user_id)][today][-1] = meal
    save_data(data)

# ========================
# LOGIC
# ========================
def is_special(text: str, calories: int) -> bool:
    if calories >= 700:
        return True
    t = text.lower()
    return any(k in t for k in ALCOHOL_KEYWORDS)

def choose_comment(text, calories):
    return random.choice(SPECIAL_COMMENTS if is_special(text, calories) else NORMAL_COMMENTS)

def extract_calories(text):
    total = 0
    for line in text.splitlines():
        if "ккал" in line:
            digits = "".join(c for c in line if c.isdigit())
            if digits:
                total += int(digits)
    return total

# ========================
# GPT
# ========================
async def analyze(prompt, image_base64=None):
    content = [{"type": "text", "text": prompt}]
    if image_base64:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}
        })

    response = await asyncio.to_thread(
        client.chat.completions.create,
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": content}],
        max_tokens=500,
    )
    return response.choices[0].message.content.strip()

# ========================
# COMMANDS
# ========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_stopped(update.effective_user.id, False)
    await update.message.reply_text(
        "Бот активен.\n\n"
        "Команды:\n"
        "/today — калории за сегодня\n"
        "/week — статистика за 7 дней\n"
        "/fix — исправить последний приём пищи\n"
        "/reset — сбросить день\n"
        "/stop — временно отключить бота"
    )

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_stopped(update.effective_user.id, True)
    await update.message.reply_text("Бот остановлен. Напиши /start, чтобы включить снова.")

# ========================
# HANDLERS
# ========================
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_stopped(update.effective_user.id):
        return

    file = await update.message.photo[-1].get_file()
    image_bytes = await file.download_as_bytearray()
    image_base64 = base64.b64encode(image_bytes).decode()

    prompt = """
Определи блюда на фото, их вес и калории.

Формат:
Блюда:
• название — вес — ккал

Итого: ккал
"
