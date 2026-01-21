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

ALCOHOL_KEYWORDS = [
    "пиво", "пивко", "ipa", "lager", "stout", "эль", "алкоголь"
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

def delete_last_meal(user_id):
    data = load_data()
    today = str(date.today())
    meals = data.get(str(user_id), {}).get(today, [])
    if not meals:
        return False
    meals.pop()
    save_data(data)
    return True

# ========================
# LOGIC
# ========================
def is_special(text: str, calories: int) -> bool:
    if calories >= 700:
        return True
    t = text.lower()
    return any(k in t for k in ALCOHOL_KEYWORDS)

def choose_comment(text, calories):
    if is_special(text, calories):
        return random.choice(SPECIAL_COMMENTS)
    return random.choice(NORMAL_COMMENTS)

# ========================
# GPT HELPERS
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

def extract_calories(text):
    total = 0
    for line in text.splitlines():
        if "ккал" in line:
            digits = "".join(c for c in line if c.isdigit())
            if digits:
                total += int(digits)
    return total

# ========================
# COMMANDS
# ========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Пришли фото еды или просто напиши, что ты съел.\n\n"
        "Команды:\n"
        "/today — калории за сегодня\n"
        "/week — статистика за 7 дней\n"
        "/delete — удалить последний приём пищи\n"
        "/fix — исправить последний приём пищи\n"
        "/reset — сбросить весь день"
    )

async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    today_key = str(date.today())
    meals = data.get(str(update.effective_user.id), {}).get(today_key, [])

    if not meals:
        await update.message.reply_text("Сегодня пока ничего не записано.")
        return

    total = sum(m["calories"] for m in meals)
    lines = [f"• {m['title']} — {m['calories']} ккал" for m in meals]

    await update.message.reply_text(
        "Сегодня:\n\n" + "\n".join(lines) + f"\n\nИтого: {total} ккал"
    )

async def week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    uid = str(update.effective_user.id)

    lines = []
    total_week = 0

    for i in range(6, -1, -1):
        day = date.today() - timedelta(days=i)
        key = str(day)
        calories = sum(
            m["calories"]
            for m in data.get(uid, {}).get(key, [])
        )
        total_week += calories
        lines.append(f"{day.strftime('%a')}: {calories} ккал")

    await update.message.reply_text(
        "Последние 7 дней:\n\n"
        + "\n".join(lines)
        + f"\n\nИтого: {total_week} ккал"
        + f"\nСреднее: {total_week // 7} ккал/день"
    )

async def delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if delete_last_meal(update.effective_user.id):
        await update.message.reply_text("Последний приём пищи удалён.")
    else:
        await update.message.reply_text("Удалять нечего.")

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    uid = str(update.effective_user.id)
    today_key = str(date.today())

    if uid in data and today_key in data[uid]:
        del data[uid][today_key]
        save_data(data)
        await update.message.reply_text("Сегодняшний день очищен.")
    else:
        await update.message.reply_text("Сегодня пока нечего сбрасывать.")

async def fix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    last = get_last_meal(update.effective_user.id)
    if not last:
        await update.message.reply_text("Нет приёма пищи для исправления.")
        return

    context.user_data["fixing"] = True
    await update.message.reply_text(
        "Опиши, что нужно исправить.\n"
        "Например: добавить помидор, сосисок было 2."
    )

# ========================
# HANDLERS
# ========================
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    caption = update.message.caption or ""
    file = await update.message.photo[-1].get_file()
    image_bytes = await file.download_as_bytearray()
    image_base64 = base64.b64encode(image_bytes).decode()

    prompt = """
Если на фото несколько блюд — перечисли каждое.
Если одно — тоже.

Формат:
Блюда:
• название — вес — ккал

Итого: ккал
"""

    answer = await analyze(prompt + "\n" + caption, image_base64)
    calories = extract_calories(answer)
    comment = choose_comment(answer, calories)

    add_meal(
        update.effective_user.id,
        {"title": "Приём пищи", "calories": calories, "raw": answer}
    )

    await update.message.reply_text(answer + "\n\n" + comment)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if context.user_data.get("fixing"):
        context.user_data["fixing"] = False
        last = get_last_meal(update.effective_user.id)

        prompt = f"""
Вот исходное описание приёма пищи:
{last['raw']}

Исправь его согласно инструкции:
{text}

Верни результат в том же формате.
"""

        answer = await analyze(prompt)
        calories = extract_calories(answer)
        comment = choose_comment(answer, calories)

        update_last_meal(
            update.effective_user.id,
            {"title": "Приём пищи (исправлено)", "calories": calories, "raw": answer}
        )

        await update.message.reply_text(answer + "\n\n" + comment)
        return

    prompt = f"""
Пользователь съел:
{text}

Если не указано количество — возьми среднюю порцию человека.

Формат:
Блюда:
• название — вес — ккал

Итого: ккал
"""

    answer = await analyze(prompt)
    calories = extract_calories(answer)
    comment = choose_comment(answer, calories)

    add_meal(
        update.effective_user.id,
        {"title": text, "calories": calories, "raw": answer}
    )

    await update.message.reply_text(answer + "\n\n" + comment)

# ========================
# MAIN
# ========================
def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("today", today))
    app.add_handler(CommandHandler("week", week))
    app.add_handler(CommandHandler("delete", delete))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("fix", fix))

    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("Bot started")
    app.run_polling()

if __name__ == "__main__":
    main()
